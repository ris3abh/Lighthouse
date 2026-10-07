"""Chat-history intake (C14a): whatever the person drops (an export .zip, several .json files, or a whole folder)
is read in memory, a manifest is followed to the files it lists, and each file goes through the adapter for its
format. Nothing is written here; the picker decides what reaches the workspace.

Adapters recognise Claude and ChatGPT exports by shape, not by file name, so a renamed or split export still
reads. A file no adapter recognises is named in a plain message, never dropped silently.
"""

from __future__ import annotations

import io
import json
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

from areao1.sources.chat_export import (
    MAX_EXPORT_BYTES,
    Conversation,
    ExportError,
    _parse_chatgpt,
    _parse_claude,
    _ts,
)

MAX_FILES = 20_000
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024  # uncompressed, across everything dropped
# Files an export carries that aren't chats; they're skipped quietly (and listed as skipped, not as failures).
NOT_CHATS = {"users.json", "memories.json", "user.json", "message_feedback.json", "model_comparisons.json",
             "shared_conversations.json", "chat.html", "user_settings.json"}  # fmt: skip


@dataclass
class Project:
    """A Claude Project: its instructions and knowledge files. Weighted highest by the relevance filter."""

    provider: str
    id: str
    name: str
    instructions: str = ""
    docs: list[tuple[str, str]] = field(default_factory=list)  # (file name, text)
    created: datetime | None = None

    @property
    def url(self) -> str:
        return f"chat:{self.provider}:project:{self.id}"

    def text(self) -> str:
        parts = [f"# Project: {self.name}", "", "## Instructions", "", self.instructions or "(none)", ""]
        for name, body in self.docs:
            parts += [f"## Knowledge: {name}", "", body, ""]
        return "\n".join(parts)


@dataclass
class Intake:
    conversations: list[Conversation] = field(default_factory=list)
    projects: list[Project] = field(default_factory=list)
    formats: list[str] = field(default_factory=list)  # what was recognised, for the person to see
    unread: list[tuple[str, str]] = field(default_factory=list)  # (file, why) for files no adapter took
    skipped: list[str] = field(default_factory=list)  # non-chat files in the export (attachments, settings)
    files: int = 0

    def summary(self) -> str:
        from areao1.core.text import plural

        bits = [plural(len(self.conversations), "conversation")]
        if self.projects:
            bits.append(plural(len(self.projects), "project"))
        return f"{' and '.join(bits)} from {plural(self.files, 'file')} ({'; '.join(self.formats) or 'nothing recognised'})"


# ----------------------------------------------------------------------------- the files


def gather(
    dropped: list[tuple[str, bytes]], left_out: list[tuple[str, str]] | None = None
) -> dict[str, bytes]:
    """Every dropped file, with .zip archives opened in memory (never extracted to disk). Paths keep their
    folders, so a manifest's relative paths resolve. Files inside an archive that aren't read go to `left_out`
    with the reason, so a drop that yields nothing can say why."""
    out: dict[str, bytes] = {}
    left_out = left_out if left_out is not None else []
    total = 0

    def add(name: str, data: bytes) -> None:
        nonlocal total
        total += len(data)
        if total > MAX_TOTAL_BYTES or len(out) >= MAX_FILES:
            raise ExportError(
                "that's more than 2 GB or 20,000 files; drop the export's conversations folder instead"
            )
        out[name.replace("\\", "/").lstrip("/")] = data

    for name, data in dropped:
        if zipfile.is_zipfile(io.BytesIO(data)):
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                entries = [i for i in zf.infolist() if not i.is_dir()]
                if not entries:
                    left_out.append((name, "the .zip is empty"))
                for info in entries:
                    if info.file_size > MAX_EXPORT_BYTES:
                        left_out.append((f"{name}/{info.filename}", "larger than 512 MB unpacked"))
                        continue
                    if (
                        PurePosixPath(info.filename).name.startswith((".", "__MACOSX"))
                        or "__MACOSX" in info.filename
                    ):
                        left_out.append((f"{name}/{info.filename}", "a hidden or Mac metadata file"))
                        continue
                    add(info.filename, zf.read(info))
        else:
            add(name, data)
    return out


def _manifest_paths(name: str, doc: Any, files: dict[str, bytes]) -> list[str]:
    """Paths a manifest lists that exist among the dropped files (relative to the manifest, or by suffix)."""
    wanted: list[str] = []

    def walk(v: Any) -> None:
        if isinstance(v, str) and v.lower().endswith(".json"):
            wanted.append(v)
        elif isinstance(v, dict):
            for x in v.values():
                walk(x)
        elif isinstance(v, list):
            for x in v:
                walk(x)

    walk(doc)
    base = PurePosixPath(name).parent
    found = []
    for w in wanted:
        rel = str((base / w.lstrip("./")).as_posix()) if str(base) != "." else w.lstrip("./")
        hit = (
            rel
            if rel in files
            else next((p for p in files if p.endswith("/" + w.lstrip("./")) or p == w), None)
        )
        if hit and hit not in found:
            found.append(hit)
    return found


# ----------------------------------------------------------------------------- adapters


