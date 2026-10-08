"""The service layer: the one door every user- or agent-initiated write goes through.

The dashboard API and (from Phase 1c) the agent's write tools call these methods; nothing else may write
Inbox, Pipeline, Letters, Calendar or Evidence state on their behalf (``tests/test_service_layer.py``
enforces it). Each call:

* runs inside a guard context (:func:`in_service`), which the test uses to catch writes from elsewhere, and
* appends a :class:`~areao1.core.models.Change` to ``data/changes.jsonl``: who (``user`` or
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

from areao1.agent.autopilot import AUTO_ACTIONS, AutopilotRefused
from areao1.core import clock
from areao1.core.models import Briefing, Candidate, Change, Evidence, Exhibit, MetricRow
from areao1.core.text import plural
from areao1.core.workspace import NotFound, WorkspaceError
from areao1.criteria.case import Case

T = TypeVar("T")
MAX_CONTEXT_CHARS = 4000
_ACTIVE: ContextVar[str | None] = ContextVar("areao1_service_call", default=None)


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
    """``auto=True`` is the autopilot service: it may only perform the actions in
    :data:`areao1.agent.autopilot.AUTO_ACTIONS` and refuses everything else."""

    def __init__(self, ws: Case, actor: str = "user", *, auto: bool = False):
        self.ws = ws
        self.actor = actor
        self.auto = auto

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
        undoes: str | None = None,
    ) -> T:
        if self.auto and action not in AUTO_ACTIONS:
            raise AutopilotRefused(f"autopilot can't {action}; it needs the user's approval")
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
                    auto=self.auto,
                    undoes=undoes,
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
        if not any(edits.get(k) is not None for k in self.ws.TEXT_FIELDS):
            self._rule_gate(before)
        return self._record("inbox.accept", before.kind, lambda: self.ws.accept_candidate(candidate_id, **edits),
                            before=before, summary=before.title)  # fmt: skip

    def _rule_gate(self, cand: Candidate) -> None:
        """Unverified rule claims can't enter exhibits or letters (SPEC 5a). Freshness is re-evaluated now, so a
        claim whose source changed or went stale since it was proposed blocks too."""
        if cand.rule_check is None:
            return
        from areao1.vault import Vault
        from areao1.vault.rulecheck import refresh

        check = refresh(cand.rule_check, Vault(self.ws))
        if check is not None and check.blocking:
            items = "; ".join(f'"{c.sentence[:120]}" ({c.status})' for c in check.blocking[:3])
            raise WorkspaceError(f"This suggestion states rules the knowledge vault doesn't confirm: {items}. "
                                 "Re-check it, or edit the text into your own words first.")  # fmt: skip

    def set_rule_check(self, candidate_id: str, check: Any) -> Candidate:
        before = self._candidate(candidate_id)

        def apply() -> Candidate:
            with self.ws.lock:
                inbox = self.ws.inbox()
                cand = next(c for c in inbox.candidates if c.id == candidate_id)
                cand.rule_check = check
                self.ws.save_inbox(inbox)
                return cand

        return self._record("inbox.recheck", "candidate", apply, target_id=candidate_id, before=before,
                            summary=f"rule-check: {before.title}")  # fmt: skip

    def set_briefing_check(self, check: Any) -> Any:
        before = self.ws.briefing()

        def apply() -> Any:
            b = self.ws.briefing()
            b.rule_check = check
            self.ws.save_briefing(b)
            return b

        return self._record("briefing.recheck", "briefing", apply, target_id="overview", before=before,
                            summary="rule-check")  # fmt: skip

    def reject_candidate(self, candidate_id: str) -> Candidate:
        before = self._candidate(candidate_id)
        return self._record("inbox.reject", "candidate", lambda: self.ws.reject_candidate(candidate_id),
                            target_id=candidate_id, before=before, summary=before.title)  # fmt: skip

    def snooze_candidate(self, candidate_id: str, until: date | None = None) -> Candidate:
        before = self._candidate(candidate_id)
        return self._record("inbox.snooze", "candidate", lambda: self.ws.snooze_candidate(candidate_id, until),
                            target_id=candidate_id, before=before, summary=before.title)  # fmt: skip

    def set_verification(self, candidate_id: str, verification: str, note: str) -> Candidate:
        """An opportunity find's verification changed (ADR 0016), e.g. the organizer replied to the check-in."""
        before = self._candidate(candidate_id)
        return self._record("inbox.verify", "candidate",
                            lambda: self.ws.set_verification(candidate_id, verification, note),
                            target_id=candidate_id, before=before, summary=f"{before.title}: {verification}")  # fmt: skip

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

    def propose_context(
        self, text: str, title: str = "", client: str = "", topic: str = ""
    ) -> Candidate | None:
        """Context an AI tool sends over MCP (C3): an Inbox note, tier self_reported. Accepting it keeps it as a
        self-reported observation; it can never become evidence or count toward a criterion."""
        import hashlib

        text = text.strip()
        if not text:
            raise WorkspaceError("send some context")
        if len(text) > MAX_CONTEXT_CHARS:
            raise WorkspaceError(f"context is limited to {MAX_CONTEXT_CHARS:,} characters; send a summary")
        digest = hashlib.sha256(text.encode()).hexdigest()[:16]
        who = (client or "an AI tool").strip()[:60]
        cand = Candidate(kind="context", fingerprint=f"context:{digest}", source=f"mcp:{who}", evidence_type="context_note",
                         proposed_criterion="", title=(title.strip() or text.splitlines()[0])[:120], source_tier="self_reported",
                         summary=text[:600], proposal={"id": digest, "text": text, "client": who, "topic": topic[:80]},
                         confidence=0.3)  # fmt: skip
        return self.propose_candidate(cand)

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

    # ------------------------------------------------------------------ contacts (ADR 0014 §4)

    def add_contact(self, **fields: Any) -> Any:
        return self._record("contact.add", "contact", lambda: self.ws.add_contact(**fields),
                            summary=str(fields.get("name", "")))  # fmt: skip

    def update_contact(self, contact_id: str, **changes: Any) -> Any:
        before = self._find(self.ws.contacts().contacts, contact_id, "contact")
        return self._record("contact.update", "contact", lambda: self.ws.update_contact(contact_id, **changes),
                            before=before, summary=before.name)  # fmt: skip

    def delete_contact(self, contact_id: str) -> None:
        before = self._find(self.ws.contacts().contacts, contact_id, "contact")
        self._record("contact.delete", "contact", lambda: self.ws.delete_contact(contact_id),
                     target_id=contact_id, before=before, summary=before.name)  # fmt: skip

    # ------------------------------------------------------------------ outreach (ADR 0014 §5)

    def _draft(self, draft_id: str) -> Any:
        return self._find(self.ws.outreach().drafts, draft_id, "email draft")

    def save_draft(self, draft: Any) -> Any:
        return self._record("outreach.draft", "outreach", lambda: self.ws.put_draft(draft),
                            summary=f"to {draft.to}: {draft.subject}")  # fmt: skip

    def edit_draft(self, draft_id: str, **changes: Any) -> Any:
        before = self._draft(draft_id)
        if before.status != "draft":
            raise WorkspaceError(f"this email is already {before.status}")
        bad = set(changes) - {"subject", "body"}
        if bad:
            raise WorkspaceError(f"not editable: {', '.join(sorted(bad))}")
        updated = before.model_copy(update={k: str(v) for k, v in changes.items()})
        type(before).model_validate(updated.model_dump())
        return self._record("outreach.edit", "outreach", lambda: self.ws.put_draft(updated), before=before,
                            summary=f"to {before.to}: {updated.subject}")  # fmt: skip

    def reject_draft(self, draft_id: str) -> Any:
        before = self._draft(draft_id)
        if before.status != "draft":
            raise WorkspaceError(f"this email is already {before.status}")
        return self._record("outreach.reject", "outreach",
                            lambda: self.ws.put_draft(before.model_copy(update={"status": "rejected"})),
                            before=before, summary=f"to {before.to}: {before.subject}")  # fmt: skip

    def _user_only(self) -> None:
        if self.auto or self.actor != "user":
            raise WorkspaceError("only you can approve and send an email")

    def approve_draft(self, draft_id: str) -> Any:
        """Your approval (Approve & send): the email waits out the undo window, then deliver_draft sends it. Every
        rule is checked now too, so a refusal shows at once. Agents and autopilot can't approve."""
        self._user_only()
        from areao1.google import outreach

        with outreach.SENDING:
            before = self._draft(draft_id)
            if before.status != "draft":
                raise WorkspaceError(f"this email is already {before.status}")
            outreach.check(self.ws, before)
            after = before.model_copy(update={"status": "queued", "queued_at": clock.utcnow()})
            return self._record("outreach.approve", "outreach", lambda: self.ws.put_draft(after), before=before,
                                summary=f"to {before.to}: {before.subject}")  # fmt: skip

    def undo_send(self, draft_id: str) -> Any:
        """Undo send, within the window: the email goes back to being a draft and nothing leaves."""
        self._user_only()
        from areao1.google import outreach

        with outreach.SENDING:
            before = self._draft(draft_id)
            if before.status != "queued":
                raise WorkspaceError("too late to undo: it's already sent" if before.status == "sent"
                                     else f"this email is {before.status}, not waiting to send")  # fmt: skip
            after = before.model_copy(update={"status": "draft", "queued_at": None})
            return self._record("outreach.undo", "outreach", lambda: self.ws.put_draft(after), before=before,
                                summary=f"to {before.to}: {before.subject}")  # fmt: skip

    def deliver_draft(self, draft_id: str) -> Any:
        """Send an approved email once its undo window is over. Nothing happens if it was undone meanwhile. If Gmail
        refuses, it goes back to being a draft (the failure is logged) and the error is raised."""
        from areao1.google import outreach

        with outreach.SENDING:  # one at a time, read fresh: approving twice sends once
            before = self._draft(draft_id)
            if before.status != "queued":
                return None
            try:
                sent = outreach.send(self.ws, before)
            except WorkspaceError:
                back = before.model_copy(update={"status": "draft", "queued_at": None})
                self._record("outreach.send_failed", "outreach", lambda: self.ws.put_draft(back), before=before,
                             summary=f"to {before.to}: {before.subject}")  # fmt: skip
                raise
            after = before.model_copy(update={"status": "sent", "sent_at": clock.utcnow(), "gmail_id": sent.get("id"),
                                              "thread_id": sent.get("threadId") or before.thread_id})  # fmt: skip
            return self._record("outreach.send", "outreach", lambda: self.ws.put_draft(after), before=before,
                                summary=f"to {before.to}: {before.subject}")  # fmt: skip

    def send_draft(self, draft_id: str) -> Any:
        """Approve and send at once, with no undo window (the CLI and tests). Agents and autopilot can't."""
        self.approve_draft(draft_id)
        return self.deliver_draft(draft_id)

    # ------------------------------------------------------------------ trackers (generic) + metrics

    def update_tracker(self, target_type: str, target_id: str, **changes: Any) -> Any:
        if target_type == "pipeline_item":
            return self.update_pipeline_item(target_id, **changes)
        if target_type == "letter":
            return self.update_letter(target_id, **changes)
        if target_type == "deadline":
            return self.update_deadline(target_id, **changes)
        raise WorkspaceError(f"can't update {target_type!r}")

    def record_metric(self, row: MetricRow, evidence: Evidence | None = None) -> MetricRow:
        key = (row.date, row.source, row.item, row.metric)
        before = next((r for r in self.ws.metrics() if (r.date, r.source, r.item, r.metric) == key), None)
        if evidence is not None:
            row = row.with_evidence(evidence)

        def apply() -> MetricRow:
            self.ws.append_metrics([row])
            self.ws.after_change()
            return row

        return self._record("metrics.record", "metric", apply, target_id=f"{row.source}/{row.item}/{row.metric}",
                            before=before, summary=f"{row.item} {row.metric} = {row.value:g} ({row.date})")  # fmt: skip

    # ------------------------------------------------------------------ briefing

    def publish_briefing(self, briefing: Briefing) -> Briefing:
        before = self.ws.briefing()

        def apply() -> Briefing:
            self.ws.save_briefing(briefing)
            return briefing

        return self._record("briefing.publish", "briefing", apply, target_id="overview", before=before,
                            summary=f"{plural(len(briefing.changed), 'change')}, {plural(len(briefing.todos), 'to-do')}")  # fmt: skip

    # ------------------------------------------------------------------ settings

    def set_autopilot(self, **flags: bool) -> Any:
        if self.auto:
            raise AutopilotRefused("autopilot can't change its own settings")
        cfg = self.ws.config()
        before = cfg.agent.autopilot.model_dump()

        def apply() -> Any:
            cfg.agent.autopilot = cfg.agent.autopilot.model_validate(
                {**before, **{k: bool(v) for k, v in flags.items()}}
            )
            self.ws.save_config(cfg)
            return cfg.agent.autopilot

        return self._record("settings.autopilot", "settings", apply, target_id="autopilot", before=before,
                            summary=", ".join(f"{k}={'on' if v else 'off'}" for k, v in flags.items()))  # fmt: skip

    def set_opportunities(self, enabled: bool | None = None, verify_on_web: bool | None = None) -> Any:
        """The daily opportunity job (ADR 0016): on or off, and whether finds are confirmed on the web."""
        if self.auto:
            raise AutopilotRefused("autopilot can't change settings")
        cfg = self.ws.config()
        before = cfg.opportunities.model_dump()

        def apply() -> Any:
            if enabled is not None:
                cfg.opportunities.enabled = bool(enabled)
            if verify_on_web is not None:
                cfg.opportunities.verify_on_web = bool(verify_on_web)
            self.ws.save_config(cfg)
            return cfg.opportunities.model_dump()

        return self._record("settings.opportunities", "settings", apply, target_id="opportunities", before=before,
                            summary=f"daily opportunity check {'on' if cfg.opportunities.enabled or enabled else 'off'}")  # fmt: skip

    def set_mail_sorting(self, on: bool) -> Any:
        """Model sorting for the Mail view (off by default: rules only)."""
        if self.auto:
            raise AutopilotRefused("autopilot can't change settings")
        cfg = self.ws.config()
        before = {"model_sorting": cfg.mail.model_sorting}

        def apply() -> Any:
            cfg.mail.model_sorting = bool(on)
            self.ws.save_config(cfg)
            return {"model_sorting": cfg.mail.model_sorting}

        return self._record("settings.mail", "settings", apply, target_id="model_sorting", before=before,
                            summary=f"mail model sorting {'on' if on else 'off'}")  # fmt: skip

    def set_cheap_mode(self, on: bool) -> Any:
        if self.auto:
            raise AutopilotRefused("autopilot can't change settings")
        cfg = self.ws.config()
        before = {"cheap_mode": cfg.agent.cheap_mode}

        def apply() -> Any:
            cfg.agent.cheap_mode = bool(on)
            self.ws.save_config(cfg)
            return {"cheap_mode": cfg.agent.cheap_mode}

        return self._record("settings.agent", "settings", apply, target_id="cheap_mode", before=before,
                            summary=f"cheap mode {'on' if on else 'off'}")  # fmt: skip

    def set_missions(self, **flags: bool) -> Any:
        if self.auto:
            raise AutopilotRefused("autopilot can't change mission settings")
        cfg = self.ws.config()
        before = cfg.agent.missions.model_dump()

        def apply() -> Any:
            cfg.agent.missions = cfg.agent.missions.model_validate(
                {**before, **{k: bool(v) for k, v in flags.items()}}
            )
            self.ws.save_config(cfg)
            return cfg.agent.missions

        return self._record("settings.missions", "settings", apply, target_id="missions", before=before,
                            summary=", ".join(f"{k}={'on' if v else 'off'}" for k, v in flags.items()))  # fmt: skip

    def promote_finding(self, finding_id: str, kind: str) -> Any:
        """A person decides an official page the agent found is a source the vault should rely on."""
        if self.auto:
            raise AutopilotRefused("autopilot can't change what counts as a source")
        from areao1.vault import Vault

        vault = Vault(self.ws)
        before = vault.manifest.source(finding_id)
        return self._record("vault.promote", "vault_source", lambda: vault.promote(finding_id, kind),
                            target_id=finding_id, before=before, summary=f"{before.title if before else finding_id} → {kind}")  # fmt: skip

    # ------------------------------------------------------------------ undo

    UNDOABLE = frozenset({"pipeline.add", "pipeline.update", "pipeline.move", "pipeline.delete", "deadline.add",
                          "deadline.update", "deadline.delete", "letter.add", "letter.update", "letter.delete",
                          "todo.update", "contact.add", "contact.update", "contact.delete", "metrics.record"})  # fmt: skip

    def undoable(self, change: Change, changes: list[Change] | None = None) -> bool:
        changes = changes if changes is not None else self.ws.changes()
        return change.action in self.UNDOABLE and not any(c.undoes == change.id for c in changes)

    def undo(self, change_id: str) -> Change:
        """Revert one change to its recorded 'before' state, if nothing has changed the record since."""
        changes = self.ws.changes()
        change = next((c for c in changes if c.id == change_id), None)
        if change is None:
            raise NotFound(f"no change {change_id!r}")
        if change.action not in self.UNDOABLE:
            raise WorkspaceError(f"{change.action} can't be undone here")
        if not self.undoable(change, changes):
            raise WorkspaceError("already undone")
        if change.action == "metrics.record":
            self._undo_metric(change)
        else:
            current = self._current(change.target_type, change.target_id)
            if not _same_record(current, change.after):
                raise WorkspaceError("it was changed again since; undo that first, or edit it by hand")
            self._record(f"{change.target_type}.undo", change.target_type,
                         lambda: self.ws.restore_record(change.target_type, change.target_id or "", change.before),
                         target_id=change.target_id, before=current, summary=f"undo: {change.summary}",
                         undoes=change.id)  # fmt: skip
        return self.ws.changes()[-1]

    def _current(self, target_type: str, target_id: str | None) -> dict[str, Any] | None:
        items: list[Any]
        if target_type == "pipeline_item":
            items = list(self.ws.pipeline().items)
        elif target_type == "deadline":
            items = list(self.ws.deadlines().deadlines)
        elif target_type == "letter":
            items = list(self.ws.letters().letters)
        elif target_type == "todo":
            items = list(self.ws.todos().todos)
        elif target_type == "contact":
            items = list(self.ws.contacts().contacts)
        else:
            raise WorkspaceError(f"can't undo changes to {target_type!r}")
        found = next((i for i in items if i.id == target_id), None)
        return found.model_dump(mode="json") if found else None

    def _undo_metric(self, change: Change) -> None:
        after = MetricRow.model_validate(change.after or {})
        key = (after.date, after.source, after.item, after.metric)
        current = next((r for r in self.ws.metrics() if (r.date, r.source, r.item, r.metric) == key), None)
        if current is None or current.value != after.value:
            raise WorkspaceError("that metric was changed again since; undo that first")

        def revert() -> Any:
            if change.before:
                self.ws.append_metrics([MetricRow.model_validate(change.before)])
            else:
                self.ws.remove_metric(*key)
            self.ws.after_change()
            return change.before

        self._record("metrics.undo", "metric", revert, target_id=change.target_id,
                     before=current, summary=f"undo: {change.summary}", undoes=change.id)  # fmt: skip

    # ------------------------------------------------------------------ to-dos

    def update_todo(self, todo_id: str, status: str) -> Any:
        before = next((t for t in self.ws.todos().todos if t.id == todo_id), None)
        if before is None:
            raise NotFound(f"no to-do {todo_id!r}")
        closed = clock.today() if status != "open" else None
        return self._record("todo.update", "todo", lambda: self.ws.update_todo(todo_id, status=status, closed=closed),
                            before=before, summary=f"{before.title}: {status}")  # fmt: skip

    # ------------------------------------------------------------------ onboarding (ADR 0008)

    def onboarding_save(self, state: Any, action: str, summary: str = "", person: dict[str, Any] | None = None,
                        evidence: Evidence | None = None, todos: list[Any] | None = None,
                        dismiss: list[str] | None = None) -> Any:  # fmt: skip
        """Save onboarding progress, plus the person fields an answer confirmed, the PDF observation and the
        self-reported to-dos the answers produced."""
        before = self.ws.onboarding()

        def do() -> Any:
            if evidence is not None:
                claims = self.ws.memory.record(evidence)
                if state.source is not None and claims:
                    state.source.observation_id = claims[0].observation_id
                elif state.source is not None:
                    state.source.observation_id = None
            if person:
                p = self.ws.person()
                for key, value in person.items():
                    setattr(p, key, value)
                self.ws.save_person(p)
            if todos:
                self.ws.add_todos(todos)
            for todo_id in dismiss or []:
                self.ws.update_todo(todo_id, status="dismissed", closed=clock.today())
            self.ws.save_onboarding(state)
            return state

        return self._record(action, "onboarding", do, before=before, summary=summary)


def _same_record(current: dict[str, Any] | None, after: dict[str, Any] | None) -> bool:
    if current is None or after is None:
        return current == after
    strip = {"moved_at"}
    return {k: v for k, v in current.items() if k not in strip} == {
        k: v for k, v in after.items() if k not in strip
    }
