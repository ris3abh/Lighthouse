"""Evidence-aware graph memory (SPEC 5b): append-only JSONL files plus a rebuildable SQLite index.

Layout inside a workspace::

    memory/observations.jsonl   raw captures (one line each, deduplicated by sha256)
    memory/entities.jsonl       people, artifacts, orgs, events ...
    memory/claims.jsonl         one factual statement per line, with exact excerpt + offsets
    memory/edges.jsonl          DERIVED_FROM, ABOUT, SUPERSEDES, REVIEWED_BY, CITES, ...
    memory/decisions.jsonl      review records (approved / rejected)
    memory/sources/<sha256>.*   the snapshot text that excerpts index into

Nothing is rewritten in place. Review status is derived: the latest decision wins; otherwise a claim
is ``corroborated`` when two independent connectors observed the same subject/predicate/value, else
``proposed``. The index (``.areao1/cache/memory.db``) can always be deleted and rebuilt.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from datetime import date
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from areao1.core import clock
from areao1.core.models import (
    Claim,
    ClaimDraft,
    Decision,
    Edge,
    Entity,
    Evidence,
    ExtractedBy,
    Observation,
    ReviewStatus,
    canonical_text,
)

M = TypeVar("M", bound=BaseModel)

FILES = {
    "observations": Observation,
    "entities": Entity,
    "claims": Claim,
    "edges": Edge,
    "decisions": Decision,
}
_EXT = {"application/json": "json", "text/markdown": "md", "text/plain": "txt", "text/html": "html"}
TEXT_TYPES = frozenset(_EXT)


class MemoryError(Exception):
    pass


class Memory:
    def __init__(self, root: Path, cache_dir: Path):
        self.dir = root / "memory"
        self.root = root
        self.index_path = cache_dir / "memory.db"
        self.lock = threading.RLock()
        self._obs_cache: tuple[tuple[int, int], dict[str, Observation]] | None = None

    # ------------------------------------------------------------------ raw io

    def _path(self, name: str) -> Path:
        return self.dir / f"{name}.jsonl"

    def _read(self, name: str, model: type[M]) -> Iterator[M]:
        path = self._path(name)
        if not path.exists():
            return
        with path.open(encoding="utf-8") as fh:
            for n, line in enumerate(fh, 1):
                if line.strip():
                    try:
                        yield model.model_validate_json(line)
                    except ValueError as exc:
                        raise MemoryError(f"memory/{name}.jsonl line {n}: {exc}") from exc

    def _append(self, name: str, records: Iterable[BaseModel]) -> None:
        lines = [r.model_dump_json() + "\n" for r in records]
        if not lines:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        with self._path(name).open("a", encoding="utf-8") as fh:
            fh.writelines(lines)

    def init(self) -> None:
        (self.dir / "sources").mkdir(parents=True, exist_ok=True)
        (self.dir / "sources" / ".gitkeep").touch()
        for name in FILES:
            self._path(name).touch()

    # ------------------------------------------------------------------ readers

    def observations(self) -> list[Observation]:
        return list(self._read("observations", Observation))

    def entities(self) -> list[Entity]:
        return list(self._read("entities", Entity))

    def claims(self) -> list[Claim]:
        return list(self._read("claims", Claim))

    def edges(self) -> list[Edge]:
        return list(self._read("edges", Edge))

    def decisions(self) -> list[Decision]:
        return list(self._read("decisions", Decision))

    def snapshot_text(self, obs: Observation) -> str:
        return (self.root / obs.snapshot).read_text(encoding="utf-8")

    # ------------------------------------------------------------------ writes

    def record(self, evidence: Evidence) -> list[Claim]:
        """Store an observation (deduplicated by content hash) and the claims drawn from it.

        Each draft's excerpt must occur verbatim in the snapshot, so every claim can be checked
        against the exact text it came from. A claim identical to the current one for the same
        subject + predicate is not repeated; a different value appends a new claim that SUPERSEDES it.
        """
        with self.lock:
            text = canonical_text(evidence.payload, evidence.media_type)
            obs = self._observe(evidence, text)
            entities = {e.id for e in self._read("entities", Entity)}
            current = self._current_claims()
            new_entities: list[Entity] = []
            new_claims: list[Claim] = []
            new_edges: list[Edge] = []
            out: list[Claim] = []
            for draft in evidence.claims:
                prior = current.get((draft.subject, draft.predicate))
                if prior and _same(prior, draft) and prior.extracted_by.name == evidence.connector:
                    out.append(prior)
                    continue
                # Same value from another connector corroborates; a different value supersedes.
                supersedes = prior if prior and not _same(prior, draft) else None
                start = text.find(draft.excerpt)
                if start < 0:
                    raise MemoryError(
                        f"excerpt not found in {evidence.source_url}: {draft.excerpt!r} — claims must quote their source"
                    )
                claim = Claim(
                    subject=draft.subject,
                    predicate=draft.predicate,
                    value=draft.value,
                    stage=draft.stage,
                    event_date=draft.event_date,
                    valid_from=draft.valid_from or clock.today(),
                    observation_id=obs.id,
                    excerpt=draft.excerpt,
                    excerpt_start=start,
                    excerpt_end=start + len(draft.excerpt),
                    extracted_by=ExtractedBy(kind="connector", name=evidence.connector),
                    confidence=draft.confidence,
                    version=(prior.version + 1) if supersedes and prior else (prior.version if prior else 1),
                )
                if draft.subject not in entities:
                    entities.add(draft.subject)
                    new_entities.append(
                        Entity(
                            id=draft.subject,
                            kind=draft.subject_kind,
                            name=draft.subject_name,
                            url=draft.subject_url,
                        )
                    )
                new_edges.append(Edge(type="DERIVED_FROM", src=claim.id, dst=obs.id))
                new_edges.append(Edge(type="ABOUT", src=claim.id, dst=draft.subject))
                if supersedes:
                    new_edges.append(Edge(type="SUPERSEDES", src=claim.id, dst=supersedes.id))
                current[(draft.subject, draft.predicate)] = claim
                new_claims.append(claim)
                out.append(claim)
            self._append("entities", new_entities)
            self._append("claims", new_claims)
            self._append("edges", new_edges)
            return out

    def _observe(self, evidence: Evidence, text: str) -> Observation:
        return self._store(
            text.encode("utf-8"),
            ext=_EXT.get(evidence.media_type, "txt"),
            connector=evidence.connector,
            source_url=evidence.source_url,
            media_type=evidence.media_type,
            tier=evidence.tier,
            filename=evidence.filename,
        )

    def snapshot(self, evidence: Evidence) -> Observation:
        """Store an observation without claims (e.g. a page an agent read) and return it."""
        with self.lock:
            return self._observe(evidence, canonical_text(evidence.payload, evidence.media_type))

    def record_file(
        self, content: bytes, *, filename: str, media_type: str, connector: str = "upload", tier: str = "user"
    ) -> Observation:
        """Snapshot an uploaded file byte-for-byte (content-addressed, deduplicated)."""
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
        if not ext.isalnum() or len(ext) > 8:
            ext = "bin"
        with self.lock:
            return self._store(
                content, ext=ext, connector=connector, source_url=f"upload:{filename}",
                media_type=media_type, tier=tier, filename=filename,
            )  # fmt: skip

    def _store(
        self,
        data: bytes,
        *,
        ext: str,
        connector: str,
        source_url: str,
        media_type: str,
        tier: str | None,
        filename: str | None,
    ) -> Observation:
        sha = hashlib.sha256(data).hexdigest()
        # One observation per (source, content): the same text read at two URLs is two observations (each with
        # its own provenance) sharing one content-addressed snapshot file.
        obs_id = "obs_" + hashlib.sha256(f"{source_url}\n{sha}".encode()).hexdigest()[:16]
        known = self._observation_index()
        if obs_id in known:
            return known[obs_id]
        rel = f"memory/sources/{sha}.{ext}"
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        obs = Observation(
            id=obs_id,
            connector=connector,
            source_url=source_url,
            sha256=sha,
            snapshot=rel,
            media_type=media_type,
            tier=tier,  # type: ignore[arg-type]
            filename=filename,
        )
        self._append("observations", [obs])
        known[obs_id] = obs
        self._obs_cache = (self._stamp("observations"), known)
        return obs

    def _stamp(self, name: str) -> tuple[int, int]:
        path = self._path(name)
        if not path.exists():
            return (0, 0)
        st = path.stat()
        return (st.st_size, st.st_mtime_ns)

    def _observation_index(self) -> dict[str, Observation]:
        """id -> observation, cached until observations.jsonl changes on disk (e.g. another process)."""
        stamp = self._stamp("observations")
        if self._obs_cache is None or self._obs_cache[0] != stamp:
            self._obs_cache = (stamp, {o.id: o for o in self._read("observations", Observation)})
        return self._obs_cache[1]

    def observation(self, obs_id: str) -> Observation | None:
        return self._observation_index().get(obs_id)

    def _current_claims(self) -> dict[tuple[str, str], Claim]:
        """Latest claim per (subject, predicate): the ones nothing has superseded."""
        latest: dict[tuple[str, str], Claim] = {}
        for c in self._read("claims", Claim):
            latest[(c.subject, c.predicate)] = c  # file order == recorded order
        return latest

    def decide(
        self, claim_ids: Iterable[str], decision: str, rationale: str = "", reviewer: str = "user"
    ) -> None:
        with self.lock:
            known = {c.id for c in self._read("claims", Claim)}
            records, edges = [], []
            for cid in claim_ids:
                if cid not in known:
                    raise MemoryError(f"no claim {cid!r}")
                rec = Decision(claim_id=cid, decision=decision, rationale=rationale, reviewer=reviewer)  # type: ignore[arg-type]
                records.append(rec)
                edges.append(Edge(type="REVIEWED_BY", src=cid, dst=rec.id))
            self._append("decisions", records)
            self._append("edges", edges)

    def cite(self, src: str, claim_ids: Iterable[str]) -> None:
        """Record that an exhibit or generated sentence relies on these claims."""
        with self.lock:
            self._append("edges", [Edge(type="CITES", src=src, dst=cid) for cid in claim_ids])

    # ------------------------------------------------------------------ derived views

    def statuses(self) -> dict[str, ReviewStatus]:
        claims = self.claims()
        observations = {o.id: o for o in self.observations()}
        decided: dict[str, ReviewStatus] = {}
        for d in self.decisions():
            if (
                d.decision == "reopened"
            ):  # an undone decision: back to waiting (append-only, the history stays)
                decided.pop(d.claim_id, None)
            else:
                decided[d.claim_id] = d.decision
        connectors: dict[tuple[str, str, str], set[str]] = {}
        for c in claims:
            key = (c.subject, c.predicate, json.dumps(c.value))
            obs = observations.get(c.observation_id)
            connectors.setdefault(key, set()).add(obs.connector if obs else c.extracted_by.name)
        out: dict[str, ReviewStatus] = {}
        for c in claims:
            if c.id in decided:
                out[c.id] = decided[c.id]
            elif len(connectors[(c.subject, c.predicate, json.dumps(c.value))]) >= 2:
                out[c.id] = "corroborated"
            else:
                out[c.id] = "proposed"
        return out

    def verify(self) -> list[str]:
        """Exact-quote check for every claim, plus dangling references. Empty list = consistent."""
        problems: list[str] = []
        try:
            observations = {o.id: o for o in self.observations()}
            claims = self.claims()
            ids = set(observations) | {c.id for c in claims} | {e.id for e in self.entities()}
            ids |= {d.id for d in self.decisions()}
            edges = self.edges()
        except MemoryError as exc:
            return [str(exc)]
        texts: dict[str, str] = {}
        for obs in observations.values():
            path = self.root / obs.snapshot
            if not path.exists():
                problems.append(f"{obs.snapshot}: snapshot missing for {obs.id}")
                continue
            data = path.read_bytes()
            if hashlib.sha256(data).hexdigest() != obs.sha256:
                problems.append(f"{obs.snapshot}: content no longer matches its sha256")
            if obs.media_type in TEXT_TYPES:
                texts[obs.id] = data.decode("utf-8", errors="replace")
        for c in claims:
            snap = texts.get(c.observation_id)
            if snap is None:
                problems.append(f"claim {c.id}: observation {c.observation_id} missing")
            elif snap[c.excerpt_start : c.excerpt_end] != c.excerpt:
                problems.append(f"claim {c.id}: excerpt does not match the snapshot at the recorded offsets")
        for e in edges:
            if e.src not in ids and not e.src.startswith("exh_"):
                problems.append(f"edge {e.id}: unknown source {e.src}")
            if e.type != "CITES" and e.dst not in ids:
                problems.append(f"edge {e.id}: unknown target {e.dst}")
        return problems

    # ------------------------------------------------------------------ index

    def _index_stale(self) -> bool:
        if not self.index_path.exists():
            return True
        built = self.index_path.stat().st_mtime
        return any(self._path(n).exists() and self._path(n).stat().st_mtime > built for n in FILES)

    def rebuild_index(self) -> Path:
        """(Re)build the SQLite index from the JSONL files. Safe to delete at any time."""
        with self.lock:
            self.index_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.index_path.with_suffix(".tmp")
            tmp.unlink(missing_ok=True)
            statuses = self.statuses()
            superseded = {e.dst for e in self.edges() if e.type == "SUPERSEDES"}
            con = sqlite3.connect(tmp)
            con.executescript(
                """
                CREATE TABLE claims (id TEXT PRIMARY KEY, subject TEXT, predicate TEXT, value TEXT, stage TEXT,
                    valid_from TEXT, recorded_at TEXT, status TEXT, current INTEGER, json TEXT);
                CREATE INDEX claims_subject ON claims(subject, predicate);
                CREATE TABLE edges (id TEXT PRIMARY KEY, type TEXT, src TEXT, dst TEXT);
                CREATE INDEX edges_src ON edges(src); CREATE INDEX edges_dst ON edges(dst);
                """
            )
            con.executemany(
                "INSERT INTO claims VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    (
                        c.id,
                        c.subject,
                        c.predicate,
                        json.dumps(c.value),
                        c.stage,
                        c.valid_from.isoformat() if c.valid_from else None,
                        c.recorded_at.isoformat(),
                        statuses[c.id],
                        int(c.id not in superseded),
                        c.model_dump_json(),
                    )
                    for c in self.claims()
                ],  # fmt: skip
            )
            con.executemany(
                "INSERT INTO edges VALUES (?,?,?,?)", [(e.id, e.type, e.src, e.dst) for e in self.edges()]
            )
            con.commit()
            con.close()
            tmp.replace(self.index_path)
            return self.index_path

    def query_claims(
        self,
        subject: str | None = None,
        predicate: str | None = None,
        status: str | None = None,
        as_of: date | None = None,
        current_only: bool = True,
    ) -> list[tuple[Claim, str]]:
        """Claims with their review status. ``as_of`` answers "what did we believe on that day?"."""
        if self._index_stale():
            self.rebuild_index()
        sql = "SELECT json, status FROM claims WHERE 1=1"
        args: list[str] = []
        if subject:
            sql, args = sql + " AND subject = ?", [*args, subject]
        if predicate:
            sql, args = sql + " AND predicate = ?", [*args, predicate]
        if status:
            sql, args = sql + " AND status = ?", [*args, status]
        if as_of:
            # Bitemporal: true in the world by then AND already known to Area O1 by then.
            # "Known by then" means recorded before the end of that day where the person is (recorded_at is UTC).
            cutoff = clock.end_of_day_utc(as_of)
            sql += " AND (valid_from IS NULL OR valid_from <= ?) AND recorded_at < ?"
            args = [*args, as_of.isoformat(), cutoff.isoformat()]
        elif current_only:
            sql += " AND current = 1"
        sql += " ORDER BY recorded_at"
        con = sqlite3.connect(self.index_path)
        try:
            rows = [(Claim.model_validate_json(j), s) for j, s in con.execute(sql, args)]
        finally:
            con.close()
        if as_of:
            # Keep the latest claim per subject/predicate known on that day.
            latest: dict[tuple[str, str], tuple[Claim, str]] = {}
            for claim, s in rows:
                latest[(claim.subject, claim.predicate)] = (claim, s)
            rows = list(latest.values())
        return rows


def _same(prior: Claim, draft: ClaimDraft) -> bool:
    return prior.value == draft.value and prior.stage == draft.stage
