"""Outreach (ADR 0014 §5): emails to your contacts, drafted by you, the agent or the follow-up job, and sent from
your Gmail over SMTP with your app password, only when you approve them. Case contacts only, a daily send limit,
and the same guardrails as other text the agent writes for your case."""

from __future__ import annotations

import threading
from email.message import EmailMessage
from email.utils import make_msgid
from typing import Any

from areao1.agent.guardrails import guard_answer
from areao1.core import clock
from areao1.core.workspace import WorkspaceError
from areao1.criteria.case import Case
from areao1.criteria.models import OutreachDraft, SendAttempt
from areao1.google import mail


def compose(ws: Case, contact_id: str, subject: str, body: str, purpose: str = "other", drafted_by: str = "user",
            thread_id: str | None = None) -> OutreachDraft:  # fmt: skip
    """A draft to a contact (not saved). Refused for anyone who isn't a contact with an email."""
    contact = next((c for c in ws.contacts().contacts if c.id == contact_id), None)
    if contact is None:
        raise WorkspaceError(
            f"{contact_id!r} isn't one of your contacts; outreach goes to case contacts only"
        )
    if not contact.emails:
        raise WorkspaceError(f"{contact.name} has no email yet; add one on the Contacts page")
    body, _ = guard_answer(body.strip())  # no eligibility verdicts or guarantees in your name either
    return OutreachDraft(
        contact_id=contact.id,
        to=contact.emails[0],
        subject=subject.strip()[:200],
        body=body,
        purpose=purpose,
        drafted_by=drafted_by,
        thread_id=thread_id,
    )  # type: ignore[arg-type]


UNDO_SECONDS = 10.0  # after Approve & send, how long Undo send can still stop it
SENDING = threading.Lock()
"""Held from reading a draft to recording it as sent: a second Approve & send (a double click while Gmail is slow)
waits, then finds the email already sent instead of sending it again."""


def can_send() -> bool:
    return mail.connected()


def sent_today(ws: Case) -> int:
    """Emails that actually went out today (each send Gmail accepted), not drafts marked sent."""
    today = clock.today()
    out = ws.outreach()
    logged = {a.draft_id for a in out.attempts}
    went = sum(1 for a in out.attempts if a.ok and clock.local_date(a.at) == today)
    # Sends from before the log: every one left an outreach.send change (even a duplicate of the same draft).
    before_the_log = sum(1 for ch in ws.changes() if ch.action == "outreach.send" and ch.target_id not in logged
                         and clock.local_date(ch.at) == today)  # fmt: skip
    return went + before_the_log


def failures(ws: Case, days: int = 7) -> list[SendAttempt]:
    """Sends that didn't go out in the last ``days``, newest first, unless the same email went out later."""
    since = clock.utcnow().timestamp() - days * 86400
    attempts = ws.outreach().attempts
    sent = {a.draft_id for a in attempts if a.ok}
    return [
        a for a in reversed(attempts) if not a.ok and a.at.timestamp() >= since and a.draft_id not in sent
    ]


def send(ws: Case, draft: OutreachDraft) -> dict[str, Any]:
    """Send an approved draft from your Gmail over SMTP. Returns its Message-ID and thread."""
    if draft.status not in ("draft", "queued"):
        raise WorkspaceError(f"this email is already {draft.status}")
    try:
        msg = _checked(ws, draft)
        mail.send(msg)
    except (WorkspaceError, mail.MailError) as exc:
        error = (
            f"Gmail didn't send it: {exc} It's still a draft."
            if isinstance(exc, mail.MailError)
            else str(exc)
        )
        ws.log_attempt(
            SendAttempt(draft_id=draft.id, to=draft.to, subject=draft.subject, ok=False, error=error[:500])
        )
        raise WorkspaceError(error) from exc
    ws.log_attempt(SendAttempt(draft_id=draft.id, to=draft.to, subject=draft.subject, ok=True,
                               message_id=msg["Message-ID"]))  # fmt: skip
    return {"id": msg["Message-ID"], "threadId": draft.thread_id}


def check(ws: Case, draft: OutreachDraft) -> None:
    """Every rule, checked when you approve (so a refusal shows at once instead of after the undo window). A refusal
    is logged like any failed send."""
    try:
        _checked(ws, draft)
    except WorkspaceError as exc:
        ws.log_attempt(SendAttempt(draft_id=draft.id, to=draft.to, subject=draft.subject, ok=False,
                                   error=str(exc)[:500]))  # fmt: skip
        raise


def _checked(ws: Case, draft: OutreachDraft) -> EmailMessage:
    """The message to send, after every rule: a case contact, Gmail connected, under today's limit."""
    contact = next((c for c in ws.contacts().contacts if c.id == draft.contact_id), None)
    if contact is None or draft.to.lower() not in contact.emails:
        raise WorkspaceError(
            "outreach goes to case contacts only: this address isn't on the contact any more"
        )
    if not can_send():
        raise WorkspaceError("Sending isn't connected: connect Gmail in Settings > Gmail")
    limit = ws.config().outreach.daily_limit
    if sent_today(ws) >= limit:
        raise WorkspaceError(
            f"today's limit of {limit} emails is reached; it resets tomorrow (Settings: outreach.daily_limit)"
        )
    me = mail.address()
    msg = EmailMessage()
    msg["To"] = draft.to
    if me:
        msg["From"] = me
    msg["Subject"] = draft.subject
    msg["Message-ID"] = make_msgid(domain=str(me).rpartition("@")[2] or None)
    thread = (
        next((t for t in ws.threads().threads if t.id == draft.thread_id), None) if draft.thread_id else None
    )
    if thread is not None and thread.last_message_id:  # a follow-up replies in the thread
        msg["In-Reply-To"] = thread.last_message_id
        msg["References"] = thread.last_message_id
    msg.set_content(draft.body)
    return msg


FOLLOW_UP = """Hi {first},

Just following up on my note about "{subject}". I know things get busy; whenever you have a moment, I'd be grateful for a reply.

Thank you,
{me}"""


def follow_ups(ws: Case) -> list[OutreachDraft]:
    """Drafts for threads where you wrote last and the contact has been quiet for follow_up_days. One per thread,
    and never sent without your approval. The text is a short template you edit before approving."""
    days = ws.config().outreach.follow_up_days
    now = clock.utcnow()
    contacts = {c.id: c for c in ws.contacts().contacts}
    drafts = ws.outreach().drafts
    me = (ws.person().name or "").split(" ")[0] or "Me"
    out = []
    for t in ws.threads().threads:
        if t.last_from != "you" or (now - t.last_at).days < days:
            continue
        if any(d.thread_id == t.id and d.created_at >= t.last_at for d in drafts):
            continue  # already followed up (or drafted) since your last message
        c = next((contacts[cid] for cid in t.contact_ids if cid in contacts and contacts[cid].emails), None)
        if c is None:
            continue
        body = FOLLOW_UP.format(
            first=c.name.split(" ")[0].rstrip(","), subject=t.subject or "my last email", me=me
        )
        out.append(compose(ws, c.id, f"Re: {t.subject}".strip()[:200] if t.subject else "Following up", body,
                           purpose="follow_up", drafted_by="follow-up", thread_id=t.id))  # fmt: skip
    return out
