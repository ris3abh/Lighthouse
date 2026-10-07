"""Long chats and cheap mode (D3, ADR 0009 §3): older turns summarized on the mundane tier once replaying them would
pass ~6,000 tokens; the summary is saved, the originals kept; a failed summary never blocks the chat; cheap mode
runs chat on the mid tier."""

from __future__ import annotations

from agent_fakes import FakeEngine
from fastapi.testclient import TestClient

from lighthouse_gc.agent.runner import KEEP_TURNS, AgentRunner
from lighthouse_gc.core.models import Conversation, ConversationMessage
from lighthouse_gc.server.app import create_app

W = {"X-Lighthouse": "1"}
SUMMARY = "Maya judged HackSeattle 2025 and wants to file an O-1A in March 2027."


def _long_conv(ws, n=24, words=250) -> Conversation:
    msgs = [ConversationMessage(role="user" if i % 2 == 0 else "assistant", text=f"turn {i} " + "detail " * words)
            for i in range(n)]  # fmt: skip
    conv = Conversation(title="Planning", messages=msgs)
    AgentRunner(ws)._save_conversation(conv)
    return conv


def _chat(c, conv_id, message="What's next?"):
    out = c.post("/api/agent/chat", headers=W, json={"message": message, "conversation_id": conv_id}).json()
    for _ in range(200):
        run = c.get(f"/api/agent/runs/{out['run_id']}").json()
        if run["status"] != "running":
            return run
    raise AssertionError("the run never finished")


def test_a_long_chat_is_summarized_and_the_originals_kept(demo_ws):
    engine = FakeEngine([("text", SUMMARY)])
    conv = _long_conv(demo_ws)
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine)) as c:
        _chat(c, conv.id)
        saved = c.get(f"/api/agent/conversations/{conv.id}").json()
        runs = c.get("/api/agent/runs").json()
    assert saved["summary"] == SUMMARY and saved["summarized"] == 24 - KEEP_TURNS
    assert len(saved["messages"]) == 24 + 2  # nothing deleted: the new question and answer were added
    chat_prompt = engine.requests[-1].prompt
    assert (
        SUMMARY in chat_prompt and "turn 0 " not in chat_prompt and f"turn {24 - KEEP_TURNS} " in chat_prompt
    )
    [summ] = [r for r in runs if r["task"] == "summarize"]
    assert summ["tier"] == "mundane" and summ["model"] == "claude-haiku-4-5-20251001"


def test_a_short_chat_is_replayed_as_it_is(demo_ws):
    engine = FakeEngine([("text", "Sure.")])
    conv = _long_conv(demo_ws, n=8, words=10)
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine)) as c:
        _chat(c, conv.id)
        saved = c.get(f"/api/agent/conversations/{conv.id}").json()
    assert saved["summary"] == "" and len(engine.requests) == 1 and "turn 0 " in engine.requests[0].prompt


def test_a_summary_that_fails_never_blocks_the_chat(demo_ws):
    engine = FakeEngine([("fail", "model overloaded")])
    conv = _long_conv(demo_ws)
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine)) as c:
        _chat(c, conv.id)
        saved = c.get(f"/api/agent/conversations/{conv.id}").json()
    assert saved["summary"] == "" and saved["messages"][-1]["role"] == "assistant"


def test_summaries_go_through_the_same_guardrails(demo_ws):
    engine = FakeEngine([("text", "You are definitely eligible for the O-1A. Maya judged HackSeattle.")])
    conv = _long_conv(demo_ws)
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=engine)) as c:
        _chat(c, conv.id)
        saved = c.get(f"/api/agent/conversations/{conv.id}").json()
    assert "definitely eligible" not in saved["summary"] and "only USCIS decides" in saved["summary"]


def test_cheap_mode_runs_chat_on_the_mid_tier(demo_ws):
    with TestClient(create_app(demo_ws, allowed_hosts=["testserver"], engine=FakeEngine())) as c:
        status = c.put("/api/settings/agent", headers=W, json={"cheap_mode": True}).json()
        assert status["cheap_mode"] and status["model"] == "claude-sonnet-5-5"
        run = _chat(c, None, "hello")
        assert (run["tier"], run["model"]) == ("mid", "claude-sonnet-5-5")
        c.put("/api/settings/agent", headers=W, json={"cheap_mode": False})
        assert _chat(c, None, "hello")["tier"] == "hard"
    assert demo_ws.changes()[-1].action == "settings.agent"
