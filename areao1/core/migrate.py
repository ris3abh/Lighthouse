"""From Lighthouse to Area O1 (ADR 0010 §2): old names keep working, and what can be moved is moved once, each
with a one-line notice. Environment variables are read under the old prefixes when the new one isn't set; a
Lighthouse-era user config folder is copied; a workspace's lighthouse.yaml and .lighthouse/ are renamed; keychain
secrets are copied from the old service (see secrets.py)."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from areao1.core import names

NOTICES: list[str] = []


def note(message: str) -> None:
    """Say it once per process (on stderr, so piped output stays clean)."""
    if message not in NOTICES:
        NOTICES.append(message)
        print(f"{names.PRODUCT}: {message}", file=sys.stderr)


def env(name: str) -> str | None:
    """AREAO1_<name>, else the Lighthouse-era LIGHTHOUSE_GC_<name> / LIGHTHOUSE_<name>."""
    value = os.environ.get(names.env(name))
    if value:
        return value
    for prefix in names.PREVIOUS["env_prefixes"]:
        old = prefix + name
        if os.environ.get(old):
            note(f"{old} is now {names.env(name)}; it still works for now, but please rename it.")
            return os.environ[old]
    return None


def user_config(new: Path) -> None:
    """Copy a Lighthouse-era user config folder (remembered workspace, agent settings) next to the new one."""
    if new.exists():
        return
    old = new.with_name(names.PREVIOUS["config_dir"])
    if old.is_dir():
        shutil.copytree(old, new)
        note(f"copied your settings from {old} to {new}.")


def workspace(root: Path) -> None:
    """Rename a Lighthouse-era workspace's config file and state folder, and its .gitignore lines."""
    old_cfg, new_cfg = root / names.PREVIOUS["workspace_config"], root / names.WORKSPACE_CONFIG
    if not old_cfg.is_file() or new_cfg.exists():
        return
    old_cfg.rename(new_cfg)
    old_state, new_state = root / names.PREVIOUS["workspace_state"], root / names.WORKSPACE_STATE
    if old_state.is_dir() and not new_state.exists():
        old_state.rename(new_state)
    ignore = root / ".gitignore"
    if ignore.is_file():
        text = ignore.read_text()
        ignore.write_text(text.replace(names.PREVIOUS["workspace_state"], names.WORKSPACE_STATE))
    note(
        f"updated {root} for the new name ({names.PREVIOUS['workspace_config']} is now {names.WORKSPACE_CONFIG})."
    )
