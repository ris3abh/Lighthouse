"""Local relevance filter for chat history (C14b). No model call: every conversation and project is scored for
case signals, and each score comes with the reasons a person can read in the picker.

Signals: immigration terms, criteria words, names and projects from the person's own profile (onboarding),
people who come up across several chats, and dates with deadline words. Claude Projects (instructions and
knowledge files) are weighted highest: people keep their case material there.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from lighthouse_gc.core import clock
from lighthouse_gc.sources.chat_export import DEADLINE_WORDS, Conversation, find_date
from lighthouse_gc.sources.chat_intake import Intake, Project

VISA = re.compile(
    r"\b(O-?1A?|O-?1|EB-?1A?|EB-?1|EB-?2|NIW|national interest waiver|H-?1B|green card|USCIS|I-129|I-140|I-485|RFE|"
    r"extraordinary ability|immigration|visa|petition|premium processing|priority date|attorney|lawyer)\b",
    re.I,
)
CRITERIA_WORDS: dict[str, tuple[str, ...]] = {
    "awards": ("award", "prize", "honor", "honour", "winner", "won", "fellowship"),
    "membership": ("member of", "membership", "fellow of", "society", "association"),
    "press": ("press", "featured in", "interviewed", "article about", "coverage", "podcast"),
    "judging": ("judge", "judging", "judged", "reviewer", "program committee", "peer review", "review for"),
    "original_contributions": (
        "open source",
        "open-source",
        "adopted by",
        "contribution",
        "patent",
        "used by",
    ),
    "scholarly_articles": (
        "paper",
        "publication",
        "published",
        "citations",
        "arxiv",
        "journal",
        "conference",
    ),
    "critical_role": ("led the", "lead the", "head of", "founding", "critical role", "tech lead"),
    "high_salary": ("salary", "compensation", "offer letter", "total comp", "equity"),
}
# The case itself: letters, evidence, the petition's paperwork.
CASE_WORDS = re.compile(r"\b(recommendation letter|reference letter|support letter|expert letter|letter of support|"
                        r"letter writer|evidence|exhibit|criteria|criterion)s?\b", re.I)  # fmt: skip
ACRONYMS = {"o1a": "O-1A", "o1": "O-1", "eb1a": "EB-1A", "eb1": "EB-1", "eb2": "EB-2", "h1b": "H-1B", "niw": "NIW",
            "uscis": "USCIS", "rfe": "RFE", "i129": "I-129", "i140": "I-140", "i485": "I-485"}  # fmt: skip
_PERSON = re.compile(r"\b(?:(?:Dr|Prof|Professor)\.?\s+)?([A-Z][a-z]{2,}\s+[A-Z][a-z]{2,})\b")
_COMMON = {"Thank You", "Best Regards", "Good Morning", "New York", "San Francisco", "United States", "Machine Learning",
           "Open Source", "Next Week", "Last Week", "Pull Request", "Hacker News", "Google Scholar", "Program Committee"}  # fmt: skip
WEIGHTS = {"visa": 3.0, "case": 3.0, "criteria": 1.5, "profile": 2.0, "people": 1.0, "deadlines": 1.0}
CAPS = {"visa": 9.0, "case": 6.0, "criteria": 6.0, "profile": 6.0, "people": 3.0, "deadlines": 2.0}
DEFAULT_TICK = 3.5


def _term(match: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", match.lower())
    return ACRONYMS.get(key, match.lower())


@dataclass
class Match:
    id: str
    kind: str  # conversation | project
    provider: str
    title: str
    date: str | None
    messages: int
    score: float
    reasons: list[str] = field(default_factory=list)
    ticked: bool = False

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def profile_terms(person_names: list[str], fields: dict[str, Any]) -> list[str]:
    """Distinctive names from the person's profile: employer, and the proper nouns in their awards, judging,
    papers, memberships and links (HackSeattle, Northwind Cloud, quillstream)."""
    out: list[str] = []
    for key in ("employer", "awards", "judging", "publications", "memberships", "certifications", "headline"):
        values = fields.get(key) or []
        for value in values if isinstance(values, list) else [values]:
            for chunk in re.findall(r"\b[A-Z][\w&.-]{3,}(?:\s+[A-Z][\w&.-]{2,})*", str(value)):
                if chunk not in (
                    "Judge",
                    "Member",
                    "Senior",
                    "Award",
                    "Best",
                    "Paper",
                    "Workshop",
                    "Program",
                    "Reviewer",
                ):
                    out.append(chunk)
    for link in fields.get("links") or []:
        tail = str(link).rstrip("/").split("/")[-1]
        if len(tail) >= 4 and "." not in tail:
            out.append(tail)  # a GitHub handle or project name
    own = {n.lower() for n in person_names if n}
    return sorted({t for t in out if t.lower() not in own}, key=str.lower)


def _text(conv: Conversation) -> str:
    return conv.title + "\n" + "\n".join(m.text for m in conv.messages)


def _people(text: str, own: set[str]) -> set[str]:
    return {m for m in _PERSON.findall(text) if m not in _COMMON and m.lower() not in own}


def score(intake: Intake, person_names: list[str], fields: dict[str, Any]) -> list[Match]:
    """A Match per conversation and project, highest first, with sensible defaults ticked."""
    terms = profile_terms(person_names, fields)
    own = {n.lower() for n in person_names if n}
    texts: dict[str, str] = {f"c:{c.provider}:{c.id}": _text(c) for c in intake.conversations}
    texts |= {f"p:{p.provider}:{p.id}": p.text() for p in intake.projects}
    seen_in = Counter(name for t in texts.values() for name in _people(t, own))
    recurring = {n for n, k in seen_in.items() if k >= 2}

    def rate(key: str, text: str, project: bool) -> tuple[float, list[str]]:
        parts: dict[str, float] = {}
        reasons = []
        visa = sorted({_term(m) for m in VISA.findall(text)}, key=lambda s: (not s[:1].isupper(), s))
        if visa:
            parts["visa"] = WEIGHTS["visa"] * len(visa)
            reasons.append(f"mentions {', '.join(visa[:4])}")
        case = sorted({m.lower() for m in CASE_WORDS.findall(text)})
        if case:
            parts["case"] = WEIGHTS["case"] * len(case)
            reasons.append(f"about your case: {', '.join(case[:3])}")
        low = text.lower()
        crit = [
            c
            for c, words in CRITERIA_WORDS.items()
            if any(re.search(rf"\b{re.escape(w)}\b", low) for w in words)
        ]
        if crit:
            parts["criteria"] = WEIGHTS["criteria"] * len(crit)
            reasons.append(f"criteria words: {', '.join(c.replace('_', ' ') for c in crit[:4])}")
        mine = [t for t in terms if re.search(rf"\b{re.escape(t)}\b", text, re.I)]
        if mine:
            parts["profile"] = WEIGHTS["profile"] * len(mine)
            reasons.append(f"names from your profile: {', '.join(mine[:3])}")
        people = sorted(_people(text, own) & recurring)
        if people:
            parts["people"] = WEIGHTS["people"] * len(people)
            reasons.append(f"people you mention in other chats: {', '.join(people[:3])}")
        dated = sum(
            1 for line in text.splitlines() if DEADLINE_WORDS.search(line) and find_date(line, _today())
        )
        if dated:
            parts["deadlines"] = WEIGHTS["deadlines"] * dated
            reasons.append(f"{dated} dated {'deadline' if dated == 1 else 'deadlines'}")
        total = sum(min(v, CAPS[k]) for k, v in parts.items())
        if project:
            total = total * 1.5 + 5  # instructions and knowledge files: where people keep their case
            reasons.insert(0, "a Claude Project (instructions and knowledge files)")
        return round(total, 1), reasons

    out = []
    for c in intake.conversations:
        s, why = rate(f"c:{c.provider}:{c.id}", texts[f"c:{c.provider}:{c.id}"], False)
        out.append(Match(f"c:{c.provider}:{c.id}", "conversation", c.provider, c.title,
                         clock.local_date(c.created).isoformat() if c.created else None, len(c.messages), s, why, s >= DEFAULT_TICK))  # fmt: skip
    for p in intake.projects:
        s, why = rate(f"p:{p.provider}:{p.id}", texts[f"p:{p.provider}:{p.id}"], True)
        has_signal = len(why) > 1
        out.append(Match(f"p:{p.provider}:{p.id}", "project", p.provider, p.name,
                         clock.local_date(p.created).isoformat() if p.created else None, len(p.docs), s, why, has_signal))  # fmt: skip
    return sorted(out, key=lambda m: (-m.score, m.title.lower()))


def _today():
    return clock.today()


def pick(intake: Intake, ids: set[str]) -> tuple[list[Conversation], list[Project]]:
    convs = [c for c in intake.conversations if f"c:{c.provider}:{c.id}" in ids]
    projects = [p for p in intake.projects if f"p:{p.provider}:{p.id}" in ids]
    return convs, projects
