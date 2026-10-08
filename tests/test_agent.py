"""Agent layer (ADR 0005, ADR 0015): the OpenAI engine, grounded tools, the service layer, budgets. No model is
called: OpenAI is the scripted fake in agent_fakes.py."""

from __future__ import annotations

import json
import re
import socket

import anyio
import httpx
import pytest
from agent_fakes import FakeEngine, ScriptedResponses, openai_usage, sse

from areao1.agent import tools as agent_tools
from areao1.agent.redact import redact
from areao1.agent.runner import AgentRunner, BudgetExceeded
from areao1.agent.tools import RunContext, UnsafeURL, build_tools, check_url, html_to_text
from areao1.core.models import AgentRun
from areao1.engine import get_engine
from areao1.engine.base import AgentEvent, AgentTool, EngineRequest, EngineUnavailable
from areao1.engine.openai_engine import PRICES, OpenAIEngine, cost

PAGE = """<html><head><title>MLH Fall 2026 judges</title><script>var x=1</script></head>
<body><nav>menu</nav><h1>Judges</h1><p>Alex Rivera will judge the ML track at MLH Fall 2026, held October 24.</p>
<p>Contact judges@mlh.example or call 412-555-0100.</p></body></html>"""


def _public_dns(monkeypatch, ip="93.184.216.34"):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, *a, **k: [(2, 1, 6, "", (ip, port))])


def _run(ws, kind="manual") -> AgentRun:
    return AgentRun(kind=kind, engine="fake", model="test", prompt="test")


def _tools(ws, run=None):
    ctx = RunContext(ws, run or _run(ws))
    return ctx, {t.name: t for t in build_tools(ctx)}


# ----------------------------------------------------------------------------- the OpenAI engine


def _tool(name, read_only=True, handler=None):
    async def default(args):
        return f"{name} ok"

    return AgentTool(name, "x", {"type": "object", "properties": {}}, handler or default, read_only)


def _collect():
    events: list[AgentEvent] = []

    async def emit(ev):
        events.append(ev)

    return events, emit


def test_openai_engine_offers_only_our_tools_and_stores_nothing():
    engine = FakeEngine([("text", "hi")])
    req = EngineRequest(system_prompt="sys", prompt="hello", model="gpt-6.1-sol", effort="high")
    anyio.run(
        lambda: engine.run(req, [_tool("get_scoreboard"), _tool("propose_deadline", False)], _collect()[1])
    )
    [body] = engine.api.bodies
    assert (
        body["model"] == "gpt-6.1-sol"
        and body["instructions"] == "sys"
        and body["reasoning"] == {"effort": "high"}
    )
    assert (
        body["store"] is False
        and body["include"] == ["reasoning.encrypted_content"]
        and body["stream"] is True
    )
    assert [(t["type"], t["name"]) for t in body["tools"]] == [("function", "get_scoreboard"),
                                                              ("function", "propose_deadline"), ("function", "web_search")]  # fmt: skip
    assert body["input"] == [{"role": "user", "content": "hello"}]
    assert len(body["prompt_cache_key"]) == 32  # stable per workspace and model, no prompt content
    again = FakeEngine([("text", "hi")])
    anyio.run(
        lambda: again.run(req, [_tool("get_scoreboard"), _tool("propose_deadline", False)], _collect()[1])
    )
    assert again.api.bodies[0]["prompt_cache_key"] == body["prompt_cache_key"]
    assert {k: v for k, v in again.api.bodies[0].items() if k != "input"} == {
        k: v for k, v in body.items() if k != "input"
    }


