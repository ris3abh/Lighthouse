"""Gmail with an app password (ADR 0014, amendment): no Google Cloud project, just your address and a 16-letter
app password, checked with one IMAP login and kept in the OS keychain only. ``IMAP`` and ``SMTP`` are the
connection classes, replaced in tests so no test reaches Google."""

from __future__ import annotations

import imaplib
import json
import re
import smtplib
from collections.abc import Iterator
from contextlib import contextmanager
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
        try:
            conn.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


@contextmanager
def session() -> Iterator[Any]:
    """A logged-in IMAP connection with the saved app password."""
    a = account()
    if a is None:
        raise MailError("Gmail isn't connected (Settings > Google > Connect Gmail).")
    with _imap(a["email"], a["password"]) as conn:
        yield conn
