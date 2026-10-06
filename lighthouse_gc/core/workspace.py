"""The workspace store: every read and write of a private case directory goes through here.

Files are the source of truth. Every write is validated against the pydantic models and written
atomically (temp file + rename) as pretty, stable JSON so diffs stay small and reviewable.
"""

from __future__ import annotations

import csv
import io
import json
import os
import re
import shutil
import tempfile
import threading
from collections.abc import Iterable
from datetime import date, timedelta
from pathlib import Path
from typing import Any, TypeVar

import yaml
from pydantic import BaseModel

from lighthouse_gc.core import criteria as engine
from lighthouse_gc.core.models import (
    EXHIBIT_NAME_RE,
    METRICS_COLUMNS,
    Candidate,
    Deadlines,
    Exhibit,
    Exhibits,
    Inbox,
    Letters,
    MetricRow,
    Opportunities,
    Person,
    Pipeline,
    Profile,
    Scoreboard,
    SourceRecord,
    SourcesFile,
    WorkspaceConfig,
    slugify,
    utcnow,
)

M = TypeVar("M", bound=BaseModel)

CONFIG_FILE = "lighthouse.yaml"

DATA_FILES: dict[str, type[BaseModel]] = {
    "person.json": Person,
    "sources.json": SourcesFile,
    "inbox.json": Inbox,
    "exhibits.json": Exhibits,
    "pipeline.json": Pipeline,
    "letters.json": Letters,
    "deadlines.json": Deadlines,
    "opportunities.json": Opportunities,
}


class WorkspaceError(Exception):
    pass


