"""Pydantic models for every workspace file.

These models are the single definition of each file's shape. The JSON Schemas in
``lighthouse_gc/core/schemas/`` are generated from them (``python -m lighthouse_gc.core.schemas``)
and a test fails if the two drift apart.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SCHEMA_VERSION: Final = 1

Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_\-]*$")]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


def utcnow() -> datetime:
    return datetime.now(UTC).replace(microsecond=0)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def slugify(text: str, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-") or "item"


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class _File(_Model):
    """Base for a top-level workspace file."""

    schema_version: Literal[1] = SCHEMA_VERSION


# --------------------------------------------------------------------------- person.json


class FilingTarget(_Model):
    profile: str = "o1a"
    target_date: date | None = None


class Petitioner(_Model):
    name: str = ""
    kind: Literal["employer", "agent", "self", "other"] = "employer"


class Person(_File):
    name: str = ""
    aliases: list[str] = Field(default_factory=list, description="Other spellings used for mention matching.")
    field: str = ""
    current_status: str = Field("", description="Current immigration status, e.g. F-1 OPT, H-1B.")
    location: str = ""
    filing_target: FilingTarget = Field(default_factory=FilingTarget)
    petitioner: Petitioner = Field(default_factory=Petitioner)


# --------------------------------------------------------------------------- sources.json


class TrackedItem(_Model):
    id: str = Field(description="Globally unique: '<source kind>:<path>', e.g. 'github:octo/repo'.")
    kind: str = Field(description="Item type within the source: repo, model, dataset, space, ...")
    name: str = Field(description="Path within the source, e.g. 'octo/repo' or 'datasets/octo/data'.")
    url: str
    title: str = ""
    private: bool = False
    tracked: bool = True
    discovered_at: datetime = Field(default_factory=utcnow)


class SourceRecord(_Model):
    id: str = Field(description="'<kind>:<handle>', e.g. 'github:octo'.")
    kind: str
    handle: str
    url: str
    auth: Literal["none", "token"] = "none"
    secret_ref: str | None = Field(
        None, description="Keychain entry name holding the token. Never the token."
    )
    added_at: datetime = Field(default_factory=utcnow)
    last_sync: datetime | None = None
    last_error: str | None = None
    items: list[TrackedItem] = Field(default_factory=list)


class SourcesFile(_File):
    sources: list[SourceRecord] = Field(default_factory=list)


# --------------------------------------------------------------------------- inbox.json


class Candidate(_Model):
    id: str = Field(default_factory=lambda: new_id("cand"))
    fingerprint: str = Field(description="Stable de-duplication key; re-imports never duplicate a candidate.")
    source: str = Field(description="Source record id that produced this candidate (or 'manual').")
    item_id: str | None = None
    evidence_type: str
    proposed_criterion: str
    title: str
    summary: str = Field(description="One-line summary shown in the Inbox.")
    confidence: Confidence = 0.5
    raw_url: str | None = None
    signals: list[str] = Field(default_factory=list, description="Strength signal ids the source observed.")
    facts: dict[str, float | int | str] = Field(default_factory=dict, description="Numbers at capture time.")
    created_at: datetime = Field(default_factory=utcnow)
    status: Literal["pending", "snoozed", "rejected"] = "pending"
    snoozed_until: date | None = None


class Inbox(_File):
    candidates: list[Candidate] = Field(default_factory=list)


# --------------------------------------------------------------------------- exhibits.json


EXHIBIT_NAME_RE = re.compile(
    r"^(?P<crit>[a-z0-9_]+)_(?P<date>\d{4}-\d{2}-\d{2})_(?P<slug>[a-z0-9\-]+)\.[a-z0-9]+$"
)


class Exhibit(_Model):
    id: str = Field(default_factory=lambda: new_id("exh"))
    criterion: str
    evidence_type: str
    title: str
    summary: str = ""
    date: date
    file: str = Field(
        description="Path relative to the workspace: evidence/<crit>/<crit>_<yyyy-mm-dd>_<slug>.<ext>"
    )
    source_url: str | None = None
    candidate_id: str | None = None
    fingerprint: str | None = Field(
        None, description="Fingerprint of the accepted candidate, for de-duplication."
    )
    signals: list[str] = Field(default_factory=list)
    accepted_at: datetime = Field(default_factory=utcnow)
    notes: str = ""

    @field_validator("file")
    @classmethod
    def _relative(cls, v: str) -> str:
        if v.startswith("/") or ".." in v.split("/"):
            raise ValueError("exhibit file must be a relative path inside the workspace")
        return v


class Exhibits(_File):
    exhibits: list[Exhibit] = Field(default_factory=list)


# --------------------------------------------------------------------------- criteria.json


CriterionState = Literal["banked", "building", "gap", "dropped"]


class CriterionScore(_Model):
    id: str
    label: str
    status: CriterionState
    exhibit_count: int = 0
    exhibit_ids: list[str] = Field(default_factory=list)
    matched_signals: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    needed_exhibits: int = Field(0, description="Exhibits still needed to reach 'banked'.")
    reason: str = ""
    overridden: bool = False


class Scoreboard(_File):
    profile: str
    profile_name: str
    computed_at: datetime = Field(default_factory=utcnow)
    threshold: int
    target: int
    banked: int
    building: int
    criteria: list[CriterionScore]
    reviewer_note: str | None = Field(
        None, description="Agent-written 'how a reviewer would see this' note. Opinion, not a rule result."
    )


# --------------------------------------------------------------------------- metrics.csv


METRICS_COLUMNS = ("date", "source", "item", "metric", "value")


class MetricRow(_Model):
    date: date
    source: str = Field(description="Connector kind, e.g. github, huggingface.")
    item: str = Field(description="Item path within the source, e.g. octo/repo.")
    metric: Slug
    value: float


# --------------------------------------------------------------------------- pipeline.json


class PipelineItem(_Model):
    id: str = Field(default_factory=lambda: new_id("pipe"))
    title: str
    criterion: str | None = None
    stage: Literal["idea", "applied", "waiting", "done"] = "idea"
    url: str | None = None
    follow_up: date | None = None
    created_at: datetime = Field(default_factory=utcnow)
    moved_at: datetime = Field(default_factory=utcnow)
    notes: str = ""


class Pipeline(_File):
    items: list[PipelineItem] = Field(default_factory=list)


# --------------------------------------------------------------------------- letters.json


class Letter(_Model):
    id: str = Field(default_factory=lambda: new_id("let"))
    name: str
    relationship: Literal["employer", "independent", "coauthor"]
    credentials: str = ""
    criteria: list[str] = Field(default_factory=list)
    asks: list[Literal["letter", "membership_ref"]] = Field(default=["letter"])
    status: Literal["prospect", "asked", "drafting", "sent", "signed", "declined"] = "prospect"
    draft_path: str | None = None
    last_contact: date | None = None


class Letters(_File):
    letters: list[Letter] = Field(default_factory=list)


# --------------------------------------------------------------------------- deadlines.json


class Deadline(_Model):
    id: str = Field(default_factory=lambda: new_id("dl"))
    title: str
    due: date
    kind: Literal["filing", "application", "submission", "follow_up", "personal", "other"] = "other"
    criterion: str | None = None
    url: str | None = None
    human_only: bool = Field(True, description="Needs the user, not the agent.")
    done: bool = False


class Deadlines(_File):
    deadlines: list[Deadline] = Field(default_factory=list)


# --------------------------------------------------------------------------- opportunities.json


class Opportunity(_Model):
    id: str = Field(default_factory=lambda: new_id("opp"))
    title: str
    criterion: str
    scan: str
    url: str | None = None
    deadline: date | None = None
    fit_score: Confidence = 0.0
    summary: str = ""
    status: Literal["new", "added", "dismissed"] = "new"
    found_at: datetime = Field(default_factory=utcnow)


class Opportunities(_File):
    opportunities: list[Opportunity] = Field(default_factory=list)


# --------------------------------------------------------------------------- lighthouse.yaml


class ServerConfig(_Model):
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(7777, ge=1024, le=65535)


class PrivacyConfig(_Model):
    redact_before_llm: bool = True


class ConnectorConfig(_Model):
    include_forks: bool = False
    min_stars_for_candidate: int = Field(5, ge=0)
    min_downloads_for_candidate: int = Field(100, ge=0)


class WorkspaceConfig(_File):
    workspace_name: str = "my-case"
    profile: str = "o1a"
    engine: Literal["claude_code", "codex", "api"] = "claude_code"
    server: ServerConfig = Field(default_factory=ServerConfig)
    schedules: dict[str, str] = Field(
        default_factory=lambda: {
            "sync": "0 8 * * *",
            "metrics-snapshot": "0 9 * * mon/2",
            "deadline-check": "0 7 * * *",
            "digest": "0 17 * * fri",
        },
        description="Cron expressions per job. Used by the scheduler (Phase 1) and as cron hints.",
    )
    connectors: ConnectorConfig = Field(default_factory=ConnectorConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    overrides: dict[str, dict[str, Literal["dropped", "gap"]]] = Field(
        default_factory=dict,
        description="User status overrides per profile: {profile_id: {criterion_id: dropped|gap}}.",
    )


# --------------------------------------------------------------------------- profiles/*.yaml


class StrengthSignal(_Model):
    id: Slug
    label: str


class CriterionRule(_Model):
    min_exhibits: int = Field(1, ge=1, description="Accepted exhibits needed to bank the criterion.")
    min_signals: int = Field(0, ge=0, description="Distinct strength signals needed to bank it.")


class ProfileCriterion(_Model):
    id: Slug
    label: str
    regulation: str = ""
    description: str = ""
    evidence_types: list[Slug]
    strength_signals: list[StrengthSignal] = Field(default_factory=list)
    bank: CriterionRule = Field(default_factory=CriterionRule)

    @field_validator("strength_signals", mode="before")
    @classmethod
    def _signals_from_strings(cls, v: object) -> object:
        # Profiles may list signals as plain strings ("peer-reviewed"); derive a stable id.
        if isinstance(v, list):
            return [{"id": slugify(s).replace("-", "_"), "label": s} if isinstance(s, str) else s for s in v]
        return v


class NarrativeLayer(_Model):
    id: Slug
    label: str
    description: str = ""
    prompts: list[str] = Field(default_factory=list)


class Profile(_Model):
    id: Slug
    name: str
    regulation: str = ""
    description: str = ""
    threshold: int = Field(ge=1)
    target: int = Field(ge=1)
    criteria: list[ProfileCriterion]
    narrative: list[NarrativeLayer] = Field(
        default_factory=list, description="Qualitative layers scored by the agent, e.g. EB-1A final merits."
    )

    def criterion(self, criterion_id: str) -> ProfileCriterion | None:
        return next((c for c in self.criteria if c.id == criterion_id), None)


# Files the schema generator emits, keyed by schema file stem.
WORKSPACE_FILE_MODELS: dict[str, type[BaseModel]] = {
    "person": Person,
    "sources": SourcesFile,
    "inbox": Inbox,
    "exhibits": Exhibits,
    "criteria": Scoreboard,
    "metric-row": MetricRow,
    "pipeline": Pipeline,
    "letters": Letters,
    "deadlines": Deadlines,
    "opportunities": Opportunities,
    "lighthouse-config": WorkspaceConfig,
    "profile": Profile,
}
