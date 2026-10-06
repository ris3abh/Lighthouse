"""Import a Claude / ChatGPT data export into the workspace (see :mod:`lighthouse_gc.sources.chat_export`)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from lighthouse_gc.core.models import Evidence
from lighthouse_gc.core.workspace import Workspace
from lighthouse_gc.sources import chat_export


@dataclass
class ChatImportReport:
    provider: str
    conversations: int
    snapshots_new: int
    candidates_added: dict[str, int] = field(default_factory=dict)
    export_sha256: str = ""

    def line(self) -> str:
        added = ", ".join(f"{n} {k}" for k, n in sorted(self.candidates_added.items())) or "no new"
        return (f"{self.provider}: {self.conversations} conversation(s) snapshotted ({self.snapshots_new} new); "
                f"{added} tracker candidate(s) in the Inbox. Self-reported: never counts toward a criterion.")  # fmt: skip


def import_chats(ws: Workspace, data: bytes, filename: str = "conversations.json") -> ChatImportReport:
    provider, conversations, sha = chat_export.load_export(data, filename)
    mem = ws.memory
    before = len(mem.observations())
    proposals = []
    with ws.lock:
        for conv in conversations:
            snapshot, cands = chat_export.candidates(conv)
            mem.record(snapshot)  # every conversation becomes a snapshot, extractions or not
            proposals += cands
        # One manifest per export: what was imported, when, and the export's hash (the export itself stays
        # wherever you keep it).
        mem.record(
            Evidence(
                connector=f"{provider}_export",
                source_url=f"file:{filename}",
                payload={
                    "provider": provider,
                    "export_sha256": sha,
                    "conversations": len(conversations),
                    "conversation_ids": sorted(c.id for c in conversations),
                },  # fmt: skip
                tier=chat_export.TIER,
                filename=filename,
            )
        )
        added = ws.add_candidates(proposals)
        snapshots_new = len(mem.observations()) - before - 1
    ws.after_change()
    return ChatImportReport(
        provider=provider,
        conversations=len(conversations),
        snapshots_new=max(0, snapshots_new),
        candidates_added=dict(Counter(c.kind for c in added)),
        export_sha256=sha,
    )
