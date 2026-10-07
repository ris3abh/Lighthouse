"""Two-way calendar sync (E3, ADR 0014 §3): a dedicated calendar, one all-day event per open deadline, edits
either way (latest wins), events added or deleted in Google, every change from Google logged and undoable.
Google Calendar is an in-memory fake; nothing leaves."""

from __future__ import annotations

import json
import time
from datetime import UTC, date, datetime

import httpx
import pytest

from areao1.core.secrets import set_secret
from areao1.google import auth, calendar
from areao1.service import Service


class FakeCalendar:
    """Just enough of the Calendar API: create a calendar, list events with sync tokens, insert, patch, delete."""

    def __init__(self):
        self.calendars: dict[str, str] = {}
        self.events: dict[str, dict] = {}
        self.seq = 0  # bumps on every change, so a sync token is "everything after seq N"
        self.changed: dict[str, int] = {}

    def _touch(self, eid):
        self.seq += 1
        self.changed[eid] = self.seq
        # Real time, like Google: an edit here after an edit there is really later (no fixed clock to race).
        time.sleep(0.002)
        self.events[eid]["updated"] = datetime.now(UTC).isoformat()

    def user_edit(self, eid, **fields):  # someone changes the event in Google Calendar
        self.events[eid].update(fields)
        self._touch(eid)

    def user_add(self, summary, day):
        eid = f"ev{len(self.events) + 1}"
        self.events[eid] = {
            "id": eid,
            "status": "confirmed",
            "summary": summary,
            "start": {"date": day},
            "end": {"date": day},
        }
        self._touch(eid)
        return eid

    def user_delete(self, eid):
        self.events[eid]["status"] = "cancelled"
        self._touch(eid)

    def handler(self, request: httpx.Request) -> httpx.Response:
        path, m = request.url.path, request.method
        assert request.headers["authorization"] == "Bearer ya29.t"
        if path == "/calendar/v3/calendars" and m == "POST":
            self.calendars["cal1"] = json.loads(request.content)["summary"]
            return httpx.Response(200, json={"id": "cal1"})
        assert path.startswith("/calendar/v3/calendars/cal1/events"), path  # only its own calendar
        eid = path.rsplit("/", 1)[-1] if path.count("/") > 5 else None
        if m == "GET":
            since = int(request.url.params.get("syncToken", "0"))
            items = [self.events[e] for e, s in self.changed.items() if s > since]
            return httpx.Response(200, json={"items": items, "nextSyncToken": str(self.seq)})
        if m == "POST":
            eid = f"ev{len(self.events) + 1}"
            self.events[eid] = {"id": eid, "status": "confirmed", **json.loads(request.content)}
            self._touch(eid)
            return httpx.Response(200, json=self.events[eid])
        if m == "PATCH":
            self.events[eid].update(json.loads(request.content))
            self._touch(eid)
            return httpx.Response(200, json=self.events[eid])
        if m == "DELETE":
            self.events[eid]["status"] = "cancelled"
            self._touch(eid)
            return httpx.Response(204)
        return httpx.Response(405)


@pytest.fixture
def gcal(http_mock):
    set_secret(
        auth.CLIENT_REF, json.dumps({"client_id": "x.apps.googleusercontent.com", "client_secret": "s"})
    )
    set_secret(auth.TOKEN_REF, json.dumps({"refresh_token": "r", "access_token": "ya29.t", "expires_at": time.time() + 600,
                                           "scope": auth.SCOPES["calendar"]}))  # fmt: skip
    fake = FakeCalendar()
    http_mock.route(host="www.googleapis.com").mock(side_effect=fake.handler)
    return fake


def _event_for(ws, fake, deadline_id):
    return fake.events[ws.calendar_sync().links[deadline_id].event_id]


