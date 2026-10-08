"""Domain-agnostic pydantic models: workspace files, the inbox, metrics and the memory store (5b).

These models are the single definition of each file's shape. The JSON Schemas in
``areao1/core/schemas/`` are generated from them (``python -m areao1.schemas``)
and a test fails if the two drift apart. Nothing here knows about any particular profile.
"""

from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from typing import Annotated, Any, Final, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator

SCHEMA_VERSION: Final = 1

Slug = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_\-]*$")]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


def utcnow() -> datetime:
    from areao1.core import clock

    return clock.utcnow()


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


# --------------------------------------------------------------------------- source tiers

# How much a source can be trusted on its own. Tiers 1-3 follow SPEC 5a (primary law, adjudication,
# secondary); "platform" is a service's own API (GitHub, Hugging Face); "user" is a document the user filed;
# "self_reported" is the user's own words (e.g. imported chat history): useful for trackers, never proof.
SourceTier = Literal["tier1", "tier2", "tier3", "platform", "user", "self_reported"]
NON_EVIDENTIARY_TIERS: frozenset[str] = frozenset({"self_reported"})


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
    unreadable: str | None = Field(
        None,
        description="Why the page couldn't be read automatically (bot protection, login wall, maintenance).",
    )


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
    kind: Literal["evidence", "pipeline", "deadline", "letter", "update", "metric", "context"] = Field(
        "evidence",
        description="evidence becomes an exhibit; pipeline / deadline / letter add tracker entries; update changes "
        "an existing tracker entry; metric records a metric value; context (from an AI tool over MCP) is kept as a "
        "self-reported note. Only evidence can ever become an exhibit.",
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
    attachment: str | None = Field(None, description="Observation id of an uploaded file filed on accept.")
    source_tier: SourceTier | None = Field(None, description="Tier of the source this candidate came from.")
    proposal: dict[str, Any] = Field(
        default_factory=dict,
        description="For tracker candidates: the pipeline / deadline / letter entry to add.",
    )
    status: Literal["pending", "snoozed", "rejected"] = "pending"
    snoozed_until: date | None = None
    rule_check: RuleCheck | None = Field(None, description="Rule claims in agent-written text, checked.")

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
    source_tier: SourceTier | None = Field(
        None, description="self_reported exhibits never count toward a criterion."
    )
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


# --------------------------------------------------------------------------- rule checks


RuleStatus = Literal["verified", "unverified", "stale", "conflict"]


class RuleCitation(_Model):
    """A knowledge-store excerpt a rule claim was checked against, with the exact words quoted from it."""

    chunk_id: str
    source_id: str
    title: str
    tier: int
    url: str
    quote: str
    start: int = Field(..., description="Offset of the quote in the source snapshot.")
    end: int
    sha256: str = Field(..., description="The snapshot the quote is from.")
    checked_at: datetime
    verdict: Literal["entails", "contradicts"]
    fresh: bool = True
    secondary_to: str | None = Field(
        None, description="Set for a secondary copy: the primary source's id. The primary governs."
    )


class RuleClaim(_Model):
    id: str = Field(default_factory=lambda: new_id("rc"))
    text: str = Field(..., description="The rule as the checker restated it.")
    sentence: str = Field(..., description="The sentence it came from.")
    start: int = Field(0, description="Offset of the sentence in the checked text.")
    end: int = 0
    kind: str = "other"
    status: RuleStatus
    reason: str = ""
    citations: list[RuleCitation] = Field(default_factory=list)


class RuleCheck(_Model):
    """Rule claims found in a piece of agent-written text and how each was verified (SPEC 5a)."""

    checked_at: datetime = Field(default_factory=utcnow)
    model: str | None = None
    claims: list[RuleClaim] = Field(default_factory=list)
    note: str | None = Field(None, description="Why nothing was checked, or why checking failed.")
    cost_usd: float | None = None

    @property
    def blocking(self) -> list[RuleClaim]:
        return [c for c in self.claims if c.status != "verified"]


# --------------------------------------------------------------------------- briefing.json


class BriefingTodo(_Model):
    title: str = Field(..., min_length=1, max_length=160)
    why: str = Field("", max_length=400)
    candidate_id: str | None = Field(None, description="An Inbox item this action approves or dismisses.")
    link: str | None = Field(None, description="An in-app route (#/pipeline) or a URL.")


class Briefing(_File):
    """The agent-written Overview briefing, refreshed by the daily what-changed mission."""

    generated_at: datetime | None = None
    run_id: str | None = None
    since: date | None = None
    changed: list[str] = Field(default_factory=list, max_length=8, description="What changed, one line each.")
    todos: list[BriefingTodo] = Field(
        default_factory=list, max_length=3, description="Three things this week."
    )
    rule_check: RuleCheck | None = None


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


# --------------------------------------------------------------------------- areao1.yaml


class ServerConfig(_Model):
    host: Literal["127.0.0.1"] = "127.0.0.1"
    port: int = Field(7777, ge=1024, le=65535)


class PrivacyConfig(_Model):
    redact_before_llm: bool = True


class ConnectorConfig(_Model):
    include_forks: bool = False
    min_stars_for_candidate: int = Field(5, ge=0)
    min_downloads_for_candidate: int = Field(100, ge=0)


class ChannelConfig(_Model):
    """One notification channel. Secrets (webhook URLs, SMTP password, ntfy token) live in the keychain
    under ``secret_ref``; this file only names the entry."""

    kind: Literal["desktop", "email", "slack", "discord", "ntfy"]
    enabled: bool = True
    detail: Literal["full", "minimal"] = Field(
        "full", description="minimal sends counts only (no titles), for channels that leave this machine."
    )
    secret_ref: str | None = Field(
        None, description="Keychain entry: webhook URL, SMTP password or ntfy token."
    )
    # email
    host: str | None = None
    port: int = Field(587, ge=1, le=65535)
    starttls: bool = True
    username: str | None = None
    from_addr: str | None = None
    to_addr: str | None = None
    # ntfy
    server: str = "https://ntfy.sh"
    topic: str | None = None


NotificationEvent = Literal["deadline", "digest", "new_candidates", "sync_error", "mission", "vault", "test"]


def _default_routes() -> dict[NotificationEvent, list[str]]:
    return {"deadline": ["desktop"], "digest": ["desktop"], "new_candidates": ["desktop"],
            "sync_error": ["desktop"], "mission": ["desktop"], "vault": ["desktop"], "test": ["desktop"]}  # fmt: skip


class NotificationsConfig(_Model):
    channels: dict[str, ChannelConfig] = Field(
        default_factory=lambda: {"desktop": ChannelConfig(kind="desktop")},
        description="Named channels. Desktop is on by default; add email / slack / discord / ntfy as needed.",
    )
    routes: dict[NotificationEvent, list[str]] = Field(
        default_factory=lambda: _default_routes(), description="Which channels each event goes to."
    )

    @field_validator("routes", mode="before")
    @classmethod
    def _new_events_get_default_routes(cls, v: Any) -> Any:
        # Events added in later versions route to their defaults until the user configures them.
        return {**_default_routes(), **v} if isinstance(v, dict) else v

    deadline_alert_days: list[int] = Field(
        default_factory=lambda: [14, 3, 1, 0], description="Alert when a deadline is this many days away."
    )


class AutopilotConfig(_Model):
    """What the agent may apply without asking. Everything is off by default; nothing that could affect a
    criterion (evidence, exhibits, overrides, profile) can ever be auto-applied, whatever is set here."""

    tracker_updates: bool = Field(
        False, description="Pipeline stage / follow-up / notes, letter status / contact, deadline edits."
    )
    metrics: bool = Field(False, description="Metric values the agent read from a page and quoted.")
    tier1_deadlines: bool = Field(
        False, description="New deadlines quoted from a Tier-1 source (primary law or agency pages, SPEC 5a)."
    )


class AgentBudget(_Model):
    """Spend caps. Tokens counted = input + output + cache-creation (cache reads are recorded, not counted)."""

    per_run_tokens: int = Field(300_000, ge=1_000)
    per_run_usd: float | None = Field(2.0, gt=0)
    monthly_tokens: int = Field(10_000_000, ge=1_000)
    monthly_usd: float | None = Field(50.0, gt=0)


class AgentModels(_Model):
    """One model per tier (ADR 0015 §2): change a line to upgrade a tier. Which tasks use which tier is a fixed
    table (agent/routing.py)."""

    hard: str = Field("gpt-6.1-sol", description="Chat, hand-started runs, letters.")
    mid: str = Field("gpt-6.1-sol", description="Missions, the rule-check judge, PDFs, cheap-mode chat.")
    mundane: str = Field("gpt-6-luna", description="Chat extraction, long-chat summaries, mail sorting.")

    @model_validator(mode="before")
    @classmethod
    def _from_claude_slots(cls, data: Any) -> Any:
        # Before ADR 0015: per-run-type slots (chat, task, mission, check) and Claude model names. Those load as
        # the OpenAI defaults; a non-Claude model set in a slot carries over to its tier.
        if not isinstance(data, dict):
            return data
        old = {"chat": "hard", "task": "hard", "mission": "mid", "check": "mid"}
        if not (set(data) & set(old)) and not any(str(v).startswith("claude") for v in data.values()):
            return data
        from areao1.core import migrate

        out: dict[str, Any] = {}
        for key, value in data.items():
            tier = old.get(key, key)
            if tier in ("hard", "mid", "mundane") and not str(value).startswith("claude"):
                out.setdefault(tier, value)
        migrate.note("agent.models now has one line per tier (hard, mid, mundane) on OpenAI; Claude models "
                     "were replaced with the defaults (ADR 0015).")  # fmt: skip
        return out


class MissionsConfig(_Model):
    """Scheduled agent runs. Off by default: they spend tokens without anyone pressing a button. Schedules live
    in ``schedules`` (mission-opportunity-scout, mission-what-changed); budgets apply as for any run."""

    opportunity_scout: bool = Field(False, description="Weekly: find opportunities for the weakest criteria.")
    what_changed: bool = Field(False, description="Daily: review what changed and write the briefing.")


class AgentConfig(_Model):
    models: AgentModels = Field(default_factory=AgentModels)
    missions: MissionsConfig = Field(default_factory=MissionsConfig)

    @model_validator(mode="before")
    @classmethod
    def _migrate_single_model(cls, data: Any) -> Any:
        # Before per-run-type models, areao1.yaml had `agent.model`; keep those workspaces loading.
        if isinstance(data, dict) and "model" in data:
            data = dict(data)
            legacy = data.pop("model")
            models = dict(data.get("models") or {})
            models.setdefault("chat", legacy)
            data["models"] = models
        return data

    effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    cheap_mode: bool = Field(
        False, description="Run chat on the mid tier instead of the hard one (ADR 0009 §3)."
    )
    web_search: bool = True
    max_turns: int = Field(25, ge=1, le=200)
    budget: AgentBudget = Field(default_factory=AgentBudget)
    autopilot: AutopilotConfig = Field(default_factory=AutopilotConfig)


DEFAULT_SCHEDULES: dict[str, str] = {
    "sync": "0 8 * * *",
    "metrics-snapshot": "0 9 * * mon",  # runs weekly; the job itself skips unless 13+ days passed
    "deadline-check": "0 7 * * *",
    "digest": "0 17 * * fri",
    "mission-opportunity-scout": "0 9 * * fri",
    "mission-what-changed": "0 7 * * *",
    "vault-watch": "0 6 * * *",
    "google": "*/15 * * * *",  # Gmail threads with contacts and follow-ups; skips (no network) until connected
}


class VaultConfig(_Model):
    enabled: bool = Field(True, description="Fetch the public sources listed in the vault manifest.")


class OutreachConfig(_Model):
    """Emails to your contacts (ADR 0014 §5): drafted, approved by you, then sent from your Gmail."""

    daily_limit: int = Field(10, ge=0, le=100, description="Most emails sent per day; checked at approval.")
    follow_up_days: int = Field(
        7, ge=2, le=60, description="Quiet days after your email before a follow-up draft."
    )


class MailConfig(_Model):
    """The Mail view on Contacts (ADR 0014, Mail view amendment)."""

    model_sorting: bool = Field(False, description="Send mail no rule could sort to the mundane model tier "
                                "(sender, subject, first lines, redacted). Off: rules only.")  # fmt: skip


class WorkspaceConfig(_File):
    workspace_name: str = "my-case"
    profile: str = Field("", description="Active profile id; the domain layer supplies the default.")
    engine: Literal["openai"] = Field("openai", description="The agent engine (ADR 0015: OpenAI only).")

    @field_validator("engine", mode="before")
    @classmethod
    def _engine_is_openai(cls, v: Any) -> str:
        return "openai"  # claude_code, codex and api from before ADR 0015 load as OpenAI

    server: ServerConfig = Field(default_factory=ServerConfig)
    vault: VaultConfig = Field(default_factory=VaultConfig)
    outreach: OutreachConfig = Field(default_factory=OutreachConfig)
    mail: MailConfig = Field(default_factory=MailConfig)
    schedules: dict[str, str] = Field(
        default_factory=lambda: dict(DEFAULT_SCHEDULES), description="Cron per job; '' turns a job off."
    )

    @field_validator("schedules", mode="before")
    @classmethod
    def _new_jobs_get_default_schedules(cls, v: Any) -> Any:
        # Jobs added in later versions get their default schedule until the user sets one ('' to turn off).
        return {**DEFAULT_SCHEDULES, **v} if isinstance(v, dict) else v

    connectors: ConnectorConfig = Field(default_factory=ConnectorConfig)
    notifications: NotificationsConfig = Field(default_factory=NotificationsConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    privacy: PrivacyConfig = Field(default_factory=PrivacyConfig)
    overrides: dict[str, dict[str, Literal["dropped", "gap"]]] = Field(
        default_factory=dict,
        description="User status overrides per profile: {profile_id: {criterion_id: dropped|gap}}.",
    )


# --------------------------------------------------------------------------- data/changes.jsonl


class Change(_Model):
    """One user- or agent-initiated write, recorded by the service layer (append-only audit trail).
    ``before`` / ``after`` hold the record's state so a change can be reviewed or undone."""

    id: str = Field(default_factory=lambda: new_id("chg"))
    at: datetime = Field(default_factory=utcnow)
    actor: str = Field(description="'user', or 'agent:<run id>'.")
    action: str = Field(description="e.g. inbox.accept, pipeline.move, deadline.update")
    target_type: str
    target_id: str | None = None
    summary: str = ""
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    auto: bool = Field(False, description="Applied by autopilot without the user's approval (undoable).")
    undoes: str | None = Field(None, description="For an undo: the id of the change it reverted.")


# --------------------------------------------------------------------------- agent/ (ADR 0005)


class RunUsage(_Model):
    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def counted(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_creation_input_tokens


class TimelineItem(_Model):
    """One step of a run, in order: assistant text, a tool call and its result, or an error."""

    type: Literal["text", "tool_call", "error"]
    at: datetime = Field(default_factory=utcnow)
    text: str = ""
    tool: str | None = None
    tool_id: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)
    ok: bool | None = None
    result: str = Field("", description="Short summary of the tool result (full results aren't kept).")


class RunSource(_Model):
    url: str
    title: str = ""
    observation_id: str | None = None
    at: datetime = Field(default_factory=utcnow)


class AgentRun(_File):
    id: str = Field(default_factory=lambda: new_id("run"))
    kind: Literal["chat", "manual", "scheduled"]
    mission: str | None = Field(None, description="For scheduled runs: which mission.")
    rule_check: RuleCheck | None = Field(None, description="Rule claims in the final answer, checked.")
    status: Literal["running", "done", "error", "stopped"] = "running"
    engine: str
    model: str
    task: str | None = Field(
        None, description="What the run was for (ADR 0009 routing), e.g. chat, chat_extract."
    )
    tier: Literal["hard", "mid", "mundane"] | None = None
    provider: Literal["anthropic", "openai"] | None = None
    prompt: str
    conversation_id: str | None = None
    started_at: datetime = Field(default_factory=utcnow)
    finished_at: datetime | None = None
    text: str = Field("", description="The assistant's final answer.")
    timeline: list[TimelineItem] = Field(default_factory=list)
    sources: list[RunSource] = Field(default_factory=list)
    proposals: list[str] = Field(default_factory=list, description="Inbox candidate ids this run proposed.")
    changes: list[str] = Field(default_factory=list, description="data/changes.jsonl ids this run made.")
    usage: RunUsage = Field(default_factory=RunUsage)
    cost_usd: float | None = None
    stop_reason: str | None = None
    error: str | None = None


class ConversationMessage(_Model):
    role: Literal["user", "assistant"]
    text: str
    at: datetime = Field(default_factory=utcnow)
    run_id: str | None = None


class Conversation(_File):
    id: str = Field(default_factory=lambda: new_id("conv"))
    title: str = ""
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)
    messages: list[ConversationMessage] = Field(default_factory=list)
    summary: str = Field("", description="Older turns, summarized on the mundane tier (ADR 0009 §3). The "
                         "originals stay in messages.")  # fmt: skip
    summarized: int = Field(0, ge=0, description="How many of the first messages the summary covers.")


# --------------------------------------------------------------------------- memory/ (section 5b)
#
# Append-only JSONL: memory/observations.jsonl, claims.jsonl, edges.jsonl, decisions.jsonl,
# entities.jsonl, plus raw snapshots in memory/sources/<sha256>.<ext>. Nothing is overwritten;
# a newer claim SUPERSEDES an older one. A SQLite index in .areao1/cache/ is rebuilt from these.

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
    tier: SourceTier | None = None
    filename: str | None = Field(None, description="Original file name, for uploads and imported exports.")


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
    recorded_at: datetime = Field(default_factory=utcnow, description="When Area O1 learned it.")
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
    tier: SourceTier | None = None
    filename: str | None = None
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
