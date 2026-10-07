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

from lighthouse_gc.agent.guardrails import guard_answer, log_refusal
from lighthouse_gc.agent.prompt import SYSTEM_PROMPT
from lighthouse_gc.agent.search_policy import SearchPolicy
from lighthouse_gc.agent.tools import RunContext, build_tools
from lighthouse_gc.core import clock
from lighthouse_gc.core.models import AgentRun, Conversation, ConversationMessage, TimelineItem, utcnow
from lighthouse_gc.core.workspace import NotFound, WorkspaceError, _atomic_write, dump_model
from lighthouse_gc.criteria.case import Case
from lighthouse_gc.engine import get_engine
from lighthouse_gc.engine.base import AgentEvent, Engine, EngineRequest, EngineUnavailable, StopRun
from lighthouse_gc.vault import Vault
from lighthouse_gc.vault.rulecheck import Judge, RuleChecker, engine_judge, notify_conflicts

MAX_HISTORY_MESSAGES = 30


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
        return RuleChecker(Vault(self.ws), self.judge(), self.ws.config().agent.models.check)

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
        return {"engine": cfg.engine, "available": ok, "reason": why, "model": cfg.agent.models.chat,
                "models": cfg.agent.models.model_dump(),
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
        model = cfg.agent.model_for(kind)
        run = AgentRun(kind=kind, engine=engine.name, model=model, prompt=prompt, mission=mission,  # type: ignore[arg-type]
                       conversation_id=conv.id if conv else None)  # fmt: skip
        if conv is not None:
            history = list(conv.messages)
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
            prompt=_render_turn(prompt, history, self.ws, page),
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


def _render_turn(prompt: str, history: list[ConversationMessage], ws: Case, page: str | None) -> str:
    lines = [f"Today is {clock.today().isoformat()}. Active profile: {ws.profile_id()}."]
    if page:
        lines.append(f"The person is on the {page} page of the dashboard.")
    if history:
        lines += ["", "Conversation so far:"]
        for m in history[-MAX_HISTORY_MESSAGES:]:
            lines.append(f"{'Person' if m.role == 'user' else 'You'}: {m.text}")
    lines += ["", "Person:" if history else "Request:", prompt]
    return "\n".join(lines)
