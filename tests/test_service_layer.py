"""Every create / update / move on the Inbox, Pipeline, Letters, Calendar and Evidence pages goes through the
service layer (areao1/service.py). These tests fail if a page or route writes workspace files any
other way, or if a new write route appears without being covered here."""

from __future__ import annotations

import builtins
import io
import os
import pathlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from areao1.criteria.models import OutreachDraft
from areao1.server.app import create_app
from areao1.service import in_service

ROOT = Path(__file__).resolve().parent.parent
W = {"X-AreaO1": "1"}
PDF = b"%PDF-1.4 fictional\n"

# Routes the five pages write through. Every mutating route under these prefixes must be covered below.
PAGE_PREFIXES = ("/api/inbox", "/api/pipeline", "/api/letters", "/api/deadlines", "/api/exhibits", "/api/profile",
                 "/api/criteria", "/api/changes", "/api/settings/autopilot",
                 "/api/settings/missions", "/api/settings/agent", "/api/settings/mail", "/api/settings/opportunities", "/api/rulecheck/briefing", "/api/rulecheck/inbox", "/api/knowledge/findings",
                 "/api/onboarding", "/api/todos", "/api/contacts", "/api/outreach")  # fmt: skip
# Writes that aren't page edits: connector syncs, jobs, imports and notifications (system processes with their
# own audit trail in memory/ or the cache).
SYSTEM_ROUTES = {
    ("POST", "/api/sources"), ("POST", "/api/sources/{source_id:path}/sync"),
    ("PUT", "/api/sources/{source_id:path}/token"), ("DELETE", "/api/sources/{source_id:path}"),
    ("POST", "/api/metrics/snapshot"), ("POST", "/api/jobs/{name}/run"), ("POST", "/api/notify/test"),
    ("POST", "/api/imports/chats"), ("POST", "/api/imports/chats/scan"), ("POST", "/api/imports/chats/{scan_id}/import"),
    ("DELETE", "/api/imports/chats/{scan_id}"),
    # The Anthropic key lives in the OS keychain, never in the workspace (like source tokens).
    ("PUT", "/api/ai/key"), ("DELETE", "/api/ai/key"),
    # Gmail: the app password lives in the keychain; nothing in the workspace (ADR 0014).
    ("PUT", "/api/gmail"), ("DELETE", "/api/gmail"),
    # Gmail sync writes only data/threads.json (like a source sync); last-touch changes go through the service.
    ("POST", "/api/gmail/sync"),
    # The Mail view writes only data/mail.json, a read-only cache of case mail headers and the sorting rules you
    # teach by moving a message; nothing in the case changes (ADR 0014, Mail view amendment).
    ("POST", "/api/mail/sync"), ("PUT", "/api/mail/{gm_id}"),
    # The daily opportunity check proposes to the Inbox through the service layer (actor "opportunities").
    ("POST", "/api/opportunities/run"),
    # The capture extension (ADR 0011 §2): pairing state in the cache, captures into the vault cache like an import.
    ("POST", "/api/vault/capture/code"), ("DELETE", "/api/vault/capture"), ("POST", "/api/vault/capture/pair"),
    ("POST", "/api/vault/capture/page"),
    # Agent runs write their own records (agent/runs, agent/conversations); anything the agent changes in
    # the workspace goes through Service(actor="agent:<run>"), covered in tests/test_agent.py.
    ("POST", "/api/agent/chat"), ("POST", "/api/agent/runs"), ("POST", "/api/agent/runs/{run_id}/stop"),
    ("POST", "/api/agent/missions/{name}/run"), ("POST", "/api/rulecheck/runs/{run_id}"),
    # The vault's fetched content lives in the cache; its fetch log is append-only (like source syncs).
    ("POST", "/api/knowledge/sync"), ("POST", "/api/knowledge/import/{source_id}"),
}  # fmt: skip
# Onboarding lookups run connectors the person approved (like adding a source); their status is saved through
# the service layer (tests/test_onboarding.py checks it).
ONBOARDING_LOOKUP = ("POST", "/api/onboarding/lookups/{lookup_id}")
# Sending mail needs Google, so it has no sample here; the send is saved through the service layer and
# tests/test_outreach.py checks it.
OUTREACH_SEND = ("POST", "/api/outreach/{draft_id}/send")
# Undo send needs an approved email inside its window; tests/test_gmail_imap.py checks it goes through the service.
OUTREACH_UNDO = ("POST", "/api/outreach/{draft_id}/undo")
# Importing a forwarded original needs Gmail; it goes through Service.stage_upload (tests/test_eml.py checks it).
MAIL_IMPORT = ("POST", "/api/mail/{gm_id}/import")


