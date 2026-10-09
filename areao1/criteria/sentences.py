"""Reader-facing sentences for the review packet (ADR 0020): one plain sentence per approved claim, from a template
chosen by the exhibit's evidence type and the claim's predicate.

    "Maya received the Northwind Engineering Excellence Award in 2024 (Exhibit C1-01)."

A template is used only when every slot it needs is filled with something that reads as words (an award's name,
not a number). A count gets the metric template when its unit is known ("FastQueue had 4,800 GitHub stars as of
September 2025"); anything else quotes the exhibit ("Exhibit C1-01 states: “…”"), which is always true to the
source. Claim ids never appear in these sentences: the packet turns them into footnotes, and only matrix.csv
carries them in full. ``problems`` names whatever would make a sentence unreadable (an unfilled slot, a raw id, a
snake_case predicate), and the tests run it over every reader-facing line of the packet.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

# (evidence types, predicate, template). The predicate pattern must match the whole predicate, so a template
# fires only for the fact the exhibit is about ("award_received"), never a detail of it ("award_selectivity").
# The first match wins; {the_value} adds "the" to a proper name.
JUDGING = frozenset({"judge_invite", "panel_letter", "reviewer_record", "program_committee"})
NAMED: list[tuple[frozenset[str], str, str]] = [
    (frozenset({"award_certificate", "award_notice", "fellowship", "hackathon_win"}),
     r"(award|prize|honou?r|fellowship)(_(received|won|name|title))?|(received|won)_(award|prize|honou?r|fellowship)",
     "{person} received {the_value} in {year}"),
    (JUDGING, r"(program_)?committee(_member(ship)?)?|pc_member|served_on_committee",
     "{person} served on the program committee of {value} in {year}"),
    (JUDGING, r"review(er)?(_for|_of)?|reviewed(_for)?", "{person} reviewed for {value} in {year}"),
    (JUDGING, r"judg(e|ed|ing)(_event|_for|_at|_of)?|panel(ist)?", "{person} served as a judge for {the_value} in {year}"),
    (frozenset({"press_article", "interview", "podcast_feature", "media_mention"}),
     r"(press|media)(_(mention|feature|coverage|article))?|featured(_in)?|feature|article(_title)?|profile"
     r"|interview|headline|podcast(_feature)?", "{org_featured} {person} in {quoted} in {year}"),
    (frozenset({"membership_certificate", "membership_letter", "membership_bylaws"}),
     r"member(ship)?(_(of|in|granted|admitted))?|admitted(_to)?|elected(_to)?",
     "{person} was admitted to {the_value} in {year}"),
    (frozenset({"paper", "preprint", "journal_article", "conference_paper"}),
     r"(paper|article)(_(published|title))?|published(_paper)?|publication(_title)?", "{person} published {quoted} in {year}"),
    (frozenset({"patent"}), r"patent(_(granted|number|title))?|inventor(_on)?", "{person} is a named inventor on {value}"),
    (frozenset({"open_source_project", "ml_model", "dataset", "adoption_evidence", "expert_letter"}),
     r"adopted_by|used_by|user_org|customer|deployed_by", "{value} uses {work}, as of {month}"),
    (frozenset({"open_source_project", "ml_model", "dataset"}), r"created|authored|maintainer|built",
     "{person} created {value} in {year}"),
    (frozenset({"role_letter", "org_chart", "offer_letter", "org_reputation"}), r"role(_title)?|title|position|job_title",
     "{person} held the role of {value}{at_org} in {year}"),
    (frozenset({"pay_stub", "offer_letter", "w2", "salary_survey"}), r"(base_)?salary|compensation|pay|wage",
     "{person_s} compensation was {value} in {year}"),
]  # fmt: skip

# A count's unit, by a word in the predicate.
METRICS = {"stars": "GitHub stars", "forks": "forks", "downloads": "downloads", "citation": "citations",
           "citations": "citations", "followers": "followers", "readers": "readers", "subscribers": "subscribers",
           "users": "users", "installs": "installs", "views": "views", "likes": "likes"}  # fmt: skip

ID = re.compile(r"\b(?:clm|ex|ent|obs|edge|ltr|evd)_[0-9a-z]{4,}\b")
SNAKE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")
SLOT = re.compile(r"\{[^}]*\}|\bNone\b|\bnull\b|\bnan\b|\(\s*\)|\[\s*\]|“\s*”|\s[,;:]|\s\.(?!\.)|\s{2,}")
MAX_QUOTE = 240


@dataclass
class Fact:
    """What a sentence is built from."""

    person: str  # the person's name as the packet calls them ("Maya")
    predicate: str
    value: Any
    evidence_type: str
    exhibit: str  # its number, "C1-01"
    excerpt: str
    on: date | None  # the claim's date, else the exhibit's
    org: str = ""  # who issued the exhibit
    work: str = ""  # the subject's name ("FastQueue")


def first_name(name: str) -> str:
    return name.split()[0] if name.strip() else "The person"


def plain(v: Any) -> str:
    if isinstance(v, str):
        return v.strip().rstrip(".").strip()
    if isinstance(v, bool) or v is None:
        return ""
    if isinstance(v, int | float):
        return f"{v:,}"
    if isinstance(v, dict):
        return "; ".join(f"{str(k).replace('_', ' ')} {plain(x)}".strip() for k, x in v.items())
    if isinstance(v, list):
        return ", ".join(plain(x) for x in v)
    return json.dumps(v, ensure_ascii=False)


def _is_words(s: str) -> bool:
    """A name or title, not a number or a code: has a letter, isn't mostly digits, isn't snake_case."""
    letters = sum(ch.isalpha() for ch in s)
    return letters >= 3 and letters >= sum(ch.isdigit() for ch in s) and not SNAKE.fullmatch(s)


def _is_count(v: Any) -> bool:
    if isinstance(v, int | float) and not isinstance(v, bool):
        return True
    return isinstance(v, str) and bool(re.fullmatch(r"\$?\d[\d,.]*\s*[kKmM]?(?:\+)?", v.strip()))


def _the(s: str) -> str:
    if re.match(r"(?i)(the|a|an)\s", s):
        return s
    return f"the {s}" if s[:1].isupper() else s


def _quoted(s: str) -> str:
    return "“" + s.strip("\"'“”‘’ ") + "”"


def _month(d: date | None) -> str:
    return f"{d:%B} {d.year}" if d else ""


def _clip(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= MAX_QUOTE:
        return text
    cut = text[:MAX_QUOTE].rsplit(" ", 1)[0].rstrip(",;:")
    return cut + "…"


def _metric(f: Fact) -> str | None:
    words = f.predicate.lower().split("_")
    unit = next((METRICS[w] for w in reversed(words) if w in METRICS), None)
    if unit is None or not _is_count(f.value) or not f.on:
        return None
    work = f.work if f.work and _is_words(f.work) else f"{f.person}'s work"
    per = " a month" if "monthly" in words else " a week" if "weekly" in words else ""
    return f"{work} had {plain(f.value)} {unit}{per} as of {_month(f.on)}"


def _named(f: Fact) -> str | None:
    value = plain(f.value)
    if re.search(r"salary|compensation|pay|wage", f.predicate):
        money = r"[$€£]?\s?\d[\d,.]*\s?[kKmM]?(\s?(USD|EUR|GBP|a year|per year|annually|a month|per month))?"
        if not isinstance(f.value, str) or not re.fullmatch(money, value):
            return None  # an amount with its currency and period, as the document says it
    elif not _is_words(value) or value[:1].isdigit():
        return None  # "3 of 412 nominees" is a detail, not a name: it's quoted instead
    for types, pattern, template in NAMED:
        if f.evidence_type not in types or not re.fullmatch(pattern, f.predicate, re.I):
            continue
        if f.on and str(f.on.year) in value:
            template = template.replace(
                " in {year}", ""
            )  # "the Example Systems Conf 2025", not "… 2025 in 2025"
        slots = {"person": f.person, "person_s": f"{f.person}'s", "value": value, "the_value": _the(value),
                 "quoted": _quoted(value), "year": str(f.on.year) if f.on else "", "month": _month(f.on),
                 "org_featured": f"{f.org} featured" if f.org else "Coverage featured",
                 "at_org": f" at {f.org}" if f.org else "",
                 "work": f.work if f.work and _is_words(f.work) else f"{f.person}'s work"}  # fmt: skip
        needed = re.findall(r"\{(\w+)\}", template)
        if any(not slots[s] for s in needed):
            continue  # a slot this template needs is empty: try the next, then fall back
        return template.format(**slots)
    return None


def factplain(f: Fact) -> str | None:
    """The sentence's fact, without the exhibit reference; None when only a quote will do."""
    return _named(f) or _metric(f)


