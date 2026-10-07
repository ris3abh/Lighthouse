"""Pipeline kanban (staleness) and the Letters roster: store + API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from areao1.core.workspace import NotFound, WorkspaceError, _atomic_write, dump_model
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}


def test_moving_stage_resets_staleness_but_edits_do_not(ws):
    item = ws.add_pipeline_item(title="IEEE Senior Member", criterion="membership", stage="idea")
    old = datetime.now(UTC) - timedelta(days=30)
    pl = ws.pipeline()
    pl.items[0].moved_at = old
    _atomic_write(ws.data_dir / "pipeline.json", dump_model(pl))

    before = ws.pipeline().items[0].moved_at
    edited = ws.update_pipeline_item(item.id, notes="sent references", follow_up="2026-10-20")
    assert edited.moved_at == before  # editing notes or a date isn't movement
    moved = ws.update_pipeline_item(item.id, stage="applied")
    assert moved.moved_at > old + timedelta(days=29)
    assert (
        ws.update_pipeline_item(item.id, stage="applied").moved_at == moved.moved_at
    )  # same stage: no reset


def test_pipeline_validation(ws):
    with pytest.raises(WorkspaceError):
        ws.add_pipeline_item(title="x", stage="maybe")
    item = ws.add_pipeline_item(title="x")
    with pytest.raises(WorkspaceError, match="not editable"):
        ws.update_pipeline_item(item.id, moved_at="2020-01-01")
    with pytest.raises(NotFound):
        ws.delete_pipeline_item("pipe_nope")
    ws.delete_pipeline_item(item.id)
    assert ws.pipeline().items == []


def test_pipeline_api_flags_stale_items(demo_ws):
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    items = {p["id"]: p for p in c.get("/api/pipeline").json()}
    assert items["pipe_demo_ieee"]["stale"] is True  # demo: no movement since 2026-09-10
    assert items["pipe_demo_ieee"]["days_since_move"] >= 14
    r = c.patch("/api/pipeline/pipe_demo_ieee", json={"stage": "waiting"}, headers=W)
    assert r.status_code == 200 and r.json()["stage"] == "waiting"
    assert {p["id"]: p for p in c.get("/api/pipeline").json()}["pipe_demo_ieee"]["stale"] is False
    created = c.post(
        "/api/pipeline", json={"title": "Pitch to ML newsletter", "criterion": "press"}, headers=W
    )
    assert created.json()["stage"] == "idea"
    assert c.patch("/api/pipeline/pipe_demo_ieee", json={"stage": "someday"}, headers=W).status_code == 400
    assert c.delete(f"/api/pipeline/{created.json()['id']}", headers=W).status_code == 200


def test_letters_roster_and_coverage(demo_ws):
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    data = c.get("/api/letters").json()
    names = {lt["name"]: lt for lt in data["letters"]}
    assert names["Dr. Priya Natarajan (fictional)"]["draft_exists"] is True
    oc = next(row for row in data["coverage"] if row["id"] == "original_contributions")
    assert oc["independent"] == 1 and oc["employer"] == 0
    lid = names["Marcus Webb (fictional)"]["id"]
    assert c.patch(f"/api/letters/{lid}", json={"status": "signed"}, headers=W).json()["status"] == "signed"
    assert c.patch(f"/api/letters/{lid}", json={"relationship": "friend"}, headers=W).status_code == 400
    added = c.post("/api/letters", json={"name": "Dr. New Writer", "relationship": "independent",
                                         "criteria": ["judging"]}, headers=W)  # fmt: skip
    assert added.status_code == 200 and added.json()["status"] == "prospect"
    assert c.delete(f"/api/letters/{added.json()['id']}", headers=W).status_code == 200


def test_draft_paths_stay_inside_drafts(demo_ws):
    lid = demo_ws.letters().letters[0].id
    with pytest.raises(WorkspaceError):
        demo_ws.update_letter(lid, draft_path="data/person.json")
    with pytest.raises(WorkspaceError):
        demo_ws.update_letter(lid, draft_path="../outside.md")
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    assert c.get("/api/drafts/letters/natarajan.md").status_code == 200
    assert c.get("/api/drafts/../data/person.json").status_code in (400, 404)


def test_declined_writers_do_not_count_in_coverage(demo_ws):
    lid = next(lt.id for lt in demo_ws.letters().letters if lt.name.startswith("Dr. Priya"))
    demo_ws.update_letter(lid, status="declined")
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    oc = next(
        row for row in c.get("/api/letters").json()["coverage"] if row["id"] == "original_contributions"
    )
    assert oc["independent"] == 0


def test_letter_asks_and_last_contact_are_editable(demo_ws):
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    lt = next(x for x in c.get("/api/letters").json()["letters"] if x["name"].startswith("Marcus"))
    assert lt["asks"] == ["letter"]
    r = c.patch(f"/api/letters/{lt['id']}", json={"asks": ["letter", "membership_ref"], "last_contact": "2026-10-05"},
                headers=W)  # fmt: skip
    assert r.status_code == 200 and r.json()["asks"] == ["letter", "membership_ref"]
    assert r.json()["last_contact"] == "2026-10-05"
    assert demo_ws.letters().letters[1].asks == ["letter", "membership_ref"]  # persisted to letters.json
    assert (
        c.patch(f"/api/letters/{lt['id']}", json={"last_contact": None}, headers=W).json()["last_contact"]
        is None
    )
    assert c.patch(f"/api/letters/{lt['id']}", json={"asks": ["coffee"]}, headers=W).status_code == 400
    assert c.patch(f"/api/letters/{lt['id']}", json={"last_contact": "soon"}, headers=W).status_code == 422
    assert c.patch(f"/api/letters/{lt['id']}", json={"asks": []}, headers=W).json()["asks"] == []
