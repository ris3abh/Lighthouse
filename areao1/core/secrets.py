"""Token storage: OS keychain via ``keyring``, with environment / workspace ``.env`` fallbacks.

Tokens are never written to tracked workspace files. ``sources.json`` only stores ``secret_ref`` —
the name of the keychain entry.
"""

from __future__ import annotations

import re
from pathlib import Path

from areao1.core import migrate, names

SERVICE = names.KEYCHAIN_SERVICE
OLD_SERVICE = names.PREVIOUS["keychain_service"]


def env_var_name(secret_ref: str) -> str:
    """``github:octo`` -> ``AREAO1_GITHUB_OCTO``."""
    return names.env(_suffix(secret_ref))


def _suffix(secret_ref: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", secret_ref.upper()).strip("_")


def _read_dotenv(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def get_secret(secret_ref: str, workspace: Path | None = None) -> str | None:
    name = env_var_name(secret_ref)
    from_env = migrate.env(_suffix(secret_ref))  # AREAO1_…, or the Lighthouse-era LIGHTHOUSE_GC_…
    if from_env:
        return from_env
    try:
        import keyring

        value = keyring.get_password(SERVICE, secret_ref)
        if value:
            return value
        old = keyring.get_password(OLD_SERVICE, secret_ref)  # saved by Lighthouse: copy it under the new name
        if old:
            keyring.set_password(SERVICE, secret_ref, old)
            migrate.note(f"moved the {secret_ref} secret to the {SERVICE} keychain entry.")
            return old
    except Exception:  # no usable keychain backend
        pass
    if workspace is not None:
        return _read_dotenv(workspace / ".env").get(name)
    return None


def set_secret(secret_ref: str, value: str, workspace: Path | None = None) -> str:
    """Store a token. Returns where it went: ``keychain`` or ``.env``."""
    try:
        import keyring

        keyring.set_password(SERVICE, secret_ref, value)
        return "keychain"
    except Exception:
        if workspace is None:
            raise
    env_path = workspace / ".env"
    values = _read_dotenv(env_path)
    values[env_var_name(secret_ref)] = value
    env_path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
    env_path.chmod(0o600)
    return ".env"


def delete_secret(secret_ref: str, workspace: Path | None = None) -> None:
    try:
        import keyring

        keyring.delete_password(SERVICE, secret_ref)
    except Exception:
        pass
    if workspace is not None:
        env_path = workspace / ".env"
        values = _read_dotenv(env_path)
        if values.pop(env_var_name(secret_ref), None) is not None:
            env_path.write_text("".join(f"{k}={v}\n" for k, v in values.items()))
