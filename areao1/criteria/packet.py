"""The review packet (ADR 0020): the case organized for an attorney to review. "Build review packet", never
"generate petition"; every page and every generated paragraph is labeled "Draft for attorney review".

- Counted exhibits are numbered per criterion (``C<n>-<nn>``: n is the criterion's place in the active profile, nn
  the exhibit's order in it by date, then title). Self-reported material never enters the packet as evidence.
- A table of contents and a per-criterion exhibit index with each exhibit's page range in the review PDF.
- The claim -> exhibit -> page/quote matrix: for every approved claim an exhibit cites, the page the quote is on
  (found by searching the exhibit's text; "not found" when it isn't, never guessed).
- An outline drafted only from approved claims, one plain sentence per claim from a template for its evidence type
  (sentences.py), each ending with its exhibit and a footnote that gives the page and the quote. Claim ids appear only
  in matrix.csv (and the machine-readable provenance); any eligibility verdict is dropped (grounding).
- The open preflight issues (ADR 0018) and the final-merits summary (ADR 0019).

Outputs go to ``exports/packet-<as of>-<input hash>/``: packet.docx (Office Open XML written here), packet.pdf
(continuous "Page n of N", exhibits included), matrix.csv, preflight.json, provenance.json, provenance.prov.json,
manifest.json and attorney-export.zip. Same inputs, same bytes: ordering is fixed, dates come from the inputs (the
latest decision), ZIP entries carry fixed timestamps, and ReportLab runs in invariant mode.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import zipfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from areao1.core import clock
from areao1.core.models import NON_EVIDENTIARY_TIERS, Claim, Exhibit
from areao1.criteria import sentences
from areao1.criteria.grounding import CITE, LABEL, is_verdict

IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
TEXTS = {".md", ".txt", ".html", ".htm", ".csv", ".eml", ".json"}
FIXED_ZIP_TIME = (1980, 1, 1, 0, 0, 0)
FILES = ("packet.docx", "packet.pdf", "matrix.csv", "preflight.json", "provenance.json", "provenance.prov.json",
         "manifest.json", "attorney-export.zip")  # fmt: skip


@dataclass
class Item:
    """A numbered exhibit and its pages as they'll appear in the review PDF."""

    number: str
    exhibit: Exhibit
    criterion: str
    pdf: bytes = b""
    texts: list[str] = field(default_factory=list)  # one per content page
    start: int = 0  # packet page of its cover sheet (1-based)

    @property
    def pages(self) -> int:
        return 1 + len(self.texts)  # the cover sheet, then the content

    @property
    def range(self) -> str:
        return f"{self.start}–{self.start + self.pages - 1}" if self.pages > 1 else str(self.start)


@dataclass
class Row:
    """One line of the matrix."""

    item: Item
    claim: Claim
    subject: str
    page: int | None  # within the exhibit's content, 1-based

    @property
    def packet_page(self) -> int | None:
        return self.item.start + self.page if self.page else None

    def fact(self, person: str) -> sentences.Fact:
        e = self.item.exhibit
        return sentences.Fact(person=sentences.first_name(person), predicate=self.claim.predicate,
                              value=self.claim.value, evidence_type=e.evidence_type, exhibit=self.item.number,
                              excerpt=self.claim.excerpt, on=self.claim.event_date or e.date,
                              org=e.organization.strip(), work=self.subject)  # fmt: skip

    def where(self) -> str:
        """The footnote: where the quote is, and the quote."""
        if self.page:
            at = f"Exhibit {self.item.number}, page {self.page}" + (f" (packet page {self.packet_page})"
                                                                     if self.item.start else "")  # fmt: skip
        else:
            at = f"Exhibit {self.item.number} (the quote wasn't found in its text)"
        return f"{at}: “{sentences._clip(self.claim.excerpt)}”"


# ------------------------------------------------------------------------------------------------------- inputs


def number(ws: Any) -> list[Item]:
    """Counted exhibits, numbered per criterion in the active profile's order. Self-reported never appears."""
    board, profile = ws.scoreboard(), ws.profile()
    counted = {i for c in board.criteria for i in c.exhibit_ids}
    exhibits = [
        e for e in ws.exhibits().exhibits if e.id in counted and e.source_tier not in NON_EVIDENTIARY_TIERS
    ]
    items = []
    for n, crit in enumerate(profile.criteria, 1):
        mine = sorted(
            (e for e in exhibits if e.criterion == crit.id), key=lambda e: (e.date, e.title.lower(), e.id)
        )
        items += [Item(number=f"C{n}-{k:02d}", exhibit=e, criterion=crit.short_label or crit.label)
                  for k, e in enumerate(mine, 1)]  # fmt: skip
    return items


def _norm(text: str) -> str:
    text = re.sub(r"-\s*\n\s*", "", text)  # words broken across lines
    return re.sub(r"\s+", " ", text).strip().lower()


