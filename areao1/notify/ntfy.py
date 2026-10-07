"""ntfy.sh (or self-hosted ntfy) push. Pick an unguessable topic; an access token can live in the keychain."""

from __future__ import annotations

from areao1.core.models import ChannelConfig
from areao1.notify import Notification, NotifyError
from areao1.notify._http import post

PRIORITY = {"low": "2", "default": "3", "high": "4"}


def _header(text: str) -> str:
    # HTTP headers must be latin-1; ntfy accepts RFC 2047 for anything else.
    try:
        text.encode("latin-1")
        return text
    except UnicodeEncodeError:
        import base64

        return "=?UTF-8?B?" + base64.b64encode(text.encode()).decode() + "?="


class Ntfy:
    def send(self, note: Notification, cfg: ChannelConfig, secret: str | None) -> None:
        if not cfg.topic:
            raise NotifyError("ntfy channel needs a topic")
        if not cfg.server.startswith("https://") and not cfg.server.startswith("http://127.0.0.1"):
            raise NotifyError("ntfy server must use https")
        headers = {"Title": _header(note.title), "Priority": PRIORITY[note.priority], "Tags": "areao1"}
        if note.url and not note.url.startswith("http://127.0.0.1"):
            headers["Click"] = note.url  # a phone can't open the laptop's localhost
        if secret:
            headers["Authorization"] = f"Bearer {secret}"
        post(f"{cfg.server.rstrip('/')}/{cfg.topic}", content=note.body.encode(), headers=headers)