@pytest.fixture
def writes(monkeypatch, demo_ws):
    """Record every file write inside the workspace and whether it happened inside a service call."""
    root = demo_ws.root
    log: list[tuple[str, bool]] = []

    def note(path) -> None:
        try:
            rel = Path(path).resolve().relative_to(root).as_posix()
        except (ValueError, TypeError, OSError):
            return
        if not rel.startswith(".areao1/cache"):
            log.append((rel, in_service()))

    real_replace, real_open = os.replace, builtins.open
    real_wb, real_wt = pathlib.Path.write_bytes, pathlib.Path.write_text

    def guarded_open(file, mode="r", *a, **kw):
        if isinstance(file, (str, os.PathLike)) and any(c in mode for c in "wax+"):
            note(file)
        return real_open(file, mode, *a, **kw)

    def replace(src, dst, *a, **kw):
        note(dst)
        return real_replace(src, dst, *a, **kw)

    def write_bytes(self, data):
        note(self)
        return real_wb(self, data)

    def write_text(self, data, *a, **kw):
        note(self)
        return real_wt(self, data, *a, **kw)

    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(builtins, "open", guarded_open)
    monkeypatch.setattr(io, "open", guarded_open)
    monkeypatch.setattr(pathlib.Path, "write_bytes", write_bytes)
    monkeypatch.setattr(pathlib.Path, "write_text", write_text)
    return log


def _ids(ws):
    cands = ws.pending_candidates()
    return {
        "evidence": next(c.id for c in cands if c.kind == "evidence" and c.evidence_type == "ml_model"),
        "tracker": next(c.id for c in cands if c.kind == "deadline"),
        "other": next(c.id for c in cands if c.kind == "evidence" and c.evidence_type == "dataset"),
        "exhibit": ws.exhibits().exhibits[0].id,
        "deadline": ws.deadlines().deadlines[0].id,
        "pipeline": ws.pipeline().items[0].id,
        "letter": ws.letters().letters[0].id,
        "undo": _undoable_change(ws),
        "briefing": _briefing(ws),
        "finding": _finding(ws),
        "onboarding": _onboarding(ws),
        "contact": (con := ws.add_contact(name="Dr. Sam Ortiz", emails=["sam@uni.example"])).id,
        "draft": ws.put_draft(
            OutreachDraft(contact_id=con.id, to="sam@uni.example", subject="Hi", body="Hello")
        ).id,
        "todo": _todo(ws),
    }


def _letter_claims(ws) -> None:
    """An approved claim in the first writer's criteria, so a letter can be drafted from it."""
    from datetime import date

    from areao1.core.models import ClaimDraft, Evidence

    lt = ws.letters().letters[0]
    crit = (lt.criteria or ["judging"])[0]
    pred = {"judging": "judged_event", "awards": "award_received", "press": "press_mention"}.get(
        crit, "judged_event"
    )
    [c] = ws.memory.record(Evidence(connector="upload", source_url="upload:letter-facts.txt", media_type="text/plain",
                                    payload="Served as a judge for Example Hacks 2026.",
                                    claims=[ClaimDraft(subject="event:example-hacks-2026", subject_kind="event",
                                                       subject_name="Example Hacks 2026", predicate=pred, value="judge",
                                                       excerpt="Served as a judge for Example Hacks 2026.",
                                                       event_date=date(2026, 2, 1))]))  # fmt: skip
    ws.memory.decide([c.id], "approved", rationale="test")
    ws.update_letter(lt.id, criteria=[crit])


def _letter_drafted(ws) -> None:
    """The first writer's draft exists and they're a contact with an email."""
    import anyio

    from areao1.criteria import letters

    lt = ws.letters().letters[0]
    anyio.run(letters.draft, ws, lt.id, None, "")
    ws.add_contact(name=lt.name, emails=["writer@uni.example"])


def _todo(ws) -> str:
    from datetime import date

    from areao1.criteria.models import Todo

    ws.add_todos([Todo(id="todo_test", title="Upload proof of HackSeattle 2025 judging", kind="judging",
                       item="Judge, HackSeattle 2025", criterion="judging", created=date(2026, 10, 6))])  # fmt: skip
    return "todo_test"


