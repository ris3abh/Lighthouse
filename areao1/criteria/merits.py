"""The final-merits view (ADR 0019): the counted evidence as a whole, by rules anyone can read.

- A sustained-acclaim timeline: counted exhibits by year and criterion, the span of years and the gaps.
- Themes (independent recognition, recognition outside the employer, multiple years, peer-relative context,
  external adoption), each ``strong``, ``building`` or ``missing`` by a rule from the profile, with the exhibits
  behind it and a sentence saying why ("2 of 6 letter writers are independent").
- Field benchmarks from OpenAlex, fetched only when the person asks, stored as claims quoting the response.
- The standard (Kazarian, the Policy Manual), each sentence checked against the passage it cites in the vault.

No score, no verdict (SPEC §2a): a status says what the evidence in the workspace covers against a visible rule.
"""

from __future__ import annotations

import json
import re
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field

from areao1.core.models import NON_EVIDENTIARY_TIERS, ClaimDraft, Evidence, Exhibit
from areao1.criteria.models import MeritsTheme, Profile

ThemeStatus = Literal["strong", "building", "missing"]
EMPLOYER_PREDICATES = ("employer", "linkedin_employer", "current_employer")
BENCHMARK = "field_citation_percentile"


class Theme(BaseModel):
    id: str
    label: str
    description: str = ""
    status: ThemeStatus
    why: str
    rule: str = Field(description="The rule in words, so the status can be checked.")
    exhibit_ids: list[str] = Field(default_factory=list)
    letter_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)


class Year(BaseModel):
    year: int
    count: int
    by_criterion: dict[str, list[str]] = Field(default_factory=dict)


class Benchmark(BaseModel):
    claim_id: str
    work: str
    year: int | None = None
    percentile: float
    review: str = Field(description="The claim's review status in memory (proposed, approved, rejected…).")
    source_url: str


class StandardSentence(BaseModel):
    text: str = ""
    section: str = ""
    source_id: str
    title: str = ""
    link: str = ""
    quote: str
    status: Literal["verified", "stale", "unverified"]
    why: str = ""


class MeritsReport(BaseModel):
    profile: str
    label: str
    framing: str
    employer: list[str] = Field(default_factory=list)
    timeline: list[Year] = Field(default_factory=list)
    first_year: int | None = None
    last_year: int | None = None
    gap_years: list[int] = Field(default_factory=list)
    themes: list[Theme] = Field(default_factory=list)
    benchmarks: list[Benchmark] = Field(default_factory=list)
    openalex_authors: int = Field(0, description="OpenAlex authors in Sources (benchmarks need one).")
    standard: list[StandardSentence] = Field(default_factory=list)
    no_organization: list[str] = Field(
        default_factory=list, description="Counted exhibits that name no organization."
    )
    exhibits: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Counted exhibits by id, to show."
    )
    criteria: dict[str, str] = Field(default_factory=dict, description="Criterion labels by id.")
    letters: dict[str, str] = Field(default_factory=dict, description="Letter writers by id.")


# ------------------------------------------------------------------------------------------------- organizations


