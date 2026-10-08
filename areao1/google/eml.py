"""Emails from other accounts (ADR 0014, amendment): a dropped .eml file, or the original attached to a message
forwarded as an attachment. The original file is kept as the exhibit source (the upload pipeline), and on top of a
plain upload it gets: sender authentication from its original headers, the Mail view's rules for the category,
and a stage from the text (completed only on explicit completion; otherwise invited)."""

from __future__ import annotations

import re
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr, parsedate_to_datetime
from typing import Any

from areao1.core import clock

# Category -> (criterion, evidence type). A membership goes to Membership; the rest stays "you decide".
CRITERIA: dict[str, tuple[str, str]] = {
    "judging": ("judging", "judge_invite"),
    "reviewer": ("judging", "reviewer_record"),
    "awards": ("awards", "award_notice"),
    "press": ("press", "media_mention"),
}
COMPLETED = re.compile(
    r"thank(s| you) for (judging|serving|reviewing|your review|being a judge|participating as a judge)"
    r"|your reviews? (has|have) been (submitted|received|completed)|certificate of (appreciation|participation|service)"
    r"|you (have been|were|are) (selected|awarded|elected|admitted|accepted) as|congratulations on (winning|being "
    r"(selected|elected|awarded))|we are pleased to (confirm|announce) (that )?you",
    re.I,
)


def parse(content: bytes) -> EmailMessage:
    msg = BytesParser(policy=default).parsebytes(content)
    if not msg.get("From") and not msg.get("Subject"):
        raise ValueError("this doesn't look like an email (no From or Subject header)")
    return msg  # type: ignore[return-value]


def _org(domain: str) -> str:
    """The organizational domain, roughly: the last two labels (three under a two-letter country suffix like co.uk)."""
    labels = domain.lower().strip(".").split(".")
    n = (
        3
        if len(labels) >= 3
        and len(labels[-1]) == 2
        and labels[-2] in ("co", "ac", "com", "org", "edu", "gov")
        else 2
    )
    return ".".join(labels[-n:])


def authentication(headers: Any) -> dict[str, Any]:
    """The receiving server's verdict, from the topmost Authentication-Results (else ARC-Authentication-Results).
    ``headers`` is a message or a mapping with get_all. Returns {verdict, spf, dkim, dmarc, dkim_domain,
    from_domain, aligned, by}: verdict is "verified" (DMARC pass, or DKIM pass for the From domain's organization),
    "failed" (an explicit fail) or "unverified" (no results)."""
    get_all = (
        headers.get_all
        if hasattr(headers, "get_all")
        else (lambda k, d=None: [headers[k]] if headers.get(k) else d)
    )
    results = get_all("Authentication-Results") or get_all("ARC-Authentication-Results") or []
    from_domain = parseaddr(str(headers.get("From", "") or ""))[1].rpartition("@")[2].lower()
    out: dict[str, Any] = {"verdict": "unverified", "spf": None, "dkim": None, "dmarc": None, "dkim_domain": None,
                           "from_domain": from_domain or None, "aligned": False, "by": None}  # fmt: skip
    if not results:
        return out
    top = re.sub(r"\s+", " ", str(results[0]))
    top = re.sub(r"^\s*i=\d+;\s*", "", top)  # ARC instance tag
    out["by"] = top.split(";", 1)[0].strip().split(" ")[0] or None
    for method in ("spf", "dmarc"):
        m = re.search(rf"\b{method}=(\w+)", top, re.I)
        out[method] = m.group(1).lower() if m else None
    dkims = re.findall(r"\bdkim=(\w+)(?:[^;]*?header\.(?:d|i)=@?([\w.-]+))?", top, re.I)
    passing = [d.lower().rpartition("@")[2] for r, d in dkims if r.lower() == "pass" and d]
    if dkims:
        out["dkim"] = "pass" if any(r.lower() == "pass" for r, _ in dkims) else dkims[0][0].lower()
    aligned = next((d for d in passing if from_domain and _org(d) == _org(from_domain)), None)
    out["dkim_domain"] = aligned or (passing[0] if passing else None)
    out["aligned"] = aligned is not None
    if out["dmarc"] == "pass" or aligned:
        out["verdict"] = "verified"
    elif "fail" in (out["dmarc"], out["dkim"], out["spf"]) or out["dmarc"] in ("quarantine", "reject"):
        out["verdict"] = "failed"
    return out


