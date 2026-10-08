"""The daily opportunity job (ADR 0016): opportunity mail becomes Inbox items, each with its stage and a verification.

Reuses the Mail view (its rules, Promotions / Social filtered, a forward's attached original), the sender check and
the .eml stage rule. A message's text is read in memory (PEEK); only facts and one quoted sentence are kept."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

import anyio

from areao1.core import clock
from areao1.core.models import Candidate
from areao1.criteria.case import Case
from areao1.criteria.models import MailItem
from areao1.google import eml, mail, mailview

FIND_CATEGORIES = ("invites", "judging", "reviewer", "press", "awards")
MAX_FINDS = 20  # per run
MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov",
                                      "dec"), 1)}  # fmt: skip
_MON = r"(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?"
_DATES = [
    re.compile(rf"\b{_MON}\s+(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*[-–]\s*\d{{1,2}})?(?:,?\s+(\d{{4}}))?", re.I),
    re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?(?:\s*[-–]\s*\d{{1,2}})?\s+{_MON}(?:,?\s+(\d{{4}}))?", re.I),
    re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b"),
]
URL = re.compile(r"https?://[^\s<>\"')\]]+", re.I)


def dates_in(text: str, around: date | None = None) -> set[date]:
    """Dates written in ``text`` ("November 8, 2026", "8 Nov", "Nov 7-8", "2026-11-08"). A date with no year takes
    the next one on or after ``around`` (the email's date)."""
    around = around or clock.today()
    out: set[date] = set()

    def add(y: int | None, m: int, d: int) -> None:
        try:
            when = date(y or around.year, m, d)
            if y is None and when < around:
                when = date(around.year + 1, m, d)
            out.add(when)
        except ValueError:
            pass

    for m in _DATES[0].finditer(text):
        add(int(m.group(3)) if m.group(3) else None, MONTHS[m.group(1).lower()[:3]], int(m.group(2)))
    for m in _DATES[1].finditer(text):
        add(int(m.group(3)) if m.group(3) else None, MONTHS[m.group(2).lower()[:3]], int(m.group(1)))
    for m in _DATES[2].finditer(text):
        add(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return out


def links_in(text: str) -> list[str]:
    return list(dict.fromkeys(u.rstrip(".,;:!?") for u in URL.findall(text or "")))[:30]


def event_name(subject: str) -> str:
    """The subject without reply / forward prefixes and invitation boilerplate."""
    s = re.sub(r"^\s*((re|fwd?|aw|fw)\s*:\s*)+", "", subject or "", flags=re.I)
    s = re.sub(r"^(you'?re invited( to (judge|speak|review))?|invitation( to (judge|review|speak)( at| for)?)?|"
               r"invite( to judge)?|join us( as a judge)?)\b\s*[:\-–]?\s*", "", s, flags=re.I)  # fmt: skip
    return s.strip()[:120]


def gmail_link(item: MailItem) -> str:
    return f"https://mail.google.com/mail/u/0/#all/{item.thread_id}"


def finds(ws: Case) -> list[MailItem]:
    """New mail in the opportunity categories the job hasn't looked at; dropped .eml files went to the Inbox."""
    box = ws.mailbox()
    done = set(box.processed)
    return [i for i in box.items
            if i.category in FIND_CATEGORIES and i.source == "gmail" and i.id not in done and not i.outgoing][:MAX_FINDS]  # fmt: skip


def read_find(ws: Case, item: MailItem) -> dict[str, Any]:
    """The find's text in memory (PEEK, or the forward's attached original) and what the pipeline needs from it."""
    msg = mailview.open_item(ws, item.id)
    text = msg.get("text", "")
    when = item.at
    headers = {"From": msg.get("from", ""), "To": msg.get("to", ""), "Cc": msg.get("cc", ""),
               "Subject": msg.get("subject", "") or item.subject, "Date": msg.get("date", "")}  # fmt: skip
    return {"headers": headers, "text": text, "when": when, "category": item.category, "why": item.why,
            "stage": eml.stage_of(text), "auth": dict(item.auth or {"verdict": "unverified", "dmarc": None,
                                                                    "dkim": None, "spf": None, "dkim_domain": None,
                                                                    "by": None}),
            "dates": sorted(dates_in(f"{headers['Subject']}\n{text}", clock.local_date(when))),
            "links": links_in(text), "event": event_name(headers["Subject"])}  # fmt: skip


def candidate(
    item: MailItem, info: dict[str, Any], verification: str, note: str, url: str | None = None
) -> Candidate:
    fields = eml.candidate_fields(info, f"{info['event'] or 'email'}.eml", "")
    facts = {k: v for k, v in fields.pop("facts").items() if k not in ("file", "size")}
    if info["dates"]:
        facts["dates"] = ", ".join(d.isoformat() for d in info["dates"][:6])
    return Candidate(fingerprint=f"opp:{item.id}", source=f"gmail:{item.thread_id}", raw_url=url or gmail_link(item),
                     source_tier="user", facts=facts, verification=verification, verification_note=note[:500],  # type: ignore[arg-type]
                     **fields)  # fmt: skip


async def run(ws: Case, mundane: Any = None, verifier: Any = None) -> dict[str, Any]:
    """One pass: refresh the Mail view, then each new find becomes an Inbox item. ``verifier`` (F3) confirms finds;
    without it every find is unconfirmed (or suspicious when the sender check failed)."""
    from areao1.service import Service

    if not mail.connected():
        return {"lines": ["skipped: Gmail isn't connected (Settings > Gmail)"], "cost_usd": 0.0, "finds": []}
    from areao1.google import verify

    synced = await mailview.sync(ws, mundane)
    cost = float(synced.get("cost_usd") or 0.0)
    confirmed = verify.confirm_replies(ws)  # organizers who answered a check-in
    svc = Service(ws, actor="opportunities")
    proposed: list[Candidate] = []
    looked: list[str] = []
    threads = {c.source for c in ws.inbox().candidates}
    for item in finds(ws):
        looked.append(item.id)
        if f"gmail:{item.thread_id}" in threads:
            continue  # a reply in a thread already in the Inbox
        try:
            info = read_find(ws, item)
        except (mail.MailError, KeyError, ValueError):
            continue  # gone from Gmail, or unreadable: try again tomorrow
        if verifier is not None:
            verification, note, url, spent = await verifier(ws, item, info)
            cost += spent
        elif info["auth"].get("verdict") == "failed":
            verification, note, url = (
                "suspicious",
                "The sender check failed: " + eml.describe(info["auth"]),
                None,
            )
        else:
            verification, note, url = "unconfirmed", eml.describe(info["auth"]), None
        cand = svc.propose_candidate(candidate(item, info, verification, note, url))
        if cand is not None:
            proposed.append(cand)
    box = ws.mailbox()
    box.processed = [*box.processed, *looked][-5000:]
    ws.save_mailbox(box)
    verified = sum(1 for c in proposed if c.verification == "verified")
    line = (f"Opportunities: {len(proposed)} new in your Inbox ({verified} verified)" if proposed
            else "Opportunities: nothing new") + (f"; {confirmed} confirmed by the organizer's reply" if confirmed else "")  # fmt: skip
    return {"lines": [*synced.get("lines", []), line], "cost_usd": round(cost, 6), "finds": proposed}


async def run_now(ws: Case, runner: Any = None) -> dict[str, Any]:
    """A run with the agent's tiers: the model sorts mail only if model sorting is on (mailview checks)."""
    from areao1.agent.runner import AgentRunner, BudgetExceeded

    runner = runner or AgentRunner(ws)

    def mundane() -> Any:
        try:
            return runner.mundane("classify")
        except BudgetExceeded:
            return None, runner.route("classify")

    from areao1.google import verify

    ok, _ = runner.engine().available()
    engine = runner.engine() if ok and hasattr(runner.engine(), "hosted_search") else None
    return await run(ws, mundane, verify.verifier(engine, runner.route("web_search").model))


def run_job(ws: Case, scheduled: bool = False) -> list[str]:
    """Scheduler / CLI entry point. Off unless opportunities.enabled (a hand-run always runs)."""
    if scheduled and not ws.config().opportunities.enabled:
        return ["skipped: the daily opportunity check is off (Settings > Gmail)"]
    try:
        out = anyio.run(run_now, ws, None)
    except mail.MailError as exc:
        return [f"Opportunities: {exc}"]
    return list(out["lines"])
