"""Turn a fetched document (HTML, eCFR XML, PDF, JSON, text) into normalized plain text."""

from __future__ import annotations

import html
import io
import json
import re
from datetime import date
from typing import Any

from areao1.web import html_to_text

_XML_BLOCK = re.compile(
    r"<(?:/?(?:P|HEAD|HD|FP|EXTRACT|NOTE|DIV\d?|CITA|AUTH|SOURCE|GPOTABLE|ROW|TABLE|TR|TD|TH|CAPTION))\b[^>]*>",
    re.I,
)


def normalize(text: str) -> str:
    text = text.replace(" ", " ").replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in text.split("\n")]
    out = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return out.strip()


def xml_to_text(raw: str) -> tuple[str, str]:
    head = re.search(r"<HEAD>(.*?)</HEAD>", raw, re.S)
    body = _XML_BLOCK.sub("\n", raw)
    body = re.sub(r"<\?xml[^>]*\?>", "", body)
    body = re.sub(r"<[^>]+>", "", body)
    title = html.unescape(re.sub(r"<[^>]+>", "", head.group(1))).strip() if head else ""
    return title, html.unescape(body)


def pdf_to_text(content: bytes) -> tuple[str, str]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(content))
    pages = [p.extract_text() or "" for p in reader.pages]
    meta = reader.metadata
    title = str(meta.title) if meta and meta.title else ""
    return title, "\n\n".join(pages)


def json_to_text(raw: str) -> tuple[str, str]:
    data = json.loads(raw)

    def flat(value: Any, prefix: str = "") -> list[str]:
        if isinstance(value, dict):
            out: list[str] = []
            for k, v in value.items():
                out += flat(v, f"{k}")
            return out
        if isinstance(value, list):
            out = []
            for item in value:
                out += flat(item, prefix)
                if isinstance(item, dict):
                    out.append("")
            return out
        if value is None or value == "":
            return []
        return [f"{prefix}: {value}" if prefix else str(value)]

    title = data.get("description", "") if isinstance(data, dict) else ""
    items = data.get("results", data) if isinstance(data, dict) else data
    return str(title), "\n".join(flat(items))


def sniff(content_type: str, content: bytes, fmt: str) -> str:
    if fmt != "auto":
        return fmt
    ctype = content_type.lower()
    if "pdf" in ctype or content[:5] == b"%PDF-":
        return "pdf"
    if "json" in ctype:
        return "json"
    if "xml" in ctype and "html" not in ctype:
        return "xml"
    if "html" in ctype:
        return "html"
    return "text"


def to_text(content: bytes, content_type: str, fmt: str = "auto") -> tuple[str, str]:
    """(title, normalized text)."""
    kind = sniff(content_type, content, fmt)
    if kind == "pdf":
        title, text = pdf_to_text(content)
    else:
        raw = content.decode("utf-8", errors="replace")
        if kind == "html":
            title, text = html_to_text(raw)
        elif kind == "xml":
            title, text = xml_to_text(raw)
        elif kind == "json":
            title, text = json_to_text(raw)
        else:
            title, text = "", raw
    return " ".join(title.split()), normalize(text)


def cut(text: str, start: str | None, end: str | None) -> str:
    """Keep the part of ``text`` between the start and end markers (regexes, multiline)."""
    begin = 0
    if start:
        m = re.search(start, text, re.M)
        if not m:
            raise ValueError(f"start marker not found: {start!r}; the page may have changed shape")
        begin = m.start()
    stop = len(text)
    if end:
        m = re.search(end, text[begin + 1 :], re.M)
        if m:
            stop = begin + 1 + m.start()
    return text[begin:stop].strip()


_DATES = (
    re.compile(r"Last Reviewed/Updated:\s*(\d{1,2})/(\d{1,2})/(\d{4})", re.I),
    re.compile(r"up to date as of\s*(\d{1,2})/(\d{1,2})/(\d{4})", re.I),
    re.compile(r"Current as of\s*(\d{1,2})/(\d{1,2})/(\d{4})", re.I),
)


_HTML_REVIEWED = re.compile(r"Last Reviewed/Updated:.{0,400}?datetime=\"(\d{4})-(\d{2})-(\d{2})", re.S | re.I)


def effective_date(text: str, raw: str = "") -> date | None:
    """The page's own "last reviewed / up to date as of" date, if it states one."""
    m = _HTML_REVIEWED.search(raw[:2_000_000]) if raw else None
    if m:
        year, month, day = (int(g) for g in m.groups())
        return date(year, month, day)
    for pattern in _DATES:
        m = pattern.search(text)
        if m:
            month, day, year = (int(g) for g in m.groups())
            try:
                return date(year, month, day)
            except ValueError:
                continue
    return None
