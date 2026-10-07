"""The onboarding conversation: which question comes next, what each answer changes, and the lookups that
the person can say Yes to. State transitions only; writes go through the service layer."""

from __future__ import annotations

import difflib
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from areao1.core.models import Candidate, ClaimDraft, Evidence, json_excerpt
from areao1.core.text import plural
from areao1.criteria.models import Todo
from areao1.onboarding.linkedin import extract_text, parse_linkedin, redact_contact
from areao1.onboarding.models import Lookup, OnboardingState, ProfileField

LABELS = {"name": "Name", "headline": "Field", "location": "Based in", "employer": "Employer", "role": "Role",
          "education": "Education", "awards": "Awards", "publications": "Papers", "judging": "Judging",
          "certifications": "Certifications", "links": "Links", "skills": "Skills", "summary": "Summary",
          "memberships": "Memberships"}  # fmt: skip
# Asked in this order; skills and summary only fill the panel.
ORDER = ("name", "role", "location", "headline", "education", "awards", "publications", "judging",
         "memberships", "certifications", "links")  # fmt: skip
PROFILES = {
    "o1a": "O-1A (temporary, extraordinary ability)",
    "eb1a": "EB-1A (green card, extraordinary ability)",
}


@dataclass
class Question:
    id: str
    text: str
    keys: list[str]
    kind: str = "confirm"  # confirm: Yes / No, let me fix it / Skip; choice: pick one or Skip
    values: dict[str, Any] = field(default_factory=dict)
    options: list[dict[str, str]] = field(default_factory=list)
    quote: str = ""

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def read_pdf(pdf: bytes) -> tuple[str, int, dict[str, dict[str, Any]]]:
    """(redacted text, redaction count, parsed fields). Local only: pypdf, then redaction, then the parser."""
    text, count = redact_contact(extract_text(pdf))
    return text, count, parse_linkedin(text)


def fields_from(parsed: dict[str, dict[str, Any]]) -> list[ProfileField]:
    return [
        ProfileField(key=k, label=LABELS[k], value=v["value"], quote=v["quote"], original=v["value"])
        for k, v in parsed.items()
        if k in LABELS
    ]


def evidence_for(pdf: bytes, filename: str, text: str, fields: list[ProfileField]) -> Evidence:
    """The redacted PDF text as a self-reported observation, with one quoted claim per field read from it."""
    name = next((str(f.value) for f in fields if f.key == "name"), "")
    claims = []
    for f in fields:
        if f.key in ("summary",) or not f.quote or f.quote not in text:
            continue
        claims.append(ClaimDraft(subject="person:self", subject_kind="person", subject_name=name or "You",
                                 predicate=f"linkedin_{f.key}", value=f.value if isinstance(f.value, str) else "; ".join(f.value),
                                 excerpt=f.quote, confidence="medium"))  # fmt: skip
    digest = hashlib.sha256(pdf).hexdigest()
    return Evidence(connector="linkedin", source_url=f"upload://linkedin/{digest[:12]}/{filename or 'profile.pdf'}",
                    payload=text, media_type="text/plain", tier="self_reported", filename=filename or "profile.pdf",
                    claims=claims)  # fmt: skip


def _member(membership: str) -> str:
    """'Senior Member, IEEE' -> 'a Senior Member of IEEE'; 'Member, X' -> 'a member of X'."""
    role, _, org = membership.partition(", ")
    if not org:
        return f"a member of {membership}"
    return f"{'a member' if role.lower() == 'member' else _a(role)} of {org}"


def _count(fields: list[ProfileField], key: str) -> int:
    f = next((x for x in fields if x.key == key), None)
    return len(_list(f.value)) if f else 0


