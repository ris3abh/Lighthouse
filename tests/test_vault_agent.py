"""The agent uses the vault first; rule searches on the web are limited to Tier 1, then Tier 2; official pages
it reads become vault findings (observations, not reviewed sources)."""

from __future__ import annotations

import json
import re
from datetime import timedelta

import anyio
import httpx
from agent_fakes import FakeEngine
from test_rulecheck import QUOTE, RULE, FakeJudge
from test_vault import GENERIC, Pages, _at, public_dns  # noqa: F401  (fixture)

from lighthouse_gc.agent.runner import AgentRunner
from lighthouse_gc.agent.search_policy import SearchPolicy
from lighthouse_gc.agent.tools import RunContext, build_tools
from lighthouse_gc.core.models import AgentRun
from lighthouse_gc.engine.base import EngineRequest
from lighthouse_gc.engine.claude_code import ClaudeAgentEngine, _guard_hook
from lighthouse_gc.vault import Vault, load_manifest
from lighthouse_gc.vault.rulecheck import RuleChecker

OFFICIAL = "https://www.uscis.gov/newsroom/alerts/new-o-1-guidance"
BLOG = "https://immigration-blog.example/o1-guide"


def _policy():
    return SearchPolicy(load_manifest())


def _ask(policy, query, domains=None):
    data = {"query": query, **({"allowed_domains": domains} if domains is not None else {})}
    return anyio.run(lambda: policy("WebSearch", data))


# ----------------------------------------------------------------------------- the search policy


def test_open_searches_stay_open():
    p = _policy()
    assert _ask(p, "NeurIPS 2026 workshop reviewer call for volunteers") is None
    assert _ask(p, "Alex Rivera ICML 2025 paper") is None
    assert anyio.run(lambda: p("read_page", {"url": "x"})) is None  # only the built-in search is guarded


def test_rule_searches_need_the_vault_first_then_tier1_then_tier2():
    p = _policy()
    q = "I-129 O-1 filing fee 2026"
    assert "search_vault first" in _ask(p, q, ["uscis.gov"])
    p.vault_searched = True
    assert "allowed_domains" in _ask(p, q)  # unrestricted
    assert "Secondary sites" in _ask(p, q, ["uscis.gov", "boundless.com"])
    assert "Secondary" in _ask(p, q, ["uscis.gov.evil.example"])  # look-alike domain
    assert "Tier 1 domains first" in _ask(p, "Kazarian final merits", ["courtlistener.com"])
    assert _ask(p, q, ["www.uscis.gov", "https://ecfr.gov/"]) is None  # Tier 1, normalized
    assert _ask(p, "Kazarian final merits", ["courtlistener.com"]) is None  # Tier 2 after Tier 1
    assert [e["denied"] is None for e in p.log] == [False, False, False, False, False, True, True]


def test_claude_engine_wires_the_guard_as_a_websearch_hook():
    async def guard(tool, data):
        return "nope" if "fee" in data.get("query", "") else None

    opts = ClaudeAgentEngine(query=lambda **k: None).options(
        EngineRequest(system_prompt="s", prompt="p", model="m", guard=guard), []
    )
    [matcher] = opts.hooks["PreToolUse"]
    assert matcher.matcher == "WebSearch"
    hook = _guard_hook(guard)
    denied = anyio.run(
        lambda: hook({"tool_name": "WebSearch", "tool_input": {"query": "filing fee"}}, "t1", {})
    )
    assert denied["hookSpecificOutput"] == {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                            "permissionDecisionReason": "nope"}  # fmt: skip
    assert anyio.run(lambda: hook({"tool_name": "WebSearch", "tool_input": {"query": "cfp"}}, "t2", {})) == {}
    no_guard = ClaudeAgentEngine(query=lambda **k: None).options(
        EngineRequest(system_prompt="s", prompt="p", model="m"), []
    )
    assert no_guard.hooks is None


# ----------------------------------------------------------------------------- the agent, end to end


def _vault_ws(ws, http_mock):
    Pages(http_mock).install()
    anyio.run(lambda: Vault(ws).sync())
    return ws