def _compact(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


def organization(e: Exhibit) -> str:
    """Who issued or published an exhibit: the field the person set, else the host of its source address."""
    if e.organization.strip():
        return e.organization.strip()
    if e.source_url and e.source_url.startswith(("http://", "https://")):
        host = (urlparse(e.source_url).hostname or "").lower()
        return host.removeprefix("www.")
    return ""


def is_employer(org: str, employers: list[str]) -> bool:
    c = _compact(org.split(".")[0] if "." in org and " " not in org else org)
    full = _compact(org)
    for emp in employers:
        e = _compact(emp)
        if e and (e in full or (c and (c in e or e in c))):
            return True
    return False


def employers(ws: Any) -> list[str]:
    """The person's employer: the petitioner when it is the employer, and current, unrejected employer claims."""
    out: list[str] = []
    person = ws.person()
    if person.petitioner.kind == "employer" and person.petitioner.name.strip():
        out.append(person.petitioner.name.strip())
    statuses = ws.memory.statuses()
    for (_, predicate), claim in ws.memory._current_claims().items():
        if predicate not in EMPLOYER_PREDICATES or statuses.get(claim.id) == "rejected":
            continue
        name = claim.value.strip() if isinstance(claim.value, str) else ""
        if name and name not in out:
            out.append(name)
    return out


# ----------------------------------------------------------------------------------------------------- the rules


def _status(n: float, theme: MeritsTheme) -> ThemeStatus:
    return "strong" if n >= theme.strong else "building" if n >= theme.building else "missing"


def _names(orgs: list[str], k: int = 3) -> str:
    uniq = list(dict.fromkeys(orgs))
    head = ", ".join(uniq[:k])
    return head + (f" and {len(uniq) - k} more" if len(uniq) > k else "")


def _theme(theme: MeritsTheme, counted: list[Exhibit], ws: Any, emps: list[str],
           benchmarks: list[Benchmark]) -> Theme:  # fmt: skip
    base = {"id": theme.id, "label": theme.label, "description": theme.description}
    emp = " or ".join(emps) if emps else "your employer"
    if theme.rule == "independent_letters":
        writers = [lt for lt in ws.letters().letters if lt.status != "declined"]
        ind = [lt for lt in writers if lt.relationship == "independent"]
        outside = [e for e in counted if e.criterion in theme.criteria and organization(e)
                   and emps and not is_employer(organization(e), emps)]  # fmt: skip
        share = len(ind) / len(writers) if writers else 0.0
        need = theme.strong_share or 0.0
        if len(ind) >= theme.strong and share >= need:
            status: ThemeStatus = "strong"
        elif len(ind) >= theme.building or outside:
            status = "building"
        else:
            status = "missing"
        why = f"{len(ind)} of {len(writers)} letter writers {'is' if len(ind) == 1 else 'are'} independent"
        why += (
            f"; {len(outside)} award or press exhibit{'' if len(outside) == 1 else 's'} from outside {emp}."
            if outside
            else "."
        )
        rule = (f"Strong: at least {theme.strong} independent letter writers, and at least {need:.0%} of all writers. "
                f"Building: {theme.building} independent writer, or an award or press exhibit from outside your "
                "employer.")  # fmt: skip
        return Theme(**base, status=status, why=why, rule=rule, letter_ids=[lt.id for lt in ind],
                     exhibit_ids=[e.id for e in outside])  # fmt: skip
    if theme.rule == "outside_employer":
        rule = (f"Strong: at least {theme.strong} counted exhibits from organizations other than your employer. "
                f"Building: at least {theme.building}.")  # fmt: skip
        if not emps:
            return Theme(**base, status="missing", rule=rule,
                         why="Your employer isn't recorded (Settings: petitioner, or an employer claim in Memory), so "
                             "this can't be checked.")  # fmt: skip
        outside = [e for e in counted if organization(e) and not is_employer(organization(e), emps)]
        why = f"{len(outside)} counted exhibit{'' if len(outside) == 1 else 's'} from organizations other than {emp}"
        why += f" ({_names([organization(e) for e in outside])})." if outside else "."
        unknown = [e for e in counted if not organization(e)]
        if unknown:
            why += f" {len(unknown)} name no organization; set one below."
        return Theme(**base, status=_status(len(outside), theme), why=why, rule=rule,
                     exhibit_ids=[e.id for e in outside])  # fmt: skip
    if theme.rule == "years":
        years = sorted({e.date.year for e in counted})
        rule = f"Strong: counted exhibits in at least {theme.strong} different years. Building: {theme.building}."
        why = (f"Counted exhibits in {len(years)} year{'' if len(years) == 1 else 's'}"
               + (f" ({', '.join(map(str, years))})." if years else "."))  # fmt: skip
        return Theme(**base, status=_status(len(years), theme), why=why, rule=rule,
                     exhibit_ids=[e.id for e in counted])  # fmt: skip
    if theme.rule == "peer_context":
        usable = [b for b in benchmarks if b.review != "rejected"]
        signalled = [e for e in counted if set(e.signals) & set(theme.signals)]
        status = "strong" if usable or len(signalled) >= theme.strong else _status(len(signalled), theme)
        parts = [f"{len(usable)} field benchmark{'' if len(usable) == 1 else 's'} from OpenAlex",
                 f"{len(signalled)} counted exhibit{'' if len(signalled) == 1 else 's'} documenting selectivity"]  # fmt: skip
        rule = (f"Strong: a field benchmark, or at least {theme.strong} exhibits with a selectivity signal. "
                f"Building: {theme.building} such exhibit.")  # fmt: skip
        return Theme(**base, status=status, why="; ".join(parts) + ".", rule=rule,
                     exhibit_ids=[e.id for e in signalled], claim_ids=[b.claim_id for b in usable])  # fmt: skip
    # adoption
    used = [
        e for e in counted if e.evidence_type in theme.evidence_types or set(e.signals) & set(theme.signals)
    ]
    adopters = [
        organization(e) for e in used if organization(e) and not (emps and is_employer(organization(e), emps))
    ]
    n = len(set(adopters))
    rule = (
        f"Strong: adoption by at least {theme.strong} independent organizations. Building: {theme.building}."
    )
    why = f"{len(used)} counted exhibit{'' if len(used) == 1 else 's'} of adoption, from {n} independent organization{'' if n == 1 else 's'}"
    why += f" ({_names(adopters)})." if adopters else "."
    unnamed = [e for e in used if not organization(e)]
    if unnamed:
        why += f" {len(unnamed)} name no organization; set one below."
    return Theme(**base, status=_status(n, theme), why=why, rule=rule, exhibit_ids=[e.id for e in used])


# ------------------------------------------------------------------------------------------------------ the view


def counted_exhibits(ws: Any, board: Any) -> list[Exhibit]:
    ids = {i for c in board.criteria for i in c.exhibit_ids}
    return [e for e in ws.exhibits().exhibits if e.id in ids and e.source_tier not in NON_EVIDENTIARY_TIERS]


def benchmarks(ws: Any) -> list[Benchmark]:
    statuses = ws.memory.statuses()
    obs = {o.id: o for o in ws.memory.observations()}
    names = {e.id: e.name for e in ws.memory.entities()}
    out = []
    for (subject, predicate), c in ws.memory._current_claims().items():
        if predicate != BENCHMARK or not isinstance(c.value, int | float):
            continue
        o = obs.get(c.observation_id)
        out.append(Benchmark(claim_id=c.id, work=names.get(subject, subject), percentile=float(c.value),
                             year=c.event_date.year if c.event_date else None, review=statuses.get(c.id, "proposed"),
                             source_url=o.source_url if o else ""))  # fmt: skip
    return sorted(out, key=lambda b: -b.percentile)


def passage_text(text: str) -> str:
    """A snapshot's text for checking a quote word for word: words a PDF broke across lines with a hyphen are
    joined ("peti-\ntioner" -> "petitioner") and runs of whitespace become one space. Nothing else changes."""
    return re.sub(r"\s+", " ", re.sub(r"(\w)-[ \t]*\n\s*(\w)", r"\1\2", text)).strip()


def quoted_in(quote: str, text: str) -> bool:
    """Is this quote, word for word, in the source text (see passage_text)?"""
    q = re.sub(r"\s+", " ", quote).strip()
    return len(q) >= 8 and q in passage_text(text)


def check_standard(profile: Profile, vault: Any) -> list[StandardSentence]:
    """Each sentence about the standard against the passage it cites: verified when the quote is in the source's
    current, fresh copy; stale when the copy has expired; unverified when there's no copy or the quote isn't in it."""
    rules = profile.final_merits
    if rules is None:
        return []
    status = {s["id"]: s for s in vault.status()} if vault is not None else {}
    out = []
    for cite in rules.standard:
        st = status.get(cite.source_id) or {}
        common = {"text": cite.text, "section": cite.section, "source_id": cite.source_id, "quote": cite.quote,
                  "title": st.get("title", ""),
                  "link": st.get("link") or st.get("url") or ""}  # fmt: skip
        if not st.get("sha256"):
            out.append(StandardSentence(**common, status="unverified",
                                        why="This source isn't in your vault yet: sync Knowledge, or save the page."))  # fmt: skip
            continue
        if not quoted_in(cite.quote, vault.snapshot_text(st["sha256"])):
            out.append(
                StandardSentence(
                    **common, status="unverified", why="The quoted passage isn't in the current copy."
                )
            )
        elif not st.get("fresh"):
            out.append(
                StandardSentence(
                    **common, status="stale", why="The vault's copy has expired: sync Knowledge."
                )
            )
        else:
            out.append(
                StandardSentence(
                    **common, status="verified", why="Quoted from the current copy in your vault."
                )
            )
    return out


def report(ws: Any, vault: Any = None) -> MeritsReport:
    board = ws.scoreboard()
    profile = ws.profile()
    rules = profile.final_merits
    counted = counted_exhibits(ws, board)
    by_year: dict[int, dict[str, list[str]]] = {}
    for e in sorted(counted, key=lambda e: e.date):
        by_year.setdefault(e.date.year, {}).setdefault(e.criterion, []).append(e.id)
    years = sorted(by_year)
    timeline = [
        Year(year=y, count=sum(map(len, by_year[y].values())), by_criterion=by_year[y]) for y in years
    ]
    gaps = [y for y in range(years[0], years[-1] + 1) if y not in by_year] if years else []
    emps = employers(ws)
    marks = benchmarks(ws)
    themes = [_theme(t, counted, ws, emps, marks) for t in (rules.themes if rules else [])]
    return MeritsReport(profile=profile.id, label=rules.label if rules else "The evidence as a whole",
                        framing=rules.framing if rules else "", employer=emps, timeline=timeline,
                        first_year=years[0] if years else None, last_year=years[-1] if years else None,
                        gap_years=gaps, themes=themes, benchmarks=marks,
                        openalex_authors=sum(s.kind == "openalex" for s in ws.sources().sources), standard=check_standard(profile, vault),
                        no_organization=[e.id for e in counted if not organization(e)],
                        exhibits={e.id: {"title": e.title, "criterion": e.criterion, "date": e.date.isoformat(),
                                         "organization": organization(e)} for e in counted},
                        criteria={c.id: c.short_label or c.label for c in profile.criteria},
                        letters={lt.id: lt.name for lt in ws.letters().letters})  # fmt: skip


# ----------------------------------------------------------------------------------------------- OpenAlex (button)

WORK_FIELDS = "id,display_name,publication_year,cited_by_count,citation_normalized_percentile"


def benchmark_evidence(handle: str, works: list[dict[str, Any]], url: str) -> Evidence:
    """OpenAlex works as one observation, one claim per work that has a field percentile, each quoting its own
    line of the response (the percentile against works of the same field and year)."""
    lines, claims = [], []
    for w in works:
        line = json.dumps({k: w.get(k) for k in WORK_FIELDS.split(",")}, sort_keys=True)
        lines.append(line)
        pct = (w.get("citation_normalized_percentile") or {}).get("value")
        if pct is None:
            continue
        wid = str(w.get("id", "")).rsplit("/", 1)[-1]
        year = w.get("publication_year")
        claims.append(ClaimDraft(subject=f"work:openalex:{wid}", subject_kind="artifact",
                                 subject_name=str(w.get("display_name") or wid), predicate=BENCHMARK,
                                 value=round(float(pct) * 100, 1), excerpt=line, confidence="high",
                                 event_date=f"{year}-01-01" if year else None))  # fmt: skip
    return Evidence(connector="openalex", source_url=url, payload="\n".join(lines), media_type="text/plain",
                    filename=f"openalex-benchmarks-{handle}.jsonl", claims=claims)  # fmt: skip


def fetch_benchmarks(ws: Any, http: Any = None) -> dict[str, Any]:
    """For every OpenAlex author in Sources: their works' citation percentile against works of the same field and
    year, as claims in memory. Network: only when the person presses the button."""
    from areao1.sources.http import HttpClient
    from areao1.sources.openalex import API

    authors = [s for s in ws.sources().sources if s.kind == "openalex"]
    if not authors:
        raise ValueError("Add your OpenAlex author page in Sources first.")
    client = http or HttpClient(API, kind="openalex")
    recorded = 0
    for s in authors:
        data = client.get("/works", params={"filter": f"author.id:{s.handle}", "per-page": 100,
                                            "select": WORK_FIELDS, "sort": "cited_by_count:desc"}).data  # fmt: skip
        works = data.get("results") or []
        url = f"{API}/works?filter=author.id:{s.handle}&select={WORK_FIELDS}"
        ev = benchmark_evidence(s.handle, works, url)
        if ev.claims:
            recorded += len(ws.memory.record(ev))
    return {"authors": len(authors), "benchmarks": recorded}
