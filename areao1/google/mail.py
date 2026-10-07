"""Gmail with an app password (ADR 0014, amendment): no Google Cloud project, just your address and a 16-letter
app password, checked with one IMAP login and kept in the OS keychain only. ``IMAP`` and ``SMTP`` are the
connection classes, replaced in tests so no test reaches Google."""

from __future__ import annotations

import imaplib
import json
import re
import smtplib
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from typing import Any

IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
REF = "google:app-password"
APP_PASSWORDS = "https://myaccount.google.com/apppasswords"
TIMEOUT = 30

IMAP: Any = imaplib.IMAP4_SSL
SMTP: Any = smtplib.SMTP_SSL


class MailError(Exception):
    pass


def account() -> dict[str, str] | None:
    from areao1.core.secrets import get_secret

    raw = get_secret(REF)
    try:
        data = json.loads(raw) if raw else None
    except ValueError:
        return None
    if not isinstance(data, dict) or not data.get("email") or not data.get("password"):
        return None
    return {"email": str(data["email"]), "password": str(data["password"])}


def connected() -> bool:
    return account() is not None


def address() -> str:
    return (account() or {}).get("email", "").lower()


def status() -> dict[str, Any]:
    a = account()
    return {"connected": a is not None, "email": a["email"] if a else None}


def clean_password(password: str) -> str:
    """Google shows an app password as four groups of four; people paste it with or without the spaces."""
    return re.sub(r"\s+", "", password).lower()


def connect(email: str, password: str) -> dict[str, Any]:
    """Check the address and app password with one IMAP login, then keep them in the keychain."""
    from areao1.core.secrets import set_secret

    email, password = email.strip(), clean_password(password)
    if not re.fullmatch(r"[^@\s\"\\]+@[^@\s\"\\]+\.[^@\s\"\\]+", email):
        raise MailError("That doesn't look like an email address. Use the Gmail address you sign in with.")
    if not re.fullmatch(r"[a-z]{16}", password):
        raise MailError(
            "An app password is 16 letters (Google shows it as four groups of four). Your normal Google password "
            "won't work here. If the App passwords page says the setting isn't available, 2-Step Verification is "
            "off: turn it on first (step 1)."
        )
    with _imap(email, password):
        pass
    set_secret(REF, json.dumps({"email": email, "password": password}))
    return status()


def disconnect() -> dict[str, Any]:
    """Forget the app password here. Google has no API to revoke it: you remove it on the App passwords page."""
    from areao1.core.secrets import delete_secret

    delete_secret(REF)
    return status()


def plain_error(exc: BaseException, email: str = "") -> MailError:
    """What went wrong, in words: Gmail's IMAP and SMTP answers are terse and partly in codes."""
    text = str(exc).lower()
    if "not enabled for imap" in text or "imap access is disabled" in text or "imap is disabled" in text:
        return MailError(
            "IMAP is turned off for this Gmail account. In Gmail: Settings > See all settings > Forwarding and "
            "POP/IMAP > Enable IMAP, save, and try again. On a work or school account, your admin may need to "
            "allow it."
        )
    if "application-specific password required" in text:
        return MailError(
            "That's your normal Google password. Gmail needs an app password here: create one at "
            f"{APP_PASSWORDS} (step 2) and paste it instead."
        )
    if "web browser" in text or "webalert" in text:
        return MailError(
            "Google wants you to sign in once in your browser first (it noticed a new sign-in). Open gmail.com, "
            "then try again."
        )
    if (
        "authenticationfailed" in text
        or "invalid credentials" in text
        or "username and password not accepted" in text
    ):
        return MailError(
            f"Gmail didn't accept that app password{f' for {email}' if email else ''}. Check the address, or create a "
            "new app password (step 2) and paste it right away (Google shows each one only once). If you can't "
            "create one, 2-Step Verification is off: turn it on (step 1)."
        )
    if isinstance(exc, (OSError, TimeoutError)):
        return MailError("Couldn't reach Gmail. Check your internet connection and try again.")
    return MailError(f"Gmail said: {str(exc)[:200]}")


