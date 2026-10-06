"""Domain-layer models: criteria profiles, the computed scoreboard, and case-specific files
(person.json, letters.json). The core never imports this module."""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import Field, field_validator

from lighthouse_gc.core.models import Slug, _File, _Model, new_id, slugify, utcnow

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
