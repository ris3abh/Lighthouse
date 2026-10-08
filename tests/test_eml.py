"""Emails from other accounts (ADR 0014, amendment): dropped .eml files and Gmail messages forwarded as an attachment.
Sender authentication from the original headers, the Mail view's rules, a stage from the text, the original kept
as the exhibit source. Every email here is invented."""

from __future__ import annotations

from email.message import EmailMessage

import anyio
import pytest
from fastapi.testclient import TestClient
from mail_fakes import FakeGmail

from areao1.google import eml, mail, mailview
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}
GOOD = ("mx.google.com; dkim=pass header.i=@examplehacks.org header.s=s1 header.b=abc; "
        "spf=pass (google.com: domain of team@examplehacks.org designates 192.0.2.1) smtp.mailfrom=team@examplehacks.org; "
        "dmarc=pass (p=REJECT) header.from=examplehacks.org")  # fmt: skip


def make_eml(subject: str, body: str, frm: str = "Example Hacks <team@examplehacks.org>",
             auth: str | None = GOOD, extra: dict[str, str] | None = None) -> bytes:  # fmt: skip
    m = EmailMessage()
    if auth:
        m["Authentication-Results"] = auth
    for k, v in (extra or {}).items():
        m[k] = v
    m["From"], m["To"], m["Subject"] = frm, "Alex Rivera <alex@work.example>", subject
    m["Date"] = "Mon, 05 Oct 2026 16:30:00 +0000"
    m.set_content(body)
    return bytes(m)


@pytest.fixture
def c(ws):
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        yield client


def _drop(c, *files):
    return c.post(
        "/api/inbox/upload", headers=W, files=[("files", (n, b, "message/rfc822")) for n, b in files]
    )


# ----------------------------------------------------------------------------- sender authentication


@pytest.mark.parametrize(
    ("headers", "verdict", "dkim_domain"),
    [
        ([GOOD], "verified", "examplehacks.org"),
        (["mx.google.com; dkim=pass header.d=mail.examplehacks.org; spf=softfail smtp.mailfrom=x.example"],
         "verified", "mail.examplehacks.org"),  # DKIM for the From domain's organization, no DMARC result
        (["mx.google.com; dkim=pass header.d=bulkmailer.example; spf=pass; dmarc=fail header.from=examplehacks.org"],
         "failed", "bulkmailer.example"),  # signed by someone else and DMARC failed
        (["mx.google.com; dkim=none; spf=neutral; dmarc=none"], "unverified", None),
        ([], "unverified", None),
        # the receiving server adds its header on top; a "pass" lower down (added by the sender) is ignored
        (["mx.google.com; dkim=fail header.d=examplehacks.org; dmarc=fail header.from=examplehacks.org", GOOD],
         "failed", None),
    ],
)  # fmt: skip
def test_authentication_from_the_topmost_results(headers, verdict, dkim_domain):
    m = EmailMessage()
    for h in headers:
        m["Authentication-Results"] = h
    m["From"] = "team@examplehacks.org"
    a = eml.authentication(m)
    assert (a["verdict"], a["dkim_domain"]) == (verdict, dkim_domain)
    if headers:
        assert a["by"] == "mx.google.com"


def test_arc_results_when_no_authentication_results():
    m = EmailMessage()
    m["ARC-Authentication-Results"] = (
        "i=1; mx.microsoft.com 1; spf=pass; dkim=pass header.d=examplehacks.org; dmarc=pass"
    )
    m["From"] = "team@examplehacks.org"
    assert (
        eml.authentication(m)["verdict"] == "verified" and eml.authentication(m)["by"] == "mx.microsoft.com"
    )


@pytest.mark.parametrize(
    ("text", "stage"),
    [
        ("We'd love for you to judge the finals on November 8. Would you be available?", "invited"),
        ("Thank you for judging at Example Hacks! Your scores helped pick 12 winners.", "completed"),
        ("Your reviews have been submitted for the workshop. We appreciate your time.", "completed"),
        ("Thanks for applying to judge. We'll let you know.", "invited"),
    ],
)
def test_stage_comes_from_the_text_and_defaults_to_invited(text, stage):
    assert eml.stage_of(text) == stage


# ----------------------------------------------------------------------------- dropped .eml files


