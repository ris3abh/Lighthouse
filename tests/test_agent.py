"""Agent layer (ADR 0005): engine adapters, grounded tools, the service layer, budgets. No model is called."""

from __future__ import annotations

import socket

import anyio
import pytest
from agent_fakes import FakeEngine

from lighthouse_gc.agent import tools as agent_tools
from lighthouse_gc.agent.redact import redact
from lighthouse_gc.agent.runner import AgentRunner, BudgetExceeded
from lighthouse_gc.agent.tools import RunContext, UnsafeURL, build_tools, check_url, html_to_text
from lighthouse_gc.core.models import AgentRun
from lighthouse_gc.engine import get_engine
from lighthouse_gc.engine.base import AgentEvent, AgentTool, EngineRequest, EngineUnavailable
from lighthouse_gc.engine.claude_code import BLOCKED_BUILTINS, ClaudeAgentEngine

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


# ----------------------------------------------------------------------------- the Claude adapter


def test_claude_adapter_is_locked_down():
    tools = [AgentTool("get_scoreboard", "x", {"type": "object", "properties": {}}, None, True),  # type: ignore[arg-type]
             AgentTool("propose_deadline", "x", {"type": "object", "properties": {}}, None, False)]  # type: ignore[arg-type]  # fmt: skip
    req = EngineRequest(system_prompt="sys", prompt="hi", model="claude-opus-5-5", effort="medium",
                        max_budget_usd=1.5, task_budget_tokens=50_000)  # fmt: skip
    opts = ClaudeAgentEngine(query=lambda **k: None).options(req, tools)
    assert opts.tools == ["WebSearch"]  # the only built-in tool
    assert set(opts.allowed_tools) == {
        "WebSearch",
        "mcp__lighthouse__get_scoreboard",
        "mcp__lighthouse__propose_deadline",
    }
    for blocked in ("Bash", "Read", "Write", "Edit", "WebFetch", "Glob", "Grep"):
        assert blocked in opts.disallowed_tools and blocked in BLOCKED_BUILTINS
    assert opts.strict_mcp_config is True and list(opts.mcp_servers) == ["lighthouse"]
    assert opts.setting_sources == []  # no user settings, hooks or CLAUDE.md
    assert opts.permission_mode == "dontAsk"
    assert "no-session-persistence" in opts.extra_args  # no transcripts in ~/.claude
    assert opts.model == "claude-opus-5-5" and opts.effort == "medium"
    assert opts.max_budget_usd == 1.5 and opts.task_budget["total"] == 50_000
    assert opts.include_partial_messages is True
    no_web = ClaudeAgentEngine(query=lambda **k: None).options(
        EngineRequest("s", "p", "m", web_search=False), tools
    )
    assert no_web.tools == [] and "WebSearch" not in no_web.allowed_tools


def test_claude_adapter_translates_the_sdk_stream():
    from claude_agent_sdk import (
        AssistantMessage,
        ResultMessage,
        StreamEvent,
        TextBlock,
        ToolResultBlock,
        ToolUseBlock,
        UserMessage,
    )  # fmt: skip

    async def fake_query(*, prompt, options):
        yield StreamEvent(uuid="u1", session_id="s", event={"type": "content_block_delta",
                                                            "delta": {"type": "text_delta", "text": "Look"}})  # fmt: skip
        tool_use = ToolUseBlock(id="t1", name="mcp__lighthouse__list_gaps", input={})
        usage = {"input_tokens": 1000, "output_tokens": 50, "cache_read_input_tokens": 9000}
        yield AssistantMessage(content=[tool_use], model="m", usage=usage, message_id="msg1")
        yield AssistantMessage(
            content=[TextBlock(text="")], model="m", usage=usage, message_id="msg1"
        )  # same msg
        yield UserMessage(
            content=[ToolResultBlock(tool_use_id="t1", content=[{"type": "text", "text": "2 gaps"}])]
        )
        yield AssistantMessage(content=[TextBlock(text="You have 2 gaps.")], model="m",
                               usage={"input_tokens": 1200, "output_tokens": 30}, message_id="msg2")  # fmt: skip
        yield ResultMessage(subtype="success", duration_ms=10, duration_api_ms=9, is_error=False, num_turns=2,
                            session_id="s", stop_reason="end_turn", total_cost_usd=0.0123, usage={}, result="done")  # fmt: skip

    events: list[AgentEvent] = []

    async def emit(ev):
        events.append(ev)

    result = anyio.run(
        lambda: ClaudeAgentEngine(query=fake_query).run(EngineRequest("s", "p", "m"), [], emit)
    )
    kinds = [e.type for e in events]
    assert kinds == ["text_delta", "tool_call", "usage", "tool_result", "text", "usage"]
    assert events[1].data == {"id": "t1", "name": "list_gaps", "input": {}}
    assert events[3].data["summary"] == "2 gaps" and events[3].data["ok"] is True
    assert events[2].data["input_tokens"] == 1000 and events[2].data["cache_read_input_tokens"] == 9000
    assert (
        result.text == "You have 2 gaps." and result.cost_usd == 0.0123 and result.stop_reason == "end_turn"
    )


def test_codex_is_stubbed_behind_the_same_interface():
    codex = get_engine("codex")
    assert codex.available()[0] is False
    with pytest.raises(EngineUnavailable):
        anyio.run(lambda: codex.run(EngineRequest("s", "p", "m"), [], None))
    with pytest.raises(EngineUnavailable):
        get_engine("gpt-whatever")


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
    assert redact("mail me at a.b@c.org, $185,000/yr or 92,000 USD, +1 (412) 555-0100") == (
        "mail me at [email], [amount]/yr or [amount], [phone]"
    )
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
    runner, _ = _runner(demo_ws, [("usage", {"input_tokens": 4000, "output_tokens": 500}),
                                  ("usage", {"input_tokens": 4000, "output_tokens": 500}),
                                  ("text", "never reached")])  # fmt: skip

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
            return False, "The `claude` CLI isn't on PATH."

    runner = AgentRunner(demo_ws, engine=Missing())
    assert runner.status()["available"] is False
    with pytest.raises(EngineUnavailable, match="claude"):
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


def test_model_per_run_type(demo_ws):
    cfg = demo_ws.config()
    assert (cfg.agent.models.chat, cfg.agent.models.task, cfg.agent.models.mission) == (
        "claude-opus-5-5",
        "claude-opus-5-5",
        "claude-sonnet-5-5",
    )
    cfg.agent.models.task = "claude-sonnet-5-5"
    demo_ws.save_config(cfg)
    runner, engine = _runner(demo_ws, [("text", "ok")])

    async def go(kind):
        run = await runner.start(kind, "hi")
        return (await runner.wait(run.id)).model

    assert anyio.run(go, "chat") == "claude-opus-5-5"
    assert anyio.run(go, "manual") == "claude-sonnet-5-5"
    assert anyio.run(go, "scheduled") == "claude-sonnet-5-5"
    assert [r.model for r in engine.requests] == ["claude-opus-5-5", "claude-sonnet-5-5", "claude-sonnet-5-5"]


def test_legacy_single_model_config_still_loads():
    from lighthouse_gc.core.models import AgentConfig

    cfg = AgentConfig.model_validate({"model": "claude-opus-5", "effort": "high"})
    assert (cfg.models.chat, cfg.models.task, cfg.models.mission) == (
        "claude-opus-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
    )
