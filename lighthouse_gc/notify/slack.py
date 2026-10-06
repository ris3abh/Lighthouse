"""Slack incoming webhook. The webhook URL is a secret: store it with `lighthouse-gc secret set <ref>`."""

from __future__ import annotations

from lighthouse_gc.core.models import ChannelConfig
from lighthouse_gc.notify import Notification, NotifyError
from lighthouse_gc.notify._http import post

PREFIX = "https://hooks.slack.com/"


class Slack:
    def send(self, note: Notification, cfg: ChannelConfig, secret: str | None) -> None:
        if not secret:
            raise NotifyError(f"no webhook URL in the keychain for {cfg.secret_ref!r}")
        if not secret.startswith(PREFIX):
            raise NotifyError(f"refusing to post: Slack webhook URLs start with {PREFIX}")
        text = f"*{note.title}*\n{note.body}" + (f"\n<{note.url}|Open Lighthouse>" if note.url else "")
        post(secret, json={"text": text})