def _claude_project(item: dict[str, Any]) -> Project:
    docs = [(str(d.get("filename") or d.get("name") or "file"), str(d.get("content") or ""))
            for d in item.get("docs") or item.get("files") or [] if isinstance(d, dict)]  # fmt: skip
    return Project("claude", str(item.get("uuid") or item.get("id") or ""), str(item.get("name") or "Untitled project"),
                   str(item.get("prompt_template") or item.get("instructions") or item.get("description") or ""),
                   docs, _ts(item.get("created_at")))  # fmt: skip


def _shape(item: Any) -> str | None:
    """Which adapter an object belongs to."""
    if not isinstance(item, dict):
        return None
    if "chat_messages" in item:
        return "claude"
    if "mapping" in item and ("current_node" in item or "title" in item):
        return "chatgpt"
    if ("prompt_template" in item or "docs" in item) and ("uuid" in item or "name" in item):
        return "claude_project"
    return None


LABELS = {
    "claude": "Claude conversations",
    "chatgpt": "ChatGPT conversations",
    "claude_project": "Claude Projects",
}


def read(dropped: list[tuple[str, bytes]]) -> Intake:
    """Read everything dropped. Raises ExportError naming the files when nothing at all could be read."""
    left_out: list[tuple[str, str]] = []
    files = gather(dropped, left_out)
    intake = Intake(files=len(files))
    order = sorted(files)
    manifests = [
        p for p in order if p.lower().endswith(".json") and "manifest" in PurePosixPath(p).name.lower()
    ]
    for m in manifests:  # follow the manifest first, in its order; the rest are still tried after
        try:
            listed = _manifest_paths(m, json.loads(files[m]), files)
        except ValueError:
            intake.unread.append((m, "the manifest isn't valid JSON"))
            continue
        order = [p for p in listed if p != m] + [p for p in order if p not in listed and p != m]
        intake.formats.append(f"followed {PurePosixPath(m).name} to {len(listed)} files")
        wanted = _manifest_wants(json.loads(files[m]))
        if len(listed) < wanted:
            left_out.append(
                (m, f"it lists {wanted} files and {wanted - len(listed)} of them weren't in what you dropped")
            )
    seen: dict[tuple[str, str], Conversation] = {}
    labels: dict[str, int] = {}
    for path in order:
        if path in manifests:
            continue
        name = PurePosixPath(path).name.lower()
        if not name.endswith(".json"):
            intake.skipped.append(path)
            continue
        if name in NOT_CHATS:
            intake.skipped.append(path)
            continue
        try:
            doc = json.loads(files[path])
        except ValueError:
            intake.unread.append((path, "not valid JSON"))
            continue
        items = (
            doc
            if isinstance(doc, list)
            else (doc.get("conversations") or doc.get("projects") or [doc])
            if isinstance(doc, dict)
            else []
        )
        took = 0
        for item in items:
            kind = _shape(item)
            if kind == "claude" or kind == "chatgpt":
                conv = (_parse_claude if kind == "claude" else _parse_chatgpt)(item)
                if conv.messages:
                    key = (conv.provider, conv.id or f"{path}:{took}")
                    seen[key] = conv  # a later file (a newer dated export) wins
                    took += 1
            elif kind == "claude_project":
                intake.projects.append(_claude_project(item))
                took += 1
            if kind:
                labels[LABELS[kind]] = labels.get(LABELS[kind], 0) + 1
        if not took:
            intake.unread.append((path, "not a Claude or ChatGPT format I know" if items else "empty"))
    intake.conversations = sorted(
        seen.values(), key=lambda c: c.created.timestamp() if c.created else 0, reverse=True
    )
    intake.formats += [k for k in LABELS.values() if k in labels]
    if not intake.conversations and not intake.projects:
        raise ExportError(no_chats_message(dropped, intake, left_out))
    return intake


def _manifest_wants(doc: Any) -> int:
    """How many .json files a manifest lists."""
    if isinstance(doc, str):
        return int(doc.lower().endswith(".json"))
    if isinstance(doc, dict):
        return sum(_manifest_wants(v) for v in doc.values())
    if isinstance(doc, list):
        return sum(_manifest_wants(v) for v in doc)
    return 0


def no_chats_message(
    dropped: list[tuple[str, bytes]], intake: Intake, left_out: list[tuple[str, str]]
) -> str:
    """What arrived and what happened to each file, when nothing in the drop was a chat. Never just "nothing"."""
    from areao1.core.text import plural

    received = ", ".join(n for n, _ in dropped[:4]) + (" …" if len(dropped) > 4 else "")
    why = [*left_out, *intake.unread, *((p, "not a chat file") for p in intake.skipped)]
    head = f"I couldn't find any Claude or ChatGPT chats in what you dropped ({plural(len(dropped), 'file')}: {received or 'none'})."
    if not why:
        return head + " The drop arrived empty. Drop the export .zip, or its whole folder."
    lines = "; ".join(f"{p}: {r}" for p, r in why[:6]) + (
        f"; and {len(why) - 6} more" if len(why) > 6 else ""
    )
    return f"{head} What happened to each: {lines}. Drop the export .zip, or its whole folder."
