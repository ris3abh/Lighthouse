"""Shared pieces of the scholarly connectors (Semantic Scholar, OpenAlex, arXiv, ORCID).

Each connector turns an author identifier into one ``author`` item (profile-level metrics: citations,
h-index, paper count) and one ``paper`` item per work. Every paper is proposed for the scholarly-articles
criterion, with what the source says about it: venue, year, type, citations. Connectors can't know whether
the account is really the person (author pages get merged), so every proposal asks them to confirm.

The same paper found by several connectors (or linked from GitHub / Hugging Face) is proposed once: the
fingerprint is the arXiv id when there is one, else the DOI, else the source's own id.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from lighthouse_gc.core import clock
from lighthouse_gc.core.models import Candidate, ConnectorConfig, Evidence, MetricRow, TrackedItem
from lighthouse_gc.sources.base import dig, field_claims
from lighthouse_gc.sources.http import HttpClient

MAX_PAPERS = 500
_ARXIV_ID = re.compile(
    r"(?:arxiv[:/]|abs/|pdf/)?(\d{4}\.\d{4,5}|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?:v\d+)?", re.I
)


def arxiv_id(value: str | None) -> str | None:
    """'arXiv:2509.04321v2', 'https://arxiv.org/abs/2509.04321' -> '2509.04321'."""
    if not value:
        return None
    m = _ARXIV_ID.search(value)
    return m.group(1) if m else None


def doi(value: str | None) -> str | None:
    """'https://doi.org/10.1038/X' -> '10.1038/x' (DOIs are case-insensitive)."""
    if not value:
        return None
    m = re.search(r"10\.\d{4,9}/\S+", value)
    return m.group(0).rstrip(".").lower() if m else None


@dataclass
class Paper:
    key: str  # the source's own id for the work
    title: str
    payload: dict[str, Any]  # the source's record for it (quoted by the claims)
    source_url: str  # the API URL the record came from
    url: str  # human-facing page
    year: int | None = None
    venue: str = ""
    kind: str = "unknown"  # journal | conference | preprint | unknown
    doi: str | None = None
    arxiv: str | None = None
    citations: int | None = None
    claim_fields: dict[str, str] = field(default_factory=dict)  # predicate -> top-level key in payload
    extra: dict[str, str] = field(default_factory=dict)  # more facts (journal_ref, type, ...)

    @property
    def fingerprint(self) -> str:
        if self.arxiv:
            return f"paper:arxiv:{self.arxiv}:scholarly_articles"
        if self.doi:
            return f"paper:doi:{self.doi}:scholarly_articles"
        return f"paper:{self.key}:scholarly_articles"

    @property
    def subject(self) -> str:
        return (f"artifact:arxiv:{self.arxiv}" if self.arxiv
                else f"artifact:doi:{self.doi}" if self.doi else f"artifact:paper:{self.key}")  # fmt: skip


class ScholarlySource:
    """Base for the four scholarly connectors. Subclasses set ``kind``, ``API`` and implement ``parse``,
    ``source_url``, ``author`` (profile record + metric fields) and ``fetch_papers``."""

    kind = "scholarly"
    label = "Scholarly"
    API = ""
    confidence = 0.5  # how sure we are the profile's works are the person's (merged author pages exist)

    def __init__(self, http: HttpClient | None = None, config: ConnectorConfig | None = None,
                 today: Callable[[], date] = clock.today):  # fmt: skip
        self.http = http or HttpClient(self.API, kind=self.kind)
        self.config = config or ConnectorConfig()
        self.today = today
        self._papers: dict[str, list[Paper]] = {}

    # -- input -------------------------------------------------------------------------------

    @classmethod
    def detect(cls, url_or_handle: str) -> bool:
        try:
            cls.parse(url_or_handle)
            return True
        except ValueError:
            return False

    @staticmethod
    def parse(url_or_handle: str) -> str:
        raise NotImplementedError

    def source_url(self, handle: str) -> str:
        raise NotImplementedError

    # -- what subclasses provide -------------------------------------------------------------

    def author(self, handle: str) -> tuple[dict[str, Any], str, dict[str, str]]:
        """(the author record, its API URL, {metric: top-level key}) for profile metrics."""
        raise NotImplementedError

    def fetch_papers(self, handle: str) -> list[Paper]:
        raise NotImplementedError

    def papers(self, handle: str) -> list[Paper]:
        if handle not in self._papers:
            self._papers[handle] = self.fetch_papers(handle)[:MAX_PAPERS]
        return self._papers[handle]

    def author_name(self, record: dict[str, Any], handle: str) -> str:
        return str(record.get("name") or handle)

    # -- the Source interface -----------------------------------------------------------------

    def discover(self, handle: str, creds: str | None) -> list[TrackedItem]:
        record, _, _ = self.author(handle)
        items = [TrackedItem(id=f"{self.kind}:{handle}", kind="author", name=handle, url=self.source_url(handle),
                             title=self.author_name(record, handle))]  # fmt: skip
        items += [TrackedItem(id=f"{self.kind}:{handle}/{p.key}", kind="paper", name=f"{handle}/{p.key}", url=p.url,
                              title=p.title[:200]) for p in self.papers(handle)]  # fmt: skip
        return items

    def snapshot(self, item: TrackedItem, creds: str | None) -> list[MetricRow]:
        today = self.today()
        if item.kind == "author":
            record, url, fields = self.author(item.name)
            evidence = self._evidence(
                url, record, f"artifact:{self.kind}:{item.name}", item.title, item.url, fields
            )
            return [MetricRow(date=today, source=self.kind, item=item.name, metric=metric, value=float(dig(record, key)))
                    .with_evidence(evidence) for metric, key in fields.items()
                    if isinstance(dig(record, key), int | float)]  # fmt: skip
        paper = self._paper(item)
        if paper is None or paper.citations is None:
            return []
        evidence = self._evidence(paper.source_url, paper.payload, paper.subject, paper.title, paper.url,
                                  paper.claim_fields)  # fmt: skip
        return [MetricRow(date=today, source=self.kind, item=item.name, metric="citations",
                          value=float(paper.citations)).with_evidence(evidence)]  # fmt: skip

    def candidates(self, item: TrackedItem, creds: str | None) -> list[Candidate]:
        if item.kind != "paper":
            return []
        paper = self._paper(item)
        if paper is None:
            return []
        handle = item.name.split("/", 1)[0]
        evidence_type, stage, signals = _classify(paper)
        facts: dict[str, float | int | str] = {k: v for k, v in {
            "venue": paper.venue, "year": paper.year, "citations": paper.citations, "doi": paper.doi,
            "arxiv": paper.arxiv, **paper.extra}.items() if v not in (None, "")}  # fmt: skip
        where = (
            f" in {paper.venue}" if paper.venue else (" (arXiv preprint)" if paper.kind == "preprint" else "")
        )
        cites = f", cited {paper.citations:,} times" if paper.citations else ""
        year = f" ({paper.year})" if paper.year else ""
        return [Candidate(
            fingerprint=paper.fingerprint, source=f"{self.kind}:{handle}", item_id=item.id, evidence_type=evidence_type,
            proposed_criterion="scholarly_articles", title=f"Paper: {paper.title}"[:200],
            summary=(f"{paper.title}{year}{where}{cites}. Listed on your {self.label} profile; confirm you are an "
                     "author" + ("" if stage == "published" else " and add the venue if it was published") + "."),
            confidence=self.confidence, raw_url=paper.url, signals=signals, facts=facts, stage=stage,
        ).with_evidence(self._evidence(paper.source_url, paper.payload, paper.subject, paper.title, paper.url,
                                       paper.claim_fields))]  # fmt: skip

    # -- helpers --------------------------------------------------------------------------------

    def _paper(self, item: TrackedItem) -> Paper | None:
        handle, _, key = item.name.partition("/")
        return next((p for p in self.papers(handle) if p.key == key), None)

    def _evidence(self, url: str, payload: dict[str, Any], subject: str, name: str, page: str,
                  fields: dict[str, str]) -> Evidence:  # fmt: skip
        return Evidence(connector=self.kind, tier="platform", source_url=url, payload=payload,
                        claims=field_claims(subject, name, page, payload, fields, self.today()))  # fmt: skip


def _classify(p: Paper) -> tuple[str, str, list[str]]:
    """(evidence type, stage, signals) from what the source says about the venue."""
    signals = ["cited"] if p.citations else []
    if p.kind in ("journal", "conference"):
        return (
            ("journal_article" if p.kind == "journal" else "conference_paper"),
            "published",
            ["peer_reviewed", *signals],
        )
    if p.kind == "preprint" or not p.venue:
        return "preprint", "preprint", signals
    return "paper", "published", signals  # a named venue of unknown type: published, peer review not shown
