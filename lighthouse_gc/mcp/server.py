"""``lighthouse-gc mcp``: a read-only MCP server over one workspace (stdio by default).

    claude mcp add lighthouse -- lighthouse-gc mcp -w ~/my-case

Every tool is annotated read-only. Agents can query the scoreboard, gaps and the claim graph with full
provenance; they cannot change anything. Proposing claims or candidates (always through the Inbox)
comes in a later phase.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from lighthouse_gc import __version__
from lighthouse_gc.criteria.case import Case
from lighthouse_gc.mcp import tools

INSTRUCTIONS = """\
Lighthouse is the user's private, file-based memory for an O-1A / EB-1A evidence case.
All tools are read-only.
- Start a session with what_changed(since=<last session date>) and get_scoreboard().
- Every fact is a claim that quotes its source verbatim; check get_provenance(claim_id) before relying on one.
- Draft only from claims whose status is 'approved' and that are current. If proof is missing, say what is
  unknown. Don't fill the gap.
- An invitation is not a completion: respect each claim's and exhibit's stage.
- Lighthouse is not legal advice; any judgment you add is an opinion and must be labeled as one."""

READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

TOOL_NAMES = ("get_scoreboard", "list_gaps", "query_claims", "get_provenance", "what_changed")


def build_server(ws: Case) -> MCPServer:
    server: MCPServer = MCPServer(
        name="lighthouse",
        title="Lighthouse",
        instructions=INSTRUCTIONS,
        version=__version__,
        log_level="WARNING",
    )

    @server.tool(annotations=READ_ONLY)
    def get_scoreboard() -> dict[str, Any]:
        """Current criteria scoreboard for the active profile (banked / building / gap / dropped per criterion)."""
        return tools.get_scoreboard(ws)

    @server.tool(annotations=READ_ONLY)
    def list_gaps() -> dict[str, Any]:
        """Criteria not yet banked: missing exhibits and signals, in-progress items, pending Inbox candidates."""
        return tools.list_gaps(ws)

    @server.tool(annotations=READ_ONLY)
    def query_claims(entity: str, as_of: str | None = None) -> dict[str, Any]:
        """Claims about an entity (id like 'artifact:github:octo/repo' or a name fragment like 'fastgrad').
        Pass as_of=YYYY-MM-DD for what was valid and already known on that day."""
        return tools.query_claims(ws, entity, as_of)

    @server.tool(annotations=READ_ONLY)
    def get_provenance(claim_id: str) -> dict[str, Any]:
        """Provenance chain for one claim: source snapshot, verified verbatim excerpt, reviews, versions, citations."""
        return tools.get_provenance(ws, claim_id)

    @server.tool(annotations=READ_ONLY)
    def what_changed(since: str) -> dict[str, Any]:
        """Claims, reviews, exhibits, Inbox candidates and metric changes recorded on or after since=YYYY-MM-DD."""
        return tools.what_changed(ws, since)

    return server


def serve(ws: Case) -> None:
    build_server(ws).run("stdio")