def test_openai_engine_translates_the_stream_and_prices_the_run():
    api = ScriptedResponses([("tool", "list_gaps", {}),
                             ("usage", {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 9000}),
                             ("text", "You have 2 gaps."), ("usage", {"input_tokens": 1200, "output_tokens": 30})])  # fmt: skip
    engine = OpenAIEngine(transport=httpx.MockTransport(api), key="sk-test")

    async def gaps(args):
        return "2 gaps"

    events, emit = _collect()
    result = anyio.run(
        lambda: engine.run(EngineRequest("s", "p", "gpt-6.1-sol"), [_tool("list_gaps", handler=gaps)], emit)
    )
    assert [e.type for e in events] == ["usage", "tool_call", "tool_result", "text_delta", "text", "usage"]
    assert events[1].data == {"id": "call_1", "name": "list_gaps", "input": {}}
    assert events[2].data == {"id": "call_1", "ok": True, "summary": "2 gaps"}
    assert events[0].data == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    assert events[5].data == {
        "input_tokens": 2200,
        "output_tokens": 80,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 9000,
    }
    assert result.text == "You have 2 gaps." and result.stop_reason == "end_turn"
    inp, cached, out = PRICES["gpt-6.1-sol"]
    assert result.cost_usd == pytest.approx((2200 * inp + 9000 * cached + 80 * out) / 1e6)
    second = api.bodies[1]["input"]
    assert second[1]["type"] == "function_call" and second[2] == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": "2 gaps",
    }


def test_cost_counts_cache_writes_and_searches_and_unknown_models_have_none():
    u = {
        "input_tokens": 100,
        "output_tokens": 10,
        "cache_creation_input_tokens": 1000,
        "cache_read_input_tokens": 0,
    }
    inp, _, out = PRICES["gpt-6-luna"]
    assert cost("gpt-6-luna", u, searches=2) == pytest.approx(
        (100 * inp + 1000 * inp * 1.25 + 10 * out) / 1e6 + 0.02
    )
    assert cost("some-new-model", u) is None


def test_reasoning_goes_back_encrypted_on_the_next_turn():
    reasoning = {"type": "reasoning", "id": "rs_1", "encrypted_content": "gAAA…", "summary": []}
    call = {"type": "function_call", "id": "fc_1", "call_id": "c1", "name": "list_gaps", "arguments": "{}"}
    bodies = []

    def handler(request):
        bodies.append(json.loads(request.content))
        if len(bodies) == 1:
            events = [{"type": "response.output_item.done", "output_index": 0, "item": reasoning},
                      {"type": "response.output_item.done", "output_index": 1, "item": call},
                      {"type": "response.completed", "response": {"status": "completed", "usage": openai_usage({})}}]  # fmt: skip
        else:
            msg = {"type": "message", "content": [{"type": "output_text", "text": "done"}]}
            events = [{"type": "response.output_item.done", "output_index": 0, "item": msg},
                      {"type": "response.completed", "response": {"status": "completed", "usage": openai_usage({})}}]  # fmt: skip
        return httpx.Response(200, content=sse(events))

    engine = OpenAIEngine(transport=httpx.MockTransport(handler), key="sk-test")
    result = anyio.run(lambda: engine.run(EngineRequest("s", "p", "m"), [_tool("list_gaps")], _collect()[1]))
    assert result.text == "done" and bodies[1]["input"][1] == reasoning and bodies[1]["input"][2] == call


def test_the_engine_enforces_the_dollar_cap_and_max_turns():
    many = [("tool", "list_gaps", {}), ("usage", {"input_tokens": 400_000})] * 5 + [("text", "never")]
    engine = OpenAIEngine(transport=httpx.MockTransport(ScriptedResponses(many)), key="sk-test")
    req = EngineRequest("s", "p", "gpt-6.1-sol", max_budget_usd=1.0)
    result = anyio.run(lambda: engine.run(req, [_tool("list_gaps")], _collect()[1]))
    assert result.stop_reason == "budget: max_budget_usd" and result.cost_usd == pytest.approx(
        1.6
    )  # stops between turns
    loop = OpenAIEngine(
        transport=httpx.MockTransport(ScriptedResponses([("tool", "list_gaps", {})] * 9)), key="sk-test"
    )
    result = anyio.run(
        lambda: loop.run(EngineRequest("s", "p", "m", max_turns=3), [_tool("list_gaps")], _collect()[1])
    )
    assert result.stop_reason == "max_turns"


