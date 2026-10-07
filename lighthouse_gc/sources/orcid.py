"""ORCID connector: the works on a public ORCID record (https://orcid.org/<iD>) via the public API
(https://pub.orcid.org/v3.0). No key. ORCID lists works but not citations."""

from __future__ import annotations

import re
from typing import Any

from lighthouse_gc.sources.base import dig
from lighthouse_gc.sources.scholarly import Paper, ScholarlySource, arxiv_id, doi

API = "https://pub.orcid.org"
HEADERS = {"Accept": "application/json"}
TYPES = {"journal-article": "journal", "conference-paper": "conference", "preprint": "preprint",
         "working-paper": "preprint"}  # fmt: skip

_ID = r"(?P<id>\d{4}-\d{4}-\d{4}-\d{3}[\dX])"
_URL_RE = re.compile(rf"^(?:https?://)?(?:www\.|sandbox\.)?orcid\.org/{_ID}/?$", re.I)
_HANDLE_RE = re.compile(rf"^(?:orcid:)?{_ID}$", re.I)


def valid_orcid(orcid: str) -> bool:
    """ISO 7064 mod 11-2 check digit."""
    digits = orcid.replace("-", "")
    total = 0
    for ch in digits[:-1]:
        total = (total + int(ch)) * 2
    check = (12 - total % 11) % 11
    return digits[-1].upper() == ("X" if check == 10 else str(check))


class OrcidSource(ScholarlySource):
    kind = "orcid"
    label = "ORCID"
    API = API
    confidence = 0.7  # an ORCID record is curated by its owner

    @staticmethod
    def parse(url_or_handle: str) -> str:
        text = url_or_handle.strip()
        m = _URL_RE.match(text) or _HANDLE_RE.match(text)
        if not m or not valid_orcid(m["id"]):
            raise ValueError(f"not an ORCID iD (0000-0000-0000-000X) or orcid.org URL: {text!r}")
        return m["id"].upper()

    def source_url(self, handle: str) -> str:
        return f"https://orcid.org/{handle}"

    def author(self, handle: str) -> tuple[dict[str, Any], str, dict[str, str]]:
        path = f"/v3.0/{handle}/person"
        return self.http.get(path).data or {}, API + path, {}  # ORCID has no citation metrics

    def author_name(self, record: dict[str, Any], handle: str) -> str:
        credit = dig(record, "name.credit-name.value")
        given, family = dig(record, "name.given-names.value"), dig(record, "name.family-name.value")
        return str(credit or " ".join(x for x in (given, family) if x) or handle)

    def fetch_papers(self, handle: str) -> list[Paper]:
        path = f"/v3.0/{handle}/works"
        data = self.http.get(path).data or {}
        out = []
        for group in data.get("group") or []:
            summaries = group.get("work-summary") or []
            if not summaries:
                continue
            w = summaries[0]
            title = dig(w, "title.title.value")
            if not title:
                continue
            ids = {x.get("external-id-type"): x.get("external-id-value")
                   for x in dig(group, "external-ids.external-id") or [] if x.get("external-id-relationship") == "self"}  # fmt: skip
            year = dig(w, "publication-date.year.value")
            the_doi = doi(ids.get("doi"))
            kind = TYPES.get(w.get("type") or "", "unknown")
            out.append(Paper(key=str(w["put-code"]), title=title, payload=w, source_url=API + path,
                             url=f"https://doi.org/{the_doi}" if the_doi else (dig(w, "url.value") or self.source_url(handle)),
                             year=int(year) if year and str(year).isdigit() else None,
                             venue=dig(w, "journal-title.value") or "", kind=kind, doi=the_doi, arxiv=arxiv_id(ids.get("arxiv")),
                             claim_fields={"title": "title.title.value", "type": "type",
                                           "year": "publication-date.year.value"},
                             extra={"orcid_type": w.get("type") or ""}))  # fmt: skip
        return out