def opening(fields: list[ProfileField], parser: str) -> str:
    """The first thing Area O1 says after reading the PDF: a short, warm reaction and what it found. Every
    detail comes from the PDF; nothing is confirmed yet, so the questions that follow check each one."""
    got = {f.key: f.value for f in fields}
    found = [(_a(word) if n == 1 else plural(n, word)) for key, word in (("awards", "award"), ("judging", "judging role"), ("publications", "paper"),
             ("memberships", "membership"), ("certifications", "certification")) if (n := _count(fields, key))]  # fmt: skip
    if not fields:
        return ("I couldn't read much from that PDF, so I'll just ask. Nice to meet you! "
                "A few quick questions, and you can skip any of them.")  # fmt: skip
    many = len(fields) >= 7 or len(found) >= 2
    first = str(got.get("name", "")).split()[0] if got.get("name") else ""
    hello = f"Nice to meet you{', ' + first if first else ''}!"
    lead = ("That wasn't a LinkedIn export, but I picked out a few things. " if parser == "model" else
            "I got quite a few things about you. " if many else "I got the basics from your PDF. ")  # fmt: skip
    who = ""
    if got.get("role") and got.get("employer"):
        who = f"You're {_a(str(got['role']))} at {got['employer']}"
    elif got.get("headline"):
        who = f"You work as {got['headline']}"
    if who and got.get("location"):
        who += f", based in {str(got['location']).split(',')[0]}"
    parts = [lead + hello]
    if who:
        parts.append(who + ".")
    if found:
        parts.append(f"I also spotted {_and(found)}, which can matter for your case.")
    parts.append("I'll check each with you, one at a time. It takes a couple of minutes.")
    return " ".join(parts)


def _a(role: str) -> str:
    if role.split(" ")[0].lower() in (
        "head",
        "director",
        "chief",
        "vp",
        "president",
        "founder",
        "co-founder",
    ):
        return role  # "You're Head of Analytics at ..."
    return ("an " if role[:1].lower() in "aeiou" else "a ") + role


def _and(items: list[str]) -> str:
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " and " + items[-1]


def reply_text(q: Question, action: str, value: Any = None) -> str:
    """How the person's answer reads in the transcript."""
    if action == "skip":
        return "Skip"
    if q.kind == "choice":
        return next((o["label"] for o in q.options if o["value"] == value), str(value))
    if q.kind == "month":
        return str(value)
    if action == "fix":
        shown = "; ".join(str(v) for v in value.values()) if isinstance(value, dict) else str(value)
        return f"Not quite: {shown}"
    return "Yes"


def _first(state: OnboardingState) -> str:
    name = state.field("name")
    if name and name.status in ("confirmed", "fixed") and str(name.value).strip():
        return str(name.value).split()[0]
    return ""


def _list(value: str | list[str]) -> list[str]:
    return value if isinstance(value, list) else [value] if value else []


STEPS = ("linkedin", "questions", "ai", "lookups", "chats", "mail", "tour", "done")


def question_ids(state: OnboardingState) -> list[str]:
    """Every question this onboarding has, in the order they're asked."""
    ids = []
    for key in ORDER:
        if key == "role":
            if state.field("employer") or state.field("role"):
                ids.append("role")
        elif state.field(key):
            ids.append(key)
    return [*ids, "target", "when"]


def answered(state: OnboardingState, qid: str) -> bool:
    if qid == "target":
        return state.target_profile is not None
    if qid == "when":
        return state.target_date is not None
    keys = ["employer", "role"] if qid == "role" else [qid]
    present = [f for k in keys if (f := state.field(k))]
    return bool(present) and all(f.status != "pending" for f in present)


def build_question(state: OnboardingState, qid: str, hi: str = "") -> Question:
    """The question for ``qid``, worded from the PDF (or the earlier answer, when the person went back)."""

    def shown(f: ProfileField) -> str | list[str]:
        return f.original if f.status == "skipped" and f.original else f.value

    if qid == "target":
        return Question(id="target", kind="choice", keys=["target"], text=hi + "Which petition are you working toward?",
                        options=[{"value": k, "label": v} for k, v in PROFILES.items()] + [{"value": "unsure", "label": "Not sure yet"}])  # fmt: skip
    if qid == "when":
        return Question(id="when", kind="month", keys=["when"], text="When do you hope to file? A rough month is fine.",
                        values={"when": state.target_date if state.target_date not in (None, "skipped") else ""})  # fmt: skip
    if qid == "role":
        emp, role = state.field("employer"), state.field("role")
        present = [f for f in (emp, role) if f]
        if emp and role:
            text = f"Looks like you're at {shown(emp)} working as {shown(role)}. Is that right?"
        elif emp:
            text = f"Looks like you work at {shown(emp)}. Is that right?"
        else:
            assert role is not None
            text = f"Looks like your role is {shown(role)}. Is that right?"
        return Question(id="role", text=hi + text, keys=[f.key for f in present], values={f.key: shown(f) for f in present},
                        quote=" / ".join(f.quote for f in present))  # fmt: skip
    f = state.field(qid)
    if f is None:
        raise ValueError(f"no question {qid!r}")
    value = shown(f)
    items = _list(value)
    text = {
        "name": f"Let's start with your name as it should appear on your case: {value}. Is that right?",
        "location": f"You're based in {value}?",
        "headline": f"For your field, I'd use your headline: “{value}”. Does that describe your work?",
        "education": f"Your education: {'; '.join(items)}. Is that right?",
        "awards": f"You list {plural(len(items), 'award')}: {'; '.join(items)}. Is that right?",
        "publications": f"You mentioned {plural(len(items), 'paper')}: {'; '.join(items)}. Is that right?",
        "judging": f"You mention judging or reviewing: {'; '.join(items)}. Is that right?",
        "memberships": f"You're {_and([_member(m) for m in items])}. Is that right?",
        "certifications": f"You list {plural(len(items), 'certification')}: {'; '.join(items)}. Is that right?",
        "links": f"Your profile links to {', '.join(items)}. {'Is this yours' if len(items) == 1 else 'Are these yours'}?",
    }[qid]
    return Question(
        id=qid, text=(hi + text) if qid != "name" else text, keys=[qid], values={qid: value}, quote=f.quote
    )


