"""Exhibit dates (B2): the date a document shows, read from the document where it says so. For exhibits filed before
dates were tracked, `areao1 repair-dates` finds what it can (an email's Date header, a PDF's creation date, the
claims' event dates) and marks the rest "date unconfirmed" when their date is only the day they were filed."""

from __future__ import annotations

from datetime import date
from email import message_from_bytes, policy
from email.utils import parsedate_to_datetime
from typing import Any

from areao1.core import clock
from areao1.core.models import Exhibit
from areao1.criteria.case import Case


def from_file(ws: Case, exhibit: Exhibit) -> tuple[date, str] | None:
    path = ws.root / exhibit.file
    if not path.is_file():
        return None
    data = path.read_bytes()
    if exhibit.file.lower().endswith(".eml"):
        try:
            when = message_from_bytes(data, policy=policy.default).get("Date")
            return (clock.local_date(parsedate_to_datetime(str(when))), "email") if when else None
        except (TypeError, ValueError, IndexError):
            return None
    made = ws.document_date(data, exhibit.file)
    return (made, "pdf") if made else None


def from_claims(ws: Case, exhibit: Exhibit, claims: dict[str, Any]) -> tuple[date, str] | None:
    dated = [claims[i].event_date for i in exhibit.claim_ids if i in claims and claims[i].event_date]
    return (max(dated), "claim") if dated else None


def plan(ws: Case) -> list[dict[str, Any]]:
    """What repair would do, per exhibit whose date isn't known to come from the document: a found date, or
    "unconfirmed" when its date is only its filing day. Exhibits with a recorded source are left alone."""
    claims = {c.id: c for c in ws.memory.claims()}
    out = []
    for ex in ws.exhibits().exhibits:
        if ex.date_source not in (None, "unconfirmed"):
            continue
        found = from_file(ws, ex) or from_claims(ws, ex, claims)
        if found:
            out.append({"exhibit": ex.id, "title": ex.title, "from": ex.date.isoformat(), "to": found[0].isoformat(),
                        "source": found[1]})  # fmt: skip
        elif ex.date_source is None and ex.date == clock.local_date(ex.accepted_at):
            out.append({"exhibit": ex.id, "title": ex.title, "from": ex.date.isoformat(), "to": ex.date.isoformat(),
                        "source": "unconfirmed"})  # fmt: skip
    return out


def apply(ws: Case, steps: list[dict[str, Any]], actor: str = "user") -> int:
    from areao1.service import Service

    svc = Service(ws, actor=actor)
    for step in steps:
        svc.redate_exhibit(step["exhibit"], date.fromisoformat(step["to"]), step["source"])
    return len(steps)