def test_deadlines_go_to_a_dedicated_calendar_as_all_day_events(demo_ws, gcal):
    open_ids = {d.id for d in demo_ws.deadlines().deadlines if not d.done}
    lines = calendar.sync(demo_ws)
    assert gcal.calendars == {"cal1": "Area O1"} and f"{len(open_ids)} sent" in lines[0]
    assert set(demo_ws.calendar_sync().links) == open_ids  # done deadlines stay off the calendar
    d = next(x for x in demo_ws.deadlines().deadlines if not x.done)
    ev = _event_for(demo_ws, gcal, d.id)
    assert ev["summary"] == d.title and ev["start"] == {"date": d.due.isoformat()}
    assert ev["extendedProperties"]["private"]["areao1_id"] == d.id
    calendar.sync(demo_ws)  # nothing changed: nothing sent
    assert "0 changes from Google, 0 sent" in calendar.sync(demo_ws)[0]


def test_an_edit_in_google_updates_the_deadline_logged_and_undoable(demo_ws, gcal):
    calendar.sync(demo_ws)
    d = next(x for x in demo_ws.deadlines().deadlines if not x.done)
    gcal.user_edit(
        demo_ws.calendar_sync().links[d.id].event_id,
        summary="Reviews due (moved)",
        start={"date": "2026-10-28"},
    )
    assert "1 change from Google" in calendar.sync(demo_ws)[0]
    after = next(x for x in demo_ws.deadlines().deadlines if x.id == d.id)
    assert (after.title, after.due) == ("Reviews due (moved)", date(2026, 10, 28))
    change = demo_ws.changes()[-1]
    assert change.actor == "google-calendar" and change.action == "deadline.update"
    Service(demo_ws).undo(change.id)  # undo: the local value wins on the next push
    calendar.sync(demo_ws)
    assert _event_for(demo_ws, gcal, d.id)["summary"] == d.title


def test_latest_edit_wins_when_both_sides_changed(demo_ws, gcal):
    calendar.sync(demo_ws)
    d = next(x for x in demo_ws.deadlines().deadlines if not x.done)
    gcal.user_edit(demo_ws.calendar_sync().links[d.id].event_id, summary="Edited in Google first")
    Service(demo_ws).update_deadline(d.id, title="Edited here later")  # newer than the Google edit
    calendar.sync(demo_ws)
    assert next(x for x in demo_ws.deadlines().deadlines if x.id == d.id).title == "Edited here later"
    assert _event_for(demo_ws, gcal, d.id)["summary"] == "Edited here later"


def test_events_added_or_deleted_in_google(demo_ws, gcal):
    calendar.sync(demo_ws)
    eid = gcal.user_add("Call with the attorney", "2026-10-20")
    calendar.sync(demo_ws)
    added = next(x for x in demo_ws.deadlines().deadlines if x.title == "Call with the attorney")
    assert added.due == date(2026, 10, 20) and demo_ws.calendar_sync().links[added.id].event_id == eid
    assert gcal.events[eid]["extendedProperties"]["private"]["areao1_id"] == added.id
    gcal.user_delete(eid)
    calendar.sync(demo_ws)
    assert not [x for x in demo_ws.deadlines().deadlines if x.id == added.id]
    assert (
        demo_ws.changes()[-1].action == "deadline.delete" and demo_ws.changes()[-1].actor == "google-calendar"
    )


def test_done_or_deleted_here_comes_off_the_calendar(demo_ws, gcal):
    calendar.sync(demo_ws)
    d = next(x for x in demo_ws.deadlines().deadlines if not x.done)
    eid = demo_ws.calendar_sync().links[d.id].event_id
    Service(demo_ws).update_deadline(d.id, done=True)
    calendar.sync(demo_ws)
    assert gcal.events[eid]["status"] == "cancelled" and d.id not in demo_ws.calendar_sync().links
    assert any(x.id == d.id for x in demo_ws.deadlines().deadlines)  # still here, just done


def test_nothing_without_the_calendar_permission(demo_ws, http_mock):
    set_secret(auth.TOKEN_REF, json.dumps({"refresh_token": "r", "access_token": "t", "expires_at": time.time() + 600,
                                           "scope": auth.SCOPES["gmail_read"]}))  # fmt: skip
    route = http_mock.route(host="www.googleapis.com").respond(200, json={})
    assert "isn't connected" in calendar.sync(demo_ws)[0] and not route.called
