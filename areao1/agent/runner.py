"""Runs the agent (ADR 0005 §5–6): budgets, live event fan-out, run records and chat conversations.

Every run is saved to ``agent/runs/<id>.json``. Chat turns also go to ``agent/conversations/<id>.json``. The
history is replayed into each turn, so no transcript lives outside the workspace.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from areao1.agent.guardrails import guard_answer, log_refusal
from areao1.agent.prompt import SYSTEM_PROMPT
from areao1.agent.redact import redact
from areao1.agent.routing import Route, route, table
from areao1.agent.search_policy import SearchPolicy
from areao1.agent.tools import RunContext, build_tools
from areao1.core import clock
from areao1.core.models import (
    AgentRun,
    Conversation,
    ConversationMessage,
    RunUsage,
    TimelineItem,
    utcnow,
)
from areao1.core.workspace import NotFound, WorkspaceError, _atomic_write, dump_model
from areao1.criteria.case import Case
from areao1.engine import get_engine
from areao1.engine.base import AgentEvent, Engine, EngineRequest, EngineUnavailable, StopRun
from areao1.vault import Vault
from areao1.vault.rulecheck import Judge, RuleChecker, engine_judge, notify_conflicts

MAX_HISTORY_MESSAGES = 30
SUMMARIZE_AFTER_TOKENS = 6_000  # replayed history past this is summarized (ADR 0009 §3)
KEEP_TURNS = 6  # the most recent messages always go as they are
SUMMARY_SYSTEM = """You summarize the earlier part of a conversation between a person and Area O1, an assistant \
for their O-1A / EB-1A immigration case, so the conversation can continue without the full text.

Keep: facts the person stated about themselves and their case, decisions, what they asked for and whether it was \
done, open questions, names, dates and numbers exactly as written. Leave out pleasantries. Never add anything that \
wasn't said, and never judge eligibility. Plain sentences or short bullets, under 250 words."""


class BudgetExceeded(WorkspaceError):
    pass


@dataclass
class _Live:
    events: list[dict[str, Any]] = field(default_factory=list)
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)
    done: bool = False
    stop: str | None = None
    task: asyncio.Task[None] | None = None


