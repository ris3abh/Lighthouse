"""Gmail threads with your case contacts (ADR 0014 §2). Searches only for mail to or from your contacts' email
addresses, asks Google for headers only (never bodies or attachments), and keeps per thread: the subject, which
contacts are on it, the last message's date and sender, and one redacted line. Each contact's last touch follows
the newest thread. ``client`` is injectable so tests never reach Google."""

from __future__ import annotations

from datetime import UTC, date, datetime
from email.utils import getaddresses
from typing import Any

import httpx

from areao1.agent.redact import redact
from areao1.core import clock
from areao1.criteria.case import Case
from areao1.criteria.models import GmailThread, GmailThreads
from areao1.google import auth

API = "https://gmail.googleapis.com/gmail/v1/users/me"
HEADERS = ["From", "To", "Cc", "Subject", "Date"]
LOOKBACK_DAYS = 365


def load_threads(ws: Case) -> GmailThreads:
    return ws.threads()


def _emails(header: str) -> set[str]:
    return {addr.lower() for _, addr in getaddresses([header]) if addr}


def sync(ws: Case, client: httpx.Client | None = None, days: int = LOOKBACK_DAYS) -> list[str]:
    """Refresh the threads for every contact with an email. Returns report lines."""
    if not auth.granted("gmail_read"):
        return ["skipped: Gmail isn't connected (Settings > Google)"]
    by_email = {e: c.id for c in ws.contacts().contacts for e in c.emails}
    if not by_email:
        return ["skipped: no contact has an email yet"]
    me = str((auth.token() or {}).get("email") or "").lower()
    own = client is None
    c = client or httpx.Client(timeout=30)
    try:
        headers = {"Authorization": f"Bearer {auth.access_token(c)}"}
        ids: set[str] = set()
        for email in sorted(by_email):
            q = f"(from:{email} OR to:{email} OR cc:{email}) newer_than:{days}d"
            r = c.get(f"{API}/threads", params={"q": q, "maxResults": 50}, headers=headers)
            r.raise_for_status()
            ids |= {t["id"] for t in r.json().get("threads", [])}
        threads = []
        for tid in sorted(ids):
            r = c.get(f"{API}/threads/{tid}", params=[("format", "metadata"), *(("metadataHeaders", h) for h in HEADERS)],
                      headers=headers)  # fmt: skip
            r.raise_for_status()
            t = _thread(r.json(), by_email, me)
            if t is not None:
                threads.append(t)
    finally:
        if own:
            c.close()
    ws.save_threads(GmailThreads(threads=threads, synced_at=clock.utcnow()))
    touched = _touch(ws, threads)
    return [
        f"Gmail: {len(threads)} threads with your contacts"
        + (f"; last touch updated for {touched}" if touched else "")
    ]


def _thread(data: dict[str, Any], by_email: dict[str, str], me: str) -> GmailThread | None:
    msgs = data.get("messages") or []
    if not msgs:
        return None
    contacts: set[str] = set()
    last: tuple[int, dict[str, str]] | None = None
    subject = ""
    for m in msgs:
        h = {x["name"]: x["value"] for x in (m.get("payload") or {}).get("headers", [])}
        for name in ("From", "To", "Cc"):
            contacts |= {by_email[e] for e in _emails(h.get(name, "")) if e in by_email}
        subject = subject or h.get("Subject", "")
        at = int(m.get("internalDate", 0))
        if last is None or at > last[0]:
            last = (at, h)
    if not contacts or last is None:
        return None  # Google matched something else (an alias, a list): not a thread with your contacts
    sender = _emails(last[1].get("From", ""))
    last_from = "them" if sender & set(by_email) else "you" if (not me or me in sender) else "them"
    return GmailThread(id=str(data["id"]), subject=redact(subject)[:200], contact_ids=sorted(contacts),
                       last_at=datetime.fromtimestamp(last[0] / 1000, tz=UTC), last_from=last_from,  # type: ignore[arg-type]
                       snippet=redact(str(msgs[-1].get("snippet") or ""))[:200], messages=len(msgs))  # fmt: skip


def _touch(ws: Case, threads: list[GmailThread]) -> int:
    """Move each contact's last touch to their newest thread (only forward), through the service layer."""
    from areao1.service import Service

    newest: dict[str, date] = {}
    for t in threads:
        for cid in t.contact_ids:
            seen = clock.local_date(t.last_at)
            newest[cid] = max(newest.get(cid, seen), seen)
    svc, n = Service(ws, actor="gmail"), 0
    for c in ws.contacts().contacts:
        latest = newest.get(c.id)
        if latest and (c.last_touch is None or latest > c.last_touch):
            svc.update_contact(c.id, last_touch=latest)
            n += 1
    return n