def sentence(f: Fact) -> str:
    """One reader-facing sentence, ending with its exhibit. No claim id: the caller adds the footnote."""
    fact = factplain(f)
    if fact:
        return f"{fact} (Exhibit {f.exhibit})."  # never re-capitalized: "sparse-router had …" keeps its name
    quote = _clip(f.excerpt).strip('"“” ')
    if not quote:
        return f"Exhibit {f.exhibit} records this claim."
    end = "" if quote.endswith((".", "!", "?", "…")) else "."
    return f"Exhibit {f.exhibit} states: “{quote}{end}”"


def label(f: Fact) -> str:
    """A short name for the claim in a table: the fact when a template fits, else 'Predicate: value'."""
    fact = factplain(f)
    if fact:
        return fact
    words = f.predicate.replace("_", " ").strip()
    value = plain(f.value)
    return f"{words[:1].upper()}{words[1:]}: {value}" if value else words[:1].upper() + words[1:]


def problems(text: str, predicates: tuple[str, ...] = ()) -> list[str]:
    """What would make a reader-facing line unreadable: an unfilled slot, a raw id, a snake_case word, or a
    predicate spelled out as if it were English ("award received 17"; a table's "Award selectivity: 3 of 412
    nominees" is a label, and fine)."""
    found = [f"raw id {m.group(0)}" for m in ID.finditer(text)]
    found += [f"snake_case {m.group(0)}" for m in SNAKE.finditer(text) if "@" not in text[max(0, m.start() - 40) : m.start()]
              and "://" not in text[max(0, m.start() - 80) : m.start()]]  # fmt: skip
    found += [f"unfilled slot {m.group(0)!r}" for m in SLOT.finditer(text)]
    for p in predicates:
        phrase = p.replace("_", " ")
        if " " in phrase and re.search(rf"\b{re.escape(phrase)}\b\s*=?\s*\d", text, re.I):
            found.append(f"template predicate {phrase!r}")
    return found