class AgentRunner:
    def __init__(self, ws: Case, engine: Engine | None = None, judge: Judge | None = None):
        self.ws = ws
        self._engine = engine
        self._judge = judge
        self._live: dict[str, _Live] = {}
        self.on_finish: list[Callable[[AgentRun], None]] = []

    # ------------------------------------------------------------------ storage

    @property
    def runs_dir(self) -> Path:
        return self.ws.root / "agent" / "runs"

    @property
    def conversations_dir(self) -> Path:
        return self.ws.root / "agent" / "conversations"

    def engine(self) -> Engine:
        if self._engine is None:
            self._engine = get_engine(self.ws.config().engine)
        return self._engine

    def judge(self) -> Judge:
        if self._judge is None:
            self._judge = engine_judge(self.engine())
        return self._judge

    def checker(self) -> RuleChecker:
        return RuleChecker(Vault(self.ws), self.judge(), self.route("check").model)

    async def _summarize(self, conv: Conversation) -> None:
        """When replaying the unsummarized turns would pass SUMMARIZE_AFTER_TOKENS, fold all but the last KEEP_TURNS
        into the summary, on the mundane tier. The originals stay in the conversation. If no model is available the
        turns are replayed as before."""
        pending = conv.messages[conv.summarized :]
        if len(pending) <= KEEP_TURNS:
            return
        if _tokens(conv.summary) + sum(_tokens(m.text) for m in pending) <= SUMMARIZE_AFTER_TOKENS:
            return
        fold = pending[:-KEEP_TURNS]
        try:
            judge, how = self.mundane("summarize")
            if judge is None:
                return
            text = "\n".join(f"{'Person' if m.role == 'user' else 'Area O1'}: {m.text}" for m in fold)
            prompt = (
                f"Summary so far:\n{conv.summary}\n\n" if conv.summary else ""
            ) + f"Earlier messages:\n{text}"
            reply = await judge(SUMMARY_SYSTEM, prompt, how.model)
        except Exception:  # noqa: BLE001  (a failed summary never blocks the chat)
            return
        summary, _ = guard_answer(reply.text.strip())
        if not summary:
            return
        conv.summary, conv.summarized = summary, conv.summarized + len(fold)
        self._save_conversation(conv)
        self.save(AgentRun(kind="chat", engine=how.provider if how.provider == "openai" else self.engine().name,
                           model=how.model, task="summarize", tier=how.tier, provider=how.provider, status="done",
                           prompt=f"Summarized {len(fold)} earlier messages of a long chat", text=summary,
                           conversation_id=conv.id, cost_usd=reply.cost_usd,
                           usage=RunUsage(input_tokens=int(reply.usage.get("input_tokens", 0)),
                                          output_tokens=int(reply.usage.get("output_tokens", 0))),
                           finished_at=clock.utcnow()))  # fmt: skip

    def route(self, task: str) -> Route:
        cfg = self.ws.config()
        return route(task, cfg.agent.models, self.ws.root, cheap=cfg.agent.cheap_mode)

    def mundane(self, task: str = "chat_extract") -> tuple[Judge | None, Route]:
        """The judge for bulk, simple reading, on the mundane tier. Its input is redacted (privacy.redact_before_llm),
        as tool results are. None when no AI is connected. Refuses once the monthly cap is reached, like any run."""
        how = self.route(task)
        b, month = self.ws.config().agent.budget, self.month_usage()
        if b.monthly_usd is not None and float(month["usd"] or 0.0) >= b.monthly_usd:
            raise BudgetExceeded(
                f"monthly budget reached (${float(month['usd'] or 0):.2f} of ${b.monthly_usd:.2f})"
            )
        ok, _ = self.engine().available()
        if not ok:
            return None, how
        judge = self.judge()
        if not self.ws.config().privacy.redact_before_llm:
            return judge, how

        async def redacted(system: str, prompt: str, model: str) -> Any:
            return await judge(redact(system), redact(prompt), model)

        return redacted, how

    def save(self, run: AgentRun) -> None:
        _atomic_write(self.runs_dir / f"{run.id}.json", dump_model(run))

    def get(self, run_id: str) -> AgentRun:
        path = self.runs_dir / f"{run_id}.json"
        if not path.is_file() or "/" in run_id:
            raise NotFound(f"no run {run_id!r}")
        return AgentRun.model_validate_json(path.read_text(encoding="utf-8"))

    def runs(self, limit: int = 100) -> list[AgentRun]:
        if not self.runs_dir.is_dir():
            return []
        runs = [
            AgentRun.model_validate_json(p.read_text(encoding="utf-8"))
            for p in self.runs_dir.glob("run_*.json")
        ]
        return sorted(runs, key=lambda r: r.started_at, reverse=True)[:limit]

    def conversation(self, conv_id: str) -> Conversation:
        path = self.conversations_dir / f"{conv_id}.json"
        if not path.is_file() or "/" in conv_id:
            raise NotFound(f"no conversation {conv_id!r}")
        return Conversation.model_validate_json(path.read_text(encoding="utf-8"))

    def conversations(self) -> list[Conversation]:
        if not self.conversations_dir.is_dir():
            return []
        convs = [Conversation.model_validate_json(p.read_text(encoding="utf-8"))
                 for p in self.conversations_dir.glob("conv_*.json")]  # fmt: skip
        return sorted(convs, key=lambda c: c.updated_at, reverse=True)

    def _save_conversation(self, conv: Conversation) -> None:
        conv.updated_at = utcnow()
        _atomic_write(self.conversations_dir / f"{conv.id}.json", dump_model(conv))

    # ------------------------------------------------------------------ budgets

    def month_usage(self, today: date | None = None) -> dict[str, float | None]:
        today = today or clock.today()
        tokens, usd, cached, written, uncached = 0, 0.0, 0, 0, 0
        for run in self.runs(limit=100_000):
            if run.started_at.year == today.year and run.started_at.month == today.month:
                tokens += run.usage.counted
                usd += run.cost_usd or 0.0
                cached += run.usage.cache_read_input_tokens
                written += run.usage.cache_creation_input_tokens
                uncached += run.usage.input_tokens
        total_in = cached + written + uncached
        return {"tokens": tokens, "usd": round(usd, 4), "cache_read": cached, "cache_write": written,
                "uncached_input": uncached, "cache_hit_rate": round(cached / total_in, 3) if total_in else None}  # fmt: skip

    def status(self) -> dict[str, Any]:
        cfg = self.ws.config()
        try:
            ok, why = self.engine().available()
        except EngineUnavailable as exc:
            ok, why = False, str(exc)
        b = cfg.agent.budget
        return {"engine": cfg.engine, "available": ok, "reason": why, "model": self.route("chat").model,
                "models": cfg.agent.models.model_dump(), "cheap_mode": cfg.agent.cheap_mode,
                "routes": [r.__dict__ for r in table(cfg.agent.models, self.ws.root, cfg.agent.cheap_mode)],
                "effort": cfg.agent.effort, "web_search": cfg.agent.web_search,
                "budget": b.model_dump(), "month": self.month_usage()}  # fmt: skip

    # ------------------------------------------------------------------ running

    async def start(
        self,
        kind: str,
        prompt: str,
        *,
        conversation_id: str | None = None,
        page: str | None = None,
        mission: str | None = None,
        namesake: list[str] | None = None,
    ) -> AgentRun:
        prompt = prompt.strip()
        if not prompt:
            raise WorkspaceError("say something first")
        cfg = self.ws.config()
        engine = self.engine()
        ok, why = engine.available()
        if not ok:
            raise EngineUnavailable(why)
        b, month = cfg.agent.budget, self.month_usage()
        used_tokens, used_usd = int(month["tokens"] or 0), float(month["usd"] or 0.0)
        if used_tokens >= b.monthly_tokens:
            raise BudgetExceeded(f"monthly token budget reached ({used_tokens:,} of {b.monthly_tokens:,})")
        if b.monthly_usd is not None and used_usd >= b.monthly_usd:
            raise BudgetExceeded(f"monthly budget reached (${used_usd:.2f} of ${b.monthly_usd:.2f})")

        conv = None
        if kind == "chat":
            conv = self.conversation(conversation_id) if conversation_id else Conversation(title=prompt[:60])
        how = self.route(kind)
        model = how.model
        run = AgentRun(kind=kind, engine=engine.name, model=model, prompt=prompt, mission=mission,  # type: ignore[arg-type]
                       conversation_id=conv.id if conv else None, task=how.task, tier=how.tier,
                       provider=how.provider)  # fmt: skip
        summary = ""
        if conv is not None:
            await self._summarize(conv)
            history = list(conv.messages[conv.summarized :])
            summary = conv.summary
            conv.messages.append(ConversationMessage(role="user", text=prompt, run_id=run.id))
            self._save_conversation(conv)
        else:
            history = []
        self.save(run)

        caps = [
            c for c in (b.per_run_usd, (b.monthly_usd - used_usd) if b.monthly_usd else None) if c is not None
        ]
        request = EngineRequest(
            system_prompt=SYSTEM_PROMPT,
            prompt=_render_turn(prompt, history, self.ws, page, summary),
            model=model,
            effort=cfg.agent.effort,
            web_search=cfg.agent.web_search,
            max_turns=cfg.agent.max_turns,
            max_budget_usd=min(caps) if caps else None,
            task_budget_tokens=max(20_000, min(b.per_run_tokens, b.monthly_tokens - used_tokens)),
        )
        live = _Live()
        self._live[run.id] = live
        live.task = asyncio.create_task(self._execute(run, request, live, used_tokens, namesake))
        return run

    async def _execute(self, run: AgentRun, request: EngineRequest, live: _Live, month_tokens: int,
                       namesake: list[str] | None = None) -> None:  # fmt: skip
        cfg = self.ws.config()
        b = cfg.agent.budget
        checker = self.checker()
        policy = SearchPolicy(checker.vault.manifest)
        request.guard = policy
        ctx = RunContext(self.ws, run, redact=cfg.privacy.redact_before_llm, checker=checker, search=policy,
                         namesake=namesake)  # fmt: skip
        tools = build_tools(ctx)
        meta = {t.name: {"read_only": t.read_only, "touches": list(t.touches)} for t in tools}
        meta["WebSearch"] = meta["web_search"] = {"read_only": True, "touches": []}
        calls: dict[str, TimelineItem] = {}

        async def emit(ev: AgentEvent) -> None:
            if ev.type == "text":
                run.timeline.append(TimelineItem(type="text", text=ev.data["text"]))
            elif ev.type == "tool_call":
                item = TimelineItem(type="tool_call", tool=ev.data["name"], tool_id=ev.data["id"],
                                    input=ev.data.get("input") or {})  # fmt: skip
                calls[ev.data["id"]] = item
                run.timeline.append(item)
                self.save(run)
            elif ev.type == "tool_result":
                found = calls.get(ev.data["id"])
                if found is not None:
                    found.ok, found.result = ev.data.get("ok"), ev.data.get("summary", "")
                self.save(run)
            elif ev.type == "usage":
                for k, v in ev.data.items():
                    setattr(run.usage, k, getattr(run.usage, k) + int(v))
            elif ev.type == "error":
                run.timeline.append(TimelineItem(type="error", text=str(ev.data.get("error"))))
            extra: dict[str, Any] = {}
            if ev.type == "usage":
                extra["usage"] = run.usage.model_dump()
            elif ev.type == "tool_call":
                extra.update(meta.get(ev.data["name"], {"read_only": True, "touches": []}))
            elif ev.type == "tool_result" and ev.data["id"] in calls:
                extra["proposals"] = list(run.proposals)
            await self._publish(live, {"type": ev.type, **ev.data, **extra})
            if live.stop:
                raise StopRun(live.stop)
            if run.usage.counted > b.per_run_tokens:
                raise StopRun(f"per-run token budget reached ({b.per_run_tokens:,})")
            if month_tokens + run.usage.counted > b.monthly_tokens:
                raise StopRun(f"monthly token budget reached ({b.monthly_tokens:,})")

        try:
            result = await self.engine().run(request, tools, emit)
            run.text = result.text
            run.cost_usd = result.cost_usd
            run.stop_reason = result.stop_reason
            if result.is_error:
                run.status, run.error = "error", result.error
            elif result.stop_reason and ("budget" in result.stop_reason or result.stop_reason == live.stop):
                run.status = "stopped"
            else:
                run.status = "done"
            if run.status == "done" and run.text.strip():
                guarded, hits = guard_answer(run.text)
                if hits:  # eligibility verdicts and guarantees never reach the person
                    run.text = guarded
                    for item in run.timeline:
                        if item.type == "text" and item.text:
                            item.text = guard_answer(item.text)[0]
                    log_refusal(self.ws, run.id, "no_eligibility_verdict", "An answer stated an eligibility verdict or a "
                                "guarantee; it was replaced.", "Only USCIS decides; an attorney can assess the case.",
                                " | ".join(hits))  # fmt: skip
                    await self._publish(live, {"type": "guardrail", "text": run.text})
                run.rule_check = await checker.check(run.text)
                await self._publish(
                    live, {"type": "rule_check", "check": run.rule_check.model_dump(mode="json")}
                )
                notify_conflicts(self.ws, run.rule_check, f"agent?run={run.id}")
        except asyncio.CancelledError:
            run.status, run.stop_reason = "stopped", live.stop or "cancelled"
        except Exception as exc:  # never leave a run stuck in "running"
            run.status, run.error = "error", f"{type(exc).__name__}: {exc}"
        finally:
            for k, n in checker.usage.items():  # the judge's tokens count toward the run and the month
                if hasattr(run.usage, k):
                    setattr(run.usage, k, getattr(run.usage, k) + n)
            if checker.cost_usd:
                run.cost_usd = (run.cost_usd or 0.0) + checker.cost_usd
            for entry in policy.log:  # web searches the search policy refused
                if entry.get("denied"):
                    log_refusal(self.ws, run.id, "search_policy", str(entry["denied"])[:300],
                                "Search the vault first, then Tier 1 domains.", str(entry.get("query", "")))  # fmt: skip
            run.finished_at = utcnow()
            run.changes = [c.id for c in self.ws.changes() if c.actor == f"agent:{run.id}"]
            self.save(run)
            if run.conversation_id:
                try:
                    conv = self.conversation(run.conversation_id)
                    reply = run.text or (f"(stopped: {run.stop_reason})" if run.status == "stopped" else
                                         f"(error: {run.error})" if run.error else "")  # fmt: skip
                    conv.messages.append(ConversationMessage(role="assistant", text=reply, run_id=run.id))
                    self._save_conversation(conv)
                except NotFound:
                    pass
            for hook in self.on_finish:  # e.g. onboarding saving a web search's outcome
                with contextlib.suppress(Exception):  # a hook must never break the run
                    hook(run)
            await self._publish(live, {"type": "done", "run": json.loads(dump_model(run))})
            live.done = True

    async def _publish(self, live: _Live, event: dict[str, Any]) -> None:
        async with live.cond:
            live.events.append(event)
            live.cond.notify_all()

    def stop(self, run_id: str, reason: str = "stopped by you") -> bool:
        live = self._live.get(run_id)
        if live is None or live.done:
            return False
        live.stop = reason
        return True

    async def wait(self, run_id: str) -> AgentRun:
        live = self._live.get(run_id)
        if live is not None and live.task is not None:
            await live.task
        return self.get(run_id)

    async def stream(self, run_id: str) -> AsyncIterator[dict[str, Any]]:
        """Every event of a run from the start, then live ones until it finishes."""
        live = self._live.get(run_id)
        if live is None:
            # Started elsewhere (e.g. by the scheduler in another thread): poll its record until it finishes.
            run = self.get(run_id)
            for _ in range(3600):
                if run.status != "running":
                    break
                await asyncio.sleep(1)
                run = self.get(run_id)
            yield {"type": "done", "run": json.loads(dump_model(run))}
            return
        sent = 0
        while True:
            async with live.cond:
                while sent >= len(live.events) and not live.done:
                    await live.cond.wait()
                batch = live.events[sent:]
                finished = live.done and sent + len(batch) >= len(live.events)
            for event in batch:
                yield event
            sent += len(batch)
            if finished:
                return


def _tokens(text: str) -> int:
    return len(text) // 4  # a rough count; enough to decide when to summarize


def _render_turn(
    prompt: str, history: list[ConversationMessage], ws: Case, page: str | None, summary: str = ""
) -> str:
    lines = [f"Today is {clock.today().isoformat()}. Active profile: {ws.profile_id()}."]
    if page:
        lines.append(f"The person is on the {page} page of the dashboard.")
    if summary:
        lines += [
            "",
            "Summary of the earlier conversation (the full text is kept; this is shorter):",
            summary,
        ]
    if history:
        lines += ["", "Conversation so far:"]
        for m in history[-MAX_HISTORY_MESSAGES:]:
            lines.append(f"{'Person' if m.role == 'user' else 'You'}: {m.text}")
    lines += ["", "Person:" if history else "Request:", prompt]
    return "\n".join(lines)
