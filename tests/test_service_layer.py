"""Every create / update / move on the Inbox, Pipeline, Letters, Calendar and Evidence pages goes through the
service layer (lighthouse_gc/service.py). These tests fail if a page or route writes workspace files any
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

from lighthouse_gc.server.app import create_app
from lighthouse_gc.service import in_service

ROOT = Path(__file__).resolve().parent.parent
W = {"X-Lighthouse": "1"}
PDF = b"%PDF-1.4 fictional\n"

# Routes the five pages write through. Every mutating route under these prefixes must be covered below.
PAGE_PREFIXES = ("/api/inbox", "/api/pipeline", "/api/letters", "/api/deadlines", "/api/exhibits", "/api/profile",
                 "/api/criteria")  # fmt: skip
# Writes that aren't page edits: connector syncs, jobs, imports and notifications (system processes with their
# own audit trail in memory/ or the cache).
SYSTEM_ROUTES = {
    ("POST", "/api/sources"), ("POST", "/api/sources/{source_id:path}/sync"),
    ("PUT", "/api/sources/{source_id:path}/token"), ("DELETE", "/api/sources/{source_id:path}"),
    ("POST", "/api/metrics/snapshot"), ("POST", "/api/jobs/{name}/run"), ("POST", "/api/notify/test"),
    ("POST", "/api/imports/chats"),
    # Agent runs write their own records (agent/runs, agent/conversations); anything the agent changes in
    # the workspace goes through Service(actor="agent:<run>"), covered in tests/test_agent.py.
    ("POST", "/api/agent/chat"), ("POST", "/api/agent/runs"), ("POST", "/api/agent/runs/{run_id}/stop"),
}  # fmt: skip


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
        if not rel.startswith(".lighthouse/cache"):
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
    }


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
}  # fmt: skip


def _mutating_routes(app) -> set[tuple[str, str]]:
    out = set()
    for route in app.routes:
        for method in getattr(route, "methods", None) or ():
            if method in ("POST", "PUT", "PATCH", "DELETE"):
                out.add((method, route.path))
    return out


def test_every_page_write_route_is_covered(demo_ws):
    routes = _mutating_routes(create_app(demo_ws, allowed_hosts=["testserver"]))
    page_routes = {r for r in routes if r[1].startswith(PAGE_PREFIXES)}
    assert page_routes == set(SAMPLES), (
        "a write route was added or removed: cover it in SAMPLES (and route it through the service layer)"
    )
    unknown = routes - page_routes - SYSTEM_ROUTES
    assert not unknown, f"unclassified write routes: {sorted(unknown)}"


@pytest.mark.parametrize("route", sorted(SAMPLES), ids=lambda r: f"{r[0]} {r[1]}")
def test_page_writes_only_happen_inside_the_service_layer(route, demo_ws, writes):
    client = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    path, kwargs, action = SAMPLES[route]
    path = path.format(**_ids(demo_ws))
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
    """Writes need the X-Lighthouse header and a non-GET method; only web/src/api.ts may do either."""
    for name, text in _web_sources().items():
        if name == "web/src/api.ts":
            continue
        assert "X-Lighthouse" not in text, f"{name} sends the write header itself; use api.ts"
        assert not re.search(r"method\s*:", text), f"{name} makes a non-GET request itself; use api.ts"


def test_api_client_writes_map_to_known_routes(demo_ws):
    """Every mutating call in api.ts hits either a service-layer page route or a known system route."""
    api_ts = _web_sources()["web/src/api.ts"]
    calls = re.findall(r'request<[^>]*>\(\s*"(POST|PUT|PATCH|DELETE)",\s*[`"]([^`"]+)[`"]', api_ts, re.S)
    assert calls
    known = set(SAMPLES) | SYSTEM_ROUTES

    def matches(method: str, path: str) -> bool:
        concrete = "/api" + re.sub(r"\$\{[^}]+\}", "X", path)
        for m, template in known:
            pattern = "^" + re.sub(r"\{[^}]+\}", "[^/]+(?:/[^/]+)*?", template) + "$"
            if m == method and re.match(pattern, concrete):
                return True
        return False

    unmatched = [(m, p) for m, p in calls if not matches(m, p)]
    assert not unmatched, f"api.ts writes to routes the service-layer test doesn't know: {unmatched}"
