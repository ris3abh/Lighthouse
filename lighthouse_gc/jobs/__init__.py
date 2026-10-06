"""Jobs: scheduled inside ``lighthouse-gc up`` and runnable headless via ``lighthouse-gc run <job>``.

Each job takes ``(workspace, scheduled)``. ``scheduled`` is True when the scheduler (not a person) started it;
``metrics-snapshot`` uses it to stay biweekly while running on a weekly cron. gmail-triage and
opportunity-scan arrive in Phase 2.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, timedelta

from lighthouse_gc.criteria.case import Case
from lighthouse_gc.criteria.dashboard import write_dashboard
from lighthouse_gc.jobs import alerts
from lighthouse_gc.jobs import sync as _sync

SNAPSHOT_MIN_DAYS = 13  # biweekly, scheduled on a weekly cron


def _run_sync(ws: Case, scheduled: bool = False) -> list[str]:
    from lighthouse_gc.notify import Notification, send

    before = {c.id for c in ws.inbox().candidates}
    reports = _sync.sync(ws)
    lines = [r.line() for r in reports] or ["no sources: run `lighthouse-gc import <url>` first"]
    new = [c for c in ws.pending_candidates() if c.id not in before]
    if new:
        note = Notification(
            "new_candidates",
            f"{len(new)} new candidate(s) to review",
            "\n".join(f"· {c.title}" for c in new[:10]),
            url=alerts.dashboard_url(ws, "inbox"),
            minimal_body=f"{len(new)} new item(s) in your Inbox.",
        )
        lines.append(send(ws, note).line())
    errors = [f"{r.source_id}: {e}" for r in reports for e in r.errors]
    if errors:
        note = Notification(
            "sync_error",
            "Sync had errors",
            "\n".join(errors[:10]),
            url=alerts.dashboard_url(ws, "sources"),
            minimal_body=f"{len(errors)} sync error(s). Check the Sources page.",
        )
        lines.append(send(ws, note).line())
    return lines


def _run_snapshot(ws: Case, scheduled: bool = False) -> list[str]:
    if scheduled:
        dates = [r.date for r in ws.metrics() if r.source in ("github", "huggingface")]
        last = max(dates) if dates else None
        if last and date.today() - last < timedelta(days=SNAPSHOT_MIN_DAYS):
            return [
                f"skipped: last snapshot {last.isoformat()} is under {SNAPSHOT_MIN_DAYS} days old (biweekly)"
            ]
    return [r.line() for r in _sync.snapshot(ws)] or ["no sources: run `lighthouse-gc import <url>` first"]


def _run_dashboard(ws: Case, scheduled: bool = False) -> list[str]:
    board = ws.recompute()
    write_dashboard(ws, board)
    return [f"{board.profile_name}: {board.banked} banked / {board.threshold} needed. DASHBOARD.md written"]


def _run_deadline_check(ws: Case, scheduled: bool = False) -> list[str]:
    return alerts.deadline_check(ws)


def _run_digest(ws: Case, scheduled: bool = False) -> list[str]:
    return alerts.digest(ws)


JOBS: dict[str, tuple[str, Callable[[Case, bool], list[str]]]] = {
    "sync": ("refresh all sources, push new candidates to the Inbox", _run_sync),
    "metrics-snapshot": ("append dated rows to data/metrics.csv (biweekly when scheduled)", _run_snapshot),
    "deadline-check": ("alert on deadlines within 14 days, regenerate calendar.ics", _run_deadline_check),
    "digest": ("weekly summary: what changed, stale pipeline items, next actions", _run_digest),
    "dashboard": ("re-score criteria and regenerate DASHBOARD.md", _run_dashboard),
}
