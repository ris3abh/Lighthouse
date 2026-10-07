"""The workspace store: every read and write of a workspace directory goes through here.

Domain-agnostic: it stores sources, the inbox, exhibits, metrics and the memory graph, and knows
nothing about any criteria profile. The domain layer (``lighthouse_gc.criteria.case.Case``) subclasses
it to add scoring via the ``after_change`` / ``validate_criterion`` hooks.

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
from functools import cached_property
from pathlib import Path
from typing import Any, Self, TypeVar

import yaml
from pydantic import BaseModel, TypeAdapter

from lighthouse_gc.core.memory import Memory
from lighthouse_gc.core.models import (
    EXHIBIT_NAME_RE,
    METRICS_COLUMNS,
    NON_EVIDENTIARY_TIERS,
    Briefing,
    Candidate,
    Change,
    Deadline,
    Deadlines,
    Exhibit,
    Exhibits,
    Inbox,
    MetricRow,
    Opportunities,
    Pipeline,
    PipelineItem,
    Slug,
    SourceRecord,
    SourcesFile,
    WorkspaceConfig,
    slugify,
    utcnow,
)

M = TypeVar("M", bound=BaseModel)

CONFIG_FILE = "lighthouse.yaml"

DATA_FILES: dict[str, type[BaseModel]] = {
    "sources.json": SourcesFile,
    "inbox.json": Inbox,
    "exhibits.json": Exhibits,
    "pipeline.json": Pipeline,
    "deadlines.json": Deadlines,
    "opportunities.json": Opportunities,
}


# Written by the app on first use; validated when present.
OPTIONAL_FILES: dict[str, type[BaseModel]] = {"briefing.json": Briefing}


class WorkspaceError(Exception):
    pass


class NotFound(WorkspaceError):
    pass


def _atomic_write(path: Path, text: str | bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        if isinstance(text, bytes):
            with os.fdopen(fd, "wb") as fb:
                fb.write(text)
        else:
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

    @cached_property
    def memory(self) -> Memory:
        return Memory(self.root, self.cache_dir)

    def exists(self) -> bool:
        return (self.root / CONFIG_FILE).is_file()

    def require(self) -> Self:
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

    def deadlines(self) -> Deadlines:
        return self._load("deadlines.json", Deadlines)

    def briefing(self) -> Briefing:
        return self._load("briefing.json", Briefing)

    def save_briefing(self, briefing: Briefing) -> None:
        self._save("briefing.json", briefing)

    def opportunities(self) -> Opportunities:
        return self._load("opportunities.json", Opportunities)

    # ------------------------------------------------------------------ audit trail

    @property
    def changes_path(self) -> Path:
        return self.data_dir / "changes.jsonl"

    def append_change(self, change: Change) -> None:
        with self.lock:
            self.changes_path.parent.mkdir(parents=True, exist_ok=True)
            with self.changes_path.open("a", encoding="utf-8") as fh:
                fh.write(change.model_dump_json() + "\n")

    def changes(self) -> list[Change]:
        if not self.changes_path.exists():
            return []
        return [
            Change.model_validate_json(line)
            for line in self.changes_path.read_text().splitlines()
            if line.strip()
        ]

    # ------------------------------------------------------------------ domain hooks

    def after_change(self) -> Any:
        """Called after every write that could change derived views. The domain layer re-scores here."""
        return None

    def validate_criterion(self, criterion_id: str) -> None:
        """The domain layer checks ids against its profiles; the core only checks the shape."""
        try:
            TypeAdapter(Slug).validate_python(criterion_id)
        except ValueError as exc:
            raise WorkspaceError(f"invalid criterion id {criterion_id!r}") from exc

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
                if cand._evidence is not None:
                    # Observation + proposed claims go to memory; the candidate points at them.
                    claims = self.memory.record(cand._evidence)
                    cand.claim_ids = [c.id for c in claims]
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

    TEXT_FIELDS = ("title", "summary")
    EDITABLE_CANDIDATE_FIELDS = (
        "proposed_criterion",
        "evidence_type",
        "title",
        "summary",
        "signals",
        "stage",
        "proposal",
    )  # kind and source_tier are deliberately not editable

    def edit_candidate(self, candidate_id: str, **changes: Any) -> Candidate:
        with self.lock:
            inbox = self.inbox()
            cand = self._candidate(inbox, candidate_id)
            for key, value in changes.items():
                if key not in self.EDITABLE_CANDIDATE_FIELDS:
                    raise WorkspaceError(f"field {key!r} is not editable")
                if value is not None:
                    setattr(cand, key, value)
            if any(changes.get(k) is not None for k in self.TEXT_FIELDS):
                cand.rule_check = None  # the person rewrote it: their words now, not the agent's
            self.save_inbox(inbox)
            return cand

    def reject_candidate(self, candidate_id: str) -> Candidate:
        # Rejected candidates stay in inbox.json so a re-import never resurrects them.
        with self.lock:
            inbox = self.inbox()
            cand = self._candidate(inbox, candidate_id)
            cand.status = "rejected"
            self.save_inbox(inbox)
            if cand.claim_ids:
                self.memory.decide(cand.claim_ids, "rejected", rationale="rejected in the Inbox")
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

    def accept_candidate(self, candidate_id: str, **edits: Any) -> Any:
        """Accept a candidate. Evidence becomes an exhibit (capture file or uploaded bytes, logged, re-scored);
        a tracker candidate (pipeline / deadline / letter) becomes a tracker entry and never an exhibit."""
        with self.lock:
            inbox = self.inbox()
            cand = self._candidate(inbox, candidate_id)
            if cand.status == "rejected":
                raise WorkspaceError("candidate was rejected; edit it back to pending first")
            if cand.kind != "evidence":
                return self._accept_tracker(inbox, cand)
            if cand.source_tier in NON_EVIDENTIARY_TIERS:
                # Self-reported material (e.g. your own chat history) can organize work, never prove it.
                raise WorkspaceError(
                    "self-reported items can't become exhibits; upload the underlying document instead"
                )
            exhibit_date = edits.pop("date", None) or date.today()
            for key, value in edits.items():
                if key not in self.EDITABLE_CANDIDATE_FIELDS:
                    raise WorkspaceError(f"field {key!r} is not editable")
                if value is not None:
                    setattr(cand, key, value)
            if not cand.proposed_criterion:
                raise WorkspaceError("choose a criterion before accepting")
            self.validate_criterion(cand.proposed_criterion)

            if cand.attachment:
                # An uploaded document: file the original bytes under the naming convention.
                obs = self.memory.observation(cand.attachment)
                if obs is None or not (self.root / obs.snapshot).exists():
                    raise WorkspaceError(f"uploaded file for {cand.id} is missing from memory/sources/")
                ext = obs.snapshot.rsplit(".", 1)[-1]
                rel = self._unique_evidence_path(cand.proposed_criterion, exhibit_date, cand.title, ext)
                path = self.root / rel
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((self.root / obs.snapshot).read_bytes())
            else:
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
                stage=cand.stage,
                source_tier=cand.source_tier,
                claim_ids=list(cand.claim_ids),
            )
            if cand.claim_ids:
                # Approval records a decision; it does not certify truth or legal sufficiency.
                self.memory.decide(cand.claim_ids, "approved", rationale="accepted in the Inbox")
                self.memory.cite(exhibit.id, cand.claim_ids)
            ex = self.exhibits()
            ex.exhibits.append(exhibit)
            self.save_exhibits(ex)
            inbox.candidates = [c for c in inbox.candidates if c.id != cand.id]
            self.save_inbox(inbox)
            self.after_change()
            return exhibit

    def _accept_tracker(self, inbox: Inbox, cand: Candidate) -> BaseModel:
        record = self.apply_tracker(cand.kind, dict(cand.proposal))
        if cand.claim_ids:
            self.memory.decide(cand.claim_ids, "approved", rationale=f"added to {cand.kind} tracker")
        inbox.candidates = [c for c in inbox.candidates if c.id != cand.id]
        self.save_inbox(inbox)
        self.after_change()
        return record

    def apply_tracker(self, kind: str, proposal: dict[str, Any]) -> BaseModel:
        """Add a tracker entry. The domain layer adds kinds it owns (letters)."""
        try:
            if kind == "deadline":
                deadline = Deadline.model_validate(proposal)
                dl = self.deadlines()
                dl.deadlines.append(deadline)
                self._save("deadlines.json", dl)
                return deadline
            if kind == "pipeline":
                item = PipelineItem.model_validate(proposal)
                pl = self.pipeline()
                pl.items.append(item)
                self._save("pipeline.json", pl)
                return item
            if kind == "update":
                return self.update_tracker(
                    proposal["target_type"], proposal["target_id"], **proposal["changes"]
                )
            if kind == "metric":
                row = MetricRow.model_validate(proposal)
                self.append_metrics([row])
                return row
        except (ValueError, KeyError) as exc:
            raise WorkspaceError(f"invalid {kind} entry: {exc}") from exc
        raise WorkspaceError(f"unknown tracker kind {kind!r}")

    def update_tracker(self, target_type: str, target_id: str, **changes: Any) -> BaseModel:
        if target_type == "pipeline_item":
            return self.update_pipeline_item(target_id, **changes)
        if target_type == "deadline":
            return self.update_deadline(target_id, **changes)
        raise WorkspaceError(f"can't update {target_type!r}")

    def restore_record(self, target_type: str, record_id: str, before: dict[str, Any] | None) -> None:
        """Put a tracker record back exactly as ``before`` (or remove it when ``before`` is None). For undo."""
        files: dict[str, tuple[str, Any, str, type[BaseModel]]] = {
            "pipeline_item": ("pipeline.json", self.pipeline, "items", PipelineItem),
            "deadline": ("deadlines.json", self.deadlines, "deadlines", Deadline),
        }
        if target_type not in files:
            raise WorkspaceError(f"can't restore {target_type!r}")
        name, load, attr, model = files[target_type]
        with self.lock:
            data = load()
            records = [r for r in getattr(data, attr) if r.id != record_id]
            if before is not None:
                restored = model.model_validate(before)
                old = [r.id for r in getattr(data, attr)]
                records.insert(old.index(record_id) if record_id in old else len(records), restored)
            setattr(data, attr, records)
            self._save(name, data)
            self.after_change()

    def remove_metric(self, on: date, source: str, item: str, metric: str) -> None:
        with self.lock:
            keep = [
                r
                for r in self.metrics()
                if (r.date, r.source, r.item, r.metric) != (on, source, item, metric)
            ]
            out = io.StringIO()
            writer = csv.writer(out, lineterminator="\n")
            writer.writerow(METRICS_COLUMNS)
            for r in sorted(keep, key=lambda r: (r.date, r.source, r.item, r.metric)):
                writer.writerow([r.date.isoformat(), r.source, r.item, r.metric,
                                 int(r.value) if float(r.value).is_integer() else r.value])  # fmt: skip
            _atomic_write(self.metrics_path, out.getvalue())

    # ------------------------------------------------------------------ deadlines

    DEADLINE_FIELDS = ("title", "due", "kind", "criterion", "url", "human_only", "done")

    def add_deadline(self, **fields: Any) -> Deadline:
        with self.lock:
            try:
                deadline = Deadline.model_validate(fields)
            except ValueError as exc:
                raise WorkspaceError(f"invalid deadline: {exc}") from exc
            dl = self.deadlines()
            dl.deadlines.append(deadline)
            self._save("deadlines.json", dl)
            self.after_change()
            return deadline

    def update_deadline(self, deadline_id: str, **changes: Any) -> Deadline:
        with self.lock:
            dl = self.deadlines()
            idx = next((i for i, d in enumerate(dl.deadlines) if d.id == deadline_id), None)
            if idx is None:
                raise NotFound(f"no deadline {deadline_id!r}")
            bad = set(changes) - set(self.DEADLINE_FIELDS)
            if bad:
                raise WorkspaceError(f"not editable: {', '.join(sorted(bad))}")
            try:
                updated = Deadline.model_validate({**dl.deadlines[idx].model_dump(), **changes})
            except ValueError as exc:
                raise WorkspaceError(f"invalid deadline: {exc}") from exc
            dl.deadlines[idx] = updated
            self._save("deadlines.json", dl)
            self.after_change()
            return updated

    def delete_deadline(self, deadline_id: str) -> None:
        with self.lock:
            dl = self.deadlines()
            kept = [d for d in dl.deadlines if d.id != deadline_id]
            if len(kept) == len(dl.deadlines):
                raise NotFound(f"no deadline {deadline_id!r}")
            dl.deadlines = kept
            self._save("deadlines.json", dl)
            self.after_change()

    # ------------------------------------------------------------------ pipeline

    PIPELINE_FIELDS = ("title", "criterion", "stage", "url", "follow_up", "notes")

    def add_pipeline_item(self, **fields: Any) -> PipelineItem:
        with self.lock:
            try:
                item = PipelineItem.model_validate(fields)
            except ValueError as exc:
                raise WorkspaceError(f"invalid pipeline item: {exc}") from exc
            pl = self.pipeline()
            pl.items.append(item)
            self._save("pipeline.json", pl)
            self.after_change()
            return item

    def update_pipeline_item(self, item_id: str, **changes: Any) -> PipelineItem:
        """Edit an item. Changing its stage counts as movement (resets the staleness clock); other edits don't."""
        with self.lock:
            pl = self.pipeline()
            idx = next((i for i, p in enumerate(pl.items) if p.id == item_id), None)
            if idx is None:
                raise NotFound(f"no pipeline item {item_id!r}")
            bad = set(changes) - set(self.PIPELINE_FIELDS)
            if bad:
                raise WorkspaceError(f"not editable: {', '.join(sorted(bad))}")
            old = pl.items[idx]
            data = {**old.model_dump(), **changes}
            if "stage" in changes and changes["stage"] != old.stage:
                data["moved_at"] = utcnow()
            try:
                pl.items[idx] = PipelineItem.model_validate(data)
            except ValueError as exc:
                raise WorkspaceError(f"invalid pipeline item: {exc}") from exc
            self._save("pipeline.json", pl)
            self.after_change()
            return pl.items[idx]

    def delete_pipeline_item(self, item_id: str) -> None:
        with self.lock:
            pl = self.pipeline()
            kept = [p for p in pl.items if p.id != item_id]
            if len(kept) == len(pl.items):
                raise NotFound(f"no pipeline item {item_id!r}")
            pl.items = kept
            self._save("pipeline.json", pl)
            self.after_change()

    # ------------------------------------------------------------------ uploads

    MAX_UPLOAD_BYTES = 25 * 1024 * 1024

    def classify_upload(self, filename: str) -> tuple[str, str, str | None]:
        """(criterion, evidence_type, stage) guess for a dropped file. The domain layer knows the rubric."""
        return "", "document", None

    def stage_upload(self, content: bytes, filename: str, criterion: str | None = None) -> Candidate:
        """A dropped file: snapshot it in memory/ and propose it in the Inbox. Accepting files it as an exhibit."""
        if len(content) > self.MAX_UPLOAD_BYTES:
            raise WorkspaceError(f"{filename} is larger than 25 MB")
        if not content:
            raise WorkspaceError(f"{filename} is empty")
        name = Path(filename).name or "upload.bin"
        guessed_crit, etype, stage = self.classify_upload(name)
        if criterion:
            self.validate_criterion(criterion)
            if criterion != guessed_crit:
                etype, stage = "document", None
        crit = criterion or guessed_crit
        with self.lock:
            obs = self.memory.record_file(content, filename=name, media_type=_media_type(name))
            title = re.sub(r"[_\-]+", " ", Path(name).stem).strip() or name
            cand = Candidate(
                fingerprint=f"upload:{obs.sha256}",
                source="upload",
                evidence_type=etype,
                proposed_criterion=crit,
                title=title[:120],
                summary=f"Uploaded {name} ({_size(len(content))}). Check the criterion, type and stage, then accept.",
                confidence=0.6 if crit else 0.3,
                stage=stage,  # type: ignore[arg-type]
                attachment=obs.id,
                source_tier="user",
            )
            added = self.add_candidates([cand])
            if not added:
                existing = next(
                    (c for c in self.inbox().candidates if c.fingerprint == cand.fingerprint), None
                )
                if existing is None:
                    raise WorkspaceError(f"{name} is already filed as an exhibit")
                return existing
            self.after_change()
            return cand

    # ------------------------------------------------------------------ evidence

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
        stage: str | None = None,
    ) -> Exhibit:
        """Manual upload: the user is filing this themselves, so it becomes an exhibit directly."""
        with self.lock:
            self.validate_criterion(criterion)
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
                stage=stage,  # type: ignore[arg-type]
            )
            ex = self.exhibits()
            ex.exhibits.append(exhibit)
            self.save_exhibits(ex)
            self.after_change()
            return exhibit

    def remap_exhibit(self, exhibit_id: str, criterion: str, evidence_type: str | None = None) -> Exhibit:
        """File an exhibit under another criterion, moving and renaming its file to match."""
        with self.lock:
            self.validate_criterion(criterion)
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
            rows = list(rows)
            # Each connector response behind these rows becomes an observation with metric claims.
            recorded: set[int] = set()
            for row in rows:
                if row._evidence is not None and id(row._evidence) not in recorded:
                    recorded.add(id(row._evidence))
                    self.memory.record(row._evidence)
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


def _media_type(filename: str) -> str:
    import mimetypes

    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB" if n >= 1024 * 1024 else f"{max(1, n // 1024)} KB"