def _onboarding(ws) -> str:
    """Put onboarding at a question so the answer route has one to answer."""
    from areao1.onboarding.models import OnboardingState, ProfileField

    ws.save_onboarding(OnboardingState(status="in_progress", step="questions", reached="questions", target_profile="o1a", fields=[
        ProfileField(key="location", label="Based in", value="Pittsburgh, PA", quote="Pittsburgh, PA")]))  # fmt: skip
    return "location"


def _finding(ws) -> str:
    """An official page the agent read, so the promote route has a finding to promote."""
    from areao1.vault import Vault

    text = "Official guidance about petitions and evidence. " * 10
    return (
        Vault(ws)
        .add_finding("https://www.uscis.gov/newsroom/alerts/x", "USCIS alert", text, "run_x")
        .source_id
    )


def _briefing(ws) -> str:
    """Publish a briefing so the re-check route has one to check."""
    from datetime import UTC, datetime

    from areao1.core.models import Briefing
    from areao1.service import Service

    Service(ws, actor="agent:test").publish_briefing(Briefing(generated_at=datetime.now(UTC), changed=["x"]))
    return "overview"


def _undoable_change(ws) -> str:
    """Make one undoable change (a pipeline move) so the undo route has something to revert."""
    from areao1.service import Service

    item = ws.pipeline().items[-1]
    Service(ws).update_pipeline_item(item.id, stage="done" if item.stage != "done" else "idea")
    return ws.changes()[-1].id


