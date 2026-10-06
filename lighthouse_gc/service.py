"""The service layer: the one door every user- or agent-initiated write goes through.

The dashboard API and (from Phase 1c) the agent's write tools call these methods; nothing else may write
Inbox, Pipeline, Letters, Calendar or Evidence state on their behalf (``tests/test_service_layer.py``
enforces it). Each call:

* runs inside a guard context (:func:`in_service`), which the test uses to catch writes from elsewhere, and
* appends a :class:`~lighthouse_gc.core.models.Change` to ``data/changes.jsonl``: who (``user`` or
  ``agent:<run>``), what, and the record's state before and after, for review and undo.

Connector syncs and scheduled jobs are system processes with their own audit trail (``memory/``) and
don't go through here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date
from typing import Any, TypeVar

from pydantic import BaseModel

from lighthouse_gc.core.models import Candidate, Change, Exhibit
from lighthouse_gc.core.workspace import NotFound
from lighthouse_gc.criteria.case import Case

T = TypeVar("T")
_ACTIVE: ContextVar[str | None] = ContextVar("lighthouse_service_call", default=None)


def in_service() -> bool:
    """True while a service method is running (used by the write-path guard test)."""
    return _ACTIVE.get() is not None


def _dump(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return dict(value)


class Service:
    def __init__(self, ws: Case, actor: str = "user"):
        self.ws = ws
        self.actor = actor

    @contextmanager
    def _guard(self, action: str) -> Iterator[None]:
        token = _ACTIVE.set(action)
        try:
            yield
        finally:
            _ACTIVE.reset(token)

    def _record(
        self,
        action: str,
        target_type: str,
        fn: Callable[[], T],
        *,
        target_id: str | None = None,
        before: Any = None,
        summary: str = "",
    ) -> T:
        with self._guard(action):
            result = fn()
            after = None if action.endswith(".delete") else _dump(result)
            if target_id is None and isinstance(after, dict):
                target_id = after.get("id")
            self.ws.append_change(
                Change(
                    actor=self.actor,
                    action=action,
                    target_type=target_type,
                    target_id=target_id,
                    summary=summary,
                    before=_dump(before),
                    after=after,
                )  # fmt: skip
            )
            return result

    def changes(self, limit: int | None = None) -> list[Change]:
        out = self.ws.changes()
        return out[-limit:] if limit else out

    # ------------------------------------------------------------------ helpers

    def _candidate(self, candidate_id: str) -> Candidate:
        cand = next((c for c in self.ws.inbox().candidates if c.id == candidate_id), None)
        if cand is None:
            raise NotFound(f"no candidate {candidate_id!r}")
        return cand

    @staticmethod
    def _find(items: list[Any], item_id: str, what: str) -> Any:
        found = next((i for i in items if i.id == item_id), None)
        if found is None:
            raise NotFound(f"no {what} {item_id!r}")
        return found

    # ------------------------------------------------------------------ inbox

    def edit_candidate(self, candidate_id: str, **changes: Any) -> Candidate:
        before = self._candidate(candidate_id)
        return self._record("inbox.edit", "candidate", lambda: self.ws.edit_candidate(candidate_id, **changes),
                            target_id=candidate_id, before=before, summary=before.title)  # fmt: skip

    def accept_candidate(self, candidate_id: str, **edits: Any) -> Any:
        before = self._candidate(candidate_id)
        return self._record("inbox.accept", before.kind, lambda: self.ws.accept_candidate(candidate_id, **edits),
                            before=before, summary=before.title)  # fmt: skip

    def reject_candidate(self, candidate_id: str) -> Candidate:
        before = self._candidate(candidate_id)
        return self._record("inbox.reject", "candidate", lambda: self.ws.reject_candidate(candidate_id),
                            target_id=candidate_id, before=before, summary=before.title)  # fmt: skip

    def snooze_candidate(self, candidate_id: str, until: date | None = None) -> Candidate:
        before = self._candidate(candidate_id)
        return self._record("inbox.snooze", "candidate", lambda: self.ws.snooze_candidate(candidate_id, until),
                            target_id=candidate_id, before=before, summary=before.title)  # fmt: skip

    def stage_upload(self, content: bytes, filename: str, criterion: str | None = None) -> Candidate:
        return self._record("inbox.upload", "candidate", lambda: self.ws.stage_upload(content, filename, criterion),
                            summary=filename)  # fmt: skip

    def propose_candidate(self, cand: Candidate) -> Candidate | None:
        """Put a proposal in the Inbox (e.g. from the agent). Returns None if it duplicates an existing one."""

        def add() -> Candidate | None:
            added = self.ws.add_candidates([cand])
            if added:
                self.ws.after_change()
            return added[0] if added else None

        return self._record("inbox.propose", cand.kind, add, target_id=cand.id, summary=cand.title)

    # ------------------------------------------------------------------ evidence + scoring

    def add_exhibit_file(self, **kwargs: Any) -> Exhibit:
        return self._record("evidence.upload", "exhibit", lambda: self.ws.add_exhibit_file(**kwargs),
                            summary=str(kwargs.get("title", "")))  # fmt: skip

    def remap_exhibit(self, exhibit_id: str, criterion: str, evidence_type: str | None = None) -> Exhibit:
        before = self._find(self.ws.exhibits().exhibits, exhibit_id, "exhibit")
        return self._record("evidence.remap", "exhibit",
                            lambda: self.ws.remap_exhibit(exhibit_id, criterion, evidence_type),
                            before=before, summary=f"{before.title} -> {criterion}")  # fmt: skip

    def set_profile(self, profile_id: str) -> Any:
        before = {"profile": self.ws.profile_id()}
        return self._record("profile.set", "profile", lambda: self.ws.set_profile(profile_id),
                            target_id=profile_id, before=before, summary=profile_id)  # fmt: skip

    def set_override(self, criterion_id: str, status: str | None) -> Any:
        before = {"status": self.ws.config().overrides.get(self.ws.profile_id(), {}).get(criterion_id)}
        return self._record("criterion.override", "criterion", lambda: self.ws.set_override(criterion_id, status),
                            target_id=criterion_id, before=before, summary=f"{criterion_id}: {status}")  # fmt: skip

    # ------------------------------------------------------------------ calendar

    def add_deadline(self, **fields: Any) -> Any:
        return self._record("deadline.add", "deadline", lambda: self.ws.add_deadline(**fields),
                            summary=str(fields.get("title", "")))  # fmt: skip

    def update_deadline(self, deadline_id: str, **changes: Any) -> Any:
        before = self._find(self.ws.deadlines().deadlines, deadline_id, "deadline")
        return self._record("deadline.update", "deadline", lambda: self.ws.update_deadline(deadline_id, **changes),
                            before=before, summary=before.title)  # fmt: skip

    def delete_deadline(self, deadline_id: str) -> None:
        before = self._find(self.ws.deadlines().deadlines, deadline_id, "deadline")
        self._record("deadline.delete", "deadline", lambda: self.ws.delete_deadline(deadline_id),
                     target_id=deadline_id, before=before, summary=before.title)  # fmt: skip

    # ------------------------------------------------------------------ pipeline

    def add_pipeline_item(self, **fields: Any) -> Any:
        return self._record("pipeline.add", "pipeline_item", lambda: self.ws.add_pipeline_item(**fields),
                            summary=str(fields.get("title", "")))  # fmt: skip

    def update_pipeline_item(self, item_id: str, **changes: Any) -> Any:
        before = self._find(self.ws.pipeline().items, item_id, "pipeline item")
        action = "pipeline.move" if changes.get("stage") not in (None, before.stage) else "pipeline.update"
        return self._record(action, "pipeline_item", lambda: self.ws.update_pipeline_item(item_id, **changes),
                            before=before, summary=before.title)  # fmt: skip

    def delete_pipeline_item(self, item_id: str) -> None:
        before = self._find(self.ws.pipeline().items, item_id, "pipeline item")
        self._record("pipeline.delete", "pipeline_item", lambda: self.ws.delete_pipeline_item(item_id),
                     target_id=item_id, before=before, summary=before.title)  # fmt: skip

    # ------------------------------------------------------------------ letters

    def add_letter(self, **fields: Any) -> Any:
        return self._record("letter.add", "letter", lambda: self.ws.add_letter(**fields),
                            summary=str(fields.get("name", "")))  # fmt: skip

    def update_letter(self, letter_id: str, **changes: Any) -> Any:
        before = self._find(self.ws.letters().letters, letter_id, "letter writer")
        return self._record("letter.update", "letter", lambda: self.ws.update_letter(letter_id, **changes),
                            before=before, summary=before.name)  # fmt: skip

    def delete_letter(self, letter_id: str) -> None:
        before = self._find(self.ws.letters().letters, letter_id, "letter writer")
        self._record("letter.delete", "letter", lambda: self.ws.delete_letter(letter_id),
                     target_id=letter_id, before=before, summary=before.name)  # fmt: skip
