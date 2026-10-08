"""J1: the dev-only filming workspace builds offline, its scripted chat answer verifies, and the keypress invitation
comes out verified (and the look-alike one suspicious). Everything is fictional."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).parents[1]


@pytest.fixture
def film(monkeypatch):
    spec = importlib.util.spec_from_file_location("film_demo", ROOT / "scripts" / "film_demo.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    from areao1.google import mail

    monkeypatch.setattr(mail, "IMAP", mail.IMAP)  # restored after the test (build installs the fake)
    monkeypatch.setattr(mail, "SMTP", mail.SMTP)
    return mod


def test_maya_builds_offline_with_history_a_follow_up_and_a_verified_answer(film, tmp_path):
    from areao1.criteria.case import Case
    from areao1.criteria.constellation import stars
    from areao1.server.app import create_app

    root = tmp_path / "maya"
    film.build(root)
    ws = Case(root)
    sky = stars(ws)["stars"]
    assert len(sky) > 300 and {s["status"] for s in sky} >= {"approved", "pending", "superseded"}
    assert (
        any(s["conflict"] for s in sky) and len({s["date"][:7] for s in sky}) > 12
    )  # history for the replay
    assert [d.drafted_by for d in ws.outreach().drafts] == ["follow-up"]
    assert ws.person().name == "Maya Chen" and ws.onboarding().status == "done"
    with TestClient(create_app(ws, allowed_hosts=["testserver"], engine=film.film_engine())) as c:
        run_id = c.post(
            "/api/agent/chat", headers={"X-AreaO1": "1"}, json={"message": "Where do I stand?"}
        ).json()["run_id"]
        for _ in range(100):
            run = c.get(f"/api/agent/runs/{run_id}").json()
            if run["status"] != "running":
                break
            anyio.run(anyio.sleep, 0.05)
    assert run["status"] == "done" and film.RULE in run["text"]
    assert [x["status"] for x in run["rule_check"]["claims"]] == ["verified"]


def test_the_keypress_invites(film, tmp_path):
    from areao1.criteria.case import Case

    root = tmp_path / "maya"
    film.build(root)
    film.invite(root, True)
    film.invite(root, False)
    finds = {
        c.title: c.verification for c in Case(root).pending_candidates() if c.fingerprint.startswith("opp:")
    }
    assert list(finds.values()).count("verified") == 1 and list(finds.values()).count("suspicious") == 1


def test_it_never_ships():
    import tomllib

    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert project["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["areao1"]
    assert not any(
        p.startswith("scripts") for p in project["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]
    )


def test_the_filming_checklist_covers_window_theme_bookmarks_and_keys():
    doc = (ROOT / "docs" / "filming.md").read_text()
    for needle in (
        "Window size",
        "Hide the bookmarks bar",
        "Theme",
        "Reduce motion",
        "| `j` |",
        "| `u` |",
        "| `r` |",
    ):
        assert needle in doc, needle
