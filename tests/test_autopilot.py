"""Autopilot: off by default; per-category auto-apply with one-click undo; nothing that could affect a criterion
is ever auto-applied, whatever the settings."""

from __future__ import annotations

import re
import socket
from datetime import date
from pathlib import Path

import anyio
import pytest
from agent_fakes import FakeEngine
from fastapi.testclient import TestClient

from lighthouse_gc.agent.autopilot import AUTO_ACTIONS, CRITERION_ACTIONS, AutopilotRefused, is_tier1
from lighthouse_gc.agent.runner import AgentRunner
from lighthouse_gc.agent.tools import RunContext, build_tools
from lighthouse_gc.core.models import AgentRun
from lighthouse_gc.core.workspace import WorkspaceError
from lighthouse_gc.server.app import create_app
from lighthouse_gc.service import Service

ROOT = Path(__file__).resolve().parent.parent
W = {"X-Lighthouse": "1"}
USCIS = "https://www.uscis.gov/forms/filing-fees"
USCIS_PAGE = (
    "<html><body><p>The new fee schedule takes effect on November 30, 2026 for Form I-129.</p></body></html>"
)
BLOG = "https://immigration-blog.example/fees"
SCHOLAR = "https://scholar.example/alex"
SCHOLAR_PAGE = "<html><body><p>Sparse gradient compression at scale. Cited by 71 papers.</p></body></html>"


def _on(ws, **flags):
    cfg = ws.config()
    cfg.agent.autopilot = cfg.agent.autopilot.model_copy(update=flags or {"tracker_updates": True, "metrics": True,
                                                                          "tier1_deadlines": True})  # fmt: skip
    ws.save_config(cfg)


def _tools(ws):
    ctx = RunContext(ws, AgentRun(kind="manual", engine="fake", model="t", prompt="p"))
    return ctx, {t.name: t for t in build_tools(ctx)}


def _web(monkeypatch, http_mock):
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [(2, 1, 6, "", ("93.184.216.34", p))])
    for url, page in ((USCIS, USCIS_PAGE), (BLOG, USCIS_PAGE), (SCHOLAR, SCHOLAR_PAGE)):
        http_mock.get(url).respond(200, text=page, headers={"content-type": "text/html"})


def _read(t, url):
    out = anyio.run(t["read_page"].handler, {"url": url})
    return re.search(r'"observation_id": "(obs_[0-9a-f]+)"', out).group(1)


def _snapshot(ws):
    return (ws.exhibits().model_dump(), {(c.id, c.status, c.exhibit_count) for c in ws.recompute().criteria},
            ws.config().overrides, ws.profile_id())  # fmt: skip


# ----------------------------------------------------------------------------- the policy itself


def test_autopilot_actions_never_include_anything_criterion_affecting():
    assert AUTO_ACTIONS and not AUTO_ACTIONS & CRITERION_ACTIONS
    assert {"pipeline.update", "pipeline.move", "letter.update", "deadline.update", "deadline.add",
                            "metrics.record"} >= AUTO_ACTIONS  # fmt: skip
    # Every action the service can perform is either explicitly auto-allowed or refused under autopilot.
    actions = set(
        re.findall(r'_record\(\s*"([a-z_]+\.[a-z_]+)"', (ROOT / "lighthouse_gc/service.py").read_text())
    )
    assert CRITERION_ACTIONS - {"settings.autopilot"} <= actions | {"inbox.accept"}
    assert "inbox.propose" not in AUTO_ACTIONS  # proposals are normal (approval) path, not autopilot


@pytest.mark.parametrize(
    "call",
    [
        lambda s, ws: s.accept_candidate(ws.pending_candidates()[0].id),
        lambda s, ws: s.reject_candidate(ws.pending_candidates()[0].id),
        lambda s, ws: s.edit_candidate(ws.pending_candidates()[0].id, summary="x"),
        lambda s, ws: s.add_exhibit_file(content=b"x", filename="a.pdf", criterion="judging",
                                         evidence_type="panel_letter", title="t", on=date(2026, 1, 1)),
        lambda s, ws: s.remap_exhibit(ws.exhibits().exhibits[0].id, "press"),
        lambda s, ws: s.set_override("press", "dropped"),
        lambda s, ws: s.set_profile("eb1a"),
        lambda s, ws: s.stage_upload(b"%PDF", "judge.pdf"),
        lambda s, ws: s.set_autopilot(metrics=True),
        lambda s, ws: s.add_pipeline_item(title="x"),
        lambda s, ws: s.delete_deadline(ws.deadlines().deadlines[0].id),
        lambda s, ws: s.add_letter(name="Dr. X", relationship="independent"),
    ],
    ids=["accept", "reject", "edit", "exhibit-upload", "remap", "override", "profile", "inbox-upload",
         "settings", "pipeline-add", "deadline-delete", "letter-add"],
)  # fmt: skip
def test_the_autopilot_service_refuses_everything_else(demo_ws, call):
    _on(demo_ws)
    before = _snapshot(demo_ws)
    with pytest.raises(AutopilotRefused):
        call(Service(demo_ws, actor="agent:test", auto=True), demo_ws)
    assert _snapshot(demo_ws) == before


