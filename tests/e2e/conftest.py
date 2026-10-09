"""Browser suite (QA): Playwright against throwaway, fictional workspaces served by tests/e2e/serve.py (fake Gmail,
scripted model, in-memory keychain, no network). Runs only with AREAO1_E2E=1 (CI's e2e job, or `areao1 qa`).

Every test records findings through ``qa``; ``errors`` (uncaught JS errors, console errors, 5xx responses, broken
links, serious accessibility violations, horizontal overflow) fail the test, ``warnings`` (dead controls, controls
the keyboard can't reach, 4xx responses, pages slower than 1s) are reported only. The run's findings, coverage and
screenshots go to $AREAO1_QA_OUT (default out/qa, gitignored)."""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import Any

import pytest

from .harness import CHROME, OUT, QA, Server

pytestmark = pytest.mark.skipif(os.environ.get("AREAO1_E2E") != "1", reason="browser suite: set AREAO1_E2E=1")


def pytest_collection_modifyitems(config, items):  # type: ignore[no-untyped-def]
    if os.environ.get("AREAO1_E2E") != "1":
        skip = pytest.mark.skip(reason="browser suite: set AREAO1_E2E=1 (or run `areao1 qa`)")
        for item in items:
            if "tests/e2e" in str(item.fspath):
                item.add_marker(skip)


@pytest.fixture
def serve() -> Iterator[Any]:
    started: list[Server] = []

    def start(scenario: str) -> Server:
        s = Server(scenario)
        started.append(s)
        return s

    yield start
    for s in started:
        s.close()


# ----------------------------------------------------------------------------------------------- browser


@pytest.fixture(scope="session")
def shared() -> Iterator[Any]:
    """Read-only scenarios shared across tests (the page matrix only looks, never clicks)."""
    started: dict[str, Server] = {}

    def get(scenario: str) -> Server:
        if scenario not in started:
            started[scenario] = Server(scenario)
        return started[scenario]

    yield get
    for s in started.values():
        s.close()


@pytest.fixture(scope="session")
def browser() -> Iterator[Any]:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        local = CHROME.exists() and not os.environ.get("CI")
        b = p.chromium.launch(executable_path=str(CHROME) if local else None, headless=True)
        yield b
        b.close()


@pytest.fixture
def qa(request: Any) -> Iterator[QA]:
    q = QA(request.node.name)
    yield q
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "findings.jsonl").open("a", encoding="utf-8") as f:
        for x in q.findings:
            f.write(json.dumps(x, default=str) + "\n")
    if q.coverage:
        with (OUT / "coverage.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps({"test": q.test, **q.coverage}) + "\n")
