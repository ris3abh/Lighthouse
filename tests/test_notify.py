"""Notification channels and routing. No real sends: HTTP via respx, SMTP and the OS notifier faked."""

from __future__ import annotations

import json
import subprocess

import pytest
from typer.testing import CliRunner

from areao1 import notify
from areao1.cli import app
from areao1.core.models import ChannelConfig, NotificationsConfig
from areao1.notify import Notification, already_sent, history, send

SLACK = "https://hooks.slack.com/services/T000/B000/XXXX"
DISCORD = "https://discord.com/api/webhooks/1/abc"


@pytest.fixture
def channels(ws, fake_keyring):
    cfg = ws.config()
    cfg.notifications = NotificationsConfig(
        channels={
            "desktop": ChannelConfig(kind="desktop"),
            "slack": ChannelConfig(kind="slack", secret_ref="notify:slack", detail="full"),
            "discord": ChannelConfig(kind="discord", secret_ref="notify:discord", detail="minimal"),
            "phone": ChannelConfig(
                kind="ntfy", topic="lh-test-7f3a", secret_ref="notify:ntfy", detail="minimal"
            ),
            "mail": ChannelConfig(
                kind="email",
                host="smtp.example.org",
                username="me",
                from_addr="me@example.org",
                to_addr="me@example.org",
                secret_ref="notify:smtp",
            ),
            "off": ChannelConfig(kind="desktop", enabled=False),
        },  # fmt: skip
        routes={"deadline": ["slack", "discord", "phone", "off"], "digest": ["mail"], "test": ["desktop"]},
    )
    ws.save_config(cfg)
    fake_keyring.update({("areao1", "notify:slack"): SLACK, ("areao1", "notify:discord"): DISCORD,
                         ("areao1", "notify:ntfy"): "tk_secret", ("areao1", "notify:smtp"): "pw"})  # fmt: skip
    return ws


NOTE = Notification(
    "deadline", "IEEE application due in 3 days", "IEEE Senior Member application — due 2026-11-01",
    url="http://127.0.0.1:7777/#/calendar", priority="high", minimal_body="1 deadline in the next 3 days",
    key="deadline:dl_ieee:3",
)  # fmt: skip


def test_routes_to_channels_and_respects_detail(channels, http_mock):
    slack = http_mock.post(SLACK).respond(200, text="ok")
    discord = http_mock.post(DISCORD).respond(204)
    ntfy = http_mock.post("https://ntfy.sh/lh-test-7f3a").respond(200, json={})
    report = send(channels, NOTE)
    assert report.ok and [r.channel for r in report.results] == ["slack", "discord", "phone"]  # "off" skipped

    slack_body = json.loads(slack.calls[0].request.content)
    assert "IEEE application due in 3 days" in slack_body["text"]  # detail: full

    discord_body = json.loads(discord.calls[0].request.content)
    assert discord_body["content"] == "**Area O1**\n1 deadline in the next 3 days"  # detail: minimal
    assert "IEEE" not in discord_body["content"]
    assert discord_body["allowed_mentions"] == {"parse": []}

    req = ntfy.calls[0].request
    assert req.content == b"1 deadline in the next 3 days"
    assert req.headers["authorization"] == "Bearer tk_secret" and req.headers["priority"] == "4"
    assert "click" not in req.headers  # a phone can't open the laptop's 127.0.0.1


def test_a_broken_channel_does_not_stop_the_others(channels, http_mock, fake_keyring):
    fake_keyring[("areao1", "notify:slack")] = "https://evil.example/collect"
    http_mock.post(DISCORD).respond(204)
    http_mock.post("https://ntfy.sh/lh-test-7f3a").respond(500, text="boom")
    report = send(channels, NOTE)
    by = {r.channel: r for r in report.results}
    assert not by["slack"].ok and "refusing to post" in by["slack"].error  # never posts to a non-Slack host
    assert by["discord"].ok and not by["phone"].ok and "HTTP 500" in by["phone"].error
    assert not report.ok


