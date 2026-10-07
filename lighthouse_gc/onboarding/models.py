"""data/onboarding.json: where onboarding stands, so it can be resumed and re-run."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from lighthouse_gc.core.models import _File, _Model

Step = Literal["linkedin", "questions", "lookups", "chats", "tour", "done"]
FieldStatus = Literal["pending", "confirmed", "fixed", "skipped"]


class ProfileField(_Model):
    key: str
    label: str
    value: str | list[str] = ""
    quote: str = Field("", description="The words in the (redacted) PDF text the value was read from.")
    status: FieldStatus = "pending"


class LinkedInSource(_Model):
    filename: str = ""
    sha256: str = Field(
        "", description="Of the uploaded PDF. The PDF itself isn't kept; only its redacted text."
    )
    observation_id: str | None = None
    chars: int = 0
    redactions: int = Field(0, description="Emails and phone numbers removed before any model saw the text.")
    parser: Literal["linkedin", "model", "none"] = "none"


class Turn(_Model):
    """One line of the onboarding conversation, kept so a resumed onboarding reads the same."""

    who: Literal["lighthouse", "you"]
    text: str


class Lookup(_Model):
    id: str
    kind: Literal["papers", "github", "orcid", "website", "find"]
    prompt: str
    targets: list[str] = Field(default_factory=list)
    status: Literal["offered", "accepted", "declined", "done", "failed"] = "offered"
    result: str = ""
    todo_id: str | None = Field(None, description="find: the to-do this lookup looks for proof of.")
    run_id: str | None = Field(None, description="find: the agent run doing the search.")


class OnboardingState(_File):
    status: Literal["new", "in_progress", "done", "skipped"] = "new"
    step: Step = "linkedin"
    source: LinkedInSource | None = None
    fields: list[ProfileField] = Field(default_factory=list)
    target_profile: str | None = None
    target_date: str | None = Field(None, description="YYYY-MM the person hopes to file, or 'skipped'.")
    lookups: list[Lookup] = Field(default_factory=list)
    transcript: list[Turn] = Field(default_factory=list)
    chats: Literal["pending", "imported", "skipped"] = "pending"
    tour: Literal["pending", "seen", "skipped"] = "pending"
    started_at: datetime | None = None
    finished_at: datetime | None = None

    def field(self, key: str) -> ProfileField | None:
        return next((f for f in self.fields if f.key == key), None)
