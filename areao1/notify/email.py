"""Email over SMTP (STARTTLS by default). The SMTP password lives in the keychain under ``secret_ref``."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from areao1.core.models import ChannelConfig
from areao1.notify import Notification, NotifyError


class Email:
    def send(self, note: Notification, cfg: ChannelConfig, secret: str | None) -> None:
        if not (cfg.host and cfg.from_addr and cfg.to_addr):
            raise NotifyError("email channel needs host, from_addr and to_addr")
        msg = EmailMessage()
        msg["Subject"] = f"[Area O1] {note.title}"
        msg["From"] = cfg.from_addr
        msg["To"] = cfg.to_addr
        msg.set_content(note.body + (f"\n\nOpen Area O1: {note.url}" if note.url else ""))
        try:
            if cfg.port == 465:
                server: smtplib.SMTP = smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=20)
            else:
                server = smtplib.SMTP(cfg.host, cfg.port, timeout=20)
            with server:
                if cfg.starttls and cfg.port != 465:
                    server.starttls()
                if cfg.username:
                    if not secret:
                        raise NotifyError(f"no SMTP password in the keychain for {cfg.secret_ref!r}")
                    server.login(cfg.username, secret)
                server.send_message(msg)
        except (OSError, smtplib.SMTPException) as exc:
            raise NotifyError(f"SMTP: {exc}") from exc
