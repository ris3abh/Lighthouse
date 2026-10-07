"""Derived views shared by the Overview page, the API and DASHBOARD.md."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from typing import Any

from lighthouse_gc.core import clock
from lighthouse_gc.core.models import MetricRow
from lighthouse_gc.core.text import plural
from lighthouse_gc.criteria.case import Case

# Headline metric per source kind, used for sparklines and the dashboard table.
HEADLINE_METRICS = {
    "github": ("stars", "forks", "views"),
    "huggingface": ("downloads", "downloads_all_time", "likes"),
}


def metric_series(rows: list[MetricRow]) -> dict[tuple[str, str, str], list[MetricRow]]:
    series: dict[tuple[str, str, str], list[MetricRow]] = defaultdict(list)
    for r in sorted(rows, key=lambda r: r.date):
        series[(r.source, r.item, r.metric)].append(r)
    return series


def latest_with_delta(points: list[MetricRow]) -> dict[str, Any]:
    last = points[-1]
    prev = points[-2] if len(points) > 1 else None
    return {
        "date": last.date.isoformat(),
        "value": last.value,
        "previous": prev.value if prev else None,
        "previous_date": prev.date.isoformat() if prev else None,
        "delta": (last.value - prev.value) if prev else None,
    }


def headline_series(ws: Case, limit: int = 6) -> list[dict[str, Any]]:
    """The most-informative series for sparklines: one headline metric per item, largest first."""
    series = metric_series(ws.metrics())
    best: dict[tuple[str, str], tuple[str, list[MetricRow]]] = {}
    for (source, item, metric), points in series.items():
        prefs = HEADLINE_METRICS.get(source, ())
        if metric not in prefs:
            continue
        key = (source, item)
        current = best.get(key)
        if current is None or prefs.index(metric) < prefs.index(current[0]):
            best[key] = (metric, points)
    out = []
    for (source, item), (metric, points) in best.items():
        out.append(
            {
                "source": source,
                "item": item,
                "metric": metric,
                "points": [{"date": p.date.isoformat(), "value": p.value} for p in points[-12:]],
                **latest_with_delta(points),
            }
        )
    out.sort(key=lambda s: -s["value"])
    return out[:limit]


def upcoming_deadlines(ws: Case, n: int = 3, today: date | None = None) -> list[dict[str, Any]]:
    today = today or clock.today()
    items = sorted(
        (d for d in ws.deadlines().deadlines if not d.done and d.due >= today), key=lambda d: d.due
    )
    return [{**d.model_dump(mode="json"), "days_left": (d.due - today).days} for d in items[:n]]


def human_tasks(ws: Case, today: date | None = None) -> list[dict[str, Any]]:
    """This week's things only the user can do: review the inbox, hit deadlines, follow up."""
    today = today or clock.today()
    week_end = today + timedelta(days=7)
    tasks: list[dict[str, Any]] = []

    pending = ws.pending_candidates(today)
    if pending:
        tasks.append(
            {
                "kind": "inbox",
                "title": f"Review {plural(len(pending), 'candidate')} in the Inbox",
                "link": "#/inbox",
            }
        )

    for d in sorted(ws.deadlines().deadlines, key=lambda d: d.due):
        if not d.done and d.human_only and today - timedelta(days=30) <= d.due <= week_end:
            overdue = d.due < today
            tasks.append(
                {
                    "kind": "deadline",
                    "title": ("Overdue: " if overdue else "") + d.title,
                    "due": d.due.isoformat(),
                    "link": d.url or "#/overview",
                }
            )

    for p in ws.pipeline().items:
        if p.stage != "done" and p.follow_up and p.follow_up <= week_end:
            tasks.append(
                {
                    "kind": "follow_up",
                    "title": f"Follow up: {p.title}",
                    "due": p.follow_up.isoformat(),
                    "link": p.url,
                }
            )

    issues = ws.naming_check()
    if issues:
        tasks.append(
            {
                "kind": "evidence",
                "title": f"Fix {plural(len(issues), 'evidence file issue')}",
                "link": "#/evidence",
            }
        )
    return tasks


def overview(ws: Case, today: date | None = None) -> dict[str, Any]:
    cfg = ws.config()
    board = ws.scoreboard()
    return {
        "person": ws.person().model_dump(mode="json"),
        "profile": cfg.profile,
        "profiles": [{"id": p.id, "name": p.name} for p in ws.profiles().values()],
        "scoreboard": board.model_dump(mode="json"),
        "inbox_pending": len(ws.pending_candidates(today)),
        "tasks": human_tasks(ws, today),
        "deadlines": upcoming_deadlines(ws, 3, today),
        "sparklines": headline_series(ws),
        "sources": [
            {"id": s.id, "kind": s.kind, "last_sync": s.last_sync, "last_error": s.last_error}
            for s in ws.sources().sources
        ],
    }