def test_tier1_domains():
    assert is_tier1("https://www.uscis.gov/x") and is_tier1("https://ecfr.gov/y")
    assert not is_tier1("https://uscis.gov.evil.example/") and not is_tier1(
        "https://immigration-blog.example/"
    )


# ----------------------------------------------------------------------------- off by default


def test_off_by_default_everything_goes_to_the_inbox(demo_ws, monkeypatch, http_mock):
    _web(monkeypatch, http_mock)
    assert demo_ws.config().agent.autopilot.model_dump() == {"tracker_updates": False, "metrics": False,
                                                             "tier1_deadlines": False}  # fmt: skip
    _, t = _tools(demo_ws)
    item = demo_ws.pipeline().items[0]
    out = anyio.run(t["propose_tracker_update"].handler,
                    {"target_type": "pipeline_item", "target_id": item.id, "changes": {"stage": "waiting"}})  # fmt: skip
    assert "Proposed to the Inbox" in out and demo_ws.pipeline().items[0].stage == item.stage
    obs = _read(t, SCHOLAR)
    out = anyio.run(t["record_metric"].handler, {"item": "ICML 2025 paper", "metric": "citations", "value": 71,
                                                 "observation_id": obs, "quote": "Cited by 71 papers."})  # fmt: skip
    assert "Proposed" in out and not any(r.metric == "citations" for r in demo_ws.metrics())
    obs = _read(t, USCIS)
    out = anyio.run(t["propose_deadline"].handler, {"title": "New USCIS fee schedule", "due": "2026-11-30",
                                                    "observation_id": obs, "quote": "takes effect on November 30, 2026"})  # fmt: skip
    assert "Proposed" in out
    kinds = {c.kind for c in demo_ws.pending_candidates() if c.source.startswith("agent:")}
    assert kinds == {"update", "metric", "deadline"}
    assert not any(c.auto for c in demo_ws.changes())


# ----------------------------------------------------------------------------- on, per category


def test_tracker_updates_apply_and_undo(demo_ws):
    _on(demo_ws, tracker_updates=True)
    _, t = _tools(demo_ws)
    item = demo_ws.pipeline().items[0]
    out = anyio.run(t["propose_tracker_update"].handler,
                    {"target_type": "pipeline_item", "target_id": item.id, "changes": {"stage": "waiting"}})  # fmt: skip
    assert "automatically" in out
    assert demo_ws.pipeline().items[0].stage == "waiting"
    change = demo_ws.changes()[-1]
    assert change.auto and change.action == "pipeline.move" and change.actor.startswith("agent:")

    Service(demo_ws).undo(change.id)
    restored = demo_ws.pipeline().items[0]
    assert restored.stage == item.stage and restored.moved_at == item.moved_at  # exactly as before
    assert demo_ws.changes()[-1].undoes == change.id
    with pytest.raises(WorkspaceError, match="already undone"):
        Service(demo_ws).undo(change.id)


def test_fields_outside_the_allowlist_still_need_approval(demo_ws):
    _on(demo_ws, tracker_updates=True)
    _, t = _tools(demo_ws)
    item = demo_ws.pipeline().items[0]
    out = anyio.run(t["propose_tracker_update"].handler,
                    {"target_type": "pipeline_item", "target_id": item.id, "changes": {"criterion": "press"}})  # fmt: skip
    assert "Proposed to the Inbox" in out and demo_ws.pipeline().items[0].criterion == item.criterion
    letter = demo_ws.letters().letters[0]
    out = anyio.run(t["propose_tracker_update"].handler,
                    {"target_type": "letter", "target_id": letter.id, "changes": {"criteria": ["press"]}})  # fmt: skip
    assert "Proposed to the Inbox" in out


