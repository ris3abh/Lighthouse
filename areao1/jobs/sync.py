"""Import, sync and metrics-snapshot jobs.

* ``import_source`` — detect the connector, discover items, snapshot metrics, propose candidates.
* ``sync``          — refresh every source: discover new items and push new candidates to the Inbox.
* ``snapshot``      — append dated metric rows (incl. GitHub traffic before it expires) to metrics.csv.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from areao1 import sources
from areao1.core.models import Candidate, MetricRow, SourceRecord, utcnow
from areao1.core.secrets import get_secret, set_secret
from areao1.core.text import plural
from areao1.core.workspace import Workspace
from areao1.sources.http import SourceError


@dataclass
class SyncReport:
    source_id: str
    items: int = 0
    new_items: int = 0
    metrics_written: int = 0
    candidates_added: int = 0
    errors: list[str] = field(default_factory=list)

    def line(self) -> str:
        msg = (
            f"{self.source_id}: {plural(self.items, 'item')} ({self.new_items} new), "
            f"{plural(self.metrics_written, 'metric row')}, {plural(self.candidates_added, 'new candidate')}"
        )
        if self.errors:
            msg += f", {plural(len(self.errors), 'error')}: " + "; ".join(self.errors[:3])
        return msg


def import_source(
    ws: Workspace,
    url_or_handle: str,
    *,
    token: str | None = None,
    snapshot: bool = True,
    sleep: Callable[[float], None] = time.sleep,
) -> SyncReport:
    kind = sources.detect(url_or_handle)
    connector = sources.build(kind, ws, sleep=sleep)
    handle = connector.parse(url_or_handle)
    source_id = f"{kind}:{handle}"
    secret_ref = None
    if token:
        secret_ref = source_id
        set_secret(secret_ref, token, ws.root)
    else:
        existing = next((s for s in ws.sources().sources if s.id == source_id), None)
        secret_ref = existing.secret_ref if existing else None

    record = SourceRecord(
        id=source_id,
        kind=kind,
        handle=handle,
        url=connector.source_url(handle),
        auth="token" if secret_ref else "none",
        secret_ref=secret_ref,
    )
    # Discover before persisting so a typo'd handle never lands in sources.json.
    creds = get_secret(secret_ref, ws.root) if secret_ref else None
    try:
        record.items = connector.discover(handle, creds)
    except SourceError as exc:
        raise SourceError(_explain(kind, exc), exc.status) from exc
    new = _new_items(ws, record)
    report = _run(
        ws,
        ws.upsert_source(record),
        connector,
        creds,
        new_items=new,
        do_snapshot=snapshot,
        do_candidates=True,
    )
    ws.after_change()
    return report


def sync(ws: Workspace, *, sleep: Callable[[float], None] = time.sleep) -> list[SyncReport]:
    return _each(ws, do_snapshot=False, do_candidates=True, sleep=sleep)


def snapshot(ws: Workspace, *, sleep: Callable[[float], None] = time.sleep) -> list[SyncReport]:
    return _each(ws, do_snapshot=True, do_candidates=False, sleep=sleep)


def sync_source(ws: Workspace, source_id: str, *, sleep: Callable[[float], None] = time.sleep) -> SyncReport:
    """Refresh one source fully: discover, snapshot and candidates (the Sources page 'sync now')."""
    reports = _each(ws, do_snapshot=True, do_candidates=True, sleep=sleep, only=source_id)
    if not reports:
        raise SourceError(f"no source {source_id!r}")
    return reports[0]


def _each(
    ws: Workspace,
    *,
    do_snapshot: bool,
    do_candidates: bool,
    sleep: Callable[[float], None],
    only: str | None = None,
) -> list[SyncReport]:
    reports = []
    for record in ws.sources().sources:
        if only and record.id != only:
            continue
        if record.kind not in sources.CONNECTORS:
            reports.append(SyncReport(record.id, errors=[f"no connector for kind {record.kind!r}"]))
            continue
        connector = sources.build(record.kind, ws, sleep=sleep)
        creds = get_secret(record.secret_ref, ws.root) if record.secret_ref else None
        if record.secret_ref and not creds:
            ws.update_source(
                record.id, last_error="token missing from keychain — re-auth on the Sources page"
            )
            reports.append(SyncReport(record.id, errors=["token missing from keychain"]))
            continue
        new = 0
        if do_candidates:
            try:
                fresh = record.model_copy(update={"items": connector.discover(record.handle, creds)})
            except SourceError as exc:
                ws.update_source(record.id, last_error=_explain(record.kind, exc))
                reports.append(SyncReport(record.id, errors=[str(exc)]))
                continue
            new = _new_items(ws, fresh)
            record = ws.upsert_source(fresh)
        reports.append(
            _run(
                ws,
                record,
                connector,
                creds,
                new_items=new,
                do_snapshot=do_snapshot,
                do_candidates=do_candidates,
            )
        )
    ws.after_change()
    return reports


def _run(
    ws: Workspace,
    record: SourceRecord,
    connector: sources.Source,
    creds: str | None,
    *,
    new_items: int,
    do_snapshot: bool,
    do_candidates: bool,
) -> SyncReport:
    report = SyncReport(record.id, items=len(record.items), new_items=new_items)
    tracked = [i for i in record.items if i.tracked]
    rows: list[MetricRow] = []
    cands: list[Candidate] = []
    for item in tracked:
        try:
            if do_snapshot:
                rows.extend(connector.snapshot(item, creds))
            if do_candidates:
                cands.extend(connector.candidates(item, creds))
        except SourceError as exc:
            report.errors.append(f"{item.name}: {exc}")
    if rows:
        report.metrics_written = ws.append_metrics(rows)
    if cands:
        report.candidates_added = len(ws.add_candidates(cands))
    ws.update_source(record.id, last_sync=utcnow(), last_error="; ".join(report.errors[:3]) or None)
    return report


def _new_items(ws: Workspace, record: SourceRecord) -> int:
    existing = next((s for s in ws.sources().sources if s.id == record.id), None)
    known = {i.id for i in existing.items} if existing else set()
    return sum(i.id not in known for i in record.items)


def _explain(kind: str, exc: SourceError) -> str:
    if exc.status in (401, 403, 404):
        help_url = sources.token_help(kind)
        hint = f" If it's private, add a read-only token ({help_url})." if help_url else ""
        return f"{exc}.{hint}"
    return str(exc)
