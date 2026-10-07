"""In-memory Gmail over IMAP and SMTP: just enough of both for app-password sign-in, header-only reads and
sending. Every command is recorded so tests can check what was (and wasn't) asked for."""

from __future__ import annotations

import imaplib
import re
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import getaddresses


@dataclass
class Stored:
    uid: int
    thrid: int
    date: str  # INTERNALDATE, e.g. "07-Oct-2026 09:30:00 +0000"
    frm: str
    to: str
    subject: str
    cc: str = ""
    message_id: str = ""
    body: str = "This body must never be fetched for contact threads."

    def header_bytes(self) -> bytes:
        lines = [f"From: {self.frm}", f"To: {self.to}", f"Subject: {self.subject}", f"Date: {self.date}"]
        if self.cc:
            lines.append(f"Cc: {self.cc}")
        if self.message_id:
            lines.append(f"Message-ID: {self.message_id}")
        return ("\r\n".join(lines) + "\r\n\r\n").encode()

    def addresses(self) -> set[str]:
        return {a.lower() for _, a in getaddresses([self.frm, self.to, self.cc]) if a}


@dataclass
class FakeGmail:
    """One account. ``login_error`` is Gmail's answer to a refused login (None accepts the right password)."""

    email: str = "alex@gmail.com"
    password: str = "abcdefghijklmnop"
    login_error: str | None = None
    imap_disabled: bool = False
    messages: list[Stored] = field(default_factory=list)
    commands: list[tuple] = field(default_factory=list)
    sent: list[EmailMessage] = field(default_factory=list)
    smtp_logins: list[tuple[str, str]] = field(default_factory=list)

    def add(self, thrid: int, date: str, frm: str, to: str, subject: str, **kw) -> Stored:
        m = Stored(uid=len(self.messages) + 1, thrid=thrid, date=date, frm=frm, to=to, subject=subject, **kw)
        self.messages.append(m)
        return m

    def install(self, monkeypatch) -> FakeGmail:
        from areao1.google import mail

        gmail = self

        class IMAP:
            def __init__(self, host, port=993, timeout=None):
                assert (host, port) == (mail.IMAP_HOST, 993)
                self.selected: str | None = None
                self.readonly = False

            def login(self, user, password):
                gmail.commands.append(("LOGIN", user))
                if gmail.imap_disabled:
                    raise imaplib.IMAP4.error(
                        "[ALERT] Your account is not enabled for IMAP use. Please visit your Gmail settings page "
                        "and enable your account for IMAP access. (Failure)"
                    )
                if gmail.login_error:
                    raise imaplib.IMAP4.error(gmail.login_error)
                if (user, password) != (gmail.email, gmail.password):
                    raise imaplib.IMAP4.error("[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
                return "OK", [b"LOGIN completed"]

            def logout(self):
                return "BYE", [b""]

            def list(self, directory='""', pattern="*"):
                gmail.commands.append(("LIST",))
                return "OK", [b'(\\HasNoChildren) "/" "INBOX"',
                              b'(\\All \\HasNoChildren) "/" "[Gmail]/Alle Nachrichten"',  # localized: found by \\All
                              b'(\\HasNoChildren \\Sent) "/" "[Gmail]/Sent Mail"']  # fmt: skip

            def select(self, mailbox, readonly=False):
                gmail.commands.append(("SELECT", mailbox, readonly))
                self.selected, self.readonly = mailbox, readonly
                return "OK", [str(len(gmail.messages)).encode()]

            def uid(self, command, *args):
                gmail.commands.append(("UID", command, *args))
                assert self.selected == '"[Gmail]/Alle Nachrichten"' and self.readonly
                if command == "SEARCH":
                    assert args[0] == "X-GM-RAW"
                    raw = args[1].strip('"')
                    wanted = set(re.findall(r"(?:from|to|cc):(\S+)", raw))
                    hits = [str(m.uid) for m in gmail.messages if m.addresses() & wanted]
                    return "OK", [" ".join(hits).encode()]
                if command == "FETCH":
                    uids, spec = args
                    assert "BODY.PEEK[HEADER.FIELDS" in spec and "RFC822" not in spec and "BODY[]" not in spec
                    out: list = []
                    for u in uids.split(","):
                        m = next(x for x in gmail.messages if x.uid == int(u))
                        h = m.header_bytes()
                        meta = (f'{m.uid} (UID {m.uid} X-GM-THRID {m.thrid} INTERNALDATE "{m.date}" '
                                f"BODY[HEADER.FIELDS (FROM TO CC SUBJECT DATE MESSAGE-ID)] {{{len(h)}}}")  # fmt: skip
                        out += [(meta.encode(), h), b")"]
                    return "OK", out
                raise AssertionError(f"unexpected UID {command}")

        class SMTP:
            def __init__(self, host, port=465, timeout=None):
                assert (host, port) == (mail.SMTP_HOST, 465)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def login(self, user, password):
                gmail.smtp_logins.append((user, password))
                if (user, password) != (gmail.email, gmail.password):
                    raise smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted.")

            def send_message(self, msg):
                gmail.sent.append(msg)
                return {}

        monkeypatch.setattr(mail, "IMAP", IMAP)
        monkeypatch.setattr(mail, "SMTP", SMTP)
        return self