def test_undo_refuses_when_the_record_changed_since(demo_ws):
    _on(demo_ws, tracker_updates=True)
    _, t = _tools(demo_ws)
    letter = demo_ws.letters().letters[0]
    anyio.run(t["propose_tracker_update"].handler,
              {"target_type": "letter", "target_id": letter.id, "changes": {"status": "drafting"}})  # fmt: skip
    auto = demo_ws.changes()[-1]
    Service(demo_ws).update_letter(
        letter.id, status="signed"
    )  # the user moved on (only a person marks signed)
    with pytest.raises(WorkspaceError, match="changed again"):
        Service(demo_ws).undo(auto.id)
    assert demo_ws.letters().letters[0].status == "signed"


def test_metrics_apply_and_undo(demo_ws, monkeypatch, http_mock):
    _web(monkeypatch, http_mock)
    _on(demo_ws, metrics=True)
    _, t = _tools(demo_ws)
    obs = _read(t, SCHOLAR)
    with pytest.raises(ValueError, match="contain the number"):
        anyio.run(t["record_metric"].handler, {"item": "paper", "metric": "citations", "value": 99,
                                               "observation_id": obs, "quote": "Cited by 71 papers."})  # fmt: skip
    anyio.run(t["record_metric"].handler, {"item": "ICML 2025 paper", "metric": "citations", "value": 71,
                                           "observation_id": obs, "quote": "Cited by 71 papers."})  # fmt: skip
    [row] = [r for r in demo_ws.metrics() if r.metric == "citations"]
    assert row.value == 71 and row.source == "web"
    claim = next(c for c in demo_ws.memory.claims() if c.predicate == "citations")
    assert claim.excerpt == "Cited by 71 papers." and demo_ws.memory.verify() == []
    change = demo_ws.changes()[-1]
    assert change.auto and change.action == "metrics.record"
    Service(demo_ws).undo(change.id)
    assert not any(r.metric == "citations" for r in demo_ws.metrics())


def test_tier1_deadlines_only_from_tier1_pages(demo_ws, monkeypatch, http_mock):
    _web(monkeypatch, http_mock)
    _on(demo_ws, tier1_deadlines=True)
    _, t = _tools(demo_ws)
    quote = "takes effect on November 30, 2026"
    blog = _read(t, BLOG)
    out = anyio.run(t["propose_deadline"].handler, {"title": "Fee change (blog)", "due": "2026-11-30",
                                                    "observation_id": blog, "quote": quote})  # fmt: skip
    assert "Proposed" in out  # same text, but not a Tier-1 source
    uscis = _read(t, USCIS)
    out = anyio.run(t["propose_deadline"].handler, {"title": "New USCIS fee schedule", "due": "2026-11-30",
                                                    "observation_id": uscis, "quote": quote})  # fmt: skip
    assert "automatically" in out
    added = next(d for d in demo_ws.deadlines().deadlines if d.title == "New USCIS fee schedule")
    assert added.url == USCIS
    change = demo_ws.changes()[-1]
    Service(demo_ws).undo(change.id)
    assert not any(d.title == "New USCIS fee schedule" for d in demo_ws.deadlines().deadlines)
    # a deadline without a cited page is never auto-added
    out = anyio.run(t["propose_deadline"].handler, {"title": "Something", "due": "2026-12-01", "url": USCIS})
    assert "Proposed" in out


# ----------------------------------------------------------------------------- the proof


