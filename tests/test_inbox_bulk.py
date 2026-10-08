"""Inbox bulk review (F9): groups by origin, server-side filters, batch decisions through the same per-item door
(rules, rule check, logging), evidence only with confirmation, self-reported never evidence, and one Undo per batch.
Everything here is invented."""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient

from areao1.core.models import Candidate
from areao1.criteria import inbox_bulk
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}


def _chat(n: int, kind: str, **extra) -> list[Candidate]:
    out = []
    for i in range(n):
        common = dict(fingerprint=f"chatx:{kind}:{i}", source="chat:chatgpt", evidence_type="self_report",
                      proposed_criterion="", source_tier="self_reported", confidence=0.3,
                      title=f"{kind.capitalize()} {i}", summary=f'From your ChatGPT chat: "{kind} {i}"')  # fmt: skip
        if kind == "deadline":
            out.append(Candidate(kind="deadline", proposal={"title": f"Deadline {i}", "due": "2026-12-0" + str(1 + i % 8),
                                                            "kind": "other"}, **common))  # fmt: skip
        elif kind == "pipeline":
            out.append(Candidate(kind="pipeline", proposal={"title": f"Idea {i}", "stage": "idea"}, **common))
        else:
            out.append(Candidate(kind="context", proposal={"id": f"n{i}", "text": f"note {i}", "client": "ChatGPT export"},
                                 **common))  # fmt: skip
    return out


def _evidence(n: int, **extra) -> list[Candidate]:
    return [Candidate(fingerprint=f"web:{i}", source="website:hacks", evidence_type="panel_letter",
                      proposed_criterion="judging", title=f"Judges page {i}", summary="A page naming Maya.", **extra)
            for i in range(n)]  # fmt: skip


def _ws(ws):
    ws.add_candidates([*_chat(5, "deadline"), *_chat(3, "pipeline"), *_chat(12, "context"), *_evidence(2)])
    return TestClient(create_app(ws, allowed_hosts=["testserver"]))


def test_groups_by_origin_with_counts_by_kind(ws):
    c = _ws(ws)
    groups = {g["label"].split(",")[0]: g for g in c.get("/api/inbox/groups").json()}
    assert groups["ChatGPT export"]["count"] == 20
    assert groups["ChatGPT export"]["kinds"] == {"deadline": 5, "pipeline": 3, "context": 12}
    assert groups["website: hacks"]["count"] == 2


def test_a_filter_selects_on_the_server_and_refuses_if_the_inbox_changed(ws):
    c = _ws(ws)
    key = next(g["key"] for g in c.get("/api/inbox/groups").json() if g["label"].startswith("ChatGPT"))
    stale = c.post(
        "/api/inbox/bulk",
        headers=W,
        json={"action": "reject", "filter": {"group": key, "kind": "context"}, "expect": 11},
    )
    assert stale.status_code == 409 and "12 items match now" in stale.json()["detail"]
    r = c.post(
        "/api/inbox/bulk",
        headers=W,
        json={"action": "reject", "filter": {"group": key, "kind": "context"}, "expect": 12},
    ).json()
    assert len(r["done"]) == 12 and r["failed"] == [] and r["batch"]
    assert {ch.batch for ch in ws.changes() if ch.action == "inbox.reject"} == {
        r["batch"]
    }  # one batch, per-item changes
    assert len([ch for ch in ws.changes() if ch.action == "inbox.reject"]) == 12
    assert len(ws.pending_candidates()) == 10


def test_bulk_accept_adds_trackers_but_evidence_needs_confirmation(ws):
    c = _ws(ws)
    ids = [x.id for x in ws.pending_candidates() if x.kind in ("deadline", "evidence")]
    r = c.post("/api/inbox/bulk", headers=W, json={"action": "accept", "ids": ids}).json()
    assert len(r["done"]) == 5 and {f["why"] for f in r["failed"]} == {"evidence needs your confirmation"}
    assert len(ws.deadlines().deadlines) == 5 and ws.exhibits().exhibits == []
    ev = [x.id for x in ws.pending_candidates() if x.kind == "evidence"]
    r2 = c.post(
        "/api/inbox/bulk", headers=W, json={"action": "accept", "ids": ev, "confirm_evidence": True}
    ).json()
    assert len(r2["done"]) == 2 and len(ws.exhibits().exhibits) == 2


