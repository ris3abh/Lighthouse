"""The knowledge vault store (SPEC 5a).

* Each source in the manifest is fetched through the shared public-web guard, turned into plain text, cut to
  the part that matters and stored content-addressed (sha256 of the text) under
  ``.lighthouse/cache/vault/snapshots``. Old snapshots are kept, so you can see what a page said before.
* The current snapshot of each source is chunked (every chunk is an exact slice of the snapshot text, with
  offsets, so a quote can be checked character for character) and indexed for full-text search (SQLite FTS5)
  and local embeddings, fused with reciprocal-rank fusion.
* Freshness: a source is fresh until its last successful check plus its kind's window from the manifest's
  ``ttl_days`` registry. Bot-blocked or failed fetches never refresh it.
* Every fetch that finds something (new, changed, unreadable, error) is appended to the workspace's
  ``vault/log.jsonl``; content and the index live in the cache and are rebuildable.
"""

from __future__ import annotations

import difflib
import gzip
import hashlib
import json
import re
import sqlite3
import threading
from array import array
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any

import anyio
import httpx
import yaml

from lighthouse_gc import web
from lighthouse_gc.core import clock
from lighthouse_gc.core.models import utcnow
from lighthouse_gc.core.workspace import Workspace, _atomic_write
from lighthouse_gc.resources import vault_manifest_path
from lighthouse_gc.vault.embed import Embedder, default_embedder, dot, tokens
from lighthouse_gc.vault.extract import cut, effective_date, normalize, to_text
from lighthouse_gc.vault.models import DiffSummary, VaultFetch, VaultHit, VaultManifest, VaultSource

_DB_LOCK = threading.RLock()
_READY: set[str] = set()
MAX_VAULT_BYTES = 15_000_000  # fee schedules and policy chapters are big PDFs / pages
MIN_TEXT = 200
CHUNK_TARGET = 900
CHUNK_MAX = 1600
ECFR_TITLES = "https://www.ecfr.gov/api/versioner/v1/titles.json"
MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december")  # fmt: skip

# Exact figures and identifiers in a query: amounts with thousands separators, form-style numbers (I-129, G-1055),
# dotted section numbers (214.2, 204.5).
EXACT = re.compile(r"\$?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\b[A-Z]{1,2}-\d{2,5}[A-Z]{0,2}\b|\b\d+(?:\.\d+)+\b")

SCHEMA = """
create table if not exists state(
  source_id text primary key, url text, title text, sha text, checked_at text, fetched_at text,
  effective_date text, status text, error text);
create table if not exists snapshots(
  sha text, source_id text, url text, fetched_at text, effective_date text, chars int,
  primary key (sha, source_id));
create table if not exists chunks(
  rid integer primary key, id text unique, sha text, source_id text, ord int, start int, stop int,
  text text, embedder text, vec blob);
create index if not exists chunks_by_snapshot on chunks(source_id, sha);
create virtual table if not exists chunks_fts using fts5(text, content='chunks', content_rowid='rid',
  tokenize='porter unicode61');
"""


def load_manifest(override: Path | None = None) -> VaultManifest:
    """The bundled manifest, with a workspace's own vault/sources.yaml merged in (sources replaced by id)."""
    base = VaultManifest.model_validate(yaml.safe_load(vault_manifest_path().read_text(encoding="utf-8")))
    if override is None or not override.exists():
        return base
    data = yaml.safe_load(override.read_text(encoding="utf-8")) or {}
    # The override's sources may point at bundled ones (secondary_to); that's checked after the merge.
    extra = VaultManifest.model_validate({**data, "sources": []})
    extra.sources = [VaultSource.model_validate(s) for s in data.get("sources") or []]
    by_id = {s.id: s for s in base.sources}
    by_id.update({s.id: s for s in extra.sources})
    return VaultManifest(
        ttl_days={**base.ttl_days, **extra.ttl_days},
        tier1_domains=sorted({*base.tier1_domains, *extra.tier1_domains}),
        tier2_domains=sorted({*base.tier2_domains, *extra.tier2_domains}),
        rule_hints=[*base.rule_hints, *(h for h in extra.rule_hints if h not in base.rule_hints)],
        sources=list(by_id.values()),
    )


