"""Slack incoming webhook. The webhook URL is a secret: store it with `areao1 secret set <ref>`."""

from __future__ import annotations

from areao1.core.models import ChannelConfig
from areao1.notify import Notification, NotifyError
from areao1.notify._http import post

PREFIX = "https://hooks.slack.com/"


class Slack:
    def send(self, note: Notification, cfg: ChannelConfig, secret: str | None) -> None:
        if not secret:
            raise NotifyError(f"no webhook URL in the keychain for {cfg.secret_ref!r}")
        if not secret.startswith(PREFIX):
            raise NotifyError(f"refusing to post: Slack webhook URLs start with {PREFIX}")
        text = f"*{note.title}*\n{note.body}" + (f"\n<{note.url}|Open Area O1>" if note.url else "")
        post(secret, json={"text": text})