def test_the_same_rules_hold_per_item(ws):
    ws.add_candidates([Candidate(fingerprint="self:1", source="mcp:x", evidence_type="document", proposed_criterion="awards",
                                 title="I won an award", summary="Self-reported.", source_tier="self_reported")])  # fmt: skip
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    [cand] = ws.pending_candidates()
    r = c.post(
        "/api/inbox/bulk", headers=W, json={"action": "accept", "ids": [cand.id], "confirm_evidence": True}
    ).json()
    assert r["done"] == [] and "self-reported items can't become exhibits" in r["failed"][0]["why"]
    assert r["batch"] is None and ws.exhibits().exhibits == []


def test_one_undo_reverses_the_whole_batch(ws):
    c = _ws(ws)
    every = [x.id for x in ws.pending_candidates()]
    r = c.post(
        "/api/inbox/bulk", headers=W, json={"action": "accept", "ids": every, "confirm_evidence": True}
    ).json()
    assert len(r["done"]) == 22
    files = [e.file for e in ws.exhibits().exhibits]
    assert len(ws.deadlines().deadlines) == 5 and len(ws.pipeline().items) == 3 and len(files) == 2
    u = c.post(f"/api/inbox/batches/{r['batch']}/undo", headers=W).json()
    assert len(u["undone"]) == 22 and u["left"] == []
    assert len(ws.pending_candidates()) == 22  # all back, pending
    assert ws.deadlines().deadlines == [] and ws.pipeline().items == [] and ws.exhibits().exhibits == []
    assert not any((ws.root / f).exists() for f in files)
    again = c.post(f"/api/inbox/batches/{r['batch']}/undo", headers=W)
    assert again.status_code >= 400 and "already undone" in again.json()["detail"]


def test_undo_a_reject_and_a_snooze(ws):
    c = _ws(ws)
    notes = [x.id for x in ws.pending_candidates() if x.kind == "context"][:3]
    ideas = [x.id for x in ws.pending_candidates() if x.kind == "pipeline"]
    a = c.post("/api/inbox/bulk", headers=W, json={"action": "reject", "ids": notes}).json()
    b = c.post(
        "/api/inbox/bulk", headers=W, json={"action": "snooze", "ids": ideas, "until": "2027-01-01"}
    ).json()
    assert len(ws.pending_candidates()) == 22 - 3 - 3
    c.post(f"/api/inbox/batches/{b['batch']}/undo", headers=W)
    c.post(f"/api/inbox/batches/{a['batch']}/undo", headers=W)
    assert len(ws.pending_candidates()) == 22 and all(
        x.snoozed_until is None for x in ws.pending_candidates()
    )


def test_filters():
    from datetime import UTC, datetime

    c = Candidate(fingerprint="x", source="chat:claude", evidence_type="self_report", proposed_criterion="", kind="context",
                  title="Talked to Omar about judging", summary="s", created_at=datetime(2026, 10, 7, 12, tzinfo=UTC))  # fmt: skip
    assert inbox_bulk.group_of(c) == ("chat:claude@2026-10-07", "Claude export, Oct 7")
    assert inbox_bulk.matches(c, {"kind": "context", "text": "omar"}) and not inbox_bulk.matches(
        c, {"kind": "deadline"}
    )
    assert date(2026, 10, 7)  # the label's day is the person's local day


def test_undo_reopens_the_claims_an_acceptance_approved(ws):
    from areao1.core.models import ClaimDraft, Evidence

    payload = "Maya judged Example Hacks 2026."
    [claim] = ws.memory.record(Evidence(connector="website", source_url="https://hacks.example/judges", payload=payload,
                                        media_type="text/plain",
                                        claims=[ClaimDraft(subject="event:x", subject_kind="event", subject_name="Example Hacks",
                                                           predicate="judged_event", value="judge", excerpt=payload)]))  # fmt: skip
    ws.add_candidates([Candidate(fingerprint="web:c", source="website:hacks", evidence_type="panel_letter",
                                 proposed_criterion="judging", title="Judges page", summary="s", claim_ids=[claim.id])])  # fmt: skip
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    [cand] = ws.pending_candidates()
    r = c.post(
        "/api/inbox/bulk", headers=W, json={"action": "accept", "ids": [cand.id], "confirm_evidence": True}
    ).json()
    assert ws.memory.statuses()[claim.id] == "approved"
    c.post(f"/api/inbox/batches/{r['batch']}/undo", headers=W)
    assert ws.memory.statuses()[claim.id] == "proposed"  # waiting again; the decision history stays on record
    assert [d.decision for d in ws.memory.decisions() if d.claim_id == claim.id] == ["approved", "reopened"]
