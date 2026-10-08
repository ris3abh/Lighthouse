"""Model routing (D2, ADR 0009 §2, ADR 0015 §2): three tiers by task, one model per tier, all on OpenAI; the mundane
tier has the same redaction, cap and cost record as any run; never a real call."""

from __future__ import annotations

import json

from agent_fakes import FakeEngine
from fastapi.testclient import TestClient
from test_chat_intake import CASE, RECIPE, W, _scan

from areao1.agent.routing import DEFAULTS, route, table
from areao1.core.models import AgentModels
from areao1.server.app import create_app


def test_the_default_table():
    got = {r.task: (r.tier, r.provider, r.model) for r in table()}
    assert got["chat"] == got["manual"] == ("hard", "openai", "gpt-6.1-sol")
    assert got["scheduled"] == got["check"] == got["pdf"] == ("mid", "openai", "gpt-6.1-sol")
    assert got["chat_extract"] == got["summarize"] == got["classify"] == ("mundane", "openai", "gpt-6-luna")
    assert route("chat", cheap=True).tier == "mid"  # cheap mode
    assert DEFAULTS == {"hard": "gpt-6.1-sol", "mid": "gpt-6.1-sol", "mundane": "gpt-6-luna"}


def test_one_line_per_tier_in_areao1_yaml_and_the_environment_wins(monkeypatch, tmp_path):
    assert route("chat", AgentModels(hard="gpt-6-astra")).model == "gpt-6-astra"  # upgrade hard: one line
    assert route("scheduled", AgentModels(hard="gpt-6-astra")).model == "gpt-6.1-sol"  # mid unchanged
    monkeypatch.setenv("AREAO1_MODEL_HARD", "gpt-5.5")
    assert route("chat", AgentModels(hard="gpt-6-astra")).model == "gpt-5.5"
    (tmp_path / ".env").write_text("AREAO1_MODEL_MID=gpt-5.4\n")
    assert route("scheduled", workspace=tmp_path).model == "gpt-5.4"
    monkeypatch.setenv("AREAO1_MODEL_MUNDANE", "claude-haiku-4-5-20251001")  # from before ADR 0015
    assert route("summarize").model == "gpt-6-luna"


def test_runs_record_their_task_tier_and_provider(demo_ws):
    from agent_fakes import FakeEngine

    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=FakeEngine()))
    with c:
        run_id = c.post("/api/agent/runs", headers=W, json={"prompt": "hello"}).json()["run_id"]
        for _ in range(100):
            run = c.get(f"/api/agent/runs/{run_id}").json()
            if run["status"] != "running":
                break
    assert (run["task"], run["tier"], run["provider"], run["model"]) == (
        "manual",
        "hard",
        "openai",
        "gpt-6.1-sol",
    )
    status = c.get("/api/agent/status").json()
    assert {r["task"] for r in status["routes"]} >= {"chat", "scheduled", "chat_extract"}


def test_the_mundane_tier_is_redacted_and_costed(demo_ws):
    import anyio

    from areao1.agent.runner import AgentRunner

    engine = FakeEngine([("text", "ok")])
    judge, how = AgentRunner(demo_ws, engine=engine).mundane("summarize")
    reply = anyio.run(judge, "system", "Write to maya@example.com or 206-555-0100.", how.model)
    sent = json.dumps(engine.api.bodies[-1])
    assert "maya@example.com" not in sent and "206-555-0100" not in sent and "[email]" in sent
    assert reply.text == "ok" and how.model == "gpt-6-luna" and engine.api.bodies[-1]["model"] == "gpt-6-luna"
    assert "tools" not in engine.api.bodies[-1]  # tool-less, single turn


def test_chat_extraction_runs_on_the_mundane_tier_with_the_same_guards(ws):
    reply = json.dumps({"items": [
        {"type": "deadline", "title": "NeurIPS reviewer sign-up", "due": "2026-10-20",
         "quote": "The NeurIPS reviewer sign-up deadline is 2026-10-20, remind me before then."},
        {"type": "decision", "title": "Paraphrased", "quote": "I decided to file in March."},  # not verbatim: dropped
    ]})  # fmt: skip
    engine = FakeEngine([("usage", {"input_tokens": 1200, "output_tokens": 300}), ("text", reply)])
    c = TestClient(create_app(ws, allowed_hosts=["testserver"], engine=engine))
    scan = _scan(c, [("conversations.json", json.dumps([CASE, RECIPE]).encode())])
    case_id = next(i["id"] for i in scan["items"] if i["title"] == "O-1A plan")
    out = c.post(f"/api/imports/chats/{scan['id']}/import", headers=W, json={"ids": [case_id]}).json()
    assert out["extracted_by"] == "gpt-6-luna" and len(engine.api.bodies) == 1
    assert "soak lentils" not in json.dumps(engine.api.bodies[0])  # only the picked chat
    titles = {x.title for x in ws.pending_candidates() if x.fingerprint.startswith("chatx:")}
    assert titles == {"NeurIPS reviewer sign-up"}
    [run] = [x for x in c.get("/api/agent/runs").json() if "Chat-history extraction" in x["prompt"]]
    assert (run["provider"], run["tier"], run["model"]) == ("openai", "mundane", "gpt-6-luna") and run[
        "cost_usd"
    ] > 0


def test_the_monthly_cap_stops_the_mundane_tier_too(ws):
    from areao1.agent.runner import AgentRunner
    from areao1.core.models import AgentRun

    engine = FakeEngine([("text", '{"items": []}')])
    c = TestClient(create_app(ws, allowed_hosts=["testserver"], engine=engine))
    cap = ws.config().agent.budget.monthly_usd
    AgentRunner(ws).save(
        AgentRun(kind="manual", engine="fake", model="x", prompt="spent", status="done", cost_usd=cap)
    )
    scan = _scan(c, [("conversations.json", json.dumps([CASE]).encode())])
    out = c.post(
        f"/api/imports/chats/{scan['id']}/import", headers=W, json={"ids": [scan["items"][0]["id"]]}
    ).json()
    assert (
        out["extracted_by"] == "rules" and engine.api.bodies == []
    )  # over the cap: read locally, nothing sent
