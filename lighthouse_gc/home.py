"""Where Lighthouse looks when you don't say (ADR 0013): the default workspace (~/Lighthouse) and the
user config file that remembers the workspace you last opened. Nothing case-related is stored here."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def config_dir() -> Path:
    if os.environ.get("LIGHTHOUSE_GC_CONFIG_DIR"):
        return Path(os.environ["LIGHTHOUSE_GC_CONFIG_DIR"]).expanduser()
    if sys.platform == "win32" and os.environ.get("APPDATA"):
        return Path(os.environ["APPDATA"]) / "lighthouse-gc"
    base = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    return Path(base) / "lighthouse-gc"


def default_workspace() -> Path:
    return Path(os.environ.get("LIGHTHOUSE_GC_HOME") or Path.home() / "Lighthouse").expanduser()


def _load() -> dict:
    try:
        data = json.loads((config_dir() / "config.json").read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def remembered() -> Path | None:
    value = _load().get("workspace")
    return Path(value) if isinstance(value, str) and value else None


def remember(workspace: Path) -> None:
    try:
        d = config_dir()
        d.mkdir(parents=True, exist_ok=True)
        data = {**_load(), "workspace": str(Path(workspace).resolve())}
        (d / "config.json").write_text(json.dumps(data, indent=2) + "\n")
    except OSError:  # a read-only home shouldn't stop Lighthouse from starting
        pass
