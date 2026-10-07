"""OS-native desktop notification (macOS: osascript, Linux: notify-send, Windows: PowerShell toast)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from areao1.core.models import ChannelConfig
from areao1.notify import Notification, NotifyError


def _applescript_string(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


class Desktop:
    def send(self, note: Notification, cfg: ChannelConfig, secret: str | None) -> None:
        body = note.body if len(note.body) <= 240 else note.body[:237] + "…"
        if sys.platform == "darwin":
            script = f"display notification {_applescript_string(body)} with title {_applescript_string(note.title)}"
            cmd = ["osascript", "-e", script]
        elif sys.platform.startswith("linux"):
            if not shutil.which("notify-send"):
                raise NotifyError("notify-send not found (install libnotify)")
            urgency = {"high": "critical", "low": "low"}.get(note.priority, "normal")
            cmd = ["notify-send", "-u", urgency, "-a", "Area O1", note.title, body]
        elif sys.platform == "win32":
            ps = (
                "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null;"
                "$t = [Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent(1);"
                "$x = $t.GetElementsByTagName('text'); $x.Item(0).AppendChild($t.CreateTextNode($env:LH_TITLE)) > $null;"
                "$x.Item(1).AppendChild($t.CreateTextNode($env:LH_BODY)) > $null;"
                "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Area O1').Show("
                "[Windows.UI.Notifications.ToastNotification]::new($t))"
            )
            # Text goes through environment variables, never interpolated into the script.
            subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True, timeout=15, capture_output=True,
                           env={**os.environ, "LH_TITLE": note.title, "LH_BODY": body})  # fmt: skip
            return
        else:
            raise NotifyError(f"desktop notifications aren't supported on {sys.platform}")
        subprocess.run(cmd, check=True, timeout=15, capture_output=True)