def test_missing_secret_is_reported(channels, http_mock, fake_keyring):
    del fake_keyring[("areao1", "notify:slack")]
    report = send(channels, NOTE, only="slack")
    assert not report.ok and "keychain" in report.results[0].error


def test_email_uses_starttls_and_keychain_password(channels, monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def starttls(self):
            sent["tls"] = True

        def login(self, user, pw):
            sent["login"] = (user, pw)

        def send_message(self, msg):
            sent["msg"] = msg

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    report = send(channels, Notification("digest", "Weekly digest", "3 things changed"))
    assert report.ok
    assert sent["server"] == ("smtp.example.org", 587) and sent["tls"] and sent["login"] == ("me", "pw")
    assert sent["msg"]["Subject"] == "[Area O1] Weekly digest"


def test_desktop_notification_escapes_text(channels, monkeypatch):
    calls = []
    monkeypatch.setattr("sys.platform", "darwin")
    monkeypatch.setattr(subprocess, "run", lambda cmd, **kw: calls.append(cmd))
    report = send(channels, Notification("test", 'Say "hi"', 'Body with "quotes" and \\ slash'))
    assert report.ok
    script = calls[0][2]
    assert calls[0][:2] == ["osascript", "-e"]
    assert '\\"hi\\"' in script and "\\\\ slash" in script


def test_sends_are_logged_for_dedupe(channels, http_mock):
    http_mock.post(SLACK).respond(200)
    http_mock.post(DISCORD).respond(204)
    http_mock.post("https://ntfy.sh/lh-test-7f3a").respond(200)
    assert not already_sent(channels, NOTE.key)
    send(channels, NOTE)
    assert already_sent(channels, NOTE.key)
    entry = history(channels)[-1]
    assert entry["event"] == "deadline" and entry["ok"]
    assert (channels.cache_dir / "notifications.jsonl").is_relative_to(channels.root / ".areao1" / "cache")


def test_unknown_channel_in_route(channels):
    cfg = channels.config()
    cfg.notifications.routes["test"] = ["nope"]
    channels.save_config(cfg)
    report = send(channels, Notification("test", "t", "b"))
    assert not report.ok and "no such channel" in report.results[0].error


def test_cli_notify_test_and_secret_set(channels, monkeypatch, fake_keyring):
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": _Recorder()})
    result = CliRunner().invoke(app, ["notify", "test", "-w", str(channels.root)])
    assert result.exit_code == 0, result.output
    assert "desktop: sent" in result.output

    result = CliRunner().invoke(
        app, ["secret", "set", "notify:new", "-w", str(channels.root)], input="s3cret\n"
    )
    assert result.exit_code == 0 and fake_keyring[("areao1", "notify:new")] == "s3cret"
    assert "s3cret" not in result.output
    assert b"s3cret" not in (channels.root / "areao1.yaml").read_bytes()


def test_api_settings_never_leaks_secrets(channels):
    from fastapi.testclient import TestClient

    from areao1.server.app import create_app

    c = TestClient(create_app(channels, allowed_hosts=["testserver"]))
    text = c.get("/api/settings").text
    assert SLACK not in text and "tk_secret" not in text and '"secret_stored":true' in text.replace(" ", "")


class _Recorder:
    def send(self, note, cfg, secret):
        pass


def test_api_notify_test_targets_one_channel(channels, monkeypatch):
    from fastapi.testclient import TestClient

    from areao1.server.app import create_app

    monkeypatch.setattr(
        notify, "CHANNELS", lambda: {k: _Recorder() for k in ("desktop", "slack", "discord", "ntfy", "email")}
    )
    c = TestClient(create_app(channels, allowed_hosts=["testserver"]))
    r = c.post("/api/notify/test", json={"channel": "slack"}, headers={"X-AreaO1": "1"})
    assert r.status_code == 200 and [x["channel"] for x in r.json()["results"]] == ["slack"]