def find_page(quote: str, texts: list[str]) -> int | None:
    q = _norm(quote)
    if len(q) < 4:
        return None
    for i, t in enumerate(texts, 1):
        if q in _norm(t):
            return i
    return None


def matrix(ws: Any, items: list[Item]) -> list[Row]:
    """Every approved, current claim each exhibit cites, with the page its quote is on. A superseded value isn't
    listed (preflight flags an exhibit that still cites one)."""
    statuses = ws.memory.statuses()
    current = {c.id for c in ws.memory._current_claims().values()}
    claims = {c.id: c for c in ws.memory.claims()}
    names = {e.id: e.name for e in ws.memory.entities()}
    cites: dict[str, list[str]] = {}
    for edge in ws.memory.edges():
        if edge.type == "CITES":
            cites.setdefault(edge.src, []).append(edge.dst)
    rows = []
    for it in items:
        ids = list(dict.fromkeys([*it.exhibit.claim_ids, *cites.get(it.exhibit.id, [])]))
        for cid in sorted(ids, key=lambda i: (claims[i].predicate, i) if i in claims else ("", i)):
            c = claims.get(cid)
            if c is None or statuses.get(cid) != "approved" or cid not in current:
                continue
            rows.append(
                Row(
                    item=it,
                    claim=c,
                    subject=names.get(c.subject, c.subject),
                    page=find_page(c.excerpt, it.texts),
                )
            )
    return rows


def _value(v: Any) -> str:
    return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)


def outline(items: list[Item], rows: list[Row], person: str = "") -> tuple[str, list[str], list[str]]:
    """An outline from approved claims only: one sentence per claim, from its evidence type's template, ending with
    ``[claim id]`` (the renderers turn it into a footnote). Returns (text, cited, dropped)."""
    lines = [f"# Outline ({LABEL.lower()})", ""]
    by_crit: dict[str, list[Row]] = {}
    for r in rows:
        by_crit.setdefault(r.item.criterion, []).append(r)
    cited, dropped = [], []
    for crit, mine in by_crit.items():
        lines.append(f"## {crit}")
        for r in mine:
            text = sentences.sentence(r.fact(person))
            if is_verdict(text):
                dropped.append(text)  # never an eligibility verdict, even quoted
                continue
            lines.append(f"{text} [{r.claim.id}]")
            cited.append(r.claim.id)
        lines.append("")
    return "\n".join(lines).strip(), cited, dropped


def footnoted(outline_text: str, rows: list[Row]) -> list[tuple[str, str, list[str]]]:
    """The outline as (kind, text, footnotes) lines: kind is "h2" or "p"; each sentence's claim ids become
    footnotes saying where the quote is. Numbering runs through the outline."""
    by_id = {r.claim.id: r for r in rows}
    out: list[tuple[str, str, list[str]]] = []
    for line in outline_text.splitlines():
        if line.startswith("## "):
            out.append(("h2", line[3:], []))
        elif line.strip() and not line.startswith("# "):
            ids = [i.strip() for m in CITE.finditer(line) for i in m.group(1).split(",")]
            out.append(("p", CITE.sub("", line).rstrip(), [by_id[i].where() for i in ids if i in by_id]))
    return out


def grouped(issues: list[dict[str, Any]], most: int = 3) -> list[dict[str, Any]]:
    """The issues for a reader: a low-severity rule with more than ``most`` issues becomes one row naming the first
    few (preflight.json keeps every one)."""
    by_rule: dict[str, list[dict[str, Any]]] = {}
    for i in issues:
        by_rule.setdefault(i.get("kind", i["id"]), []).append(i)
    out: list[dict[str, Any]] = []
    for i in issues:
        same = by_rule[i.get("kind", i["id"])]
        if i["severity"] != "low" or len(same) <= most:
            out.append(i)
        elif i is same[0]:
            names = "; ".join(x["title"] for x in same[:most])
            out.append({"severity": "low", "title": f"{len(same)} similar issues",
                        "detail": f"{names}; and {len(same) - most} more (all in preflight.json)."})  # fmt: skip
    return out


def humanize(slug: str) -> str:
    return slug.replace("_", " ")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def as_of(ws: Any, items: list[Item]) -> datetime:
    """The packet's date comes from its inputs: the latest review decision or accepted exhibit."""
    times = [d.at for d in ws.memory.decisions()] + [it.exhibit.accepted_at for it in items]
    return max(times) if times else datetime(2000, 1, 1, tzinfo=UTC)


# ------------------------------------------------------------------------------------------------ exhibit pages


def _page_count(data: bytes) -> int:
    from pypdf import PdfReader

    return len(PdfReader(io.BytesIO(data)).pages)


def _pdf_texts(data: bytes) -> list[str]:
    from pypdf import PdfReader

    return [p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages]


