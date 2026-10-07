"""FastAPI app: the JSON API under /api plus the built web UI.

Every write goes through :class:`~lighthouse_gc.core.workspace.Workspace`, so each UI action is a plain,
Git-trackable file change in the workspace.

Local-only hardening: the server binds to 127.0.0.1 (see ``cli.up``), rejects foreign Host headers
(DNS rebinding) and requires an ``X-Lighthouse`` header on every write, which a cross-site form or
``fetch`` can't send without a CORS preflight this server never approves.
"""

from __future__ import annotations

import asyncio
import csv
import datetime as dt
import io
import json
from collections.abc import AsyncIterator
from typing import Any, Literal

import anyio
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from lighthouse_gc import __version__
from lighthouse_gc.agent.runner import AgentRunner, BudgetExceeded
from lighthouse_gc.core import clock
from lighthouse_gc.core.models import METRICS_COLUMNS
from lighthouse_gc.core.workspace import NotFound, WorkspaceError
from lighthouse_gc.criteria import overview as views
from lighthouse_gc.criteria.case import Case
from lighthouse_gc.engine.base import Engine, EngineUnavailable
from lighthouse_gc.resources import web_static_dir
from lighthouse_gc.service import Service
from lighthouse_gc.sources.http import SourceError
from lighthouse_gc.vault import Vault
from lighthouse_gc.vault.rulecheck import briefing_text, refresh
from lighthouse_gc.vault.store import MAX_VAULT_BYTES

