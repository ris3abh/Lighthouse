"""Gmail threads with your case contacts (ADR 0014 §2 and its amendment). Over IMAP with your app password: searches
only for mail to or from your contacts' email addresses, fetches headers only (never bodies or attachments), and
keeps per thread: the subject, which contacts are on it, and the last message's date, sender and Message-ID. Each
contact's last touch follows the newest thread."""

from __future__ import annotations

from datetime import UTC, date, datetime
from email.utils import getaddresses

from areao1.agent.redact import redact
from areao1.core import clock
from areao1.criteria.case import Case
from areao1.criteria.models import GmailThread, GmailThreads
from areao1.google import mail

Msgs = list[tuple[int, dict[str, str]]]  # (time in ms, headers), per message
LOOKBACK_DAYS = 365


def load_threads(ws: Case) -> GmailThreads:
    return ws.threads()


def _emails(header: str) -> set[str]:
    return {addr.lower() for _, addr in getaddresses([header]) if addr}


def sync(ws: Case, days: int = LOOKBACK_DAYS) -> list[str]:
    """Refresh the threads for every contact with an email. Returns report lines."""
    if not mail.connected():
        return ["skipped: Gmail isn't connected (Settings > Gmail)"]
    by_email = {e: c.id for c in ws.contacts().contacts for e in c.emails}
    if not by_email:
        return ["skipped: no contact has an email yet"]
    me = mail.address()
    found = mail.threads(sorted(by_email), days)
    threads = [t for tid, msgs in found if (t := _thread(tid, msgs, by_email, me)) is not None]
    ws.save_threads(GmailThreads(threads=threads, synced_at=clock.utcnow()))
    touched = _touch(ws, threads)
    return [
        f"Gmail: {len(threads)} threads with your contacts"
        + (f"; last touch updated for {touched}" if touched else "")
    ]


def _thread(tid: str, msgs: Msgs, by_email: dict[str, str], me: str) -> GmailThread | None:
    if not msgs:
        return None
    contacts: set[str] = set()
    last: tuple[int, dict[str, str]] | None = None
    subject = ""
    for at, h in msgs:
        h = {k.title(): v for k, v in h.items()}
        for name in ("From", "To", "Cc"):
            contacts |= {by_email[e] for e in _emails(h.get(name, "")) if e in by_email}
        subject = subject or h.get("Subject", "")
        if last is None or at > last[0]:
            last = (at, h)
    if not contacts or last is None:
        return None  # Google matched something else (an alias, a list): not a thread with your contacts
    sender = _emails(last[1].get("From", ""))
    last_from = "them" if sender & set(by_email) else "you" if (not me or me in sender) else "them"
    return GmailThread(id=tid, subject=redact(subject)[:200], contact_ids=sorted(contacts),
                       last_at=datetime.fromtimestamp(last[0] / 1000, tz=UTC), last_from=last_from,  # type: ignore[arg-type]
                       messages=len(msgs),
                       last_message_id=last[1].get("Message-Id", "").strip()[:998] or None)  # fmt: skip


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
