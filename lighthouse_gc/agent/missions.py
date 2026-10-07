"""Missions (Phase 1c item 5): scheduled agent runs on the existing scheduler, inside the budget caps.

* ``opportunity_scout``, weekly: find current opportunities for the weakest criteria; propose pipeline items
  and deadlines (to the Inbox, or auto-applied where the person enabled autopilot).
* ``what_changed``, daily: review what changed and what's due, and summarize. Skipped without spending a token
  when nothing changed since the last run.

Both are off by default (``agent.missions`` in lighthouse.yaml, toggled in Settings) and use the ``mission``
model. Results are on the Agent page and go out as a ``mission`` notification.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import anyio

from lighthouse_gc.agent.runner import AgentRunner, BudgetExceeded
from lighthouse_gc.core import clock
from lighthouse_gc.core.models import AgentRun
from lighthouse_gc.core.text import plural
from lighthouse_gc.criteria.case import Case
from lighthouse_gc.engine.base import Engine, EngineUnavailable


@dataclass(frozen=True)
class Mission:
    name: str
    job: str
    title: str
    prompt: Callable[[Case, date | None], str]


def _scout_prompt(ws: Case, since: date | None) -> str:
    return (
        "Weekly opportunity scout.\n"
        "1. Call list_gaps and get_profile, and list_pipeline so you don't duplicate anything already tracked.\n"
        "2. Pick the two or three criteria that are weakest but realistic to strengthen in the next two months.\n"
        "3. Use web search to find concrete, current opportunities for them, open in the next 8 weeks: judging or "
        "reviewing calls, CFPs and talks, awards and fellowships, selective memberships. Prefer official pages.\n"
        "4. Read each promising page with read_page. For each good fit, call propose_pipeline_item (with url, "
        "criterion and follow_up if known) and propose_deadline for its deadline, citing observation_id and a "
        "verbatim quote.\n"
        "5. Finish with a short ranked list: opportunity, criterion, deadline, and why it fits. If you found "
        "nothing worth the person's time, say so."
    )


def _changed_prompt(ws: Case, since: date | None) -> str:
    since = since or clock.today() - timedelta(days=1)
    return (
        f"Daily check-in. Since {since.isoformat()}:\n"
        f"1. Call what_changed with since={since.isoformat()}, then list_inbox, list_deadlines, list_pipeline and "
        "get_scoreboard.\n"
        "2. Call publish_briefing: what changed that matters (short lines), and the three most useful things for "
        "the person to do this week, each with why. When a to-do is deciding an Inbox item, set its candidate_id; "
        "otherwise link the page (#/pipeline, #/letters, #/calendar, #/evidence) or the opportunity's URL.\n"
        f"   Pass since={since.isoformat()}.\n"
        "3. Reply with the same briefing in a few lines."
    )


MISSIONS: dict[str, Mission] = {
    "opportunity_scout": Mission(
        "opportunity_scout", "mission-opportunity-scout", "Opportunity scout", _scout_prompt
    ),
    "what_changed": Mission("what_changed", "mission-what-changed", "What changed", _changed_prompt),
}


def last_run(runner: AgentRunner, name: str) -> AgentRun | None:
    return next((r for r in runner.runs(limit=1000) if r.mission == name and r.status == "done"), None)


def precheck(ws: Case, runner: AgentRunner, name: str) -> str | None:
    """A reason to skip this mission without calling the model, or None to run it."""
    if name != "what_changed":
        return None
    previous = last_run(runner, name)
    if previous is None:
        return None
    since = previous.started_at
    own = f"agent:{previous.id}"
    activity = (
        [c for c in ws.changes() if c.at > since and c.actor != own]
        + [c for c in ws.memory.claims() if c.recorded_at > since]
        + [c for c in ws.pending_candidates() if c.created_at > since and c.source != own]
    )
    soon = [d for d in ws.deadlines().deadlines if not d.done and 0 <= (d.due - clock.today()).days <= 3]
    if not (activity or soon):
        return f"nothing changed since {clock.local_date(since).isoformat()}"
    return None


async def start(runner: AgentRunner, name: str) -> AgentRun:
    mission = MISSIONS[name]
    previous = last_run(runner, name)
    prompt = mission.prompt(runner.ws, clock.local_date(previous.started_at) if previous else None)
    return await runner.start("scheduled", prompt, mission=name)


def notify_result(ws: Case, run: AgentRun) -> str:
    from lighthouse_gc.jobs.alerts import dashboard_url
    from lighthouse_gc.notify import Notification, send

    mission = MISSIONS.get(run.mission or "")
    title = mission.title if mission else "Mission"
    auto = [c for c in ws.changes() if c.id in run.changes and c.auto]
    counts = f"{plural(len(run.proposals), 'suggestion')} in your Inbox" + (
        f", {len(auto)} applied by autopilot" if auto else ""
    )
    if run.status != "done":
        body = f"{title} {run.status}: {run.stop_reason or run.error or ''}".strip()
        note = Notification("mission", f"{title} {run.status}", body, url=dashboard_url(ws, f"agent?run={run.id}"),
                            minimal_body=body, key=f"mission:{run.id}")  # fmt: skip
    else:
        note = Notification("mission", f"{title}: {counts}", (run.text or "Done.")[:1500],
                            url=dashboard_url(ws, f"agent?run={run.id}"), priority="low",
                            minimal_body=f"{title} finished: {counts}.", key=f"mission:{run.id}")  # fmt: skip
    return send(ws, note).line()


def run_job(ws: Case, name: str, scheduled: bool, engine: Engine | None = None) -> list[str]:
    """Scheduler / CLI entry point (runs in a worker thread, so it gets its own event loop)."""
    cfg = ws.config().agent.missions
    if scheduled and not getattr(cfg, name):
        return [f"skipped: the {MISSIONS[name].title.lower()} mission is off (Settings → Missions)"]
    runner = AgentRunner(ws, engine=engine)
    reason = precheck(ws, runner, name)
    if reason:
        return [f"skipped: {reason}; no tokens spent"]

    async def go() -> AgentRun:
        run = await start(runner, name)
        return await runner.wait(run.id)

    try:
        run = anyio.run(go)
    except (BudgetExceeded, EngineUnavailable) as exc:
        return [f"skipped: {exc}"]
    return [f"{MISSIONS[name].title}: {run.status}, {plural(len(run.proposals), 'proposal')}, ${run.cost_usd or 0:.2f}",
            notify_result(ws, run)]  # fmt: skip


def missions_status(ws: Case, runner: AgentRunner) -> list[dict[str, Any]]:
    from lighthouse_gc.jobs.scheduler import jobs_status

    jobs = {j["name"]: j for j in jobs_status(ws)}
    cfg = ws.config().agent.missions
    out = []
    for m in MISSIONS.values():
        last = last_run(runner, m.name)
        out.append({"name": m.name, "title": m.title, "enabled": getattr(cfg, m.name), "job": m.job,
                    "schedule": jobs.get(m.job, {}).get("schedule"), "next_run": jobs.get(m.job, {}).get("next_run"),
                    "model": ws.config().agent.models.mission,
                    "last_run": {"id": last.id, "at": last.started_at.isoformat(), "proposals": len(last.proposals),
                                 "cost_usd": last.cost_usd} if last else None})  # fmt: skip
    return out
