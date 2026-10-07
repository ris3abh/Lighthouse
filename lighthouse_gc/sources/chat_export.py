"""Claude / ChatGPT data-export import (``conversations.json`` or the export ``.zip``).

Every conversation becomes a content-addressed transcript snapshot in ``memory/`` with source tier
``self_reported``. A rule-based pass reads **only the user's own messages** (never the assistant's: an AI's
statement isn't a fact about you) and proposes tracker candidates: deadlines, pipeline items and letter
writers. Each one carries a low-confidence claim quoting the exact sentence it came from.

Self-reported items help you stay organized. They are never evidence: the workspace refuses to turn them
into exhibits, and the criteria engine ignores any self-reported exhibit.
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from lighthouse_gc.core import clock
from lighthouse_gc.core.models import Candidate, ClaimDraft, Evidence, slugify

Provider = Literal["claude", "chatgpt"]
MAX_EXPORT_BYTES = 512 * 1024 * 1024  # uncompressed conversations.json
TIER = "self_reported"


class ExportError(ValueError):
    pass


@dataclass
class Message:
    role: Literal["user", "assistant"]
    text: str
    at: datetime | None


@dataclass
class Conversation:
    provider: Provider
    id: str
    title: str
    created: datetime | None
    messages: list[Message] = field(default_factory=list)

    @property
    def url(self) -> str:
        return f"chat:{self.provider}:{self.id}"


# ----------------------------------------------------------------------------- loading


def load_export(
    data: bytes, filename: str = "conversations.json"
) -> tuple[Provider, list[Conversation], str]:
    """Parse an export. Returns (provider, conversations, sha256 of the conversations.json bytes)."""
    raw = _conversations_bytes(data, filename)
    try:
        items = json.loads(raw)
    except ValueError as exc:
        raise ExportError(f"{filename}: not valid JSON ({exc})") from exc
    if not isinstance(items, list):
        raise ExportError(f"{filename}: expected a list of conversations")
    provider = _detect(items)
    parse = _parse_claude if provider == "claude" else _parse_chatgpt
    convs = [c for c in (parse(item) for item in items if isinstance(item, dict)) if c.messages]
    return provider, convs, hashlib.sha256(raw).hexdigest()


def _conversations_bytes(data: bytes, filename: str) -> bytes:
    if not zipfile.is_zipfile(io.BytesIO(data)):
        if len(data) > MAX_EXPORT_BYTES:
            raise ExportError("export is larger than 512 MB")
        return data
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # Read in memory only; never extract archive paths to disk.
        names = [n for n in zf.namelist() if n.rsplit("/", 1)[-1] == "conversations.json"]
        if not names:
            raise ExportError(f"{filename}: no conversations.json inside the archive")
        info = zf.getinfo(min(names, key=len))
        if info.file_size > MAX_EXPORT_BYTES:
            raise ExportError("conversations.json is larger than 512 MB")
        return zf.read(info)


def _detect(items: list[Any]) -> Provider:
    for item in items:
        if isinstance(item, dict):
            if "chat_messages" in item:
                return "claude"
            if "mapping" in item:
                return "chatgpt"
    raise ExportError("not a Claude or ChatGPT conversations export")


def _ts(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, int | float):
        return datetime.fromtimestamp(value, UTC)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_claude(item: dict[str, Any]) -> Conversation:
    conv = Conversation("claude", str(item.get("uuid") or item.get("id") or ""), item.get("name") or "Untitled",
                        _ts(item.get("created_at")))  # fmt: skip
    for m in item.get("chat_messages") or []:
        text = m.get("text") or "\n".join(
            c.get("text", "")
            for c in m.get("content") or []
            if isinstance(c, dict) and c.get("type") == "text"
        )
        role = (
            "user" if m.get("sender") == "human" else "assistant" if m.get("sender") == "assistant" else None
        )
        if role and text.strip():
            conv.messages.append(Message(role, text.strip(), _ts(m.get("created_at"))))  # type: ignore[arg-type]
    return conv


def _parse_chatgpt(item: dict[str, Any]) -> Conversation:
    conv = Conversation("chatgpt", str(item.get("conversation_id") or item.get("id") or ""),
                        item.get("title") or "Untitled", _ts(item.get("create_time")))  # fmt: skip
    mapping: dict[str, Any] = item.get("mapping") or {}
    # Follow the branch the user actually ended on (current_node -> root); fall back to time order.
    path: list[dict[str, Any]] = []
    node_id = item.get("current_node")
    seen: set[str] = set()
    while node_id and node_id in mapping and node_id not in seen:
        seen.add(node_id)
        path.append(mapping[node_id])
        node_id = mapping[node_id].get("parent")
    nodes = list(reversed(path)) if path else sorted(
        mapping.values(), key=lambda n: ((n.get("message") or {}).get("create_time") or 0))  # fmt: skip
    for node in nodes:
        msg = node.get("message") or {}
        role = (msg.get("author") or {}).get("role")
        parts = (msg.get("content") or {}).get("parts") or []
        text = "\n".join(p for p in parts if isinstance(p, str)).strip()
        if role in ("user", "assistant") and text:
            conv.messages.append(Message(role, text, _ts(msg.get("create_time"))))
    return conv


# ----------------------------------------------------------------------------- transcripts


def transcript(conv: Conversation) -> str:
    """Deterministic markdown rendering of a conversation; excerpts index into this text."""
    when = clock.local_date(conv.created).isoformat() if conv.created else "unknown date"
    lines = [f"# {conv.title}", "", f"_{conv.provider} conversation {conv.id}, {when}_", ""]
    for m in conv.messages:
        stamp = m.at.isoformat(timespec="minutes") if m.at else ""
        lines += [f"### {m.role} {stamp}".rstrip(), "", m.text, ""]
    return "\n".join(lines)


# ----------------------------------------------------------------------------- extraction

MONTHS = {m: i + 1 for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}  # fmt: skip
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
DATE_PATTERNS = [
    (re.compile(r"\b(20\d\d)-(\d{2})-(\d{2})\b"), "ymd"),
    (re.compile(rf"\b{_MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(20\d\d))?\b", re.I), "mdy"),
    (re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?{_MON}(?:,?\s+(20\d\d))?\b", re.I), "dmy"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b"), "us"),
]
DEADLINE_WORDS = re.compile(
    r"\b(deadline|due|closes|close|expires|submit|apply|application|by|before|until|remind)\b", re.I
)
_NAME = r"(?P<name>(?:(?:Dr|Prof|Professor|Mr|Ms|Mrs)\.?\s+)?[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})"
_WHAT = r"(?P<what>[A-Z0-9][^.,;!?\n]{2,80}?)"
_STOP = r"(?=\s+(?:last|next|this|in|on|and|but|which|that|yesterday|today)\b|[.,;!?\n]|$)"

PIPELINE_RULES: list[tuple[re.Pattern[str], str, str | None]] = [
    # (pattern, pipeline stage, claim stage)
    (re.compile(rf"\bI\s+(?:was|got|have been|am)\s+invited\s+to\s+(?:judge|review\s+for|speak\s+at|give\s+a\s+talk\s+at)\s+(?:the\s+)?{_WHAT}{_STOP}"), "waiting", "invited"),
    (re.compile(rf"\bI\s+(?:just\s+)?(?:judged|reviewed\s+for|spoke\s+at)\s+(?:the\s+)?{_WHAT}{_STOP}"), "done", "completed"),
    (re.compile(rf"\bI\s+(?:just\s+)?(?:applied|submitted\s+(?:my|an)\s+application|sent\s+(?:my|an)\s+application)\s+(?:to|for)\s+(?:the\s+)?{_WHAT}{_STOP}"), "applied", "applied"),
    (re.compile(rf"\b(?:waiting\s+to\s+hear\s+back|still\s+waiting|haven't\s+heard\s+back)\s+(?:from|on|about)\s+(?:the\s+)?{_WHAT}{_STOP}", re.I), "waiting", None),
    (re.compile(rf"\bI\s+(?:want|plan|need|should)\s+to\s+apply\s+(?:to|for)\s+(?:the\s+)?{_WHAT}{_STOP}"), "idea", None),
]  # fmt: skip
LETTER_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(rf"\bI\s+(?:asked|emailed|reached\s+out\s+to)\s+{_NAME}\s+(?:for|about|to\s+write)\s+(?:a\s+|my\s+)?(?:recommendation|reference|support|expert)?\s*letter"), "asked"),
    (re.compile(rf"\b{_NAME}\s+(?:agreed|said\s+yes|is\s+happy|offered)\s+to\s+write"), "drafting"),
    (re.compile(rf"\b{_NAME}\s+(?:signed|sent\s+(?:me\s+)?(?:the|my))\s+(?:signed\s+)?letter"), "signed"),
    (re.compile(rf"\b{_NAME}\s+(?:declined|said\s+no|can't\s+write|cannot\s+write)"), "declined"),
]  # fmt: skip
EMPLOYER = re.compile(
    r"\b(my\s+(manager|boss|employer|lead|cto|vp)|at\s+my\s+company|works?\s+with\s+me)\b", re.I
)
COAUTHOR = re.compile(r"\b(co-?author|collaborator|we\s+wrote)\b", re.I)
_NOT_NAMES = {"I", "The", "My", "He", "She", "They", "We", "It", "This", "That", "Remind"}


@dataclass
class Extraction:
    kind: Literal["deadline", "pipeline", "letter"]
    key: str
    title: str
    sentence: str
    claim: ClaimDraft
    proposal: dict[str, Any]
    stage: str | None = None


# Sentence ends, except after common title abbreviations ("Dr. Priya Natarajan" is one sentence).
_SENTENCE_END = re.compile(
    r"(?<!\bDr\.)(?<!\bMr\.)(?<!\bMs\.)(?<!\bMrs\.)(?<!\bProf\.)(?<!\bSt\.)(?<!\be\.g\.)(?<!\bi\.e\.)"
    r"(?<=[.!?])\s+|\n+"
)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s.strip()]


def find_date(sentence: str, ref: date) -> date | None:
    for pattern, kind in DATE_PATTERNS:
        m = pattern.search(sentence)
        if not m:
            continue
        try:
            if kind == "ymd":
                return date(int(m[1]), int(m[2]), int(m[3]))
            if kind == "us":
                return date(int(m[3]), int(m[1]), int(m[2]))
            if kind == "mdy":
                month, day, year = MONTHS[m[1][:3].lower()], int(m[2]), m[3]
            else:
                day, month, year = int(m[1]), MONTHS[m[2][:3].lower()], m[3]
            when = date(int(year) if year else ref.year, month, day)
            if not year and when < ref - timedelta(days=30):
                when = date(ref.year + 1, month, day)  # "Nov 1" said in December means next year
            return when
        except (ValueError, KeyError):
            continue
    return None


def _deadline_kind(sentence: str) -> str:
    s = sentence.lower()
    if re.search(r"\bappl(y|ication)", s):
        return "application"
    if re.search(r"\b(submit|review|paper|abstract)", s):
        return "submission"
    if re.search(r"\b(fil(e|ing)|petition|i-129|i-140)\b", s):
        return "filing"
    if re.search(r"\b(follow.?up|remind|send|email)\b", s):
        return "follow_up"
    return "other"


def extract(conv: Conversation) -> list[Extraction]:
    """Tracker items from the user's own messages. Each sentence quoted verbatim as the claim's excerpt."""
    out: list[Extraction] = []
    for msg in conv.messages:
        if msg.role != "user":
            continue
        ref = clock.local_date(msg.at or conv.created or clock.utcnow())
        for sentence in _sentences(msg.text):
            out += _letters(sentence, ref) + _pipeline(sentence, ref)
            due = find_date(sentence, ref)
            if due and due >= ref and DEADLINE_WORDS.search(sentence):
                title = re.sub(r"^(remind me:?|also,?|and|so)\s+", "", sentence, flags=re.I).rstrip(".!")
                title = title[:1].upper() + title[1:]
                out.append(Extraction(
                    kind="deadline", key=f"{slugify(title, 40)}:{due.isoformat()}", title=title[:120],
                    sentence=sentence,
                    claim=_claim(f"task:{slugify(title, 40)}", title[:80], "deadline", due.isoformat(), sentence,
                                 ref, kind="event", event_date=due),
                    proposal={"title": title[:120], "due": due.isoformat(), "kind": _deadline_kind(sentence),
                              "human_only": True},
                ))  # fmt: skip
    return out


def _pipeline(sentence: str, ref: date) -> list[Extraction]:
    for pattern, stage, claim_stage in PIPELINE_RULES:
        m = pattern.search(sentence)
        if not m:
            continue
        what = m["what"].strip()
        criterion = "judging" if re.search(r"\b(judge|judged|review)", sentence, re.I) else None
        title = {"waiting": f"Waiting on: {what}", "done": f"Done: {what}", "applied": f"Applied: {what}",
                 "idea": f"Apply to {what}"}[stage]  # fmt: skip
        if claim_stage == "invited":
            title = f"Invited: {what}"
        return [Extraction(
            kind="pipeline", key=slugify(what, 40), title=title, sentence=sentence, stage=claim_stage,
            claim=_claim(f"event:{slugify(what, 40)}", what, "pipeline_stage", stage, sentence, ref,
                         kind="event", stage=claim_stage),
            proposal={"title": title, "stage": stage, "criterion": criterion,
                      "notes": "From your own chat history (self-reported). Not evidence."},
        )]  # fmt: skip
    return []


def _letters(sentence: str, ref: date) -> list[Extraction]:
    for pattern, status in LETTER_RULES:
        m = pattern.search(sentence)
        if not m or m["name"].split()[0] in _NOT_NAMES:
            continue
        name = m["name"].strip()
        relationship = (
            "employer"
            if EMPLOYER.search(sentence)
            else "coauthor"
            if COAUTHOR.search(sentence)
            else "independent"
        )
        return [Extraction(
            kind="letter", key=slugify(name, 40), title=f"Letter writer: {name} ({status})", sentence=sentence,
            claim=_claim(f"person:{slugify(name, 40)}", name, "letter_status", status, sentence, ref,
                         kind="letter_writer"),
            proposal={"name": name, "relationship": relationship, "status": status, "last_contact": ref.isoformat()},
        )]  # fmt: skip
    return []


def _claim(subject: str, name: str, predicate: str, value: str, sentence: str, ref: date, *, kind: str,
           stage: str | None = None, event_date: date | None = None) -> ClaimDraft:  # fmt: skip
    return ClaimDraft(
        subject=subject,
        subject_kind=kind,  # type: ignore[arg-type]
        subject_name=name,
        predicate=predicate,
        value=value,
        excerpt=sentence,
        stage=stage,  # type: ignore[arg-type]
        event_date=event_date,
        valid_from=ref,
        confidence="low",  # self-reported, rule-extracted
    )


# ----------------------------------------------------------------------------- candidates


def candidates(conv: Conversation) -> tuple[Evidence, list[Candidate]]:
    """The conversation's transcript snapshot, and one tracker candidate per extracted item."""
    text = transcript(conv)
    snapshot = Evidence(
        connector=f"{conv.provider}_export", source_url=conv.url, payload=text, media_type="text/markdown",
        tier=TIER, filename="conversations.json",
    )  # fmt: skip
    noun = {"claude": "Claude", "chatgpt": "ChatGPT"}[conv.provider]
    out = []
    for ex in extract(conv):
        evidence = snapshot.model_copy(update={"claims": [ex.claim]})
        when = ex.claim.valid_from.isoformat() if ex.claim.valid_from else ""
        cand = Candidate(
            kind=ex.kind,
            fingerprint=f"chat:{ex.kind}:{ex.key}",
            source=f"chat:{conv.provider}",
            evidence_type="self_report",
            proposed_criterion="",
            title=ex.title,
            summary=f'From your {noun} chat "{conv.title}" ({when}): "{ex.sentence}"',
            confidence=0.35,
            stage=ex.stage,  # type: ignore[arg-type]
            source_tier=TIER,
            proposal=ex.proposal,
        )
        out.append(cand.with_evidence(evidence))
    return snapshot, out


def read_export(path: Path) -> bytes:
    if not path.is_file():
        raise ExportError(f"{path} is not a file")
    return path.read_bytes()