def test_runs_enforce_vault_first(ws, http_mock, public_dns):  # noqa: F811
    _vault_ws(ws, http_mock)
    engine = FakeEngine([
        ("search", {"query": "EB-1A three of the ten criteria", "allowed_domains": ["uscis.gov"]}),
        ("tool", "search_vault", {"query": "EB-1A at least three of the ten criteria"}),
        ("search", {"query": "EB-1A three of the ten criteria"}),
        ("search", {"query": "EB-1A three of the ten criteria", "allowed_domains": ["uscis.gov"]}),
        ("search", {"query": "IEEE senior member application"}),
        ("text", "done"),
    ])  # fmt: skip

    async def go():
        runner = AgentRunner(ws, engine=engine, judge=FakeJudge())
        return await runner.wait((await runner.start("manual", "what does EB-1A need?")).id)

    run = anyio.run(go)
    searches = [(ok, out) for name, ok, out in engine.tool_outputs if name == "WebSearch"]
    assert [ok for ok, _ in searches] == [False, False, True, True]
    assert "search_vault first" in searches[0][1] and "allowed_domains" in searches[1][1]
    vault_out = json.loads(next(out for name, ok, out in engine.tool_outputs if name == "search_vault"))
    assert vault_out["results"] and any(r["tier"] == 1 and r["fresh"] for r in vault_out["results"])
    assert engine.requests[0].guard is not None
    assert any(i.tool == "WebSearch" and i.ok is False for i in run.timeline if i.type == "tool_call")


def test_search_vault_refetches_stale_sources_before_use(ws, http_mock, public_dns, monkeypatch):  # noqa: F811
    pages = Pages(http_mock)
    pages.install()
    vault = Vault(ws)
    anyio.run(lambda: vault.sync())
    _at(monkeypatch, timedelta(days=8))  # forms and fees are past their 7-day window
    pages.calls.clear()
    policy = SearchPolicy(vault.manifest)
    ctx = RunContext(ws, AgentRun(kind="manual", engine="fake", model="t", prompt="p"),
                     checker=RuleChecker(vault, None, "m"), search=policy)  # fmt: skip
    t = {x.name: x for x in build_tools(ctx)}
    out = json.loads(anyio.run(t["search_vault"].handler, {"query": "Form I-129 edition date", "tiers": [1]}))
    assert "uscis-i-129" in pages.calls and "uscis-i-129" in out["refreshed"]
    assert policy.vault_searched
    i129 = [r for r in out["results"] if "I-129" in r["source"]]
    assert i129 and i129[0]["fresh"] is True


def test_empty_vault_points_to_tier1_search(ws, public_dns):  # noqa: F811
    cfg = ws.config()
    cfg.vault.enabled = False
    ws.save_config(cfg)
    ctx = RunContext(ws, AgentRun(kind="manual", engine="fake", model="t", prompt="p"))
    t = {x.name: x for x in build_tools(ctx)}
    out = json.loads(anyio.run(t["search_vault"].handler, {"query": "premium processing business days"}))
    assert out["results"] == [] and "uscis.gov" in out["note"] and "Tier 2" in out["note"]


def test_official_pages_read_become_findings_but_never_verify_rules(ws, http_mock, public_dns):  # noqa: F811
    _vault_ws(ws, http_mock)
    page = GENERIC.format(title="New O-1 guidance", body=f"USCIS states that {RULE.lower()} {QUOTE} applies.")
    http_mock.get(OFFICIAL).mock(
        return_value=httpx.Response(200, text=page, headers={"content-type": "text/html"})
    )
    http_mock.get(BLOG).mock(
        return_value=httpx.Response(200, text=page, headers={"content-type": "text/html"})
    )
    ctx = RunContext(ws, AgentRun(kind="manual", engine="fake", model="t", prompt="p"))
    t = {x.name: x for x in build_tools(ctx)}
    out = json.loads(anyio.run(t["read_page"].handler, {"url": OFFICIAL}))
    assert "Tier 1 finding" in out["vault"]
    out = json.loads(anyio.run(t["read_page"].handler, {"url": BLOG}))
    assert "vault" not in out  # not an official domain

    vault = Vault(ws)
    [found] = vault.findings()
    assert found.url == OFFICIAL and found.tier == 1 and found.finding
    entry = vault.log()[-1]
    assert entry.origin == "agent" and entry.source_id == found.id
    hits = vault.search("new O-1 guidance three of the ten", k=12)
    assert any(h.source_id == found.id for h in hits)  # searchable
    # ... but rule-check never offers findings as evidence.
    judge = FakeJudge(rules=[("three of the ten", QUOTE, "entails", "New O-1 guidance")])
    check = anyio.run(lambda: RuleChecker(vault, judge, "m").check(RULE))
    assert check.claims[0].status != "verified" or all(
        c.source_id != found.id for c in check.claims[0].citations
    )
    assert "New O-1 guidance" not in judge.calls[0]
    # Findings aren't re-fetched by the watch.
    assert found.id not in {r.source_id for r in anyio.run(lambda: vault.sync(force=False))}
    assert re.match(r"found-[0-9a-f]{12}$", found.id)
