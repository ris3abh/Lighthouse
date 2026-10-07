"""Shared fixtures. No test touches the network: HTTP is served from tests/fixtures via respx, and the OS
keychain is replaced with an in-memory dict."""

from __future__ import annotations

import json
import os
import shutil
from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from areao1.criteria.case import Case
from areao1.scaffold import create_workspace

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 10, 6)
ALEX = Path(__file__).parent / "fixtures" / "workspaces" / "alex-rivera"  # the fictional fixture case


def fixture_json(*parts: str):
    return json.loads((FIXTURES.joinpath(*parts)).read_text())


@pytest.fixture(autouse=True)
def user_config(tmp_path_factory, monkeypatch):
    """Never read or write the real ~/.config/areao1 or ~/AreaO1."""
    d = tmp_path_factory.mktemp("userconfig")
    monkeypatch.setenv("AREAO1_CONFIG_DIR", str(d / "config"))
    monkeypatch.setenv("AREAO1_HOME", str(d / "AreaO1"))
    monkeypatch.delenv("AREAO1_WORKSPACE", raising=False)
    for name in list(os.environ):  # Lighthouse-era variables on the developer's machine never leak in
        if name.startswith(("LIGHTHOUSE_GC_", "LIGHTHOUSE_MODEL_")):
            monkeypatch.delenv(name)
    return d


@pytest.fixture(autouse=True)
def no_real_model(monkeypatch):
    """Tests never call a real model: the real engine reports itself unavailable, whatever this machine has
    installed or logged in. Tests that need an agent inject the scripted FakeEngine."""
    from areao1.engine.claude_code import ClaudeAgentEngine

    real = ClaudeAgentEngine.available

    def available(self):
        if self._query is not None:  # a test injected a scripted query function
            return real(self)
        return False, "no real model in tests"

    monkeypatch.setattr(ClaudeAgentEngine, "available", available)

    real_run = ClaudeAgentEngine.run

    async def run(self, *a, **k):
        if self._query is None:
            raise AssertionError("a test tried to call a real model")
        return await real_run(self, *a, **k)

    monkeypatch.setattr(ClaudeAgentEngine, "run", run)


@pytest.fixture(autouse=True)
def fake_keyring(monkeypatch):
    import keyring

    store: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(keyring, "get_password", lambda s, k: store.get((s, k)))
    monkeypatch.setattr(keyring, "set_password", lambda s, k, v: store.__setitem__((s, k), v))

    def delete(s, k):
        store.pop((s, k), None)

    monkeypatch.setattr(keyring, "delete_password", delete)
    return store


@pytest.fixture
def ws(tmp_path) -> Case:
    return create_workspace(tmp_path / "case", name="Test Person", git=False)


@pytest.fixture
def demo_ws(tmp_path) -> Case:
    target = tmp_path / "demo"
    shutil.copytree(ALEX, target)
    return Case(target)


@pytest.fixture
def no_sleep():
    calls: list[float] = []
    return calls.append, calls


# ----------------------------------------------------------------------------- GitHub

GH = "api.github.com"


def _link_last(path: str, last: int) -> dict[str, str]:
    return {
        "link": f'<https://api.github.com{path}?per_page=1&page=2>; rel="next", '
        f'<https://api.github.com{path}?per_page=1&page={last}>; rel="last"'
    }


