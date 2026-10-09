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


def test_the_merits_section_is_named_for_the_profile(ws):
    _case(ws)

    def texts(m):
        out = ws.root / "exports" / m["name"]
        pdf = "\n".join(page.extract_text() for page in PdfReader(out / "packet.pdf").pages[:8])
        with zipfile.ZipFile(out / "packet.docx") as z:
            return pdf, z.read("word/document.xml").decode()

    pdf, doc = texts(packet.build(ws))  # O-1A: the totality of the evidence
    assert "Totality of the evidence" in pdf and "Totality of the evidence" in doc
    assert "Final merits" not in pdf and "Final merits" not in doc
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    c.put("/api/profile", headers=W, json={"id": "eb1a"})
    pdf, doc = texts(packet.build(ws))  # EB-1A keeps its final merits step
    assert "Final merits" in pdf and "Final merits" in doc and "Totality of the evidence" not in pdf


def test_the_cover_names_the_person_and_the_index_explains_the_numbers(ws):
    _case(ws)
    person = ws.person()
    person.name = "Maya Chen"
    ws.save_person(person)
    m = packet.build(ws)
    out = ws.root / "exports" / m["name"]
    reader = PdfReader(out / "packet.pdf")
    cover = reader.pages[0].extract_text()
    assert cover.splitlines()[0] == "Maya Chen" and "from Maya Chen's workspace" in cover
    assert "the person" not in cover.lower() and reader.metadata.title == "Review packet: Maya Chen"
    index = next(p.extract_text() for p in reader.pages if p.extract_text().startswith("Exhibit index"))
    flat = " ".join(index.split())
    assert (
        "numbered by criterion, in the order the O-1A Extraordinary Ability profile lists them (C1 Awards"
        in flat
    )
    assert "within a criterion, by date and then title" in flat
    with zipfile.ZipFile(out / "packet.docx") as z:
        doc = z.read("word/document.xml").decode()
    assert "Maya Chen" in doc and "numbered by criterion" in doc and "The person" not in doc


def _render(ws, name, data):
    e = ws.add_exhibit_file(content=data, filename=name, criterion="judging", evidence_type="panel_letter",
                            title=name, on=date(2026, 3, 1))  # fmt: skip
    it = packet.Item(
        number="C4-09", exhibit=next(x for x in ws.exhibits().exhibits if x.id == e.id), criterion="Judging"
    )
    packet.render_exhibit(ws, it)
    return it


def test_uploaded_files_appear_as_their_pages_or_as_readable_text(ws):
    from email.message import EmailMessage

    from PIL import Image

    pdf = _render(ws, "certificate.pdf", _pdf("Certificate of appreciation", "Maya Chen judged the finals"))
    assert pdf.pdf == (ws.root / pdf.exhibit.file).read_bytes() and len(pdf.texts) == 2  # the original pages

    m = EmailMessage()
    m["From"], m["To"], m["Subject"] = (
        "Lakeside Hacks <judges@lakesidehacks.example>",
        "maya@example.com",
        "Thanks",
    )
    m["Date"] = "Sat, 03 Oct 2026 18:00:00 +0000"
    m.set_content("Hi Maya, thank you for judging the systems track at Lakeside Hacks 2026. Your scores picked "
                  "the 12 winning teams out of 340 submissions.")  # fmt: skip
    m.add_alternative("<p>Hi Maya, thank you for <b>judging</b>.</p>", subtype="html")
    m.add_attachment(b"%PDF-1.4", maintype="application", subtype="pdf", filename="certificate.pdf")
    eml = "\n".join(_render(ws, "thanks.eml", bytes(m)).texts)
    assert (
        "From: Lakeside Hacks <judges@lakesidehacks.example>" in eml and "Attachments: certificate.pdf" in eml
    )
    assert "Content-Type" not in eml and "boundary" not in eml and "=\n" not in eml  # not the raw MIME source
    assert "Re-rendered as text from" in eml and "attorney export ZIP" in eml
    assert packet.find_page("Your scores picked the 12 winning teams out of 340 submissions.", [eml]) == 1

    html = "\n".join(_render(ws, "judges.html", b"<html><script>x()</script><h1>Judges</h1><p>Maya Chen &amp; "
                                                b"Sam Lee</p></html>").texts)  # fmt: skip
    assert "Judges\nMaya Chen & Sam Lee" in html and "x()" not in html

    docx = _render(ws, "letter.docx", packet.docx(packet.gather(ws)))  # a real Word document
    assert "Re-rendered as text from" in docx.texts[0] and "Exhibit index" in "\n".join(docx.texts)
    assert "PK" not in "".join(docx.texts)  # never the zip's bytes

    blob = "\n".join(_render(ws, "sheet.xlsx", b"PK\x03\x04 binary").texts)
    assert "can't show as pages" in blob and "PK" not in blob

    buf = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buf, "PNG")
    img = _render(ws, "photo.png", buf.getvalue())
    assert (
        len(img.texts) == 1 and "can't be searched" in PdfReader(io.BytesIO(img.pdf)).pages[0].extract_text()
    )


def test_a_quote_across_a_wrapped_line_is_still_found(ws):
    long = "word " * 15 + "Maya Chen served as a judge for the systems track finals at Lakeside Hacks 2026."
    it = _render(ws, "note.txt", long.encode())
    assert packet.find_page("Maya Chen served as a judge for the systems track finals at Lakeside Hacks 2026.",
                            it.texts) == 1  # fmt: skip