# (method, route template) -> (concrete path, request kwargs, expected change action)
SAMPLES = {
    ("PATCH", "/api/inbox/{candidate_id}"): ("/api/inbox/{other}", {"json": {"summary": "edited"}}, "inbox.edit"),
    ("POST", "/api/inbox/{candidate_id}/accept"): ("/api/inbox/{evidence}/accept", {"json": {}}, "inbox.accept"),
    ("POST", "/api/inbox/{candidate_id}/reject"): ("/api/inbox/{other}/reject", {}, "inbox.reject"),
    ("POST", "/api/inbox/{candidate_id}/snooze"): ("/api/inbox/{other}/snooze", {"json": {}}, "inbox.snooze"),
    ("POST", "/api/inbox/upload"): ("/api/inbox/upload", {"files": [("files", ("x.pdf", PDF, "application/pdf"))]},
                                    "inbox.upload"),
    ("POST", "/api/exhibits/upload"): ("/api/exhibits/upload", {
        "files": {"file": ("a.pdf", PDF, "application/pdf")},
        "data": {"criterion": "press", "evidence_type": "press_article", "title": "Profile", "date": "2026-10-01"},
    }, "evidence.upload"),
    ("PATCH", "/api/exhibits/{exhibit_id}"): ("/api/exhibits/{exhibit}", {"json": {"criterion": "press"}},
                                              "evidence.remap"),
    ("PUT", "/api/profile"): ("/api/profile", {"json": {"id": "eb1a"}}, "profile.set"),
    ("PUT", "/api/criteria/{criterion_id}/override"): ("/api/criteria/press/override", {"json": {"status": "gap"}},
                                                       "criterion.override"),
    ("POST", "/api/deadlines"): ("/api/deadlines", {"json": {"title": "New", "due": "2026-12-01"}}, "deadline.add"),
    ("PATCH", "/api/deadlines/{deadline_id}"): ("/api/deadlines/{deadline}", {"json": {"title": "Renamed"}},
                                                "deadline.update"),
    ("DELETE", "/api/deadlines/{deadline_id}"): ("/api/deadlines/{deadline}", {}, "deadline.delete"),
    ("POST", "/api/pipeline"): ("/api/pipeline", {"json": {"title": "Idea"}}, "pipeline.add"),
    ("PATCH", "/api/pipeline/{item_id}"): ("/api/pipeline/{pipeline}", {"json": {"stage": "done"}}, "pipeline.move"),
    ("DELETE", "/api/pipeline/{item_id}"): ("/api/pipeline/{pipeline}", {}, "pipeline.delete"),
    ("POST", "/api/letters"): ("/api/letters", {"json": {"name": "Dr. A", "relationship": "independent"}},
                               "letter.add"),
    ("PATCH", "/api/letters/{letter_id}"): ("/api/letters/{letter}", {"json": {"status": "sent"}}, "letter.update"),
    ("DELETE", "/api/letters/{letter_id}"): ("/api/letters/{letter}", {}, "letter.delete"),
    ("POST", "/api/letters/{letter_id}/draft"): ("/api/letters/{letter}/draft", {}, "letter.draft", "_letter_claims"),
    ("POST", "/api/letters/{letter_id}/send"): ("/api/letters/{letter}/send", {"json": {}}, "outreach.draft",
                                                "_letter_claims", "_letter_drafted"),
    ("PUT", "/api/settings/autopilot"): ("/api/settings/autopilot", {"json": {"metrics": True}}, "settings.autopilot"),
    ("POST", "/api/knowledge/findings/{source_id}/promote"): ("/api/knowledge/findings/{finding}/promote",
                                                             {"json": {"kind": "guidance"}}, "vault.promote"),
    ("POST", "/api/rulecheck/briefing"): ("/api/rulecheck/briefing", {}, "briefing.recheck"),
    ("POST", "/api/rulecheck/inbox/{candidate_id}"): ("/api/rulecheck/inbox/{other}", {}, "inbox.recheck"),
    ("PUT", "/api/settings/missions"): ("/api/settings/missions", {"json": {"what_changed": True}}, "settings.missions"),
    ("POST", "/api/changes/{change_id}/undo"): ("/api/changes/{undo}/undo", {}, "pipeline_item.undo"),
    ("POST", "/api/onboarding/linkedin"): ("/api/onboarding/linkedin", {"files": {"file": (
        "linkedin.pdf", (Path(__file__).parent / "fixtures" / "personas" / "maya" / "linkedin.pdf").read_bytes(),
        "application/pdf")}}, "onboarding.linkedin"),
    ("POST", "/api/onboarding/answer"): ("/api/onboarding/answer", {"json": {"id": "{onboarding}", "action": "yes"}},
                                        "onboarding.answer"),
    ("POST", "/api/onboarding/step"): ("/api/onboarding/step", {"json": {"step": "skip_all"}}, "onboarding.step"),
    ("POST", "/api/onboarding/restart"): ("/api/onboarding/restart", {}, "onboarding.restart"),
    ("POST", "/api/onboarding/goto"): ("/api/onboarding/goto", {"json": {"step": "questions"}}, "onboarding.goto"),
    ("PATCH", "/api/todos/{todo_id}"): ("/api/todos/{todo}", {"json": {"status": "done"}}, "todo.update"),
    ("PUT", "/api/settings/agent"): ("/api/settings/agent", {"json": {"cheap_mode": True}}, "settings.agent"),
    ("PUT", "/api/settings/mail"): ("/api/settings/mail", {"json": {"model_sorting": True}}, "settings.mail"),
    ("PUT", "/api/settings/opportunities"): ("/api/settings/opportunities", {"json": {"enabled": True}}, "settings.opportunities"),
    ("POST", "/api/outreach"): ("/api/outreach", {"json": {"contact_id": "{contact}", "subject": "Thank you",
                                                         "body": "Thanks for judging with me."}}, "outreach.draft"),
    ("PATCH", "/api/outreach/{draft_id}"): ("/api/outreach/{draft}", {"json": {"body": "Thank you again."}}, "outreach.edit"),
    ("POST", "/api/outreach/{draft_id}/reject"): ("/api/outreach/{draft}/reject", {}, "outreach.reject"),
    ("POST", "/api/contacts"): ("/api/contacts", {"json": {"name": "Prof. Lee"}}, "contact.add"),
    ("PATCH", "/api/contacts/{contact_id}"): ("/api/contacts/{contact}", {"json": {"notes": "Met at ICML"}}, "contact.update"),
    ("DELETE", "/api/contacts/{contact_id}"): ("/api/contacts/{contact}", {}, "contact.delete"),
    ("POST", "/api/onboarding/ai"): ("/api/onboarding/ai", {"json": {"choice": "skip"}}, "onboarding.ai", "_at_ai"),
}  # fmt: skip


def _at_ai(ws) -> None:
    """Put onboarding at Connect your AI."""
    from areao1.onboarding.models import OnboardingState

    ws.save_onboarding(OnboardingState(status="in_progress", step="ai", reached="ai"))


def _mutating_routes(app) -> set[tuple[str, str]]:
    out = set()
    for route in app.routes:
        for method in getattr(route, "methods", None) or ():
            if method in ("POST", "PUT", "PATCH", "DELETE"):
                out.add((method, route.path))
    return out


