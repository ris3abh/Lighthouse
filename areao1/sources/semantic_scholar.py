"""Semantic Scholar connector: an author's papers, citations, venues and h-index via the free Graph API
(https://api.semanticscholar.org). No key needed; requests are rate-limited, and the shared client backs off."""

from __future__ import annotations

import re
from typing import Any

from areao1.sources.scholarly import Paper, ScholarlySource, arxiv_id, doi

API = "https://api.semanticscholar.org"
HEADERS: dict[str, str] = {}
AUTHOR_FIELDS = "name,url,affiliations,paperCount,citationCount,hIndex"
PAPER_FIELDS = (
    "title,year,venue,publicationVenue,externalIds,citationCount,publicationTypes,publicationDate,url,journal"
)
PAGE = 100

_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?semanticscholar\.org/author/(?:[^/?#]+/)?(?P<id>\d+)/?(?:[?#].*)?$", re.I
)
_HANDLE_RE = re.compile(r"^(?:s2|semanticscholar):(?P<id>\d+)$", re.I)


class SemanticScholarSource(ScholarlySource):
    kind = "semantic_scholar"
    label = "Semantic Scholar"
    API = API

    @staticmethod
    def parse(url_or_handle: str) -> str:
        text = url_or_handle.strip()
        m = _HANDLE_RE.match(text) or _URL_RE.match(text)
        if not m:
            raise ValueError(f"not a Semantic Scholar author URL or s2:<id>: {text!r}")
        return m["id"]

    def source_url(self, handle: str) -> str:
        return f"https://www.semanticscholar.org/author/{handle}"

    def author(self, handle: str) -> tuple[dict[str, Any], str, dict[str, str]]:
        path = f"/graph/v1/author/{handle}"
        record = self.http.get(path, params={"fields": AUTHOR_FIELDS}).data
        return record, API + path, {"citations": "citationCount", "h_index": "hIndex", "papers": "paperCount"}

    def fetch_papers(self, handle: str) -> list[Paper]:
        path = f"/graph/v1/author/{handle}/papers"
        out: list[Paper] = []
        offset: int | None = 0
        while offset is not None and len(out) < 500:
            page = self.http.get(path, params={"fields": PAPER_FIELDS, "limit": PAGE, "offset": offset}).data
            out += [
                self._to_paper(p, API + path)
                for p in page.get("data") or []
                if p.get("paperId") and p.get("title")
            ]
            offset = page.get("next")
        return out

    @staticmethod
    def _to_paper(p: dict[str, Any], source_url: str) -> Paper:
        ids = p.get("externalIds") or {}
        venue_type = ((p.get("publicationVenue") or {}).get("type") or "").lower()
        types = p.get("publicationTypes") or []
        venue = p.get("venue") or ""
        if venue_type in ("journal", "conference"):
            kind = venue_type
        elif "JournalArticle" in types:
            kind = "journal"
        elif "Conference" in types:
            kind = "conference"
        elif "arxiv" in venue.lower() or (ids.get("ArXiv") and not venue):
            kind = "preprint"
        else:
            kind = "unknown"
        return Paper(key=p["paperId"], title=p["title"], payload=p, source_url=source_url,
                     url=p.get("url") or f"https://www.semanticscholar.org/paper/{p['paperId']}", year=p.get("year"),
                     venue="" if kind == "preprint" else venue, kind=kind, doi=doi(ids.get("DOI")),
                     arxiv=arxiv_id(ids.get("ArXiv")), citations=p.get("citationCount"),
                     claim_fields={"title": "title", "year": "year", "venue": "venue", "citations": "citationCount"})  # fmt: skip
