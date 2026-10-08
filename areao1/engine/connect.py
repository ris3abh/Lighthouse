"""Connect your AI (ADR 0015 §3): an OpenAI API key, kept in the OS keychain. A pasted key is checked with the free
model-list request before it's stored, and it's never written to the workspace. OPENAI_API_KEY from the
environment works too."""

from __future__ import annotations

import os
from typing import Any

import httpx

from areao1.core.secrets import delete_secret, get_secret, set_secret

KEY_REF = "openai:api_key"
OLD_KEY_REF = "anthropic:api_key"  # before ADR 0015; removed from the keychain on start
MODELS_URL = "https://api.openai.com/v1/models"
COST_NOTE = ("Chat and web lookups use your AI and usually cost a few cents each; the monthly cap in "
             "Settings > Agent stops runs before they go over.")  # fmt: skip


def stored_key() -> str | None:
    """The OpenAI key Area O1 uses: the one saved in Settings, else OPENAI_API_KEY from the environment."""
    return get_secret(KEY_REF) or os.environ.get("OPENAI_API_KEY") or None


def key_source() -> str | None:
    if get_secret(KEY_REF):
        return "keychain"
    return "environment" if os.environ.get("OPENAI_API_KEY") else None


def check_key(key: str, client: httpx.Client | None = None) -> tuple[bool, str]:
    """Ask OpenAI whether the key works, with the free model-list request. (ok, plain message)."""
    key = key.strip()
    if key.startswith("sk-ant-"):
        return False, "That's an Anthropic key. Area O1 now runs on OpenAI: paste an OpenAI API key (sk-…)."
    if not key.startswith("sk-") or len(key) < 20:
        return False, "That doesn't look like an OpenAI API key (they start with sk-)."
    try:
        own = client is None
        client = client or httpx.Client(timeout=15)
        try:
            r = client.get(MODELS_URL, headers={"Authorization": f"Bearer {key}"})
        finally:
            if own:
                client.close()
    except httpx.HTTPError as exc:
        return False, f"Couldn't reach OpenAI to check the key ({type(exc).__name__}). Try again in a moment."
    if r.status_code == 200:
        return True, "The key works."
    if r.status_code in (401, 403):
        return False, "OpenAI refused that key. Check you copied all of it, and that it isn't revoked."
    return False, f"OpenAI answered {r.status_code}; the key wasn't saved. Try again in a moment."


def save_key(key: str) -> str:
    """Store a checked key in the OS keychain only (never the workspace). Returns "keychain"."""
    return set_secret(KEY_REF, key.strip())


def forget_key() -> None:
    delete_secret(KEY_REF)


def forget_anthropic() -> bool:
    """An Anthropic key saved before ADR 0015 leaves the keychain. True if one was there."""
    from areao1.core import migrate

    if not get_secret(OLD_KEY_REF):
        return False
    delete_secret(OLD_KEY_REF)
    migrate.note(
        "removed the Anthropic API key from your keychain: Area O1 now runs on OpenAI (Settings > Your AI)."
    )
    return True


def status() -> dict[str, Any]:
    source = key_source()
    if source:
        how = "Using your OpenAI API key" + (" from the environment." if source == "environment" else ".")
    else:
        how = ("No AI connected. Add an OpenAI API key to use chat and web lookups; everything else works "
               "without one.")  # fmt: skip
    return {"key": source, "ready": bool(source), "how": how, "cost": COST_NOTE}