def test_tool_errors_bad_arguments_and_unknown_tools_go_back_to_the_model():
    async def boom(args):
        raise ValueError("no such deadline")

    api = ScriptedResponses([("tool", "broken", {}), ("tool", "nope", {}), ("text", "sorry")])
    engine = OpenAIEngine(transport=httpx.MockTransport(api), key="sk-test")
    anyio.run(
        lambda: engine.run(EngineRequest("s", "p", "m"), [_tool("broken", handler=boom)], _collect()[1])
    )
    assert api.tool_outputs == [("broken", False, "Error: no such deadline"),
                                ("nope", False, "Error: there is no tool named 'nope'")]  # fmt: skip


def test_api_errors_are_plain():
    def refused(request):
        return httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})

    engine = OpenAIEngine(transport=httpx.MockTransport(refused), key="sk-test")
    with pytest.raises(RuntimeError, match="refused the API key"):
        anyio.run(lambda: engine.run(EngineRequest("s", "p", "m"), [], _collect()[1]))
    failing = OpenAIEngine(
        transport=httpx.MockTransport(ScriptedResponses([("fail", "overloaded")])), key="sk-test"
    )
    with pytest.raises(RuntimeError, match="overloaded"):
        anyio.run(lambda: failing.run(EngineRequest("s", "p", "m"), [], _collect()[1]))


def test_openai_is_the_only_engine(monkeypatch):
    from areao1.core.models import WorkspaceConfig
    from areao1.engine import connect

    for name in ("openai", "claude_code", "codex"):
        assert isinstance(get_engine(name), OpenAIEngine)
    assert WorkspaceConfig.model_validate({"engine": "claude_code"}).engine == "openai"
    monkeypatch.setattr(connect, "stored_key", lambda: None)
    no_key = OpenAIEngine(transport=httpx.MockTransport(ScriptedResponses([])))
    ok, why = no_key.available()
    assert ok is False and "OpenAI API key" in why
    with pytest.raises(EngineUnavailable):
        anyio.run(lambda: no_key.run(EngineRequest("s", "p", "m"), [], _collect()[1]))


# ----------------------------------------------------------------------------- web reading


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "192.168.1.20", "169.254.169.254", "::1", "fc00::1"])
def test_read_page_refuses_local_and_private_addresses(monkeypatch, ip):
    _public_dns(monkeypatch, ip)
    with pytest.raises(UnsafeURL, match="private or local"):
        check_url("https://innocent.example/page")


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.org/x", "http:///nohost"])
def test_read_page_refuses_other_schemes(url):
    with pytest.raises(UnsafeURL):
        check_url(url)


