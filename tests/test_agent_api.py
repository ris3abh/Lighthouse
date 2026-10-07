"""Agent HTTP API: chat, manual runs, the live SSE stream, conversations, status, errors. No model is called."""

from __future__ import annotations

import json

from agent_fakes import FakeEngine
from fastapi.testclient import TestClient

from areao1.server.app import create_app

W = {"X-AreaO1": "1"}


def _events(text: str) -> list[dict]:
    out = []
    for block in text.strip().split("\n\n"):
        data = next((line[6:] for line in block.splitlines() if line.startswith("data: ")), None)
        if data:
            out.append(json.loads(data))
    return out


def test_chat_streams_tool_calls_and_saves_the_conversation(demo_ws):
    engine = FakeEngine([
        ("text", "Checking your gaps."),
        ("tool", "list_gaps", {}),
        ("tool", "propose_pipeline_item", {"title": "Apply: ACM Senior Member", "criterion": "membership"}),
        ("usage", {"input_tokens": 2000, "output_tokens": 200}),
        ("text", "I proposed one pipeline item."),
    ])  # fmt: skip
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine)) as c:
        r = c.post("/api/agent/chat", json={"message": "What next?", "page": "overview"}, headers=W)
        assert r.status_code == 200, r.text
        run_id, conv_id = r.json()["run_id"], r.json()["conversation_id"]
        stream = c.get(f"/api/agent/runs/{run_id}/stream")
        assert stream.headers["content-type"].startswith("text/event-stream")
        events = _events(stream.text)
        types = [e["type"] for e in events]
        assert types[0] == "text_delta" and types[-1] == "done"
        calls = [e for e in events if e["type"] == "tool_call"]
        assert [e["name"] for e in calls] == ["list_gaps", "propose_pipeline_item"]
        assert calls[0]["read_only"] is True and "data/exhibits.json" in calls[0]["touches"]
        assert calls[1]["read_only"] is False and calls[1]["touches"] == ["data/inbox.json"]
        results = [e for e in events if e["type"] == "tool_result"]
        assert len(results[1]["proposals"]) == 1  # the panel links this to the Inbox
        done = events[-1]["run"]
        assert done["status"] == "done" and done["text"] == "I proposed one pipeline item."

        conv = c.get(f"/api/agent/conversations/{conv_id}").json()
        assert [m["role"] for m in conv["messages"]] == ["user", "assistant"]
        assert c.get("/api/agent/conversations").json()[0]["id"] == conv_id
        runs = c.get("/api/agent/runs").json()
        assert runs[0]["id"] == run_id and runs[0]["tool_calls"] == 2 and runs[0]["counted_tokens"] == 2200
        full = c.get(f"/api/agent/runs/{run_id}").json()
        assert [i["tool"] for i in full["timeline"] if i["type"] == "tool_call"] == [
            "list_gaps",
            "propose_pipeline_item",
        ]
        pending = [x for x in c.get("/api/inbox").json() if x["source"] == f"agent:{run_id}"]
        assert len(pending) == 1 and pending[0]["kind"] == "pipeline"

        # A finished run's stream returns the stored result at once.
        assert _events(c.get(f"/api/agent/runs/{run_id}/stream").text)[-1]["type"] == "done"


def test_manual_run_status_and_errors(demo_ws):
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=FakeEngine())) as c:
        status = c.get("/api/agent/status").json()
        assert status["available"] is True and status["models"]["mission"] == "claude-sonnet-5-5"
        assert status["budget"]["monthly_tokens"] == 10_000_000
        r = c.post("/api/agent/runs", json={"prompt": "Summarize my week"}, headers=W)
        run_id = r.json()["run_id"]
        assert _events(c.get(f"/api/agent/runs/{run_id}/stream").text)[-1]["run"]["kind"] == "manual"
        assert c.post("/api/agent/runs", json={"prompt": "  "}, headers=W).status_code == 400
        assert c.get("/api/agent/runs/run_nope").status_code == 404
        assert c.get("/api/agent/runs/run_nope/stream").status_code == 404
        assert c.post("/api/agent/chat", json={"message": "hi"}).status_code == 403  # write header required


def test_budget_and_unavailable_engine_errors(demo_ws):
    cfg = demo_ws.config()
    cfg.agent.budget.monthly_tokens = 1_000
    demo_ws.save_config(cfg)
    engine = FakeEngine([("usage", {"input_tokens": 1500})])
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine)) as c:
        run_id = c.post("/api/agent/runs", json={"prompt": "go"}, headers=W).json()["run_id"]
        c.get(f"/api/agent/runs/{run_id}/stream")
        r = c.post("/api/agent/runs", json={"prompt": "again"}, headers=W)
        assert r.status_code == 429 and "monthly token budget" in r.json()["detail"]

    class Missing(FakeEngine):
        def available(self):
            return False, "The `claude` CLI isn't on PATH."

    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=Missing())) as c:
        assert c.get("/api/agent/status").json()["available"] is False
        r = c.post("/api/agent/chat", json={"message": "hi"}, headers=W)
        assert r.status_code == 503 and "claude" in r.json()["detail"]


def test_changes_api_filters_by_actor(demo_ws):
    engine = FakeEngine([("tool", "propose_deadline", {"title": "CFP closes", "due": "2026-11-15"})])
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine)) as c:
        run_id = c.post("/api/agent/runs", json={"prompt": "go"}, headers=W).json()["run_id"]
        c.get(f"/api/agent/runs/{run_id}/stream")
        c.post("/api/deadlines", json={"title": "mine", "due": "2026-12-01"}, headers=W)
        mine = c.get(f"/api/changes?actor=agent:{run_id}").json()
        assert [x["action"] for x in mine] == ["inbox.propose"] and mine[0]["summary"] == "CFP closes"
        assert {x["actor"] for x in c.get("/api/changes").json()} == {"user", f"agent:{run_id}"}
        assert c.get(f"/api/agent/runs/{run_id}").json()["changes"] == [mine[0]["id"]]
