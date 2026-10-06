"""Notifications: desktop, email (SMTP), Slack / Discord webhooks and ntfy push.

Channels are configured in ``lighthouse.yaml`` (``notifications.channels``) and each event type routes to
named channels (``notifications.routes``). Secrets (webhook URLs, SMTP password, ntfy token) stay in the OS
keychain under the channel's ``secret_ref``. Channels that leave this machine default to ``detail: minimal``
(counts only, no titles).

Every send is recorded in ``.lighthouse/cache/notifications.jsonl`` (local, gitignored). Jobs use that log
so the same alert isn't sent twice.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Literal, Protocol

from lighthouse_gc.core.models import ChannelConfig, utcnow
from lighthouse_gc.core.secrets import get_secret
from lighthouse_gc.core.workspace import Workspace

Priority = Literal["low", "default", "high"]


@dataclass
class Notification:
    event: str
    title: str
    body: str
    url: str | None = None
    priority: Priority = "default"
    minimal_body: str | None = None  # what a `detail: minimal` channel gets instead of title + body
    key: str | None = None  # stable id for de-duplication, e.g. "deadline:dl_123:3"

    def for_channel(self, cfg: ChannelConfig) -> Notification:
        if cfg.detail == "minimal" and self.minimal_body is not None:
            return Notification(
                self.event, "Lighthouse", self.minimal_body, self.url, self.priority, None, self.key
            )
        return self


class NotifyError(Exception):
    pass


class Channel(Protocol):
    def send(self, note: Notification, cfg: ChannelConfig, secret: str | None) -> None: ...


@dataclass
class SendResult:
    channel: str
    ok: bool
    error: str | None = None


@dataclass
class Report:
    event: str
    results: list[SendResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.results) and all(r.ok for r in self.results)

    def line(self) -> str:
        if not self.results:
            return f"{self.event}: no channels routed"
        return ", ".join(
            f"{r.channel}: {'sent' if r.ok else 'failed (' + (r.error or '') + ')'}" for r in self.results
        )


def _channels() -> dict[str, Channel]:
    from lighthouse_gc.notify import desktop, discord, email, ntfy, slack

    return {
        "desktop": desktop.Desktop(),
        "email": email.Email(),
        "slack": slack.Slack(),
        "discord": discord.Discord(),
        "ntfy": ntfy.Ntfy(),
    }


CHANNELS: Callable[[], dict[str, Channel]] = _channels


def send(ws: Workspace, note: Notification, only: str | None = None) -> Report:
    """Send ``note`` to every channel routed for its event (or just ``only``)."""
    cfg = ws.config().notifications
    names = [only] if only else cfg.routes.get(note.event, [])  # type: ignore[call-overload]
    impls = CHANNELS()
    report = Report(note.event)
    for name in names:
        ch = cfg.channels.get(name)
        if ch is None:
            report.results.append(SendResult(name, False, "no such channel in lighthouse.yaml"))
            continue
        if not ch.enabled:
            continue
        secret = get_secret(ch.secret_ref, ws.root) if ch.secret_ref else None
        try:
            impls[ch.kind].send(note.for_channel(ch), ch, secret)
            report.results.append(SendResult(name, True))
        except Exception as exc:  # a broken channel must never break a job
            report.results.append(SendResult(name, False, str(exc)[:200]))
    _log(ws, note, report)
    return report


def already_sent(ws: Workspace, key: str) -> bool:
    return any(entry.get("key") == key and entry.get("ok") for entry in history(ws))


def history(ws: Workspace, limit: int | None = None) -> list[dict]:
    path = ws.cache_dir / "notifications.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for line in lines[-limit:] if limit else lines:
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def _log(ws: Workspace, note: Notification, report: Report) -> None:
    path = ws.cache_dir / "notifications.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "at": utcnow().isoformat(),
        "event": note.event,
        "key": note.key,
        "title": note.title,
        "ok": report.ok,
        "results": [asdict(r) for r in report.results],
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def last_sent(ws: Workspace, event: str) -> datetime | None:
    times = [e["at"] for e in history(ws) if e.get("event") == event and e.get("ok")]
    return datetime.fromisoformat(times[-1]) if times else None
