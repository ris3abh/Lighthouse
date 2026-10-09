"""Grounded drafting (SPEC §2a.2, §2a.3): every generated sentence that states a fact cites the approved claims it
rests on, or it's dropped; no eligibility verdicts and no odds; every draft carries the label.

Used by letter drafts (letters.py) and the review packet's outline (ADR 0020)."""

from __future__ import annotations

import re

from areao1.agent.guardrails import guard_answer

LABEL = "Draft for attorney review"
CITE = re.compile(r"\[(clm_[0-9a-f]{6,}(?:\s*,\s*clm_[0-9a-f]{6,})*)\]")
# Any sentence judging eligibility goes (third person too: "she qualifies", "meets the criteria").
VERDICT = re.compile(
    r"\b(qualif(?:y|ies|ied)|eligib\w*|meets? (?:the |all |each |every )?(?:\w+ )?(?:criteri\w*|standards?|requirements?)"
    r"|satisf(?:y|ies|ied) (?:the |all )?(?:\w+ )?criteri\w*|will (?:surely |certainly |definitely )?be approved"
    r"|deserves? (?:the|a|an) (?:visa|green card|approval))\b",
    re.I,
)
# Not facts: greetings, closings, headings and placeholders for a person's own words.
FRAME = re.compile(r"^(dear\b|to whom it may concern|sincerely|respectfully|regards|best\b|#|\[)", re.I)


def is_verdict(sentence: str) -> bool:
    """An eligibility verdict or a probability, in anyone's voice."""
    return bool(VERDICT.search(sentence) or guard_answer(sentence)[1])


def cited_ids(sentence: str) -> list[str]:
    return [i.strip() for m in CITE.finditer(sentence) for i in m.group(1).split(",")]


def keep_grounded(text: str, allowed: set[str]) -> tuple[str, list[str], list[str]]:
    """Drop factual sentences that cite nothing approved, and any verdict. Returns (text, cited ids, dropped)."""
    kept, cited, dropped = [], [], []
    for para in text.split("\n"):
        if not para.strip():
            kept.append("")
            continue
        out = []
        for sentence in re.split(
            r"(?<=[.!?\]])\s+(?=[A-Z]|\[(?!clm_))", para.strip()
        ):  # a citation stays with its sentence
            ids = cited_ids(sentence)
            if is_verdict(sentence):
                dropped.append(sentence)  # never an eligibility verdict or a probability, in anyone's voice
            elif FRAME.match(sentence.strip()) or (sentence.strip().startswith("[") and not ids):
                out.append(sentence)  # greeting, closing, heading, a placeholder for the writer
            elif ids and all(i in allowed for i in ids):
                out.append(sentence)
                cited += ids
            else:
                dropped.append(sentence)
        if out:
            kept.append(" ".join(out))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), list(dict.fromkeys(cited)), dropped
