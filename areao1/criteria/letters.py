"""Recommendation letter drafts (I1): from approved claims only, every factual sentence linked to the claims it rests
on, for the writer to review, rewrite and sign. Area O1 never signs or sends anything as the writer: the draft goes
to them as an email from the person, through the normal Approve & send.

With an AI connected the hard tier writes the draft from the claims (and nothing else); any sentence that cites no
approved claim (other than the greeting, the closing and placeholders for the writer's own words) is dropped. Without
one, a plain template lists the facts. Eligibility verdicts are removed either way."""

from __future__ import annotations

import re
from typing import Any

from areao1.agent.guardrails import guard_answer
from areao1.core import clock
from areao1.criteria import constellation
from areao1.criteria.case import Case

CITE = re.compile(r"\[(clm_[0-9a-f]{6,}(?:\s*,\s*clm_[0-9a-f]{6,})*)\]")
# In a letter, any sentence judging eligibility goes (third person too: "she qualifies", "meets the criteria").
VERDICT = re.compile(
    r"\b(qualif(?:y|ies|ied)|eligib\w*|meets? (?:the |all |each |every )?(?:\w+ )?(?:criteri\w*|standards?|requirements?)"
    r"|satisf(?:y|ies|ied) (?:the |all )?(?:\w+ )?criteri\w*|will (?:surely |certainly |definitely )?be approved"
    r"|deserves? (?:the|a|an) (?:visa|green card|approval))\b",
    re.I,
)
FRAME = re.compile(r"^(dear\b|to whom it may concern|sincerely|respectfully|regards|best\b|\[)", re.I)
SYSTEM = """You draft a recommendation letter that a named writer will review, rewrite and sign. Write in the
writer's voice, in plain professional English, under 400 words.

Use ONLY the facts in the numbered claims you're given. Every sentence that states a fact must end with the ids of
the claims it rests on, in square brackets, e.g. [clm_1a2b3c4d5e6f]. Don't add facts, numbers, praise or comparisons
the claims don't support. Where only the writer can speak (how they know the person, their own judgment), write a
placeholder in square brackets for them to fill in, e.g. [WRITER: how you worked together].

Never state that the person qualifies, meets a criterion, or will be approved; never mention USCIS outcomes. Begin
with "Dear Officer," or "To whom it may concern," and end with "Sincerely," then "[WRITER: signature, name, title]".
The writer signs, not you."""
HEADER = ("<!-- Draft for {writer} to review, rewrite and sign. Area O1 never signs or sends it as them. Each "
          "bracketed id is the claim a sentence rests on; the sources are listed at the end. -->")  # fmt: skip


def approved_claims(ws: Case, criteria: list[str]) -> list[dict[str, Any]]:
    """Approved, current claims for these criteria (all criteria when empty), oldest first."""
    stars = constellation.stars(ws)["stars"]
    return [
        s
        for s in stars
        if s["status"] == "approved" and not s["conflict"] and (not criteria or s["criterion"] in criteria)
    ]


def _claim_line(s: dict[str, Any]) -> str:
    return f"{s['id']}: {s['entity_name']}, {s['predicate'].replace('_', ' ')}: {s['value']} ({s['date']})"


def template(writer: str, person: str, claims: list[dict[str, Any]]) -> str:
    lines = ["Dear Officer,", "",
             f"I am writing in support of {person}. [WRITER: how you know {person} and for how long.]", ""]  # fmt: skip
    for s in claims:
        lines.append(f"{person}'s record shows: {s['entity_name']}, {s['predicate'].replace('_', ' ')} "
                     f"{s['value']} ({s['date']}). [{s['id']}]")  # fmt: skip
    lines += ["", "[WRITER: your own assessment of this work, in your words.]", "", "Sincerely,",
              "[WRITER: signature, name, title]"]  # fmt: skip
    return "\n".join(lines)


