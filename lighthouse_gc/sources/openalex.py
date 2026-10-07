"""OpenAlex connector: an author's works, citations, venues and h-index via the free OpenAlex API
(https://api.openalex.org). No key. (OpenAlex asks for a contact email for its "polite pool"; we don't send
one, because it would identify the person.)"""

from __future__ import annotations

import re
from typing import Any

from lighthouse_gc.sources.scholarly import Paper, ScholarlySource, arxiv_id, doi

API = "https://api.openalex.org"
HEADERS: dict[str, str] = {}
SELECT = (
    "id,doi,display_name,publication_year,publication_date,type,cited_by_count,primary_location,ids,locations"
)
PAGE = 200

_URL_RE = re.compile(
    r"^(?:https?://)?(?:api\.)?openalex\.org/(?:authors/)?(?P<id>A\d{4,})/?(?:[?#].*)?$", re.I
)
_HANDLE_RE = re.compile(r"^openalex:(?P<id>A\d{4,})$", re.I)


def _short(openalex_url: str) -> str:
    return openalex_url.rstrip("/").rsplit("/", 1)[-1]


class OpenAlexSource(ScholarlySource):
    kind = "openalex"
    label = "OpenAlex"
    API = API

    @staticmethod
    def parse(url_or_handle: str) -> str:
        text = url_or_handle.strip()
        m = _HANDLE_RE.match(text) or _URL_RE.match(text)
        if not m:
            raise ValueError(f"not an OpenAlex author URL or openalex:<A-id>: {text!r}")
        return m["id"].upper()

    def source_url(self, handle: str) -> str:
        return f"https://openalex.org/{handle}"

    def author_name(self, record: dict[str, Any], handle: str) -> str:
        return str(record.get("display_name") or handle)

    def author(self, handle: str) -> tuple[dict[str, Any], str, dict[str, str]]:
        path = f"/authors/{handle}"
        record = self.http.get(path).data
        return record, API + path, {"citations": "cited_by_count", "h_index": "summary_stats.h_index",
                                    "papers": "works_count"}  # fmt: skip

    def fetch_papers(self, handle: str) -> list[Paper]:
        out: list[Paper] = []
        page = 1
        while len(out) < 500:
            data = self.http.get("/works", params={"filter": f"author.id:{handle}", "per-page": PAGE, "page": page,
                                                  "select": SELECT, "sort": "publication_year:desc"}).data  # fmt: skip
            results = data.get("results") or []
            out += [self._to_paper(w) for w in results if w.get("id") and w.get("display_name")]
            if len(results) < PAGE:
                break
            page += 1
        return out

    @staticmethod
    def _to_paper(w: dict[str, Any]) -> Paper:
        primary = w.get("primary_location") or {}
        source = primary.get("source") or {}
        source_type = (source.get("type") or "").lower()
        if w.get("type") == "preprint" or source_type == "repository":
            kind = "preprint"
        elif source_type in ("journal", "conference"):
            kind = source_type
        else:
            kind = "unknown"
        landing = [loc.get("landing_page_url") or "" for loc in w.get("locations") or []]
        arxiv = next((arxiv_id(u) for u in landing if "arxiv.org" in u), None) or arxiv_id(
            (w.get("doi") or "") if "arxiv" in (w.get("doi") or "").lower() else None
        )
        key = _short(w["id"])
        return Paper(key=key, title=w["display_name"], payload=w, source_url=f"{API}/works/{key}", url=w["id"],
                     year=w.get("publication_year"), venue="" if kind == "preprint" else source.get("display_name") or "",
                     kind=kind, doi=doi(w.get("doi")), arxiv=arxiv, citations=w.get("cited_by_count"),
                     claim_fields={"title": "display_name", "year": "publication_year",
                                   "citations": "cited_by_count"})  # fmt: skip
