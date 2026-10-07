"""Gmail, connected with an app password (ADR 0014 and its amendment)."""

from __future__ import annotations

OLD_REFS = ("google:token", "google:client")  # the OAuth sign-in and client, removed by the amendment


def forget_oauth() -> bool:
    """Remove a Google sign-in or client saved before Google became Gmail-only: the token is revoked with Google
    first (best effort), then both leave the keychain. True when there was something to remove."""
    import json

    import httpx

    from areao1.core import migrate
    from areao1.core.secrets import delete_secret, get_secret

    found = {ref: get_secret(ref) for ref in OLD_REFS}
    if not any(found.values()):
        return False
    try:
        token = json.loads(found["google:token"] or "{}")
        tok = token.get("refresh_token") or token.get("access_token")
        if tok:
            httpx.post("https://oauth2.googleapis.com/revoke", params={"token": tok}, timeout=5)
    except (ValueError, AttributeError, httpx.HTTPError):
        pass  # removed here either way
    for ref in OLD_REFS:
        delete_secret(ref)
    migrate.note(
        "removed the old Google sign-in and client from your keychain; Gmail now uses an app password."
    )
    return True
