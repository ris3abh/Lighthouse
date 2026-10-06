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
    skipped: int = 0
    candidates_added: dict[str, int] = field(default_factory=dict)
    export_sha256: str = ""

    def line(self) -> str:
        added = ", ".join(f"{n} {k}" for k, n in sorted(self.candidates_added.items())) or "no new"
        kept = self.conversations - self.skipped
        skipped = f", {self.skipped} without suggestions not saved" if self.skipped else ""
        return (f"{self.provider}: {self.conversations} conversation(s) read, {kept} snapshotted "
                f"({self.snapshots_new} new){skipped}; {added} tracker candidate(s) in the Inbox. "
                "Self-reported: never counts toward a criterion.")  # fmt: skip


def import_chats(
    ws: Workspace, data: bytes, filename: str = "conversations.json", *, keep_all: bool = False
) -> ChatImportReport:
    """Import an export. Only conversations that produced suggestions are snapshotted, unless ``keep_all``."""
    provider, conversations, sha = chat_export.load_export(data, filename)
    mem = ws.memory
    before = {o.id for o in mem.observations()}
    proposals = []
    kept: list[str] = []
    with ws.lock:
        for conv in conversations:
            snapshot, cands = chat_export.candidates(conv)
            if cands or keep_all:
                mem.record(snapshot)
                kept.append(conv.id)
            proposals += cands
        # One manifest per export: its hash, how many conversations it had, and which ones were kept. The
        # export itself stays wherever you keep it; skipped conversations leave no content behind.
        manifest = Evidence(
            connector=f"{provider}_export",
            source_url=f"file:{filename}",
            payload={
                "provider": provider,
                "export_sha256": sha,
                "conversations": len(conversations),
                "snapshotted": sorted(kept),
                "keep_all": keep_all,
            },  # fmt: skip
            tier=chat_export.TIER,
            filename=filename,
        )
        mem.record(manifest)
        added = ws.add_candidates(proposals)
        new_snapshots = [
            o for o in mem.observations() if o.id not in before and o.source_url.startswith("chat:")
        ]
    ws.after_change()
    return ChatImportReport(
        provider=provider,
        conversations=len(conversations),
        snapshots_new=len(new_snapshots),
        skipped=len(conversations) - len(kept),
        candidates_added=dict(Counter(c.kind for c in added)),
        export_sha256=sha,
    )
