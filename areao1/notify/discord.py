"""Discord webhook. The webhook URL is a secret: store it with `areao1 secret set <ref>`."""

from __future__ import annotations

from areao1.core.models import ChannelConfig
from areao1.notify import Notification, NotifyError
from areao1.notify._http import post

PREFIXES = ("https://discord.com/api/webhooks/", "https://discordapp.com/api/webhooks/")
LIMIT = 2000


class Discord:
    def send(self, note: Notification, cfg: ChannelConfig, secret: str | None) -> None:
        if not secret:
            raise NotifyError(f"no webhook URL in the keychain for {cfg.secret_ref!r}")
        if not secret.startswith(PREFIXES):
            raise NotifyError("refusing to post: not a discord.com webhook URL")
        content = f"**{note.title}**\n{note.body}"
        if len(content) > LIMIT:
            content = content[: LIMIT - 1] + "…"
        # Never let a deadline title ping @everyone.
        post(secret, json={"content": content, "allowed_mentions": {"parse": []}})
