"""Import a Claude / ChatGPT data export into the workspace (see :mod:`areao1.sources.chat_export`)."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from areao1.core.models import Evidence
from areao1.core.text import plural
from areao1.core.workspace import Workspace
from areao1.sources import chat_export


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
        return (f"{self.provider}: {plural(self.conversations, 'conversation')} read, {kept} snapshotted "
                f"({self.snapshots_new} new){skipped}; {added} tracker {'suggestion' if sum(self.candidates_added.values()) == 1 else 'suggestions'} in the Inbox. "
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


@dataclass
class PickedImport:
    picked: int
    conversations: int
    projects: int
    candidates_added: dict[str, int] = field(default_factory=dict)
    extracted_by: str = "rules"
    cost_usd: float = 0.0
    usage: dict[str, int] = field(
        default_factory=dict
    )  # tokens the model used, so a cost never shows 0 tokens
    note: str = ""

    def line(self) -> str:
        added = sum(self.candidates_added.values())
        what = plural(self.picked, "item")
        tail = (f" Read by {self.extracted_by} (${self.cost_usd:.2f})." if self.extracted_by != "rules"
                else " Read with local rules only." + (f" {self.note}" if self.note else ""))  # fmt: skip
        return (f"Imported {what}: {plural(added, 'suggestion')} in your Inbox, each quoting your own words. "
                f"Self-reported: never counts toward a criterion.{tail}")  # fmt: skip


async def import_picked(
    ws: Workspace, intake: object, ids: set[str], judge: object = None, model: str = ""
) -> PickedImport:
    """Import only what the person ticked: each picked conversation or project is snapshotted (tier
    self_reported), read by the local rules, and, when a model is available, by the mundane-tier extractor.
    Anything not ticked leaves nothing in the workspace."""
    from areao1.sources import chat_extract, chat_relevance
    from areao1.sources.chat_intake import Intake

    assert isinstance(intake, Intake)
    convs, projects = chat_relevance.pick(intake, ids)
    proposals = []
    cost, used_model, note = 0.0, False, ""
    usage: Counter[str] = Counter()
    snapshots: list[tuple[object, Evidence, str]] = []
    for conv in convs:
        snapshot, cands = chat_export.candidates(conv)
        proposals += cands
        snapshots.append((conv, snapshot, {"claude": "Claude", "chatgpt": "ChatGPT"}[conv.provider]))
    for p in projects:
        snapshots.append((p, Evidence(connector=f"{p.provider}_export", source_url=p.url, payload=p.text(),
                                      media_type="text/markdown", tier=chat_export.TIER, filename="projects.json"),
                          "Claude"))  # fmt: skip
    if judge is not None:
        for source, snapshot, noun in snapshots:
            try:
                items, spent, used = await chat_extract.extract(judge, model, source)
                usage.update(used)
            except Exception as exc:  # the model failing never loses the rule-based suggestions
                note = f"The model couldn't read some of it ({str(exc)[:120]})."
                continue
            cost += spent
            used_model = True
            proposals += chat_extract.candidates(source, items, snapshot, noun)
    else:
        note = "Connect your AI for people, asks, decisions and metrics too."
    proposals, trimmed = chat_extract.tighten(ws, proposals)  # F10: notes that matter, no near-duplicates
    if trimmed["left_out"] or trimmed["merged"]:
        note = " ".join(x for x in (note, f"Left out {trimmed['left_out']} notes with no person, date, deadline or case "
                                    f"item; merged {trimmed['merged']} near-duplicates.") if x)  # fmt: skip
    with ws.lock:
        for _, snapshot, _ in snapshots:
            ws.memory.record(snapshot)
        ws.memory.record(Evidence(connector="chat_import", source_url="file:picked", tier=chat_export.TIER,
                                  payload={"formats": intake.formats, "files": intake.files,
                                           "offered": len(intake.conversations) + len(intake.projects),
                                           "picked": sorted(ids)},
                                  filename="picker"))  # fmt: skip
        added = ws.add_candidates(proposals)
    ws.after_change()
    return PickedImport(picked=len(convs) + len(projects), conversations=len(convs), projects=len(projects),
                        candidates_added=dict(Counter(c.kind for c in added)),
                        extracted_by=model if used_model else "rules", cost_usd=round(cost, 4), usage=dict(usage),
                        note=note)  # fmt: skip