@contextmanager
def _imap(email: str, password: str) -> Iterator[Any]:
    try:
        conn = IMAP(IMAP_HOST, 993, timeout=TIMEOUT)
        conn.login(email, password)
    except (imaplib.IMAP4.error, OSError) as exc:
        raise plain_error(exc, email) from exc
    try:
        yield conn
    finally:
        with suppress(imaplib.IMAP4.error, OSError):
            conn.logout()


@contextmanager
def session() -> Iterator[Any]:
    """A logged-in IMAP connection with the saved app password."""
    a = account()
    if a is None:
        raise MailError("Gmail isn't connected (Settings > Gmail).")
    with _imap(a["email"], a["password"]) as conn:
        yield conn


# ------------------------------------------------------------------ reading: headers only, over IMAP

HEADER_FIELDS = "FROM TO CC SUBJECT DATE MESSAGE-ID"
_META = re.compile(rb'X-GM-THRID (\d+).*?INTERNALDATE "([^"]+)"', re.S)
BATCH = 200


def _all_mail(conn: Any) -> str:
    """Gmail's "All Mail", found by its \\All flag (its name is translated in other languages)."""
    _, boxes = conn.list()
    for line in boxes or []:
        text = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
        if "\\All" in text.split(")")[0]:
            name = text.rsplit(' "/" ', 1)[-1].strip()
            return name if name.startswith('"') else f'"{name}"'
    return "INBOX"


def _internaldate(raw: str) -> int:
    from datetime import datetime

    return int(datetime.strptime(raw.strip(), "%d-%b-%Y %H:%M:%S %z").timestamp() * 1000)


def threads(emails: list[str], days: int) -> list[tuple[str, list[tuple[int, dict[str, str]]]]]:
    """Gmail threads with any of ``emails`` in the last ``days``, as (thread ID, [(time in ms, headers)]).
    The mailbox is opened read-only and only header fields are fetched (with PEEK, so nothing turns read)."""
    from email.parser import BytesParser
    from email.policy import default

    safe = [e for e in emails if re.fullmatch(r"[^@\s\"\\()]+@[^@\s\"\\()]+", e)]
    found: dict[str, list[tuple[int, dict[str, str]]]] = {}
    with session() as conn:
        conn.select(_all_mail(conn), readonly=True)
        uids: set[int] = set()
        for e in safe:
            _, data = conn.uid("SEARCH", "X-GM-RAW", f'"from:{e} OR to:{e} OR cc:{e} newer_than:{days}d"')
            uids |= {int(u) for u in (data[0] or b"").split()}
        ordered = sorted(uids)
        for i in range(0, len(ordered), BATCH):
            batch = ",".join(str(u) for u in ordered[i : i + BATCH])
            _, data = conn.uid(
                "FETCH", batch, f"(X-GM-THRID INTERNALDATE BODY.PEEK[HEADER.FIELDS ({HEADER_FIELDS})])"
            )
            for part in data or []:
                if not isinstance(part, tuple):
                    continue
                meta = _META.search(part[0])
                if meta is None:
                    continue
                msg = BytesParser(policy=default).parsebytes(part[1], headersonly=True)
                headers = {
                    k: str(msg.get(k, "")) for k in ("From", "To", "Cc", "Subject", "Date", "Message-ID")
                }
                tid = format(int(meta.group(1)), "x")  # the same thread ID Gmail's API uses
                found.setdefault(tid, []).append((_internaldate(meta.group(2).decode()), headers))
    return sorted(found.items())


# ------------------------------------------------------------------ sending, over SMTP


def send(msg: Any) -> None:
    """Send one message you approved, from your Gmail (Gmail files it under Sent)."""
    a = account()
    if a is None:
        raise MailError("Gmail isn't connected (Settings > Gmail).")
    try:
        with SMTP(SMTP_HOST, 465, timeout=TIMEOUT) as conn:
            conn.login(a["email"], a["password"])
            conn.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise plain_error(exc, a["email"]) from exc
