"""Gmail with an app password (ADR 0014, amendment): your address and a 16-letter app password, checked with one
IMAP login, kept in the keychain only, with plain errors. Gmail is the in-memory fake in mail_fakes.py."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from mail_fakes import FakeGmail

from areao1.google import mail
from areao1.server.app import create_app

W = {"X-AreaO1": "1"}


@pytest.fixture
def c(ws):
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        yield client


def _put(c, email="alex@gmail.com", password="abcd efgh ijkl mnop"):
    return c.put("/api/google/mail", headers=W, json={"email": email, "password": password})


def test_connect_checks_the_password_and_keeps_it_in_the_keychain_only(c, ws, monkeypatch, fake_keyring):
    gmail = FakeGmail().install(monkeypatch)
    r = _put(c)  # pasted with Google's spaces
    assert r.status_code == 200, r.text
    assert r.json()["mail"] == {"connected": True, "email": "alex@gmail.com"}
    assert gmail.commands == [("LOGIN", "alex@gmail.com")]  # one test login, nothing read
    assert mail.account() == {"email": "alex@gmail.com", "password": "abcdefghijklmnop"}
    assert any("abcdefghijklmnop" in v for v in fake_keyring.values())
    for f in ws.root.rglob("*"):  # nowhere in the workspace
        if f.is_file():
            assert b"abcdefghijklmnop" not in f.read_bytes(), f
    assert c.delete("/api/google/mail", headers=W).json()["mail"]["connected"] is False
    assert mail.account() is None


@pytest.mark.parametrize(
    ("setup", "password", "says"),
    [
        ({}, "abcdefghijklmnoq", "didn't accept that app password"),  # wrong password
        ({}, "my-normal-Passw0rd!", "16 letters"),  # not an app password: 2-Step Verification hint
        ({}, "abcdefghijklmnop", None),
        ({"imap_disabled": True}, "abcdefghijklmnop", "Enable IMAP"),
        (
            {
                "login_error": "[ALERT] Application-specific password required: https://support.google.com/accounts/"
                "answer/185833 (Failure)"
            },
            "abcdefghijklmnop",
            "normal Google password",
        ),  # fmt: skip
        (
            {"login_error": "[ALERT] Please log in via your web browser (Failure)"},
            "abcdefghijklmnop",
            "browser",
        ),
    ],
)
def test_plain_errors(c, monkeypatch, setup, password, says):
    FakeGmail(**setup).install(monkeypatch)
    r = _put(c, password=password)
    if says is None:
        assert r.status_code == 200
        return
    assert r.status_code == 400 and says in r.json()["detail"], r.text
    assert "AUTHENTICATIONFAILED" not in r.json()["detail"] and mail.account() is None


def test_the_2_step_verification_hint_names_the_step(c, monkeypatch):
    FakeGmail().install(monkeypatch)
    assert "2-Step Verification is off" in _put(c, password="hunter2").json()["detail"]


def test_no_network_means_a_plain_error(c, monkeypatch):
    def offline(*a, **k):
        raise OSError("nodename nor servname provided")

    monkeypatch.setattr(mail, "IMAP", offline)
    assert "Couldn't reach Gmail" in _put(c).json()["detail"]


def test_a_bad_address_is_refused_before_any_login(c, monkeypatch):
    gmail = FakeGmail().install(monkeypatch)
    assert _put(c, email='alex"@gmail.com').status_code == 400 and not gmail.commands
