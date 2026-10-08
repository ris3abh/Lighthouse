"""I4: nothing is left of removed features (Google Calendar sync and the OAuth client, the Anthropic engine, the demo
workspace) except the start-up cleanups that remove their old secrets and the values that let old records load."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).parents[1]
GONE = ("claude_agent_sdk", "claude-agent-sdk", "ClaudeAgentEngine", "CodexEngine", "openai_chat", "find_cli",
        "google/calendar", "google.calendar", "calendar.app.created", "CalendarSync", "gmail.readonly",
        "GoogleConnect", "areao1 demo", "make_demo", "OPENAI_MUNDANE")  # fmt: skip


def test_removed_features_leave_nothing_behind():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    hits = []
    for f in tracked:
        if f.startswith(("docs/adr/", "tests/", "CHANGELOG", "TODO")) or not f.endswith((".py", ".ts", ".tsx", ".md",
                                                                                      ".toml", ".yml", ".yaml", ".json")):  # fmt: skip
            continue
        text = (ROOT / f).read_text(encoding="utf-8", errors="replace")
        hits += [f"{f}: {g}" for g in GONE if g in text]
    assert hits == []
    assert not (ROOT / "areao1" / "engine" / "claude_code.py").exists()
    assert (
        not (ROOT / "areao1" / "google" / "calendar.py").exists()
        and not (ROOT / "areao1" / "google" / "auth.py").exists()
    )
