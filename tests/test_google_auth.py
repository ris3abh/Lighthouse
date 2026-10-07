"""Google sign-in (E1, ADR 0014 §1): your own Desktop client, PKCE and a loopback redirect, only the scopes of the
features you turn on, tokens in the keychain only, revoked on disconnect. Google is mocked; nothing leaves."""

from __future__ import annotations

import base64
import hashlib
import json
import time
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from areao1.core.secrets import get_secret
from areao1.google import auth
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}
CLIENT = {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "GOCSPX-test-secret"}


@pytest.fixture
def c(ws):
    auth.PENDING.clear()
    return TestClient(
        create_app(ws, allowed_hosts=["testserver", "127.0.0.1"]), base_url="http://127.0.0.1:7777"
    )


def _connect(c, features):
    assert c.put("/api/google/client", headers=W, json=CLIENT).status_code == 200
    url = c.post("/api/google/connect", headers=W, json={"features": features}).json()["url"]
    return url, {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}


def _google(http_mock, scope, refresh="1//refresh-token", email="maya@example.com"):
    token = http_mock.post(auth.TOKEN_URL).respond(json={"access_token": "ya29.access", "expires_in": 3599,
                                                          "refresh_token": refresh, "scope": scope,
                                                          "token_type": "Bearer"})  # fmt: skip
    http_mock.get(auth.USERINFO_URL).respond(json={"email": email})
    return token


def test_only_the_scopes_of_the_features_you_turn_on(c):
    url, q = _connect(c, ["calendar"])
    assert url.startswith(auth.AUTH_URL)
    assert set(q["scope"].split()) == {"openid", "email", auth.SCOPES["calendar"]}  # not Gmail
    assert q["redirect_uri"] == "http://127.0.0.1:7777/api/google/callback"  # loopback, this computer only
    assert q["client_id"] == CLIENT["client_id"] and "client_secret" not in q
    assert q["code_challenge_method"] == "S256" and q["access_type"] == "offline"
    verifier = auth.PENDING[q["state"]].verifier
    assert (
        q["code_challenge"]
        == base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    assert c.post("/api/google/connect", headers=W, json={"features": ["drive"]}).status_code == 400


def test_signing_in_keeps_tokens_in_the_keychain_only(c, ws, http_mock):
    _, q = _connect(c, ["gmail_read", "calendar"])
    scope = " ".join(["openid", "email", auth.SCOPES["gmail_read"], auth.SCOPES["calendar"]])
    token = _google(http_mock, scope)
    verifier = auth.PENDING[q["state"]].verifier
    r = c.get(
        "/api/google/callback", params={"state": q["state"], "code": "4/auth-code"}, follow_redirects=False
    )
    assert r.status_code == 303 and r.headers["location"] == "/#/settings?google=connected"
    sent = parse_qs(token.calls.last.request.content.decode())
    assert sent["code_verifier"] == [verifier] and q["state"] not in auth.PENDING  # used once
    assert sent["grant_type"] == ["authorization_code"] and sent["client_secret"] == [CLIENT["client_secret"]]
    s = c.get("/api/google").json()
    assert s["connected"] and s["email"] == "maya@example.com"
    assert {f["id"] for f in s["features"] if f["granted"]} == {"gmail_read", "calendar"}
    stored = json.loads(get_secret(auth.TOKEN_REF))
    assert stored["refresh_token"] == "1//refresh-token"
    for f in ws.root.rglob("*"):  # nothing in the workspace (or its git history)
        if f.is_file():
            body = f.read_bytes()
            assert (
                b"1//refresh-token" not in body and b"GOCSPX-test-secret" not in body and b"ya29." not in body
            ), f


def test_a_callback_that_wasnt_started_here_is_refused(c, http_mock):
    _connect(c, ["calendar"])
    token = _google(http_mock, "openid")
    r = c.get("/api/google/callback", params={"state": "forged", "code": "x"}, follow_redirects=False)
    assert "google=error" in r.headers["location"] and not token.called
    assert not c.get("/api/google").json()["connected"]
    r = c.get("/api/google/callback", params={"error": "access_denied"}, follow_redirects=False)
    assert "access_denied" in r.headers["location"]


def test_the_access_token_is_refreshed_when_it_expires(c, http_mock):
    _, q = _connect(c, ["calendar"])
    _google(http_mock, f"openid email {auth.SCOPES['calendar']}")
    c.get("/api/google/callback", params={"state": q["state"], "code": "x"}, follow_redirects=False)
    assert auth.access_token() == "ya29.access"  # still fresh: no request
    t = json.loads(get_secret(auth.TOKEN_REF))
    t["expires_at"] = time.time() - 1
    from areao1.core.secrets import set_secret

    set_secret(auth.TOKEN_REF, json.dumps(t))
    refresh = http_mock.post(auth.TOKEN_URL).respond(json={"access_token": "ya29.new", "expires_in": 3599})
    assert auth.access_token() == "ya29.new"
    assert parse_qs(refresh.calls.last.request.content.decode())["grant_type"] == ["refresh_token"]


def test_disconnect_revokes_with_google_and_forgets(c, http_mock):
    _, q = _connect(c, ["calendar"])
    _google(http_mock, f"openid email {auth.SCOPES['calendar']}")
    c.get("/api/google/callback", params={"state": q["state"], "code": "x"}, follow_redirects=False)
    revoke = http_mock.post(auth.REVOKE_URL).respond(200)
    s = c.delete("/api/google", headers=W).json()
    assert revoke.called and revoke.calls.last.request.url.params["token"] == "1//refresh-token"
    assert not s["connected"] and get_secret(auth.TOKEN_REF) is None
    assert s["client"]  # the client stays, so connecting again is one click


def test_a_client_id_that_isnt_googles_is_refused(c):
    r = c.put("/api/google/client", headers=W, json={"client_id": "abc", "client_secret": "x"})
    assert r.status_code == 400 and "googleusercontent" in r.json()["detail"]
