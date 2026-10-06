"""The connector interface. Adding a platform = one module implementing :class:`Source`.

Connectors are read-only and never file evidence: ``candidates()`` proposes, the user decides in the Inbox.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from lighthouse_gc.core.models import Candidate, MetricRow, TrackedItem

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
) -> Candidate:
    """A paper found via a connector. Shared fingerprint so GitHub and HF never duplicate it."""
    return Candidate(
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
    )
