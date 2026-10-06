"""A case workspace: the domain-agnostic store plus criteria profiles, scoring and case files."""

from __future__ import annotations

from pydantic import BaseModel

from lighthouse_gc.core.workspace import DATA_FILES as CORE_DATA_FILES
from lighthouse_gc.core.workspace import NotFound, Workspace, WorkspaceError
from lighthouse_gc.criteria import engine
from lighthouse_gc.criteria.models import DEFAULT_PROFILE, Letters, Person, Profile, Scoreboard

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
            if board.profile == self.profile_id():
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
        from lighthouse_gc.criteria.dashboard import write_dashboard

        board = self.recompute()
        write_dashboard(self, board)
        return board

    def validate_criterion(self, criterion_id: str) -> None:
        known = {c.id for p in self.profiles().values() for c in p.criteria}
        if criterion_id not in known:
            raise WorkspaceError(f"unknown criterion {criterion_id!r}")
