"""Inbox bulk review (F9): candidates grouped by where they came from, filtered on the server, so a long Inbox (a
chat import can bring hundreds) can be reviewed a group at a time. Deciding goes through Service.bulk_inbox, one
item at a time, and one Undo reverses a batch."""

from __future__ import annotations

from typing import Any

from areao1.core import clock
from areao1.core.models import Candidate
from areao1.criteria.case import Case

PROVIDERS = {"chatgpt": "ChatGPT", "claude": "Claude"}


def group_of(c: Candidate) -> tuple[str, str]:
    """(key, label): a chat export by provider and import day, the agent, Gmail, uploads, or the source."""
    day = clock.local_date(c.created_at)
    when = f"{day:%b} {day.day}"
    src = c.source or "manual"
    if src.startswith("chat:"):
        name = PROVIDERS.get(src.split(":", 1)[1].lower(), src.split(":", 1)[1].title())
        return f"{src}@{day.isoformat()}", f"{name} export, {when}"
    if src == "agent" or src.startswith("agent"):
        return f"agent@{day.isoformat()}", f"Agent suggestions, {when}"
    if src.startswith("gmail:"):
        return "gmail", "Gmail"
    if src.startswith("mcp"):
        return "mcp", "From your AI tools (MCP)"
    if src in ("upload", "manual"):
        return "upload", "Your uploads"
    return src, src.replace(":", ": ", 1)


def matches(c: Candidate, f: dict[str, Any]) -> bool:
    if f.get("group") and group_of(c)[0] != f["group"]:
        return False
    if f.get("kind") and c.kind != f["kind"]:
        return False
    if f.get("criterion") and (c.proposed_criterion or "") != f["criterion"]:
        return False
    if f.get("text"):
        needle = str(f["text"]).lower()
        if needle not in f"{c.title} {c.summary}".lower():
            return False
    return f.get("min_confidence") is None or c.confidence >= float(f["min_confidence"])


def select(ws: Case, f: dict[str, Any]) -> list[Candidate]:
    return [c for c in ws.pending_candidates() if matches(c, f)]


def groups(ws: Case) -> list[dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for c in ws.pending_candidates():
        key, label = group_of(c)
        g = out.setdefault(key, {"key": key, "label": label, "count": 0, "kinds": {}})
        g["count"] += 1
        g["kinds"][c.kind] = g["kinds"].get(c.kind, 0) + 1
    return sorted(out.values(), key=lambda g: -g["count"])