def describe(auth: dict[str, Any]) -> str:
    if auth["verdict"] == "verified":
        how = "DMARC passed" if auth["dmarc"] == "pass" else f"DKIM passed for {auth['dkim_domain']}"
        return f"Verified sender ({how}, checked by {auth['by'] or 'the receiving server'})"
    if auth["verdict"] == "failed":
        bad = ", ".join(
            f"{k.upper()} {auth[k]}" for k in ("dmarc", "dkim", "spf") if auth[k] and auth[k] != "pass"
        )
        return f"Sender authentication failed ({bad})"
    return "Sender not verified (no authentication results in the original headers)"


def stage_of(text: str) -> str:
    """completed only on explicit completion; everything else is an invitation."""
    return "completed" if COMPLETED.search(text or "") else "invited"


def _quote(text: str) -> str:
    """One sentence from the message, the most telling one, for the summary."""
    flat = re.sub(r"\s+", " ", text or "").strip()
    flat = re.sub(
        r"^(hi|hello|hey|dear|greetings)\b[^,.!?]{0,60}[,!]\s*", "", flat, flags=re.I
    )  # the greeting
    sentences = re.split(r"(?<=[.!?])\s+", flat)
    hit = COMPLETED.search(flat)
    for s in sentences:
        if hit and hit.group(0) in s:
            return s[:240]
    for s in sentences:
        if (
            re.search(r"invit|judg|review|award|panel|speak|interview|nominat|member", s, re.I)
            and len(s) > 20
        ):
            return s[:240]
    return next((s[:240] for s in sentences if len(s) > 20), "")


def read(content: bytes, ws: Any) -> dict[str, Any]:
    """Everything the pipeline needs from one email, in memory: headers, text, authentication, category, stage."""
    from areao1.google import mail, mailview

    msg = parse(content)
    text = mail._text(msg)
    headers = {k: str(msg.get(k, "") or "") for k in ("From", "To", "Cc", "Subject", "Date")}
    contacts = {e: c for c in ws.contacts().contacts for e in c.emails}
    decided = mailview.by_rules({"headers": headers}, ws.mailbox().rules, contacts, mail.address())
    if decided is None and mailview._keyword(text[:600]):  # the subject said nothing; the first lines may
        cat, word = mailview._keyword(text[:600])  # type: ignore[misc]
        decided = (cat, "rule", f"the text says {word!r}")
    try:
        when = parsedate_to_datetime(headers["Date"]) if headers["Date"] else None
    except (TypeError, ValueError):
        when = None
    return {"msg": msg, "headers": headers, "text": text, "auth": authentication(msg), "when": when,
            "category": decided[0] if decided and decided[0] != "hide" else None,
            "why": decided[2] if decided else "", "stage": stage_of(text)}  # fmt: skip


def candidate_fields(info: dict[str, Any], filename: str, size: str) -> dict[str, Any]:
    """The Inbox candidate's fields for one email (the caller adds the attachment and fingerprint)."""
    h, auth = info["headers"], info["auth"]
    cat = info["category"]
    crit, etype = CRITERIA.get(cat or "", ("", "document"))
    subject = (h["Subject"] or filename).strip()
    if cat == "awards" and re.search(r"member", subject, re.I):
        crit, etype = "membership", "membership_letter"
    name, addr = parseaddr(h["From"])
    when = clock.local_date(info["when"]).isoformat() if info["when"] else "an unknown date"
    quote = _quote(info["text"])
    summary = (f"Email from {name or addr} <{addr}>, {when}. {describe(auth)}."
               + (f' "{quote}"' if quote else "")
               + (f" Sorted as {cat} ({info['why']})." if cat else " No rule placed it: choose the criterion."))  # fmt: skip
    return {"evidence_type": etype, "proposed_criterion": crit, "title": subject[:120], "summary": summary[:1000],
            "document_date": clock.local_date(info["when"]) if info["when"] else None,
            "date_source": "email" if info["when"] else None,
            "confidence": (0.7 if auth["verdict"] == "verified" else 0.45) if crit else 0.3,
            "stage": _stage(info["stage"], crit, cat),
            "facts": {"from": addr, "date": when, "sender_auth": auth["verdict"],
                      **({"dkim_domain": auth["dkim_domain"]} if auth["dkim_domain"] else {}),
                      **({"checked_by": auth["by"]} if auth["by"] else {}), "file": filename[:120], "size": size}}  # fmt: skip


def _stage(read_stage: str, criterion: str, category: str | None) -> str | None:
    """Judging and talks: invited or completed. Awards and memberships: granted only on explicit completion."""
    if criterion == "judging" or category == "invites":
        return read_stage
    if criterion in ("awards", "membership"):
        return "granted" if read_stage == "completed" else None
    return None
