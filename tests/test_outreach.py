"""Outreach (E5, ADR 0014 §5): drafts never send themselves; only your approval sends one, from your Gmail, to a
case contact, within the daily limit; follow-ups after quiet days are drafts too. Gmail is mocked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from agent_fakes import FakeEngine
from fastapi.testclient import TestClient
from mail_fakes import FakeGmail

from areao1.criteria.models import GmailThread, GmailThreads
from areao1.google import mail, outreach
from areao1.server.app import create_app
from areao1.service import Service

W = {"X-AreaO1": "1"}


@pytest.fixture
def gm(monkeypatch):
    g = FakeGmail(email="alex@example.com").install(monkeypatch)
    mail.connect(g.email, g.password)
    return g


@pytest.fixture
def omar(ws):
    return ws.add_contact(name="Omar Haddad", emails=["omar@mlh.example"], relationship="organizer")


def _draft(c, contact_id, body="Could you confirm my judging at MLH Fall in writing?"):
    r = c.post(
        "/api/outreach", headers=W, json={"contact_id": contact_id, "subject": "MLH judging", "body": body}
    )
    assert r.status_code == 200, r.text
    return r.json()


def test_the_agent_drafts_and_nothing_is_sent(ws, omar, gm):
    script = [("tool", "draft_email", {"contact_id": omar.id, "subject": "Thank you", "purpose": "thank_you",
                                       "body": "Thanks for having me as a judge at MLH Fall."}), ("text", "Drafted.")]  # fmt: skip
    engine = FakeEngine(script)
    with TestClient(create_app(ws, allowed_hosts=["testserver"], engine=engine)) as c:
        run_id = c.post("/api/agent/chat", headers=W, json={"message": "Draft a thank-you to Omar"}).json()[
            "run_id"
        ]
        for _ in range(200):
            if c.get(f"/api/agent/runs/{run_id}").json()["status"] != "running":
                break
    [d] = ws.outreach().drafts
    assert d.status == "draft" and d.to == "omar@mlh.example" and d.drafted_by.startswith("agent:")
    assert not gm.sent
    assert not [t for t in engine.tool_names if "send" in t]  # no tool can send


def test_your_approval_sends_it_from_your_gmail(ws, omar, gm):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    d = _draft(c, omar.id)
    out = c.post(f"/api/outreach/{d['id']}/send", headers=W).json()
    [msg] = gm.sent
    assert out["status"] == "sent" and out["gmail_id"] == msg["Message-ID"]
    assert (
        msg["To"] == "omar@mlh.example"
        and msg["Subject"] == "MLH judging"
        and msg["From"] == "alex@example.com"
    )
    change = ws.changes()[-1]
    assert change.action == "outreach.send" and change.actor == "user"
    assert (
        c.patch(f"/api/outreach/{d['id']}", headers=W, json={"body": "x"}).status_code >= 400
    )  # sent: final


def test_case_contacts_only(ws, omar, gm):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    r = c.post(
        "/api/outreach", headers=W, json={"contact_id": "con_nobody", "subject": "Hi", "body": "Hello"}
    )
    assert r.status_code >= 400 and "case contacts only" in r.json()["detail"]
    d = _draft(c, omar.id)
    Service(ws).update_contact(omar.id, emails=["omar@new.example"])  # the address changed after drafting
    r = c.post(f"/api/outreach/{d['id']}/send", headers=W)
    assert r.status_code >= 400 and "case contacts only" in r.json()["detail"] and not gm.sent


def test_the_daily_limit_and_the_send_permission(ws, omar, monkeypatch):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    d1, d2 = _draft(c, omar.id), _draft(c, omar.id)
    gm = FakeGmail().install(monkeypatch)  # Gmail not connected yet
    r = c.post(f"/api/outreach/{d1['id']}/send", headers=W)
    assert r.status_code >= 400 and "connect Gmail" in r.json()["detail"] and not gm.sent
    mail.connect(gm.email, gm.password)
    cfg = ws.config()
    cfg.outreach.daily_limit = 1
    ws.save_config(cfg)
    assert c.post(f"/api/outreach/{d1['id']}/send", headers=W).status_code == 200
    r = c.post(f"/api/outreach/{d2['id']}/send", headers=W)
    assert r.status_code >= 400 and "limit of 1" in r.json()["detail"] and len(gm.sent) == 1


def test_edit_and_reject_are_yours_and_agents_cant_send(ws, omar):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    d = _draft(c, omar.id, body="You are definitely eligible to vouch. Please confirm my judging.")
    assert "definitely eligible" not in d["body"]  # the same guardrails as everything written in your name
    assert (
        c.patch(f"/api/outreach/{d['id']}", headers=W, json={"body": "Please confirm my judging."}).json()[
            "body"
        ]
        == "Please confirm my judging."
    )
    with pytest.raises(Exception, match="only you"):
        Service(ws, actor="agent:run_x").send_draft(d["id"])
    assert c.post(f"/api/outreach/{d['id']}/reject", headers=W).json()["status"] == "rejected"


def test_follow_ups_after_quiet_days_are_drafts_once(ws, omar):
    priya = ws.add_contact(name="Dr. Priya Natarajan", emails=["priya@lakeshore.example"])
    now = datetime.now(UTC)
    ws.save_threads(GmailThreads(threads=[
        GmailThread(id="t_quiet", subject="MLH judging", contact_ids=[omar.id], last_at=now - timedelta(days=8), last_from="you"),
        GmailThread(id="t_recent", subject="Letter", contact_ids=[priya.id], last_at=now - timedelta(days=3), last_from="you"),
        GmailThread(id="t_replied", subject="Re: hello", contact_ids=[priya.id], last_at=now - timedelta(days=20), last_from="them"),
    ]))  # fmt: skip
    from areao1.jobs import JOBS

    # Gmail not connected: the job only drafts from threads already here, and can't send anything
    lines = JOBS["google"][1](ws, True)
    [d] = ws.outreach().drafts
    assert (
        d.thread_id == "t_quiet" and d.drafted_by == "follow-up" and d.status == "draft" and "Omar" in d.body
    )
    assert any("waiting for your approval" in line for line in lines)
    JOBS["google"][1](ws, True)
    assert len(ws.outreach().drafts) == 1  # once per thread


def test_the_follow_up_has_one_line_per_paragraph():
    """Mail clients wrap paragraphs themselves; a hard break mid-sentence reads oddly."""
    for para in outreach.FOLLOW_UP.split("\n\n"):
        assert "\n" not in para or para.startswith("Thank you"), para
