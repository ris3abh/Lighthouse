"""Google sign-in with your own Desktop OAuth client (ADR 0014 §1): PKCE, a loopback redirect to 127.0.0.1, and
only the scopes of the features you turn on. The client secret and tokens live in the OS keychain only.
``client`` is injectable so tests never reach Google."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode

import httpx

from areao1.core.names import PRODUCT
from areao1.core.secrets import delete_secret, get_secret, set_secret

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
CLIENT_REF = "google:client"
TOKEN_REF = "google:token"

SCOPES: dict[str, str] = {
    "gmail_read": "https://www.googleapis.com/auth/gmail.readonly",
    "gmail_send": "https://www.googleapis.com/auth/gmail.send",
    "calendar": "https://www.googleapis.com/auth/calendar.app.created",
}
FEATURES: dict[str, str] = {
    "gmail_read": "Threads with your case contacts (read only)",
    "gmail_send": "Send drafts you approved",
    "calendar": f"A dedicated {PRODUCT} calendar",
}
BASE_SCOPES = ["openid", "email"]


class GoogleError(Exception):
    pass


def _json(ref: str) -> dict[str, Any] | None:
    raw = get_secret(ref)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def client_config() -> dict[str, str] | None:
    return _json(CLIENT_REF)  # type: ignore[return-value]


def save_client(client_id: str, client_secret: str) -> None:
    client_id, client_secret = client_id.strip(), client_secret.strip()
    if not client_id.endswith(".apps.googleusercontent.com"):
        raise GoogleError("That isn't a Google OAuth client ID (it ends in .apps.googleusercontent.com).")
    if not client_secret:
        raise GoogleError("Paste the client secret too (Desktop clients have one).")
    set_secret(CLIENT_REF, json.dumps({"client_id": client_id, "client_secret": client_secret}))


def token() -> dict[str, Any] | None:
    return _json(TOKEN_REF)


def granted(feature: str) -> bool:
    t = token()
    return bool(t) and SCOPES[feature] in str(t.get("scope", "")).split()  # type: ignore[union-attr]


def status() -> dict[str, Any]:
    t = token() or {}
    scopes = str(t.get("scope", "")).split()
    return {
        "client": bool(client_config()),
        "connected": bool(t.get("refresh_token")),
        "email": t.get("email"),
        "features": [{"id": f, "label": FEATURES[f], "granted": SCOPES[f] in scopes} for f in SCOPES],
    }


@dataclass
class Pending:
    """A sign-in in progress: the PKCE verifier and what was asked, keyed by ``state``."""

    verifier: str
    redirect_uri: str
    scopes: list[str]
    created: float = field(default_factory=time.time)


PENDING: dict[str, Pending] = {}


def begin(features: list[str], redirect_uri: str) -> str:
    """The Google URL to send the browser to. Asks only for the scopes of ``features`` (plus what's granted)."""
    cfg = client_config()
    if not cfg:
        raise GoogleError("Add your Google OAuth client first (Settings > Google).")
    unknown = [f for f in features if f not in SCOPES]
    if unknown or not features:
        raise GoogleError(f"Pick at least one feature ({', '.join(SCOPES)}).")
    already = str((token() or {}).get("scope", "")).split()
    scopes = sorted(
        {*BASE_SCOPES, *(SCOPES[f] for f in features), *(s for s in already if s in SCOPES.values())}
    )
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(24)
    for k in [k for k, p in PENDING.items() if time.time() - p.created > 900]:
        PENDING.pop(k)
    PENDING[state] = Pending(verifier, redirect_uri, scopes)
    params = {
        "client_id": cfg["client_id"],
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",  # a refresh token, so you sign in once
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def finish(code: str, state: str, client: httpx.Client | None = None) -> dict[str, Any]:
    """Exchange the code for tokens and keep them in the keychain. Returns the status."""
    pending = PENDING.pop(state, None)
    if pending is None or time.time() - pending.created > 900:
        raise GoogleError("That sign-in link expired or wasn't started here; connect again from Settings.")
    cfg = client_config()
    if not cfg:
        raise GoogleError("Add your Google OAuth client first.")
    with _client(client) as c:
        r = c.post(TOKEN_URL, data={"code": code, "client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                                    "redirect_uri": pending.redirect_uri, "grant_type": "authorization_code",
                                    "code_verifier": pending.verifier})  # fmt: skip
        if r.status_code != 200:
            raise GoogleError(f"Google didn't accept the sign-in ({_why(r)}).")
        data = r.json()
        info = c.get(USERINFO_URL, headers={"Authorization": f"Bearer {data['access_token']}"})
        email = info.json().get("email") if info.status_code == 200 else None
    previous = token() or {}
    set_secret(TOKEN_REF, json.dumps({
        "refresh_token": data.get("refresh_token") or previous.get("refresh_token"),
        "access_token": data["access_token"], "expires_at": time.time() + int(data.get("expires_in", 3600)) - 60,
        "scope": data.get("scope", " ".join(pending.scopes)), "email": email or previous.get("email"),
    }))  # fmt: skip
    return status()


def access_token(client: httpx.Client | None = None) -> str:
    """A valid access token, refreshed when it's about to expire."""
    t, cfg = token(), client_config()
    if not t or not t.get("refresh_token") or not cfg:
        raise GoogleError("Google isn't connected (Settings > Google).")
    if t.get("access_token") and float(t.get("expires_at", 0)) > time.time():
        return str(t["access_token"])
    with _client(client) as c:
        r = c.post(TOKEN_URL, data={"client_id": cfg["client_id"], "client_secret": cfg["client_secret"],
                                    "refresh_token": t["refresh_token"], "grant_type": "refresh_token"})  # fmt: skip
    if r.status_code != 200:
        raise GoogleError(f"Google refused to refresh the sign-in ({_why(r)}); connect again from Settings.")
    data = r.json()
    t.update(
        access_token=data["access_token"], expires_at=time.time() + int(data.get("expires_in", 3600)) - 60
    )
    if data.get("scope"):
        t["scope"] = data["scope"]
    set_secret(TOKEN_REF, json.dumps(t))
    return str(data["access_token"])


def disconnect(client: httpx.Client | None = None) -> dict[str, Any]:
    """Revoke the sign-in with Google, then forget it here."""
    t = token() or {}
    tok = t.get("refresh_token") or t.get("access_token")
    if tok:
        try:
            with _client(client) as c:
                c.post(REVOKE_URL, params={"token": tok})
        except httpx.HTTPError:
            pass  # forgotten locally either way
    delete_secret(TOKEN_REF)
    return status()


def _client(client: httpx.Client | None) -> Any:
    from contextlib import nullcontext

    return nullcontext(client) if client is not None else httpx.Client(timeout=20)


def _why(r: httpx.Response) -> str:
    try:
        body = r.json()
        return str(body.get("error_description") or body.get("error") or r.status_code)
    except ValueError:
        return str(r.status_code)
