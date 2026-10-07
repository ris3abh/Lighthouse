"""Two-way sync between your deadlines and a dedicated "Area O1" Google calendar (ADR 0014 §3). Area O1 creates
the calendar (the calendar.app.created scope sees nothing else) and keeps one all-day event per open deadline.
Each run pulls what changed in Google first (with Google's sync token), then pushes local changes.

Latest edit wins: an event changed in Google after the deadline's last change here updates the deadline, and a
deadline changed here after the event's last update overwrites the event. A new event you add to the calendar
becomes a deadline; an event you delete there deletes its deadline (unless the deadline changed here since).
Every change from Google goes through the service layer as "google-calendar", so it's logged and undoable."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import httpx

from areao1.core import clock
from areao1.core.names import PRODUCT
from areao1.criteria.case import Case
from areao1.criteria.models import CalendarLink, CalendarSync
from areao1.google import auth
from areao1.service import Service

API = "https://www.googleapis.com/calendar/v3"
ACTOR = "google-calendar"
TAG = "areao1_id"


def _sig(title: str, due: date | str) -> str:
    return f"{title}|{due}"


def _event_body(d: Any) -> dict[str, Any]:
    note = f"A deadline in {PRODUCT}." + (f" {d.url}" if d.url else "")
    return {"summary": d.title, "description": note, "start": {"date": d.due.isoformat()},
            "end": {"date": (d.due + timedelta(days=1)).isoformat()}, "transparency": "transparent",
            "extendedProperties": {"private": {TAG: d.id}}}  # fmt: skip


def _event_day(ev: dict[str, Any]) -> date | None:
    start = ev.get("start") or {}
    if start.get("date"):
        return date.fromisoformat(start["date"])
    if start.get("dateTime"):
        return clock.local_date(datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00")))
    return None


def _updated(ev: dict[str, Any]) -> datetime:
    """When the event last changed, to the second: local changes are stored to the second, and a tie goes to the
    edit made here."""
    at = datetime.fromisoformat(str(ev.get("updated", "1970-01-01T00:00:00Z")).replace("Z", "+00:00"))
    return at.replace(microsecond=0)


def _last_local_change(ws: Case, deadline_id: str) -> datetime | None:
    times = [
        c.at
        for c in ws.changes()
        if c.target_type == "deadline" and c.target_id == deadline_id and c.actor != ACTOR
    ]
    return max(times) if times else None


def sync(ws: Case, client: httpx.Client | None = None) -> list[str]:
    if not auth.granted("calendar"):
        return ["skipped: the calendar isn't connected (Settings > Google)"]
    own = client is None
    c = client or httpx.Client(timeout=30)
    try:
        h = {"Authorization": f"Bearer {auth.access_token(c)}"}
        state = ws.calendar_sync()
        if not state.calendar_id:
            r = c.post(
                f"{API}/calendars",
                json={"summary": PRODUCT, "description": f"Deadlines from {PRODUCT}."},
                headers=h,
            )
            r.raise_for_status()
            state = CalendarSync(calendar_id=r.json()["id"])
            ws.save_calendar_sync(state)
        pulled = _pull(ws, c, h, state)
        pushed = _push(ws, c, h, state)
        ws.save_calendar_sync(state)
    finally:
        if own:
            c.close()
    return [f"Calendar: {pulled} change{'s' if pulled != 1 else ''} from Google, {pushed} sent"]


def _pull(ws: Case, c: httpx.Client, h: dict[str, str], state: CalendarSync) -> int:
    svc, n = Service(ws, actor=ACTOR), 0
    params: dict[str, Any] = {"showDeleted": "true", "singleEvents": "true", "maxResults": 250}
    if state.sync_token:
        params["syncToken"] = state.sync_token
    events: list[dict[str, Any]] = []
    while True:
        r = c.get(f"{API}/calendars/{state.calendar_id}/events", params=params, headers=h)
        if r.status_code == 410:  # Google expired the token: start over with a full listing
            state.sync_token = None
            params.pop("syncToken", None)
            continue
        r.raise_for_status()
        data = r.json()
        events += data.get("items", [])
        if data.get("nextPageToken"):
            params["pageToken"] = data["nextPageToken"]
            continue
        state.sync_token = data.get("nextSyncToken", state.sync_token)
        break
    by_event = {link.event_id: did for did, link in state.links.items()}
    deadlines = {d.id: d for d in ws.deadlines().deadlines}
    for ev in events:
        tagged = ((ev.get("extendedProperties") or {}).get("private") or {}).get(TAG)
        did = str(tagged or by_event.get(ev.get("id", ""), ""))
        local = deadlines.get(did) if did else None
        link = state.links.get(did) if did else None
        if ev.get("status") == "cancelled":
            if local is not None and link is not None:
                newer_here = (
                    _last_local_change(ws, did) or datetime.min.replace(tzinfo=_updated(ev).tzinfo)
                ) > _updated(ev)
                if newer_here:
                    state.links.pop(did, None)  # pushed again below, as a new event
                else:
                    svc.delete_deadline(did)
                    state.links.pop(did, None)
                    n += 1
            continue
        day, title = _event_day(ev), str(ev.get("summary") or "").strip()
        if day is None or not title:
            continue
        if local is None:
            if did and did in state.links:  # its deadline was deleted here: the push removes the event
                continue
            created = svc.add_deadline(title=title[:200], due=day, kind="other")
            state.links[created.id] = CalendarLink(
                event_id=ev["id"], pushed=_sig(title, day), synced_at=clock.utcnow()
            )
            c.patch(f"{API}/calendars/{state.calendar_id}/events/{ev['id']}", headers=h,
                    json={"extendedProperties": {"private": {TAG: created.id}}})  # fmt: skip
            n += 1
            continue
        if _sig(title, day) == _sig(local.title, local.due):
            if link is not None:
                link.pushed = _sig(title, day)
            continue
        here = _last_local_change(ws, local.id)
        if link is not None and (here is None or _updated(ev) > here):  # edited in Google last
            svc.update_deadline(local.id, title=title[:200], due=day)
            link.pushed, link.synced_at = _sig(title, day), clock.utcnow()
            n += 1
    return n


def _push(ws: Case, c: httpx.Client, h: dict[str, str], state: CalendarSync) -> int:
    n = 0
    base = f"{API}/calendars/{state.calendar_id}/events"
    open_deadlines = {d.id: d for d in ws.deadlines().deadlines if not d.done}
    for did, old in list(state.links.items()):  # deleted or done here: take the event off the calendar
        if did not in open_deadlines:
            r = c.delete(f"{base}/{old.event_id}", headers=h)
            if r.status_code not in (200, 204, 404, 410):
                r.raise_for_status()
            state.links.pop(did)
            n += 1
    for did, d in open_deadlines.items():
        link = state.links.get(did)
        if link is None:
            r = c.post(base, json=_event_body(d), headers=h)
            r.raise_for_status()
            state.links[did] = CalendarLink(
                event_id=r.json()["id"], pushed=_sig(d.title, d.due), synced_at=clock.utcnow()
            )
            n += 1
        elif link.pushed != _sig(d.title, d.due):
            r = c.patch(f"{base}/{link.event_id}", json=_event_body(d), headers=h)
            r.raise_for_status()
            link.pushed, link.synced_at = _sig(d.title, d.due), clock.utcnow()
            n += 1
    return n