def test_a_dropped_eml_becomes_an_invited_judging_candidate_with_its_file(c, ws):
    raw = make_eml("Invitation to judge Example Hacks 2026",
                   "Hi Alex,\n\nWe'd like to invite you to judge the AI track at Example Hacks on November 8.\n\nTeam")  # fmt: skip
    r = _drop(c, ("judge-invite.eml", raw))
    assert r.status_code == 200, r.text
    [cand] = r.json()
    assert (cand["proposed_criterion"], cand["evidence_type"], cand["stage"]) == (
        "judging",
        "judge_invite",
        "invited",
    )
    assert cand["title"] == "Invitation to judge Example Hacks 2026"
    assert "Verified sender (DMARC passed, checked by mx.google.com)" in cand["summary"]
    assert (
        '"We\'d like to invite you to judge the AI track at Example Hacks on November 8."' in cand["summary"]
    )
    assert cand["facts"]["sender_auth"] == "verified" and cand["facts"]["from"] == "team@examplehacks.org"
    obs = ws.memory.observation(cand["attachment"])
    assert ws.resolve_inside(obs.snapshot).read_bytes() == raw  # the original file, byte for byte
    [item] = ws.mailbox().items  # case mail: shown in Contacts > Mail too
    assert (item.source, item.category, item.auth["verdict"]) == ("eml", "judging", "verified")
    text = c.get(f"/api/mail/{item.id}/text").json()
    assert "invite you to judge the AI track" in text["text"] and text["from"].startswith("Example Hacks")
    accepted = c.post(f"/api/inbox/{cand['id']}/accept", headers=W, json={}).json()
    exhibit = next(x for x in ws.exhibits().exhibits if x.title == cand["title"])
    assert exhibit.file.endswith(".eml") and exhibit.stage == "invited" and accepted


def test_a_completed_role_and_an_unverified_sender(c):
    done = make_eml("Thank you!", "Thank you for judging at Example Hacks. Your certificate is attached.")
    spoof = make_eml("You won", "Congratulations on winning our grand prize award", frm="Prize Desk <win@prizes.example>",
                     auth=None)  # fmt: skip
    a, b = _drop(c, ("thanks.eml", done), ("won.eml", spoof)).json()
    assert (
        a["stage"] == "completed" and a["proposed_criterion"] == "judging"
    )  # "judging" in the text placed it
    assert b["proposed_criterion"] == "awards" and b["stage"] == "granted"
    assert "Sender not verified" in b["summary"] and b["confidence"] < a["confidence"]


def test_dropped_on_a_criterion_that_wins_and_a_non_email_is_refused(c):
    raw = make_eml("Quick note", "See you there.", frm="Someone <someone@else.example>")
    [cand] = c.post("/api/inbox/upload", headers=W, data={"criterion": "press"},
                    files=[("files", ("note.eml", raw, "message/rfc822"))]).json()  # fmt: skip
    assert cand["proposed_criterion"] == "press"
    r = _drop(c, ("notes.eml", b"just some text\nwith no headers"))
    assert r.status_code == 400 and "doesn't look like an email" in r.json()["detail"]


# ----------------------------------------------------------------------------- forwarded as an attachment


def test_a_gmail_forward_is_sorted_and_verified_by_its_attached_original(ws, monkeypatch, c):
    g = FakeGmail(bodies_ok=True).install(monkeypatch)
    mail.connect(g.email, g.password)
    original = make_eml("Judge for Example Hacks 2026?", "Would you judge our finals? We'd be honored.")
    g.add(1, "05-Oct-2026 16:30:00 +0000", "Alex <alex@gmail.com>", "alex@gmail.com", "Fwd: from my work inbox",
          attached=original, auth_results="mx.google.com; dkim=fail header.d=gmail.com; dmarc=fail")  # fmt: skip
    g.commands.clear()
    anyio.run(mailview.sync, ws, None)
    [item] = ws.mailbox().items
    assert (item.from_addr, item.subject, item.category) == ("team@examplehacks.org", "Judge for Example Hacks 2026?",
                                                             "judging")  # fmt: skip
    assert (
        item.auth["verdict"] == "verified" and item.forwarded_part == "2"
    )  # the original's, not the forward's
    assert "forwarded as an attachment" in item.why
    specs = [x[3] for x in g.commands if x[:2] == ("UID", "FETCH")]
    assert "(BODYSTRUCTURE)" in specs and "(BODY.PEEK[2.HEADER])" in specs
    assert "Would you judge our finals" in c.get(f"/api/mail/{item.id}/text").json()["text"]
    cand = c.post(f"/api/mail/{item.id}/import", headers=W).json()
    assert (cand["proposed_criterion"], cand["stage"]) == ("judging", "invited")
    assert "Verified sender" in cand["summary"] and cand["attachment"]
    assert ("UID", "FETCH", "1", "(BODY.PEEK[2])") in g.commands  # PEEK: still unread in Gmail
    assert ws.changes()[-1].action == "inbox.upload"  # through the service layer, like any drop
    assert c.post("/api/mail/12345/import", headers=W).status_code == 404


def test_the_guide_for_other_accounts_is_in_the_docs_and_the_mail_view():
    from pathlib import Path

    root = Path(__file__).parents[1]
    doc = (root / "docs" / "manual" / "connectors" / "gmail.md").read_text()
    view = (root / "web" / "src" / "components" / "MailView.tsx").read_text()
    for text in (doc, view):
        assert "Bring in emails from another account (e.g. work)" in text
        assert "employer's email policy first" in text
        assert (
            "Forward as attachment" in text
            and ".eml" in text
            and "plain Forward" in text.replace("A plain **Forward**", "A plain Forward")
        )