WRITE_HEADER = "x-lighthouse"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
PREVIEWABLE = {".md", ".txt", ".json", ".csv", ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"}


class ProfileBody(BaseModel):
    id: str


class OverrideBody(BaseModel):
    status: str | None


class CandidateEdit(BaseModel):
    proposed_criterion: str | None = None
    evidence_type: str | None = None
    title: str | None = None
    summary: str | None = None
    signals: list[str] | None = None


class AcceptBody(CandidateEdit):
    date: dt.date | None = None


class SnoozeBody(BaseModel):
    until: dt.date | None = None


class RemapBody(BaseModel):
    criterion: str
    evidence_type: str | None = None


class SourceBody(BaseModel):
    input: str
    token: str | None = None
    snapshot: bool = True


class TokenBody(BaseModel):
    token: str


class PickBody(BaseModel):
    ids: list[str]


class TodoBody(BaseModel):
    status: Literal["open", "done", "dismissed"]


class DeadlineBody(BaseModel):
    title: str | None = None
    due: dt.date | None = None
    kind: str | None = None
    criterion: str | None = None
    url: str | None = None
    human_only: bool | None = None
    done: bool | None = None


class PipelineBody(BaseModel):
    title: str | None = None
    criterion: str | None = None
    stage: str | None = None
    url: str | None = None
    follow_up: dt.date | None = None
    notes: str | None = None


class LetterBody(BaseModel):
    name: str | None = None
    relationship: str | None = None
    credentials: str | None = None
    criteria: list[str] | None = None
    asks: list[str] | None = None
    status: str | None = None
    draft_path: str | None = None
    last_contact: dt.date | None = None


class KeyBody(BaseModel):
    key: str = Field(min_length=1, max_length=400)


class ChatBody(BaseModel):
    message: str
    conversation_id: str | None = None
    page: str | None = None


class RunBody(BaseModel):
    prompt: str


class AutopilotBody(BaseModel):
    tracker_updates: bool | None = None
    metrics: bool | None = None
    tier1_deadlines: bool | None = None


class MissionsBody(BaseModel):
    opportunity_scout: bool | None = None
    what_changed: bool | None = None


class VaultSyncBody(BaseModel):
    sources: list[str] | None = None
    force: bool = False


class PromoteBody(BaseModel):
    kind: str


class NotifyTestBody(BaseModel):
    channel: str | None = None


STALE_DAYS = 14


def pipeline_view(ws: Case) -> list[dict[str, Any]]:
    today = clock.today()
    return [
        {
            **p.model_dump(mode="json"),
            "days_since_move": (today - clock.local_date(p.moved_at)).days,
            "stale": p.stage != "done" and (today - clock.local_date(p.moved_at)).days >= STALE_DAYS,
        }  # fmt: skip
        for p in ws.pipeline().items
    ]


def create_app(ws: Case, allowed_hosts: list[str] | None = None, engine: Engine | None = None) -> FastAPI:
    app = FastAPI(
        title="Lighthouse", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    svc = Service(ws)  # every user-initiated write goes through the service layer
    runner = AgentRunner(ws, engine=engine)
    from lighthouse_gc.onboarding.api import mount as mount_onboarding

    def _onboarding_judge():  # the model fallback for PDFs that aren't LinkedIn exports
        ok, _ = runner.engine().available()
        return runner.judge() if ok else None

    mount_onboarding(app, ws, svc, judge=_onboarding_judge, runner=runner)
    app.state.runner = runner
    vault = Vault(ws)

    def checked(check: Any) -> Any:
        """A rule check with statuses re-evaluated against the vault as it is now."""
        fresh = refresh(check, vault)
        return fresh.model_dump(mode="json") if fresh else None

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["127.0.0.1", "localhost"])

    @app.middleware("http")
    async def require_write_header(request: Request, call_next: Any) -> Response:
        if request.method not in ("GET", "HEAD", "OPTIONS") and request.headers.get(WRITE_HEADER) != "1":
            return JSONResponse({"detail": f"missing {WRITE_HEADER} header"}, status_code=403)
        response: Response = await call_next(request)
        # Workspace files change under the server; never let the browser show stale numbers.
        # Hashed assets under /assets/ stay cacheable.
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif not request.url.path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    @app.exception_handler(NotFound)
    async def _not_found(_: Request, exc: NotFound) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=404)

    @app.exception_handler(WorkspaceError)
    async def _bad_request(_: Request, exc: WorkspaceError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(BudgetExceeded)
    async def _budget(_: Request, exc: BudgetExceeded) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=429)

    @app.exception_handler(EngineUnavailable)
    async def _engine(_: Request, exc: EngineUnavailable) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.exception_handler(SourceError)
    async def _source_error(_: Request, exc: SourceError) -> JSONResponse:
        return JSONResponse({"detail": str(exc)}, status_code=502)

    # ------------------------------------------------------------------ overview + profiles

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "version": __version__, "workspace": ws.root.name}

    @app.get("/api/overview")
    def get_overview() -> dict[str, Any]:
        return views.overview(ws)

    @app.get("/api/profiles")
    def get_profiles() -> list[dict[str, Any]]:
        return [p.model_dump(mode="json") for p in ws.profiles().values()]

    @app.get("/api/profile")
    def get_profile() -> dict[str, Any]:
        return ws.profile().model_dump(mode="json")

    @app.put("/api/profile")
    def put_profile(body: ProfileBody) -> dict[str, Any]:
        return svc.set_profile(body.id).model_dump(mode="json")

    @app.get("/api/scoreboard")
    def get_scoreboard() -> dict[str, Any]:
        return ws.scoreboard().model_dump(mode="json")

    @app.put("/api/criteria/{criterion_id}/override")
    def put_override(criterion_id: str, body: OverrideBody) -> dict[str, Any]:
        return svc.set_override(criterion_id, body.status).model_dump(mode="json")

    # ------------------------------------------------------------------ inbox

    @app.get("/api/inbox")
    def get_inbox(status: str = "pending") -> list[dict[str, Any]]:
        if status == "pending":
            items = ws.pending_candidates()
        elif status == "all":
            items = ws.inbox().candidates
        else:
            items = [c for c in ws.inbox().candidates if c.status == status]
        return [{**c.model_dump(mode="json"), "rule_check": checked(c.rule_check)}
                for c in sorted(items, key=lambda c: (-c.confidence, c.created_at))]  # fmt: skip

    @app.patch("/api/inbox/{candidate_id}")
    def patch_candidate(candidate_id: str, body: CandidateEdit) -> dict[str, Any]:
        return svc.edit_candidate(candidate_id, **body.model_dump(exclude_none=True)).model_dump(mode="json")

    @app.post("/api/inbox/{candidate_id}/accept")
    def accept(candidate_id: str, body: AcceptBody | None = None) -> dict[str, Any]:
        edits = body.model_dump(exclude_none=True) if body else {}
        return svc.accept_candidate(candidate_id, **edits).model_dump(mode="json")

    @app.post("/api/inbox/{candidate_id}/reject")
    def reject(candidate_id: str) -> dict[str, Any]:
        return svc.reject_candidate(candidate_id).model_dump(mode="json")

    @app.post("/api/inbox/{candidate_id}/snooze")
    def snooze(candidate_id: str, body: SnoozeBody | None = None) -> dict[str, Any]:
        return svc.snooze_candidate(candidate_id, body.until if body else None).model_dump(mode="json")

    @app.post("/api/inbox/upload")
    async def upload_to_inbox(
        files: list[UploadFile] = File(...),
        criterion: str = Form("", description="Optional: the criterion the files were dropped on"),
    ) -> list[dict[str, Any]]:
        """Drag-and-drop: each file becomes a snapshot in memory/ and a candidate in the Inbox."""
        out = []
        for f in files:
            content = await f.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                raise HTTPException(413, f"{f.filename} is larger than 25 MB")
            cand = svc.stage_upload(content, f.filename or "upload.bin", criterion or None)
            out.append(cand.model_dump(mode="json"))
        return out

    @app.post("/api/imports/chats")
    async def import_chat_export(
        file: UploadFile = File(...), keep_all: bool = Form(False)
    ) -> dict[str, Any]:
        """Claude / ChatGPT export (conversations.json or .zip) -> snapshots + self-reported tracker candidates."""
        from lighthouse_gc.jobs.chats import import_chats
        from lighthouse_gc.sources.chat_export import MAX_EXPORT_BYTES, ExportError

        data = await file.read(MAX_EXPORT_BYTES + 1)
        if len(data) > MAX_EXPORT_BYTES:
            raise HTTPException(413, "export is larger than 512 MB")
        try:
            report = import_chats(ws, data, file.filename or "conversations.json", keep_all=keep_all)
        except ExportError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {**report.__dict__, "summary": report.line()}

    staged: dict[
        str, tuple[float, Any]
    ] = {}  # chat imports waiting for the picker; memory only, never on disk

    @app.post("/api/imports/chats/scan")
    async def scan_chats(files: list[UploadFile] = File(...)) -> dict[str, Any]:
        """Read whatever was dropped (an export .zip, several .json files or a folder) and score each conversation
        and project for case signals, locally. Nothing is written: the picker decides what's imported."""
        import time

        from lighthouse_gc.core.models import new_id
        from lighthouse_gc.sources import chat_intake, chat_relevance
        from lighthouse_gc.sources.chat_export import MAX_EXPORT_BYTES, ExportError

        dropped = []
        for f in files:
            data = await f.read(MAX_EXPORT_BYTES + 1)
            if len(data) > MAX_EXPORT_BYTES:
                raise HTTPException(413, f"{f.filename} is larger than 512 MB")
            dropped.append((f.filename or "file", data))
        try:
            intake = chat_intake.read(dropped)
        except ExportError as exc:
            raise HTTPException(400, str(exc)) from exc
        person = ws.person()
        fields = {f.key: f.value for f in ws.onboarding().fields if f.status in ("confirmed", "fixed")}
        if person.field:
            fields.setdefault("headline", person.field)
        matches = chat_relevance.score(intake, [person.name, *person.aliases], fields)
        for key, (at, _) in list(staged.items()):  # keep a few recent scans for an hour at most
            if time.time() - at > 3600 or len(staged) > 3:
                staged.pop(key, None)
        scan_id = new_id("scan")
        staged[scan_id] = (time.time(), intake)
        return {"id": scan_id, "summary": intake.summary(), "formats": intake.formats,
                "unread": [{"file": p, "why": why} for p, why in intake.unread], "skipped": len(intake.skipped),
                "items": [m.as_dict() for m in matches]}  # fmt: skip

    @app.post("/api/imports/chats/{scan_id}/import")
    async def import_picked_chats(scan_id: str, body: PickBody) -> dict[str, Any]:
        """Import only the ticked conversations and projects; the rest of the scan is discarded."""
        from lighthouse_gc.core.models import AgentRun
        from lighthouse_gc.jobs.chats import import_picked

        if scan_id not in staged:
            raise HTTPException(404, "that scan has expired; drop the export again")
        _, intake = staged.pop(scan_id)
        try:
            judge, how = runner.mundane("chat_extract")
        except BudgetExceeded:
            judge, how = None, runner.route("chat_extract")  # over the cap: the local rules still read them
        report = await import_picked(ws, intake, set(body.ids), judge, how.model)
        if (
            report.extracted_by != "rules"
        ):  # the model's cost shows on the Agent page and counts toward the month
            run = AgentRun(kind="manual", engine=how.provider if how.provider == "openai" else runner.engine().name,
                           model=how.model, task=how.task, tier=how.tier, provider=how.provider, status="done",
                           prompt=f"Chat-history extraction ({report.picked} picked)", text=report.line(),
                           cost_usd=report.cost_usd, finished_at=clock.utcnow())  # fmt: skip
            runner.save(run)
        return {**report.__dict__, "summary": report.line()}

    @app.delete("/api/imports/chats/{scan_id}")
    def discard_scan(scan_id: str) -> dict[str, Any]:
        staged.pop(scan_id, None)
        return {"discarded": scan_id}

    @app.get("/api/attachments/{obs_id}")
    def get_attachment(obs_id: str) -> FileResponse:
        """Preview an uploaded file before it's filed (only files staged via upload)."""
        obs = ws.memory.observation(obs_id)
        if obs is None or obs.connector != "upload":
            raise HTTPException(404, "no such upload")
        target = ws.resolve_inside(obs.snapshot)
        if target.suffix.lower() not in PREVIEWABLE:
            raise HTTPException(415, "no preview for this file type")
        media = "text/plain; charset=utf-8" if target.suffix.lower() in (".md", ".txt", ".csv") else None
        return FileResponse(target, media_type=media, headers={"Content-Security-Policy": "sandbox"})

    # ------------------------------------------------------------------ evidence

    @app.get("/api/exhibits")
    def get_exhibits() -> dict[str, Any]:
        board = ws.scoreboard()
        exhibits = ws.exhibits().exhibits
        profile = ws.profile()
        criteria = []
        for row in board.criteria:
            crit = profile.criterion(row.id)
            criteria.append(
                {
                    **row.model_dump(mode="json"),
                    "evidence_types": crit.evidence_types if crit else [],
                    "strength_signals": [s.model_dump() for s in crit.strength_signals] if crit else [],
                    "bank": crit.bank.model_dump() if crit else None,
                    "exhibits": [e.model_dump(mode="json") for e in exhibits if e.criterion == row.id],
                }
            )
        in_profile = {c.id for c in profile.criteria}
        other = [e.model_dump(mode="json") for e in exhibits if e.criterion not in in_profile]
        return {"criteria": criteria, "other_exhibits": other, "naming_issues": ws.naming_check()}

    @app.post("/api/exhibits/upload")
    async def upload(
        file: UploadFile = File(...),
        criterion: str = Form(...),
        evidence_type: str = Form(...),
        title: str = Form(...),
        on: dt.date = Form(..., alias="date"),
        summary: str = Form(""),
        signals: str = Form("", description="Comma-separated signal ids"),
        source_url: str = Form(""),
        stage: str = Form("", description="Event stage, e.g. invited / completed; empty if not an activity"),
    ) -> dict[str, Any]:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "file is larger than 25 MB")
        exhibit = svc.add_exhibit_file(
            content=content,
            filename=file.filename or "upload.bin",
            criterion=criterion,
            evidence_type=evidence_type,
            title=title,
            on=on,
            summary=summary,
            signals=[s.strip() for s in signals.split(",") if s.strip()],
            source_url=source_url or None,
            stage=stage or None,
        )
        return exhibit.model_dump(mode="json")

    @app.patch("/api/exhibits/{exhibit_id}")
    def remap(exhibit_id: str, body: RemapBody) -> dict[str, Any]:
        return svc.remap_exhibit(exhibit_id, body.criterion, body.evidence_type).model_dump(mode="json")

    @app.get("/api/files/{path:path}")
    def get_file(path: str) -> FileResponse:
        target = ws.resolve_inside(path)
        if ws.evidence_dir not in target.parents or not target.is_file():
            raise HTTPException(404, "not an evidence file")
        if target.suffix.lower() not in PREVIEWABLE:
            raise HTTPException(415, "no preview for this file type")
        media = "text/plain; charset=utf-8" if target.suffix.lower() in (".md", ".txt", ".csv") else None
        return FileResponse(target, media_type=media, headers={"Content-Security-Policy": "sandbox"})

    # ------------------------------------------------------------------ memory (5b)

    @app.get("/api/claims")
    def get_claims(ids: str = "", subject: str = "", status: str = "") -> list[dict[str, Any]]:
        """Claims with review status and provenance. ``ids`` is comma-separated."""
        mem = ws.memory
        statuses = mem.statuses()
        observations = {o.id: o for o in mem.observations()}
        wanted = {i for i in ids.split(",") if i}
        out = []
        for c in mem.claims():
            if wanted and c.id not in wanted:
                continue
            if subject and c.subject != subject:
                continue
            if status and statuses[c.id] != status:
                continue
            obs = observations.get(c.observation_id)
            out.append(
                {
                    **c.model_dump(mode="json"),
                    "status": statuses[c.id],
                    "source_url": obs.source_url if obs else None,
                    "connector": obs.connector if obs else None,
                    "captured_at": obs.captured_at.isoformat() if obs else None,
                    "snapshot": obs.snapshot if obs else None,
                }
            )
        return out

    @app.get("/api/memory")
    def memory_summary() -> dict[str, Any]:
        mem = ws.memory
        statuses = mem.statuses()
        counts: dict[str, int] = {}
        for s in statuses.values():
            counts[s] = counts.get(s, 0) + 1
        return {
            "observations": len(mem.observations()),
            "claims": len(statuses),
            "by_status": counts,
            "edges": len(mem.edges()),
            "problems": mem.verify(),
        }

    # ------------------------------------------------------------------ metrics

    @app.get("/api/metrics")
    def get_metrics() -> dict[str, Any]:
        series = views.metric_series(ws.metrics())
        items = {i.name: i.url for s in ws.sources().sources for i in s.items}
        out = []
        for (source, item, metric), points in sorted(series.items()):
            out.append(
                {
                    "source": source,
                    "item": item,
                    "metric": metric,
                    "url": items.get(item),
                    "points": [{"date": p.date.isoformat(), "value": p.value} for p in points],
                    **views.latest_with_delta(points),
                }
            )
        return {"series": out}

    @app.post("/api/metrics/snapshot")
    def post_snapshot() -> dict[str, Any]:
        from lighthouse_gc.jobs.sync import snapshot

        return {"reports": [r.__dict__ for r in snapshot(ws)]}

    # ------------------------------------------------------------------ deadlines + calendar

    @app.get("/api/deadlines")
    def get_deadlines() -> list[dict[str, Any]]:
        today = clock.today()
        return [
            {**d.model_dump(mode="json"), "days_left": (d.due - today).days}
            for d in sorted(ws.deadlines().deadlines, key=lambda d: d.due)
        ]

    @app.post("/api/deadlines")
    def post_deadline(body: DeadlineBody) -> dict[str, Any]:
        return svc.add_deadline(**body.model_dump(exclude_none=True)).model_dump(mode="json")

    @app.patch("/api/deadlines/{deadline_id}")
    def patch_deadline(deadline_id: str, body: DeadlineBody) -> dict[str, Any]:
        return svc.update_deadline(deadline_id, **body.model_dump(exclude_unset=True)).model_dump(mode="json")

    @app.delete("/api/deadlines/{deadline_id}")
    def remove_deadline(deadline_id: str) -> dict[str, Any]:
        svc.delete_deadline(deadline_id)
        return {"removed": deadline_id}

    @app.patch("/api/todos/{todo_id}")
    def patch_todo(todo_id: str, body: TodoBody) -> dict[str, Any]:
        """Tick off (or dismiss, or reopen) a self-reported to-do. It never changes a criterion."""
        return svc.update_todo(todo_id, body.status).model_dump(mode="json")

    @app.get("/api/pipeline")
    def get_pipeline() -> list[dict[str, Any]]:
        return pipeline_view(ws)

    @app.post("/api/pipeline")
    def post_pipeline(body: PipelineBody) -> dict[str, Any]:
        return svc.add_pipeline_item(**body.model_dump(exclude_none=True)).model_dump(mode="json")

    @app.patch("/api/pipeline/{item_id}")
    def patch_pipeline(item_id: str, body: PipelineBody) -> dict[str, Any]:
        return svc.update_pipeline_item(item_id, **body.model_dump(exclude_unset=True)).model_dump(
            mode="json"
        )

    @app.delete("/api/pipeline/{item_id}")
    def remove_pipeline(item_id: str) -> dict[str, Any]:
        svc.delete_pipeline_item(item_id)
        return {"removed": item_id}

    @app.get("/api/letters")
    def get_letters() -> dict[str, Any]:
        profile = ws.profile()
        letters = ws.letters().letters
        coverage = []
        for crit in profile.criteria:
            writers = [lt for lt in letters if crit.id in lt.criteria and lt.status != "declined"]
            coverage.append({"id": crit.id, "label": crit.label, "short_label": crit.short_label or crit.label,
                             **{rel: sum(lt.relationship == rel for lt in writers)
                                for rel in ("independent", "employer", "coauthor")}})  # fmt: skip
        return {
            "letters": [
                {
                    **lt.model_dump(mode="json"),
                    "draft_exists": bool(lt.draft_path and (ws.root / lt.draft_path).is_file()),
                }  # fmt: skip
                for lt in letters
            ],
            "coverage": coverage,
            "criteria": [
                {"id": c.id, "label": c.label, "short_label": c.short_label or c.label}
                for c in profile.criteria
            ],
        }

    @app.post("/api/letters")
    def post_letter(body: LetterBody) -> dict[str, Any]:
        return svc.add_letter(**body.model_dump(exclude_none=True)).model_dump(mode="json")

    @app.patch("/api/letters/{letter_id}")
    def patch_letter(letter_id: str, body: LetterBody) -> dict[str, Any]:
        return svc.update_letter(letter_id, **body.model_dump(exclude_unset=True)).model_dump(mode="json")

    @app.delete("/api/letters/{letter_id}")
    def remove_letter(letter_id: str) -> dict[str, Any]:
        svc.delete_letter(letter_id)
        return {"removed": letter_id}

    @app.get("/api/drafts/{path:path}")
    def get_draft(path: str) -> FileResponse:
        target = ws.resolve_inside(f"drafts/{path}")
        if not target.is_file() or target.suffix.lower() not in (".md", ".txt"):
            raise HTTPException(404, "no such draft")
        return FileResponse(target, media_type="text/plain; charset=utf-8",
                            headers={"Content-Security-Policy": "sandbox"})  # fmt: skip

    @app.get("/calendar.ics")
    def calendar_feed() -> Response:
        """Subscribe from a calendar app on this machine: webcal://127.0.0.1:<port>/calendar.ics"""
        from lighthouse_gc.core.calendar import render

        return Response(render(ws), media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": 'inline; filename="lighthouse.ics"'})  # fmt: skip

    # ------------------------------------------------------------------ jobs

    @app.get("/api/jobs")
    def get_jobs() -> list[dict[str, Any]]:
        from lighthouse_gc.jobs.scheduler import jobs_status

        return jobs_status(ws)

    @app.post("/api/jobs/{name}/run")
    def run_job_now(name: str) -> dict[str, Any]:
        from lighthouse_gc.jobs import JOBS
        from lighthouse_gc.jobs.scheduler import run_job

        if name not in JOBS:
            raise HTTPException(404, f"no job {name!r}")
        return run_job(ws, name)

    @app.get("/api/metrics/export.csv")
    def export_csv() -> PlainTextResponse:
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(METRICS_COLUMNS)
        for r in ws.metrics():
            writer.writerow([r.date.isoformat(), r.source, r.item, r.metric, r.value])
        return PlainTextResponse(
            out.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="metrics.csv"'},
        )

    # ------------------------------------------------------------------ sources

    @app.get("/api/sources")
    def get_sources() -> list[dict[str, Any]]:
        from lighthouse_gc import sources

        return [
            {**s.model_dump(mode="json"), "token_help": sources.token_help(s.kind)}
            for s in ws.sources().sources
        ]

    @app.post("/api/sources")
    def add_source(body: SourceBody) -> dict[str, Any]:
        from lighthouse_gc.jobs.sync import import_source

        try:
            report = import_source(ws, body.input, token=body.token or None, snapshot=body.snapshot)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return report.__dict__

    @app.post("/api/sources/{source_id:path}/sync")
    def sync_one(source_id: str) -> dict[str, Any]:
        from lighthouse_gc.jobs.sync import sync_source

        _source(source_id)
        return sync_source(ws, source_id).__dict__

    @app.put("/api/sources/{source_id:path}/token")
    def reauth(source_id: str, body: TokenBody) -> dict[str, Any]:
        from lighthouse_gc.core.secrets import set_secret

        _source(source_id)
        where = set_secret(source_id, body.token, ws.root)
        ws.update_source(source_id, auth="token", secret_ref=source_id, last_error=None)
        return {"stored_in": where}

    @app.delete("/api/sources/{source_id:path}")
    def remove(source_id: str) -> dict[str, Any]:
        from lighthouse_gc.core.secrets import delete_secret

        record = _source(source_id)
        ws.remove_source(source_id)
        if record.secret_ref:
            delete_secret(record.secret_ref, ws.root)
        ws.after_change()
        return {"removed": source_id}

    def _source(source_id: str) -> Any:
        record = next((s for s in ws.sources().sources if s.id == source_id), None)
        if record is None:
            raise NotFound(f"no source {source_id!r}")
        return record

    # ------------------------------------------------------------------ settings + notifications

    @app.get("/api/settings")
    def get_settings() -> dict[str, Any]:
        from lighthouse_gc.core.secrets import get_secret
        from lighthouse_gc.notify import history

        cfg = ws.config()
        channels = []
        for name, ch in cfg.notifications.channels.items():
            data = ch.model_dump()
            channels.append({"name": name, **data,
                             "secret_stored": bool(ch.secret_ref and get_secret(ch.secret_ref, ws.root))})  # fmt: skip
        return {
            "profile": ws.profile_id(),
            "engine": cfg.engine,
            "privacy": cfg.privacy.model_dump(),
            "channels": channels,
            "routes": cfg.notifications.routes,
            "deadline_alert_days": cfg.notifications.deadline_alert_days,
            "autopilot": cfg.agent.autopilot.model_dump(),
            "missions": cfg.agent.missions.model_dump(),
            "schedules": cfg.schedules,
            "recent_notifications": history(ws, limit=20)[::-1],
        }

    @app.post("/api/notify/test")
    def notify_test(body: NotifyTestBody | None = None) -> dict[str, Any]:
        from lighthouse_gc.notify import Notification, send

        report = send(ws, Notification("test", "Lighthouse test", "Notifications are working.",
                                       minimal_body="Notifications are working."),
                      only=body.channel if body else None)  # fmt: skip
        return {"ok": report.ok, "summary": report.line(), "results": [r.__dict__ for r in report.results]}

    # ------------------------------------------------------------------ agent (ADR 0005)

    @app.get("/api/changes")
    def get_changes(actor: str = "", limit: int = 200) -> list[dict[str, Any]]:
        """The audit trail (data/changes.jsonl), newest first, optionally for one actor (e.g. agent:<run>)."""
        every = ws.changes()
        changes = [c for c in every if not actor or c.actor == actor]
        return [
            {
                **c.model_dump(mode="json"),
                "undoable": svc.undoable(c, every),
                "undone": any(x.undoes == c.id for x in every),
            }  # fmt: skip
            for c in reversed(changes[-limit:])
        ]

    @app.post("/api/changes/{change_id}/undo")
    def undo_change(change_id: str) -> dict[str, Any]:
        return svc.undo(change_id).model_dump(mode="json")

    @app.put("/api/settings/autopilot")
    def put_autopilot(body: AutopilotBody) -> dict[str, Any]:
        return svc.set_autopilot(**body.model_dump(exclude_none=True)).model_dump()

    @app.get("/api/agent/status")
    def agent_status() -> dict[str, Any]:
        return runner.status()

    @app.get("/api/ai")
    def ai_status() -> dict[str, Any]:
        from lighthouse_gc.engine import connect

        return connect.status()

    @app.put("/api/ai/key")
    def ai_key(body: KeyBody) -> dict[str, Any]:
        """Check an Anthropic key with the free model-list request, then keep it in the OS keychain only."""
        from lighthouse_gc.engine import connect

        ok, why = connect.check_key(body.key)
        if not ok:
            raise HTTPException(400, why)
        try:
            connect.save_key(body.key)
        except Exception as exc:  # no usable keychain: never fall back to a workspace file
            raise HTTPException(
                500, f"The key works, but there's no keychain to keep it in ({exc})."
            ) from exc
        return connect.status()

    @app.delete("/api/ai/key")
    def ai_key_forget() -> dict[str, Any]:
        from lighthouse_gc.engine import connect

        connect.forget_key()
        return connect.status()

    @app.post("/api/agent/chat")
    async def agent_chat(body: ChatBody) -> dict[str, Any]:
        run = await runner.start("chat", body.message, conversation_id=body.conversation_id, page=body.page)
        return {"run_id": run.id, "conversation_id": run.conversation_id}

    @app.post("/api/agent/runs")
    async def agent_manual_run(body: RunBody) -> dict[str, Any]:
        run = await runner.start("manual", body.prompt)
        return {"run_id": run.id}

    @app.get("/api/agent/runs")
    def agent_runs(limit: int = 100) -> list[dict[str, Any]]:
        return [
            {
                **r.model_dump(mode="json", exclude={"timeline"}),
                "tool_calls": sum(i.type == "tool_call" for i in r.timeline),
                "counted_tokens": r.usage.counted,
                "rule_check": checked(r.rule_check),
            }  # fmt: skip
            for r in runner.runs(limit)
        ]

    @app.get("/api/agent/runs/{run_id}")
    def agent_run(run_id: str) -> dict[str, Any]:
        r = runner.get(run_id)
        return {
            **r.model_dump(mode="json"),
            "counted_tokens": r.usage.counted,
            "rule_check": checked(r.rule_check),
        }

    @app.get("/api/agent/runs/{run_id}/stream")
    async def agent_stream(run_id: str) -> StreamingResponse:
        runner.get(run_id)  # 404 if unknown

        async def events() -> AsyncIterator[bytes]:
            async for event in runner.stream(run_id):
                # EventSource reserves "error" for connection failures, so agent errors go out as agent_error.
                name = "agent_error" if event["type"] == "error" else event["type"]
                yield f"event: {name}\ndata: {json.dumps(event, default=str)}\n\n".encode()

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})  # fmt: skip

    @app.post("/api/agent/runs/{run_id}/stop")
    def agent_stop(run_id: str) -> dict[str, Any]:
        runner.get(run_id)
        return {"stopping": runner.stop(run_id)}

    @app.get("/api/briefing")
    def get_briefing() -> dict[str, Any]:
        """The Overview briefing, with each linked Inbox item's current state for inline approve / dismiss."""
        b = ws.briefing()
        inbox = {c.id: c for c in ws.inbox().candidates}
        running = next(
            (r for r in runner.runs(limit=50) if r.mission == "what_changed" and r.status == "running"), None
        )
        todos = []
        for t in b.todos:
            c = inbox.get(t.candidate_id or "")
            todos.append({**t.model_dump(mode="json"), "candidate": {
                "id": c.id, "kind": c.kind, "title": c.title, "status": c.status,
                "proposed_criterion": c.proposed_criterion, "source_tier": c.source_tier} if c else None})  # fmt: skip
        return {**b.model_dump(mode="json", exclude={"todos"}), "todos": todos,
                "refreshing": running.id if running else None, "rule_check": checked(b.rule_check)}  # fmt: skip

    # ------------------------------------------------------------------ knowledge (SPEC 5a)

    def open_conflicts() -> list[dict[str, Any]]:
        """Rule claims where Tier 1 sources disagree, wherever they appeared (answers, briefing, Inbox)."""
        found: dict[str, dict[str, Any]] = {}

        def add(check: Any, where: dict[str, Any], at: Any) -> None:
            fresh = refresh(check, vault)
            for c in fresh.claims if fresh else []:
                if c.status == "conflict" and c.text not in found:
                    found[c.text] = {"claim": c.model_dump(mode="json"), "where": where, "at": str(at)}

        for r in runner.runs(limit=200):
            add(r.rule_check, {"type": "run", "id": r.id, "label": r.prompt[:80]}, r.started_at)
        b = ws.briefing()
        add(b.rule_check, {"type": "briefing", "id": None, "label": "This week's briefing"}, b.generated_at)
        for cand in ws.pending_candidates():
            add(cand.rule_check, {"type": "candidate", "id": cand.id, "label": cand.title}, cand.created_at)
        return list(found.values())

    @app.get("/api/knowledge")
    def knowledge() -> dict[str, Any]:
        sources = vault.status()
        titles = {s["id"]: s["title"] for s in sources}
        recent = [{**e.model_dump(mode="json"), "title": titles.get(e.source_id, e.source_id)}
                  for e in reversed(vault.log()[-60:])]  # fmt: skip
        return {"enabled": ws.config().vault.enabled, "sources": sources, "recent": recent,
                "conflicts": open_conflicts(), "tier1_domains": vault.manifest.tier1_domains,
                "tier2_domains": vault.manifest.tier2_domains,
                "kinds": sorted(k for k in vault.manifest.ttl_days if k != "finding")}  # fmt: skip

    @app.get("/api/knowledge/sources/{source_id}")
    def knowledge_source(source_id: str) -> dict[str, Any]:
        src = vault.manifest.source(source_id)
        if src is None:
            raise HTTPException(404, f"no vault source {source_id!r}")
        return {
            "source": src.model_dump(),
            "snapshots": vault.history(source_id),
            "log": [e.model_dump(mode="json") for e in reversed(vault.log()) if e.source_id == source_id][
                :30
            ],
        }

    @app.get("/api/knowledge/snapshots/{sha}")
    def knowledge_snapshot(sha: str) -> PlainTextResponse:
        if not vault.has_snapshot(sha):
            raise HTTPException(404, "no such snapshot")
        return PlainTextResponse(vault.snapshot_text(sha))

    @app.post("/api/knowledge/sync")
    async def knowledge_sync(body: VaultSyncBody | None = None) -> list[dict[str, Any]]:
        if not ws.config().vault.enabled:
            raise HTTPException(400, "the vault is turned off (vault.enabled in lighthouse.yaml)")
        body = body or VaultSyncBody()
        try:
            results = await vault.sync(body.sources or None, force=body.force)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return [r.model_dump(mode="json") for r in results]

    @app.post("/api/knowledge/import/{source_id}")
    async def knowledge_import(source_id: str, file: UploadFile = File(...)) -> dict[str, Any]:
        content = await file.read(MAX_VAULT_BYTES + 1)
        if len(content) > MAX_VAULT_BYTES:
            raise HTTPException(413, "file is too large")
        try:
            entry = vault.import_file(source_id, content, file.filename or "", file.content_type or "")
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return entry.model_dump(mode="json")

    @app.post("/api/knowledge/findings/{source_id}/promote")
    def knowledge_promote(source_id: str, body: PromoteBody) -> dict[str, Any]:
        try:
            promoted = svc.promote_finding(source_id, body.kind)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return promoted.model_dump()

    # Re-run rule-check (one judge call when the text states rules) after the vault was refreshed.
    @app.post("/api/rulecheck/runs/{run_id}")
    async def recheck_run(run_id: str) -> dict[str, Any]:
        r = runner.get(run_id)
        if r.status == "running" or not r.text.strip():
            raise HTTPException(400, "nothing to check yet")
        r.rule_check = await runner.checker().check(r.text)
        runner.save(r)
        return checked(r.rule_check)

    @app.post("/api/rulecheck/briefing")
    async def recheck_briefing() -> dict[str, Any]:
        b = ws.briefing()
        if not b.generated_at:
            raise HTTPException(400, "no briefing yet")
        check = await runner.checker().check(briefing_text(b.changed, b.todos))
        svc.set_briefing_check(check)
        return checked(check)

    @app.post("/api/rulecheck/inbox/{candidate_id}")
    async def recheck_candidate(candidate_id: str) -> dict[str, Any]:
        cand = next((c for c in ws.inbox().candidates if c.id == candidate_id), None)
        if cand is None:
            raise HTTPException(404, f"no candidate {candidate_id!r}")
        text = f"{cand.title}. {cand.summary}"
        if cand.kind in ("letter", "update"):
            text = " ".join(str(v) for v in (cand.proposal.get("changes") or cand.proposal).values())
        check = await runner.checker().check(text)
        svc.set_rule_check(candidate_id, check)
        return checked(check)

    @app.get("/api/agent/refusals")
    def agent_refusals() -> list[dict[str, Any]]:
        """Everything the agent or a guardrail declined, newest first (ADR 0008, C4)."""
        from lighthouse_gc.agent.guardrails import refusals

        return refusals(ws)

    @app.get("/api/agent/missions")
    def agent_missions() -> list[dict[str, Any]]:
        from lighthouse_gc.agent.missions import missions_status

        return missions_status(ws, runner)

    @app.put("/api/settings/missions")
    def put_missions(body: MissionsBody) -> dict[str, Any]:
        return svc.set_missions(**body.model_dump(exclude_none=True)).model_dump()

    @app.post("/api/agent/missions/{name}/run")
    async def agent_mission_run(name: str) -> dict[str, Any]:
        from lighthouse_gc.agent import missions

        if name not in missions.MISSIONS:
            raise HTTPException(404, f"no mission {name!r}")
        run = await missions.start(runner, name)

        async def notify_when_done() -> None:
            finished = await runner.wait(run.id)
            await anyio.to_thread.run_sync(missions.notify_result, ws, finished)

        app.state.background = getattr(app.state, "background", set())
        task = asyncio.create_task(notify_when_done())
        app.state.background.add(task)
        task.add_done_callback(app.state.background.discard)
        return {"run_id": run.id}

    @app.get("/api/agent/conversations")
    def agent_conversations() -> list[dict[str, Any]]:
        return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat(), "messages": len(c.messages)}
                for c in runner.conversations()]  # fmt: skip

    @app.get("/api/agent/conversations/{conv_id}")
    def agent_conversation(conv_id: str) -> dict[str, Any]:
        return runner.conversation(conv_id).model_dump(mode="json")

    # ------------------------------------------------------------------ web UI

    @app.get("/api/{rest:path}")
    def api_404(rest: str) -> None:
        raise HTTPException(404, f"no API route /api/{rest}")

    static = web_static_dir()
    if (static / "index.html").exists():
        app.mount("/", StaticFiles(directory=static, html=True), name="web")
    else:

        @app.get("/")
        def not_built() -> PlainTextResponse:
            return PlainTextResponse(
                "Lighthouse API is running, but the web UI isn't built.\n"
                "From the repo: npm --prefix web install && npm --prefix web run build\n"
                "API docs: /api/docs\n"
            )

    return app