class NotFound(WorkspaceError):
    pass


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def dump_model(model: BaseModel) -> str:
    return json.dumps(model.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def exhibit_filename(criterion: str, on: date, title: str, ext: str) -> str:
    ext = ext.lower().lstrip(".") or "md"
    return f"{criterion}_{on.isoformat()}_{slugify(title)}.{ext}"


class Workspace:
    """A private case directory. Cheap to construct; reads hit the disk every time."""

    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.lock = threading.RLock()

    # ------------------------------------------------------------------ paths

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def evidence_dir(self) -> Path:
        return self.root / "evidence"

    @property
    def cache_dir(self) -> Path:
        return self.root / ".lighthouse" / "cache"

    @property
    def metrics_path(self) -> Path:
        return self.data_dir / "metrics.csv"

    def exists(self) -> bool:
        return (self.root / CONFIG_FILE).is_file()

    def require(self) -> Workspace:
        if not self.exists():
            raise WorkspaceError(f"{self.root} is not a Lighthouse workspace (no {CONFIG_FILE}).")
        return self

    def resolve_inside(self, relative: str) -> Path:
        """Resolve a workspace-relative path, refusing anything that escapes the workspace."""
        path = (self.root / relative).resolve()
        if path != self.root and self.root not in path.parents:
            raise WorkspaceError(f"path escapes the workspace: {relative}")
        return path

    # ------------------------------------------------------------------ generic io

    def _load(self, name: str, model: type[M]) -> M:
        path = self.data_dir / name
        if not path.exists():
            return model()
        return model.model_validate_json(path.read_text(encoding="utf-8"))

    def _save(self, name: str, value: BaseModel) -> None:
        # Round-trip through the model so nothing invalid reaches disk.
        type(value).model_validate(value.model_dump())
        _atomic_write(self.data_dir / name, dump_model(value))

    # ------------------------------------------------------------------ config

    def config(self) -> WorkspaceConfig:
        path = self.root / CONFIG_FILE
        if not path.exists():
            return WorkspaceConfig()
        return WorkspaceConfig.model_validate(yaml.safe_load(path.read_text()) or {})

    def save_config(self, cfg: WorkspaceConfig) -> None:
        body = yaml.safe_dump(cfg.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
        header = "# Lighthouse workspace config. No secrets here — tokens live in the OS keychain.\n"
        _atomic_write(self.root / CONFIG_FILE, header + body)

    # ------------------------------------------------------------------ typed files

    def person(self) -> Person:
        return self._load("person.json", Person)

    def save_person(self, v: Person) -> None:
        self._save("person.json", v)

    def sources(self) -> SourcesFile:
        return self._load("sources.json", SourcesFile)

    def save_sources(self, v: SourcesFile) -> None:
        self._save("sources.json", v)

    def inbox(self) -> Inbox:
        return self._load("inbox.json", Inbox)

    def save_inbox(self, v: Inbox) -> None:
        self._save("inbox.json", v)

    def exhibits(self) -> Exhibits:
        return self._load("exhibits.json", Exhibits)

    def save_exhibits(self, v: Exhibits) -> None:
        self._save("exhibits.json", v)

    def pipeline(self) -> Pipeline:
        return self._load("pipeline.json", Pipeline)

    def letters(self) -> Letters:
        return self._load("letters.json", Letters)

    def deadlines(self) -> Deadlines:
        return self._load("deadlines.json", Deadlines)

    def opportunities(self) -> Opportunities:
        return self._load("opportunities.json", Opportunities)

    def scoreboard(self) -> Scoreboard:
        path = self.data_dir / "criteria.json"
        if path.exists():
            board = Scoreboard.model_validate_json(path.read_text(encoding="utf-8"))
            if board.profile == self.config().profile:
                return board
        return self.recompute()

    # ------------------------------------------------------------------ profiles + scoring

    def profiles(self) -> dict[str, Profile]:
        return engine.load_profiles(self.root / "profiles")

    def profile(self, profile_id: str | None = None) -> Profile:
        pid = profile_id or self.config().profile
        profiles = self.profiles()
        if pid not in profiles:
            raise WorkspaceError(f"unknown profile {pid!r}; available: {', '.join(sorted(profiles))}")
        return profiles[pid]

    def recompute(self) -> Scoreboard:
        with self.lock:
            cfg = self.config()
            board = engine.score(
                self.profile(cfg.profile), self.exhibits().exhibits, cfg.overrides.get(cfg.profile)
            )
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
            if self.profile(cfg.profile).criterion(criterion_id) is None:
                raise NotFound(f"criterion {criterion_id!r} is not in profile {cfg.profile!r}")
            per_profile = cfg.overrides.setdefault(cfg.profile, {})
            if status is None:
                per_profile.pop(criterion_id, None)
            elif status in ("dropped", "gap"):
                per_profile[criterion_id] = status  # type: ignore[assignment]
            else:
                raise WorkspaceError("override must be 'dropped', 'gap' or null")
            if not per_profile:
                cfg.overrides.pop(cfg.profile, None)
            self.save_config(cfg)
            return self.after_change()

    def after_change(self) -> Scoreboard:
        """Recompute the scoreboard and regenerate DASHBOARD.md."""
        from lighthouse_gc.core.dashboard import write_dashboard

        board = self.recompute()
        write_dashboard(self, board)
        return board

    # ------------------------------------------------------------------ sources

    def upsert_source(self, record: SourceRecord) -> SourceRecord:
        """Insert or merge a source; existing items keep their tracked flag and discovery date."""
        with self.lock:
            sf = self.sources()
            existing = next((s for s in sf.sources if s.id == record.id), None)
            if existing is None:
                sf.sources.append(record)
                self.save_sources(sf)
                return record
            known = {i.id: i for i in existing.items}
            for item in record.items:
                if item.id in known:
                    old = known[item.id]
                    item.tracked, item.discovered_at = old.tracked, old.discovered_at
                known[item.id] = item
            existing.items = sorted(known.values(), key=lambda i: i.id)
            existing.url, existing.auth = record.url, record.auth
            existing.secret_ref = record.secret_ref or existing.secret_ref
            self.save_sources(sf)
            return existing

    def update_source(self, source_id: str, **changes: Any) -> SourceRecord:
        with self.lock:
            sf = self.sources()
            src = next((s for s in sf.sources if s.id == source_id), None)
            if src is None:
                raise NotFound(f"no source {source_id!r}")
            for key, value in changes.items():
                setattr(src, key, value)
            self.save_sources(sf)
            return src

    def remove_source(self, source_id: str) -> None:
        with self.lock:
            sf = self.sources()
            before = len(sf.sources)
            sf.sources = [s for s in sf.sources if s.id != source_id]
            if len(sf.sources) == before:
                raise NotFound(f"no source {source_id!r}")
            self.save_sources(sf)

    # ------------------------------------------------------------------ inbox

    def add_candidates(self, candidates: Iterable[Candidate]) -> list[Candidate]:
        """Add candidates that aren't already in the inbox (any status) or accepted as exhibits."""
        with self.lock:
            inbox = self.inbox()
            seen = {c.fingerprint for c in inbox.candidates}
            seen |= {e.fingerprint for e in self.exhibits().exhibits if e.fingerprint}
            added = []
            for cand in candidates:
                if cand.fingerprint in seen:
                    continue
                seen.add(cand.fingerprint)
                inbox.candidates.append(cand)
                added.append(cand)
            if added:
                self.save_inbox(inbox)
            return added

    def pending_candidates(self, today: date | None = None) -> list[Candidate]:
        today = today or date.today()
        out = []
        for c in self.inbox().candidates:
            if c.status == "pending" or (
                c.status == "snoozed" and c.snoozed_until and c.snoozed_until <= today
            ):
                out.append(c)
        return out

    def _candidate(self, inbox: Inbox, candidate_id: str) -> Candidate:
        cand = next((c for c in inbox.candidates if c.id == candidate_id), None)
        if cand is None:
            raise NotFound(f"no candidate {candidate_id!r}")
        return cand

    EDITABLE_CANDIDATE_FIELDS = ("proposed_criterion", "evidence_type", "title", "summary", "signals")

    def edit_candidate(self, candidate_id: str, **changes: Any) -> Candidate:
        with self.lock:
            inbox = self.inbox()
            cand = self._candidate(inbox, candidate_id)
            for key, value in changes.items():
                if key not in self.EDITABLE_CANDIDATE_FIELDS:
                    raise WorkspaceError(f"field {key!r} is not editable")
                if value is not None:
                    setattr(cand, key, value)
            self.save_inbox(inbox)
            return cand

    def reject_candidate(self, candidate_id: str) -> Candidate:
        # Rejected candidates stay in inbox.json so a re-import never resurrects them.
        with self.lock:
            inbox = self.inbox()
            cand = self._candidate(inbox, candidate_id)
            cand.status = "rejected"
            self.save_inbox(inbox)
            self.after_change()
            return cand

    def snooze_candidate(self, candidate_id: str, until: date | None = None) -> Candidate:
        with self.lock:
            inbox = self.inbox()
            cand = self._candidate(inbox, candidate_id)
            cand.status = "snoozed"
            cand.snoozed_until = until or (date.today() + timedelta(days=7))
            self.save_inbox(inbox)
            self.after_change()
            return cand

    def accept_candidate(self, candidate_id: str, **edits: Any) -> Exhibit:
        """Turn a candidate into an exhibit: write a capture file, log it, re-score."""
        with self.lock:
            inbox = self.inbox()
            cand = self._candidate(inbox, candidate_id)
            if cand.status == "rejected":
                raise WorkspaceError("candidate was rejected; edit it back to pending first")
            exhibit_date = edits.pop("date", None) or date.today()
            for key, value in edits.items():
                if key not in self.EDITABLE_CANDIDATE_FIELDS:
                    raise WorkspaceError(f"field {key!r} is not editable")
                if value is not None:
                    setattr(cand, key, value)
            self._check_criterion(cand.proposed_criterion)

            rel = self._unique_evidence_path(cand.proposed_criterion, exhibit_date, cand.title, "md")
            _atomic_write(self.root / rel, _capture_markdown(cand, exhibit_date))
            exhibit = Exhibit(
                criterion=cand.proposed_criterion,
                evidence_type=cand.evidence_type,
                title=cand.title,
                summary=cand.summary,
                date=exhibit_date,
                file=rel,
                source_url=cand.raw_url,
                candidate_id=cand.id,
                fingerprint=cand.fingerprint,
                signals=list(cand.signals),
            )
            ex = self.exhibits()
            ex.exhibits.append(exhibit)
            self.save_exhibits(ex)
            inbox.candidates = [c for c in inbox.candidates if c.id != cand.id]
            self.save_inbox(inbox)
            self.after_change()
            return exhibit

    # ------------------------------------------------------------------ evidence

    def _check_criterion(self, criterion_id: str) -> None:
        known = {c.id for p in self.profiles().values() for c in p.criteria}
        if criterion_id not in known:
            raise WorkspaceError(f"unknown criterion {criterion_id!r}")

    def _unique_evidence_path(self, criterion: str, on: date, title: str, ext: str) -> str:
        name = exhibit_filename(criterion, on, title, ext)
        stem, suffix = name.rsplit(".", 1)
        rel = f"evidence/{criterion}/{name}"
        n = 2
        while (self.root / rel).exists():
            rel = f"evidence/{criterion}/{stem}-{n}.{suffix}"
            n += 1
        return rel

    def add_exhibit_file(
        self,
        *,
        content: bytes,
        filename: str,
        criterion: str,
        evidence_type: str,
        title: str,
        on: date,
        summary: str = "",
        signals: list[str] | None = None,
        source_url: str | None = None,
    ) -> Exhibit:
        """Manual upload: the user is filing this themselves, so it becomes an exhibit directly."""
        with self.lock:
            self._check_criterion(criterion)
            ext = Path(filename).suffix.lstrip(".") or "bin"
            if not re.fullmatch(r"[A-Za-z0-9]{1,8}", ext):
                raise WorkspaceError(f"unsupported file extension {ext!r}")
            rel = self._unique_evidence_path(criterion, on, title, ext)
            path = self.root / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            exhibit = Exhibit(
                criterion=criterion,
                evidence_type=evidence_type,
                title=title,
                summary=summary,
                date=on,
                file=rel,
                source_url=source_url,
                signals=signals or [],
            )
            ex = self.exhibits()
            ex.exhibits.append(exhibit)
            self.save_exhibits(ex)
            self.after_change()
            return exhibit

    def remap_exhibit(self, exhibit_id: str, criterion: str, evidence_type: str | None = None) -> Exhibit:
        """File an exhibit under another criterion, moving and renaming its file to match."""
        with self.lock:
            self._check_criterion(criterion)
            ex = self.exhibits()
            exhibit = next((e for e in ex.exhibits if e.id == exhibit_id), None)
            if exhibit is None:
                raise NotFound(f"no exhibit {exhibit_id!r}")
            old = self.resolve_inside(exhibit.file)
            ext = old.suffix.lstrip(".") or "md"
            if criterion != exhibit.criterion:
                new_rel = self._unique_evidence_path(criterion, exhibit.date, exhibit.title, ext)
                if old.exists():
                    (self.root / new_rel).parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(old, self.root / new_rel)
                exhibit.file = new_rel
                exhibit.criterion = criterion
            if evidence_type:
                exhibit.evidence_type = evidence_type
            self.save_exhibits(ex)
            self.after_change()
            return exhibit

    def naming_check(self) -> list[dict[str, str]]:
        """Problems between evidence/ on disk and exhibits.json."""
        issues: list[dict[str, str]] = []
        logged = {e.file: e for e in self.exhibits().exhibits}
        for rel, exhibit in logged.items():
            if not (self.root / rel).exists():
                issues.append(
                    {"file": rel, "problem": "missing", "detail": f"exhibit {exhibit.id} has no file"}
                )
            match = EXHIBIT_NAME_RE.match(Path(rel).name)
            if not match:
                issues.append(
                    {
                        "file": rel,
                        "problem": "bad_name",
                        "detail": "expected <crit>_<yyyy-mm-dd>_<slug>.<ext>",
                    }
                )
            elif match["crit"] != exhibit.criterion or Path(rel).parent.name != exhibit.criterion:
                issues.append(
                    {
                        "file": rel,
                        "problem": "wrong_folder",
                        "detail": f"exhibit is filed under {exhibit.criterion}",
                    }
                )
        if self.evidence_dir.is_dir():
            for path in sorted(self.evidence_dir.rglob("*")):
                if not path.is_file() or path.name.startswith("."):
                    continue
                rel = path.relative_to(self.root).as_posix()
                if rel in logged:
                    continue
                problem = "unlogged" if EXHIBIT_NAME_RE.match(path.name) else "bad_name"
                issues.append({"file": rel, "problem": problem, "detail": "file is not in exhibits.json"})
        return issues

    # ------------------------------------------------------------------ metrics

    def metrics(self) -> list[MetricRow]:
        if not self.metrics_path.exists():
            return []
        with self.metrics_path.open(newline="", encoding="utf-8") as fh:
            return [MetricRow.model_validate(row) for row in csv.DictReader(fh)]

    def append_metrics(self, rows: Iterable[MetricRow]) -> int:
        """Upsert rows keyed on (date, source, item, metric). Returns how many rows were new or changed."""
        with self.lock:
            existing = {(r.date, r.source, r.item, r.metric): r for r in self.metrics()}
            changed = 0
            for row in rows:
                key = (row.date, row.source, row.item, row.metric)
                if key not in existing or existing[key].value != row.value:
                    changed += 1
                existing[key] = row
            out = io.StringIO()
            writer = csv.writer(out, lineterminator="\n")
            writer.writerow(METRICS_COLUMNS)
            for r in sorted(existing.values(), key=lambda r: (r.date, r.source, r.item, r.metric)):
                value = int(r.value) if float(r.value).is_integer() else r.value
                writer.writerow([r.date.isoformat(), r.source, r.item, r.metric, value])
            _atomic_write(self.metrics_path, out.getvalue())
            return changed


def _capture_markdown(cand: Candidate, on: date) -> str:
    lines = [
        f"# {cand.title}",
        "",
        f"- Criterion: `{cand.proposed_criterion}`",
        f"- Evidence type: `{cand.evidence_type}`",
        f"- Captured: {on.isoformat()} (accepted {utcnow().isoformat()})",
        f"- Source: {cand.source}",
    ]
    if cand.raw_url:
        lines.append(f"- Link: {cand.raw_url}")
    if cand.signals:
        lines.append(f"- Strength signals: {', '.join(cand.signals)}")
    lines += ["", cand.summary, ""]
    if cand.facts:
        lines += ["## Facts at capture time", "", "| Fact | Value |", "|---|---|"]
        lines += [f"| {k} | {v} |" for k, v in sorted(cand.facts.items())]
        lines.append("")
    lines += [
        "> Capture file generated by Lighthouse. Upload the primary document (PDF, screenshot, letter)",
        "> as its own exhibit from the Evidence page before filing.",
        "",
    ]
    return "\n".join(lines)