def test_every_page_write_route_is_covered(demo_ws):
    routes = _mutating_routes(create_app(demo_ws, allowed_hosts=["testserver"]))
    page_routes = {r for r in routes if r[1].startswith(PAGE_PREFIXES)} - {
        ONBOARDING_LOOKUP,
        OUTREACH_SEND,
        OUTREACH_UNDO,
    }
    assert page_routes == set(SAMPLES), (
        "a write route was added or removed: cover it in SAMPLES (and route it through the service layer)"
    )
    unknown = (
        routes - page_routes - SYSTEM_ROUTES - {ONBOARDING_LOOKUP, OUTREACH_SEND, OUTREACH_UNDO, MAIL_IMPORT}
    )
    assert not unknown, f"unclassified write routes: {sorted(unknown)}"


@pytest.mark.parametrize("route", sorted(SAMPLES), ids=lambda r: f"{r[0]} {r[1]}")
def test_page_writes_only_happen_inside_the_service_layer(route, demo_ws, writes):
    client = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    path, kwargs, action, *setup = SAMPLES[route]
    ids = _ids(demo_ws)
    for name in setup:  # a route that needs a particular state first
        globals()[name](demo_ws)
    path = path.format(**ids)
    if "json" in kwargs:  # ids in the body too ({contact}, {onboarding})
        body = {
            k: v.format(**ids) if isinstance(v, str) and "{" in v else v for k, v in kwargs["json"].items()
        }
        kwargs = {**kwargs, "json": body}
    before = len(demo_ws.changes())
    writes.clear()
    resp = client.request(route[0], path, headers=W, **kwargs)
    assert resp.status_code < 400, resp.text
    assert writes, f"{route} wrote nothing"
    outside = sorted({rel for rel, inside in writes if not inside})
    assert not outside, f"{route} wrote {outside} outside the service layer"
    new = demo_ws.changes()[before:]
    assert [c.action for c in new] == [action] and new[0].actor == "user"


def test_the_guard_catches_a_bypass(demo_ws, writes):
    """Negative control: a write that skips the service layer is detected."""
    demo_ws.add_deadline(title="sneaky", due="2026-12-01")
    assert any(rel == "data/deadlines.json" and not inside for rel, inside in writes)


def test_changes_record_before_and_after_for_undo(demo_ws):
    client = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    item = demo_ws.pipeline().items[0]
    client.patch(f"/api/pipeline/{item.id}", json={"stage": "done"}, headers=W)
    change = demo_ws.changes()[-1]
    assert change.action == "pipeline.move" and change.target_id == item.id
    assert change.before["stage"] == item.stage and change.after["stage"] == "done"
    assert (demo_ws.root / "data" / "changes.jsonl").exists()


# ----------------------------------------------------------------------------- the frontend side


def _web_sources() -> dict[str, str]:
    return {p.relative_to(ROOT).as_posix(): p.read_text() for p in (ROOT / "web" / "src").rglob("*.ts*")}


def test_pages_only_write_through_the_api_client():
    """Writes need the X-AreaO1 header and a non-GET method; only web/src/api.ts may do either."""
    for name, text in _web_sources().items():
        if name == "web/src/api.ts":
            continue
        assert "X-AreaO1" not in text, f"{name} sends the write header itself; use api.ts"
        assert not re.search(r"method\s*:", text), f"{name} makes a non-GET request itself; use api.ts"


def test_api_client_writes_map_to_known_routes(demo_ws):
    """Every mutating call in api.ts hits either a service-layer page route or a known system route."""
    api_ts = _web_sources()["web/src/api.ts"]
    calls = re.findall(r'request<[^>]*>\(\s*"(POST|PUT|PATCH|DELETE)",\s*[`"]([^`"]+)[`"]', api_ts, re.S)
    assert calls
    known = set(SAMPLES) | SYSTEM_ROUTES | {ONBOARDING_LOOKUP, OUTREACH_SEND, OUTREACH_UNDO, MAIL_IMPORT}

    def matches(method: str, path: str) -> bool:
        concrete = "/api" + re.sub(r"\$\{[^}]+\}", "X", path)
        for m, template in known:
            pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+(?:/[^/]+)*?", template) + "$"
            if m == method and re.match(pattern, concrete):
                return True
        return False

    unmatched = [(m, p) for m, p in calls if not matches(m, p)]
    assert not unmatched, f"api.ts writes to routes the service-layer test doesn't know: {unmatched}"
