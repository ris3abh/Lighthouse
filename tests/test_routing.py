"""Model routing (D2, ADR 0009 §2): three tiers by task, from the environment or the workspace .env; OpenAI for
the mundane tier when its key is set, with the same redaction, cap and cost record; never a real call."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient
from test_chat_intake import CASE, RECIPE, W, _scan

from areao1.agent.routing import route, table
from areao1.core.models import AgentModels
from areao1.engine import openai_chat
from areao1.server.app import create_app

KEY = "sk-proj-test"


@pytest.fixture(autouse=True)
def no_env(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "AREAO1_MODEL_HARD",
        "AREAO1_MODEL_MID",
        "AREAO1_MODEL_MUNDANE",
    ):
        monkeypatch.delenv(name, raising=False)


def test_the_default_table():
    got = {r.task: (r.tier, r.provider, r.model) for r in table()}
    assert got["chat"] == got["manual"] == ("hard", "anthropic", "claude-opus-5-5")
    assert got["scheduled"] == got["check"] == got["pdf"] == ("mid", "anthropic", "claude-sonnet-5-5")
    assert got["chat_extract"] == got["summarize"] == ("mundane", "anthropic", "claude-haiku-4-5-20251001")
    assert route("chat", cheap=True).tier == "mid"  # cheap mode


def test_tiers_come_from_the_environment_or_the_workspace_env(monkeypatch, tmp_path):
    monkeypatch.setenv("AREAO1_MODEL_HARD", "claude-opus-5")
    assert route("chat").model == "claude-opus-5"
    (tmp_path / ".env").write_text("AREAO1_MODEL_MID=claude-sonnet-5\n")
    assert route("scheduled", workspace=tmp_path).model == "claude-sonnet-5"
    # an OpenAI model name without an OpenAI key stays on Claude
    monkeypatch.setenv("AREAO1_MODEL_MUNDANE", "gpt-5-nano")
    assert route("summarize").provider == "anthropic"
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    assert (route("summarize").provider, route("summarize").model) == ("openai", "gpt-5-nano")
    assert route("chat").provider == "anthropic"  # only the mundane tier moves


def test_a_model_chosen_in_areao1_yaml_still_wins(monkeypatch):
    monkeypatch.setenv("AREAO1_MODEL_HARD", "claude-opus-5")
    assert route("chat", AgentModels()).model == "claude-opus-5"  # the shipped default doesn't block the tier
    assert route("chat", AgentModels(chat="claude-sonnet-5-5")).model == "claude-sonnet-5-5"


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
        "anthropic",
        "claude-opus-5-5",
    )
    status = c.get("/api/agent/status").json()
    assert {r["task"] for r in status["routes"]} >= {"chat", "scheduled", "chat_extract"}


def _openai(http_mock, reply: str, usage=(1200, 300), status=200):
    body = {
        "choices": [{"message": {"content": reply}}],
        "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1]},
    }
    return http_mock.post(openai_chat.URL).respond(status, json=body)


def test_the_openai_call_is_redacted_and_costed(http_mock):
    import anyio

    r = _openai(http_mock, "ok")
    reply = anyio.run(
        openai_chat.openai_judge(KEY), "system", "Write to maya@example.com or 206-555-0100.", "gpt-5-mini"
    )
    sent = json.loads(r.calls.last.request.content)
    assert "maya@example.com" not in json.dumps(sent) and "206-555-0100" not in json.dumps(sent)
    assert r.calls.last.request.headers["authorization"] == f"Bearer {KEY}"
    assert reply.text == "ok" and reply.cost_usd == pytest.approx((1200 * 0.25 + 300 * 2.0) / 1e6)
    _openai(http_mock, "", status=429)
    with pytest.raises(RuntimeError, match="429"):
        anyio.run(openai_chat.openai_judge(KEY), "s", "p", "gpt-5-mini")


def test_chat_extraction_uses_openai_when_its_key_is_set_with_the_same_guards(ws, http_mock, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    reply = json.dumps({"items": [
        {"type": "deadline", "title": "NeurIPS reviewer sign-up", "due": "2026-10-20",
         "quote": "The NeurIPS reviewer sign-up deadline is 2026-10-20, remind me before then."},
        {"type": "decision", "title": "Paraphrased", "quote": "I decided to file in March."},  # not verbatim: dropped
    ]})  # fmt: skip
    r = _openai(http_mock, reply)
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    scan = _scan(c, [("conversations.json", json.dumps([CASE, RECIPE]).encode())])
    case_id = next(i["id"] for i in scan["items"] if i["title"] == "O-1A plan")
    out = c.post(f"/api/imports/chats/{scan['id']}/import", headers=W, json={"ids": [case_id]}).json()
    assert out["extracted_by"] == "gpt-5-mini" and len(r.calls) == 1
    assert "soak lentils" not in r.calls.last.request.content.decode()  # only the picked chat
    titles = {x.title for x in ws.pending_candidates() if x.fingerprint.startswith("chatx:")}
    assert titles == {"NeurIPS reviewer sign-up"}
    [run] = [x for x in c.get("/api/agent/runs").json() if "Chat-history extraction" in x["prompt"]]
    assert (run["provider"], run["tier"], run["model"]) == ("openai", "mundane", "gpt-5-mini") and run[
        "cost_usd"
    ] > 0


def test_the_monthly_cap_stops_openai_too(ws, http_mock, monkeypatch):
    from areao1.core.models import AgentRun

    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    r = _openai(http_mock, '{"items": []}')
    app = create_app(ws, allowed_hosts=["testserver"])
    c = TestClient(app)
    cap = ws.config().agent.budget.monthly_usd
    from areao1.agent.runner import AgentRunner

    AgentRunner(ws).save(
        AgentRun(kind="manual", engine="fake", model="x", prompt="spent", status="done", cost_usd=cap)
    )
    scan = _scan(c, [("conversations.json", json.dumps([CASE]).encode())])
    out = c.post(
        f"/api/imports/chats/{scan['id']}/import", headers=W, json={"ids": [scan["items"][0]["id"]]}
    ).json()
    assert out["extracted_by"] == "rules" and not r.called  # over the cap: read locally, nothing sent
