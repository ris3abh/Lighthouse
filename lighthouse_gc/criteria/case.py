"""A case workspace: the domain-agnostic store plus criteria profiles, scoring and case files."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from lighthouse_gc.core.workspace import DATA_FILES as CORE_DATA_FILES
from lighthouse_gc.core.workspace import NotFound, Workspace, WorkspaceError
from lighthouse_gc.criteria import engine
from lighthouse_gc.criteria.models import DEFAULT_PROFILE, Letter, Letters, Person, Profile, Scoreboard
from lighthouse_gc.onboarding.models import OnboardingState

# Case files written on first use; validated when present.
CASE_OPTIONAL_FILES: dict[str, type[BaseModel]] = {"onboarding.json": OnboardingState}

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
        from lighthouse_gc.core.calendar import write_calendar
        from lighthouse_gc.criteria.dashboard import write_dashboard

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
        from lighthouse_gc.criteria.classify import classify

        return classify(filename, self.profile())

    def validate_criterion(self, criterion_id: str) -> None:
        known = {c.id for p in self.profiles().values() for c in p.criteria}
        if criterion_id not in known:
            raise WorkspaceError(f"unknown criterion {criterion_id!r}")
