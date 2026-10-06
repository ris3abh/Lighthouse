"""Overview briefing: written by the agent through publish_briefing, refreshed by the daily mission, with inline
approve / dismiss for linked Inbox items."""

from __future__ import annotations

import anyio
import pytest
from agent_fakes import FakeEngine
from fastapi.testclient import TestClient

from lighthouse_gc import notify
from lighthouse_gc.agent import missions
from lighthouse_gc.agent.tools import RunContext, build_tools
from lighthouse_gc.core.models import AgentRun
from lighthouse_gc.scaffold import validate_workspace as validate
from lighthouse_gc.server.app import create_app

W = {"X-Lighthouse": "1"}


class _Quiet:
    def send(self, note, cfg, secret):
        pass


def _todos(ws):
    pending = [c for c in ws.pending_candidates() if c.kind != "evidence" or c.source_tier != "self_reported"]
    tracker = next(c for c in pending if c.kind in ("deadline", "pipeline", "letter"))
    other = next(c for c in pending if c.id != tracker.id)
    return (
        tracker,
        other,
        [
            {"title": f"Decide: {tracker.title}", "why": "It has a date.", "candidate_id": tracker.id},
            {"title": "Dismiss the stale suggestion", "candidate_id": other.id},
            {
                "title": "Email Dr. Lee about the letter",
                "why": "Two weeks since last contact.",
                "link": "#/letters",
            },
        ],
    )


def test_publish_validates_and_records_a_change(demo_ws):
    ctx = RunContext(
        demo_ws, AgentRun(kind="scheduled", engine="fake", model="t", prompt="p", mission="what_changed")
    )
    t = {x.name: x for x in build_tools(ctx)}["publish_briefing"]
    assert not t.read_only and t.touches == ("data/briefing.json",)
    with pytest.raises(ValueError, match="pending Inbox item"):
        anyio.run(t.handler, {"changed": [], "todos": [{"title": "x", "candidate_id": "cand_nope"}]})
    with pytest.raises(ValueError, match="link must be"):
        anyio.run(t.handler, {"changed": [], "todos": [{"title": "x", "link": "javascript:alert(1)"}]})
    with pytest.raises(ValueError, match="at most three"):
        anyio.run(t.handler, {"changed": [], "todos": [{"title": str(i)} for i in range(4)]})
    _, _, todos = _todos(demo_ws)
    out = anyio.run(t.handler, {"since": "2026-10-01", "changed": ["Citations 64 → 71."], "todos": todos})
    assert "Published" in out
    b = demo_ws.briefing()
    assert b.run_id == ctx.run.id and b.changed == ["Citations 64 → 71."] and len(b.todos) == 3
    change = demo_ws.changes()[-1]
    assert change.action == "briefing.publish" and change.actor == f"agent:{ctx.run.id}"
    assert validate(demo_ws) == []


def test_daily_mission_refreshes_the_briefing_and_inline_decisions_work(demo_ws, monkeypatch):
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": _Quiet()})
    cfg = demo_ws.config()
    cfg.agent.missions.what_changed = True
    demo_ws.save_config(cfg)
    tracker, other, todos = _todos(demo_ws)
    engine = FakeEngine([
        ("tool", "what_changed", {"since": "2026-10-01"}),
        ("tool", "publish_briefing", {"changed": ["Two new Inbox items."], "todos": todos}),
        ("text", "Briefing published."),
    ])  # fmt: skip
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine))
    assert c.get("/api/briefing").json()["generated_at"] is None  # nothing until the first run

    lines = missions.run_job(demo_ws, "what_changed", scheduled=True, engine=engine)
    assert lines[0].startswith("What changed: done")
    assert "publish_briefing" in engine.requests[0].prompt

    b = c.get("/api/briefing").json()
    assert b["changed"] == ["Two new Inbox items."] and b["refreshing"] is None
    first, second, third = b["todos"]
    assert first["candidate"]["id"] == tracker.id and first["candidate"]["status"] == "pending"
    assert third["candidate"] is None and third["link"] == "#/letters"

    # Inline approve / dismiss go through the normal Inbox routes.
    assert c.post(f"/api/inbox/{tracker.id}/accept", json={}, headers=W).status_code == 200
    assert c.post(f"/api/inbox/{other.id}/reject", headers=W).status_code == 200
    b = c.get("/api/briefing").json()
    assert b["todos"][1]["candidate"]["status"] == "rejected"
    assert b["todos"][0]["candidate"] is None or b["todos"][0]["candidate"]["status"] != "pending"


def test_refresh_from_the_overview_runs_the_mission(demo_ws, monkeypatch):
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": _Quiet()})
    engine = FakeEngine(
        [("tool", "publish_briefing", {"changed": ["Quiet week."], "todos": []}), ("text", "ok")]
    )
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine)) as c:
        run_id = c.post("/api/agent/missions/what_changed/run", headers=W).json()["run_id"]
        c.get(f"/api/agent/runs/{run_id}/stream")
        b = c.get("/api/briefing").json()
    assert b["run_id"] == run_id and b["changed"] == ["Quiet week."]


def test_a_broken_briefing_file_is_reported(demo_ws):
    (demo_ws.data_dir / "briefing.json").write_text('{"schema_version": 1, "todos": [{"why": "no title"}]}')
    assert any(p.startswith("data/briefing.json") for p in validate(demo_ws))
