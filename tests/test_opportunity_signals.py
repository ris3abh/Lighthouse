"""F4 (ADR 0016 §4): finds are de-duplicated against the Inbox (scout leads included), the pipeline and exhibits;
each new find sends one notification with the banter copy; and no phishing fixture ever comes out verified. Every
email and page here is invented."""

from __future__ import annotations

import anyio
import pytest
from mail_fakes import FakeGmail
from test_missions import _recorder
from test_verify import PAGE, pages

from areao1.core.models import Candidate
from areao1.google import mail, opportunities, verify

D = "05-Oct-2026 16:30:00 +0000"


def auth(domain: str) -> str:
    return f"mx.google.com; dkim=pass header.d={domain}; spf=pass; dmarc=pass header.from={domain}"


@pytest.fixture
def g(monkeypatch):
    fake = FakeGmail(bodies_ok=True).install(monkeypatch)
    mail.connect(fake.email, fake.password)
    return fake


def _run(ws, fetch):
    return anyio.run(opportunities.run, ws, None, verify.verifier(None, "gpt-6-luna", fetch))


def _finds(ws):
    return [c for c in ws.pending_candidates() if c.fingerprint.startswith("opp:")]


# ----------------------------------------------------------------------------- de-duplication


def test_a_find_already_tracked_by_a_scout_lead_or_the_pipeline_is_skipped(ws, g):
    ws.add_candidates([Candidate(kind="pipeline", fingerprint="agent:pipeline:x", source="agent:run_1",
                                 evidence_type="agent_suggestion", proposed_criterion="",
                                 title="Apply to judge Example Hacks 2026 (Example University)", summary="scout lead")])  # fmt: skip
    ws.add_pipeline_item(title="Reviewer: Workshop on Example Agents 2026", stage="idea")
    g.add(1, D, "Example Hacks <team@examplehacks.org>", "alex@gmail.com", "Invitation to judge Example Hacks 2026",
          body="Judge with us on November 8, 2026.", auth_results=auth("examplehacks.org"))  # fmt: skip
    g.add(2, D, "Chairs <chairs@agents.example>", "alex@gmail.com", "Invitation to review: Workshop on Example Agents 2026",
          body="Please review for us.", auth_results=auth("agents.example"))  # fmt: skip
    g.add(3, D, "Example Hacks <team@examplehacks.org>", "alex@gmail.com", "Invitation to judge Example Hacks 2027",
          body="Next year's edition!", auth_results=auth("examplehacks.org"))  # fmt: skip
    out = _run(ws, pages({}))
    assert [c.title for c in _finds(ws)] == ["Invitation to judge Example Hacks 2027"]  # another year is new
    assert out["lines"][-1].endswith("2 already tracked")


# ----------------------------------------------------------------------------- notifications


def test_each_new_find_notifies_once_with_the_banter_copy(ws, g, monkeypatch):
    rec = _recorder(monkeypatch)
    g.add(1, D, "Example Hacks <team@examplehacks.org>", "alex@gmail.com", "Invitation to judge Example Hacks 2026",
          body="Judge on November 8, 2026: https://examplehacks.org/judges", auth_results=auth("examplehacks.org"))  # fmt: skip
    g.add(2, D, "Chairs <chairs@agents.example>", "alex@gmail.com", "Invitation to review for Example Agents 2026",
          body="Please review.", auth_results=auth("agents.example"))  # fmt: skip
    g.add(3, D, "Example Hacks <team@examplehacks-org.co>", "alex@gmail.com", "Judge Example Hackathon 2026 now",
          body="Urgent: confirm your judge seat", auth_results="mx.google.com; spf=fail; dkim=none; dmarc=fail")  # fmt: skip
    _run(ws, pages({"https://examplehacks.org/judges": PAGE}))
    titles = sorted(n.title for n in rec.sent)
    assert titles == sorted(["New signal detected: Example Hacks 2026, verified.",
                             "Unidentified signal. Couldn't confirm the sender, so I drafted a check-in.",
                             "Suspicious invitation: Judge Example Hackathon 2026 now"])  # fmt: skip
    assert all(n.event == "opportunity" and "inbox?candidate=cand_" in n.url for n in rec.sent)
    _run(ws, pages({"https://examplehacks.org/judges": PAGE}))
    assert len(rec.sent) == 3  # nothing new, nothing sent


# ----------------------------------------------------------------------------- phishing never verifies

PHISHING = [
    # a famous name on a free mail account, linking to the real event page
    ("Example Hacks <examplehacks.team@gmail.com>", auth("gmail.com"), "https://examplehacks.org/judges"),
    # a look-alike domain with its own DMARC and a copied page
    ("Example Hacks <team@examp1ehacks.org>", auth("examp1ehacks.org"), "https://examp1ehacks.org/judges"),
    # the real domain hidden in front of the attacker's
    ("Example Hacks <team@examplehacks.org.evil.example>", auth("evil.example"),
     "https://examplehacks.org.evil.example/judges"),
    # the real domain in From, but DMARC failed (spoofed)
    ("Example Hacks <team@examplehacks.org>", "mx.google.com; spf=fail; dkim=fail header.d=examplehacks.org; "
     "dmarc=fail header.from=examplehacks.org", "https://examplehacks.org/judges"),
    # signed by a bulk sender for someone else's From
    ("Example Hacks <team@examplehacks.org>", "mx.google.com; dkim=pass header.d=bulkmail.example; dmarc=fail",
     "https://examplehacks.org/judges"),
    # no authentication results at all
    ("Example Hacks <team@examplehacks.org>", "", "https://examplehacks.org/judges"),
    # authenticated, but only links elsewhere (a shortener)
    ("Example Hacks <team@examplehacks.org>", auth("examplehacks.org"), "https://short.example/x"),
    # an imitation of a known platform
    ("Devpost <judges@dev-post.com>", auth("dev-post.com"), "https://dev-post.com/example-hacks-2026"),
]  # fmt: skip


@pytest.mark.parametrize(("frm", "results", "link"), PHISHING)
def test_no_phishing_fixture_comes_out_verified(ws, g, frm, results, link):
    g.add(1, D, frm, "alex@gmail.com", "Invitation to judge Example Hacks 2026",
          body=f"Confirm your judge seat for Example Hacks 2026 on November 8, 2026: {link}", auth_results=results)  # fmt: skip
    every_page_confirms = pages({link: PAGE, "https://examplehacks.org/judges": PAGE})
    _run(ws, every_page_confirms)
    [c] = _finds(ws)
    assert c.verification != "verified", (frm, c.verification_note)


def test_an_authenticated_sender_whose_page_doesnt_mention_the_event_stays_unconfirmed(ws, g):
    g.add(1, D, "Example Hacks <team@examplehacks.org>", "alex@gmail.com", "Invitation to judge Example Hacks 2026",
          body="Judge on November 8, 2026: https://examplehacks.org/", auth_results=auth("examplehacks.org"))  # fmt: skip
    _run(ws, pages({"https://examplehacks.org/": "Welcome to our club. Meetings on November 8, 2026."}))
    [c] = _finds(ws)
    assert c.verification == "unconfirmed" and "doesn't name the event" in c.verification_note


def test_imitations_are_named():
    assert "imitation of examplehacks" in verify.imitation("examp1ehacks.org", "Example Hacks 2026", [])
    assert "hides another domain" in verify.imitation("examplehacks.org.evil.example", "Example Hacks", [])
    assert verify.imitation("example-hacks.org", "Example Hacks 2026", []) is None  # an event's own domain
    assert verify.imitation("examplehacks.org", "Example Hacks 2026", ["devpost.com"]) is None
