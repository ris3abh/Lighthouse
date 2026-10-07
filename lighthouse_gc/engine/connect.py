"""Connect your AI (ADR 0013 §4, amended): an Anthropic API key, kept in the OS keychain. It's the only supported
option: Anthropic's Agent SDK terms don't let third-party products offer claude.ai login, so Lighthouse never
uses a Claude Code login, even one already on this computer (the engine runs the CLI with its own empty config
folder). A pasted key is checked with the free model-list request before it's stored, and it's never written to
the workspace. The CLI bundled with claude-agent-sdk is enough; PATH isn't needed."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Any

import httpx

from lighthouse_gc.core.secrets import delete_secret, get_secret, set_secret

KEY_REF = "anthropic:api_key"
MODELS_URL = "https://api.anthropic.com/v1/models"
COST_NOTE = ("Chat and web lookups use your AI and usually cost a few cents each; the monthly cap in "
             "Settings > Agent stops runs before they go over.")  # fmt: skip


def bundled_cli() -> Path | None:
    """The Claude Code CLI that ships inside claude-agent-sdk, if this install has it."""
    try:
        import claude_agent_sdk
    except ImportError:
        return None
    name = "claude.exe" if os.name == "nt" else "claude"
    path = Path(claude_agent_sdk.__file__).parent / "_bundled" / name
    return path if path.is_file() else None


def find_cli() -> tuple[str | None, str]:
    """(path, "installed" | "bundled" | "missing")."""
    on_path = shutil.which("claude")
    if on_path:
        return on_path, "installed"
    bundled = bundled_cli()
    return (str(bundled), "bundled") if bundled else (None, "missing")


def stored_key() -> str | None:
    """The Anthropic key Lighthouse uses: the one saved in Settings, else ANTHROPIC_API_KEY from the environment."""
    return get_secret(KEY_REF) or os.environ.get("ANTHROPIC_API_KEY") or None


def key_source() -> str | None:
    if get_secret(KEY_REF):
        return "keychain"
    return "environment" if os.environ.get("ANTHROPIC_API_KEY") else None


def check_key(key: str, client: httpx.Client | None = None) -> tuple[bool, str]:
    """Ask Anthropic whether the key works, with the free model-list request. (ok, plain message)."""
    key = key.strip()
    if not key.startswith("sk-ant-"):
        return False, "That doesn't look like an Anthropic API key (they start with sk-ant-)."
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    try:
        own = client is None
        client = client or httpx.Client(timeout=15)
        try:
            r = client.get(MODELS_URL, headers=headers, params={"limit": 1})
        finally:
            if own:
                client.close()
    except httpx.HTTPError as exc:
        return (
            False,
            f"Couldn't reach Anthropic to check the key ({type(exc).__name__}). Try again in a moment.",
        )
    if r.status_code == 200:
        return True, "The key works."
    if r.status_code in (401, 403):
        return False, "Anthropic refused that key. Check you copied all of it, and that it isn't revoked."
    return False, f"Anthropic answered {r.status_code}; the key wasn't saved. Try again in a moment."


def save_key(key: str) -> str:
    """Store a checked key in the OS keychain only (never the workspace). Returns "keychain"."""
    return set_secret(KEY_REF, key.strip())


def forget_key() -> None:
    delete_secret(KEY_REF)


def status() -> dict[str, Any]:
    cli, where = find_cli()
    source = key_source()
    if source and cli:
        how = "Using your Anthropic API key" + (" from the environment." if source == "environment" else ".")
    elif source:
        how = "Your key is saved, but the agent runtime is missing; reinstall Lighthouse."
    else:
        how = ("No AI connected. Add an Anthropic API key to use chat and web lookups; everything else works "
               "without one.")  # fmt: skip
    return {"cli": where, "key": source, "ready": bool(cli and source), "how": how, "cost": COST_NOTE}
