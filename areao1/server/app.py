"""FastAPI app: the JSON API under /api plus the built web UI.

Every write goes through :class:`~areao1.core.workspace.Workspace`, so each UI action is a plain,
Git-trackable file change in the workspace.

Local-only hardening: the server binds to 127.0.0.1 (see ``cli.up``), rejects foreign Host headers
(DNS rebinding) and requires an ``X-AreaO1`` header on every write, which a cross-site form or
``fetch`` can't send without a CORS preflight this server never approves.
"""

from __future__ import annotations

import asyncio
import contextlib
import csv
import datetime as dt
import io
import json
import re
import threading
from collections.abc import AsyncIterator
from typing import Any, Literal

import anyio
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import (
    FileResponse,
    JSONResponse,
    PlainTextResponse,
    Response,
    StreamingResponse,
)
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from areao1 import __version__
from areao1.agent.runner import AgentRunner, BudgetExceeded
from areao1.core import clock, names
from areao1.core.models import METRICS_COLUMNS
from areao1.core.workspace import NotFound, WorkspaceError
from areao1.criteria import overview as views
from areao1.criteria.case import Case
from areao1.engine.base import Engine, EngineUnavailable
from areao1.resources import web_static_dir
from areao1.service import Service
from areao1.sources.http import SourceError
from areao1.vault import Vault
from areao1.vault.rulecheck import briefing_text, refresh
from areao1.vault.store import MAX_VAULT_BYTES

WRITE_HEADER = names.WRITE_HEADER.lower()
OLD_WRITE_HEADER = names.PREVIOUS["write_header"].lower()  # a tab left open across the rename still saves
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


class DateBody(BaseModel):
    date: dt.date


class NoteBody(BaseModel):
    note: str = ""


class ProofBody(BaseModel):
    anchor: str
    item: str
    exhibit_id: str | None = None
    note: str = ""


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


class OutreachBody(BaseModel):
    contact_id: str
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=8000)
    purpose: str = "other"


class OutreachEdit(BaseModel):
    subject: str | None = Field(None, min_length=1, max_length=200)
    body: str | None = Field(None, min_length=1, max_length=8000)


class ContactBody(BaseModel):
    name: str | None = None
    emails: list[str] | None = None
    org: str | None = None
    relationship: str | None = None
    notes: str | None = None
    asks: list[str] | None = None
    next_follow_up: dt.date | None = None
    last_touch: dt.date | None = None
    letter_ids: list[str] | None = None
    pipeline_ids: list[str] | None = None


class LetterBody(BaseModel):
    name: str | None = None
    relationship: str | None = None
    credentials: str | None = None
    criteria: list[str] | None = None
    asks: list[str] | None = None
    status: str | None = None
    draft_path: str | None = None
    last_contact: dt.date | None = None


class LetterSendBody(BaseModel):
    contact_id: str | None = None


class CapturePairBody(BaseModel):
    code: str = Field(min_length=4, max_length=20)