def next_question(state: OnboardingState) -> Question | None:
    """The question to ask now: the one the person went back to, else the next unanswered one; None when done."""
    if state.revisit:
        return build_question(state, state.revisit)
    # Thank them once, on the question right after they confirm their name.
    answered_after_name = any(f.status != "pending" for f in state.fields if f.key != "name")
    hi = f"Thanks, {_first(state)}. " if _first(state) and not answered_after_name else ""
    for qid in question_ids(state):
        if not answered(state, qid):
            return build_question(state, qid, hi)
    return None


def previous_question(state: OnboardingState, current: str | None) -> str | None:
    """The answered question before ``current`` (the last one when ``current`` is None), for Back."""
    ids = question_ids(state)
    end = ids.index(current) if current in ids else len(ids)
    return next((q for q in reversed(ids[:end]) if answered(state, q)), None)


def answer(state: OnboardingState, qid: str, action: str, value: Any = None) -> dict[str, Any]:
    """Apply one answer. Returns what to write elsewhere: {"person": {...}, "profile": "o1a"|None}."""
    writes: dict[str, Any] = {"person": {}, "profile": None}
    if action not in ("yes", "fix", "skip"):
        raise ValueError("answer must be yes, fix or skip")
    q = next_question(state)  # the question being answered (a revisit, or the next unanswered one)
    if state.revisit == qid:
        state.revisit = None
    if qid == "when":
        if action == "skip" or not value:
            state.target_date = "skipped"
            return writes
        if not re.fullmatch(r"20\d\d-(0[1-9]|1[0-2])", str(value)):
            raise ValueError("send a month like 2027-03")
        state.target_date = str(value)
        writes["filing_date"] = f"{value}-01"
        return writes
    if qid == "target":
        if action == "skip" or value in (None, "", "unsure"):
            state.target_profile = "unsure"
        else:
            if value not in PROFILES:
                raise ValueError(f"unknown petition {value!r}")
            state.target_profile = str(value)
            writes["profile"] = value
        return writes
    keys = ["employer", "role"] if qid == "role" else [qid]
    targets = [f for k in keys if (f := state.field(k))]
    if not targets:
        raise ValueError(f"no question {qid!r}")
    if q is None or q.id != qid:
        raise ValueError(f"question {qid!r} isn't the current one")
    for f in targets:
        if action == "skip":
            f.status = "skipped"
            f.value = [] if isinstance(f.value, list) else ""  # skipped stays blank; nothing guessed
            continue
        if action == "fix":
            before = f.value
            new = (value or {}).get(f.key) if isinstance(value, dict) else value
            if new is None:
                raise ValueError(f"send the corrected {f.label.lower()}")
            f.value = (
                [x.strip() for x in new if str(x).strip()]
                if isinstance(f.value, list) and isinstance(new, list)
                else (
                    [x.strip() for x in str(new).split(";") if x.strip()]
                    if isinstance(f.value, list)
                    else str(new).strip()
                )
            )
            f.status = "confirmed" if f.value == before else "fixed"  # unchanged in the form: just confirmed
        else:
            if f.status == "skipped" and f.original:  # going back to a skipped answer and saying Yes
                f.value = f.original
            f.status = "confirmed"
        if f.key == "name":
            writes["person"]["name"] = f.value
        elif f.key == "location":
            writes["person"]["location"] = f.value
        elif f.key == "headline":
            writes["person"]["field"] = f.value
    return writes


