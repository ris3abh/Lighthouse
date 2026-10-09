"""Domain-layer models: criteria profiles, the computed scoreboard, and case-specific files
(person.json, letters.json). The core never imports this module."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, Literal

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
    status: Literal["draft", "queued", "sent", "rejected"] = Field(
        "draft", description="queued: approved, waiting out the undo window before it's sent."
    )
    drafted_by: str = Field(
        "user", description="'user', 'agent:<run>', or 'follow-up' (the 7-quiet-days job)."
    )
    thread_id: str | None = Field(None, description="The Gmail thread a follow-up continues.")
    created_at: datetime = Field(default_factory=utcnow)
    queued_at: datetime | None = None
    sent_at: datetime | None = None
    gmail_id: str | None = None


class SendAttempt(_Model):
    """One try at sending an approved email, whether Gmail took it or not. The daily limit counts the ones that
    went out; failures show on the Contacts page."""

    at: datetime = Field(default_factory=utcnow)
    draft_id: str
    to: str
    subject: str = Field("", max_length=200)
    ok: bool
    error: str = Field("", max_length=500)
    message_id: str | None = Field(None, max_length=998)


class Outreach(_File):
    drafts: list[OutreachDraft] = Field(default_factory=list)
    attempts: list[SendAttempt] = Field(default_factory=list)


class GmailThreads(_File):
    threads: list[GmailThread] = Field(default_factory=list)
    synced_at: datetime | None = None


MailCategory = Literal["invites", "judging", "reviewer", "letters", "press", "awards", "contacts"]


class MailItem(_Model):
    """One case-relevant message in the Mail view: who, when, the redacted subject and its category. No body: the
    text is fetched when you open it and never kept. Mail outside the categories is never stored at all."""

    id: str = Field(description="Gmail's message ID (X-GM-MSGID).")
    thread_id: str
    at: datetime
    from_name: str = Field("", max_length=200)
    from_addr: str = Field("", max_length=320)
    to: list[str] = Field(default_factory=list)
    subject: str = Field("", max_length=200)
    outgoing: bool = False
    category: MailCategory
    by: Literal["rule", "learned", "model", "you"] = "rule"
    why: str = Field("", max_length=200, description="Which rule (or the model, or your move) put it here.")
    contact_ids: list[str] = Field(default_factory=list)
    source: Literal["gmail", "eml"] = "gmail"
    auth: dict[str, str | bool | None] | None = Field(
        None,
        description="Sender authentication from the original headers (verdict, spf, dkim, dmarc, by, ...).",
    )
    forwarded_part: str | None = Field(None, description="The attached original's MIME part, for a message "
                                       "forwarded as an attachment; sender, subject and auth are the original's.")  # fmt: skip
    file_sha: str | None = Field(None, description="For a dropped .eml: its snapshot in memory/sources.")


class MailRule(_Model):
    """Taught by moving a message: mail from this sender goes to this category (or is never shown: 'hide')."""

    sender: str = Field(min_length=3, max_length=320)
    category: MailCategory | Literal["hide"]
    at: datetime = Field(default_factory=utcnow)


class Mailbox(_File):
    items: list[MailItem] = Field(default_factory=list)
    rules: list[MailRule] = Field(default_factory=list)
    seen: list[str] = Field(default_factory=list, description="Hashes of message IDs already classified, so "
                            "nothing is read twice. Not the messages: one-way hashes.")  # fmt: skip
    unsorted: int = Field(0, ge=0, description="New mail no rule sorted at the last refresh (not kept).")
    processed: list[str] = Field(default_factory=list, description="Mail the daily opportunity job already "
                                 "looked at (message ids), so a find is proposed once.")  # fmt: skip
    synced_at: datetime | None = None


# --------------------------------------------------------------------------- proof recipes (ADR 0017)


class RecipeMatch(_Model):
    """How an exhibit or a message is recognized as this proof item: any listed evidence type or stage, or (for
    mail and source items, and for suggesting existing exhibits) a keyword phrase in its title or subject."""

    evidence_types: list[Slug] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list, description="Lowercase phrases.")


class RecipeItem(_Model):
    id: Slug
    label: str
    why: str = ""
    optional: bool = Field(False, description='"If available": never counted as missing.')
    match: RecipeMatch = Field(default_factory=RecipeMatch)


class Recipe(_Model):
    """profiles/recipes/<criterion>.yaml: the proof to preserve once an activity is accepted, completed, granted or
    published. Community-edited advice, not a legal requirement."""

    criterion: Slug
    label: str
    applies_to: list[Slug] = Field(
        default_factory=list,
        description="Evidence types this recipe is for; empty means all of the criterion's.",
    )
    items: list[RecipeItem]


class ProofLink(_Model):
    anchor: str = Field(description="The activity: exhibit:<id>, pipeline:<id> or claim:<id>.")
    item: Slug
    status: Literal["linked", "waived"] = "linked"
    exhibit_id: str | None = Field(None, description="The exhibit that preserves this item.")
    note: str = Field("", max_length=300, description="Why it doesn't apply, for a waived item.")
    at: datetime


class ProofLinks(_File):
    links: list[ProofLink] = Field(default_factory=list)


# --------------------------------------------------------------------------- preflight (ADR 0018)


class PreflightIssue(_Model):
    id: str = Field(description="Stable: a hash of the kind and the records involved, so a dismissal sticks.")
    kind: str
    severity: Literal["high", "medium", "low"] = Field(
        description="How likely a reader is to notice; never odds."
    )
    title: str
    detail: str = ""
    refs: list[dict[str, Any]] = Field(
        default_factory=list, description="The claims, exhibits, letters, drafts."
    )
    dismissed: bool = False
    dismissed_note: str = ""


class PreflightReport(_File):
    run_at: datetime | None = None
    issues: list[PreflightIssue] = Field(default_factory=list)
    dismissed: dict[str, dict[str, str]] = Field(default_factory=dict, description="issue id -> {note, at}")
    counts: dict[str, int] = Field(default_factory=dict, description="Open issues by severity.")
    by_kind: dict[str, int] = Field(default_factory=dict)
    exhibits: int = 0
    claims: int = 0


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


MeritsRule = Literal["independent_letters", "outside_employer", "years", "peer_context", "adoption"]


class MeritsTheme(_Model):
    """One theme of the final-merits view (ADR 0019) and the visible rule that sets its status."""

    id: Slug
    label: str
    rule: MeritsRule
    description: str = ""
    strong: int = Field(1, ge=1, description="The count at which the theme is strong.")
    building: int = Field(1, ge=1, description="The count at which it is building.")
    strong_share: float | None = Field(
        None, ge=0, le=1, description="independent_letters: share of writers too."
    )
    signals: list[str] = Field(
        default_factory=list, description="Strength signals that count for this theme."
    )
    evidence_types: list[str] = Field(default_factory=list)
    criteria: list[str] = Field(
        default_factory=list, description="Criteria whose exhibits count for this theme."
    )


class MeritsCitation(_Model):
    """A passage of the standard, quoted word for word from a vault source, with where it is in that source."""

    quote: str = Field(description="A whole sentence, exactly as the source has it.")
    source_id: str
    section: str = Field("", description='Where in the source, e.g. "USCIS Policy Manual, Vol. 6, Part F, Ch. 2, '
                         'Sec. B".')  # fmt: skip
    text: str = Field("", description="Optional plain-language lead shown before the quote.")


class FinalMeritsRules(_Model):
    label: str
    framing: str = ""
    themes: list[MeritsTheme] = Field(default_factory=list)
    standard: list[MeritsCitation] = Field(default_factory=list)


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
    final_merits: FinalMeritsRules | None = Field(
        None, description="The final-merits view's themes and rules."
    )

    def criterion(self, criterion_id: str) -> ProfileCriterion | None:
        return next((c for c in self.criteria if c.id == criterion_id), None)
