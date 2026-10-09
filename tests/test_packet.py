"""The review packet (ADR 0020): numbered counted exhibits (never self-reported), the claim -> exhibit -> page/quote
matrix (pages found, never guessed), an outline from approved claims only, the label on every page, .docx / PDF /
ZIP outputs with provenance, and byte-identical rebuilds. Everything here is invented."""

from __future__ import annotations

import io
import json
import xml.etree.ElementTree as ET
import zipfile
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient
from pypdf import PdfReader

from areao1.core.models import ClaimDraft, Evidence
from areao1.criteria import packet
from areao1.criteria.grounding import LABEL
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}
WEB = Path(__file__).resolve().parents[1] / "web" / "src"


def _pdf(*pages: str) -> bytes:
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, invariant=1)
    for text in pages:
        c.drawString(72, 700, text)
        c.showPage()
    c.save()
    return buf.getvalue()


def _exhibit(ws, title, *, crit="judging", kind="panel_letter", on=date(2025, 3, 1), content=None, tier=None,
             filename="x.pdf"):  # fmt: skip
    e = ws.add_exhibit_file(content=content or _pdf(title), filename=filename, criterion=crit, evidence_type=kind,
                            title=title, on=on)  # fmt: skip
    if tier:
        ex = ws.exhibits()
        next(x for x in ex.exhibits if x.id == e.id).source_tier = tier
        ws.save_exhibits(ex)
        ws.after_change()
    return e


def _claim(ws, predicate, value, excerpt, *, approve=True, subject="event:hacks"):
    [c] = ws.memory.record(Evidence(connector="website", source_url=f"https://hacks.example/{predicate}/{value}",
                                    payload=excerpt, media_type="text/plain",
                                    claims=[ClaimDraft(subject=subject, subject_kind="event", subject_name="Lakeside Hacks",
                                                       predicate=predicate, value=value, excerpt=excerpt)]))  # fmt: skip
    if approve:
        ws.memory.decide([c.id], "approved")
    return c


def _case(ws):
    judged = _exhibit(ws, "Lakeside Hacks judges", on=date(2025, 3, 1),
                      content=_pdf("Lakeside Hacks 2025", "Judges: Maya Chen, systems track"))  # fmt: skip
    _exhibit(ws, "Another panel", on=date(2025, 1, 5))
    _exhibit(ws, "Award certificate", crit="awards", kind="award_certificate", on=date(2024, 6, 1))
    _exhibit(ws, "My own notes", tier="self_reported")
    found = _claim(ws, "judged_event", "systems track", "Judges: Maya Chen, systems track")
    missing = _claim(ws, "panel_size", "9 judges", "Nine judges served on the panel.")
    waiting = _claim(ws, "track_count", "4 tracks", "Four tracks.", approve=False)
    verdict = _claim(ws, "status", "qualifies for O-1", "qualifies for O-1")
    ws.memory.cite(judged.id, [found.id, missing.id, waiting.id, verdict.id])
    return judged, found, missing, waiting, verdict


def test_counted_exhibits_are_numbered_per_criterion_and_self_reported_never_appears(ws):
    _case(ws)
    items = packet.number(ws)
    assert [(i.number, i.exhibit.title) for i in items] == [
        ("C1-01", "Award certificate"),  # awards is C1 in O-1A
        ("C4-01", "Another panel"),  # judging is C4; by date, then title
        ("C4-02", "Lakeside Hacks judges"),
    ]


def test_the_matrix_finds_the_page_and_never_guesses(ws):
    _, found, missing, waiting, verdict = _case(ws)
    items = packet.number(ws)
    for it in items:
        packet.render_exhibit(ws, it)
    rows = {r.claim.id: r for r in packet.matrix(ws, items)}
    assert waiting.id not in rows  # only approved claims
    assert rows[found.id].page == 2 and rows[found.id].item.number == "C4-02"
    assert rows[missing.id].page is None  # "not found", not a guess
    text, cited, dropped = packet.outline(items, list(rows.values()))
    assert found.id in cited and any("qualifies" in d for d in dropped) and "qualifies" not in text
    assert all(line.rstrip().endswith("]") for line in text.splitlines() if line and not line.startswith("#"))


