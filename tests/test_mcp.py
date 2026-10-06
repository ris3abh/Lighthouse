"""`lighthouse-gc mcp`: read-only tools over the demo workspace, in-process and over real stdio."""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.client import Client
from mcp.client.stdio import StdioServerParameters
from typer.testing import CliRunner

from lighthouse_gc.cli import app
from lighthouse_gc.mcp import tools
from lighthouse_gc.mcp.server import TOOL_NAMES, build_server


def _workspace_digest(root: Path) -> dict[str, str]:
    """Hash of every workspace file except the disposable cache."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file() and ".lighthouse/cache" not in p.relative_to(root).as_posix()
    }


def _structured(result) -> dict:
    if result.structured_content is not None:
        data = result.structured_content
        return data.get("result", data) if set(data) == {"result"} else data
    return json.loads(result.content[0].text)


# ----------------------------------------------------------------------------- the tool functions


def test_get_scoreboard(demo_ws):
    board = tools.get_scoreboard(demo_ws)
    assert board["profile"] == "o1a" and board["banked"] == 2 and board["threshold"] == 3
    judging = next(c for c in board["criteria"] if c["id"] == "judging")
    assert judging["status"] == "banked" and judging["in_progress"] == 1
    assert "not legal advice" in board["note"].lower()


def test_list_gaps(demo_ws):
    gaps = tools.list_gaps(demo_ws)
    ids = {g["id"] for g in gaps["gaps"]}
    assert {"press", "membership", "original_contributions", "awards", "critical_role"} <= ids
    assert not ids & {"judging", "scholarly_articles", "high_salary"}  # banked, banked, dropped
    assert gaps["still_needed_to_reach_threshold"] == 1
    oc = next(g for g in gaps["gaps"] if g["id"] == "original_contributions")
    assert oc["needs_exhibits"] == 1 and oc["pending_in_inbox"]  # tiny-vlm etc. are waiting in the Inbox
    awards = next(g for g in gaps["gaps"] if g["id"] == "awards")
    assert awards["needs_signals"] == 1 and awards["missing_signals"]


def test_query_claims_current_and_as_of(demo_ws):
    res = tools.query_claims(demo_ws, "fastgrad")
    assert res["matched_entities"] == ["artifact:github:arivera-demo/fastgrad"]
    stars = next(c for c in res["claims"] if c["predicate"] == "stars")
    assert stars["value"] == 1840 and stars["current"] and stars["status"] == "approved"
    assert stars["excerpt"] == '"stargazers_count": 1840'
    assert stars["source_url"] == "https://api.github.com/repos/arivera-demo/fastgrad"
    assert tools.query_claims(demo_ws, "fastgrad", as_of="2000-01-01")["claims"] == []
    assert tools.query_claims(demo_ws, "no-such-thing")["claims"] == []
    with pytest.raises(tools.ToolError):
        tools.query_claims(demo_ws, "fastgrad", as_of="last tuesday")


def test_get_provenance(demo_ws):
    stars = next(c for c in tools.query_claims(demo_ws, "fastgrad")["claims"] if c["predicate"] == "stars")
    prov = tools.get_provenance(demo_ws, stars["id"])
    assert prov["excerpt_verified"] is True
    assert prov["observation"]["source_url"].endswith("/repos/arivera-demo/fastgrad")
    assert prov["observation"]["snapshot"].startswith("memory/sources/")
    assert [r["decision"] for r in prov["reviews"]] == ["approved"]
    assert prov["cited_by"] and prov["cited_by"][0]["file"].startswith("evidence/original_contributions/")
    assert prov["extracted_by"]["name"] == "github"
    assert prov["prov"]["wasDerivedFrom"] == prov["observation"]["id"]
    with pytest.raises(tools.ToolError):
        tools.get_provenance(demo_ws, "clm_nope")


def test_what_changed(demo_ws):
    everything = tools.what_changed(demo_ws, "2000-01-01")
    assert everything["claims"] and everything["reviews"] and everything["exhibits_accepted"]
    since_october = tools.what_changed(demo_ws, "2026-10-01")
    stars = next(
        m
        for m in since_october["metric_changes"]
        if m["item"] == "arivera-demo/fastgrad" and m["metric"] == "stars"
    )
    assert stars["from"] == 1751 and stars["to"] == 1840 and stars["delta"] == 89
    future = tools.what_changed(demo_ws, "2099-01-01")
    assert not any(
        future[k] for k in ("claims", "reviews", "exhibits_accepted", "new_candidates", "metric_changes")
    )


def test_what_changed_reports_superseded_values(demo_ws, http_mock):
    from conftest import fixture_json

    from lighthouse_gc.jobs import sync as jobs

    repo = {**fixture_json("github", "repo_fastgrad.json"), "stargazers_count": 1900}
    http_mock.route(method="GET", host="api.github.com", path="/repos/arivera-demo/fastgrad").respond(
        json=repo
    )
    http_mock.route(method="GET", host="api.github.com").respond(json=[])
    demo_ws.remove_source("huggingface:arivera-demo")
    gh = demo_ws.sources().sources[0]
    demo_ws.update_source(gh.id, items=[i for i in gh.items if i.name == "arivera-demo/fastgrad"])
    jobs.snapshot(demo_ws, sleep=lambda s: None)
    changed = tools.what_changed(demo_ws, "2000-01-01")["claims"]
    stars = [c for c in changed if c["predicate"] == "stars" and c["change"] == "updated"]
    assert stars and stars[-1]["previous_value"] == 1840 and stars[-1]["value"] == 1900


def test_tools_never_write_the_workspace(demo_ws):
    before = _workspace_digest(demo_ws.root)
    tools.get_scoreboard(demo_ws)
    tools.list_gaps(demo_ws)
    claim = tools.query_claims(demo_ws, "tiny-vlm", as_of="2099-01-01")["claims"][0]
    tools.get_provenance(demo_ws, claim["id"])
    tools.what_changed(demo_ws, "2000-01-01")
    assert _workspace_digest(demo_ws.root) == before


# ----------------------------------------------------------------------------- over MCP


def test_server_exposes_exactly_the_read_only_tools(demo_ws):
    async def main():
        async with Client(build_server(demo_ws)) as client:
            listed = (await client.list_tools()).tools
            assert sorted(t.name for t in listed) == sorted(TOOL_NAMES)
            assert all(t.annotations and t.annotations.read_only_hint for t in listed)
            assert all(t.annotations.destructive_hint is False for t in listed)

            board = _structured(await client.call_tool("get_scoreboard", {}))
            assert board["banked"] == 2

            res = _structured(await client.call_tool("query_claims", {"entity": "fastgrad"}))
            stars = next(c for c in res["claims"] if c["predicate"] == "stars")
            prov = _structured(await client.call_tool("get_provenance", {"claim_id": stars["id"]}))
            assert prov["excerpt_verified"] is True

            bad = await client.call_tool("what_changed", {"since": "not-a-date"})
            assert bad.is_error

    anyio.run(main)


def test_mcp_over_stdio(demo_ws, tmp_path):
    """End to end: spawn `lighthouse-gc mcp` as a subprocess and talk to it over stdio."""
    exe = shutil.which("lighthouse-gc", path=str(Path(sys.executable).parent))
    assert exe, "lighthouse-gc entry point not installed in this environment"
    params = StdioServerParameters(command=exe, args=["mcp", "-w", str(demo_ws.root)])

    async def main():
        with anyio.fail_after(30):
            async with Client(params) as client:
                names = {t.name for t in (await client.list_tools()).tools}
                assert names == set(TOOL_NAMES)
                gaps = _structured(await client.call_tool("list_gaps", {}))
                assert gaps["still_needed_to_reach_threshold"] == 1

    anyio.run(main)


def test_cli_mcp_requires_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("LIGHTHOUSE_GC_WORKSPACE", raising=False)
    result = CliRunner().invoke(app, ["mcp"])
    assert result.exit_code == 1 and "No workspace found" in result.output
