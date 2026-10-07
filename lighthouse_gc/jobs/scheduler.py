"""In-process scheduler for ``lighthouse-gc up`` (APScheduler), plus run-state bookkeeping.

Schedules are cron expressions in ``lighthouse.yaml`` (``schedules``). Run state (last run, result) is kept
in ``.lighthouse/cache/scheduler.json``, which is local and gitignored. When ``up`` starts, any job whose last
scheduled time passed while the machine was off runs once to catch up. Machines that aren't always on can
call ``lighthouse-gc run <job>`` from cron / launchd / GitHub Actions instead.
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from lighthouse_gc.core import clock
from lighthouse_gc.core.models import utcnow
from lighthouse_gc.criteria.case import Case

log = logging.getLogger("lighthouse_gc.scheduler")
_run_lock = threading.Lock()


def trigger(expr: str) -> CronTrigger:
    try:
        return CronTrigger.from_crontab(expr, timezone=clock.local_tz())
    except ValueError as exc:
        raise ValueError(f"invalid cron expression {expr!r}: {exc}") from exc


def _state_path(ws: Case):
    return ws.cache_dir / "scheduler.json"


def load_state(ws: Case) -> dict[str, dict[str, Any]]:
    path = _state_path(ws)
    try:
        return json.loads(path.read_text()) if path.exists() else {}
    except ValueError:
        return {}


def _save_state(ws: Case, state: dict[str, dict[str, Any]]) -> None:
    path = _state_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def run_job(ws: Case, name: str, *, scheduled: bool = False) -> dict[str, Any]:
    """Run one job (serialized with every other job) and record the result."""
    from lighthouse_gc.jobs import JOBS

    _, fn = JOBS[name]
    started = utcnow()
    with _run_lock:
        try:
            lines = fn(ws, scheduled)
            result = {"last_run": started.isoformat(), "ok": True, "summary": lines[:20]}
        except Exception as exc:  # a failing job must not kill the scheduler
            log.exception("job %s failed", name)
            result = {
                "last_run": started.isoformat(),
                "ok": False,
                "summary": [f"{type(exc).__name__}: {exc}"],
            }
        state = load_state(ws)
        state[name] = result
        _save_state(ws, state)
    return result


def jobs_status(ws: Case, now: datetime | None = None) -> list[dict[str, Any]]:
    from lighthouse_gc.jobs import JOBS

    now = now or clock.now()
    state = load_state(ws)
    out = []
    for name, (desc, _) in JOBS.items():
        expr = ws.config().schedules.get(name)
        next_run = None
        error = None
        if expr:
            try:
                nxt = trigger(expr).get_next_fire_time(None, now)
                next_run = nxt.isoformat() if nxt else None
            except ValueError as exc:
                error = str(exc)
        out.append({"name": name, "description": desc, "schedule": expr, "next_run": next_run, "error": error,
                    **state.get(name, {})})  # fmt: skip
    return out


def missed(ws: Case, now: datetime | None = None) -> list[str]:
    """Jobs whose last scheduled time passed since their last run (e.g. the laptop was asleep)."""
    now = now or clock.now()
    state = load_state(ws)
    out = []
    for name, expr in ws.config().schedules.items():
        last = state.get(name, {}).get("last_run")
        if not expr:
            continue
        try:
            trig = trigger(expr)
        except ValueError:
            continue
        if last is None:
            continue  # never run here: wait for the first scheduled time instead of firing everything at once
        nxt = trig.get_next_fire_time(None, datetime.fromisoformat(last))
        if nxt is not None and nxt <= now:
            out.append(name)
    return out


def start(ws: Case) -> BackgroundScheduler:
    from lighthouse_gc.jobs import JOBS

    sched = BackgroundScheduler(timezone=clock.local_tz(), job_defaults={"coalesce": True, "max_instances": 1,
                                                                          "misfire_grace_time": 3600})  # fmt: skip
    for name, expr in ws.config().schedules.items():
        if not expr:
            continue  # turned off
        if name not in JOBS:
            log.warning("schedule for unknown job %r ignored", name)
            continue
        sched.add_job(run_job, trigger(expr), args=[ws, name], kwargs={"scheduled": True}, id=name, name=name)
    sched.start()
    for name in missed(ws):
        sched.add_job(run_job, args=[ws, name], kwargs={"scheduled": True}, id=f"catchup-{name}")
    return sched
