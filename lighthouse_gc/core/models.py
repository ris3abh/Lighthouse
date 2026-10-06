"""Domain-agnostic pydantic models: workspace files, the inbox, metrics and the memory store (5b).

These models are the single definition of each file's shape. The JSON Schemas in
``lighthouse_gc/core/schemas/`` are generated from them (``python -m lighthouse_gc.schemas``)
and a test fails if the two drift apart. Nothing here knows about any particular profile.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, date, datetime
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator

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


# --------------------------------------------------------------------------- event stages

# Lifecycle of an activity. An invitation is not a completion: only COMPLETED_STAGES count toward
# anything. ``None`` means the evidence isn't an activity (e.g. a repo's star count).
Stage = Literal[
    "invited", "accepted", "completed", "declined", "cancelled",  # judging, talks, reviewing
    "preprint", "submitted", "published", "retracted",  # papers
    "applied", "granted", "denied",  # memberships, awards
]  # fmt: skip
COMPLETED_STAGES: frozenset[str] = frozenset({"completed", "published", "granted"})


def stage_counts(stage: str | None) -> bool:
    return stage is None or stage in COMPLETED_STAGES


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
    kind: Literal["evidence", "pipeline", "deadline", "letter"] = Field(
        "evidence",
        description="evidence becomes an exhibit; the others become tracker entries, never exhibits.",
    )
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
    stage: Stage | None = Field(None, description="Event stage the evidence shows; None if not an activity.")
    claim_ids: list[str] = Field(default_factory=list, description="Memory claims this candidate rests on.")
    status: Literal["pending", "snoozed", "rejected"] = "pending"
    snoozed_until: date | None = None

    # Raw evidence a connector attached; turned into an observation + claims by the sync job.
    _evidence: Evidence | None = PrivateAttr(default=None)

    def with_evidence(self, evidence: Evidence) -> Candidate:
        self._evidence = evidence
        return self


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
    stage: Stage | None = Field(None, description="Only completed stages (or None) count toward a criterion.")
    claim_ids: list[str] = Field(
        default_factory=list, description="Approved memory claims this exhibit cites."
    )
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


# --------------------------------------------------------------------------- metrics.csv


METRICS_COLUMNS = ("date", "source", "item", "metric", "value")


class MetricRow(_Model):
    date: date
    source: str = Field(description="Connector kind, e.g. github, huggingface.")
    item: str = Field(description="Item path within the source, e.g. octo/repo.")
    metric: Slug
    value: float

    _evidence: Evidence | None = PrivateAttr(default=None)

    def with_evidence(self, evidence: Evidence) -> MetricRow:
        self._evidence = evidence
        return self


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
    profile: str = Field("", description="Active profile id; the domain layer supplies the default.")
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


# --------------------------------------------------------------------------- memory/ (section 5b)
#
# Append-only JSONL: memory/observations.jsonl, claims.jsonl, edges.jsonl, decisions.jsonl,
# entities.jsonl, plus raw snapshots in memory/sources/<sha256>.<ext>. Nothing is overwritten;
# a newer claim SUPERSEDES an older one. A SQLite index in .lighthouse/cache/ is rebuilt from these.

ConfidenceBand = Literal["high", "medium", "low"]
ReviewStatus = Literal["proposed", "corroborated", "approved", "rejected"]
EdgeType = Literal["DERIVED_FROM", "ABOUT", "SUPPORTS", "CONTRADICTS", "SUPERSEDES", "REVIEWED_BY", "CITES"]
ClaimValue = str | int | float | bool | None


class ExtractedBy(_Model):
    kind: Literal["connector", "model", "user"]
    name: str = Field(description="Connector kind, model id, or 'user'.")
    version: str = ""


class Observation(_Model):
    """A raw snapshot exactly as it was captured."""

    id: str = Field(description="'obs_' + first 16 hex chars of sha256.")
    connector: str
    source_url: str
    captured_at: datetime = Field(default_factory=utcnow)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    snapshot: str = Field(description="Path relative to the workspace, memory/sources/<sha256>.<ext>")
    media_type: str = "application/json"


class Entity(_Model):
    id: str = Field(description="'<kind>:<stable key>', e.g. 'artifact:github:octo/repo'.")
    kind: Literal["person", "artifact", "org", "venue", "event", "letter_writer", "other"]
    name: str
    url: str | None = None
    recorded_at: datetime = Field(default_factory=utcnow)


class Claim(_Model):
    """One factual statement, tied to the exact text it was read from."""

    id: str = Field(default_factory=lambda: new_id("clm"))
    subject: str = Field(description="Entity id the claim is about.")
    predicate: Slug
    value: ClaimValue
    stage: Stage | None = None
    event_date: date | None = None
    valid_from: date | None = Field(None, description="When it became true in the world.")
    valid_to: date | None = None
    recorded_at: datetime = Field(default_factory=utcnow, description="When Lighthouse learned it.")
    observation_id: str
    excerpt: str = Field(description="Exact supporting text from the observation snapshot.")
    excerpt_start: int = Field(ge=0)
    excerpt_end: int = Field(ge=0)
    extracted_by: ExtractedBy
    confidence: ConfidenceBand = "medium"
    version: int = Field(1, ge=1)


class Edge(_Model):
    id: str = Field(default_factory=lambda: new_id("edge"))
    type: EdgeType
    src: str
    dst: str
    recorded_at: datetime = Field(default_factory=utcnow)


class Decision(_Model):
    """A review record. Approval records a decision; it does not certify truth or legal sufficiency."""

    id: str = Field(default_factory=lambda: new_id("dec"))
    claim_id: str
    decision: Literal["approved", "rejected"]
    reviewer: str = "user"
    at: datetime = Field(default_factory=utcnow)
    rationale: str = ""


# Drafts: what a connector hands over before the memory store assigns ids and offsets.


class ClaimDraft(_Model):
    subject: str
    subject_kind: Literal["person", "artifact", "org", "venue", "event", "letter_writer", "other"] = (
        "artifact"
    )
    subject_name: str
    subject_url: str | None = None
    predicate: Slug
    value: ClaimValue
    excerpt: str = Field(description="Must occur verbatim in the observation's canonical text.")
    stage: Stage | None = None
    event_date: date | None = None
    valid_from: date | None = None
    confidence: ConfidenceBand = "high"


class Evidence(_Model):
    connector: str
    source_url: str
    payload: Any = Field(description="Raw JSON payload, or a string for text/markdown.")
    media_type: str = "application/json"
    claims: list[ClaimDraft] = Field(default_factory=list)


def canonical_text(payload: Any, media_type: str) -> str:
    """The exact text stored as a snapshot; excerpt offsets index into this."""
    import json

    if media_type == "application/json":
        return json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    return str(payload)


def json_excerpt(key: str, value: Any) -> str:
    """The verbatim line fragment ``"key": value`` as it appears in a canonical JSON snapshot."""
    import json

    return f"{json.dumps(key)}: {json.dumps(value, ensure_ascii=False)}"


Candidate.model_rebuild()
MetricRow.model_rebuild()
