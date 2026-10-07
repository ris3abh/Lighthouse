"""A case workspace: the domain-agnostic store plus criteria profiles, scoring and case files."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from areao1.core.workspace import DATA_FILES as CORE_DATA_FILES
from areao1.core.workspace import NotFound, Workspace, WorkspaceError
from areao1.criteria import engine
from areao1.criteria.models import (
    DEFAULT_PROFILE,
    CalendarSync,
    Contact,
    Contacts,
    GmailThreads,
    Letter,
    Letters,
    Person,
    Profile,
    Scoreboard,
    Todo,
    Todos,
)
from areao1.onboarding.models import OnboardingState

# Case files written on first use; validated when present.
CASE_OPTIONAL_FILES: dict[str, type[BaseModel]] = {"onboarding.json": OnboardingState, "todos.json": Todos,
                                                   "contacts.json": Contacts, "threads.json": GmailThreads,
                                                   "google-calendar.json": CalendarSync}  # fmt: skip

DATA_FILES: dict[str, type[BaseModel]] = {
    "person.json": Person,
    **CORE_DATA_FILES,
    "letters.json": Letters,
}


class Case(Workspace):
    # ------------------------------------------------------------------ case files

    def person(self) -> Person:
        return self._load("person.json", Person)

    def save_person(self, v: Person) -> None:
        self._save("person.json", v)

    def onboarding(self) -> OnboardingState:
        return self._load("onboarding.json", OnboardingState)

    def save_onboarding(self, v: OnboardingState) -> None:
        self._save("onboarding.json", v)

    # ------------------------------------------------------------------ contacts (ADR 0014 §4)

    def calendar_sync(self) -> CalendarSync:
        return self._load("google-calendar.json", CalendarSync)

    def save_calendar_sync(self, state: CalendarSync) -> None:
        self._save("google-calendar.json", state)

    def threads(self) -> GmailThreads:
        return self._load("threads.json", GmailThreads)

    def save_threads(self, threads: GmailThreads) -> None:
        self._save("threads.json", threads)

    def contacts(self) -> Contacts:
        return self._load("contacts.json", Contacts)

    CONTACT_FIELDS = ("name", "emails", "org", "relationship", "notes", "asks", "next_follow_up", "last_touch",
                     "letter_ids", "pipeline_ids")  # fmt: skip

    def add_contact(self, **fields: Any) -> Contact:
        with self.lock:
            bad = set(fields) - set(self.CONTACT_FIELDS)
            if bad:
                raise WorkspaceError(f"not a contact field: {', '.join(sorted(bad))}")
            try:
                contact = Contact.model_validate(fields)
            except ValueError as exc:
                raise WorkspaceError(f"invalid contact: {exc}") from exc
            contacts = self.contacts()
            contacts.contacts.append(contact)
            self._save("contacts.json", contacts)
            self.after_change()
            return contact

    def update_contact(self, contact_id: str, **changes: Any) -> Contact:
        with self.lock:
            contacts = self.contacts()
            idx = next((i for i, p in enumerate(contacts.contacts) if p.id == contact_id), None)
            if idx is None:
                raise NotFound(f"no contact {contact_id!r}")
            bad = set(changes) - set(self.CONTACT_FIELDS)
            if bad:
                raise WorkspaceError(f"not editable: {', '.join(sorted(bad))}")
            try:
                updated = Contact.model_validate({**contacts.contacts[idx].model_dump(), **changes})
            except ValueError as exc:
                raise WorkspaceError(f"invalid contact: {exc}") from exc
            contacts.contacts[idx] = updated
            self._save("contacts.json", contacts)
            self.after_change()
            return updated

    def delete_contact(self, contact_id: str) -> None:
        with self.lock:
            contacts = self.contacts()
            kept = [p for p in contacts.contacts if p.id != contact_id]
            if len(kept) == len(contacts.contacts):
                raise NotFound(f"no contact {contact_id!r}")
            contacts.contacts = kept
            self._save("contacts.json", contacts)
            self.after_change()

    def todos(self) -> Todos:
        return self._load("todos.json", Todos)

    def add_todos(self, todos: list[Todo]) -> list[Todo]:
        """Add the ones not already there (same id: same kind and item), so re-running onboarding adds nothing twice."""
        current = self.todos()
        have = {t.id for t in current.todos}
        new = [t for t in todos if t.id not in have]
        if new:
            current.todos += new
            self._save("todos.json", current)
        return new

    def update_todo(self, todo_id: str, **changes: Any) -> Todo:
        current = self.todos()
        todo = next((t for t in current.todos if t.id == todo_id), None)
        if todo is None:
            raise NotFound(f"no to-do {todo_id!r}")
        for key, value in changes.items():
            setattr(todo, key, value)
        self._save("todos.json", current)
        return todo

    def needs_onboarding(self) -> bool:
        """A brand-new workspace (no onboarding file, no name, nothing collected) or one mid-onboarding."""
        state = self.onboarding()
        if (self.data_dir / "onboarding.json").exists():
            return state.status in ("new", "in_progress")
        return not self.person().name and not self.inbox().candidates and not self.exhibits().exhibits

    def letters(self) -> Letters:
        return self._load("letters.json", Letters)

    # ------------------------------------------------------------------ profiles + scoring

    def profiles(self) -> dict[str, Profile]:
        return engine.load_profiles(self.root / "profiles")

    def profile_id(self) -> str:
        return self.config().profile or DEFAULT_PROFILE

    def profile(self, profile_id: str | None = None) -> Profile:
        pid = profile_id or self.profile_id()
        profiles = self.profiles()
        if pid not in profiles:
            raise WorkspaceError(f"unknown profile {pid!r}; available: {', '.join(sorted(profiles))}")
        return profiles[pid]

    def scoreboard(self) -> Scoreboard:
        path = self.data_dir / "criteria.json"
        if path.exists():
            board = Scoreboard.model_validate_json(path.read_text(encoding="utf-8"))
            if board.profile == self.profile_id() and board.rules_digest == engine.rules_digest(
                self.profile()
            ):
                return board
        return self.recompute()

    def recompute(self) -> Scoreboard:
        with self.lock:
            cfg = self.config()
            pid = self.profile_id()
            board = engine.score(self.profile(pid), self.exhibits().exhibits, cfg.overrides.get(pid))
            previous = self.data_dir / "criteria.json"
            if previous.exists():
                # Keep the agent's reviewer note across rule recomputes for the same profile.
                old = Scoreboard.model_validate_json(previous.read_text(encoding="utf-8"))
                if old.profile == board.profile:
                    board.reviewer_note = old.reviewer_note
            self._save("criteria.json", board)
            return board

    def set_profile(self, profile_id: str) -> Scoreboard:
        with self.lock:
            self.profile(profile_id)  # validates
            cfg = self.config()
            cfg.profile = profile_id
            self.save_config(cfg)
            return self.after_change()

    def set_override(self, criterion_id: str, status: str | None) -> Scoreboard:
        with self.lock:
            cfg = self.config()
            pid = self.profile_id()
            if self.profile(pid).criterion(criterion_id) is None:
                raise NotFound(f"criterion {criterion_id!r} is not in profile {pid!r}")
            per_profile = cfg.overrides.setdefault(pid, {})
            if status is None:
                per_profile.pop(criterion_id, None)
            elif status in ("dropped", "gap"):
                per_profile[criterion_id] = status  # type: ignore[assignment]
            else:
                raise WorkspaceError("override must be 'dropped', 'gap' or null")
            if not per_profile:
                cfg.overrides.pop(pid, None)
            self.save_config(cfg)
            return self.after_change()

    # ------------------------------------------------------------------ hooks

    def after_change(self) -> Scoreboard:
        """Recompute the scoreboard and regenerate DASHBOARD.md."""
        from areao1.core.calendar import write_calendar
        from areao1.criteria.dashboard import write_dashboard

        board = self.recompute()
        write_dashboard(self, board)
        write_calendar(self)
        return board

    def apply_tracker(self, kind: str, proposal: dict[str, Any]) -> BaseModel:
        if kind == "update" and proposal.get("target_type") == "letter":
            return self.update_letter(proposal["target_id"], **proposal.get("changes", {}))
        if kind != "letter":
            return super().apply_tracker(kind, proposal)
        try:
            letter = Letter.model_validate(proposal)
        except ValueError as exc:
            raise WorkspaceError(f"invalid letter entry: {exc}") from exc
        letters = self.letters()
        letters.letters.append(letter)
        self._save("letters.json", letters)
        return letter

    LETTER_FIELDS = (
        "name",
        "relationship",
        "credentials",
        "criteria",
        "asks",
        "status",
        "draft_path",
        "last_contact",
    )

    def add_letter(self, **fields: Any) -> Letter:
        with self.lock:
            letter = self.apply_tracker("letter", fields)
            self.after_change()
            return letter  # type: ignore[return-value]

    def update_letter(self, letter_id: str, **changes: Any) -> Letter:
        with self.lock:
            letters = self.letters()
            idx = next((i for i, lt in enumerate(letters.letters) if lt.id == letter_id), None)
            if idx is None:
                raise NotFound(f"no letter writer {letter_id!r}")
            bad = set(changes) - set(self.LETTER_FIELDS)
            if bad:
                raise WorkspaceError(f"not editable: {', '.join(sorted(bad))}")
            if changes.get("draft_path"):
                self._check_draft_path(changes["draft_path"])
            try:
                letters.letters[idx] = Letter.model_validate({**letters.letters[idx].model_dump(), **changes})
            except ValueError as exc:
                raise WorkspaceError(f"invalid letter entry: {exc}") from exc
            self._save("letters.json", letters)
            self.after_change()
            return letters.letters[idx]

    def delete_letter(self, letter_id: str) -> None:
        with self.lock:
            letters = self.letters()
            kept = [lt for lt in letters.letters if lt.id != letter_id]
            if len(kept) == len(letters.letters):
                raise NotFound(f"no letter writer {letter_id!r}")
            letters.letters = kept
            self._save("letters.json", letters)
            self.after_change()

    def _check_draft_path(self, rel: str) -> None:
        path = self.resolve_inside(rel)
        if (self.root / "drafts") not in path.parents:
            raise WorkspaceError("draft_path must be inside drafts/")

    def update_tracker(self, target_type: str, target_id: str, **changes: Any) -> BaseModel:
        if target_type == "letter":
            return self.update_letter(target_id, **changes)
        return super().update_tracker(target_type, target_id, **changes)

    def restore_record(self, target_type: str, record_id: str, before: dict[str, Any] | None) -> None:
        if target_type == "contact":
            with self.lock:
                contacts = self.contacts()
                ids = [p.id for p in contacts.contacts]
                others = [p for p in contacts.contacts if p.id != record_id]
                if before is not None:
                    others.insert(
                        ids.index(record_id) if record_id in ids else len(others),
                        Contact.model_validate(before),
                    )
                contacts.contacts = others
                self._save("contacts.json", contacts)
                self.after_change()
            return None
        if target_type == "todo":
            with self.lock:
                todos = self.todos()
                todos.todos = [
                    Todo.model_validate(before) if t.id == record_id and before else t for t in todos.todos
                ]
                self._save("todos.json", todos)
                self.after_change()
            return None
        if target_type != "letter":
            return super().restore_record(target_type, record_id, before)
        with self.lock:
            letters = self.letters()
            old = [lt.id for lt in letters.letters]
            kept = [lt for lt in letters.letters if lt.id != record_id]
            if before is not None:
                kept.insert(
                    old.index(record_id) if record_id in old else len(kept), Letter.model_validate(before)
                )
            letters.letters = kept
            self._save("letters.json", letters)
            self.after_change()

    def classify_upload(self, filename: str) -> tuple[str, str, str | None]:
        from areao1.criteria.classify import classify

        return classify(filename, self.profile())

    def validate_criterion(self, criterion_id: str) -> None:
        known = {c.id for p in self.profiles().values() for c in p.criteria}
        if criterion_id not in known:
            raise WorkspaceError(f"unknown criterion {criterion_id!r}")