def keep_grounded(text: str, allowed: set[str]) -> tuple[str, list[str], list[str]]:
    """Drop factual sentences that cite nothing approved. Returns (text, cited claim ids, dropped sentences)."""
    kept, cited, dropped = [], [], []
    for para in text.split("\n"):
        if not para.strip():
            kept.append("")
            continue
        out = []
        for sentence in re.split(
            r"(?<=[.!?\]])\s+(?=[A-Z]|\[(?!clm_))", para.strip()
        ):  # a citation stays with its sentence
            ids = [i.strip() for m in CITE.finditer(sentence) for i in m.group(1).split(",")]
            if VERDICT.search(sentence) or guard_answer(sentence)[1]:
                dropped.append(sentence)  # never an eligibility verdict, in anyone's voice
            elif FRAME.match(sentence.strip()) or (sentence.strip().startswith("[") and not ids):
                out.append(sentence)  # greeting, closing, a placeholder for the writer
            elif ids and all(i in allowed for i in ids):
                out.append(sentence)
                cited += ids
            else:
                dropped.append(sentence)
        if out:
            kept.append(" ".join(out))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip(), list(dict.fromkeys(cited)), dropped


async def draft(ws: Case, letter_id: str, judge: Any = None, model: str = "") -> dict[str, Any]:
    """Write drafts/letters/<writer>.md and record what it cites. Returns {path, cited, dropped, by}."""
    from areao1.core.models import slugify
    from areao1.service import Service

    letter = next((lt for lt in ws.letters().letters if lt.id == letter_id), None)
    if letter is None:
        raise KeyError(letter_id)
    person = ws.person().name or "the beneficiary"
    claims = approved_claims(ws, letter.criteria)
    if not claims:
        raise ValueError(
            "No approved claims for this writer's criteria yet: approve some in the Inbox first."
        )
    allowed = {s["id"] for s in claims}
    by = "template"
    text = template(letter.name, person, claims)
    if judge is not None:
        prompt = (f"Writer: {letter.name} ({letter.relationship}; {letter.credentials or 'credentials not given'}).\n"
                  f"Person: {person}.\nCriteria: {', '.join(letter.criteria) or 'any'}.\n\nClaims:\n"
                  + "\n".join(_claim_line(s) for s in claims[:120]))  # fmt: skip
        reply = await judge(SYSTEM, prompt, model)
        if reply.text.strip():
            text, by = reply.text.strip(), model or "model"
    text, cited, dropped = keep_grounded(text, allowed)
    if not cited:
        raise ValueError("The draft didn't rest on any approved claim, so it wasn't kept. Try again.")
    sources = {s["id"]: s for s in claims}
    lines = [HEADER.format(writer=letter.name), "", f"# Letter from {letter.name}: draft of {clock.today().isoformat()}", "",
             text, "", "---", "", "## Sources (claims this draft rests on)", ""]  # fmt: skip
    for cid in cited:
        s = sources[cid]
        lines.append(f"- [{cid}] {s['entity_name']}: {s['predicate'].replace('_', ' ')} {s['value']} ({s['date']})"
                     + (f" · {s['source_url']}" if s.get("source_url") else ""))  # fmt: skip
    rel = f"drafts/letters/{slugify(letter.name, 40)}.md"
    Service(ws).save_letter_draft(
        letter.id, rel, "\n".join(lines) + "\n", cited
    )  # the file, its citations, draft_path
    return {"path": rel, "cited": cited, "dropped": dropped, "by": by, "text": text}


def email_body(ws: Case, letter_name: str, text: str) -> str:
    """The note to the writer: from the person, with the draft for them to rewrite and sign (citations removed)."""
    person = ws.person().name or "me"
    clean = re.sub(r"\s*" + CITE.pattern, "", text)
    parts = [
        w
        for w in letter_name.replace(",", " ").split()
        if w.lower().rstrip(".") not in ("dr", "prof", "mr", "ms", "mrs")
    ]
    first = parts[0] if parts else letter_name
    return (f"Hi {first},\n\nThank you again for agreeing to write a letter. To save you time, here is a draft built "
            "only from documented facts. Please rewrite anything in your own words, fill in the bracketed parts, and "
            f"only sign it if it reads true to you.\n\n---\n\n{clean}\n\n---\n\nThank you,\n{person}")  # fmt: skip
