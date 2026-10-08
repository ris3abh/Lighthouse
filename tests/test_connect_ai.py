"""Connect your AI (ADR 0015 §3): an OpenAI key in the keychain only, checked with the free model-list request;
skippable; the key never reaches the workspace; an Anthropic key from before leaves the keychain."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from test_onboarding import W, answer_all, client_for, upload

from areao1.core.secrets import get_secret, set_secret
from areao1.engine import connect
from areao1.scaffold import create_workspace

KEY = "sk-proj-" + "x" * 40


@pytest.fixture
def fresh(tmp_path):
    return create_workspace(tmp_path / "case", name="", git=False)


def _models(http_mock, status=200):
    return http_mock.get(connect.MODELS_URL).respond(status, json={"data": [{"id": "gpt-6.1-sol"}]})


def test_a_key_is_checked_for_free_then_kept_in_the_keychain_only(fresh, http_mock):
    route = _models(http_mock)
    c = client_for(fresh)
    r = c.put("/api/ai/key", headers=W, json={"key": KEY})
    assert r.status_code == 200 and r.json()["key"] == "keychain"
    sent = route.calls.last.request
    assert sent.method == "GET" and sent.url.path == "/v1/models"  # listing models costs nothing
    assert sent.headers["authorization"] == f"Bearer {KEY}"
    assert get_secret(connect.KEY_REF) == KEY
    for f in fresh.root.rglob("*"):  # never written to the workspace (or its git history)
        if f.is_file():
            assert KEY.encode() not in f.read_bytes(), f
    assert c.delete("/api/ai/key", headers=W).json()["key"] is None
    assert get_secret(connect.KEY_REF) is None


@pytest.mark.parametrize(
    ("key", "status", "says"),
    [(KEY, 401, "refused that key"), (KEY, 503, "answered 503"), ("hello", None, "start with sk-"),
     ("sk-ant-api03-" + "x" * 40, None, "That's an Anthropic key")],
)  # fmt: skip
def test_a_key_that_doesnt_work_is_not_saved_and_says_why(fresh, http_mock, key, status, says):
    route = _models(http_mock, status or 200)
    r = client_for(fresh).put("/api/ai/key", headers=W, json={"key": key})
    assert r.status_code == 400 and says in r.json()["detail"]
    assert get_secret(connect.KEY_REF) is None
    assert route.called == (status is not None)  # a malformed key never leaves the computer


def test_the_engine_uses_the_saved_key_or_the_environment(monkeypatch):
    from areao1.engine.openai_engine import OpenAIEngine

    assert OpenAIEngine().key() is None
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    assert OpenAIEngine().key() == KEY and connect.key_source() == "environment"
    connect.save_key("sk-proj-saved" + "y" * 30)
    assert OpenAIEngine().key().startswith("sk-proj-saved") and connect.key_source() == "keychain"


def test_an_anthropic_key_from_before_leaves_the_keychain(fresh):
    set_secret(connect.OLD_KEY_REF, "sk-ant-api03-old")
    client_for(fresh)  # the app starts
    assert get_secret(connect.OLD_KEY_REF) is None


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


def test_only_a_key_or_later_is_offered(fresh):
    """The onboarding step takes an OpenAI key or "later", nothing else (no login option)."""
    c = client_for(fresh)
    answer_all(c, upload(c, "maya"), ai=None)
    assert c.post("/api/onboarding/ai", headers=W, json={"choice": "login"}).status_code == 422
    assert c.post("/api/onboarding/ai", headers=W, json={"choice": "skip"}).json()["state"]["ai"] == "skipped"


def test_an_old_login_choice_asks_again(fresh):
    from areao1.onboarding.api import _advance

    c = client_for(fresh)
    answer_all(c, upload(c, "maya"), ai=None)  # every question answered
    state = fresh.onboarding()
    state.step, state.ai = "questions", "login"  # a file from before the login option was removed
    _advance(state)
    assert state.step == "ai"


def test_status_says_how_area_o1_reaches_the_ai_and_what_it_costs(fresh, monkeypatch):
    c: TestClient = client_for(fresh)
    s = c.get("/api/ai").json()
    assert (
        not s["ready"]
        and "works without one" in s["how"]
        and "OpenAI API key" in s["how"]
        and "monthly cap" in s["cost"]
    )
    monkeypatch.setenv("OPENAI_API_KEY", KEY)
    s = c.get("/api/ai").json()
    assert s["key"] == "environment" and s["ready"]
