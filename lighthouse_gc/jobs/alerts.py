"""deadline-check and digest: the jobs that tell you what needs you."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from lighthouse_gc.criteria import overview as views
from lighthouse_gc.criteria.case import Case
from lighthouse_gc.notify import Notification, Report, already_sent, last_sent, send

STALE_DAYS = 14
DASHBOARD_URL = "http://127.0.0.1:{port}/#/{page}"


def dashboard_url(ws: Case, page: str) -> str:
    return DASHBOARD_URL.format(port=ws.config().server.port, page=page)


def _bucket(days_left: int, thresholds: list[int]) -> str | None:
    """Smallest alert threshold the deadline has reached, e.g. 10 days left with [14, 3, 1, 0] -> '14'."""
    if days_left < 0:
        return "overdue"
    reached = [t for t in sorted(thresholds) if days_left <= t]
    return str(reached[0]) if reached else None


def _when(days_left: int) -> str:
    if days_left < 0:
        return f"overdue by {-days_left} day{'s' if days_left != -1 else ''}"
    if days_left == 0:
        return "due today"
    return f"due in {days_left} day{'s' if days_left != 1 else ''}"


def due_items(ws: Case, today: date) -> list[dict[str, Any]]:
    """Open deadlines and pipeline follow-ups that have reached an alert threshold."""
    thresholds = ws.config().notifications.deadline_alert_days or [14, 3, 1, 0]
    horizon = max(thresholds)
    items: list[dict[str, Any]] = []
    for d in ws.deadlines().deadlines:
        if d.done or (d.due - today).days > horizon:
            continue
        items.append({"id": d.id, "title": d.title, "due": d.due, "kind": "deadline", "url": d.url})
    for p in ws.pipeline().items:
        if p.stage == "done" or not p.follow_up or (p.follow_up - today).days > min(3, horizon):
            continue
        items.append(
            {
                "id": p.id,
                "title": f"Follow up: {p.title}",
                "due": p.follow_up,
                "kind": "follow_up",
                "url": p.url,
            }
        )
    out = []
    for item in sorted(items, key=lambda i: i["due"]):
        days_left = (item["due"] - today).days
        bucket = _bucket(days_left, thresholds if item["kind"] == "deadline" else [3, 1, 0])
        if bucket is None or (bucket == "overdue" and days_left < -30):
            continue  # don't nag forever about something a month overdue
        out.append(
            {**item, "days_left": days_left, "bucket": bucket, "key": f"{item['kind']}:{item['id']}:{bucket}"}
        )
    return out


def deadline_check(ws: Case, today: date | None = None) -> list[str]:
    """Alert once per deadline per threshold (14 / 3 / 1 / 0 days, overdue). Regenerates calendar.ics."""
    today = today or date.today()
    lines = []
    for item in due_items(ws, today):
        if already_sent(ws, item["key"]):
            continue
        high = item["days_left"] <= 1
        note = Notification(
            event="deadline",
            title=f"{item['title']}: {_when(item['days_left'])}",
            body=f"{item['title']}\n{_when(item['days_left']).capitalize()} ({item['due'].isoformat()}).",
            url=dashboard_url(ws, "calendar"),
            priority="high" if high else "default",
            minimal_body=f"A deadline is {_when(item['days_left'])}. Open Lighthouse for details.",
            key=item["key"],
        )
        report = send(ws, note)
        lines.append(f"{note.title} → {report.line()}")
    _write_calendar(ws)
    return lines or ["no new deadline alerts"]


def _write_calendar(ws: Case) -> None:
    try:
        from lighthouse_gc.criteria.calendar import write_calendar
    except ImportError:  # calendar export arrives with the Calendar page
        return
    write_calendar(ws)


def stale_pipeline(ws: Case, today: date) -> list[dict[str, Any]]:
    cutoff = datetime.combine(today, datetime.min.time(), UTC) - timedelta(days=STALE_DAYS)
    return [
        {"id": p.id, "title": p.title, "stage": p.stage, "days": (today - p.moved_at.date()).days}
        for p in ws.pipeline().items
        if p.stage != "done" and p.moved_at < cutoff
    ]


def build_digest(ws: Case, today: date | None = None, since: date | None = None) -> dict[str, Any]:
    from lighthouse_gc.mcp.tools import what_changed

    today = today or date.today()
    since = since or today - timedelta(days=7)
    changed = what_changed(ws, since.isoformat())
    board = ws.scoreboard()
    upcoming = [d for d in views.upcoming_deadlines(ws, 10, today) if d["days_left"] <= 14]
    stale = stale_pipeline(ws, today)
    pending = ws.pending_candidates(today)
    tasks = views.human_tasks(ws, today)

    lines = [f"Lighthouse weekly digest: {since.isoformat()} to {today.isoformat()}", ""]
    lines.append(
        f"{board.profile_name}: {board.banked} banked / {board.threshold} needed, {board.building} building."
    )
    counts = Counter(c["change"] for c in changed["claims"])
    lines.append(
        f"What changed: {len(changed['exhibits_accepted'])} exhibit(s) accepted, {len(changed['new_candidates'])} new "
        f"candidate(s), {counts['new']} new and {counts['updated']} updated fact(s)."
    )
    movers = sorted(changed["metric_changes"], key=lambda m: -abs(m["delta"]))[:5]
    for m in movers:
        sign = "+" if m["delta"] > 0 else ""
        lines.append(f"  · {m['item']} {m['metric']}: {m['from']:g} → {m['to']:g} ({sign}{m['delta']:g})")
    lines += ["", f"Due in the next 14 days ({len(upcoming)}):"]
    lines += [f"  · {d['due']}: {d['title']}" for d in upcoming] or ["  · nothing"]
    lines += ["", f"Stale pipeline items, no movement in {STALE_DAYS}+ days ({len(stale)}):"]
    lines += [f"  · {s['title']} ({s['stage']}, {s['days']} days)" for s in stale] or ["  · none"]
    lines += ["", "Next actions:"]
    lines += [f"  · {t['title']}" for t in tasks] or ["  · nothing needs you"]
    lines += ["", f"Inbox: {len(pending)} pending."]
    minimal = (f"Weekly digest: {len(pending)} to review, {len(upcoming)} deadline(s) in 14 days, "
               f"{len(stale)} stale pipeline item(s).")  # fmt: skip
    return {"text": "\n".join(lines), "minimal": minimal, "upcoming": upcoming, "stale": stale,
            "pending": len(pending), "changed": changed}  # fmt: skip


def digest(ws: Case, today: date | None = None) -> list[str]:
    today = today or date.today()
    previous = last_sent(ws, "digest")
    since = previous.date() if previous else today - timedelta(days=7)
    d = build_digest(ws, today, since)
    report: Report = send(
        ws,
        Notification("digest", "Lighthouse weekly digest", d["text"], url=dashboard_url(ws, "overview"),
                     priority="low", minimal_body=d["minimal"], key=f"digest:{today.isoformat()}"),
    )  # fmt: skip
    return [*d["text"].splitlines(), "", f"sent → {report.line()}"]
