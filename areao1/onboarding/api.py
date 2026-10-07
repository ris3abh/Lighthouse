"""Onboarding routes. Answers and steps are page writes (service layer); lookups are connector runs the person
approved (system routes, like adding a source), and their status is saved through the service layer too."""

from __future__ import annotations

import hashlib
from typing import Any, Literal

import anyio
from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel

from areao1.core import clock
from areao1.criteria.case import Case
from areao1.onboarding import flow
from areao1.onboarding.models import LinkedInSource, OnboardingState, Step, Turn
from areao1.service import Service

MAX_PDF_BYTES = 10_000_000
PANEL = ("name", "headline", "location", "employer", "role", "education", "awards", "publications", "judging",
         "memberships", "certifications", "links", "skills")  # fmt: skip


class Answer(BaseModel):
    id: str
    action: str
    value: Any = None


class StepBody(BaseModel):
    step: str


class AiBody(BaseModel):
    choice: Literal["key", "skip"]  # an Anthropic API key; claude.ai login isn't offered (ADR 0013 §4)


class LookupBody(BaseModel):
    accept: bool


class GotoBody(BaseModel):
    step: str
    question: str | None = None


def nav(state: OnboardingState) -> dict[str, Any]:
    """Where Back goes from here, and which steps the step bar can jump to (any step already reached)."""
    reached = flow.STEPS.index(state.reached) if state.reached in flow.STEPS else 0
    back: dict[str, Any] | None = None
    if state.step == "questions":
        current = flow.next_question(state)
        prev = flow.previous_question(state, current.id if current else None)
        back = {"step": "questions", "question": prev} if prev else {"step": "linkedin"}
    elif state.step == "ai":
        back = {"step": "questions", "question": flow.previous_question(state, None)}
    elif state.step == "lookups":
        back = {"step": "ai"}
    elif state.step == "chats":
        back = {"step": "lookups"} if state.lookups else {"step": "ai"}
    elif state.step == "mail":
        back = {"step": "chats"}
    elif state.step == "tour":
        back = {"step": "mail"}
    return {"back": back, "reached": state.reached,
            "steps": [{"id": s, "reachable": i <= reached} for i, s in enumerate(flow.STEPS[:-1])]}  # fmt: skip


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
            "panel": panel, "person": ws.person().model_dump(mode="json"), "nav": nav(state)}  # fmt: skip


RETRYABLE = ("nothing_found", "unreachable", "blocked", "failed")


def find_outcome(run: Any) -> tuple[str, str]:
    """(status, plain result) for a finished web search."""
    from areao1.core.text import plural

    if run.status == "running":
        return "searching", "Searching the web…"
    if run.status == "done":
        n = len(run.proposals)
        if n:
            return "found", f"Found {plural(n, 'page')} that may confirm it; check your Inbox."
        return "nothing_found", ("I couldn't find an official page that names you, so I proposed nothing. "
                                 "The to-do stays open for your own proof.")  # fmt: skip
    return "failed", f"The search stopped: {run.error or run.stop_reason or run.status}."[:300]


def _refresh_finds(state: OnboardingState, runner: Any) -> bool:
    """Bring each web search's status up to date from its agent run. True when anything changed."""
    changed = False
    for lk in state.lookups:
        if lk.kind != "find" or lk.status not in ("searching", "accepted") or not lk.run_id:
            continue
        try:
            status, result = find_outcome(runner.get(lk.run_id))
        except Exception:
            continue
        if (status, result) != (lk.status, lk.result):
            lk.status, lk.result, changed = status, result, True  # type: ignore[assignment]
    return changed


def classify(exc: Exception) -> tuple[str, str]:
    """A lookup error as (status, plain reason): the site couldn't be reached, it blocked us, or something else."""
    msg = str(exc)
    low = msg.lower()
    if any(s in low for s in ("can't resolve", "name or service", "nodename", "timed out", "timeout", "connect",
                              "unreachable", "no route", "ssl")):  # fmt: skip
        return "unreachable", f"Couldn't reach the site ({msg[:160]}). Check the address, or try again later."
    if any(
        s in low for s in ("403", "429", "blocked", "captcha", "unreadable", "forbidden", "too many requests")
    ):
        return (
            "blocked",
            f"The site blocked automated reading ({msg[:160]}). Save the page yourself and drop it in the Inbox.",
        )
    if "private" in low or "not allowed" in low or "unsafe" in low:
        return "failed", f"That address isn't a public web page ({msg[:160]})."
    return "failed", f"Something went wrong: {msg[:200]}"


def todos_for(ws: Case, state: OnboardingState) -> list[Any]:
    profile = state.target_profile if state.target_profile in flow.PROFILES else None
    return flow.todos_from(state, {c.id for c in ws.profile(profile).criteria}, clock.today())