def chunk_text(text: str) -> list[tuple[int, int]]:
    """(start, stop) offsets of chunks: whole lines up to ~900 chars, long lines split at sentence ends."""
    spans: list[tuple[int, int]] = []
    pos = 0
    pieces: list[tuple[int, int]] = []
    for line in text.split("\n"):
        start, stop = pos, pos + len(line)
        pos = stop + 1
        if not line.strip():
            continue
        while stop - start > CHUNK_MAX:
            cut_at = text.rfind(". ", start, start + CHUNK_MAX)
            cut_at = cut_at + 1 if cut_at > start + CHUNK_TARGET // 2 else start + CHUNK_MAX
            pieces.append((start, cut_at))
            start = cut_at + 1 if text[cut_at : cut_at + 1] == " " else cut_at
        pieces.append((start, stop))
    cur: tuple[int, int] | None = None
    for s, e in pieces:
        if cur is None:
            cur = (s, e)
        elif e - cur[0] <= CHUNK_TARGET:
            cur = (cur[0], e)
        else:
            spans.append(cur)
            cur = (s, e)
    if cur:
        spans.append(cur)
    return spans


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


class Vault:
    def __init__(
        self, ws: Workspace, manifest: VaultManifest | None = None, embedder: Embedder | None = None
    ):
        self.ws = ws
        self._manifest = manifest
        self._fixed = manifest is not None  # an explicit manifest (tests) is never reloaded
        self._key: tuple[int, int] = (0, 0)
        self.embedder = embedder or default_embedder()
        self.dir = ws.cache_dir / "vault"
        self.snapshots = self.dir / "snapshots"
        self.db_path = self.dir / "vault.db"
        self.log_path = ws.root / "vault" / "log.jsonl"

    # ------------------------------------------------------------------ manifest + db

    def _files_key(self) -> tuple[int, int]:
        paths = (self.ws.root / "vault" / "sources.yaml", self.ws.root / "vault" / "findings.jsonl")
        return tuple(p.stat().st_mtime_ns if p.exists() else 0 for p in paths)  # type: ignore[return-value]

    @property
    def manifest(self) -> VaultManifest:
        if self._fixed:
            assert self._manifest is not None
            return self._manifest
        key = self._files_key()
        if self._manifest is None or key != self._key:
            self._key = key
            m = load_manifest(self.ws.root / "vault" / "sources.yaml")
            known = {s.id for s in m.sources}
            m.sources += [f for f in self.findings() if f.id not in known]
            self._manifest = m
        return self._manifest

    # ------------------------------------------------------------------ findings

    @property
    def findings_path(self) -> Path:
        return self.ws.root / "vault" / "findings.jsonl"

    def findings(self) -> list[VaultSource]:
        """Official pages the agent read (Tier 1/2 domains): observations, searchable, not reviewed sources."""
        if not self.findings_path.exists():
            return []
        out = []
        for line in self.findings_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                out.append(VaultSource(id=d["id"], title=d["title"][:200] or d["url"], url=d["url"], tier=d["tier"],
                                       kind="finding", finding=True, notes=f"found by {d.get('run_id') or 'the agent'}"))  # fmt: skip
        return out

    def add_finding(self, url: str, title: str, text: str, run_id: str | None = None) -> VaultFetch | None:
        """Keep an official page the agent read as a vault observation. Pages off the Tier 1/2 domains are ignored."""
        tier = self.manifest.tier_of(url)
        if tier is None or len(text.strip()) < MIN_TEXT:
            return None
        sid = "found-" + hashlib.sha256(url.encode()).hexdigest()[:12]
        source = self.manifest.source(sid)
        if source is None:
            self.findings_path.parent.mkdir(parents=True, exist_ok=True)
            with self.findings_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({"id": sid, "url": url, "title": title or url, "tier": tier,
                                    "found_at": utcnow().isoformat(), "run_id": run_id}) + "\n")  # fmt: skip
            source = self.manifest.source(sid)
            assert source is not None
        text = normalize(text)
        return self._store(source, url, title, text, effective_date(text), self.state().get(sid), "agent")

    @contextmanager
    def db(self) -> Iterator[sqlite3.Connection]:
        """One short transaction. Serialized within the process (fetches run concurrently and indexing runs in a
        worker thread); ``BEGIN IMMEDIATE`` makes other processes (CLI, server) wait instead of failing."""
        self.dir.mkdir(parents=True, exist_ok=True)
        with _DB_LOCK:
            fresh_file = not self.db_path.exists()
            con = sqlite3.connect(self.db_path, timeout=30, isolation_level=None)
            try:
                con.row_factory = sqlite3.Row
                if fresh_file or str(self.db_path) not in _READY:
                    con.execute("pragma journal_mode=wal")
                    con.executescript(SCHEMA)
                    _READY.add(str(self.db_path))
                con.execute("begin immediate")
                try:
                    yield con
                except BaseException:
                    con.execute("rollback")
                    raise
                con.execute("commit")
            finally:
                con.close()

    # ------------------------------------------------------------------ snapshots

    def _snapshot_path(self, sha: str) -> Path:
        return self.snapshots / sha[:2] / f"{sha}.txt.gz"

    def snapshot_text(self, sha: str) -> str:
        return gzip.decompress(self._snapshot_path(sha).read_bytes()).decode("utf-8")

    def _write_snapshot(self, sha: str, text: str) -> None:
        path = self._snapshot_path(sha)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_write(path, gzip.compress(text.encode("utf-8"), mtime=0))

    # ------------------------------------------------------------------ fetch log

    def log(self) -> list[VaultFetch]:
        if not self.log_path.exists():
            return []
        return [
            VaultFetch.model_validate_json(line) for line in self.log_path.read_text().splitlines() if line
        ]

    def _append_log(self, entry: VaultFetch) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(entry.model_dump_json() + "\n")

    # ------------------------------------------------------------------ urls

    async def _resolve(
        self, source: VaultSource, client: httpx.AsyncClient, cache: dict[str, Any]
    ) -> tuple[str, date | None]:
        values = _date_values()
        hint = None
        if "{ecfr_date}" in source.url:
            if "ecfr" not in cache:
                page = await web.get(ECFR_TITLES, client)
                cache["ecfr"] = {t["number"]: t for t in json.loads(page.text)["titles"]}
            title = cache["ecfr"].get(source.ecfr_title)
            if not title or not title.get("latest_issue_date"):
                raise ValueError(f"no current eCFR date for title {source.ecfr_title}")
            values["ecfr_date"] = title["latest_issue_date"]
            hint = date.fromisoformat(title["up_to_date_as_of"] or title["latest_issue_date"])
        return source.url.format(**values), hint

    # ------------------------------------------------------------------ sync

    def state(self) -> dict[str, dict[str, Any]]:
        with self.db() as con:
            return {r["source_id"]: dict(r) for r in con.execute("select * from state")}

    def is_fresh(self, source: VaultSource, checked_at: datetime | None, now: datetime | None = None) -> bool:
        return checked_at is not None and (now or utcnow()) < self.manifest.expires_at(source, checked_at)

    def due(self, source: VaultSource, state: dict[str, Any] | None, *, tier1_daily: bool) -> bool:
        checked = _dt(state.get("checked_at")) if state else None
        if not self.is_fresh(source, checked):
            return True
        return tier1_daily and source.tier == 1 and (utcnow() - checked).total_seconds() > 20 * 3600  # type: ignore[operator]

    async def sync(self, ids: list[str] | None = None, *, force: bool = False, tier1_daily: bool = False,
                   client: httpx.AsyncClient | None = None) -> list[VaultFetch]:  # fmt: skip
        """Fetch the sources that are due (expired, never fetched, or all Tier 1 when ``tier1_daily``)."""
        state = self.state()
        sources = [s for s in self.manifest.sources if s.enabled and (ids is None or s.id in ids)]
        if ids:
            unknown = set(ids) - {s.id for s in sources}
            if unknown:
                raise ValueError(f"unknown or disabled vault source(s): {sorted(unknown)}")
        # Findings (pages the agent read) aren't watched; they refresh when the agent reads them again.
        todo = [
            s
            for s in sources
            if force or ids or (not s.finding and self.due(s, state.get(s.id), tier1_daily=tier1_daily))
        ]
        own = client is None
        client = client or httpx.AsyncClient(timeout=30.0, headers={"User-Agent": web.user_agent("vault")})
        results: list[VaultFetch] = []
        cache: dict[str, Any] = {}
        limit = anyio.Semaphore(3)

        async def one(source: VaultSource) -> None:
            async with limit:
                results.append(await self._fetch(source, client, cache, state.get(source.id)))

        try:
            async with anyio.create_task_group() as tg:
                for s in todo:
                    tg.start_soon(one, s)
        finally:
            if own:
                await client.aclose()
        order = {s.id: i for i, s in enumerate(todo)}
        return sorted(results, key=lambda r: order[r.source_id])

    async def _fetch(self, source: VaultSource, client: httpx.AsyncClient, cache: dict[str, Any],
                     prev: dict[str, Any] | None) -> VaultFetch:  # fmt: skip
        url = source.url
        try:
            url, hint = await self._resolve(source, client, cache)
            page = await web.get(url, client, max_bytes=MAX_VAULT_BYTES)
            allowed = self.manifest.tier_of(page.url)
            if source.tier < 3 and (allowed is None or source.tier < allowed):
                raise ValueError(f"redirected off the official domains to {page.url}; not stored as a Tier "
                                 f"{source.tier} source")  # fmt: skip
            title, text = await anyio.to_thread.run_sync(
                to_text, page.content, page.content_type, source.format
            )
            text = cut(text, source.start, source.end)
            if len(text) < MIN_TEXT:
                raise web.Unreadable(f"{page.url} has almost no readable text (it may need JavaScript)")
        except web.Unreadable as exc:
            return self._failed(source, url, "unreadable", str(exc), prev)
        except (web.UnsafeURL, ValueError, httpx.HTTPError, KeyError) as exc:
            return self._failed(source, url, "error", f"{type(exc).__name__}: {exc}"[:500], prev)
        raw = page.text if "html" in page.content_type else ""
        eff = effective_date(text, raw) or hint
        return await anyio.to_thread.run_sync(self._store, source, page.url, title, text, eff, prev, "fetch")

    def _store(self, source: VaultSource, url: str, title: str, text: str, eff: date | None,
               prev: dict[str, Any] | None, origin: str) -> VaultFetch:  # fmt: skip
        sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        now = utcnow()
        previous = prev.get("sha") if prev else None
        with self.db() as con:
            if sha == previous:
                con.execute("update state set checked_at=?, status='ok', error=null, url=? where source_id=?",
                            (now.isoformat(), url, source.id))  # fmt: skip
                return VaultFetch(source_id=source.id, url=url, tier=source.tier, fetched_at=now, origin=origin,  # type: ignore[arg-type]
                                  status="unchanged", sha256=sha, effective_date=eff, chars=len(text))  # fmt: skip
        self._write_snapshot(sha, text)
        self._index(source.id, sha, text)
        with self.db() as con:
            con.execute("insert or ignore into snapshots values (?,?,?,?,?,?)",
                        (sha, source.id, url, now.isoformat(), _iso_date(eff), len(text)))  # fmt: skip
            con.execute("insert or replace into state values (?,?,?,?,?,?,?,'ok',null)",
                        (source.id, url, title or source.title, sha, now.isoformat(), now.isoformat(),
                         _iso_date(eff)))  # fmt: skip
        diff = (
            _diff(self.snapshot_text(previous), text)
            if previous and self._snapshot_path(previous).exists()
            else None
        )
        entry = VaultFetch(source_id=source.id, url=url, tier=source.tier, fetched_at=now, origin=origin,  # type: ignore[arg-type]
                           status="changed" if previous else "new", sha256=sha, previous_sha256=previous,
                           effective_date=eff, chars=len(text), diff=diff)  # fmt: skip
        self._append_log(entry)
        return entry

    def import_file(
        self, source_id: str, content: bytes, filename: str = "", content_type: str = ""
    ) -> VaultFetch:
        """Store a page the person saved from their browser (for sites that block automated reading) as that
        source's snapshot. It goes through the same extraction and cut, and counts as checked now."""
        source = self.manifest.source(source_id)
        if source is None:
            raise ValueError(f"unknown vault source {source_id!r}")
        if not content_type:
            ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
            content_type = {"pdf": "application/pdf", "html": "text/html", "htm": "text/html", "xml": "text/xml",
                            "json": "application/json", "txt": "text/plain"}.get(ext, "")  # fmt: skip
        title, text = to_text(content, content_type, source.format)
        text = cut(text, source.start, source.end)
        if len(text) < MIN_TEXT:
            raise ValueError(
                "that file has almost no readable text; save the page as HTML (or PDF) from your browser"
            )
        raw = content.decode("utf-8", errors="replace") if "html" in content_type else ""
        if web.blocked_reason(200, title, raw) is not None:
            raise ValueError(
                "that file is a bot-check page, not the source; open the page in your browser first"
            )
        prev = self.state().get(source.id)
        url = source.url if "{" not in source.url else (prev or {}).get("url") or source.url
        return self._store(source, url, title, text, effective_date(text, raw), prev, "manual")

    def _failed(
        self, source: VaultSource, url: str, status: str, error: str, prev: dict[str, Any] | None
    ) -> VaultFetch:
        with self.db() as con:
            if prev:
                con.execute(
                    "update state set status=?, error=? where source_id=?", (status, error, source.id)
                )
            else:
                con.execute("insert into state (source_id, url, title, status, error) values (?,?,?,?,?)",
                            (source.id, url, source.title, status, error))  # fmt: skip
        entry = VaultFetch(source_id=source.id, url=url, tier=source.tier, status=status, error=error,  # type: ignore[arg-type]
                           previous_sha256=prev.get("sha") if prev else None)  # fmt: skip
        self._append_log(entry)
        return entry

    # ------------------------------------------------------------------ index

    def _index(self, source_id: str, sha: str, text: str) -> None:
        spans = chunk_text(text)
        vecs = self.embedder.embed([text[s:e] for s, e in spans])
        with self.db() as con:
            for row in con.execute(
                "select rid, text from chunks where source_id=? and sha!=?", (source_id, sha)
            ):
                con.execute("insert into chunks_fts(chunks_fts, rowid, text) values('delete', ?, ?)",
                            (row["rid"], row["text"]))  # fmt: skip
            con.execute("delete from chunks where source_id=? and sha!=?", (source_id, sha))
            if con.execute(
                "select 1 from chunks where source_id=? and sha=? limit 1", (source_id, sha)
            ).fetchone():
                return
            for i, ((s, e), vec) in enumerate(zip(spans, vecs, strict=True)):
                cid = f"vc_{sha[:12]}_{i:04d}"
                cur = con.execute("insert into chunks (id, sha, source_id, ord, start, stop, text, embedder, vec) "
                                  "values (?,?,?,?,?,?,?,?,?)",
                                  (cid, sha, source_id, i, s, e, text[s:e], self.embedder.name, vec.tobytes()))  # fmt: skip
                con.execute("insert into chunks_fts(rowid, text) values (?, ?)", (cur.lastrowid, text[s:e]))

    def reindex(self) -> int:
        """Rebuild the chunk index from the snapshots (e.g. after changing the embedder)."""
        with self.db() as con:
            con.execute("delete from chunks")
            con.execute("insert into chunks_fts(chunks_fts) values('delete-all')")
            current = [
                (r["source_id"], r["sha"])
                for r in con.execute("select source_id, sha from state where sha is not null")
            ]
        for source_id, sha in current:
            self._index(source_id, sha, self.snapshot_text(sha))
        return len(current)

    # ------------------------------------------------------------------ search

    def search(self, query: str, k: int = 8, *, tiers: set[int] | None = None, topics: set[str] | None = None,
               kinds: set[str] | None = None, fresh_only: bool = False, findings: bool = True,
               sources: set[str] | None = None) -> list[VaultHit]:  # fmt: skip
        """Hybrid search over the current snapshot of each source: FTS5 (bm25) + embeddings, fused by rank."""
        allowed = {s.id: s for s in self.manifest.sources
                   if (not tiers or s.tier in tiers) and (not kinds or s.kind in kinds) and (findings or not s.finding)
                   and (not sources or s.id in sources)
                   and (not topics or not s.topics or set(s.topics) & topics)}  # fmt: skip
        if not allowed:
            return []
        terms = list(dict.fromkeys(tokens(query)))[:24]
        exact = list(dict.fromkeys(m.group(0).lstrip("$") for m in EXACT.finditer(query)))[:8]
        marks = ",".join("?" * len(allowed))
        ranks: dict[int, float] = {}
        rows: dict[int, sqlite3.Row] = {}
        with self.db() as con:
            base = (f"select c.*, s.checked_at, s.effective_date as eff from chunks c join state s "
                    f"on s.source_id=c.source_id and s.sha=c.sha where c.source_id in ({marks})")  # fmt: skip
            # Words, then each exact figure or identifier ("$1,055", "I-129", "214.2") as its own ranked list:
            # among many paragraphs about fees and forms, the one with the amount or section is the one that counts.
            for group in (terms, *([e] for e in exact)):
                if not group:
                    continue
                fts = " OR ".join('"' + t.replace('"', "") + '"' for t in group)
                order = [row[0] for row in con.execute(
                    "select rowid from chunks_fts where chunks_fts match ? order by bm25(chunks_fts) limit 200",
                    (fts,))]  # fmt: skip
                if order:
                    found = {r["rid"]: r for r in con.execute(
                        f"{base} and c.rid in ({','.join('?' * len(order))})", (*allowed, *order))}  # fmt: skip
                    rows.update(found)
                    for rank, rid in enumerate([i for i in order if i in found][:60]):
                        ranks[rid] = ranks.get(rid, 0.0) + 1.0 / (60 + rank)
            qvec = self.embedder.embed([query])[0]
            scored = []
            for r in con.execute(base, tuple(allowed)):
                if r["embedder"] != self.embedder.name:
                    continue
                rows.setdefault(r["rid"], r)
                scored.append((dot(qvec, array("f", r["vec"])), r["rid"]))
            scored.sort(reverse=True)
            for rank, (_, rid) in enumerate(scored[:60]):
                ranks[rid] = ranks.get(rid, 0.0) + 1.0 / (60 + rank)
        now = utcnow()
        hits = []
        for rid, score in sorted(ranks.items(), key=lambda kv: -kv[1]):
            r = rows[rid]
            src = allowed[r["source_id"]]
            checked = _dt(r["checked_at"]) or now
            expires = self.manifest.expires_at(src, checked)
            fresh = now < expires
            if fresh_only and not fresh:
                continue
            hits.append(VaultHit(chunk_id=r["id"], source_id=src.id, title=src.title, tier=src.tier, kind=src.kind,
                                 url=self.state_url(src), text=r["text"], start=r["start"], end=r["stop"],
                                 sha256=r["sha"], checked_at=checked, expires_at=expires,
                                 effective_date=date.fromisoformat(r["eff"]) if r["eff"] else None,
                                 fresh=fresh, score=round(score, 5)))  # fmt: skip
            if len(hits) >= k:
                break
        return hits

    def link(self, source: VaultSource) -> str:
        """The page to open for a source: this month's URL for date templates, else the last URL fetched."""
        if "{" in source.url and "{ecfr_date}" not in source.url:
            return source.url.format(**_date_values())
        return self.state_url(source)

    def lapsed_manual(self, now: datetime | None = None) -> list[tuple[VaultSource, datetime]]:
        """Manual-import sources whose imported copy has passed its freshness window: (source, checked_at).
        Sources never imported aren't listed (the Knowledge page shows them as never fetched)."""
        state = self.state()
        out = []
        for s in self.manifest.sources:
            checked = _dt((state.get(s.id) or {}).get("checked_at"))
            if s.manual and s.enabled and checked and not self.is_fresh(s, checked, now):
                out.append((s, checked))
        return out

    def state_url(self, source: VaultSource) -> str:
        with self.db() as con:
            row = con.execute("select url from state where source_id=?", (source.id,)).fetchone()
        return row["url"] if row and row["url"] else source.url

    def chunk(self, chunk_id: str) -> VaultHit | None:
        with self.db() as con:
            r = con.execute("select c.*, s.checked_at, s.effective_date as eff, s.sha as current from chunks c "
                            "join state s on s.source_id=c.source_id where c.id=?", (chunk_id,)).fetchone()  # fmt: skip
        src = self.manifest.source(r["source_id"]) if r else None
        if r is None or src is None:
            return None
        checked = _dt(r["checked_at"]) or utcnow()
        expires = self.manifest.expires_at(src, checked)
        return VaultHit(chunk_id=r["id"], source_id=src.id, title=src.title, tier=src.tier, kind=src.kind,
                        url=self.state_url(src), text=r["text"], start=r["start"], end=r["stop"], sha256=r["sha"],
                        checked_at=checked, expires_at=expires,
                        effective_date=date.fromisoformat(r["eff"]) if r["eff"] else None,
                        fresh=utcnow() < expires and r["sha"] == r["current"], score=0.0)  # fmt: skip

    def history(self, source_id: str) -> list[dict[str, Any]]:
        """Every snapshot kept for a source, newest first (what the page said, and when)."""
        with self.db() as con:
            rows = con.execute("select sha, url, fetched_at, effective_date, chars from snapshots where source_id=? "
                               "order by fetched_at desc", (source_id,)).fetchall()  # fmt: skip
        return [dict(r) for r in rows]

    def has_snapshot(self, sha: str) -> bool:
        return bool(re.fullmatch(r"[0-9a-f]{64}", sha)) and self._snapshot_path(sha).exists()

    def promote(self, finding_id: str, kind: str) -> VaultSource:
        """Make a finding a reviewed source (written to the workspace's vault/sources.yaml)."""
        f = self.manifest.source(finding_id)
        if f is None or not f.finding:
            raise ValueError(f"{finding_id!r} isn't a finding")
        if kind not in self.manifest.ttl_days or kind == "finding":
            raise ValueError(
                f"kind must be one of {sorted(k for k in self.manifest.ttl_days if k != 'finding')}"
            )
        path = self.ws.root / "vault" / "sources.yaml"
        data = (yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None) or {"version": 1}
        data.setdefault("sources", [])
        data["sources"] = [s for s in data["sources"] if s.get("id") != finding_id]
        promoted = VaultSource(id=f.id, title=f.title, url=f.url, tier=f.tier, kind=kind,
                               notes="promoted from an agent finding")  # fmt: skip
        data["sources"].append(promoted.model_dump(exclude_defaults=True))
        VaultManifest.model_validate({**data, "sources": data["sources"]})
        _atomic_write(path, yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        return promoted

    # ------------------------------------------------------------------ status

    def status(self) -> list[dict[str, Any]]:
        state = self.state()
        with self.db() as con:
            counts = {
                r["source_id"]: r["n"]
                for r in con.execute("select source_id, count(*) n from snapshots group by source_id")
            }
        changed = {}
        for entry in self.log():
            if entry.status == "changed":
                changed[entry.source_id] = entry.fetched_at
        out = []
        now = utcnow()
        for s in self.manifest.sources:
            st = state.get(s.id) or {}
            checked = _dt(st.get("checked_at"))
            expires = self.manifest.expires_at(s, checked) if checked else None
            out.append({
                "id": s.id, "title": s.title, "tier": s.tier, "kind": s.kind, "topics": s.topics,
                "url": st.get("url") or s.url, "enabled": s.enabled, "notes": s.notes,
                "ttl": self.manifest.ttl(s), "status": st.get("status") or "never fetched", "error": st.get("error"),
                "checked_at": _iso(checked), "expires_at": _iso(expires),
                "fresh": bool(expires and now < expires), "effective_date": st.get("effective_date"),
                "snapshots": counts.get(s.id, 0), "last_changed": _iso(changed.get(s.id)), "sha256": st.get("sha"),
                "finding": s.finding, "manual": s.manual, "secondary_to": s.secondary_to,
                "link": self.link(s),
            })  # fmt: skip
        return out


def _date_values() -> dict[str, Any]:
    today = clock.today()
    return {"year": today.year, "month": MONTHS[today.month - 1],
            "fy": today.year + 1 if today.month >= 10 else today.year}  # fmt: skip


def _iso_date(d: date | None) -> str | None:
    return d.isoformat() if d else None


def _diff(old: str, new: str) -> DiffSummary:
    a, b = old.splitlines(), new.splitlines()
    added: list[str] = []
    removed = 0
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            removed += i2 - i1
        if tag in ("replace", "insert"):
            added += b[j1:j2]
    sample = [re.sub(r"\s+", " ", line)[:200] for line in added if line.strip()][:3]
    return DiffSummary(added=len(added), removed=removed, sample=sample)