def mock_github(router: respx.MockRouter, *, authed: bool = False, include_private: bool = True) -> None:
    g = lambda path, **kw: router.route(method="GET", host=GH, path=path, **kw)  # noqa: E731
    g("/users/arivera-demo").respond(json=fixture_json("github", "user.json"))
    g("/users/arivera-demo/repos").respond(json=fixture_json("github", "user_repos.json"))
    if authed:
        g("/user").respond(json=fixture_json("github", "auth_user.json"))
        g("/user/repos").respond(
            json=fixture_json("github", "auth_user_repos.json" if include_private else "user_repos.json")
        )
    else:
        g("/user").respond(401, json={"message": "Requires authentication"})
    for name in ("fastgrad", "tinyserve"):
        g(f"/repos/arivera-demo/{name}").respond(json=fixture_json("github", f"repo_{name}.json"))
    g("/repos/arivera-demo/thesis-code").respond(
        json={
            **fixture_json("github", "repo_tinyserve.json"),
            "name": "thesis-code",
            "full_name": "arivera-demo/thesis-code",
            "private": True,
            "stargazers_count": 0,
            "forks_count": 0,
            "html_url": "https://github.com/arivera-demo/thesis-code",
        }
    )
    contributors = fixture_json("github", "contributors_page1.json")
    releases = fixture_json("github", "releases_page1.json")
    g("/repos/arivera-demo/fastgrad/contributors").respond(
        json=contributors, headers=_link_last("/repositories/1/contributors", 37)
    )
    g("/repos/arivera-demo/fastgrad/releases").respond(
        json=releases, headers=_link_last("/repositories/1/releases", 12)
    )
    g("/repos/arivera-demo/tinyserve/contributors").respond(json=contributors)
    g("/repos/arivera-demo/tinyserve/releases").respond(json=[])
    g("/repos/arivera-demo/thesis-code/contributors").respond(status_code=204)
    g("/repos/arivera-demo/thesis-code/releases").respond(json=[])
    g("/repos/arivera-demo/fastgrad/readme").respond(
        text=(FIXTURES / "github" / "readme_fastgrad.md").read_text()
    )
    g("/repos/arivera-demo/tinyserve/readme").respond(404, json={"message": "Not Found"})
    g("/repos/arivera-demo/thesis-code/readme").respond(404, json={"message": "Not Found"})
    if authed:
        g("/repos/arivera-demo/fastgrad/traffic/views").respond(
            json=fixture_json("github", "traffic_views.json")
        )
        g("/repos/arivera-demo/fastgrad/traffic/clones").respond(
            json=fixture_json("github", "traffic_clones.json")
        )
        for name in ("tinyserve", "thesis-code"):
            for kind in ("views", "clones"):
                g(f"/repos/arivera-demo/{name}/traffic/{kind}").respond(
                    403, json={"message": "Resource not accessible by personal access token"}
                )


# ----------------------------------------------------------------------------- Hugging Face

HF = "huggingface.co"


def mock_hf(router: respx.MockRouter) -> None:
    h = lambda path, **kw: router.route(method="GET", host=HF, path=path, **kw)  # noqa: E731
    h("/api/models", params__contains={"author": "arivera-demo"}).respond(
        json=fixture_json("huggingface", "models_list.json")
    )
    h("/api/models", params__contains={"filter": "base_model:arivera-demo/tiny-vlm"}).respond(
        json=fixture_json("huggingface", "derivatives_tiny-vlm.json")
    )
    h("/api/models", params__contains={"filter": "base_model:arivera-demo/scratch-model"}).respond(json=[])
    h("/api/datasets", params__contains={"author": "arivera-demo"}).respond(
        json=fixture_json("huggingface", "datasets_list.json")
    )
    h("/api/spaces", params__contains={"author": "arivera-demo"}).respond(
        json=fixture_json("huggingface", "spaces_list.json")
    )
    h("/api/models/arivera-demo/tiny-vlm").respond(json=fixture_json("huggingface", "model_tiny-vlm.json"))
    h("/api/models/arivera-demo/scratch-model").respond(
        json=fixture_json("huggingface", "model_scratch-model.json")
    )
    h("/api/datasets/arivera-demo/robo-grasp-10k").respond(
        json=fixture_json("huggingface", "dataset_robo-grasp-10k.json")
    )
    h("/api/spaces/arivera-demo/tiny-vlm-demo").respond(
        json=fixture_json("huggingface", "space_tiny-vlm-demo.json")
    )
    h("/api/papers/2509.04321").respond(json=fixture_json("huggingface", "paper_2509.04321.json"))


@pytest.fixture
def http_mock():
    """respx router that fails any request that isn't explicitly mocked (i.e. no live network)."""
    with respx.mock(assert_all_called=False, assert_all_mocked=True) as router:
        yield router


__all__ = ["TODAY", "fixture_json", "httpx", "mock_github", "mock_hf"]