class CapturePageBody(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    title: str = Field("", max_length=500)
    html: str = Field(min_length=1, max_length=8_000_000)
    share: bool = False


class OpportunitiesBody(BaseModel):
    enabled: bool | None = None
    verify_on_web: bool | None = None


class MailSettingsBody(BaseModel):
    model_sorting: bool


class MailMoveBody(BaseModel):
    category: str = Field(min_length=3, max_length=20)


class GmailPasswordBody(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=64)


class AgentSettingsBody(BaseModel):
    cheap_mode: bool


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
    app = FastAPI(title="Area O1", version=__version__, docs_url="/api/docs", openapi_url="/api/openapi.json")
    svc = Service(ws)  # every user-initiated write goes through the service layer
    from areao1.google import forget_oauth

    forget_oauth()  # a Google sign-in from before Gmail-only leaves the keychain (ADR 0014, amendment)
    from areao1.engine.connect import forget_anthropic

    forget_anthropic()  # an Anthropic key from before OpenAI-only leaves the keychain (ADR 0015)
    from areao1.scaffold import install_agent_guides

    install_agent_guides(ws)  # the Claude Code skill and Codex notes, for workspaces made before them
    for d in (
        ws.outreach().drafts
    ):  # approved, but the app stopped inside the undo window: not sent, a draft again
        if d.status == "queued":
            ws.put_draft(d.model_copy(update={"status": "draft", "queued_at": None}))
    runner = AgentRunner(ws, engine=engine)
    from areao1.onboarding.api import mount as mount_onboarding

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
        if request.method not in ("GET", "HEAD", "OPTIONS") and "1" not in (
            request.headers.get(WRITE_HEADER),
            request.headers.get(OLD_WRITE_HEADER),
        ):
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
        from areao1.home import workspace_id

        return {
            "ok": True,
            "version": __version__,
            "workspace": ws.root.name,
            "workspace_id": workspace_id(ws.root),
        }

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
        from areao1.jobs.chats import import_chats
        from areao1.sources.chat_export import MAX_EXPORT_BYTES, ExportError

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

        from areao1.core.models import new_id
        from areao1.sources import chat_intake, chat_relevance
        from areao1.sources.chat_export import MAX_EXPORT_BYTES, ExportError

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
        from areao1.core.models import AgentRun, RunUsage
        from areao1.jobs.chats import import_picked

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
                           cost_usd=report.cost_usd, usage=RunUsage.model_validate({k: v for k, v in report.usage.items() if k in RunUsage.model_fields}),
                           finished_at=clock.utcnow())  # fmt: skip
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
        proof_anchor: str = Form("", description="Uploaded from a proof checklist: the activity (ADR 0017)"),
        proof_item: str = Form(""),
    ) -> dict[str, Any]:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        if len(content) > MAX_UPLOAD_BYTES:
            raise HTTPException(413, "file is larger than 25 MB")
        if proof_anchor:
            svc._proof_item(proof_anchor, proof_item)  # before filing anything
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
        if proof_anchor:
            svc.link_proof(proof_anchor, proof_item, exhibit.id)
        return exhibit.model_dump(mode="json")

    # ------------------------------------------------------------------ proof recipes (ADR 0017)

    # ------------------------------------------------------------------ preflight (ADR 0018)

    @app.get("/api/preflight")
    def get_preflight() -> dict[str, Any]:
        from areao1.criteria import preflight

        return {"report": preflight.latest(ws)}

    @app.post("/api/preflight/run")
    def post_preflight_run() -> dict[str, Any]:
        return {"report": svc.run_preflight()}

    @app.post("/api/preflight/{issue_id}/dismiss")
    def post_preflight_dismiss(issue_id: str, body: NoteBody) -> dict[str, Any]:
        from areao1.criteria import preflight

        svc.dismiss_preflight(issue_id, body.note)
        return {"report": preflight.latest(ws)}

    @app.get("/api/proof")
    def get_proof() -> dict[str, Any]:
        from areao1.criteria import proof

        return {"checklists": proof.checklists(ws)}

    @app.post("/api/proof/link")
    def post_proof_link(body: ProofBody) -> dict[str, Any]:
        if not body.exhibit_id:
            raise HTTPException(400, "choose an exhibit")
        return svc.link_proof(body.anchor, body.item, body.exhibit_id).model_dump(mode="json")

    @app.post("/api/proof/waive")
    def post_proof_waive(body: ProofBody) -> dict[str, Any]:
        return svc.waive_proof(body.anchor, body.item, body.note).model_dump(mode="json")

    @app.post("/api/proof/unlink")
    def post_proof_unlink(body: ProofBody) -> dict[str, Any]:
        return svc.unlink_proof(body.anchor, body.item)

    @app.patch("/api/exhibits/{exhibit_id}")
    def remap(exhibit_id: str, body: RemapBody) -> dict[str, Any]:
        return svc.remap_exhibit(exhibit_id, body.criterion, body.evidence_type).model_dump(mode="json")

    @app.post("/api/exhibits/{exhibit_id}/date")
    def redate(exhibit_id: str, body: DateBody) -> dict[str, Any]:
        return svc.redate_exhibit(exhibit_id, body.date).model_dump(mode="json")

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

    @app.get("/api/memory/constellation")
    def memory_constellation() -> dict[str, Any]:
        """Every claim as a star in its criterion's cluster (ADR 0012): status, confidence, conflicts, dates, sources."""
        from areao1.criteria import constellation

        return constellation.stars(ws)

    @app.get("/api/claims/{claim_id}/provenance")
    def claim_provenance(claim_id: str) -> dict[str, Any]:
        """One claim's full trail: the verified excerpt, the raw source, reviews, versions and citing exhibits."""
        from areao1.mcp import tools as mcp_tools

        try:
            return mcp_tools.get_provenance(ws, claim_id)
        except Exception as exc:  # noqa: BLE001  (ToolError: no such claim)
            raise HTTPException(404, str(exc)) from exc

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
        from areao1.jobs.sync import snapshot

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

    @app.post("/api/letters/{letter_id}/draft")
    async def draft_letter(letter_id: str) -> dict[str, Any]:
        """Draft the writer's letter from approved claims only (each sentence cites its claims), for them to sign."""
        from areao1.core.models import AgentRun, RunUsage
        from areao1.criteria import letters

        how = runner.route("letter")
        judge = None
        try:
            ok, _ = runner.engine().available()
            judge = runner.judge() if ok else None
        except Exception:  # noqa: BLE001  (no AI: the template)
            judge = None
        spent: dict[str, Any] = {}

        async def counted(system: str, prompt: str, model: str) -> Any:
            reply = await judge(system, prompt, model)  # type: ignore[misc]
            spent.update(usage=reply.usage, cost=reply.cost_usd)
            return reply

        try:
            out = await letters.draft(ws, letter_id, counted if judge else None, how.model)
        except KeyError as exc:
            raise HTTPException(404, "no such letter writer") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if spent:
            runner.save(AgentRun(kind="manual", engine=runner.engine().name, model=how.model, task=how.task,
                                 tier=how.tier, provider=how.provider, status="done",
                                 prompt=f"Letter draft for {letter_id}", text=out["text"][:4000],
                                 cost_usd=spent.get("cost"),
                                 usage=RunUsage.model_validate({k: v for k, v in (spent.get("usage") or {}).items()
                                                                if k in RunUsage.model_fields}),
                                 finished_at=clock.utcnow()))  # fmt: skip
        return {k: v for k, v in out.items() if k != "text"}

    @app.get("/api/letters/{letter_id}/draft")
    def get_letter_draft(letter_id: str) -> dict[str, Any]:
        lt = next((x for x in ws.letters().letters if x.id == letter_id), None)
        if lt is None or not lt.draft_path or not (ws.root / lt.draft_path).is_file():
            raise HTTPException(404, "no draft yet")
        return {"path": lt.draft_path, "text": (ws.root / lt.draft_path).read_text(encoding="utf-8")}

    @app.post("/api/letters/{letter_id}/send")
    def send_letter_draft(letter_id: str, body: LetterSendBody) -> dict[str, Any]:
        """The draft goes to the writer as an email from you, waiting for Approve & send on Contacts."""
        from areao1.criteria import letters
        from areao1.google import outreach

        lt = next((x for x in ws.letters().letters if x.id == letter_id), None)
        if lt is None or not lt.draft_path or not (ws.root / lt.draft_path).is_file():
            raise HTTPException(404, "draft the letter first")
        contacts = ws.contacts().contacts
        contact = (
            next((c for c in contacts if c.id == body.contact_id), None)
            if body.contact_id
            else next(
                (c for c in contacts if c.name.strip().lower() == lt.name.strip().lower() and c.emails), None
            )
        )
        if contact is None or not contact.emails:
            raise HTTPException(400, f"Add {lt.name} as a contact with an email first (Contacts).")
        raw = (ws.root / lt.draft_path).read_text(encoding="utf-8")
        text = raw.split("\n---\n")[0]
        text = re.sub(r"^# .*$", "", re.sub(r"<!--.*?-->", "", text, flags=re.S), flags=re.M).strip()
        draft = outreach.compose(ws, contact.id, "A draft of your letter, for you to rewrite and sign",
                                 letters.email_body(ws, lt.name, text), purpose="ask", drafted_by="letters")  # fmt: skip
        return svc.save_draft(draft).model_dump(mode="json")

    # ------------------------------------------------------------------ contacts (ADR 0014 §4)

    @app.get("/api/contacts")
    def get_contacts() -> list[dict[str, Any]]:
        from areao1.criteria import contacts

        return contacts.views(ws)

    @app.post("/api/contacts")
    def post_contact(body: ContactBody) -> dict[str, Any]:
        return svc.add_contact(**body.model_dump(exclude_none=True)).model_dump(mode="json")

    @app.patch("/api/contacts/{contact_id}")
    def patch_contact(contact_id: str, body: ContactBody) -> dict[str, Any]:
        """Change a contact. A letter writer's entry becomes a stored contact, linked to the letter."""
        from areao1.criteria import contacts

        start = contacts.from_letter(ws, contact_id)
        changes = body.model_dump(exclude_unset=True)
        if start is not None:
            return svc.add_contact(**{**start, **changes}).model_dump(mode="json")
        return svc.update_contact(contact_id, **changes).model_dump(mode="json")

    @app.delete("/api/contacts/{contact_id}")
    def remove_contact(contact_id: str) -> dict[str, Any]:
        svc.delete_contact(contact_id)
        return {"removed": contact_id}

    # ------------------------------------------------------------------ outreach (ADR 0014 §5)

    @app.get("/api/outreach")
    def get_outreach() -> dict[str, Any]:
        from areao1.google import outreach

        names = {c.id: c.name for c in ws.contacts().contacts}
        cfg = ws.config().outreach
        return {"drafts": [{**d.model_dump(mode="json"), "contact": names.get(d.contact_id, "")}
                           for d in reversed(ws.outreach().drafts)],
                "sent_today": outreach.sent_today(ws), "daily_limit": cfg.daily_limit,
                "undo_seconds": outreach.UNDO_SECONDS,
                "can_send": outreach.can_send(),
                "failures": [{**a.model_dump(mode="json"), "contact": next((names[d.contact_id] for d in
                                                                            ws.outreach().drafts if d.id == a.draft_id
                                                                            and d.contact_id in names), "")}
                             for a in outreach.failures(ws)[:5]]}  # fmt: skip

    @app.post("/api/outreach")
    def post_outreach(body: OutreachBody) -> dict[str, Any]:
        from areao1.google import outreach

        draft = outreach.compose(ws, body.contact_id, body.subject, body.body, body.purpose)
        return svc.save_draft(draft).model_dump(mode="json")

    @app.patch("/api/outreach/{draft_id}")
    def patch_outreach(draft_id: str, body: OutreachEdit) -> dict[str, Any]:
        return svc.edit_draft(draft_id, **body.model_dump(exclude_none=True)).model_dump(mode="json")

    @app.post("/api/outreach/{draft_id}/reject")
    def reject_outreach(draft_id: str) -> dict[str, Any]:
        return svc.reject_draft(draft_id).model_dump(mode="json")

    @app.post("/api/outreach/{draft_id}/send")
    def send_outreach(draft_id: str) -> dict[str, Any]:
        """Your approval: it's sent from your Gmail once the undo window is over (unless you press Undo send)."""
        from areao1.google import outreach

        queued = svc.approve_draft(draft_id)
        if outreach.UNDO_SECONDS <= 0:
            return svc.deliver_draft(draft_id).model_dump(mode="json")
        timer = threading.Timer(outreach.UNDO_SECONDS, _deliver, args=(draft_id,))
        timer.daemon = True
        timer.start()
        return {**queued.model_dump(mode="json"), "undo_seconds": outreach.UNDO_SECONDS}

    @app.post("/api/outreach/{draft_id}/undo")
    def undo_outreach(draft_id: str) -> dict[str, Any]:
        """Undo send: within the window, the email goes back to being a draft and nothing is sent."""
        return svc.undo_send(draft_id).model_dump(mode="json")

    def _deliver(draft_id: str) -> None:
        with contextlib.suppress(WorkspaceError):  # a refusal is logged and shows on the Contacts page
            svc.deliver_draft(draft_id)

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
        from areao1.core.calendar import render

        return Response(render(ws), media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": 'inline; filename="areao1.ics"'})  # fmt: skip

    # ------------------------------------------------------------------ jobs

    @app.get("/api/jobs")
    def get_jobs() -> list[dict[str, Any]]:
        from areao1.jobs.scheduler import jobs_status

        return jobs_status(ws)

    @app.post("/api/jobs/{name}/run")
    def run_job_now(name: str) -> dict[str, Any]:
        from areao1.jobs import JOBS
        from areao1.jobs.scheduler import run_job

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
        from areao1 import sources

        return [
            {**s.model_dump(mode="json"), "token_help": sources.token_help(s.kind)}
            for s in ws.sources().sources
        ]

    @app.post("/api/sources")
    def add_source(body: SourceBody) -> dict[str, Any]:
        from areao1.jobs.sync import import_source

        try:
            report = import_source(ws, body.input, token=body.token or None, snapshot=body.snapshot)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return report.__dict__

    @app.post("/api/sources/{source_id:path}/sync")
    def sync_one(source_id: str) -> dict[str, Any]:
        from areao1.jobs.sync import sync_source

        _source(source_id)
        return sync_source(ws, source_id).__dict__

    @app.put("/api/sources/{source_id:path}/token")
    def reauth(source_id: str, body: TokenBody) -> dict[str, Any]:
        from areao1.core.secrets import set_secret

        _source(source_id)
        where = set_secret(source_id, body.token, ws.root)
        ws.update_source(source_id, auth="token", secret_ref=source_id, last_error=None)
        return {"stored_in": where}

    @app.delete("/api/sources/{source_id:path}")
    def remove(source_id: str) -> dict[str, Any]:
        from areao1.core.secrets import delete_secret

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
        from areao1.core.secrets import get_secret
        from areao1.notify import history

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
            "opportunities": cfg.opportunities.model_dump(),
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
        from areao1.notify import Notification, send

        report = send(ws, Notification("test", "Area O1 test", "Notifications are working.",
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

    @app.put("/api/settings/agent")
    def put_agent_settings(body: AgentSettingsBody) -> dict[str, Any]:
        """Cheap mode: chat on the mid tier (ADR 0009 §3)."""
        svc.set_cheap_mode(body.cheap_mode)
        return runner.status()

    @app.put("/api/settings/opportunities")
    def put_opportunities(body: OpportunitiesBody) -> dict[str, Any]:
        """The daily opportunity job: on or off (off by default), and web confirmation of finds (ADR 0016)."""
        return dict(svc.set_opportunities(body.enabled, body.verify_on_web))

    @app.post("/api/opportunities/run")
    async def run_opportunities() -> dict[str, Any]:
        """Run the daily opportunity check now (even when the schedule is off)."""
        from areao1.google import mail, opportunities

        try:
            out = await opportunities.run_now(ws, runner)
        except mail.MailError as exc:
            raise HTTPException(502, str(exc)) from exc
        return {
            "lines": out["lines"],
            "cost_usd": out["cost_usd"],
            "finds": [c.model_dump(mode="json") for c in out["finds"]],
        }

    @app.put("/api/settings/mail")
    def put_mail_settings(body: MailSettingsBody) -> dict[str, Any]:
        """Model sorting for the Mail view: off sorts by rules only."""
        return dict(svc.set_mail_sorting(body.model_sorting))

    @app.get("/api/agent/status")
    def agent_status() -> dict[str, Any]:
        return runner.status()

    # ------------------------------------------------------------------ Gmail (ADR 0014 and its amendment)

    @app.get("/api/gmail")
    def gmail_status() -> dict[str, Any]:
        from areao1.google import mail

        return mail.status()

    @app.put("/api/gmail")
    def gmail_connect(body: GmailPasswordBody) -> dict[str, Any]:
        """Gmail with an app password: one test login, then the keychain only."""
        from areao1.google import mail

        try:
            return mail.connect(body.email, body.password)
        except mail.MailError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.delete("/api/gmail")
    def gmail_disconnect() -> dict[str, Any]:
        from areao1.google import mail

        return mail.disconnect()

    @app.post("/api/gmail/sync")
    def gmail_sync() -> dict[str, Any]:
        """Refresh the threads with your contacts now (the google job does it every 15 minutes)."""
        from areao1.google import gmail, mail

        try:
            return {"lines": gmail.sync(ws)}
        except mail.MailError as exc:
            raise HTTPException(502, str(exc)) from exc

    # ------------------------------------------------------------------ the Mail view (read-only)

    @app.get("/api/mail")
    def get_mail() -> dict[str, Any]:
        """Case-relevant mail only, by category, with counts. Headers and the redacted subject; no bodies."""
        from areao1.google import mailview

        return mailview.view(ws)

    @app.post("/api/mail/sync")
    async def mail_sync() -> dict[str, Any]:
        """Read new mail (PEEK only: nothing turns read in Gmail), sort it by rules, then the mundane tier."""
        from areao1.core.models import AgentRun, RunUsage
        from areao1.google import mail, mailview

        def mundane() -> Any:
            try:
                return runner.mundane("classify")
            except BudgetExceeded:
                return None, runner.route("classify")  # over the cap: rules only

        try:
            out = await mailview.sync(ws, mundane)
        except mail.MailError as exc:
            raise HTTPException(502, str(exc)) from exc
        how = out.get("route")
        if how is not None:  # the model's cost shows on the Agent page and counts toward the month
            runner.save(AgentRun(kind="manual", engine=how.provider if how.provider == "openai" else runner.engine().name,
                                 model=how.model, task=how.task, tier=how.tier, provider=how.provider, status="done",
                                 prompt="Mail view: sorting new mail", text=" ".join(out["lines"]),
                                 cost_usd=out["cost_usd"], usage=RunUsage.model_validate(out["usage"]),
                                 finished_at=clock.utcnow()))  # fmt: skip
        return {"lines": out["lines"], **mailview.view(ws)}

    @app.put("/api/mail/{gm_id}")
    def move_mail(gm_id: str, body: MailMoveBody) -> dict[str, Any]:
        """Move a message to another category (or hide it); the move teaches a rule for that sender."""
        from areao1.google import mailview

        try:
            mailview.move(ws, gm_id, body.category)
        except KeyError as exc:
            raise HTTPException(404, "no such message in the Mail view") from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return mailview.view(ws)

    @app.post("/api/mail/{gm_id}/import")
    def mail_import(gm_id: str) -> dict[str, Any]:
        """Import the original attached to a message forwarded as an attachment (PEEK): its file is kept and it goes
        to the Inbox with its own sender check and stage, like a dropped .eml."""
        from areao1.google import mail, mailview

        try:
            cand = mailview.import_forwarded(ws, gm_id)
        except KeyError as exc:
            raise HTTPException(404, "no forwarded original on that message") from exc
        except mail.MailError as exc:
            raise HTTPException(502, str(exc)) from exc
        return cand.model_dump(mode="json")

    @app.get("/api/mail/{gm_id}/text")
    def mail_text(gm_id: str) -> JSONResponse:
        """Open a message: its text, fetched from Gmail now with PEEK, returned and never written to disk."""
        from areao1.google import mail, mailview

        try:
            text = mailview.open_item(ws, gm_id)
        except KeyError as exc:
            raise HTTPException(404, "no such message in the Mail view") from exc
        except mail.MailError as exc:
            raise HTTPException(502, str(exc)) from exc
        return JSONResponse(text, headers={"Cache-Control": "no-store"})

    @app.get("/api/ai")
    def ai_status() -> dict[str, Any]:
        from areao1.engine import connect

        return connect.status()

    @app.put("/api/ai/key")
    def ai_key(body: KeyBody) -> dict[str, Any]:
        """Check an OpenAI key with the free model-list request, then keep it in the OS keychain only."""
        from areao1.engine import connect

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
        from areao1.engine import connect

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

    # ------------------------------------------------------------------ capture extension (ADR 0011 §2)

    @app.post("/api/vault/capture/code")
    def capture_code() -> dict[str, Any]:
        """A one-time pairing code for the browser extension (ten minutes, once)."""
        from areao1.vault import capture

        return {"code": capture.new_code(), "expires_in": capture.CODE_TTL}

    @app.get("/api/vault/capture/status")
    def capture_status() -> dict[str, Any]:
        from areao1.vault import capture

        return {**capture.status(ws), "watched": len(capture.watched(ws))}

    @app.delete("/api/vault/capture")
    def capture_unpair() -> dict[str, Any]:
        from areao1.vault import capture

        capture.unpair(ws)
        return capture.status(ws)

    @app.post("/api/vault/capture/pair")
    def capture_pair(body: CapturePairBody) -> dict[str, Any]:
        """The extension trades a pairing code for its capture token (shown once) and the pages to watch."""
        from areao1.vault import capture

        try:
            token = capture.pair(ws, body.code)
        except PermissionError as exc:
            raise HTTPException(403, str(exc)) from exc
        return {"token": token, "sources": capture.watched(ws)}

    @app.get("/api/vault/capture/sources")
    def capture_sources(request: Request) -> dict[str, Any]:
        from areao1.vault import capture

        if not capture.authorized(ws, request.headers.get("authorization")):
            raise HTTPException(401, "pair the extension again (Settings > Knowledge)")
        return {"sources": capture.watched(ws)}

    @app.post("/api/vault/capture/page")
    def capture_page(body: CapturePageBody, request: Request) -> dict[str, Any]:
        """A page the person visited, sent by the paired extension; imported only if it's a listed source."""
        from areao1.vault import capture

        if not capture.authorized(ws, request.headers.get("authorization")):
            raise HTTPException(401, "pair the extension again (Settings > Knowledge)")
        try:
            return capture.capture(ws, body.url, body.title, body.html, body.share)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from exc

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
            raise HTTPException(400, "the vault is turned off (vault.enabled in areao1.yaml)")
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
        from areao1.agent.guardrails import refusals

        return refusals(ws)

    @app.get("/api/agent/missions")
    def agent_missions() -> list[dict[str, Any]]:
        from areao1.agent.missions import missions_status

        return missions_status(ws, runner)

    @app.put("/api/settings/missions")
    def put_missions(body: MissionsBody) -> dict[str, Any]:
        return svc.set_missions(**body.model_dump(exclude_none=True)).model_dump()

    @app.post("/api/agent/missions/{name}/run")
    async def agent_mission_run(name: str) -> dict[str, Any]:
        from areao1.agent import missions

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
                "Area O1 API is running, but the web UI isn't built.\n"
                "From the repo: npm --prefix web install && npm --prefix web run build\n"
                "API docs: /api/docs\n"
            )

    return app
