"""The connector interface. Adding a platform = one module implementing :class:`Source`.

Connectors are read-only and never file evidence: ``candidates()`` proposes, the user decides in the Inbox.
Candidates and metric rows carry the raw response they came from (``with_evidence``); the workspace turns
that into a memory observation plus claims that quote it verbatim.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Protocol, runtime_checkable

from lighthouse_gc.core.models import Candidate, ClaimDraft, Evidence, MetricRow, TrackedItem, json_excerpt

Item = TrackedItem
Metric = MetricRow
Creds = str | None  # a read-only token, or None for public access


@runtime_checkable
class Source(Protocol):
    kind: str  # "github", "huggingface", ...

    def detect(self, url_or_handle: str) -> bool:
        """Can this connector handle the input?"""
        ...

    def parse(self, url_or_handle: str) -> str:
        """Normalize the input to a handle: an account ('octo') or a single item path ('octo/repo')."""
        ...

    def source_url(self, handle: str) -> str:
        """Human-facing URL for the handle."""
        ...

    def discover(self, handle: str, creds: Creds) -> list[Item]:
        """Items (repos, models, datasets, ...) behind a handle."""
        ...

    def snapshot(self, item: Item, creds: Creds) -> list[Metric]:
        """Dated numbers for metrics.csv."""
        ...

    def candidates(self, item: Item, creds: Creds) -> list[Candidate]:
        """Proposed evidence for the Inbox."""
        ...


def paper_candidate(
    arxiv_id: str,
    source_id: str,
    item_id: str,
    context: str,
    title: str | None = None,
    facts: dict[str, Any] | None = None,
    evidence: Evidence | None = None,
) -> Candidate:
    """A paper found via a connector. Shared fingerprint so GitHub and HF never duplicate it."""
    cand = Candidate(
        fingerprint=f"paper:arxiv:{arxiv_id}:scholarly_articles",
        source=source_id,
        item_id=item_id,
        evidence_type="preprint",
        proposed_criterion="scholarly_articles",
        title=title or f"arXiv {arxiv_id}",
        summary=f"Paper arXiv:{arxiv_id} {context}. Confirm you are an author and add venue / peer-review status.",
        confidence=0.4,
        raw_url=f"https://arxiv.org/abs/{arxiv_id}",
        facts=facts or {},
        stage="preprint",  # a link to arXiv shows a preprint, not a peer-reviewed publication
    )
    return cand.with_evidence(evidence) if evidence else cand


def artifact_id(kind: str, name: str) -> str:
    return f"artifact:{kind}:{name}"


def field_claims(
    subject: str,
    subject_name: str,
    subject_url: str | None,
    payload: dict[str, Any],
    fields: dict[str, str],
    on: date,
) -> list[ClaimDraft]:
    """One claim per ``{predicate: json_key}`` present in ``payload``, quoting ``"key": value`` verbatim."""
    out = []
    for predicate, key in fields.items():
        if payload.get(key) is None:
            continue
        out.append(
            ClaimDraft(
                subject=subject,
                subject_name=subject_name,
                subject_url=subject_url,
                predicate=predicate,
                value=payload[key],
                excerpt=json_excerpt(key, payload[key]),
                valid_from=on,
            )
        )
    return out
