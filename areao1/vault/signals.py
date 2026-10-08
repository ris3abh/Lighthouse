"""Change signals (ADR 0011 §1): when did the facts behind a source actually change?

Two official feeds, both public APIs: the Federal Register (final rules from USCIS / DHS that are in effect, matched to
a signal by CFR part or terms) and eCFR (the latest amendment date of each watched 8 CFR section). A source with a
signal stays fresh until a relevant change takes effect after its copy was taken; if the feeds weren't checked in
the last three days, its timer applies instead."""

from __future__ import annotations

import json
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx

from areao1.core import clock

FR_URL = "https://www.federalregister.gov/api/v1/documents.json"
ECFR_VERSIONS = "https://www.ecfr.gov/api/versioner/v1/versions/title-8.json"
AGENCIES = ("u-s-citizenship-and-immigration-services", "homeland-security-department")
STALE_AFTER = timedelta(days=3)
FIRST_LOOKBACK = timedelta(days=365)


def utcnow() -> datetime:
    from areao1.vault import store

    return store.utcnow()  # the vault's clock (tests move it)


def _path(vault: Any) -> Any:
    return vault.dir / "signals.json"


def load(vault: Any) -> dict[str, Any]:
    p = _path(vault)
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    except ValueError:
        return {}


def save(vault: Any, state: dict[str, Any]) -> None:
    vault.dir.mkdir(parents=True, exist_ok=True)
    _path(vault).write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")


def events_for(vault: Any, signal: str, after: datetime, now: datetime | None = None) -> list[dict[str, Any]]:
    """Changes for ``signal`` in effect after ``after`` (and not in the future)."""
    today = clock.local_date(now or utcnow())
    out = []
    for e in load(vault).get("events", []):
        if e.get("signal") != signal:
            continue
        when = date.fromisoformat(e["date"])
        if when <= today and datetime(when.year, when.month, when.day, tzinfo=UTC) > after:
            out.append(e)
    return out


def fresh(vault: Any, source: Any, checked_at: datetime, now: datetime | None = None) -> bool | None:
    """True / False for a source with a signal, or None when the feeds are stale (the timer decides)."""
    checked = load(vault).get("checked_at")
    if not checked or (now or utcnow()) - datetime.fromisoformat(checked) > STALE_AFTER:
        return None
    return not events_for(vault, source.signal, checked_at, now)


def _matches(doc: dict[str, Any], sig: Any) -> bool:
    parts = {int(r.get("part") or 0) for r in doc.get("cfr_references") or [] if str(r.get("title")) == "8"}
    if parts & set(sig.cfr_parts):
        return True
    text = f"{doc.get('title', '')} {doc.get('abstract') or ''}".lower()
    return any(re.search(rf"\b{re.escape(t.lower())}\b", text) for t in sig.terms)


async def check(vault: Any, client: httpx.AsyncClient | None = None) -> list[str]:
    """Ask both feeds what changed since the last check; record new events. Returns report lines."""
    sigs = vault.manifest.signals
    if not sigs:
        return []
    state = load(vault)
    events: list[dict[str, Any]] = state.get("events", [])
    known = {e["id"] for e in events}
    since = clock.local_date(datetime.fromisoformat(state["checked_at"]) - timedelta(days=7) if state.get("checked_at")
                             else utcnow() - FIRST_LOOKBACK)  # fmt: skip
    own = client is None
    client = client or httpx.AsyncClient(timeout=30, headers={"User-Agent": "AreaO1 vault"})
    lines: list[str] = []
    new: list[dict[str, Any]] = []
    try:
        params: list[tuple[str, str | int | float | bool | None]] = [("per_page", "100"), ("order", "newest"), ("conditions[type][]", "RULE"),
                                         ("conditions[effective_date][gte]", since.isoformat())]  # fmt: skip
        params += [("conditions[agencies][]", a) for a in AGENCIES]
        params += [("fields[]", f) for f in ("document_number", "title", "abstract", "effective_on", "html_url",
                                             "cfr_references", "publication_date")]  # fmt: skip
        try:
            r = await client.get(FR_URL, params=params)
            r.raise_for_status()
            for doc in r.json().get("results") or []:
                if not doc.get("effective_on"):
                    continue
                for name, sig in sigs.items():
                    eid = f"fr:{doc['document_number']}:{name}"
                    if eid not in known and _matches(doc, sig):
                        new.append({"id": eid, "signal": name, "date": doc["effective_on"], "title": doc["title"][:300],
                                    "url": doc.get("html_url") or "", "feed": "federal_register"})  # fmt: skip
        except (httpx.HTTPError, ValueError) as exc:
            lines.append(f"signals: Federal Register unreachable ({type(exc).__name__}); timers apply")
            return lines  # don't mark as checked: freshness falls back to timers
        latest: dict[str, str] = state.get("ecfr", {})
        for part in sorted({int(s.split(".")[0]) for sig in sigs.values() for s in sig.ecfr_sections}):
            try:
                r = await client.get(ECFR_VERSIONS, params={"part": str(part)})
                r.raise_for_status()
                versions = r.json().get("content_versions") or []
            except (httpx.HTTPError, ValueError) as exc:
                lines.append(f"signals: eCFR part {part} unreachable ({type(exc).__name__}); timers apply")
                return lines
            for name, sig in sigs.items():
                for section in (s for s in sig.ecfr_sections if int(s.split(".")[0]) == part):
                    dates = [v.get("amendment_date") or v.get("date") for v in versions
                             if v.get("identifier") == section and v.get("substantive", True) and not v.get("removed")]  # fmt: skip
                    top = max((d for d in dates if d), default=None)
                    if top and top > latest.get(section, ""):
                        latest[section] = top
                        eid = f"ecfr:{section}:{top}:{name}"
                        if eid not in known:
                            new.append({"id": eid, "signal": name, "date": top, "url": f"https://www.ecfr.gov/current/title-8/section-{section}",
                                        "title": f"8 CFR {section} amended", "feed": "ecfr"})  # fmt: skip
        state.update(checked_at=utcnow().isoformat(), ecfr=latest, events=[*events, *new][-500:])
        save(vault, state)
    finally:
        if own:
            await client.aclose()
    lines.append(
        f"signals: {len(new)} new change{'s' if len(new) != 1 else ''}" if new else "signals: no new changes"
    )
    return lines


def why(vault: Any, source: Any, checked_at: datetime) -> str:
    """The change that made a source stale, in words (for the reminder)."""
    found = events_for(vault, source.signal, checked_at) if source.signal else []
    if not found:
        return ""
    e = max(found, key=lambda x: x["date"])
    return f"{e['title']} (in effect {e['date']})"
