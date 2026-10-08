"""Claude Code and Codex drive Area O1 over its MCP server (ADR 0015 §5): every workspace has the Claude Code skill and
AGENTS.md's Claude Code / Codex section, and both name exactly the MCP server's tools."""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from areao1.mcp.server import TOOL_NAMES
from areao1.scaffold import AGENT_GUIDE_HEADING, create_workspace, install_agent_guides
from areao1.server.app import create_app


def test_a_new_workspace_has_the_skill_and_the_codex_notes(tmp_path):
    ws = create_workspace(tmp_path / "case", name="T", git=False)
    skill = (ws.root / ".claude" / "skills" / "areao1" / "SKILL.md").read_text()
    guide = (ws.root / "AGENTS.md").read_text()
    assert skill.startswith("---\nname: areao1\ndescription: ")  # Claude Code skill frontmatter
    assert "claude mcp add areao1 -- areao1 mcp -w" in skill
    assert "codex mcp add areao1 -- areao1 mcp -w" in guide and "[mcp_servers.areao1]" in guide
    for text in (skill, guide):
        named = set(re.findall(r"`([a-z_]+)\(", text))
        assert named == set(TOOL_NAMES), (named, TOOL_NAMES)  # exactly the server's tools
        assert "eligibility verdict" in text or "qualifies" in text
    assert install_agent_guides(ws) == []  # nothing to add


def test_an_older_workspace_gets_them_on_start_without_losing_its_own_text(tmp_path):
    ws = create_workspace(tmp_path / "case", name="T", git=False)
    (ws.root / ".claude" / "skills" / "areao1" / "SKILL.md").unlink()
    (ws.root / "AGENTS.md").write_text("# My own notes\n\nKeep this.\n")
    with TestClient(create_app(ws, allowed_hosts=["testserver"])):
        pass
    guide = (ws.root / "AGENTS.md").read_text()
    assert guide.startswith("# My own notes\n\nKeep this.\n") and guide.count(AGENT_GUIDE_HEADING) == 1
    assert (ws.root / ".claude" / "skills" / "areao1" / "SKILL.md").is_file()
    with TestClient(create_app(ws, allowed_hosts=["testserver"])):
        pass
    assert (ws.root / "AGENTS.md").read_text().count(AGENT_GUIDE_HEADING) == 1  # once
