"""Missions: weekly opportunity scout and daily what-changed, on the scheduler, inside the budget caps."""

from __future__ import annotations

from agent_fakes import FakeEngine
from fastapi.testclient import TestClient

from lighthouse_gc import notify
from lighthouse_gc.agent import missions
from lighthouse_gc.agent.runner import AgentRunner
from lighthouse_gc.jobs import JOBS
from lighthouse_gc.server.app import create_app

W = {"X-Lighthouse": "1"}


class _Recorder:
    def __init__(self):
        self.sent = []

    def send(self, note, cfg, secret):
        self.sent.append(note)


def _enable(ws, **flags):
    cfg = ws.config()
    cfg.agent.missions = cfg.agent.missions.model_copy(update=flags)
    ws.save_config(cfg)


def _recorder(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": rec})
    return rec


def test_off_by_default_and_scheduled(demo_ws):
    cfg = demo_ws.config()
    assert cfg.agent.missions.model_dump() == {"opportunity_scout": False, "what_changed": False}
    assert cfg.schedules["mission-opportunity-scout"] == "0 9 * * fri"
    assert cfg.schedules["mission-what-changed"] == "0 7 * * *"
    engine = FakeEngine()
    assert missions.run_job(demo_ws, "opportunity_scout", scheduled=True, engine=engine)[0].startswith(
        "skipped"
    )
    assert engine.requests == []  # no tokens spent while off
    assert {"mission-opportunity-scout", "mission-what-changed"} <= set(JOBS)


def test_scout_runs_on_the_mission_model_and_notifies(demo_ws, monkeypatch):
    rec = _recorder(monkeypatch)
    _enable(demo_ws, opportunity_scout=True)
    engine = FakeEngine([
        ("tool", "list_gaps", {}),
        ("tool", "propose_pipeline_item", {"title": "Judge: Devpost AI Hackathon", "criterion": "judging",
                                           "url": "https://devpost.example/judges"}),
        ("text", "1. Judge the Devpost AI Hackathon (judging)."),
    ])  # fmt: skip
    lines = missions.run_job(demo_ws, "opportunity_scout", scheduled=True, engine=engine)
    assert lines[0].startswith("Opportunity scout: done, 1 proposal(s)")
    [run] = AgentRunner(demo_ws, engine=engine).runs()
    assert run.kind == "scheduled" and run.mission == "opportunity_scout"
    assert run.model == demo_ws.config().agent.models.mission == "claude-sonnet-5-5"
    assert engine.requests[0].model == "claude-sonnet-5-5"
    assert "opportunity scout" in engine.requests[0].prompt.lower()
    [note] = rec.sent
    assert note.event == "mission" and "1 suggestion(s)" in note.title and f"run={run.id}" in note.url
    assert any(c.title == "Judge: Devpost AI Hackathon" for c in demo_ws.pending_candidates())


def test_missions_respect_the_monthly_budget(demo_ws, monkeypatch):
    rec = _recorder(monkeypatch)
    _enable(demo_ws, opportunity_scout=True)
    cfg = demo_ws.config()
    cfg.agent.budget.monthly_usd = 0.01
    demo_ws.save_config(cfg)
    engine = FakeEngine(cost=0.02)
    assert missions.run_job(demo_ws, "opportunity_scout", scheduled=True, engine=engine)[0].startswith(
        "Opportunity"
    )
    second = missions.run_job(demo_ws, "opportunity_scout", scheduled=True, engine=engine)
    assert second[0].startswith("skipped: monthly budget reached")
    assert len(engine.requests) == 1 and len(rec.sent) == 1


def test_what_changed_skips_without_tokens_when_nothing_changed(demo_ws, monkeypatch):
    _recorder(monkeypatch)
    _enable(demo_ws, what_changed=True)
    # Mark deadlines done so none is due in the next three days and "nothing changed" is reachable.
    for d in demo_ws.deadlines().deadlines:
        demo_ws.update_deadline(d.id, done=True)
    engine = FakeEngine([("tool", "what_changed", {"since": "2026-01-01"}), ("text", "All quiet.")])
    first = missions.run_job(demo_ws, "what_changed", scheduled=True, engine=engine)
    assert first[0].startswith("What changed: done")
    assert "Daily check-in" in engine.requests[0].prompt
    second = missions.run_job(demo_ws, "what_changed", scheduled=True, engine=engine)
    assert second == [f"skipped: nothing changed since {AgentRunner(demo_ws).runs()[0].started_at.date()}; "
                      "no tokens spent"]  # fmt: skip
    assert len(engine.requests) == 1


def test_mission_failure_is_reported(demo_ws, monkeypatch):
    rec = _recorder(monkeypatch)
    _enable(demo_ws, opportunity_scout=True)
    lines = missions.run_job(
        demo_ws, "opportunity_scout", scheduled=True, engine=FakeEngine([("fail", "boom")])
    )
    assert "error" in lines[0]
    assert rec.sent[0].title == "Opportunity scout error"


def test_api_status_toggle_and_run_now(demo_ws, monkeypatch):
    rec = _recorder(monkeypatch)
    engine = FakeEngine([("text", "Scouted.")])
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine)) as c:
        status = {m["name"]: m for m in c.get("/api/agent/missions").json()}
        assert status["opportunity_scout"]["enabled"] is False
        assert status["what_changed"]["schedule"] == "0 7 * * *"
        assert status["opportunity_scout"]["model"] == "claude-sonnet-5-5"
        r = c.put("/api/settings/missions", json={"opportunity_scout": True}, headers=W)
        assert r.json()["opportunity_scout"] is True and demo_ws.changes()[-1].action == "settings.missions"
        assert c.get("/api/settings").json()["missions"]["opportunity_scout"] is True
        assert c.post("/api/agent/missions/nope/run", headers=W).status_code == 404
        run_id = c.post("/api/agent/missions/opportunity_scout/run", headers=W).json()["run_id"]
        events = c.get(f"/api/agent/runs/{run_id}/stream").text
        assert '"type": "done"' in events or '"type":"done"' in events
        run = c.get(f"/api/agent/runs/{run_id}").json()
        assert run["mission"] == "opportunity_scout" and run["kind"] == "scheduled"
        last = {m["name"]: m for m in c.get("/api/agent/missions").json()}["opportunity_scout"]["last_run"]
        assert last["id"] == run_id
    assert any(n.event == "mission" for n in rec.sent)


