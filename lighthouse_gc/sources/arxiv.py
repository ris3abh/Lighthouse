"""arXiv connector: the papers on an arXiv author page (https://arxiv.org/a/<id>), from its Atom feed.
arXiv has no citation counts; papers are preprints unless the feed carries a journal reference."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Any

from lighthouse_gc.sources.http import SourceError
from lighthouse_gc.sources.scholarly import Paper, ScholarlySource, arxiv_id, doi

API = "https://arxiv.org"
HEADERS: dict[str, str] = {}
NS = {"a": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}

_ID = r"(?P<id>[a-z][a-z'\-]*_[a-z]_\d+|\d{4}-\d{4}-\d{4}-\d{3}[\dX])"
_URL_RE = re.compile(rf"^(?:https?://)?(?:www\.)?arxiv\.org/a/{_ID}(?:\.atom2?|\.html)?/?$", re.I)
_HANDLE_RE = re.compile(rf"^arxiv:{_ID}$", re.I)


def parse_feed(text: str) -> tuple[str, list[dict[str, Any]]]:
    """(the feed's author name, one dict per entry). Refuses DTDs and entities (no XML entity tricks)."""
    if re.search(r"<!DOCTYPE|<!ENTITY", text, re.I):
        raise SourceError("arxiv: the feed contains a DTD; refusing to parse it")
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise SourceError(f"arxiv: not an Atom feed ({exc})") from exc
    title = (root.findtext("a:title", "", NS) or "").strip()
    name = re.sub(r"[’']s articles on arXiv$", "", title).strip()
    entries = []
    for e in root.findall("a:entry", NS):
        link = e.findtext("a:id", "", NS).strip()
        entries.append({
            "id": link,
            "title": re.sub(r"\s+", " ", e.findtext("a:title", "", NS)).strip(),
            "published": e.findtext("a:published", "", NS).strip(),
            "updated": e.findtext("a:updated", "", NS).strip(),
            "authors": ", ".join(re.sub(r"\s+", " ", (a.findtext("a:name", "", NS) or "")).strip()
                                 for a in e.findall("a:author", NS)),
            "journal_ref": (e.findtext("arxiv:journal_ref", "", NS) or "").strip(),
            "doi": (e.findtext("arxiv:doi", "", NS) or "").strip(),
            "comment": re.sub(r"\s+", " ", e.findtext("arxiv:comment", "", NS) or "").strip(),
        })  # fmt: skip
    return name, entries


class ArxivSource(ScholarlySource):
    kind = "arxiv"
    label = "arXiv"
    API = API
    confidence = 0.7  # an arXiv author page is claimed by its owner

    @staticmethod
    def parse(url_or_handle: str) -> str:
        text = url_or_handle.strip()
        m = _HANDLE_RE.match(text) or _URL_RE.match(text)
        if not m:
            raise ValueError(f"not an arXiv author page (arxiv.org/a/<id>) or arxiv:<id>: {text!r}")
        return m["id"].lower() if "_" in m["id"] else m["id"].upper()

    def source_url(self, handle: str) -> str:
        return f"https://arxiv.org/a/{handle}"

    def _feed(self, handle: str) -> tuple[str, list[dict[str, Any]]]:
        text = self.http.get(f"/a/{handle}.atom", raw=True, accept="application/atom+xml").data
        return parse_feed(text or "")

    def author(self, handle: str) -> tuple[dict[str, Any], str, dict[str, str]]:
        name, entries = self._feed(handle)
        return (
            {"name": name or handle, "papers": len(entries)},
            f"{API}/a/{handle}.atom",
            {"papers": "papers"},
        )

    def fetch_papers(self, handle: str) -> list[Paper]:
        _, entries = self._feed(handle)
        out = []
        for e in entries:
            aid = arxiv_id(e["id"])
            if not aid or not e["title"]:
                continue
            ref = e["journal_ref"]
            out.append(Paper(key=aid, title=e["title"], payload=e, source_url=f"{API}/a/{handle}.atom",
                             url=f"https://arxiv.org/abs/{aid}", year=int(e["published"][:4]) if e["published"][:4].isdigit() else None,
                             venue=ref, kind="unknown" if ref else "preprint", doi=doi(e["doi"]), arxiv=aid,
                             claim_fields={"title": "title", "published": "published"},
                             extra={"journal_ref": ref} if ref else {}))  # fmt: skip
        return out


EXPORT_API = "https://export.arxiv.org"


def search_title(title: str, http: object | None = None) -> list[dict[str, Any]]:
    """arXiv entries whose title matches ``title`` (the export API's title search), newest first."""
    from lighthouse_gc.sources.http import HttpClient

    client = http if isinstance(http, HttpClient) else HttpClient(EXPORT_API, kind="arxiv")
    phrase = re.sub(r"[^\w\s-]", " ", title).strip()
    text = client.get("/api/query", params={"search_query": f'ti:"{phrase}"', "max_results": 5}, raw=True,
                      accept="application/atom+xml").data  # fmt: skip
    _, entries = parse_feed(text or "")
    return entries


def by_id(arxiv_id: str, http: object | None = None) -> list[dict[str, Any]]:
    """The arXiv entry for an id (2609.34227), via the export API's id_list."""
    from lighthouse_gc.sources.http import HttpClient

    client = http if isinstance(http, HttpClient) else HttpClient(EXPORT_API, kind="arxiv")
    text = client.get("/api/query", params={"id_list": arxiv_id, "max_results": 1}, raw=True,
                      accept="application/atom+xml").data  # fmt: skip
    _, entries = parse_feed(text or "")
    return [e for e in entries if e.get("title")]