def test_criteria_never_move_without_approval_even_with_everything_on(demo_ws, monkeypatch, http_mock):
    """All three autopilot categories on; an agent run calls every write tool, including evidence proposals.
    No exhibit, criterion status, override or profile may change: evidence waits in the Inbox."""
    _web(monkeypatch, http_mock)
    _on(demo_ws)
    before = _snapshot(demo_ws)
    item, letter, deadline = (
        demo_ws.pipeline().items[0],
        demo_ws.letters().letters[0],
        demo_ws.deadlines().deadlines[0],
    )
    engine = FakeEngine([
        ("tool", "read_page", {"url": SCHOLAR}),
        ("tool", "read_page", {"url": USCIS}),
        ("tool", "propose_tracker_update", {"target_type": "pipeline_item", "target_id": item.id,
                                            "changes": {"stage": "done"}}),
        ("tool", "propose_tracker_update", {"target_type": "letter", "target_id": letter.id,
                                            "changes": {"status": "drafting"}}),
        ("tool", "propose_tracker_update", {"target_type": "deadline", "target_id": deadline.id,
                                            "changes": {"done": True}}),
        ("tool", "propose_pipeline_item", {"title": "Apply: ACM Senior Member", "criterion": "membership"}),
        ("tool", "propose_letter_writer", {"name": "Dr. Sam Ortiz", "relationship": "independent"}),
        ("text", "done"),
    ])  # fmt: skip

    async def go():
        runner = AgentRunner(demo_ws, engine=engine)
        run = await runner.start("scheduled", "do everything")
        run = await runner.wait(run.id)
        # second phase needs the observation ids the first phase produced
        obs = {s.url: s.observation_id for s in run.sources}
        engine.script = [
            ("tool", "record_metric", {"item": "ICML 2025 paper", "metric": "citations", "value": 71,
                                       "observation_id": obs[SCHOLAR], "quote": "Cited by 71 papers."}),
            ("tool", "propose_deadline", {"title": "USCIS fee schedule", "due": "2026-11-30",
                                          "observation_id": obs[USCIS], "quote": "takes effect on November 30, 2026"}),
            ("tool", "propose_evidence", {"criterion": "scholarly_articles", "evidence_type": "conference_paper",
                                          "title": "ICML paper citations", "summary": "71 citations",
                                          "observation_id": obs[SCHOLAR], "quote": "Cited by 71 papers."}),
            ("text", "done"),
        ]  # fmt: skip
        await runner.wait((await runner.start("scheduled", "and the rest")).id)

    anyio.run(go)
    assert all(ok for _, ok, _ in engine.tool_outputs), engine.tool_outputs
    assert _snapshot(demo_ws) == before  # nothing that counts toward a criterion moved
    auto = [c for c in demo_ws.changes() if c.auto]
    assert {c.action for c in auto} == {"pipeline.move", "letter.update", "deadline.update", "metrics.record",
                                        "deadline.add"}  # fmt: skip
    assert not {c.action for c in auto} & CRITERION_ACTIONS
    pending = [c for c in demo_ws.pending_candidates() if c.source.startswith("agent:")]
    assert {c.kind for c in pending} == {"evidence", "pipeline", "letter"}  # adds and evidence wait for you
    evidence = next(c for c in pending if c.kind == "evidence")
    assert evidence.proposed_criterion == "scholarly_articles"


# ----------------------------------------------------------------------------- API + Inbox


def test_api_settings_undo_and_inbox_acceptance(demo_ws):
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=FakeEngine()))
    assert c.get("/api/settings").json()["autopilot"] == {"tracker_updates": False, "metrics": False,
                                                          "tier1_deadlines": False}  # fmt: skip
    r = c.put("/api/settings/autopilot", json={"tracker_updates": True}, headers=W)
    assert r.json()["tracker_updates"] is True and demo_ws.config().agent.autopilot.tracker_updates
    assert demo_ws.changes()[-1].action == "settings.autopilot"

    _, t = _tools(demo_ws)
    item = demo_ws.pipeline().items[0]
    anyio.run(t["propose_tracker_update"].handler,
              {"target_type": "pipeline_item", "target_id": item.id, "changes": {"follow_up": "2026-10-30"}})  # fmt: skip
    listed = c.get("/api/changes").json()
    auto = next(x for x in listed if x["auto"])
    assert auto["undoable"] and not auto["undone"]
    assert c.post(f"/api/changes/{auto['id']}/undo", headers=W).status_code == 200
    assert next(x for x in c.get("/api/changes").json() if x["id"] == auto["id"])["undone"] is True
    assert c.post(f"/api/changes/{auto['id']}/undo", headers=W).status_code == 400

    # With autopilot off, an update waits in the Inbox; accepting it applies it.
    c.put("/api/settings/autopilot", json={"tracker_updates": False}, headers=W)
    anyio.run(t["propose_tracker_update"].handler,
              {"target_type": "pipeline_item", "target_id": item.id, "changes": {"stage": "waiting"}})  # fmt: skip
    cand = next(x for x in c.get("/api/inbox").json() if x["kind"] == "update")
    assert c.post(f"/api/inbox/{cand['id']}/accept", json={}, headers=W).status_code == 200
    assert demo_ws.pipeline().items[0].stage == "waiting"