def _typeset(title: str, text: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Preformatted, SimpleDocTemplate

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=letter, invariant=1, title=title, author="Area O1",
                            topMargin=54, bottomMargin=54)  # fmt: skip
    style = getSampleStyleSheet()["Code"]
    style.fontSize, style.leading = 8.5, 11
    wrapped = "\n".join(_wrap(line, 88) for line in text.replace("\t", "    ").splitlines()) or " "
    doc.build([Preformatted(wrapped, style)])
    return buf.getvalue()


def _wrap(line: str, width: int) -> str:
    return "\n".join(line[i : i + width] for i in range(0, max(len(line), 1), width))


def _image(path: Path) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter, invariant=1)
    img = ImageReader(str(path))
    iw, ih = img.getSize()
    w, h = letter
    scale = min((w - 72) / iw, (h - 108) / ih, 1.0)
    c.drawImage(img, (w - iw * scale) / 2, (h - ih * scale) / 2, iw * scale, ih * scale)
    c.showPage()
    c.save()
    return buf.getvalue()


def render_exhibit(ws: Any, it: Item) -> None:
    """The exhibit's content as PDF pages, and the text of each page (to find quotes on)."""
    path = ws.root / it.exhibit.file
    ext = path.suffix.lower()
    try:
        if not path.is_file():
            raise FileNotFoundError(it.exhibit.file)
        if ext == ".pdf":
            data = path.read_bytes()
            texts = _pdf_texts(data)
            if not texts:
                raise ValueError("no pages")
            it.pdf, it.texts = data, texts
            return
        if ext in IMAGES:
            it.pdf, it.texts = _image(path), [""]
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        if ext in (".html", ".htm"):
            text = re.sub(
                r"\s+\n", "\n", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style).*?</\1>", "", text))
            )
        it.pdf = _typeset(it.exhibit.title, text)
        it.texts = _pdf_texts(it.pdf)
        it.texts = it.texts or [text]
    except Exception as exc:  # a missing or unreadable file is shown, not skipped
        it.pdf = _typeset(it.exhibit.title, f"This exhibit's file couldn't be included ({type(exc).__name__}): "
                                            f"{it.exhibit.file}")  # fmt: skip
        it.texts = _pdf_texts(it.pdf)


# ---------------------------------------------------------------------------------------------- the front matter


@dataclass
class Packet:
    items: list[Item]
    rows: list[Row]
    outline: str
    dropped: list[str]
    issues: list[dict[str, Any]]
    merits: Any
    person: str
    profile: str
    as_of: datetime
    input_hash: str = ""


def _styles() -> Any:
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet

    ss = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle(
            "h1", parent=ss["Heading1"], fontName="Helvetica-Bold", fontSize=18, spaceAfter=10
        ),
        "h2": ParagraphStyle(
            "h2", parent=ss["Heading2"], fontName="Helvetica-Bold", fontSize=13, spaceAfter=6
        ),
        "body": ParagraphStyle("body", parent=ss["BodyText"], fontName="Helvetica", fontSize=9.5, leading=13),
        "small": ParagraphStyle("small", parent=ss["BodyText"], fontName="Helvetica", fontSize=8, leading=10),
        "label": ParagraphStyle(
            "label", parent=ss["BodyText"], fontName="Helvetica-Bold", fontSize=11, leading=14
        ),
    }


SECTIONS = ("Contents", "Exhibit index", "Claim, exhibit, page and quote", "Outline", "Final merits",
            "Open preflight issues")  # fmt: skip


