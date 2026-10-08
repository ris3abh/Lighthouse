"""Exhibit dates (B2): an accepted exhibit carries the date its document shows (email header, PDF metadata, the
claims' event dates), or the person's date; with none it's marked "date unconfirmed", never silently today.
`areao1 repair-dates` fixes exhibits filed before. Everything here is invented."""

from __future__ import annotations

import io
from datetime import UTC, date, datetime
from email.message import EmailMessage

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from areao1.core import clock
from areao1.core.models import Candidate, ClaimDraft, Evidence
from areao1.criteria import dates, preflight
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}


def _eml(day: str = "Sat, 03 Oct 2026 18:00:00 +0000") -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"] = (
        "Example Hacks <team@hacks.example>",
        "maya@example.com",
        "Thank you for judging Example Hacks",
        day,
    )
    m["Authentication-Results"] = (
        "mx.example; dkim=pass header.d=hacks.example; spf=pass; dmarc=pass header.from=hacks.example"
    )
    m.set_content("Thank you for judging at Example Hacks 2026!")
    return bytes(m)


def _pdf(made: datetime | None) -> bytes:
    from pypdf import PdfWriter

    w = PdfWriter()
    w.add_blank_page(72, 72)
    if made:
        w.add_metadata({"/CreationDate": made.strftime("D:%Y%m%d%H%M%S+00'00'")})
    buf = io.BytesIO()
    w.write(buf)
    return buf.getvalue()


def _accept(client, cand_id, **body):
    r = client.post(f"/api/inbox/{cand_id}/accept", headers=W, json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _upload(client, name, data, mime):
    r = client.post("/api/inbox/upload", headers=W, files=[("files", (name, data, mime))])
    assert r.status_code == 200, r.text
    return r.json()[0]


def test_an_email_is_dated_by_its_date_header(ws):
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        cand = _upload(client, "thanks.eml", _eml(), "message/rfc822")
        assert (cand["document_date"], cand["date_source"]) == ("2026-10-03", "email")
        ex = _accept(client, cand["id"])
    assert (ex["date"], ex["date_source"]) == ("2026-10-03", "email") and "_2026-10-03_" in ex["file"]


def test_a_pdf_is_dated_by_its_metadata_and_a_bare_one_is_unconfirmed(ws):
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        dated = _upload(
            client, "award-certificate.pdf", _pdf(datetime(2025, 6, 12, 12, 0, tzinfo=UTC)), "application/pdf"
        )
        bare = _upload(client, "press-profile.pdf", _pdf(None), "application/pdf")
        assert (dated["document_date"], dated["date_source"]) == ("2025-06-12", "pdf")
        assert bare["document_date"] is None
        one = _accept(client, dated["id"], proposed_criterion="awards")
        two = _accept(client, bare["id"], proposed_criterion="press", evidence_type="press_article")
    assert one["date"] == "2025-06-12" and one["date_source"] == "pdf"
    assert two["date_source"] == "unconfirmed" and two["date"] == clock.today().isoformat()
    titles = {i["title"] for i in preflight.run(ws, save=False)["issues"] if i["kind"] == "undated_exhibit"}
    assert titles == {"press profile: date unconfirmed"}


def test_the_claims_event_date_and_the_persons_date(ws):
    payload = "Judged Example Hacks round 2 on 2026-03-14."
    [c] = ws.memory.record(Evidence(connector="website", source_url="https://hacks.example/judges", payload=payload,
                                    media_type="text/plain",
                                    claims=[ClaimDraft(subject="event:x", subject_kind="event", subject_name="Example Hacks",
                                                       predicate="judged_event", value="round 2", excerpt=payload,
                                                       event_date=date(2026, 3, 14))]))  # fmt: skip
    ws.add_candidates([Candidate(fingerprint="web:1", source="website:hacks", evidence_type="panel_letter",
                                 proposed_criterion="judging", title="Judges page", summary="s", claim_ids=[c.id]),
                       Candidate(fingerprint="web:2", source="website:hacks", evidence_type="panel_letter",
                                 proposed_criterion="judging", title="Another page", summary="s")])  # fmt: skip
    first, second = ws.inbox().candidates
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        a = _accept(client, first.id)
        b = _accept(client, second.id, date="2026-02-01")
    assert (a["date"], a["date_source"]) == ("2026-03-14", "claim")
    assert (b["date"], b["date_source"]) == ("2026-02-01", "you")


def test_set_date_renames_the_file_and_is_logged(ws):
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        bare = _upload(client, "certificate.pdf", _pdf(None), "application/pdf")
        ex = _accept(client, bare["id"], proposed_criterion="awards")
        r = client.post(f"/api/exhibits/{ex['id']}/date", headers=W, json={"date": "2024-11-30"})
    out = r.json()
    assert (out["date"], out["date_source"]) == ("2024-11-30", "you") and "_2024-11-30_" in out["file"]
    assert (ws.root / out["file"]).is_file() and not (ws.root / ex["file"]).exists()
    assert ws.naming_check() == [] and ws.changes()[-1].action == "evidence.redate"


def test_repair_dates_for_exhibits_filed_before(ws):
    from areao1.cli import app

    # As before B2: filed with today's date and no source.
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        mail = _upload(client, "thanks.eml", _eml(), "message/rfc822")
        bare = _upload(client, "note.pdf", _pdf(None), "application/pdf")
        e1 = _accept(client, mail["id"], date=clock.today().isoformat())
        e2 = _accept(client, bare["id"], proposed_criterion="press", evidence_type="press_article",
                     date=clock.today().isoformat())  # fmt: skip
    ex = ws.exhibits()
    for e in ex.exhibits:
        e.date_source = None
    ws.save_exhibits(ex)
    steps = {s["exhibit"]: s for s in dates.plan(ws)}
    assert steps[e1["id"]]["to"] == "2026-10-03" and steps[e1["id"]]["source"] == "email"
    assert steps[e2["id"]]["source"] == "unconfirmed"
    dry = CliRunner().invoke(app, ["repair-dates", "-w", str(ws.root)])
    assert dry.exit_code == 0 and "run again with --apply" in dry.output
    assert {e.date_source for e in ws.exhibits().exhibits} == {None}  # a dry run changes nothing
    done = CliRunner().invoke(app, ["repair-dates", "-w", str(ws.root), "--apply"])
    assert "Updated 2 exhibit(s)." in done.output
    by = {e.id: e for e in ws.exhibits().exhibits}
    assert (by[e1["id"]].date.isoformat(), by[e1["id"]].date_source) == ("2026-10-03", "email")
    assert by[e2["id"]].date_source == "unconfirmed"
    assert dates.plan(ws) == [
        s for s in dates.plan(ws) if s["source"] == "unconfirmed"
    ]  # only what nobody knows