def _confirmed(state: OnboardingState, key: str) -> list[str]:
    f = state.field(key)
    return _list(f.value) if f and f.status in ("confirmed", "fixed") else []


# What each confirmed list becomes: (to-do kind, the criteria it may support, most specific first).
TODO_KINDS = {"awards": ("award", ("awards",)), "judging": ("judging", ("judging",)),
              "publications": ("publication", ("scholarly_articles",)),
              "memberships": ("membership", ("membership",))}  # fmt: skip


def todo_title(kind: str, item: str) -> str:
    if kind == "judging":
        role, _, event = item.partition(", ")
        if not event:
            return f"Upload proof of your judging: {item}"
        if role.lower() in ("judge", "jury member"):
            return f"Upload proof of {event} judging"
        if role.lower() == "reviewer":
            return f"Upload proof of your reviewing for {event}"
        return f"Upload proof of your {role.lower()} role at {event}"
    if kind == "publication":
        return f"Upload the published version of “{item}”"
    if kind == "membership":
        return f"Upload proof that you're {_member(item)}"
    return f"Upload proof of the {item}" if not item.lower().startswith("the ") else f"Upload proof of {item}"


def todos_from(state: OnboardingState, criteria: set[str], today: Any) -> list[Todo]:
    """One self-reported to-do per confirmed award, judging role, paper and membership. Never evidence: a to-do
    asks for the proof; only accepted proof counts."""
    out = []
    for key, (kind, crits) in TODO_KINDS.items():
        for item in _confirmed(state, key):
            digest = hashlib.sha256(f"{kind}\n{item.strip().lower()}".encode()).hexdigest()[:12]
            out.append(Todo(id=f"todo_{digest}", title=todo_title(kind, item), kind=kind, item=item,  # type: ignore[arg-type]
                            criterion=next((c for c in crits if c in criteria), None), created=today))  # fmt: skip
    return out


def find_prompt(kind: str, item: str) -> str:
    if kind == "judging":
        role, _, event = item.partition(", ")
        return f"Want me to find the official {event or item} page that lists you as {_a(role.lower()) if event else 'a judge'}?"
    if kind == "membership":
        return f"Want me to look for a public page confirming you're {_member(item)}?"
    return f"Want me to look for the official announcement of the {item}?"


def find_task(kind: str, item: str, person: str) -> str:
    """The agent's instructions for one approved lookup: the official page, quoted, naming the person."""
    who = person or "the person"
    where = {"judging": "the event or organizer's own page (Devpost or MLH for hackathons, the program-committee "
                        "listing for conferences)",
             "membership": "the organization's own member directory or announcement",
             "award": "the awarding organization's own announcement or winners page"}.get(kind, "the official page")  # fmt: skip
    return (f"Onboarding lookup that {who} approved. They told Area O1: \"{item}\". Find {where} that confirms it. "
            "Search the web, read the page with read_page, and propose it with propose_evidence only if the page names "
            f"{who}; quote it word for word and use the stage the page shows (an invitation or nomination is not a "
            "completion). Public professional pages only. If nothing names them, say so in one line and propose nothing.")  # fmt: skip


def offer_lookups(state: OnboardingState, todos: list[Todo] | None = None) -> list[Lookup]:
    """Lookups only for what was confirmed; nothing runs until the person says Yes. Each award, judging role and
    membership gets one (an agent web search for the official page); papers get an arXiv search."""
    out: list[Lookup] = []
    papers = _confirmed(state, "publications")
    if papers:
        n = len(papers)
        out.append(Lookup(id="papers", kind="papers", targets=papers,
                          prompt=f"You mentioned {plural(n, 'paper')}. Want me to find {'it' if n == 1 else 'them'} on arXiv?"))  # fmt: skip
    for raw in _confirmed(state, "links"):
        link = re.sub(r"^(?:https?://)+", "", raw.strip(), flags=re.I)  # "https://x.co" and "x.co" alike
        if not link:
            continue
        host = link.split("/")[0].lower()
        if host.endswith("github.com") and "/" in link:
            out.append(Lookup(id="github", kind="github", targets=[f"https://{link}"],
                              prompt=f"You linked {link}. Want me to import your public repositories?"))  # fmt: skip
        elif host.endswith("orcid.org"):
            out.append(Lookup(id="orcid", kind="orcid", targets=[f"https://{link}"],
                              prompt="You linked your ORCID record. Want me to read your works from it?"))  # fmt: skip
        elif not host.endswith(("linkedin.com", "twitter.com", "x.com", "facebook.com", "instagram.com")):
            out.append(Lookup(id=f"website-{len(out)}", kind="website", targets=[f"https://{link}"],
                              prompt=f"You linked {link}. Want me to read it for press, talks and awards?"))  # fmt: skip
    for todo in todos or []:
        if todo.kind in ("award", "judging", "membership"):
            out.append(Lookup(id=f"find-{todo.id.removeprefix('todo_')}", kind="find", targets=[todo.item],
                              prompt=find_prompt(todo.kind, todo.item), todo_id=todo.id))  # fmt: skip
    return out