def _advance(state: OnboardingState, ws: Case | None = None) -> None:
    """Move to the next step once the current one has nothing left to ask."""
    if state.step == "questions" and flow.next_question(state) is None:
        fresh = flow.offer_lookups(state, todos_for(ws, state) if ws is not None else None)
        old = {lk.id: lk for lk in state.lookups}
        # Going back and changing an answer re-offers only the lookups it affects; the rest keep their outcome.
        state.lookups = [
            old[lk.id] if lk.id in old and old[lk.id].targets == lk.targets else lk for lk in fresh
        ]
        # Connect your AI comes before the lookups (web searches need it); once chosen, it isn't asked again. An old
        # "login" choice (no longer offered) asks again.
        state.step = "ai" if state.ai in ("pending", "login") else after_ai(state)
    # Stay on the lookups so every outcome (and Retry) stays visible; Continue moves on at any time. Only a step
    # where every lookup was declined moves on by itself.
    if state.step == "lookups" and all(lk.status == "declined" for lk in state.lookups):
        state.step = "chats"
    if flow.STEPS.index(state.step) > flow.STEPS.index(
        state.reached if state.reached in flow.STEPS else "linkedin"
    ):
        state.reached = state.step


def after_ai(state: OnboardingState) -> Step:
    return "lookups" if state.lookups else "chats"


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
            from areao1.onboarding.linkedin import extract_with_model

            try:
                model = runner.route("pdf").model if runner is not None else ws.config().agent.models.check
                parsed = await extract_with_model(text, model_judge, model)
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
        state.transcript = [Turn(who="areao1", text=flow.opening(fields, parser))]
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
            state.transcript += [Turn(who="areao1", text=asked.text),
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
        stale: list[str] = []
        if was_asking and state.step != "questions":  # the last answer: what was confirmed becomes next steps
            todos = todos_for(ws, state)
            keep = {td.id for td in todos}  # an answer changed on the way back: its old to-do goes away
            stale = [td.id for td in ws.todos().todos
                     if td.source == "onboarding" and td.status == "open" and td.id not in keep]  # fmt: skip
        svc.onboarding_save(state, "onboarding.answer", summary=f"{body.id}: {body.action}", person=person or None,
                            todos=todos, dismiss=stale)  # fmt: skip
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
            state.transcript = [Turn(who="areao1", text="No problem, we'll do without it. Nice to meet you! "
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
            state.step = "mail"
        elif s in ("mail_done", "mail_skip") and state.step == "mail":
            from areao1.google import mail

            if s == "mail_done" and not mail.connected():
                raise HTTPException(409, "Gmail isn't connected yet")
            state.mail = "connected" if s == "mail_done" else "skipped"
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

    @app.post("/api/onboarding/goto")
    def goto(body: GotoBody) -> dict[str, Any]:
        """Back, the step bar and the browser's back / forward: go to a step already reached, or to a question
        already answered. Every answer is kept; changing one updates the profile and re-offers what it affects."""
        state = ws.onboarding()
        if state.status not in ("new", "in_progress"):
            raise HTTPException(409, "onboarding isn't running")
        if body.step not in flow.STEPS[:-1]:
            raise HTTPException(400, f"unknown step {body.step!r}")
        if flow.STEPS.index(body.step) > flow.STEPS.index(state.reached):
            raise HTTPException(409, f"you haven't reached {body.step} yet")
        state.revisit = None
        if body.step == "questions":
            ids = flow.question_ids(state)
            qid = body.question
            if qid is not None and qid not in ids:
                raise HTTPException(404, f"no question {qid!r}")
            if qid is not None and not flow.answered(state, qid):
                pending = flow.next_question(state)
                if pending is None or pending.id != qid:
                    raise HTTPException(409, "answer the questions before it first")
            elif qid is not None:
                state.revisit = qid
            elif flow.next_question(state) is None:
                state.revisit = flow.previous_question(state, None)  # all answered: reopen the last one
        elif body.step == "lookups" and not state.lookups:
            raise HTTPException(409, "there were no lookups to offer")
        state.step = body.step  # type: ignore[assignment]
        svc.onboarding_save(state, "onboarding.goto", summary=f"{body.step} {body.question or ''}".strip())
        return view_now()

    @app.post("/api/onboarding/ai")
    def choose_ai(body: AiBody) -> dict[str, Any]:
        """Connect your AI: the API key just saved, or later."""
        from areao1.engine import connect

        state = ws.onboarding()
        if state.step != "ai":
            raise HTTPException(409, "this isn't the AI step")
        if body.choice == "key" and not connect.key_source():
            raise HTTPException(409, "save a key first")
        state.ai = "key" if body.choice == "key" else "skipped"
        state.step = after_ai(state)
        _advance(state)
        svc.onboarding_save(state, "onboarding.ai", summary=state.ai)
        return view_now()

    @app.post("/api/onboarding/restart")
    def restart() -> dict[str, Any]:
        """Run onboarding again (from Settings). What it added stays; the answers start over."""
        svc.onboarding_save(OnboardingState(status="in_progress", started_at=clock.utcnow()), "onboarding.restart",
                            summary="started over")  # fmt: skip
        return view_now()

    @app.post("/api/onboarding/lookups/{lookup_id}")
    async def lookup(lookup_id: str, body: LookupBody) -> dict[str, Any]:
        """Run a lookup the person said Yes to (or decline it), or retry one that didn't work. Finds go to the
        Inbox, never into the case. A failure never blocks moving on."""
        state = ws.onboarding()
        lk = next((x for x in state.lookups if x.id == lookup_id), None)
        if lk is None or state.step != "lookups":
            raise HTTPException(404, f"no lookup {lookup_id!r}")
        if lk.status not in ("offered", *RETRYABLE):
            raise HTTPException(409, f"that lookup is already {lk.status}")
        if not body.accept:
            lk.status = "declined"
        elif lk.kind == "find":
            person = ws.person()
            todo = next((t for t in ws.todos().todos if t.id == lk.todo_id), None)
            try:
                if runner is None:
                    raise RuntimeError("the agent isn't available")
                run = await runner.start("manual", flow.find_task(todo.kind if todo else "", lk.targets[0], person.name),
                                         namesake=[n for n in (person.name, *person.aliases) if n])  # fmt: skip
                lk.status, lk.run_id, lk.result = "searching", run.id, "Searching the web…"
            except Exception as exc:  # no AI connected, or over budget: nothing was searched
                lk.status = "failed"
                lk.result = (
                    f"This one needs your AI connected (Settings > Agent). Nothing was searched. ({exc})"[
                        :300
                    ]
                )
        else:
            try:
                status, lk.result, lk.resolved = await anyio.to_thread.run_sync(
                    run_lookup, ws, lk.kind, lk.targets
                )  # sync connectors
                lk.status = status  # type: ignore[assignment]
            except Exception as exc:  # say what happened; onboarding carries on
                lk.status, lk.result = classify(exc)  # type: ignore[assignment]
        _advance(state)
        svc.onboarding_save(state, "onboarding.lookup", summary=f"{lookup_id}: {lk.status}")
        return view_now()

    def _search_finished(run: Any) -> None:
        """Save a web search's outcome when its run ends, even if the person already moved on."""
        state = ws.onboarding()
        lk = next((x for x in state.lookups if x.kind == "find" and x.run_id == run.id), None)
        if lk is None:
            return
        lk.status, lk.result = find_outcome(run)  # type: ignore[assignment]
        _advance(state)
        Service(ws, actor=f"agent:{run.id}").onboarding_save(state, "onboarding.lookup_result",
                                                             summary=f"{lk.id}: {lk.status}")  # fmt: skip

    if runner is not None and hasattr(runner, "on_finish"):
        runner.on_finish.append(_search_finished)


def run_lookup(ws: Case, kind: str, targets: list[str]) -> tuple[str, str, dict[str, str]]:
    """(status, plain result, entry -> real title). Connector imports for confirmed links; arXiv for confirmed papers, by arXiv id when
    the entry has one, else by its title with venue tails dropped (namesake-checked)."""
    from areao1.core.text import plural

    if kind == "papers":
        from areao1.sources import arxiv

        person = ws.person()
        cands, missing, dois = [], [], []
        resolved: dict[str, str] = {}
        for item in targets:
            how, ref = flow.paper_ref(item)
            if how == "doi":
                dois.append(ref)
                continue
            hits = (arxiv.by_id(ref) if how == "arxiv" else
                    [e for e in arxiv.search_title(ref) if flow.paper_matches(ref, e.get("title", ""))])  # fmt: skip
            if not hits:
                missing.append(ref)
                continue
            cands.append(flow.paper_candidate(hits[0], person.name, person.aliases))
            if hits[0].get("title") and hits[0]["title"] != item:
                resolved[item] = hits[0]["title"]  # an arXiv link now shows the paper's title
        new = ws.add_candidates(cands)
        notes = []
        if missing:
            notes.append(f"not on arXiv: {'; '.join(missing)}")
        if dois:
            notes.append(f"DOIs aren't looked up yet ({'; '.join(dois)}); add the title or an arXiv link")
        if not cands:
            detail = "; ".join(notes)
            return (
                "nothing_found",
                f"Nothing found. {detail[:1].upper()}{detail[1:]}." if notes else "Nothing found.",
                {},
            )
        namesakes = sum(1 for c in new if c.facts.get("namesake_check") != "passed")
        msg = f"{plural(len(cands), 'paper')} found and sent to your Inbox"
        if namesakes:
            msg += f" ({namesakes} flagged as a possible namesake)"
        return "found", msg + ("; " + "; ".join(notes) if notes else "") + ".", resolved
    from areao1.jobs.sync import import_source

    reports = [import_source(ws, url) for url in targets]
    added = sum(r.candidates_added for r in reports)
    names = ", ".join(r.source_id for r in reports)
    if not added:
        return (
            "nothing_found",
            f"Read {names}, but found nothing to suggest yet. It's now a source, checked daily.",
            {},
        )
    return "found", f"Imported {names}: {plural(added, 'suggestion')} in your Inbox.", {}
