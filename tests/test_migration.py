"""From Lighthouse to Area O1 (ADR 0010 §2): a Lighthouse-era setup keeps working. Its workspace files, user
config folder, keychain entries and environment variables are found and moved once, each with a one-line
notice; a second run moves nothing; the old command and the old write header still work."""

from __future__ import annotations

import json

import keyring
import pytest
import uvicorn
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from areao1 import cli, home
from areao1.core import migrate, names
from areao1.core.secrets import get_secret
from areao1.criteria.case import Case
from areao1.scaffold import create_workspace
from areao1.server.app import create_app


@pytest.fixture
def lighthouse_era(tmp_path, monkeypatch):
    """A machine that ran Lighthouse: ~/.config/lighthouse-gc remembering ~/Lighthouse, a workspace with
    lighthouse.yaml and .lighthouse/, a token under the old keychain service, and old environment variables."""
    migrate.NOTICES.clear()
    monkeypatch.delenv("AREAO1_CONFIG_DIR", raising=False)
    monkeypatch.delenv("AREAO1_HOME", raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    ws = create_workspace(tmp_path / "Lighthouse", name="Maya Chen", git=False)
    (ws.root / names.WORKSPACE_CONFIG).rename(ws.root / "lighthouse.yaml")
    (ws.root / names.WORKSPACE_STATE).rename(ws.root / ".lighthouse")
    ignore = ws.root / ".gitignore"
    ignore.write_text(ignore.read_text().replace(names.WORKSPACE_STATE, ".lighthouse"))
    (ws.root / "data" / "onboarding.json").write_text(json.dumps({
        "schema_version": 1, "status": "in_progress", "step": "questions",
        "transcript": [{"who": "lighthouse", "text": "Nice to meet you, Maya!"}]}))  # fmt: skip
    old_cfg = tmp_path / "config" / "lighthouse-gc"
    old_cfg.mkdir(parents=True)
    (old_cfg / "config.json").write_text(json.dumps({"workspace": str(ws.root)}))
    keyring.set_password("lighthouse-gc", "github:maya", "ghp_lighthouse_era_token")
    monkeypatch.setenv("LIGHTHOUSE_MODEL_HARD", "gpt-6-astra")
    monkeypatch.setenv("LIGHTHOUSE_GC_SPEC", "ignored-by-the-app")
    return ws.root, tmp_path


@pytest.fixture
def launched(monkeypatch):
    calls: dict[str, list] = {"served": [], "opened": []}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls["served"].append(kw))
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: calls["opened"].append(url))
    monkeypatch.setattr(cli, "_running", lambda url: None)
    import areao1.jobs.scheduler as scheduler

    monkeypatch.setattr(scheduler, "start", lambda ws: None)
    return calls


def test_a_lighthouse_era_setup_is_found_and_moved_once(lighthouse_era, launched, monkeypatch):
    root, tmp = lighthouse_era
    monkeypatch.chdir(tmp)
    result = CliRunner().invoke(cli.app, [])
    assert result.exit_code == 0, result.output
    # the remembered workspace is still the one at ~/Lighthouse, now renamed inside
    assert launched["served"] and home.remembered() == root.resolve()
    assert (root / "areao1.yaml").is_file() and not (root / "lighthouse.yaml").exists()
    assert (root / ".areao1").is_dir() and not (root / ".lighthouse").exists()
    assert ".lighthouse" not in (root / ".gitignore").read_text()
    assert (tmp / "config" / "areao1" / "config.json").is_file()  # settings copied over
    # the old onboarding transcript still loads
    assert Case(root).onboarding().transcript[0].who == "areao1"
    # secrets: found under the old service, copied to the new one
    assert get_secret("github:maya") == "ghp_lighthouse_era_token"
    assert keyring.get_password(names.KEYCHAIN_SERVICE, "github:maya") == "ghp_lighthouse_era_token"
    # old environment variables still work, with a notice naming the new one
    from areao1.agent.routing import route

    assert route("chat").model == "gpt-6-astra"
    said = " ".join(migrate.NOTICES)
    for needle in ("AREAO1_MODEL_HARD", "areao1.yaml", "keychain", "copied your settings"):
        assert needle in said, needle
    assert all(len(n.splitlines()) == 1 for n in migrate.NOTICES)  # one line each
    # a second run moves nothing
    migrate.NOTICES.clear()
    monkeypatch.delenv("LIGHTHOUSE_MODEL_HARD")
    CliRunner().invoke(cli.app, [])
    get_secret("github:maya")
    assert migrate.NOTICES == []


def test_the_old_command_still_works_and_says_the_new_name(lighthouse_era, launched, monkeypatch, capsys):
    root, tmp = lighthouse_era
    monkeypatch.chdir(tmp)
    monkeypatch.setattr("sys.argv", ["lighthouse-gc", "--version"])
    with pytest.raises(SystemExit):
        cli.deprecated()
    err = capsys.readouterr().err
    assert "lighthouse-gc is now areao1" in err


def test_a_tab_left_open_across_the_rename_still_saves(ws):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    body = {"title": "Call with the attorney", "due": "2026-10-20", "kind": "personal"}
    assert c.post("/api/deadlines", json=body).status_code == 403  # still needs the header
    assert c.post("/api/deadlines", json=body, headers={"X-Lighthouse": "1"}).status_code < 400
    assert c.post("/api/deadlines", json={**body, "title": "x"}, headers={"X-AreaO1": "1"}).status_code < 400