# ----------------------------------------------------------------------------- what a paper entry points at

ARXIV_ID = re.compile(r"(?:arxiv\.org/(?:abs|pdf)/|arxiv:\s*)?(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
DOI = re.compile(r"\b(10\.\d{4,9}/[^\s,;]+)", re.I)
VENUE_TAIL = re.compile(r"\s*[,(-]\s*(?:an?\s+)?(?:arxiv(?:\s+preprint)?|preprint|under review|working paper|in submission)"
                        r"\b.*$", re.I)  # fmt: skip


def paper_ref(item: str) -> tuple[str, str]:
    """("arxiv", "2609.34227") | ("doi", "10.1/x") | ("title", "Clean Title"): what to look up for a paper entry.
    Venue tails like ", Arxiv Preprint" are dropped from titles."""
    m = ARXIV_ID.search(item)
    if m and ("arxiv" in item.lower() or re.fullmatch(r"\s*\d{4}\.\d{4,5}(?:v\d+)?\s*", item)):
        return "arxiv", m.group(1)
    if m := DOI.search(item):
        return "doi", m.group(1).rstrip(".")
    return "title", VENUE_TAIL.sub("", item).strip().strip(".")


# ----------------------------------------------------------------------------- namesake checks


def _tokens(name: str) -> list[str]:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z ]", " ", plain.lower()).split()


def is_author(person: str, aliases: list[str], authors: str) -> bool:
    """True when the person's first and last name (or an alias) appear together as one listed author."""
    listed = [_tokens(a) for a in re.split(r",| and ", authors) if a.strip()]
    for candidate in [person, *aliases]:
        want = _tokens(candidate)
        if len(want) < 2:
            continue
        first, last = want[0], want[-1]
        for a in listed:
            if a and a[-1] == last and (a[0] == first or (len(a[0]) == 1 and a[0] == first[0])):
                return True
    return False


def paper_matches(title: str, entry_title: str) -> bool:
    a, b = " ".join(_tokens(title)), " ".join(_tokens(entry_title))
    return a == b or difflib.SequenceMatcher(None, a, b).ratio() >= 0.9


def paper_candidate(entry: dict[str, Any], person: str, aliases: list[str]) -> Candidate:
    """An arXiv hit for a paper the person confirmed, with a namesake check on the author list."""
    from areao1.sources.scholarly import arxiv_id

    aid = arxiv_id(entry["id"]) or entry["id"]
    own = is_author(person, aliases, entry.get("authors", ""))
    summary = (f"{entry['title']}, on arXiv ({entry.get('published', '')[:4]}). Authors: {entry.get('authors', '')}. "
               + ("You're listed as an author. Confirm and add the venue if it was published." if own else
                  "Possible namesake: you aren't listed by this exact name. Accept only if this is your paper."))  # fmt: skip
    evidence = Evidence(connector="arxiv", tier="platform", source_url=f"https://export.arxiv.org/abs/{aid}", payload=entry,
                        claims=[ClaimDraft(subject=f"artifact:arxiv:{aid}", subject_name=entry["title"],
                                           subject_url=f"https://arxiv.org/abs/{aid}", predicate="title",
                                           value=entry["title"], excerpt=json_excerpt("title", entry["title"]))])  # fmt: skip
    return Candidate(fingerprint=f"paper:arxiv:{aid}:scholarly_articles", source="onboarding:arxiv", evidence_type="preprint",
                     proposed_criterion="scholarly_articles", title=f"Paper: {entry['title']}"[:200], summary=summary,
                     confidence=0.5 if own else 0.2, raw_url=f"https://arxiv.org/abs/{aid}", stage="preprint",
                     facts={"authors": entry.get("authors", "")[:300], "namesake_check": "passed" if own else "possible namesake"},
                     ).with_evidence(evidence)  # fmt: skip
