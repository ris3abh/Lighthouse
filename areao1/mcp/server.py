"""``areao1 mcp``: an MCP server over one workspace (stdio by default).

    claude mcp add areao1 -- areao1 mcp -w ~/my-case

Read tools are annotated read-only: the scoreboard, gaps and the claim graph with full provenance. The one write
tool, ``propose_context``, sends a note to the Inbox (tier self_reported). The person decides; nothing an AI tool
sends can become evidence or count toward a criterion (ADR 0008, C3).
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from areao1 import __version__
from areao1.core import names
from areao1.criteria.case import Case
from areao1.mcp import tools

INSTRUCTIONS = """\
Area O1 is the user's private, file-based memory for an O-1A / EB-1A evidence case.
All tools are read-only except propose_context.
- Start a session with what_changed(since=<last session date>) and get_scoreboard().
- Every fact is a claim that quotes its source verbatim; check get_provenance(claim_id) before relying on one.
- Draft only from claims whose status is 'approved' and that are current. If proof is missing, say what is
  unknown. Don't fill the gap.
- An invitation is not a completion: respect each claim's and exhibit's stage.
- Area O1 is not legal advice; any judgment you add is an opinion and must be labeled as one.
- When the person shares something important for their case (a deadline, an invitation, a letter writer, a
  result), offer to save it with propose_context. It goes to their Inbox for review and never counts as evidence.
  Send facts in their words, not your conclusions."""

READ_ONLY = ToolAnnotations(
    read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

WRITE_TO_INBOX = ToolAnnotations(
    read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
)

READ_TOOLS = ("get_scoreboard", "list_gaps", "query_claims", "get_provenance", "what_changed", "preflight")
TOOL_NAMES = (*READ_TOOLS, "propose_context")


def build_server(ws: Case) -> MCPServer:
    server: MCPServer = MCPServer(
        name=names.MCP_SERVER,
        title="Area O1",
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

    @server.tool(annotations=READ_ONLY)
    def preflight() -> dict[str, Any]:
        """Evidence preflight (ADR 0018): issues a reviewer would notice (outdated or unsupported values cited, facts
        that disagree, invited without completed proof, captures without a primary copy, undated exhibits), each with
        the claims and exhibits involved. Computed fresh; nothing is written. Severity says how noticeable an issue is."""
        from areao1.criteria import preflight as pf

        report = pf.run(ws, save=False)
        return {"summary": pf.summary(report), "counts": report["counts"],
                "issues": [i for i in report["issues"] if not i["dismissed"]][:100]}  # fmt: skip

    @server.tool(annotations=WRITE_TO_INBOX)
    def propose_context(text: str, title: str = "", topic: str = "", client: str = "") -> dict[str, Any]:
        """Send important context about the case to the person's Area O1 Inbox (e.g. "Accepted to judge HackMIT
        on Nov 8"). It's self-reported: the person reviews it, and it never counts toward a criterion. Up to 4,000
        characters. ``client`` names the tool sending it (e.g. "Claude Code")."""
        from areao1.service import Service

        cand = Service(ws, actor=f"mcp:{(client or 'client').strip()[:40]}").propose_context(
            text, title, client, topic
        )
        if cand is None:
            return {"status": "duplicate", "note": "That context is already in the Inbox."}
        return {"status": "proposed", "candidate_id": cand.id, "tier": "self_reported",
                "note": "Sent to the Inbox for review. It won't count toward any criterion."}  # fmt: skip

    return server


def serve(ws: Case) -> None:
    build_server(ws).run("stdio")
