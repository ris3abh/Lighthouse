"""Gmail over IMAP and SMTP with an app password (ADR 0014, amendment): every rule from §2 and §5 still holds.
Reading opens All Mail read-only, searches only your contacts' addresses and fetches headers only; sending happens
only from Approve & send, within the daily limit, to an address still on the contact. Gmail is the fake in
mail_fakes.py; nothing leaves."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from mail_fakes import FakeGmail

from areao1.criteria.models import GmailThread, GmailThreads
from areao1.google import gmail, mail, outreach
from areao1.server.app import create_app
from areao1.service import Service

W = {"X-AreaO1": "1"}
OCT3, OCT5 = "03-Oct-2026 09:00:00 +0000", "05-Oct-2026 16:30:00 +0000"


@pytest.fixture
def fake(monkeypatch):
    g = FakeGmail().install(monkeypatch)
    mail.connect(g.email, g.password)
    g.commands.clear()
    return g


@pytest.fixture
def people(ws):
    omar = ws.add_contact(name="Omar Haddad", emails=["omar@mlh.example"], last_touch=date(2026, 9, 1))
    priya = ws.add_contact(name="Dr. Priya Natarajan", emails=["priya@lakeshore.example"])
    return omar, priya


def test_reads_only_headers_of_threads_with_contacts(ws, people, fake):
    omar, priya = people
    fake.add(0x18A1, OCT3, "Alex <alex@gmail.com>", "Omar <omar@mlh.example>", "HackSeattle judging",
             message_id="<a1@mail.gmail.com>")  # fmt: skip
    fake.add(0x18A1, OCT5, "Omar Haddad <omar@mlh.example>", "alex@gmail.com", "Re: HackSeattle judging",
             message_id="<o2@mlh.example>")  # fmt: skip
    fake.add(0x18B2, OCT3, "alex@gmail.com", "priya@lakeshore.example", "Letter draft")
    fake.add(
        0x18C3, OCT5, "newsletter@shop.example", "alex@gmail.com", "Sale"
    )  # not a contact: never fetched

    assert gmail.sync(ws) == ["Gmail: 2 threads with your contacts; last touch updated for 2"]
    by_id = {t.id: t for t in ws.threads().threads}
    t = by_id["18a1"]  # Gmail's thread ID, the same one its API uses
    assert (t.subject, t.contact_ids, t.last_from, t.messages) == (
        "HackSeattle judging",
        [omar.id],
        "them",
        2,
    )
    assert t.last_at == datetime(2026, 10, 5, 16, 30, tzinfo=UTC) and t.last_message_id == "<o2@mlh.example>"
    assert t.snippet == ""  # headers only: no snippet without reading the body
    assert by_id["18b2"].last_from == "you" and by_id["18b2"].contact_ids == [priya.id]

    kinds = [c[0] if c[0] != "UID" else c[1] for c in fake.commands]
    assert kinds[:3] == ["LOGIN", "LIST", "SELECT"] and set(kinds[3:]) == {"SEARCH", "FETCH"}
    assert (
        "SELECT",
        '"[Gmail]/Alle Nachrichten"',
        True,
    ) in fake.commands  # All Mail, found by \All, read-only
    searches = [c[3] for c in fake.commands if c[:2] == ("UID", "SEARCH")]
    assert searches == ['"from:omar@mlh.example OR to:omar@mlh.example OR cc:omar@mlh.example newer_than:365d"',
                        '"from:priya@lakeshore.example OR to:priya@lakeshore.example OR cc:priya@lakeshore.example '
                        'newer_than:365d"']  # fmt: skip
    [fetch] = [c for c in fake.commands if c[:2] == ("UID", "FETCH")]
    assert fetch[2] == "1,2,3" and "BODY.PEEK[HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID)]" in fetch[3]
    assert "body must never" not in ws.root.joinpath("data", "threads.json").read_text()
    assert {c.id: c.last_touch for c in ws.contacts().contacts}[omar.id] == date(2026, 10, 5)


def test_nothing_without_a_connection(ws, people):
    assert "isn't connected" in gmail.sync(ws)[0]  # the conftest guard would fail any IMAP connection


def _app(ws):
    return TestClient(create_app(ws, allowed_hosts=["testserver"]))


def _draft(c, contact_id, subject="MLH judging"):
    r = c.post("/api/outreach", headers=W, json={"contact_id": contact_id, "subject": subject,
                                                  "body": "Could you confirm my judging at MLH Fall in writing?"})  # fmt: skip
    assert r.status_code == 200, r.text
    return r.json()


def test_approve_and_send_goes_over_smtp_from_your_gmail(ws, people, fake):
    omar, _ = people
    c = _app(ws)
    assert c.get("/api/outreach").json()["can_send"] is True
    d = _draft(c, omar.id)
    assert not fake.sent  # a draft never sends itself
    out = c.post(f"/api/outreach/{d['id']}/send", headers=W).json()
    [msg] = fake.sent
    assert (msg["From"], msg["To"], msg["Subject"]) == ("alex@gmail.com", "omar@mlh.example", "MLH judging")
    assert out["status"] == "sent" and out["gmail_id"] == msg["Message-ID"]
    assert fake.smtp_logins == [("alex@gmail.com", "abcdefghijklmnop")]
    assert ws.changes()[-1].action == "outreach.send" and ws.changes()[-1].actor == "user"
    with pytest.raises(Exception, match="only you"):
        Service(ws, actor="agent:run_x").send_draft(_draft(c, omar.id)["id"])
    assert len(fake.sent) == 1


def test_the_daily_limit_and_case_contacts_only(ws, people, fake):
    omar, _ = people
    cfg = ws.config()
    cfg.outreach.daily_limit = 1
    ws.save_config(cfg)
    c = _app(ws)
    d1, d2, d3 = _draft(c, omar.id), _draft(c, omar.id), _draft(c, omar.id)
    Service(ws).update_contact(omar.id, emails=["omar@new.example"])
    r = c.post(f"/api/outreach/{d1['id']}/send", headers=W)
    assert r.status_code >= 400 and "case contacts only" in r.json()["detail"] and not fake.sent
    Service(ws).update_contact(omar.id, emails=["omar@mlh.example"])
    assert c.post(f"/api/outreach/{d2['id']}/send", headers=W).status_code == 200
    r = c.post(f"/api/outreach/{d3['id']}/send", headers=W)
    assert r.status_code >= 400 and "limit of 1" in r.json()["detail"] and len(fake.sent) == 1


def test_a_follow_up_is_a_draft_that_replies_in_the_thread(ws, people, fake):
    from areao1.jobs import JOBS

    quiet = (datetime.now(UTC) - timedelta(days=8)).strftime("%d-%b-%Y %H:%M:%S +0000")
    fake.add(
        0x18A1, quiet, "alex@gmail.com", "omar@mlh.example", "MLH judging", message_id="<a1@mail.gmail.com>"
    )
    fake.bodies_ok = True  # the job also sorts mail for the Mail view, which peeks at first lines
    lines = JOBS["google"][1](ws, True)  # reads the thread, then drafts the follow-up
    assert any("waiting for your approval" in line for line in lines)
    [d] = ws.outreach().drafts
    assert d.status == "draft" and d.thread_id == "18a1" and not fake.sent  # never sent on its own
    Service(ws).send_draft(d.id)  # your approval: it replies in the thread
    assert fake.sent[0]["In-Reply-To"] == "<a1@mail.gmail.com>"
    JOBS["google"][1](ws, True)
    assert len(ws.outreach().drafts) == 1  # once per thread


def test_a_send_that_gmail_refuses_stays_a_draft(ws, people, fake):
    omar, _ = people
    c = _app(ws)
    d = _draft(c, omar.id)
    fake.password = "zzzzzzzzzzzzzzzz"  # the app password was revoked at Google
    r = c.post(f"/api/outreach/{d['id']}/send", headers=W)
    assert r.status_code >= 400 and "still a draft" in r.json()["detail"]
    assert "didn't accept that app password" in r.json()["detail"]
    assert ws.outreach().drafts[0].status == "draft" and not fake.sent


def test_a_reply_carries_in_reply_to(ws, people, fake):
    omar, _ = people
    ws.save_threads(GmailThreads(threads=[GmailThread(id="18a1", subject="MLH judging", contact_ids=[omar.id],
                                                      last_at=datetime.now(UTC), last_from="them",
                                                      last_message_id="<o2@mlh.example>")]))  # fmt: skip
    d = outreach.compose(ws, omar.id, "Re: MLH judging", "Thank you!", thread_id="18a1")
    Service(ws).save_draft(d)
    Service(ws).send_draft(d.id)
    [msg] = fake.sent
    assert msg["In-Reply-To"] == "<o2@mlh.example>" and msg["References"] == "<o2@mlh.example>"


def test_approving_twice_while_gmail_is_slow_sends_once(ws, people, fake, monkeypatch):
    """The live test: four clicks on Approve & send during a slow SMTP send went out four times."""
    import threading
    import time

    omar, _ = people
    c = _app(ws)
    d = _draft(c, omar.id)
    slow = mail.SMTP

    class Slow(slow):
        def send_message(self, msg):
            time.sleep(0.2)
            return super().send_message(msg)

    monkeypatch.setattr(mail, "SMTP", Slow)
    codes: list[int] = []
    clicks = [threading.Thread(target=lambda: codes.append(c.post(f"/api/outreach/{d['id']}/send", headers=W)
                                                           .status_code)) for _ in range(4)]  # fmt: skip
    for t in clicks:
        t.start()
    for t in clicks:
        t.join()
    assert len(fake.sent) == 1 and sorted(codes) == [200, 400, 400, 400]
    assert [ch.action for ch in ws.changes()].count("outreach.send") == 1
    assert c.get("/api/outreach").json()["sent_today"] == 1


def test_every_send_attempt_is_logged_and_the_limit_counts_actual_sends(ws, people, fake):
    from areao1.criteria.models import SendAttempt

    omar, _ = people
    c = _app(ws)
    d1, d2 = _draft(c, omar.id), _draft(c, omar.id)
    fake.password = "zzzzzzzzzzzzzzzz"  # Gmail refuses
    assert c.post(f"/api/outreach/{d1['id']}/send", headers=W).status_code == 400
    [fail] = ws.outreach().attempts
    assert (fail.ok, fail.to, fail.draft_id) == (False, "omar@mlh.example", d1["id"]) and fail.at is not None
    assert "didn't accept that app password" in fail.error
    view = c.get("/api/outreach").json()
    assert view["sent_today"] == 0 and view["failures"][0]["contact"] == "Omar Haddad"
    assert view["failures"][0]["error"] == fail.error
    fake.password = "abcdefghijklmnop"
    assert c.post(f"/api/outreach/{d1['id']}/send", headers=W).status_code == 200
    view = c.get("/api/outreach").json()
    assert view["sent_today"] == 1 and view["failures"] == []  # it went out on the retry
    assert [a.ok for a in ws.outreach().attempts] == [False, True]
    assert ws.outreach().attempts[-1].message_id == fake.sent[0]["Message-ID"]
    ws.log_attempt(
        SendAttempt(draft_id=d1["id"], to="omar@mlh.example", ok=True)
    )  # a duplicate that went out
    assert outreach.sent_today(ws) == 2  # counted: sends, not drafts
    cfg = ws.config()
    cfg.outreach.daily_limit = 2
    ws.save_config(cfg)
    r = c.post(f"/api/outreach/{d2['id']}/send", headers=W)
    assert "limit of 2" in r.json()["detail"] and ws.outreach().attempts[-1].error.startswith("today's limit")
