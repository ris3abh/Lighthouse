"""Letter drafts (I1): from approved claims only, each factual sentence citing its claims; guardrails; never signed or
sent as the writer; sent to them through outreach approval. Everything here is invented."""

from __future__ import annotations

import re
from datetime import date, timedelta

from agent_fakes import FakeEngine
from fastapi.testclient import TestClient

from areao1.core.models import ClaimDraft, Edge, Evidence
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}


def _claims(ws):
    payload = "\n".join(f"Judged Example Hacks round {i} in 2026." for i in range(4))
    drafts = [ClaimDraft(subject=f"event:example-hacks-{i}", subject_kind="event", subject_name=f"Example Hacks {i}",
                         predicate="judged_event", value=f"round {i}", excerpt=f"Judged Example Hacks round {i} in 2026.",
                         event_date=date(2026, 1, 1) + timedelta(days=i)) for i in range(4)]  # fmt: skip
    a, b, c, d = ws.memory.record(Evidence(connector="upload", source_url="upload:judging.txt", payload=payload,
                                           media_type="text/plain", claims=drafts))  # fmt: skip
    ws.memory.decide([a.id, b.id, d.id], "approved", rationale="ok")  # c stays pending
    ws.memory._append("edges", [Edge(type="CONTRADICTS", src=d.id, dst=c.id)])  # d conflicts: left out
    return a, b, c, d


def _writer(ws, name="Dr. Priya Natarajan"):
    return ws.add_letter(name=name, relationship="independent", credentials="Professor, Example University",
                         criteria=["judging"])  # fmt: skip


def test_without_ai_a_template_cites_only_approved_claims(ws):
    a, b, c, d = _claims(ws)
    lt = _writer(ws)
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        out = client.post(f"/api/letters/{lt.id}/draft", headers=W).json()
        text = client.get(f"/api/letters/{lt.id}/draft").json()["text"]
    assert out["by"] == "template" and set(out["cited"]) == {a.id, b.id}
    body = text.split("\n---\n")[0]
    cited = set(re.findall(r"clm_[0-9a-f]+", body))
    assert cited == {a.id, b.id} and c.id not in text.split("## Sources")[0] and d.id not in body
    assert "Area O1 never signs or sends it as them" in text and "[WRITER: signature, name, title]" in body
    assert (
        "Sincerely,\n[WRITER" in body and "Dr. Priya Natarajan\n" not in body.split("Sincerely,")[1]
    )  # never signed
    letter = ws.letters().letters[0]
    assert letter.draft_path == out["path"] and letter.status == "drafting"
    assert {e.dst for e in ws.memory.edges() if e.type == "CITES" and e.src == f"letter:{lt.id}"} == {
        a.id,
        b.id,
    }


def test_with_ai_ungrounded_sentences_and_verdicts_are_dropped(ws):
    a, b, _, _ = _claims(ws)
    lt = _writer(ws)
    reply = (f"Dear Officer,\n\nI have known Alex for years. [WRITER: how you met]\nAlex judged Example Hacks round 0. "
             f"[{a.id}] Alex judged round 1 with distinction. [{b.id}] Alex led a team of 40 engineers. [clm_ffffffffffff] "
             f"Alex clearly qualifies for the O-1A visa. [{a.id}]\n\nSincerely,\n[WRITER: signature, name, title]")  # fmt: skip
    engine = FakeEngine([("usage", {"input_tokens": 900, "output_tokens": 200}), ("text", reply)])
    with TestClient(create_app(ws, allowed_hosts=["testserver"], engine=engine)) as client:
        out = client.post(f"/api/letters/{lt.id}/draft", headers=W).json()
        text = client.get(f"/api/letters/{lt.id}/draft").json()["text"]
        runs = client.get("/api/agent/runs").json()
    body = text.split("\n---\n")[0]
    assert out["by"] == "gpt-6.1-sol" and "Alex judged Example Hacks round 0." in body
    assert "40 engineers" not in body  # cited a claim that isn't approved (or doesn't exist)
    assert "I have known Alex for years" not in body  # a fact with no citation
    assert "qualifies" not in body  # the eligibility guard
    assert len(out["dropped"]) >= 2 and "[WRITER: how you met]" in body
    assert engine.api.bodies[-1]["model"] == "gpt-6.1-sol" and "tools" not in engine.api.bodies[-1]
    assert any(r["task"] == "letter" and r["cost_usd"] for r in runs)  # its cost counts like any run


def test_the_draft_goes_to_the_writer_through_outreach_approval(ws):
    _claims(ws)
    lt = _writer(ws)
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        client.post(f"/api/letters/{lt.id}/draft", headers=W)
        r = client.post(f"/api/letters/{lt.id}/send", headers=W, json={})
        assert r.status_code == 400 and "Add Dr. Priya Natarajan as a contact" in r.json()["detail"]
        ws.add_contact(name="Dr. Priya Natarajan", emails=["priya@example.edu"], relationship="recommender")
        d = client.post(f"/api/letters/{lt.id}/send", headers=W, json={}).json()
    assert (d["status"], d["to"], d["drafted_by"]) == (
        "draft",
        "priya@example.edu",
        "letters",
    )  # waits for Approve
    assert "only sign it if it reads true to you" in d["body"] and "clm_" not in d["body"]
    assert d["body"].startswith("Hi Priya,") and "Dear Officer," in d["body"]
    assert "[WRITER: signature, name, title]" in d["body"]


def test_no_approved_claims_means_no_draft(ws):
    lt = _writer(ws)
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        r = client.post(f"/api/letters/{lt.id}/draft", headers=W)
    assert r.status_code == 400 and "approve some in the Inbox" in r.json()["detail"]
