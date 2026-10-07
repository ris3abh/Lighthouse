"""Onboarding routes. Answers and steps are page writes (service layer); lookups are connector runs the person
approved (system routes, like adding a source), and their status is saved through the service layer too."""

from __future__ import annotations

import hashlib
from typing import Any

import anyio
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from lighthouse_gc.core import clock
from lighthouse_gc.criteria.case import Case
from lighthouse_gc.onboarding import flow
from lighthouse_gc.onboarding.models import LinkedInSource, OnboardingState, Turn
from lighthouse_gc.service import Service

MAX_PDF_BYTES = 10_000_000
PANEL = ("name", "headline", "location", "employer", "role", "education", "awards", "publications", "judging",
         "memberships", "certifications", "links", "skills")  # fmt: skip


class Answer(BaseModel):
    id: str
    action: str
    value: Any = None


class StepBody(BaseModel):
    step: str


class LookupBody(BaseModel):
    accept: bool


def view(ws: Case, runner: Any = None) -> dict[str, Any]:
    state = ws.onboarding()
    if runner is not None:
        _refresh_finds(state, runner)
    q = flow.next_question(state) if state.step == "questions" else None
    panel = []
    for key in PANEL:
        f = state.field(key)
        if f is not None:
            panel.append(
                {"key": key, "label": f.label, "value": f.value, "status": f.status, "quote": f.quote}
            )
    if state.target_date and state.target_date != "skipped":
        panel.append(
            {"key": "when", "label": "Hoping to file", "status": "confirmed", "value": state.target_date}
        )
    elif state.target_date == "skipped":
        panel.append({"key": "when", "label": "Hoping to file", "status": "skipped", "value": ""})
    if state.target_profile:
        panel.append({"key": "target", "label": "Petition", "status": "confirmed" if state.target_profile != "unsure" else "skipped",
                      "value": flow.PROFILES.get(state.target_profile, "")})  # fmt: skip
    return {"needed": ws.needs_onboarding(), "state": state.model_dump(mode="json"), "question": q.as_dict() if q else None,
            "panel": panel, "person": ws.person().model_dump(mode="json")}  # fmt: skip


def _refresh_finds(state: OnboardingState, runner: Any) -> None:
    """A web lookup runs as an agent run in the background; show where it got to (not saved until the next write)."""
    from lighthouse_gc.core.text import plural

    for lk in state.lookups:
        if lk.kind != "find" or lk.status != "accepted" or not lk.run_id:
            continue
        try:
            run = runner.get(lk.run_id)
        except Exception:
            continue
        if run.status == "running":
            lk.result = "Searching the web…"
        elif run.status == "done":
            lk.status = "done"
            n = len(run.proposals)
            lk.result = (f"Found {plural(n, 'page')} that may confirm it; check your Inbox." if n else
                         "I couldn't find an official page that names you. The to-do stays open for your own proof.")  # fmt: skip
        else:
            lk.status = "failed"
            lk.result = f"The search stopped ({run.error or run.stop_reason or run.status})."[:300]


def todos_for(ws: Case, state: OnboardingState) -> list[Any]:
    profile = state.target_profile if state.target_profile in flow.PROFILES else None
    return flow.todos_from(state, {c.id for c in ws.profile(profile).criteria}, clock.today())


def _advance(state: OnboardingState, ws: Case | None = None) -> None:
    """Move to the next step once the current one has nothing left to ask."""
    if state.step == "questions" and flow.next_question(state) is None:
        state.lookups = flow.offer_lookups(state, todos_for(ws, state) if ws is not None else None)
        state.step = "lookups" if state.lookups else "chats"
    # Wait while a web lookup the person approved is still running, so they see it finish (or press Continue).
    if state.step == "lookups" and all(lk.status not in ("offered", "accepted") for lk in state.lookups):
        state.step = "chats"


def _start(state: OnboardingState) -> None:
    if state.status == "new":
        state.status = "in_progress"
        state.started_at = clock.utcnow()


