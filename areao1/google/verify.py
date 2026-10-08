"""Verifying an opportunity found in mail (ADR 0016 §3).

Verified = the sender check passed AND a page on the sender's organizational domain (or Devpost / MLH) mentions the
event and one of the email's dates. Links in the email are tried first; otherwise one hosted search restricted to
those domains, on the mundane tier. If the sender check failed the find is suspicious and nothing is sent; otherwise
it's unconfirmed, a short check-in to the organizer is drafted behind Approve & send, and a later message from them
marks it confirmed."""

from __future__ import annotations

import re
from email.utils import parseaddr
from typing import Any
from urllib.parse import urlparse

from areao1.core import clock
from areao1.criteria.case import Case
from areao1.criteria.models import MailItem
from areao1.google import eml, mailview, opportunities

PLATFORMS = ("devpost.com", "mlh.io")
FREEMAIL = ("gmail.com", "googlemail.com", "outlook.com", "hotmail.com", "live.com", "yahoo.com", "icloud.com",
            "me.com", "proton.me", "protonmail.com", "aol.com")  # fmt: skip
MAX_PAGES = 3
STOP = {"the", "and", "for", "you", "your", "with", "from", "invitation", "invite", "invited", "judge", "judging",
        "judges", "review", "reviewer", "call", "join", "event", "this", "that", "our", "are", "will", "re", "fwd"}  # fmt: skip
CHECK_IN = """Hi {first},

Thank you for the invitation to {event}. Before I confirm, could you send me the event page and the details (dates and the role)? I want to be sure I have everything right.

Best,
{me}"""


def host(url: str) -> str:
    h = (urlparse(url).hostname or "").lower()
    return h[4:] if h.startswith("www.") else h


def allowed_domains(sender_domain: str) -> list[str]:
    """Where an official page may live: the sender's organization (not a free mail provider) and the platforms."""
    org = eml._org(sender_domain) if sender_domain else ""
    return [*([org] if org and org not in FREEMAIL else []), *PLATFORMS]


def on_allowed(url: str, domains: list[str]) -> bool:
    h = host(url)
    return bool(h) and any(h == d or h.endswith("." + d) for d in domains)


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _skeleton(label: str) -> str:
    """What a look-alike reads as: digits and letter pairs that imitate letters, and hyphens, folded away."""
    s = label.lower().replace("-", "")
    for a, b in (("rn", "m"), ("vv", "w"), ("0", "o"), ("1", "l"), ("3", "e"), ("5", "s"), ("i", "l")):
        s = s.replace(a, b)
    return s


def imitation(sender_domain: str, event: str, known: list[str]) -> str | None:
    """Why the sender's domain looks deceptive, or None: a domain hidden in a subdomain (examplehacks.org.evil.co),
    or a near-miss of the event's name or a known organizer (examp1ehacks.org, example-hacks.org for
    examplehacks.org)."""
    d = sender_domain.lower()
    if re.search(r"\.(com|org|net|edu|gov|io)\.[a-z0-9-]+\.[a-z]{2,}$", d):
        return f"{d} hides another domain in front of its real one ({eml._org(d)})"
    label = eml._org(d).split(".")[0]
    named = "".join(tokens(event))
    for brand in {named, *(eml._org(k).split(".")[0] for k in known)}:
        if len(brand) < 6 or label == brand or (brand == named and label.replace("-", "") == brand):
            continue  # the brand itself (an event's own domain may be hyphenated; a known domain's isn't)
        if _skeleton(label) == _skeleton(brand) or (len(label) >= 6 and _lev(label, brand) <= 2):
            return f"{eml._org(d)} looks like an imitation of {brand}"
    return None


