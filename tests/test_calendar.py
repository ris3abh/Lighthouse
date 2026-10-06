"""calendar.ics: valid RFC 5545 (parsed by an independent library), deterministic, served, kept current."""

from __future__ import annotations

from datetime import date

import icalendar
from fastapi.testclient import TestClient

from lighthouse_gc.core.calendar import _fold, render
from lighthouse_gc.core.models import Pipeline, PipelineItem
from lighthouse_gc.core.workspace import _atomic_write, dump_model
from lighthouse_gc.server.app import create_app

W = {"X-Lighthouse": "1"}


def _events(text: str) -> dict[str, icalendar.Event]:
    cal = icalendar.Calendar.from_ical(text)
    return {str(e["UID"]): e for e in cal.walk("VEVENT")}


def test_demo_calendar_parses_and_skips_done(demo_ws):
    events = _events(render(demo_ws))
    assert "dl_demo_ieee@lighthouse-gc" in events
    assert "dl_demo_done@lighthouse-gc" not in events  # done deadlines are left out
    ieee = events["dl_demo_ieee@lighthouse-gc"]
    assert ieee["DTSTART"].dt == date(2026, 11, 1) and ieee["DTEND"].dt == date(2026, 11, 2)  # all-day
    assert str(ieee["SUMMARY"]) == "IEEE Senior Member application"
    assert any(c.name == "VALARM" for c in ieee.subcomponents)
    follow = events["followup-pipe_demo_ieee@lighthouse-gc"]
    assert str(follow["SUMMARY"]) == "Follow up: IEEE Senior Member" and follow["DTSTART"].dt == date(
        2026, 10, 20
    )


def test_escaping_folding_and_crlf(ws):
    long = "Submit; the camera-ready, version\nwith notes — " + "ü" * 60
    ws.add_deadline(title=long, due="2026-12-01", kind="submission")
    text = render(ws)
    assert "\r\n" in text and "\n" not in text.replace("\r\n", "")
    assert all(len(line.encode()) <= 75 for line in text.split("\r\n"))
    [event] = _events(text).values()
    assert str(event["SUMMARY"]) == long  # round-trips through escape + fold
    assert _fold("x" * 200)[1].startswith(" ")


def test_output_is_deterministic(demo_ws):
    assert render(demo_ws) == render(demo_ws)
    path = demo_ws.data_dir / "calendar.ics"
    demo_ws.after_change()
    first = path.read_bytes()
    demo_ws.after_change()
    assert path.read_bytes() == first


def test_calendar_file_tracks_changes(ws):
    d = ws.add_deadline(title="Reviews due", due="2026-10-14")
    assert "Reviews due" in (ws.data_dir / "calendar.ics").read_text()
    ws.update_deadline(d.id, done=True)
    assert "Reviews due" not in (ws.data_dir / "calendar.ics").read_text()
    pl = Pipeline(items=[PipelineItem(id="p1", title="Ping MLH", follow_up=date(2026, 10, 9))])
    _atomic_write(ws.data_dir / "pipeline.json", dump_model(pl))
    ws.after_change()
    assert "Follow up: Ping MLH" in (ws.data_dir / "calendar.ics").read_text()


def test_feed_and_deadline_api(ws):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    created = c.post("/api/deadlines", json={"title": "TMLR signup", "due": "2026-10-20", "kind": "submission"},
                     headers=W)  # fmt: skip
    assert created.status_code == 200, created.text
    did = created.json()["id"]
    feed = c.get("/calendar.ics")
    assert feed.headers["content-type"].startswith("text/calendar") and f"{did}@lighthouse-gc" in feed.text
    listed = c.get("/api/deadlines").json()
    assert listed[0]["title"] == "TMLR signup" and "days_left" in listed[0]
    assert c.patch(f"/api/deadlines/{did}", json={"done": True}, headers=W).json()["done"] is True
    assert c.patch(f"/api/deadlines/{did}", json={"due": "not-a-date"}, headers=W).status_code == 422
    assert c.post("/api/deadlines", json={"title": "x"}, headers=W).status_code == 400  # due is required
    assert c.delete(f"/api/deadlines/{did}", headers=W).status_code == 200
    assert c.delete(f"/api/deadlines/{did}", headers=W).status_code == 404
    assert c.delete("/api/deadlines/x").status_code == 403  # writes need the header


def test_deadlines_are_fully_editable(ws):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    did = c.post("/api/deadlines", json={"title": "Old", "due": "2026-10-20"}, headers=W).json()["id"]
    changes = {"title": "TMLR reviewer signup", "due": "2026-10-22", "kind": "submission",
               "url": "https://example.org/tmlr", "human_only": False}  # fmt: skip
    r = c.patch(f"/api/deadlines/{did}", json=changes, headers=W)
    assert r.status_code == 200, r.text
    assert {k: r.json()[k] for k in changes} == changes
    [event] = _events((ws.data_dir / "calendar.ics").read_text()).values()
    assert str(event["SUMMARY"]) == "TMLR reviewer signup" and event["DTSTART"].dt == date(2026, 10, 22)
    assert not any(c.name == "VALARM" for c in event.subcomponents)  # no reminder once it doesn't need you
    assert str(event["URL"]) == "https://example.org/tmlr"
    assert c.patch(f"/api/deadlines/{did}", json={"url": None}, headers=W).json()["url"] is None  # clearable
    assert c.patch(f"/api/deadlines/{did}", json={"kind": "someday"}, headers=W).status_code == 400
