"""Outreach (ADR 0014 §5): emails to your contacts, drafted by you, the agent or the follow-up job, and sent from
your Gmail only when you approve them. Case contacts only, a daily send limit, and the same guardrails as other
text the agent writes for your case. ``client`` is injectable so tests never reach Google."""

from __future__ import annotations

import base64
from email.message import EmailMessage
from typing import Any

import httpx

from areao1.agent.guardrails import guard_answer
from areao1.core import clock
from areao1.core.workspace import WorkspaceError
from areao1.criteria.case import Case
from areao1.criteria.models import OutreachDraft
from areao1.google import auth

SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"


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


def sent_today(ws: Case) -> int:
    today = clock.today()
    return sum(
        1
        for d in ws.outreach().drafts
        if d.status == "sent" and d.sent_at and clock.local_date(d.sent_at) == today
    )


def send(ws: Case, draft: OutreachDraft, client: httpx.Client | None = None) -> dict[str, Any]:
    """Send an approved draft from your Gmail. Returns Gmail's message (id, threadId)."""
    if draft.status != "draft":
        raise WorkspaceError(f"this email is already {draft.status}")
    contact = next((c for c in ws.contacts().contacts if c.id == draft.contact_id), None)
    if contact is None or draft.to.lower() not in contact.emails:
        raise WorkspaceError(
            "outreach goes to case contacts only: this address isn't on the contact any more"
        )
    if not auth.granted("gmail_send"):
        raise WorkspaceError(
            "Sending isn't connected: turn on 'Send drafts you approved' in Settings > Google"
        )
    limit = ws.config().outreach.daily_limit
    if sent_today(ws) >= limit:
        raise WorkspaceError(
            f"today's limit of {limit} emails is reached; it resets tomorrow (Settings: outreach.daily_limit)"
        )
    msg = EmailMessage()
    msg["To"] = draft.to
    me = (auth.token() or {}).get("email")
    if me:
        msg["From"] = me
    msg["Subject"] = draft.subject
    msg.set_content(draft.body)
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    payload: dict[str, Any] = {"raw": raw}
    if draft.thread_id:
        payload["threadId"] = draft.thread_id
    own = client is None
    c = client or httpx.Client(timeout=30)
    try:
        r = c.post(SEND_URL, json=payload, headers={"Authorization": f"Bearer {auth.access_token(c)}"})
    finally:
        if own:
            c.close()
    if r.status_code != 200:
        raise WorkspaceError(f"Gmail didn't send it ({r.status_code}); it's still a draft")
    return dict(r.json())


FOLLOW_UP = """Hi {first},

Just following up on my note about "{subject}". I know things get busy; whenever you have a moment, I'd be grateful
for a reply.

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