def mount(app: FastAPI, ws: Case, svc: Service, judge: Any = None, runner: Any = None) -> None:
    """``judge``: a callable returning the model judge (or None) for non-LinkedIn PDFs. ``runner``: the agent
    runner, for web lookups the person said Yes to."""

    def view_now() -> dict[str, Any]:
        return view(ws, runner)

    @app.get("/api/onboarding")
    def get_onboarding() -> dict[str, Any]:
        return view_now()

    @app.post("/api/onboarding/linkedin")
    async def upload_linkedin(file: UploadFile = File(...)) -> dict[str, Any]:
        """A LinkedIn PDF: text extracted and redacted locally, fields parsed, nothing sent to the web."""
        data = await file.read(MAX_PDF_BYTES + 1)
        if len(data) > MAX_PDF_BYTES:
            raise HTTPException(413, "that PDF is larger than 10 MB")
        if not data.startswith(b"%PDF"):
            raise HTTPException(400, "that isn't a PDF. On LinkedIn: your profile, More, Save to PDF.")
        try:
            text, redactions, parsed = flow.read_pdf(data)
        except Exception as exc:  # unreadable PDF
            raise HTTPException(400, f"couldn't read that PDF ({type(exc).__name__})") from exc
        parser = "linkedin" if parsed else "none"
        model_judge = judge() if callable(judge) else None
        if not parsed and text.strip() and model_judge is not None:
            from lighthouse_gc.onboarding.linkedin import extract_with_model

            try:
                parsed = await extract_with_model(text, model_judge, ws.config().agent.models.check)
                parser = "model" if parsed else "none"
            except Exception:
                parsed = {}
        state = ws.onboarding()
        _start(state)
        fields = flow.fields_from(parsed)
        state.fields = fields
        state.source = LinkedInSource(
            filename=file.filename or "profile.pdf",
            sha256=hashlib.sha256(data).hexdigest(),
            chars=len(text),
            redactions=redactions,
            parser=parser,
        )  # type: ignore[arg-type]
        state.step = "questions"
        state.transcript = [Turn(who="lighthouse", text=flow.opening(fields, parser))]
        _advance(state)
        evidence = (
            flow.evidence_for(data, file.filename or "profile.pdf", text, fields) if text.strip() else None
        )
        svc.onboarding_save(state, "onboarding.linkedin", summary=f"read {len(fields)} fields from {file.filename}",
                            evidence=evidence)  # fmt: skip
        return view_now()

    @app.post("/api/onboarding/answer")
    def answer(body: Answer) -> dict[str, Any]:
        state = ws.onboarding()
        if state.step != "questions":
            raise HTTPException(409, "there's no question waiting")
        asked = flow.next_question(state)
        try:
            writes = flow.answer(state, body.id, body.action, body.value)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        was_asking = state.step == "questions"
        if asked is not None:
            state.transcript += [Turn(who="lighthouse", text=asked.text),
                                 Turn(who="you", text=flow.reply_text(asked, body.action, body.value))]  # fmt: skip
        _advance(state, ws)
        person = dict(writes["person"])
        if writes.get("filing_date") or writes["profile"]:
            from datetime import date

            update: dict[str, Any] = {}
            if writes.get("filing_date"):
                update["target_date"] = date.fromisoformat(writes["filing_date"])
            if writes["profile"]:
                update["profile"] = writes["profile"]
            person["filing_target"] = ws.person().filing_target.model_copy(update=update)
        todos = None
        if was_asking and state.step != "questions":  # the last answer: what was confirmed becomes next steps
            todos = flow.todos_from(
                state, {c.id for c in ws.profile(writes["profile"] or None).criteria}, clock.today()
            )
        svc.onboarding_save(state, "onboarding.answer", summary=f"{body.id}: {body.action}", person=person or None,
                            todos=todos)  # fmt: skip
        if writes["profile"] and writes["profile"] != ws.profile_id():
            svc.set_profile(writes["profile"])
        return view_now()

    @app.post("/api/onboarding/step")
    def step(body: StepBody) -> dict[str, Any]:
        state = ws.onboarding()
        _start(state)
        s = body.step
        if s == "skip_linkedin" and state.step == "linkedin":
            state.step = "questions"
            state.transcript = [Turn(who="lighthouse", text="No problem, we'll do without it. Nice to meet you! "
                                     "Just two quick questions, and you can skip either.")]  # fmt: skip
        elif s == "lookups_done" and state.step == "lookups":
            if runner is not None:
                _refresh_finds(state, runner)  # keep what finished; a search still running carries on
            for lk in state.lookups:
                if lk.status == "offered":
                    lk.status = "declined"
            state.step = "chats"
        elif s in ("chats_done", "chats_skip") and state.step == "chats":
            state.chats = "imported" if s == "chats_done" else "skipped"
            state.step = "tour"
        elif s in ("tour_done", "tour_skip") and state.step == "tour":
            state.tour = "seen" if s == "tour_done" else "skipped"
            state.step = "done"
            state.status = "done"
            state.finished_at = clock.utcnow()
        elif s == "skip_all":
            state.step = "done"
            state.status = "skipped"
            state.finished_at = clock.utcnow()
        else:
            raise HTTPException(409, f"can't {s} from the {state.step} step")
        _advance(state)
        svc.onboarding_save(state, "onboarding.step", summary=s)
        return view_now()

    @app.post("/api/onboarding/restart")
    def restart() -> dict[str, Any]:
        """Run onboarding again (from Settings). What it added stays; the answers start over."""
        svc.onboarding_save(OnboardingState(status="in_progress", started_at=clock.utcnow()), "onboarding.restart",
                            summary="started over")  # fmt: skip
        return view_now()

    @app.post("/api/onboarding/lookups/{lookup_id}")
    async def lookup(lookup_id: str, body: LookupBody) -> dict[str, Any]:
        """Run a lookup the person said Yes to (or decline it). Finds go to the Inbox, never into the case."""
        state = ws.onboarding()
        lk = next((x for x in state.lookups if x.id == lookup_id), None)
        if lk is None or state.step != "lookups":
            raise HTTPException(404, f"no lookup {lookup_id!r}")
        if lk.status != "offered":
            raise HTTPException(409, f"that lookup is already {lk.status}")
        if not body.accept:
            lk.status = "declined"
        elif lk.kind == "find":
            lk.status = "accepted"
            person = ws.person()
            todo = next((t for t in ws.todos().todos if t.id == lk.todo_id), None)
            try:
                if runner is None:
                    raise RuntimeError("the agent isn't available")
                run = await runner.start("manual", flow.find_task(todo.kind if todo else "", lk.targets[0], person.name),
                                         namesake=[n for n in (person.name, *person.aliases) if n])  # fmt: skip
                lk.run_id, lk.result = run.id, "Searching the web…"
            except Exception as exc:  # no AI connected, or over budget: nothing was searched
                lk.status = "failed"
                lk.result = (
                    f"This one needs your AI connected (Settings > Agent). Nothing was searched. ({exc})"
                )[:300]
        else:
            lk.status = "accepted"
            try:
                lk.result = await anyio.to_thread.run_sync(
                    run_lookup, ws, lk.kind, lk.targets
                )  # sync connectors
                lk.status = "done"
            except Exception as exc:  # network or connector problem: say so, don't stop onboarding
                lk.result = f"couldn't finish: {exc}"[:300]
                lk.status = "failed"
        _advance(state)
        svc.onboarding_save(state, "onboarding.lookup", summary=f"{lookup_id}: {lk.status}")
        return view_now()


def run_lookup(ws: Case, kind: str, targets: list[str]) -> str:
    """Connector imports for confirmed links; arXiv title search for confirmed papers (namesake-checked)."""
    from lighthouse_gc.core.text import plural

    if kind == "papers":
        from lighthouse_gc.sources import arxiv

        person = ws.person()
        cands, missing = [], []
        for title in targets:
            hits = [e for e in arxiv.search_title(title) if flow.paper_matches(title, e.get("title", ""))]
            if not hits:
                missing.append(title)
                continue
            cands.append(flow.paper_candidate(hits[0], person.name, person.aliases))
        new = ws.add_candidates(cands)
        namesakes = sum(1 for c in new if c.facts.get("namesake_check") != "passed")
        msg = f"{plural(len(new), 'paper')} found and sent to your Inbox"
        if namesakes:
            msg += f" ({namesakes} flagged as a possible namesake)"
        if missing:
            msg += f"; not on arXiv: {'; '.join(missing)}"
        return msg + "."
    from lighthouse_gc.jobs.sync import import_source

    reports = [import_source(ws, url) for url in targets]
    added = sum(r.candidates_added for r in reports)
    return f"Imported {', '.join(r.source_id for r in reports)}: {plural(added, 'suggestion')} in your Inbox."
