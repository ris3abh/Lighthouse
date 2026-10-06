"""Jobs runnable headless via ``lighthouse-gc run <job>`` (cron / launchd / GitHub Actions).

Phase 0 ships ``sync``, ``metrics-snapshot`` and ``dashboard``. The in-process scheduler and the
remaining jobs (deadline-check, gmail-triage, opportunity-scan, digest) arrive in later phases.
"""

from __future__ import annotations

from collections.abc import Callable

from lighthouse_gc.criteria.case import Case
from lighthouse_gc.criteria.dashboard import write_dashboard
from lighthouse_gc.jobs import sync as _sync


def _run_sync(ws: Case) -> list[str]:
    return [r.line() for r in _sync.sync(ws)] or ["no sources — run `lighthouse-gc import <url>` first"]


def _run_snapshot(ws: Case) -> list[str]:
    return [r.line() for r in _sync.snapshot(ws)] or ["no sources — run `lighthouse-gc import <url>` first"]


def _run_dashboard(ws: Case) -> list[str]:
    board = ws.recompute()
    write_dashboard(ws, board)
    return [f"{board.profile_name}: {board.banked} banked / {board.threshold} needed — DASHBOARD.md written"]


JOBS: dict[str, tuple[str, Callable[[Case], list[str]]]] = {
    "sync": ("refresh all sources, push new candidates to the Inbox", _run_sync),
    "metrics-snapshot": ("append dated rows to data/metrics.csv (incl. GitHub traffic)", _run_snapshot),
    "dashboard": ("re-score criteria and regenerate DASHBOARD.md", _run_dashboard),
}
