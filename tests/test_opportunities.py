"""The daily opportunity job (ADR 0016): opportunity mail becomes Inbox items with a stage and a verification. Gmail
is the fake in mail_fakes.py; every email here is invented; nothing leaves."""

from __future__ import annotations

from datetime import date
from email.message import EmailMessage

import anyio
import pytest
from fastapi.testclient import TestClient
from mail_fakes import FakeGmail

from areao1.google import mail, opportunities
from areao1.jobs import JOBS
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}
D = "05-Oct-2026 16:30:00 +0000"
PASS = "mx.google.com; dkim=pass header.d=examplehacks.org; spf=pass; dmarc=pass header.from=examplehacks.org"


@pytest.fixture
def g(monkeypatch):
    fake = FakeGmail(bodies_ok=True).install(monkeypatch)
    mail.connect(fake.email, fake.password)
    return fake


def invite(g, uid=1, subject="Invitation to judge Example Hacks 2026", auth=PASS, frm="Example Hacks <team@examplehacks.org>",
           body="Hi Alex, we'd love you to judge the AI track at Example Hacks on November 8, 2026. Details: "
                "https://examplehacks.org/judges", **kw):  # fmt: skip
    return g.add(uid, D, frm, "alex@gmail.com", subject, body=body, auth_results=auth, **kw)


def test_dates_links_and_the_event_name():
    text = "Finals Nov 7-8 (judging on 8 November). Apply by 2026-10-20 at https://examplehacks.org/judge."
    assert opportunities.dates_in(text, date(2026, 10, 5)) == {
        date(2026, 11, 7),
        date(2026, 11, 8),
        date(2026, 10, 20),
    }
    assert opportunities.dates_in("See you March 3", date(2026, 10, 5)) == {
        date(2027, 3, 3)
    }  # the next March
    assert opportunities.links_in(text) == ["https://examplehacks.org/judge"]
    assert (
        opportunities.event_name("Fwd: You're invited to judge: Example Hacks 2026") == "Example Hacks 2026"
    )


def test_opportunity_mail_becomes_inbox_items_with_stage_facts_and_one_quote(ws, g):
    invite(g)
    g.add(2, D, "Example Hacks <team@examplehacks.org>", "alex@gmail.com", "Thank you for judging Example Hacks 2025",
          body="Thank you for judging at Example Hacks 2025! Your scores helped pick the winners.", auth_results=PASS)  # fmt: skip
    g.add(3, D, "Shop <deals@shop.example>", "alex@gmail.com", "50% off", tab="promotions")
    out = anyio.run(opportunities.run, ws, None, None)
    assert out["lines"][-1] == "Opportunities: 2 new in your Inbox (0 verified)"
    by = {c.title: c for c in ws.pending_candidates() if c.fingerprint.startswith("opp:")}
    inv, done = by["Invitation to judge Example Hacks 2026"], by["Thank you for judging Example Hacks 2025"]
    assert (inv.stage, inv.proposed_criterion, inv.evidence_type) == ("invited", "judging", "judge_invite")
    assert done.stage == "completed"
    assert inv.facts["dates"] == "2026-11-08" and inv.facts["sender_auth"] == "verified"
    assert (
        inv.verification == "unconfirmed" and "Verified sender" in inv.verification_note
    )  # no web check yet
    assert inv.raw_url.startswith("https://mail.google.com/") and inv.source.startswith("gmail:")
    assert inv.summary.count('"') == 2  # one quoted sentence, not the body
    assert ws.changes()[-1].actor == "opportunities"
    assert (
        anyio.run(opportunities.run, ws, None, None)["lines"][-1] == "Opportunities: nothing new"
    )  # once each
    for f in ws.root.rglob("*"):
        if f.is_file() and f.suffix in (".json", ".jsonl"):
            assert b"Your scores helped pick" not in f.read_bytes() or "inbox" in f.name, (
                f
            )  # body never kept beyond the quote


def test_a_failed_sender_check_is_suspicious(ws, g):
    invite(
        g,
        frm="Example Hacks <team@examplehacks-org.co>",
        auth="mx.google.com; dkim=none; spf=fail; dmarc=fail",
    )
    anyio.run(opportunities.run, ws, None, None)
    [c] = [c for c in ws.pending_candidates() if c.fingerprint.startswith("opp:")]
    assert c.verification == "suspicious" and "failed" in c.verification_note


def test_the_job_is_off_by_default_and_runs_by_hand_or_when_enabled(ws, g):
    invite(g)
    assert ws.config().opportunities.enabled is False and ws.config().schedules["daily-opportunities"]
    assert JOBS["daily-opportunities"][1](ws, True) == [
        "skipped: the daily opportunity check is off (Settings > Gmail)"
    ]
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    assert c.put("/api/settings/opportunities", headers=W, json={"enabled": True}).json()["enabled"] is True
    assert ws.changes()[-1].action == "settings.opportunities"
    lines = JOBS["daily-opportunities"][1](ws, True)
    assert lines[-1].startswith("Opportunities: 1 new")
    assert c.post("/api/opportunities/run", headers=W).json()["lines"][-1] == "Opportunities: nothing new"


def test_a_forwarded_original_is_a_find_as_itself(ws, g):
    o = EmailMessage()
    o["Authentication-Results"] = PASS
    o["From"], o["To"], o["Subject"] = (
        "Example Hacks <team@examplehacks.org>",
        "alex@work.example",
        "Judge for Example Hacks 2026?",
    )
    o["Date"] = "Mon, 05 Oct 2026 10:00:00 +0000"
    o.set_content("Would you judge our finals on November 8?")
    g.add(1, D, "Alex <alex@gmail.com>", "alex@gmail.com", "Fwd: from work", attached=bytes(o),
          auth_results="mx.google.com; dkim=fail header.d=gmail.com; dmarc=fail")  # fmt: skip
    anyio.run(opportunities.run, ws, None, None)
    [c] = [c for c in ws.pending_candidates() if c.fingerprint.startswith("opp:")]
    assert c.title == "Judge for Example Hacks 2026?" and c.facts["sender_auth"] == "verified"
    assert c.facts["from"] == "team@examplehacks.org" and c.verification == "unconfirmed"


def test_a_hackathon_notice_or_digest_is_not_a_judging_find(ws, g):
    """Found on real mail: a hackathon's participant notices and a platform's digest sit in Judging & hackathons
    (by keyword or domain) but aren't invitations, so they never become finds."""
    g.add(1, D, "Hackathon Platform <help@platform.example>", "alex@gmail.com", "Spring Hackathon: your idea was selected",
          body="Congratulations, your idea made it to round two. Build on!", tab="promotions")  # fmt: skip
    g.add(2, D, "Devpost <cassie@devpost.com>", "alex@gmail.com", "HACKATHONS just for you",
          body="Here are this week's hackathons you might like.")  # fmt: skip
    invite(g, uid=3)
    out = anyio.run(opportunities.run, ws, None, None)
    assert [c.title for c in ws.pending_candidates() if c.fingerprint.startswith("opp:")] == [
        "Invitation to judge Example Hacks 2026"
    ]
    assert "2 not about an opportunity" in out["lines"][-1]
