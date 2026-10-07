"""Domain-layer models: criteria profiles, the computed scoreboard, and case-specific files
(person.json, letters.json). The core never imports this module."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from areao1.core.models import Slug, _File, _Model, new_id, slugify, utcnow

DEFAULT_PROFILE = "o1a"

# --------------------------------------------------------------------------- person.json


class FilingTarget(_Model):
    profile: str = DEFAULT_PROFILE
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


# --------------------------------------------------------------------------- criteria.json


CriterionState = Literal["banked", "building", "gap", "dropped"]


class CriterionScore(_Model):
    id: str
    label: str
    short_label: str = Field(
        "", description="One or two words for tight places; the label is shown on hover."
    )
    status: CriterionState
    exhibit_count: int = 0
    exhibit_ids: list[str] = Field(default_factory=list)
    matched_signals: list[str] = Field(default_factory=list)
    missing_signals: list[str] = Field(default_factory=list)
    needed_exhibits: int = Field(0, description="Exhibits still needed to reach 'banked'.")
    in_progress_count: int = Field(
        0, description="Exhibits not counted yet because their stage isn't completed."
    )
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
    rules_digest: str = Field(
        "", description="Digest of the profile it was scored with; a profile edit rescores."
    )
    reviewer_note: str | None = Field(
        None, description="Agent-written 'how a reviewer would see this' note. Opinion, not a rule result."
    )


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


class Todo(_Model):
    """A next step from something the person told Area O1 (onboarding, chat): "Upload proof of HackSeattle 2025
    judging". Self-reported, so it never counts toward a criterion; the proof it asks for does, once accepted."""

    id: str
    title: str
    kind: Literal["award", "judging", "publication", "membership"]
    item: str = Field(description="What the person said, as they confirmed it.")
    criterion: str | None = None
    tier: Literal["self_reported"] = "self_reported"
    source: str = "onboarding"
    status: Literal["open", "done", "dismissed"] = "open"
    created: date
    closed: date | None = None


class Todos(_File):
    todos: list[Todo] = Field(default_factory=list)


RELATIONSHIPS = ("recommender", "collaborator", "organizer", "editor", "mentor", "employer", "other")


class Contact(_Model):
    """Someone your case runs through (ADR 0014 §4): a letter writer, an organizer, an editor. Tracking only: a
    contact never counts toward a criterion."""

    id: str = Field(default_factory=lambda: new_id("con"))
    name: str = Field(min_length=1, max_length=120)
    emails: list[str] = Field(default_factory=list)
    org: str = ""
    relationship: Literal[
        "recommender", "collaborator", "organizer", "editor", "mentor", "employer", "other"
    ] = "other"
    notes: str = ""
    asks: list[str] = Field(default_factory=list, description="What you've asked of them, in your words.")
    next_follow_up: date | None = None
    last_touch: date | None = Field(
        None, description="Set by hand, or from the newest Gmail thread with them."
    )
    letter_ids: list[str] = Field(default_factory=list)
    pipeline_ids: list[str] = Field(default_factory=list)
    tier: Literal["self_reported"] = "self_reported"

    @field_validator("emails")
    @classmethod
    def _emails(cls, v: list[str]) -> list[str]:
        out = []
        for e in v:
            e = e.strip().lower()
            if e and e not in out:
                if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", e):
                    raise ValueError(f"{e!r} isn't an email address")
                out.append(e)
        return out


class Contacts(_File):
    contacts: list[Contact] = Field(default_factory=list)


class GmailThread(_Model):
    """A Gmail thread with at least one of your contacts (ADR 0014 §2). No bodies, no attachments: who, when, the
    subject and one redacted line."""

    id: str
    subject: str = ""
    contact_ids: list[str] = Field(default_factory=list)
    last_at: datetime
    last_from: Literal["you", "them"]
    snippet: str = Field("", max_length=200)
    messages: int = Field(1, ge=1)
    last_message_id: str | None = Field(
        None,
        max_length=998,
        description="The last message's Message-ID, so a follow-up replies in the thread.",
    )


class OutreachDraft(_Model):
    """An email to a contact (ADR 0014 §5). It never sends itself: you approve, edit or reject it."""

    id: str = Field(default_factory=lambda: new_id("out"))
    contact_id: str
    to: str
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    purpose: Literal["ask", "thank_you", "follow_up", "update", "other"] = "other"
    status: Literal["draft", "sent", "rejected"] = "draft"
    drafted_by: str = Field(
        "user", description="'user', 'agent:<run>', or 'follow-up' (the 7-quiet-days job)."
    )
    thread_id: str | None = Field(None, description="The Gmail thread a follow-up continues.")
    created_at: datetime = Field(default_factory=utcnow)
    sent_at: datetime | None = None
    gmail_id: str | None = None


class Outreach(_File):
    drafts: list[OutreachDraft] = Field(default_factory=list)


class CalendarLink(_Model):
    event_id: str
    pushed: str = Field(
        description="What the event held when last synced (title|due), to spot either side's edits."
    )
    synced_at: datetime


class CalendarSync(_File):
    """The dedicated Google calendar's sync state (ADR 0014 §3): which event holds which deadline."""

    calendar_id: str | None = None
    sync_token: str | None = None
    links: dict[str, CalendarLink] = Field(default_factory=dict, description="deadline id -> its event")


class GmailThreads(_File):
    threads: list[GmailThread] = Field(default_factory=list)
    synced_at: datetime | None = None


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
    short_label: str = Field(
        "", description='One or two words for tight places ("Awards"); falls back to label.'
    )
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
