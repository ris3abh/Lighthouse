"""iCalendar (RFC 5545) export of open deadlines and pipeline follow-ups.

Deterministic on purpose: same data, same bytes. ``data/calendar.ics`` lives in Git, so it only changes
when a deadline does. Served at ``/calendar.ics`` for calendar apps on this machine (``webcal://127.0.0.1:...``).
"""

from __future__ import annotations

from datetime import date, timedelta

from lighthouse_gc.core.workspace import Workspace, _atomic_write

PRODID = "-//Lighthouse//lighthouse-gc//EN"


def _escape(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\r\n", "\\n")
        .replace("\n", "\\n")
    )


def _fold(line: str) -> list[str]:
    """Fold to 75 octets per line (continuation lines start with a space), never splitting a UTF-8 character."""
    out: list[str] = []
    current = ""
    for ch in line:
        limit = 75 if not out else 74
        if len((current + ch).encode("utf-8")) > limit:
            out.append(current)
            current = ch
        else:
            current += ch
    out.append(current)
    return [out[0], *(" " + part for part in out[1:])]


def _day(d: date) -> str:
    return d.strftime("%Y%m%d")


def _event(uid: str, on: date, summary: str, *, description: str = "", url: str | None = None,
           category: str = "", alarm_days: int | None = 1) -> list[str]:  # fmt: skip
    lines = [
        "BEGIN:VEVENT",
        f"UID:{uid}@lighthouse-gc",
        f"DTSTAMP:{_day(on)}T000000Z",  # derived from the data, so regenerating doesn't churn the file
        f"DTSTART;VALUE=DATE:{_day(on)}",
        f"DTEND;VALUE=DATE:{_day(on + timedelta(days=1))}",
        f"SUMMARY:{_escape(summary)}",
        "TRANSP:TRANSPARENT",
    ]
    if description:
        lines.append(f"DESCRIPTION:{_escape(description)}")
    if url:
        lines.append(f"URL:{url}")
    if category:
        lines.append(f"CATEGORIES:{_escape(category)}")
    if alarm_days is not None:
        lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_escape(summary)}",
                  f"TRIGGER:-P{alarm_days}D", "END:VALARM"]  # fmt: skip
    lines.append("END:VEVENT")
    return lines


def render(ws: Workspace) -> str:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape('Lighthouse: ' + ws.config().workspace_name)}",
    ]
    for d in sorted(ws.deadlines().deadlines, key=lambda d: (d.due, d.id)):
        if d.done:
            continue
        lines += _event(d.id, d.due, d.title, description=f"Lighthouse deadline ({d.kind}).", url=d.url,
                        category=d.kind, alarm_days=1 if d.human_only else None)  # fmt: skip
    for p in sorted(ws.pipeline().items, key=lambda p: p.id):
        if p.stage == "done" or not p.follow_up:
            continue
        lines += _event(f"followup-{p.id}", p.follow_up, f"Follow up: {p.title}",
                        description=f"Pipeline item, stage {p.stage}.", url=p.url, category="follow_up",
                        alarm_days=None)  # fmt: skip
    lines.append("END:VCALENDAR")
    return "".join(part + "\r\n" for line in lines for part in _fold(line))


def write_calendar(ws: Workspace) -> str:
    text = render(ws)
    path = ws.data_dir / "calendar.ics"
    if not path.exists() or path.read_bytes() != text.encode("utf-8"):
        _atomic_write(path, text)
    return text
