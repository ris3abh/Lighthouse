"""Knowledge vault data models (SPEC 5a): the source manifest, the fetch log and search hits."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from lighthouse_gc.core.models import new_id, utcnow

Tier = Literal[1, 2, 3]
Format = Literal["auto", "html", "xml", "pdf", "json", "text"]
FetchStatus = Literal["new", "changed", "unchanged", "unreadable", "error"]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VaultSource(_Model):
    id: str = Field(..., pattern=r"^[a-z0-9][a-z0-9-]{1,79}$")
    title: str = Field(..., min_length=1, max_length=200)
    url: str = Field(..., description="May contain {ecfr_date}, {year}, {month}, {fy}.")
    tier: Tier
    kind: str = Field(..., description="Fact kind; its freshness window comes from the manifest's ttl_days.")
    topics: list[str] = Field(default_factory=list)
    format: Format = "auto"
    ecfr_title: int | None = Field(
        None, description="For {ecfr_date}: the CFR title whose latest issue date to use."
    )
    start: str | None = Field(None, description="Regex (multiline): keep text from the first match.")
    end: str | None = Field(None, description="Regex (multiline): stop before the first match after start.")
    ttl_days: int | None = Field(None, ge=1, description="Overrides the kind's freshness window.")
    enabled: bool = True
    notes: str = ""


class VaultManifest(_Model):
    version: Literal[1] = 1
    ttl_days: dict[str, int | Literal["monthly"]] = Field(default_factory=dict)
    tier1_domains: list[str] = Field(default_factory=list)
    rule_hints: list[str] = Field(
        default_factory=list, description="Regexes for sentences that may state a rule."
    )
    sources: list[VaultSource] = Field(default_factory=list)

    @field_validator("sources")
    @classmethod
    def _unique_ids(cls, v: list[VaultSource]) -> list[VaultSource]:
        ids = [s.id for s in v]
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        if dupes:
            raise ValueError(f"duplicate source ids: {dupes}")
        return v

    def source(self, source_id: str) -> VaultSource | None:
        return next((s for s in self.sources if s.id == source_id), None)

    def ttl(self, source: VaultSource) -> int | Literal["monthly"]:
        if source.ttl_days:
            return source.ttl_days
        return self.ttl_days.get(source.kind, 30)

    def expires_at(self, source: VaultSource, checked_at: datetime) -> datetime:
        ttl = self.ttl(source)
        if ttl == "monthly":
            first = checked_at.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            return (first + timedelta(days=32)).replace(day=1)
        return checked_at + timedelta(days=ttl)


class DiffSummary(_Model):
    added: int = 0
    removed: int = 0
    sample: list[str] = Field(default_factory=list, description="A few added or changed lines.")


class VaultFetch(_Model):
    """One fetch of one source, appended to the workspace's vault/log.jsonl (unchanged re-checks aren't logged)."""

    id: str = Field(default_factory=lambda: new_id("vf"))
    source_id: str
    url: str
    tier: Tier
    fetched_at: datetime = Field(default_factory=utcnow)
    status: FetchStatus
    origin: Literal["fetch", "manual"] = Field("fetch", description="manual: imported from a saved page.")
    sha256: str | None = None
    previous_sha256: str | None = None
    effective_date: date | None = None
    chars: int = 0
    error: str | None = None
    diff: DiffSummary | None = None


class VaultHit(_Model):
    chunk_id: str
    source_id: str
    title: str
    tier: Tier
    kind: str
    url: str
    text: str
    start: int = Field(..., description="Offset of this chunk in the snapshot text.")
    end: int
    sha256: str
    checked_at: datetime
    expires_at: datetime
    effective_date: date | None = None
    fresh: bool
    score: float
