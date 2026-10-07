"""The front door (ADR 0013, S1): `lighthouse-gc` with no arguments creates ~/Lighthouse the first time,
remembers it, serves it and opens the browser; later runs and other commands find it again. Nothing is
served for real: uvicorn, the browser and the scheduler are replaced."""

from __future__ import annotations

import json

import pytest
import uvicorn
from typer.testing import CliRunner

from lighthouse_gc import cli, home
from lighthouse_gc.criteria.case import Case


@pytest.fixture
def launched(monkeypatch):
    calls = {"served": [], "opened": []}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls["served"].append(kw))
    monkeypatch.setattr(cli.webbrowser, "open", lambda url: calls["opened"].append(url))
    monkeypatch.setattr(cli, "_running", lambda url: False)
    import lighthouse_gc.jobs.scheduler as scheduler

    monkeypatch.setattr(scheduler, "start", lambda ws: None)
    return calls


def test_no_arguments_creates_remembers_and_opens_the_workspace(launched, user_config, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(cli.app, [])
    assert result.exit_code == 0, result.output
    root = home.default_workspace()
    assert Case(root).exists() and "Created your private workspace" in result.output
    assert json.loads((home.config_dir() / "config.json").read_text())["workspace"] == str(root.resolve())
    assert launched["opened"] == ["http://127.0.0.1:7777"] and launched["served"][0]["host"] == "127.0.0.1"
    again = CliRunner().invoke(cli.app, [])  # second run: reopens, creates nothing
    assert again.exit_code == 0 and "Created" not in again.output and len(launched["served"]) == 2


def test_other_commands_find_the_remembered_workspace(launched, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    CliRunner().invoke(cli.app, [])
    result = CliRunner().invoke(cli.app, ["validate"])
    assert result.exit_code == 0, result.output


def test_a_workspace_in_the_current_directory_wins(launched, tmp_path, monkeypatch):
    other = tmp_path / "other-case"
    assert CliRunner().invoke(cli.app, ["init", str(other), "--no-git"]).exit_code == 0
    assert home.remembered() == other.resolve()  # the first workspace is remembered
    monkeypatch.chdir(other)
    CliRunner().invoke(cli.app, [])
    assert not Case(home.default_workspace()).exists()  # nothing new created


def test_a_non_empty_default_folder_is_never_taken_over(launched, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = home.default_workspace()
    root.mkdir(parents=True)
    (root / "notes.txt").write_text("mine")
    result = CliRunner().invoke(cli.app, [])
    assert result.exit_code == 1 and "lighthouse-gc init <dir>" in result.output
    assert sorted(p.name for p in root.iterdir()) == ["notes.txt"] and not launched["served"]


def test_a_second_launch_opens_the_running_one(launched, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "_running", lambda url: True)
    result = CliRunner().invoke(cli.app, [])
    assert "already running" in result.output and launched["opened"] and not launched["served"]


def test_help_and_version_still_work():
    assert "Usage" in CliRunner().invoke(cli.app, ["--help"]).output
    assert "lighthouse-gc" in CliRunner().invoke(cli.app, ["--version"]).output