def test_redirects_are_rechecked(monkeypatch, http_mock):
    calls = {"n": 0}

    def dns(host, port, *a, **k):
        calls["n"] += 1
        return [(2, 1, 6, "", ("127.0.0.1" if host == "internal.example" else "93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", dns)
    http_mock.get("https://public.example/go").respond(
        302, headers={"location": "http://internal.example/admin"}
    )
    with pytest.raises(UnsafeURL):
        anyio.run(agent_tools.fetch_page, "https://public.example/go")
    assert calls["n"] == 2


def test_html_to_text_drops_scripts_and_navigation():
    title, text = html_to_text(PAGE)
    assert title == "MLH Fall 2026 judges"
    assert "var x" not in text and "menu" not in text and "Alex Rivera will judge" in text


# ----------------------------------------------------------------------------- tools


def test_read_page_snapshots_and_proposals_are_grounded(demo_ws, monkeypatch, http_mock):
    _public_dns(monkeypatch)
    http_mock.get("https://mlh.example/judges").respond(200, text=PAGE, headers={"content-type": "text/html"})
    ctx, t = _tools(demo_ws)

    out = anyio.run(t["read_page"].handler, {"url": "https://mlh.example/judges"})
    assert '"observation_id": "obs_' in out
    assert "[email]" in out and "[phone]" in out and "judges@mlh.example" not in out  # redacted for the model
    obs_id = ctx.run.sources[0].observation_id
    assert ctx.run.sources[0].url == "https://mlh.example/judges" and obs_id

    args = {"criterion": "judging", "evidence_type": "judge_invite", "title": "MLH Fall 2026 judge listing",
            "summary": "Listed as an ML-track judge.", "observation_id": obs_id, "stage": "invited"}  # fmt: skip
    with pytest.raises(ValueError, match="word for word"):
        anyio.run(t["propose_evidence"].handler, {**args, "quote": "Alex Rivera won first place"})
    with pytest.raises(ValueError, match="evidence_type"):
        anyio.run(t["propose_evidence"].handler, {**args, "evidence_type": "pay_stub",
                                                  "quote": "Alex Rivera will judge the ML track"})  # fmt: skip
    quote = "Alex Rivera will judge the ML track at MLH Fall 2026, held October 24."
    msg = anyio.run(t["propose_evidence"].handler, {**args, "quote": quote})
    assert "Proposed to the Inbox" in msg
    cand = next(c for c in demo_ws.pending_candidates() if c.source == f"agent:{ctx.run.id}")
    assert cand.kind == "evidence" and cand.proposed_criterion == "judging" and cand.stage == "invited"
    claim = next(c for c in demo_ws.memory.claims() if c.id in cand.claim_ids)
    assert claim.excerpt == quote and claim.extracted_by.name == "agent"
    assert demo_ws.memory.verify() == []
    [change] = [c for c in demo_ws.changes() if c.actor == f"agent:{ctx.run.id}"]
    assert change.action == "inbox.propose"
    assert ctx.run.proposals == [cand.id]
    assert "Already" in anyio.run(t["propose_evidence"].handler, {**args, "quote": quote})


def test_proposals_never_change_evidence_or_trackers(demo_ws):
    before = (demo_ws.exhibits().model_dump(), demo_ws.deadlines().model_dump(), demo_ws.pipeline().model_dump(),
              demo_ws.letters().model_dump(), {(c.id, c.status) for c in demo_ws.recompute().criteria})  # fmt: skip
    _, t = _tools(demo_ws)
    anyio.run(
        t["propose_deadline"].handler,
        {"title": "TMLR reviewer signup", "due": "2026-10-30", "kind": "submission"},
    )
    anyio.run(
        t["propose_pipeline_item"].handler, {"title": "Apply: ACM Senior Member", "criterion": "membership"}
    )
    anyio.run(t["propose_letter_writer"].handler, {"name": "Dr. Sam Ortiz", "relationship": "independent"})
    after = (demo_ws.exhibits().model_dump(), demo_ws.deadlines().model_dump(), demo_ws.pipeline().model_dump(),
             demo_ws.letters().model_dump(), {(c.id, c.status) for c in demo_ws.recompute().criteria})  # fmt: skip
    assert after == before  # only the Inbox grew
    kinds = {c.kind for c in demo_ws.pending_candidates() if c.source.startswith("agent:")}
    assert kinds == {"deadline", "pipeline", "letter"}
    with pytest.raises(ValueError):
        anyio.run(t["propose_deadline"].handler, {"title": "x", "due": "next week"})


def test_read_tools_and_redaction(demo_ws):
    person = demo_ws.person()
    person.aliases.append("alex@example.org")
    demo_ws.save_person(person)
    _, t = _tools(demo_ws)
    assert '"banked": 2' in anyio.run(t["get_scoreboard"].handler, {})
    assert "judging" in anyio.run(t["get_profile"].handler, {})
    assert "stars" in anyio.run(t["query_claims"].handler, {"entity": "fastgrad"})
    assert "Send draft letter" in anyio.run(t["list_deadlines"].handler, {})
    assert redact("1,840 stars on 2026-10-14") == "1,840 stars on 2026-10-14"


# ----------------------------------------------------------------------------- the runner


def _runner(ws, script, **kw):
    engine = FakeEngine(script, **kw)
    return AgentRunner(ws, engine=engine), engine


def test_a_run_is_recorded_with_everything_it_did(demo_ws):
    runner, engine = _runner(demo_ws, [
        ("tool", "list_gaps", {}),
        ("tool", "propose_deadline", {"title": "IEEE Senior Member references due", "due": "2026-10-25"}),
        ("usage", {"input_tokens": 4000, "output_tokens": 300, "cache_read_input_tokens": 20000}),
        ("text", "Membership is your easiest next criterion. I proposed the references deadline."),
    ])  # fmt: skip

    async def go():
        run = await runner.start("manual", "What should I do next?")
        return await runner.wait(run.id)

    run = anyio.run(go)
    assert run.status == "done" and run.kind == "manual" and run.cost_usd == 0.01
    assert [i.tool for i in run.timeline if i.type == "tool_call"] == ["list_gaps", "propose_deadline"]
    assert all(i.ok for i in run.timeline if i.type == "tool_call")
    assert run.text.startswith("Membership is your easiest")
    assert run.usage.counted == 4300 and run.usage.cache_read_input_tokens == 20000
    assert len(run.proposals) == 1 and len(run.changes) == 1
    assert (demo_ws.root / "agent" / "runs" / f"{run.id}.json").exists()
    assert "propose_deadline" in engine.tool_names and "read_page" in engine.tool_names
    assert runner.month_usage()["tokens"] == 4300


def test_chat_keeps_the_conversation_in_the_workspace(demo_ws):
    runner, engine = _runner(demo_ws, [("text", "You have 2 banked.")])

    async def go():
        first = await runner.start("chat", "Where do I stand?", page="overview")
        await runner.wait(first.id)
        second = await runner.start("chat", "And EB-1A?", conversation_id=first.conversation_id)
        await runner.wait(second.id)
        return first.conversation_id

    conv_id = anyio.run(go)
    conv = runner.conversation(conv_id)
    assert [(m.role, m.text) for m in conv.messages] == [
        ("user", "Where do I stand?"), ("assistant", "You have 2 banked."),
        ("user", "And EB-1A?"), ("assistant", "You have 2 banked."),
    ]  # fmt: skip
    assert "on the overview page" in engine.requests[0].prompt
    assert "Person: Where do I stand?" in engine.requests[1].prompt  # history replayed, nothing server-side
    assert (demo_ws.root / "agent" / "conversations" / f"{conv_id}.json").exists()


def test_per_run_token_cap_stops_the_run(demo_ws):
    cfg = demo_ws.config()
    cfg.agent.budget.per_run_tokens = 5_000
    demo_ws.save_config(cfg)
    runner, _ = _runner(
        demo_ws,
        [
            ("usage", {"input_tokens": 4000, "output_tokens": 500}),
            ("tool", "list_gaps", {}),
            ("usage", {"input_tokens": 4000, "output_tokens": 500}),
            ("tool", "list_gaps", {}),
            ("text", "never reached"),
        ],
    )  # fmt: skip  (usage arrives once per model turn)

    async def go():
        return await runner.wait((await runner.start("manual", "go")).id)

    run = anyio.run(go)
    assert run.status == "stopped" and "per-run token budget" in run.stop_reason
    assert run.text == ""


def test_monthly_caps_block_new_runs_and_cap_dollars(demo_ws):
    cfg = demo_ws.config()
    cfg.agent.budget.monthly_usd = 1.0
    cfg.agent.budget.per_run_usd = 5.0
    demo_ws.save_config(cfg)
    runner, engine = _runner(demo_ws, [("text", "ok")], cost=0.75)

    async def one():
        return await runner.wait((await runner.start("manual", "go")).id)

    anyio.run(one)
    assert engine.requests[0].max_budget_usd == 1.0  # min(per-run $5, monthly remaining $1)
    anyio.run(one)
    assert engine.requests[1].max_budget_usd == pytest.approx(0.25)
    with pytest.raises(BudgetExceeded, match="monthly budget"):
        anyio.run(one)


def test_stop_and_engine_errors(demo_ws):
    runner, _ = _runner(demo_ws, [("usage", {"input_tokens": 10})] * 50)

    async def stopped():
        run = await runner.start("manual", "go")
        runner.stop(run.id)
        return await runner.wait(run.id)

    assert anyio.run(stopped).status == "stopped"
    broken, _ = _runner(demo_ws, [("fail", "boom")])

    async def failing():
        return await broken.wait((await broken.start("manual", "go")).id)

    run = anyio.run(failing)
    assert run.status == "error" and "boom" in run.error


def test_stream_replays_then_ends(demo_ws):
    runner, _ = _runner(demo_ws, [("text", "a"), ("tool", "list_inbox", {}), ("text", "b")])

    async def go():
        run = await runner.start("manual", "go")
        return [e["type"] async for e in runner.stream(run.id)]

    types = anyio.run(go)
    assert types[0] == "text_delta" and "tool_call" in types and types[-1] == "done"


def test_unavailable_engine_is_reported(demo_ws):
    class Missing(FakeEngine):
        def available(self):
            return False, "Add an OpenAI API key in Settings > Your AI."

    runner = AgentRunner(demo_ws, engine=Missing())
    assert runner.status()["available"] is False
    with pytest.raises(EngineUnavailable, match="OpenAI API key"):
        anyio.run(runner.start, "manual", "hi")


@pytest.mark.parametrize(
    ("status", "body", "ctype", "message"),
    [
        (202, "", "text/html", "no readable content"),  # bot-protection challenge
        (200, "", "text/html", "no readable content"),
        (
            200,
            "<html><body><div id=root></div><script>app()</script></body></html>",
            "text/html",
            "almost no readable text",
        ),
        (200, "%PDF-1.4", "application/pdf", "only HTML and text"),
        (404, "nope", "text/html", "HTTP 404"),
    ],
)
def test_read_page_never_snapshots_an_empty_page(
    demo_ws, monkeypatch, http_mock, status, body, ctype, message
):
    _public_dns(monkeypatch)
    http_mock.get("https://site.example/p").respond(status, text=body, headers={"content-type": ctype})
    ctx, t = _tools(demo_ws)
    before = len(demo_ws.memory.observations())
    with pytest.raises(ValueError, match=message):
        anyio.run(t["read_page"].handler, {"url": "https://site.example/p"})
    assert len(demo_ws.memory.observations()) == before and ctx.run.sources == []


def test_one_model_per_tier(demo_ws):
    cfg = demo_ws.config()
    assert (cfg.agent.models.hard, cfg.agent.models.mid, cfg.agent.models.mundane) == ("gpt-6.1-sol", "gpt-6.1-sol",
                                                                                       "gpt-6-luna")  # fmt: skip
    cfg.agent.models.hard = "gpt-6-astra"  # upgrading a tier is one line
    demo_ws.save_config(cfg)
    runner, engine = _runner(demo_ws, [("text", "ok")])

    async def go(kind):
        run = await runner.start(kind, "hi")
        return (await runner.wait(run.id)).model

    assert anyio.run(go, "chat") == "gpt-6-astra"
    assert anyio.run(go, "manual") == "gpt-6-astra"
    assert anyio.run(go, "scheduled") == "gpt-6.1-sol"
    assert [r.model for r in engine.requests] == ["gpt-6-astra", "gpt-6-astra", "gpt-6.1-sol"]


def test_claude_era_model_config_still_loads():
    from areao1.core.models import AgentConfig

    cfg = AgentConfig.model_validate({"model": "claude-opus-5", "effort": "high"})
    assert (cfg.models.hard, cfg.models.mid, cfg.models.mundane) == (
        "gpt-6.1-sol",
        "gpt-6.1-sol",
        "gpt-6-luna",
    )
    cfg = AgentConfig.model_validate({"models": {"chat": "claude-opus-5-5", "task": "claude-opus-5-5",
                                                 "mission": "gpt-5.5", "check": "claude-sonnet-5-5"}})  # fmt: skip
    assert (cfg.models.hard, cfg.models.mid) == ("gpt-6.1-sol", "gpt-5.5")  # a non-Claude choice carries over


# ----------------------------------------------------------------------------- prompt caching


def _tool_defs(ws):
    ctx = RunContext(ws, _run(ws))
    return json.dumps([(t.name, t.description, t.input_schema) for t in build_tools(ctx)], sort_keys=True)


def test_cacheable_prefix_is_byte_stable(demo_ws, tmp_path):
    """System prompt + tool definitions are the cached prefix: identical across runs, no volatile content."""
    from areao1.agent.prompt import SYSTEM_PROMPT

    assert not re.search(r"\d{4}-\d{2}-\d{2}|\b(run|conv|cand|obs|clm)_[0-9a-f]{6,}", SYSTEM_PROMPT)
    assert _tool_defs(demo_ws) == _tool_defs(demo_ws)  # deterministic order and content
    runner, engine = _runner(demo_ws, [("text", "ok")])

    async def two():
        for kind in ("chat", "manual"):
            await runner.wait((await runner.start(kind, f"hello {kind}", page="inbox")).id)

    anyio.run(two)
    first, second = engine.requests
    assert first.system_prompt == second.system_prompt == SYSTEM_PROMPT
    # Per-run context (date, page, history) goes in the user turn, after the cached prefix.
    assert "Today is" in first.prompt and "Today is" not in first.system_prompt


def test_cache_usage_is_reported(demo_ws):
    runner, _ = _runner(demo_ws, [("usage", {"input_tokens": 40, "output_tokens": 200,
                                             "cache_creation_input_tokens": 0, "cache_read_input_tokens": 9000})])  # fmt: skip

    async def go():
        return await runner.wait((await runner.start("manual", "go")).id)

    run = anyio.run(go)
    assert run.usage.cache_read_input_tokens == 9000 and run.usage.counted == 240
    month = runner.month_usage()
    assert month["cache_read"] == 9000 and month["uncached_input"] == 40
    assert month["cache_hit_rate"] == pytest.approx(9000 / 9040, rel=1e-3)


def test_searches_are_counted_and_priced_in_the_run(demo_ws):
    """Web search is OpenAI's hosted search, on the same key: $10 per 1,000 searches plus the sub-request's tokens.
    Every run records how many ran and what they cost, inside cost_usd."""
    api = ScriptedResponses([("search", {"query": "NeurIPS 2026 reviewer call"}), ("text", "Found it.")])
    engine = OpenAIEngine(transport=httpx.MockTransport(api), key="sk-test")
    result = anyio.run(lambda: engine.run(EngineRequest("s", "p", "gpt-6.1-sol"), [], _collect()[1]))
    inp, _, out = PRICES["gpt-6.1-sol"]
    assert result.searches == 1 and result.search_usd == pytest.approx((10 * inp + 5 * out) / 1e6 + 0.01)
    assert result.cost_usd >= result.search_usd
    runner, fake = _runner(demo_ws, [("search", {"query": "NeurIPS 2026 reviewer call"}), ("text", "ok")])

    async def go():
        return await runner.wait((await runner.start("manual", "find calls")).id)

    run = anyio.run(go)
    assert run.searches == 1 and run.search_cost_usd > 0.01
