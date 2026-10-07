"""Connect your AI (S3, ADR 0013 §4): the Claude Code login or an Anthropic key in the keychain, checked with the
free model-list request; the bundled CLI counts; skippable; the key never reaches the workspace."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_onboarding import W, answer_all, client_for, upload

from lighthouse_gc.core.secrets import get_secret
from lighthouse_gc.engine import claude_code, connect
from lighthouse_gc.scaffold import create_workspace

KEY = "sk-ant-api03-" + "x" * 40
REAL_AVAILABLE = claude_code.ClaudeAgentEngine.available  # before the autouse guard replaces it in each test


@pytest.fixture
def fresh(tmp_path):
    return create_workspace(tmp_path / "case", name="", git=False)


def _models(http_mock, status=200):
    return http_mock.get(connect.MODELS_URL).respond(status, json={"data": [{"id": "claude-opus-5-5"}]})


@pytest.fixture
def no_installed_cli(monkeypatch):
    monkeypatch.setattr(connect.shutil, "which", lambda name: None)


def test_a_key_is_checked_for_free_then_kept_in_the_keychain_only(fresh, http_mock):
    route = _models(http_mock)
    c = client_for(fresh)
    r = c.put("/api/ai/key", headers=W, json={"key": KEY})
    assert r.status_code == 200 and r.json()["key"] == "keychain"
    sent = route.calls.last.request
    assert sent.method == "GET" and sent.url.path == "/v1/models"  # listing models costs nothing
    assert sent.headers["x-api-key"] == KEY
    assert get_secret(connect.KEY_REF) == KEY
    for f in fresh.root.rglob("*"):  # never written to the workspace (or its git history)
        if f.is_file():
            assert KEY.encode() not in f.read_bytes(), f
    assert c.delete("/api/ai/key", headers=W).json()["key"] is None
    assert get_secret(connect.KEY_REF) is None


@pytest.mark.parametrize(
    ("key", "status", "says"),
    [(KEY, 401, "refused that key"), (KEY, 529, "answered 529"), ("hello", None, "start with sk-ant-")],
)
def test_a_key_that_doesnt_work_is_not_saved_and_says_why(fresh, http_mock, key, status, says):
    route = _models(http_mock, status or 200)
    r = client_for(fresh).put("/api/ai/key", headers=W, json={"key": key})
    assert r.status_code == 400 and says in r.json()["detail"]
    assert get_secret(connect.KEY_REF) is None
    assert route.called == (status is not None)  # a malformed key never leaves the computer


def test_the_bundled_cli_counts_so_path_isnt_needed(monkeypatch, tmp_path, no_installed_cli):
    fake = tmp_path / "claude"
    fake.write_text("")
    monkeypatch.setattr(connect, "bundled_cli", lambda: fake)
    assert connect.find_cli() == (str(fake), "bundled")
    monkeypatch.setattr(claude_code, "find_cli", connect.find_cli)
    assert REAL_AVAILABLE(claude_code.ClaudeAgentEngine()) == (True, "ready")
    monkeypatch.setattr(connect, "bundled_cli", lambda: None)
    ok, why = REAL_AVAILABLE(claude_code.ClaudeAgentEngine())
    assert not ok and "Settings > Agent" in why


def test_a_saved_key_goes_to_the_cli_process_only(monkeypatch):
    from lighthouse_gc.engine.base import EngineRequest

    req = EngineRequest(system_prompt="s", prompt="p", model="claude-opus-5-5")
    assert claude_code.ClaudeAgentEngine().options(req, []).env == {}
    connect.save_key(KEY)
    assert claude_code.ClaudeAgentEngine().options(req, []).env == {"ANTHROPIC_API_KEY": KEY}


def test_onboarding_asks_once_after_the_questions_and_can_be_skipped(fresh, http_mock):
    c = client_for(fresh)
    view, _ = answer_all(c, upload(c, "maya"), ai=None)
    assert view["state"]["step"] == "ai" and view["nav"]["back"]["step"] == "questions"
    assert (
        c.post("/api/onboarding/ai", headers=W, json={"choice": "key"}).status_code == 409
    )  # no key saved yet
    _models(http_mock)
    c.put("/api/ai/key", headers=W, json={"key": KEY})
    view = c.post("/api/onboarding/ai", headers=W, json={"choice": "key"}).json()
    assert view["state"]["ai"] == "key" and view["state"]["step"] == "lookups"
    # going back to the questions and finishing them again doesn't ask again
    c.post("/api/onboarding/goto", headers=W, json={"step": "questions", "question": "when"})
    q = c.get("/api/onboarding").json()["question"]
    view = c.post(
        "/api/onboarding/answer", headers=W, json={"id": q["id"], "action": "yes", "value": "2027-03"}
    ).json()
    assert view["state"]["step"] == "lookups"


def test_choosing_the_login_needs_claude_code_on_this_computer(fresh, monkeypatch):
    c = client_for(fresh)
    answer_all(c, upload(c, "maya"), ai=None)
    monkeypatch.setattr(connect, "find_cli", lambda: (None, "missing"))
    r = c.post("/api/onboarding/ai", headers=W, json={"choice": "login"})
    assert r.status_code == 409 and "API key" in r.json()["detail"]
    monkeypatch.setattr(connect, "find_cli", lambda: ("/usr/local/bin/claude", "installed"))
    assert c.post("/api/onboarding/ai", headers=W, json={"choice": "login"}).json()["state"]["ai"] == "login"


def test_status_says_how_lighthouse_reaches_the_ai_and_what_it_costs(fresh, monkeypatch):
    c: TestClient = client_for(fresh)
    monkeypatch.setattr(connect, "find_cli", lambda: (None, "missing"))
    s = c.get("/api/ai").json()
    assert not s["ready"] and "works without one" in s["how"] and "monthly cap" in s["cost"]
    monkeypatch.setattr(connect, "find_cli", lambda: ("/x/claude", "bundled"))
    assert "Claude Code login" in c.get("/api/ai").json()["how"]
    monkeypatch.setenv("ANTHROPIC_API_KEY", KEY)
    assert c.get("/api/ai").json()["key"] == "environment"