def _front(p: Packet, toc: dict[str, int], offset: int) -> tuple[bytes, dict[str, int]]:
    """The cover, contents, index, matrix, outline, final merits and issues. ``toc`` holds each section's page from
    the previous pass; returns the PDF and this pass's pages."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    st = _styles()
    found: dict[str, int] = {}

    class Doc(SimpleDocTemplate):
        def afterFlowable(self, flowable: Any) -> None:
            name = getattr(flowable, "_section", None)
            if name:
                found.setdefault(name, self.page)

    def section(name: str) -> Any:
        h = Paragraph(escape(name), st["h1"])
        h._section = name
        return h

    def para(text: str, style: str = "body") -> Any:
        return Paragraph(escape(text), st[style])

    def table(head: list[str], body: list[list[str]], widths: list[float]) -> Any:
        data = [[Paragraph(f"<b>{escape(h)}</b>", st["small"]) for h in head]]
        data += [[Paragraph(escape(str(c)), st["small"]) for c in r] for r in body]
        t = Table(data, colWidths=widths, repeatRows=1)
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.black), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke)]))  # fmt: skip
        return t

    flow: list[Any] = [Spacer(1, 120), Paragraph("Review packet", st["h1"]), para(LABEL, "label"), Spacer(1, 12),
                       para(f"{p.person or 'The person'} · {p.profile}"),
                       para(f"As of {clock.local_date(p.as_of).isoformat()} · {len(p.items)} numbered exhibits · "
                            f"{len(p.rows)} cited claims · {len(p.issues)} open preflight issues"),
                       para(f"Input hash {p.input_hash}", "small"), Spacer(1, 18),
                       para("Built by Area O1 from the person's workspace for attorney review. It is not a petition, "
                            "it is not legal advice, and it makes no eligibility determination.", "small"),
                       PageBreak(), section("Contents")]  # fmt: skip
    for name in SECTIONS[1:]:
        page = toc.get(name)
        flow.append(para(f"{name} {'.' * 8} page {page}" if page else name))
    flow.append(para(f"Exhibits {'.' * 8} pages {p.items[0].start}–{p.items[-1].start + p.items[-1].pages - 1}"
                     if p.items and p.items[0].start else "Exhibits"))  # fmt: skip
    flow += [PageBreak(), section("Exhibit index")]
    crits = list(dict.fromkeys(it.criterion for it in p.items))
    if not crits:
        flow.append(para("No counted exhibits yet."))
    for crit in crits:
        flow.append(Paragraph(escape(crit), st["h2"]))
        flow.append(table(["No.", "Title", "Date", "Type", "Stage", "Pages"],
                          [[it.number, it.exhibit.title, it.exhibit.date.isoformat(), humanize(it.exhibit.evidence_type),
                            it.exhibit.stage or "", it.range if it.start else ""] for it in p.items if it.criterion == crit],
                          [48, 190, 62, 92, 60, 52]))  # fmt: skip
        flow.append(Spacer(1, 10))
    flow += [PageBreak(), section("Claim, exhibit, page and quote"),
             para("Every approved claim an exhibit cites, the page its quote is on in the exhibit and in this packet, "
                  "and the quote itself. \"Not found\" means the quote isn't in the exhibit's text (a scan, an image); "
                  "the page is never guessed.", "small"), Spacer(1, 6)]  # fmt: skip
    flow.append(table(["Claim", "Exhibit", "Page", "Quote"],
                      [[sentences.label(r.fact(p.person)), r.item.number, f"p. {r.page} · packet {r.packet_page}" if r.page and r.item.start else
                        (f"p. {r.page}" if r.page else "not found"), r.claim.excerpt[:400]] for r in p.rows]
                      or [["No approved claims are cited yet.", "", "", ""]],
                      [170, 50, 70, 214]))  # fmt: skip
    flow += [PageBreak(), section("Outline"), para(LABEL, "label"),
             para("Drafted from approved claims only. Each sentence ends with the claims behind it; anything else was "
                  "left out. A starting point for the attorney to rewrite.", "small"), Spacer(1, 6)]  # fmt: skip
    notes: list[str] = []

    def flush() -> None:
        for k, note in enumerate(notes, len(seen) - len(notes) + 1):
            flow.append(Paragraph(f"<super>{k}</super> {escape(note)}", st["small"]))
        notes.clear()

    seen: list[str] = []
    for kind, text, foot in footnoted(p.outline, p.rows):
        if kind == "h2":
            flush()
            flow.append(Paragraph(escape(text), st["h2"]))
            continue
        marks = []
        for note in foot:
            seen.append(note)
            notes.append(note)
            marks.append(str(len(seen)))
        flow.append(
            Paragraph(escape(text) + (f"<super>{','.join(marks)}</super>" if marks else ""), st["body"])
        )
    flush()
    flow += [PageBreak(), section("Final merits")]
    if p.merits is not None:
        flow.append(para(p.merits.framing, "small"))
        flow.append(table(["Theme", "Status", "Why", "Rule"],
                          [[t.label, t.status, t.why, t.rule] for t in p.merits.themes], [100, 52, 190, 162]))  # fmt: skip
        if p.merits.standard:
            flow.append(Spacer(1, 8))
            flow.append(table(["The standard", "Source", "Check"],
                              [[s.text, s.title or s.source_id, s.status] for s in p.merits.standard], [262, 182, 60]))  # fmt: skip
    flow += [PageBreak(), section("Open preflight issues")]
    flow.append(table(["Severity", "Issue", "Detail"],
                      [[i["severity"], i["title"], i.get("detail", "")] for i in grouped(p.issues)]
                      or [["", "No open issues.", ""]], [56, 170, 278]))  # fmt: skip
    buf = io.BytesIO()
    doc = Doc(buf, pagesize=letter, invariant=1, title="Review packet", author="Area O1", subject=LABEL,
              creator="Area O1", topMargin=54, bottomMargin=60)  # fmt: skip
    doc.build(flow)
    return buf.getvalue(), found


def _cover_sheet(it: Item) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter, invariant=1)
    w, h = letter
    c.setFont("Helvetica-Bold", 28)
    c.drawString(72, h - 160, f"Exhibit {it.number}")
    c.setFont("Helvetica", 13)
    y = h - 200
    e = it.exhibit
    for line in (e.title, it.criterion, f"Date {e.date.isoformat()}" + (" (unconfirmed)" if e.date_unconfirmed else ""),
                 f"Type {humanize(e.evidence_type)}" + (f" · stage {e.stage}" if e.stage else ""), e.organization or "",
                 e.source_url or ""):  # fmt: skip
        if line:
            c.drawString(72, y, line[:95])
            y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.drawString(72, 120, LABEL)
    c.showPage()
    c.save()
    return buf.getvalue()


def _stamp(writer: Any) -> None:
    """'Draft for attorney review · Page n of N' on every page, exhibits included."""
    from pypdf import PdfReader
    from reportlab.pdfgen import canvas

    total = len(writer.pages)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, invariant=1)
    for i, page in enumerate(writer.pages, 1):
        w, h = float(page.mediabox.width), float(page.mediabox.height)
        c.setPageSize((w, h))
        c.setFont("Helvetica", 8)
        c.drawString(36, 22, LABEL)
        c.drawRightString(w - 36, 22, f"Page {i} of {total}")
        c.showPage()
    c.save()
    overlay = PdfReader(io.BytesIO(buf.getvalue()))
    for page, mark in zip(writer.pages, overlay.pages, strict=True):
        page.merge_page(mark)


def review_pdf(p: Packet) -> bytes:
    from pypdf import PdfReader, PdfWriter

    toc: dict[str, int] = {}
    front, pages = b"", 0
    for _ in range(4):  # page numbers settle in two passes; the guard stops a pathological loop
        front, found = _front(p, toc, 0)
        n = len(PdfReader(io.BytesIO(front)).pages)
        start = n + 1
        changed = found != toc or n != pages
        for it in p.items:
            it.start = start
            start += it.pages
        toc, pages = found, n
        if not changed:
            break
    writer = PdfWriter()
    writer.append(PdfReader(io.BytesIO(front)))
    for it in p.items:
        writer.append(PdfReader(io.BytesIO(_cover_sheet(it))))
        writer.append(PdfReader(io.BytesIO(it.pdf)))
    _stamp(writer)
    writer.add_metadata({"/Title": "Review packet", "/Subject": LABEL, "/Producer": "Area O1",
                         "/Creator": "Area O1"})  # fmt: skip
    buf = io.BytesIO()
    writer.write(buf)
    return _pin_id(buf.getvalue(), p.input_hash)


def _pin_id(pdf: bytes, seed: str) -> bytes:
    """pypdf may write a random file /ID; pin it to the input hash so rebuilds are byte-identical."""
    fixed = hashlib.md5(seed.encode(), usedforsecurity=False).hexdigest()
    return re.sub(
        rb"/ID \[ ?<[0-9a-fA-F]+> ?<[0-9a-fA-F]+> ?\]", f"/ID [ <{fixed}> <{fixed}> ]".encode(), pdf
    )


# ---------------------------------------------------------------------------------------------------------- docx


def _run(text: str, bold: bool = False) -> str:
    props = "<w:rPr><w:b/></w:rPr>" if bold else ""
    return f'<w:r>{props}<w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def _p(text: str, style: str = "", bold: bool = False) -> str:
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    return f"<w:p>{ppr}{_run(text, bold)}</w:p>"


def _tbl(head: list[str], rows: list[list[str]]) -> str:
    border = "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="000000"/>'
                     for s in ("top", "left", "bottom", "right", "insideH", "insideV"))  # fmt: skip
    out = [f'<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="5000" w:type="pct"/>'
           f"<w:tblBorders>{border}</w:tblBorders></w:tblPr><w:tblGrid>"
           + "".join("<w:gridCol/>" for _ in head) + "</w:tblGrid>"]  # fmt: skip
    for i, r in enumerate([head, *rows]):
        cells = "".join(f'<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/></w:tcPr>{_p(str(c), bold=i == 0)}</w:tc>'
                        for c in r)  # fmt: skip
        out.append(f"<w:tr>{cells}</w:tr>")
    out.append("</w:tbl>")
    return "".join(out)


W_NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" ' \
       'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'  # fmt: skip


def docx(p: Packet) -> bytes:
    """An editable Word document (Office Open XML, written directly): the front matter of the packet. Every page
    carries the label in its header and "Page n of N" in its footer."""
    body = [_p("Review packet", "Title"), _p(LABEL, "Label"),
            _p(f"{p.person or 'The person'} · {p.profile} · as of {clock.local_date(p.as_of).isoformat()}"),
            _p(f"Input hash {p.input_hash}"),
            _p("Built by Area O1 for attorney review. It is not a petition, it is not legal advice, and it makes no "
               "eligibility determination."), _p("Exhibit index", "Heading1")]  # fmt: skip
    for crit in dict.fromkeys(it.criterion for it in p.items):
        body.append(_p(crit, "Heading2"))
        body.append(_tbl(["No.", "Title", "Date", "Type", "Stage", "Pages"],
                         [[it.number, it.exhibit.title, it.exhibit.date.isoformat(), humanize(it.exhibit.evidence_type),
                           it.exhibit.stage or "", it.range] for it in p.items if it.criterion == crit]))  # fmt: skip
    body.append(_p("Claim, exhibit, page and quote", "Heading1"))
    body.append(_tbl(["Claim", "Exhibit", "Page", "Quote"],
                     [[sentences.label(r.fact(p.person)), r.item.number, f"p. {r.page} (packet {r.packet_page})" if r.page else "not found", r.claim.excerpt]
                      for r in p.rows]))  # fmt: skip
    body += [_p("Outline", "Heading1"), _p(LABEL, "Label")]
    notes: list[str] = []
    for kind, text, foot in footnoted(p.outline, p.rows):
        if kind == "h2":
            body.append(_p(text, "Heading2"))
            continue
        refs = ""
        for note in foot:
            notes.append(note)
            refs += f'<w:r><w:rPr><w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteReference w:id="{len(notes)}"/></w:r>'
        body.append(f"<w:p>{_run(text)}{refs}</w:p>")
    body.append(_p("Final merits", "Heading1"))
    if p.merits is not None:
        body.append(_p(p.merits.framing))
        body.append(
            _tbl(
                ["Theme", "Status", "Why", "Rule"],
                [[t.label, t.status, t.why, t.rule] for t in p.merits.themes],
            )
        )
    body.append(_p("Open preflight issues", "Heading1"))
    body.append(
        _tbl(
            ["Severity", "Issue", "Detail"],
            [[i["severity"], i["title"], i.get("detail", "")] for i in grouped(p.issues)],
        )
    )
    sect = ('<w:sectPr><w:headerReference w:type="default" r:id="rIdHeader"/>'
            '<w:footerReference w:type="default" r:id="rIdFooter"/><w:pgSz w:w="12240" w:h="15840"/>'
            '<w:pgMar w:top="1080" w:right="1080" w:bottom="1080" w:left="1080" w:header="540" w:footer="540" '
            'w:gutter="0"/></w:sectPr>')  # fmt: skip
    document = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {W_NS}><w:body>'
                + "".join(body) + sect + "</w:body></w:document>")  # fmt: skip
    header = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:hdr {W_NS}>{_p(LABEL, "Label")}</w:hdr>'
    )
    footer = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {W_NS}><w:p><w:pPr><w:jc w:val="right"/>'
              '</w:pPr>' + _run("Page ") + '<w:fldSimple w:instr="PAGE">' + _run("1") + "</w:fldSimple>" + _run(" of ")
              + '<w:fldSimple w:instr="NUMPAGES">' + _run("1") + "</w:fldSimple></w:p></w:ftr>")  # fmt: skip

    footnotes = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:footnotes {W_NS}>'
                 '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
                 '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r>'
                 "</w:p></w:footnote>"
                 + "".join(f'<w:footnote w:id="{k}"><w:p><w:pPr><w:pStyle w:val="FootnoteText"/></w:pPr><w:r><w:rPr>'
                           f'<w:rStyle w:val="FootnoteReference"/></w:rPr><w:footnoteRef/></w:r>{_run(" " + note)}'
                           "</w:p></w:footnote>" for k, note in enumerate(notes, 1))
                 + "</w:footnotes>")  # fmt: skip
    settings = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings {W_NS}><w:footnotePr>'
                '<w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr></w:settings>')  # fmt: skip

    def style(sid: str, name: str, size: int, bold: bool) -> str:
        b = "<w:b/>" if bold else ""
        return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="Normal"/>'
                f'<w:qFormat/><w:pPr><w:spacing w:before="200" w:after="80"/></w:pPr><w:rPr>{b}<w:sz w:val="{size}"/>'
                "</w:rPr></w:style>")  # fmt: skip

    styles = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {W_NS}>'
              '<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri"/><w:sz w:val="20"/>'
              '</w:rPr></w:rPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
              '<w:name w:val="Normal"/><w:qFormat/></w:style>' + style("Title", "Title", 44, True)
              + style("Heading1", "heading 1", 30, True) + style("Heading2", "heading 2", 24, True)
              + style("Label", "Label", 22, True)
              + '<w:style w:type="paragraph" w:styleId="FootnoteText"><w:name w:val="footnote text"/>'
              '<w:basedOn w:val="Normal"/><w:rPr><w:sz w:val="16"/></w:rPr></w:style>'
              '<w:style w:type="character" w:styleId="FootnoteReference"><w:name w:val="footnote reference"/>'
              '<w:rPr><w:vertAlign w:val="superscript"/></w:rPr></w:style>'
              + '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/></w:style></w:styles>')  # fmt: skip
    rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    parts = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
            '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
            '<Override PartName="/word/footnotes.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
            '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{rel}/officeDocument" Target="word/document.xml"/></Relationships>'
        ),
        "word/_rels/document.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rIdStyles" Type="{rel}/styles" Target="styles.xml"/>'
            f'<Relationship Id="rIdHeader" Type="{rel}/header" Target="header1.xml"/>'
            f'<Relationship Id="rIdFooter" Type="{rel}/footer" Target="footer1.xml"/>'
            f'<Relationship Id="rIdFootnotes" Type="{rel}/footnotes" Target="footnotes.xml"/>'
            f'<Relationship Id="rIdSettings" Type="{rel}/settings" Target="settings.xml"/></Relationships>'
        ),
        "word/document.xml": document,
        "word/styles.xml": styles,
        "word/header1.xml": header,
        "word/footer1.xml": footer,
        "word/footnotes.xml": footnotes,
        "word/settings.xml": settings,
    }
    return _zip({k: v.encode("utf-8") for k, v in parts.items()})


def _zip(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name, data in files.items():  # insertion order: [Content_Types].xml first, as Word expects
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIME)
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            z.writestr(info, data)
    return buf.getvalue()


# ---------------------------------------------------------------------------------------------------- provenance


def provenance(ws: Any, rows: list[Row]) -> tuple[dict[str, Any], dict[str, Any]]:
    """The cited claims with their observations, decisions and edges; and the same as W3C PROV-JSON."""
    ids = {r.claim.id for r in rows}
    claims = [r.claim for r in rows]
    claims = list({c.id: c for c in claims}.values())
    obs_ids = {c.observation_id for c in claims}
    observations = [o for o in ws.memory.observations() if o.id in obs_ids]
    decisions = [d for d in ws.memory.decisions() if d.claim_id in ids]
    exhibit_of = {r.item.exhibit.id: r.item.number for r in rows}
    edges = [e for e in ws.memory.edges() if e.src in ids or e.dst in ids]
    plain = {"claims": [c.model_dump(mode="json") for c in claims],
             "observations": [o.model_dump(mode="json") for o in observations],
             "decisions": [d.model_dump(mode="json") for d in decisions],
             "edges": [e.model_dump(mode="json") for e in edges], "exhibits": exhibit_of}  # fmt: skip
    prov: dict[str, Any] = {
        "prefix": {"areao1": "https://ris3abh.github.io/areao1/ns#", "prov": "http://www.w3.org/ns/prov#"},
        "entity": {}, "activity": {}, "agent": {"areao1:you": {"prov:type": "prov:Person"}},
        "wasDerivedFrom": {}, "used": {}, "wasAssociatedWith": {}, "wasInfluencedBy": {},
    }  # fmt: skip
    for o in observations:
        prov["entity"][f"areao1:{o.id}"] = {"prov:type": "areao1:Observation", "prov:location": o.source_url,
                                            "areao1:sha256": o.sha256, "prov:generatedAtTime": o.captured_at.isoformat()}  # fmt: skip
    for c in claims:
        prov["entity"][f"areao1:{c.id}"] = {"prov:type": "areao1:Claim", "areao1:predicate": c.predicate,
                                            "prov:value": _value(c.value), "areao1:excerpt": c.excerpt}  # fmt: skip
        prov["wasDerivedFrom"][f"_:d-{c.id}"] = {"prov:generatedEntity": f"areao1:{c.id}",
                                                 "prov:usedEntity": f"areao1:{c.observation_id}"}  # fmt: skip
    for d in decisions:
        prov["activity"][f"areao1:{d.id}"] = {"prov:type": "areao1:Review", "areao1:decision": d.decision,
                                              "prov:startTime": d.at.isoformat()}  # fmt: skip
        prov["used"][f"_:u-{d.id}"] = {
            "prov:activity": f"areao1:{d.id}",
            "prov:entity": f"areao1:{d.claim_id}",
        }
        prov["wasAssociatedWith"][f"_:a-{d.id}"] = {
            "prov:activity": f"areao1:{d.id}",
            "prov:agent": "areao1:you",
        }
    for r in rows:
        ex = f"areao1:exhibit-{r.item.number}"
        prov["entity"][ex] = {"prov:type": "areao1:Exhibit", "prov:label": r.item.exhibit.title}
        prov["wasInfluencedBy"][f"_:i-{r.item.number}-{r.claim.id}"] = {"prov:influencee": ex,
                                                                         "prov:influencer": f"areao1:{r.claim.id}"}  # fmt: skip
    return plain, prov


# --------------------------------------------------------------------------------------------------------- build


def _dump(obj: Any) -> bytes:
    return (json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False, default=str) + "\n").encode("utf-8")


def gather(ws: Any, vault: Any = None) -> Packet:
    from areao1.criteria import merits as merits_view
    from areao1.criteria import preflight

    items = number(ws)
    for it in items:
        render_exhibit(ws, it)
    rows = matrix(ws, items)
    text, _, dropped = outline(items, rows, ws.person().name)
    issues = [i for i in preflight.run(ws, save=False)["issues"] if not i.get("dismissed")]
    try:
        merits = merits_view.report(ws, vault)
    except Exception:  # final merits is a summary here; its absence never stops the packet
        merits = None
    p = Packet(items=items, rows=rows, outline=text, dropped=dropped, issues=issues, merits=merits,
               person=ws.person().name, profile=ws.profile().name, as_of=as_of(ws, items))  # fmt: skip
    p.input_hash = input_hash(ws, p)
    return p


def input_hash(ws: Any, p: Packet) -> str:
    inputs = {
        "profile": ws.profile().id,
        "person": p.person,
        "exhibits": [{"number": it.number, **it.exhibit.model_dump(mode="json", exclude={"accepted_at"}),
                      "sha256": _sha(ws.root / it.exhibit.file)} for it in p.items],
        "claims": [{"id": r.claim.id, "value": r.claim.value, "excerpt": r.claim.excerpt, "exhibit": r.item.number}
                   for r in p.rows],
        "issues": [{"id": i["id"], "title": i["title"], "detail": i.get("detail", "")} for i in p.issues],
        "merits": p.merits.model_dump(mode="json") if p.merits is not None else None,
        "as_of": p.as_of.isoformat(),
    }  # fmt: skip
    return hashlib.sha256(json.dumps(inputs, sort_keys=True, default=str).encode()).hexdigest()


def matrix_csv(rows: list[Row], person: str = "") -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["exhibit", "exhibit_title", "claim_id", "subject", "predicate", "value", "exhibit_page", "packet_page",
                "quote", "sentence"])  # fmt: skip
    for r in rows:
        w.writerow([r.item.number, r.item.exhibit.title, r.claim.id, r.subject, r.claim.predicate, _value(r.claim.value),
                    r.page or "not found", r.packet_page or "", r.claim.excerpt,
                    sentences.label(r.fact(person))])  # fmt: skip
    return buf.getvalue().encode("utf-8")


def build(ws: Any, vault: Any = None) -> dict[str, Any]:
    """Build the packet into exports/packet-<as of>-<hash>/ and return its manifest."""
    p = gather(ws, vault)
    pdf = review_pdf(p)  # sets each exhibit's pages first; the .docx index uses them
    files: dict[str, bytes] = {"packet.docx": docx(p), "packet.pdf": pdf, "matrix.csv": matrix_csv(p.rows, p.person),
                               "preflight.json": _dump(p.issues)}  # fmt: skip
    plain, prov = provenance(ws, p.rows)
    files["provenance.json"] = _dump(plain)
    files["provenance.prov.json"] = _dump(prov)
    name = f"packet-{clock.local_date(p.as_of).isoformat()}-{p.input_hash[:8]}"
    manifest = {
        "name": name, "label": LABEL, "as_of": p.as_of.isoformat(), "input_hash": p.input_hash,
        "profile": ws.profile().id, "exhibits": [{"number": it.number, "id": it.exhibit.id, "title": it.exhibit.title,
                                                  "pages": it.range} for it in p.items],
        "claims": len(p.rows), "open_issues": len(p.issues), "dropped_sentences": len(p.dropped),
        "pages": _page_count(pdf),
        "files": {k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
    }  # fmt: skip
    files["manifest.json"] = _dump(manifest)
    bundle = {k: files[k] for k in ("packet.docx", "packet.pdf", "matrix.csv", "preflight.json", "provenance.json",
                                    "provenance.prov.json", "manifest.json")}  # fmt: skip
    for it in p.items:
        src = ws.root / it.exhibit.file
        if src.is_file():
            bundle[f"exhibits/{it.number}_{src.name}"] = src.read_bytes()
    files["attorney-export.zip"] = _zip(bundle)
    out = ws.root / "exports" / name
    out.mkdir(parents=True, exist_ok=True)
    for k, v in files.items():
        (out / k).write_bytes(v)
    return manifest


def builds(ws: Any) -> list[dict[str, Any]]:
    """Packets built so far, newest first."""
    root = ws.root / "exports"
    out = []
    for d in sorted(root.glob("packet-*"), reverse=True) if root.is_dir() else []:
        m = d / "manifest.json"
        if m.is_file():
            data = json.loads(m.read_text(encoding="utf-8"))
            data["files_present"] = [f for f in FILES if (d / f).is_file()]
            out.append(data)
    return out


def built_file(ws: Any, name: str, filename: str) -> Path:
    if not re.fullmatch(r"packet-\d{4}-\d{2}-\d{2}-[0-9a-f]{8}", name) or filename not in FILES:
        raise FileNotFoundError(filename)
    path = ws.root / "exports" / name / filename
    if not path.is_file():
        raise FileNotFoundError(filename)
    return path