def tokens(name: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", name.lower())
    return [w for w in words if len(w) >= 3 and w not in STOP and not re.fullmatch(r"(19|20)\d\d", w)]


def page_confirms(text: str, event: str, dates: list[Any]) -> tuple[bool, str]:
    """(confirmed, why): most of the event name's words, and one of the email's dates, appear on the page."""
    low = text.lower()
    words = tokens(event)
    if not words:
        return False, "the email names no event to look for"
    hit = [w for w in words if re.search(rf"\b{re.escape(w)}\b", low)]
    if len(hit) < max(1, round(len(words) * 0.6)):
        return False, f"the page doesn't name the event ({', '.join(words)})"
    if not dates:
        return False, "the email gives no date to match"
    on_page = opportunities.dates_in(text, min(dates))
    same = sorted(set(dates) & on_page)
    if not same:
        return False, "the page doesn't show the email's dates"
    return True, f"the page names the event and {same[0].isoformat()}"


async def confirm_on_web(ws: Case, info: dict[str, Any], engine: Any = None, model: str = "",
                         fetch: Any = None) -> tuple[str | None, str, float]:  # fmt: skip
    """(confirming URL or None, why, cost). ``fetch`` (url -> (url, title, text)) is injectable for tests."""
    from areao1.web import fetch_page

    fetch = fetch or (lambda u: fetch_page(u))
    sender = parseaddr(info["headers"].get("From", ""))[1].rpartition("@")[2].lower()
    domains = allowed_domains(sender)
    urls = [u for u in info["links"] if on_allowed(u, domains)][:MAX_PAGES]
    cost, why = 0.0, "no link in the email on the organizer's site, Devpost or MLH"
    if not urls and engine is not None and info["event"]:
        year = str(info["dates"][0].year if info["dates"] else clock.today().year)
        query = info["event"] if year in info["event"] else f"{info['event']} {year}"
        try:
            found = await engine.hosted_search(None, query, domains, model)
        except Exception as exc:  # noqa: BLE001  (no search: stays unconfirmed)
            return None, f"couldn't search the web ({exc})", cost
        cost += found.cost_usd
        urls = [u for u in found.sources if on_allowed(u, domains)][:MAX_PAGES]
        why = "no official page found by a search of " + ", ".join(domains)
    for url in urls:
        try:
            final, _, text = await fetch(url)
        except Exception:  # noqa: BLE001  (unreachable or refused: try the next)
            continue
        if not on_allowed(final, domains):  # redirected off the organizer's site
            continue
        ok, reason = page_confirms(text, info["event"], info["dates"])
        if ok:
            return final, reason, cost
        why = reason
    return None, why, cost


def draft_check_in(ws: Case, item: MailItem, info: dict[str, Any]) -> str | None:
    """A short check-in to the organizer, drafted behind Approve & send. Adds them to Contacts as an organizer if
    needed. Returns the draft id."""
    from areao1.google import outreach
    from areao1.service import Service

    name, addr = parseaddr(info["headers"].get("From", ""))
    addr = addr.lower()
    if not addr:
        return None
    svc = Service(ws, actor="opportunities")
    contact = next((c for c in ws.contacts().contacts if addr in c.emails), None)
    if contact is None:
        contact = svc.add_contact(name=(name or addr.split("@")[0])[:120], emails=[addr], relationship="organizer",
                                  notes="Added by the daily opportunity check to confirm an invitation.")  # fmt: skip
    me = (ws.person().name or "").split(" ")[0] or "Me"
    body = CHECK_IN.format(first=(name or "there").split(" ")[0].strip(",") or "there", event=info["event"] or "your event",
                           me=me)  # fmt: skip
    draft = outreach.compose(ws, contact.id, f"Re: {info['headers'].get('Subject', '')}".strip()[:200], body,
                             purpose="ask", drafted_by="opportunities", thread_id=item.thread_id)  # fmt: skip
    return svc.save_draft(draft).id


def verifier(engine: Any = None, model: str = "", fetch: Any = None) -> Any:
    """The verifier the daily run calls per find: (verification, note, url, cost)."""

    async def verify(ws: Case, item: MailItem, info: dict[str, Any]) -> tuple[str, str, str | None, float]:
        auth = info["auth"]
        sender = eml.describe(auth) if auth.get("verdict") else "No sender check"
        if auth.get("verdict") == "failed":
            return "suspicious", f"{sender}. No check-in was drafted.", None, 0.0
        domain = parseaddr(info["headers"].get("From", ""))[1].rpartition("@")[2].lower()
        known = [
            *mailview.DOMAINS,
            *PLATFORMS,
            *(e.rpartition("@")[2] for c in ws.contacts().contacts for e in c.emails),
        ]
        fake = imitation(domain, info["event"], known)
        if fake:
            return (
                "suspicious",
                f"The sender's domain is suspicious: {fake}. No check-in was drafted.",
                None,
                0.0,
            )
        url, why, cost = (None, "web confirmation is off", 0.0)
        if ws.config().opportunities.verify_on_web:
            url, why, cost = await confirm_on_web(ws, info, engine, model, fetch)
        if auth.get("verdict") == "verified" and url:
            return "verified", f"{sender}; {why} ({url}).", url, cost
        draft = draft_check_in(ws, item, info)
        page = f"confirmed on {url}" if url else why
        return ("unconfirmed", f"{sender}; {page}. A check-in to the organizer is drafted on Contacts"
                + (" for your approval." if draft else "."), url, cost)  # fmt: skip

    return verify


def confirm_replies(ws: Case) -> int:
    """Unconfirmed finds whose organizer answered after the check-in was sent become confirmed. Returns how many."""
    from areao1.service import Service

    sent = {d.contact_id: d.sent_at for d in ws.outreach().drafts
            if d.drafted_by == "opportunities" and d.status == "sent" and d.sent_at}  # fmt: skip
    if not sent:
        return 0
    by_email = {e: c.id for c in ws.contacts().contacts for e in c.emails}
    items = ws.mailbox().items
    n = 0
    for cand in ws.pending_candidates():
        if cand.verification != "unconfirmed" or not cand.fingerprint.startswith("opp:"):
            continue
        who = str(cand.facts.get("from", "")).lower()
        cid = by_email.get(who)
        asked = sent.get(cid) if cid else None
        if asked is None:
            continue
        if any(i.from_addr == who and not i.outgoing and i.at > asked for i in items):
            Service(ws, actor="opportunities").set_verification(
                cand.id, "confirmed", f"{who} replied to your check-in."
            )
            n += 1
    return n
