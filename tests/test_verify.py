"""Verifying opportunity mail (ADR 0016 §3): sender check + the event on its official page (or Devpost / MLH) with a
matching date; otherwise unconfirmed with a check-in drafted for approval, or suspicious with nothing sent. Pages and
search are fakes; every email is invented."""

from __future__ import annotations

from datetime import UTC, datetime

import anyio
import pytest
from mail_fakes import FakeGmail

from areao1.engine.openai_engine import SearchResult
from areao1.google import mail, opportunities, verify

D = "05-Oct-2026 16:30:00 +0000"
PASS = "mx.google.com; dkim=pass header.d=examplehacks.org; spf=pass; dmarc=pass header.from=examplehacks.org"
PAGE = "Example Hacks 2026 · Judges · Finals on November 8, 2026 at the Example Center."


@pytest.fixture
def g(monkeypatch):
    fake = FakeGmail(bodies_ok=True).install(monkeypatch)
    mail.connect(fake.email, fake.password)
    return fake


def pages(mapping):
    calls = []

    async def fetch(url):
        calls.append(url)
        if url not in mapping:
            raise ValueError("unreachable")
        final, text = mapping[url] if isinstance(mapping[url], tuple) else (url, mapping[url])
        return final, "page", text

    fetch.calls = calls
    return fetch


class Engine:
    """Just the hosted search the verifier uses."""

    def __init__(self, sources):
        self.sources, self.queries = sources, []

    async def hosted_search(self, client, query, domains, model):
        self.queries.append((query, domains, model))
        return SearchResult("found", self.sources, {"input_tokens": 50, "output_tokens": 10}, 1, 0.0101)


def _run(ws, fetch, engine=None):
    return anyio.run(opportunities.run, ws, None, verify.verifier(engine, "gpt-6-luna", fetch))


def _find(ws):
    [c] = [c for c in ws.pending_candidates() if c.fingerprint.startswith("opp:")]
    return c


def invite(g, body="We'd love you to judge Example Hacks 2026 on November 8, 2026: https://examplehacks.org/judges",
           auth=PASS, frm="Example Hacks <team@examplehacks.org>", subject="Invitation to judge Example Hacks 2026"):  # fmt: skip
    g.add(1, D, frm, "alex@gmail.com", subject, body=body, auth_results=auth)


def test_verified_needs_the_sender_check_and_the_event_on_its_official_page(ws, g):
    invite(g)
    out = _run(ws, pages({"https://examplehacks.org/judges": PAGE}))
    c = _find(ws)
    assert c.verification == "verified" and c.raw_url == "https://examplehacks.org/judges"
    assert "Verified sender" in c.verification_note and "2026-11-08" in c.verification_note
    assert out["lines"][-1] == "Opportunities: 1 new in your Inbox (1 verified)"
    assert not ws.outreach().drafts  # nothing to ask


def test_no_matching_date_means_unconfirmed_with_a_check_in_drafted(ws, g):
    invite(g)
    _run(ws, pages({"https://examplehacks.org/judges": "Example Hacks 2026 judges. Dates to be announced."}))
    c = _find(ws)
    assert c.verification == "unconfirmed" and "doesn't show the email's dates" in c.verification_note
    [d] = ws.outreach().drafts
    assert (d.status, d.drafted_by, d.to, d.purpose) == (
        "draft",
        "opportunities",
        "team@examplehacks.org",
        "ask",
    )
    assert "Example Hacks 2026" in d.body and d.subject.startswith("Re: ")
    [contact] = ws.contacts().contacts
    assert contact.relationship == "organizer" and "daily opportunity check" in contact.notes


def test_no_link_searches_the_organizer_and_platforms_once_on_the_mundane_tier(ws, g):
    invite(g, body="Would you judge Example Hacks 2026 on November 8, 2026?")
    engine = Engine(["https://devpost.com/software/elsewhere", "https://example-hacks-2026.devpost.com/"])
    fetch = pages({"https://example-hacks-2026.devpost.com/": PAGE})
    out = _run(ws, fetch, engine)
    [(query, domains, model)] = engine.queries
    assert query == "Example Hacks 2026"
    assert domains == ["examplehacks.org", "devpost.com", "mlh.io"] and model == "gpt-6-luna"
    assert _find(ws).verification == "verified" and out["cost_usd"] == pytest.approx(0.0101)


def test_a_page_is_only_trusted_on_the_organizers_domain_or_a_platform(ws, g):
    invite(g, body="Judge Example Hacks 2026 on November 8, 2026: https://examplehacks-events.example/j and "
                   "https://examplehacks.org/r")  # fmt: skip
    fetch = pages({"https://examplehacks-events.example/j": PAGE,  # not the organizer's domain: never fetched
                   "https://examplehacks.org/r": ("https://evil.example/landing", PAGE)})  # redirected off-site  # fmt: skip
    _run(ws, fetch)
    assert fetch.calls == ["https://examplehacks.org/r"] and _find(ws).verification == "unconfirmed"


def test_an_unverified_sender_stays_unconfirmed_even_with_a_matching_page(ws, g):
    invite(g, auth="")
    _run(ws, pages({"https://examplehacks.org/judges": PAGE}))
    c = _find(ws)
    assert c.verification == "unconfirmed" and "Sender not verified" in c.verification_note
    assert (
        "confirmed on https://examplehacks.org/judges" in c.verification_note
        and len(ws.outreach().drafts) == 1
    )


def test_a_failed_sender_check_is_suspicious_and_nothing_is_drafted(ws, g):
    invite(
        g,
        frm="Example Hacks <team@examplehacks-org.co>",
        auth="mx.google.com; spf=fail; dkim=none; dmarc=fail",
    )
    fetch = pages({})
    _run(ws, fetch)
    c = _find(ws)
    assert c.verification == "suspicious" and "No check-in was drafted" in c.verification_note
    assert not ws.outreach().drafts and not ws.contacts().contacts and fetch.calls == []


def test_a_reply_from_the_organizer_after_the_check_in_confirms_it(ws, g):
    invite(g, body="Would you judge Example Hacks 2026?")  # no date, no link: unconfirmed
    _run(ws, pages({}))
    [d] = ws.outreach().drafts
    ws.put_draft(d.model_copy(update={"status": "sent", "sent_at": datetime(2026, 10, 6, 9, 0, tzinfo=UTC)}))
    g.add(1, "07-Oct-2026 12:00:00 +0000", "Example Hacks <team@examplehacks.org>", "alex@gmail.com",  # same thread
          "Re: Invitation to judge Example Hacks 2026", body="Yes! Finals are November 8.", auth_results=PASS)  # fmt: skip
    out = _run(ws, pages({}))
    c = _find(ws)
    assert c.verification == "confirmed" and "replied to your check-in" in c.verification_note
    assert "1 confirmed by the organizer's reply" in out["lines"][-1]
    assert any(ch.action == "inbox.verify" and ch.actor == "opportunities" for ch in ws.changes())


def test_free_mail_senders_only_count_platform_pages():
    assert verify.allowed_domains("gmail.com") == ["devpost.com", "mlh.io"]
    assert verify.allowed_domains("mail.examplehacks.org") == ["examplehacks.org", "devpost.com", "mlh.io"]
