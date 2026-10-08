"""Jobs: scheduled inside ``areao1 up`` and runnable headless via ``areao1 run <job>``.

Each job takes ``(workspace, scheduled)``. ``scheduled`` is True when the scheduler (not a person) started it;
``metrics-snapshot`` uses it to stay biweekly while running on a weekly cron. gmail-triage and
opportunity-scan arrive in Phase 2.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from areao1.core import clock
from areao1.core.text import plural
from areao1.criteria.case import Case
from areao1.criteria.dashboard import write_dashboard
from areao1.jobs import alerts
from areao1.jobs import sync as _sync

SNAPSHOT_MIN_DAYS = 13  # biweekly, scheduled on a weekly cron


def _run_sync(ws: Case, scheduled: bool = False) -> list[str]:
    from areao1.notify import Notification, send

    before = {c.id for c in ws.inbox().candidates}
    from areao1.criteria import proof

    reports = _sync.sync(ws)
    lines = [r.line() for r in reports] or ["no sources: run `areao1 import <url>` first"]
    if reports:
        lines += proof.propose(ws)  # source pages that may preserve a proof item (ADR 0017)
    new = [c for c in ws.pending_candidates() if c.id not in before]
    if new:
        note = Notification(
            "new_candidates",
            f"{plural(len(new), 'new candidate')} to review",
            "\n".join(f"· {c.title}" for c in new[:10]),
            url=alerts.dashboard_url(ws, "inbox"),
            minimal_body=f"{plural(len(new), 'new item')} in your Inbox.",
        )
        lines.append(send(ws, note).line())
    errors = [f"{r.source_id}: {e}" for r in reports for e in r.errors]
    if errors:
        note = Notification(
            "sync_error",
            "Sync had errors",
            "\n".join(errors[:10]),
            url=alerts.dashboard_url(ws, "sources"),
            minimal_body=f"{plural(len(errors), 'sync error')}. Check the Sources page.",
        )
        lines.append(send(ws, note).line())
    return lines


def _run_snapshot(ws: Case, scheduled: bool = False) -> list[str]:
    if scheduled:
        dates = [r.date for r in ws.metrics() if r.source in _sync.sources.CONNECTORS]
        last = max(dates) if dates else None
        if last and clock.today() - last < timedelta(days=SNAPSHOT_MIN_DAYS):
            return [
                f"skipped: last snapshot {last.isoformat()} is under {SNAPSHOT_MIN_DAYS} days old (biweekly)"
            ]
    return [r.line() for r in _sync.snapshot(ws)] or ["no sources: run `areao1 import <url>` first"]


def _run_dashboard(ws: Case, scheduled: bool = False) -> list[str]:
    board = ws.recompute()
    write_dashboard(ws, board)
    return [f"{board.profile_name}: {board.banked} banked / {board.threshold} needed. DASHBOARD.md written"]


def _run_deadline_check(ws: Case, scheduled: bool = False) -> list[str]:
    return alerts.deadline_check(ws)


def _run_digest(ws: Case, scheduled: bool = False) -> list[str]:
    return alerts.digest(ws)


def _mission(name: str) -> Callable[[Case, bool], list[str]]:
    def run(ws: Case, scheduled: bool = False) -> list[str]:
        from areao1.agent import missions

        return missions.run_job(ws, name, scheduled)

    return run


def _vault_watch(ws: Case, scheduled: bool = False) -> list[str]:
    from areao1.vault.watch import run_watch

    return run_watch(ws, scheduled)


def _mail_view(ws: Case) -> list[str]:
    """Sort new mail for the Mail view: rules, then the mundane tier (its cost is recorded like any run)."""
    import anyio

    from areao1.agent.runner import AgentRunner, BudgetExceeded
    from areao1.core import clock
    from areao1.core.models import AgentRun, RunUsage
    from areao1.google import mail, mailview

    if not mail.connected():
        return []
    runner = AgentRunner(ws)

    def mundane():  # type: ignore[no-untyped-def]
        try:
            return runner.mundane("classify")
        except BudgetExceeded:
            return None, runner.route("classify")

    try:
        out = anyio.run(mailview.sync, ws, mundane)
    except mail.MailError as exc:
        return [f"Mail: {exc}"]
    how = out.get("route")
    if how is not None:
        runner.save(AgentRun(kind="scheduled", engine=how.provider if how.provider == "openai" else runner.engine().name,
                             model=how.model, task=how.task, tier=how.tier, provider=how.provider, status="done",
                             prompt="Mail view: sorting new mail", text=" ".join(out["lines"]),
                             cost_usd=out["cost_usd"], usage=RunUsage.model_validate(out["usage"]),
                             finished_at=clock.utcnow()))  # fmt: skip
    return list(out["lines"])


def _opportunities(ws: Case, scheduled: bool = False) -> list[str]:
    from areao1.google import opportunities

    return opportunities.run_job(ws, scheduled)


def _google(ws: Case, scheduled: bool = False) -> list[str]:
    from areao1.criteria import proof
    from areao1.google import gmail, outreach
    from areao1.service import Service

    lines = gmail.sync(ws)
    lines += _mail_view(ws)
    lines += proof.propose(ws)  # mail that may preserve a proof item (ADR 0017), to the Inbox
    drafts = outreach.follow_ups(ws)  # after quiet days: drafts for you to approve, never sent on their own
    for d in drafts:
        Service(ws, actor="follow-up").save_draft(d)
    if drafts:
        lines.append(
            f"{len(drafts)} follow-up draft{'s' if len(drafts) != 1 else ''} waiting for your approval"
        )
    return lines


JOBS: dict[str, tuple[str, Callable[[Case, bool], list[str]]]] = {
    "sync": ("refresh all sources, push new candidates to the Inbox", _run_sync),
    "metrics-snapshot": ("append dated rows to data/metrics.csv (biweekly when scheduled)", _run_snapshot),
    "deadline-check": ("alert on deadlines within 14 days, regenerate calendar.ics", _run_deadline_check),
    "digest": ("weekly summary: what changed, stale pipeline items, next actions", _run_digest),
    "dashboard": ("re-score criteria and regenerate DASHBOARD.md", _run_dashboard),
    "vault-watch": (
        "re-check the knowledge vault: Tier 1 daily, others when stale; notify on Tier 1 changes",
        _vault_watch,
    ),
    "mission-opportunity-scout": (
        "agent: weekly opportunity scout (off until enabled in Settings)",
        _mission("opportunity_scout"),
    ),
    "mission-what-changed": (
        "agent: daily what-changed check (off until enabled in Settings)",
        _mission("what_changed"),
    ),
    "google": (
        "Gmail threads with your contacts, the Mail view and follow-up drafts (skips until Gmail is connected)",
        _google,
    ),
    "daily-opportunities": (
        "opportunity mail to the Inbox, each find verified or not (off until enabled in Settings > Gmail)",
        _opportunities,
    ),
}
