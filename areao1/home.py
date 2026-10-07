"""Where Area O1 looks when you don't say (ADR 0013): the default workspace (~/AreaO1) and the
user config file that remembers the workspace you last opened. Nothing case-related is stored here."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from areao1.core import migrate, names


def config_dir() -> Path:
    explicit = migrate.env("CONFIG_DIR")
    if explicit:
        d = Path(explicit).expanduser()
    elif sys.platform == "win32" and os.environ.get("APPDATA"):
        d = Path(os.environ["APPDATA"]) / names.CONFIG_DIR
    else:
        d = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / names.CONFIG_DIR
    if not explicit:
        migrate.user_config(d)  # a Lighthouse-era ~/.config/lighthouse-gc comes along once
    return d


def default_workspace() -> Path:
    return Path(migrate.env("HOME") or Path.home() / names.DEFAULT_HOME).expanduser()


def _load() -> dict:
    try:
        data = json.loads((config_dir() / "config.json").read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def remembered() -> Path | None:
    value = _load().get("workspace")
    return Path(value) if isinstance(value, str) and value else None


def workspace_id(root: Path) -> str:
    """A short id for a workspace folder, so a second launch can tell its own server from another case's."""
    import hashlib

    return hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:16]


def remember(workspace: Path) -> None:
    try:
        d = config_dir()
        d.mkdir(parents=True, exist_ok=True)
        data = {**_load(), "workspace": str(Path(workspace).resolve())}
        (d / "config.json").write_text(json.dumps(data, indent=2) + "\n")
    except OSError:  # a read-only home shouldn't stop Area O1 from starting
        pass