def test_stream_follows_a_run_started_in_another_runner(demo_ws, monkeypatch):
    """The scheduler runs missions in its own runner; the page's runner must still stream them to the end."""
    import anyio

    _recorder(monkeypatch)
    other = AgentRunner(demo_ws, engine=FakeEngine())

    async def go():
        run = await other.start("scheduled", "x", mission="what_changed")
        page = AgentRunner(demo_ws, engine=FakeEngine())
        events = [e async for e in page.stream(run.id)]
        return events[-1]

    last = anyio.run(go)
    assert last["type"] == "done" and last["run"]["status"] == "done"


def test_existing_configs_pick_up_new_jobs_and_events(tmp_path):
    from lighthouse_gc.core.models import NotificationsConfig, WorkspaceConfig

    cfg = WorkspaceConfig.model_validate({"schedules": {"sync": "0 6 * * *", "digest": ""}})
    assert cfg.schedules["sync"] == "0 6 * * *" and cfg.schedules["digest"] == ""  # user values win
    assert cfg.schedules["mission-what-changed"] == "0 7 * * *"
    routes = NotificationsConfig.model_validate({"routes": {"deadline": ["mail"]}}).routes
    assert routes["deadline"] == ["mail"] and routes["mission"] == ["desktop"]


def test_a_turned_off_schedule_is_not_scheduled(demo_ws):
    from lighthouse_gc.jobs import scheduler

    cfg = demo_ws.config()
    cfg.schedules["digest"] = ""
    demo_ws.save_config(cfg)
    sched = scheduler.start(demo_ws)
    try:
        assert "digest" not in {j.id for j in sched.get_jobs()}
        assert "mission-what-changed" in {j.id for j in sched.get_jobs()}
    finally:
        sched.shutdown(wait=False)