def test_a_superseded_value_is_left_out(ws):
    judged, *_ = _case(ws)
    old = _claim(ws, "prize", "$500", "Prize $500", subject="event:prize")
    new = _claim(ws, "prize", "$1,000", "Prize $1,000", subject="event:prize")
    ws.memory.cite(judged.id, [old.id, new.id])
    ids = {r.claim.id for r in packet.matrix(ws, packet.number(ws))}
    assert new.id in ids and old.id not in ids


def test_every_page_is_labeled_and_numbered_and_rebuilds_are_identical(ws):
    _case(ws)
    first = packet.build(ws)
    out = ws.root / "exports" / first["name"]
    reader = PdfReader(out / "packet.pdf")
    total = len(reader.pages)
    assert total == first["pages"]
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text()
        assert LABEL in text and f"Page {i} of {total}" in text, i
    assert first["exhibits"][2] == {"number": "C4-02", "id": first["exhibits"][2]["id"], "title": "Lakeside Hacks judges",
                                    "pages": first["exhibits"][2]["pages"]}  # fmt: skip
    start = int(first["exhibits"][2]["pages"].split("–")[0])
    assert "Exhibit C4-02" in reader.pages[start - 1].extract_text()  # the index's page range is right
    assert "systems track" in reader.pages[start + 1].extract_text()  # and the matrix's page 2 is that page
    again = packet.build(ws)
    assert again["files"] == first["files"] and again["name"] == first["name"]
    _exhibit(ws, "A new one", on=date(2026, 1, 1))
    assert packet.build(ws)["name"] != first["name"]  # new inputs, new folder


def test_docx_csv_zip_and_provenance(ws):
    _, found, *_ = _case(ws)
    m = packet.build(ws)
    out = ws.root / "exports" / m["name"]
    with zipfile.ZipFile(out / "packet.docx") as z:
        names = z.namelist()
        assert names[0] == "[Content_Types].xml" and {
            "word/document.xml",
            "word/header1.xml",
            "_rels/.rels",
        } <= set(names)
        for n in names:
            ET.fromstring(z.read(n))  # every part is well-formed XML
        assert (
            LABEL in z.read("word/header1.xml").decode() and "C4-02" in z.read("word/document.xml").decode()
        )
    csv_text = (out / "matrix.csv").read_text()
    assert csv_text.splitlines()[0].startswith("exhibit,exhibit_title,claim_id") and found.id in csv_text
    with zipfile.ZipFile(out / "attorney-export.zip") as z:
        names = set(z.namelist())
        assert {"packet.docx", "packet.pdf", "matrix.csv", "preflight.json", "provenance.json", "provenance.prov.json",
                "manifest.json"} <= names  # fmt: skip
        assert any(n.startswith("exhibits/C4-02_") for n in names)
        assert not any("notes" in n.lower() for n in names)  # the self-reported file isn't in it
        assert {i.date_time for i in z.infolist()} == {packet.FIXED_ZIP_TIME}
    prov = json.loads((out / "provenance.prov.json").read_text())
    assert f"areao1:{found.id}" in prov["entity"] and prov["activity"] and prov["wasDerivedFrom"]
    plain = json.loads((out / "provenance.json").read_text())
    assert found.id in {c["id"] for c in plain["claims"]} and plain["decisions"]


def test_the_api_builds_lists_and_serves_files(ws):
    _case(ws)
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    m = c.post("/api/packets", headers=W).json()
    assert m["label"] == LABEL and ws.changes()[-1].action == "packet.build"
    [listed] = c.get("/api/packets").json()
    assert listed["name"] == m["name"] and "packet.pdf" in listed["files_present"]
    pdf = c.get(f"/api/packets/{m['name']}/packet.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert c.get(f"/api/packets/{m['name']}/../../person.json").status_code == 404
    assert c.get("/api/packets/not-a-packet/packet.pdf").status_code == 404


def test_the_ui_builds_a_review_packet_and_never_a_petition():
    ui = (WEB / "components" / "Packet.tsx").read_text()
    assert "Build review packet" in ui and LABEL in ui
    for verb in ("Generate petition", "Submit", "File petition", "File with", "petition generator"):
        assert verb.lower() not in ui.lower(), verb
