"""The CI workflow runs every check the spec requires (SPEC 12: lint, type-check, tests, web build,
schema validation of the fixture workspaces), on the oldest and a current supported Python."""

from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "ci.yml"


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def _commands(job: dict) -> str:
    return "\n".join(step.get("run", "") for step in job["steps"])


def test_python_job_runs_all_checks():
    job = _workflow()["jobs"]["python"]
    cmds = _commands(job)
    for needle in ("ruff check .", "ruff format --check .", "mypy", "pytest", "lighthouse-gc validate",
                   "tests/fixtures/workspaces/", "scripts/check_repo.py", "pip install -e '.[dev]'"):  # fmt: skip
        assert needle in cmds, needle


def test_python_matrix_covers_minimum_supported_version():
    requires = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["requires-python"]
    minimum = requires.removeprefix(">=")
    assert minimum in _workflow()["jobs"]["python"]["strategy"]["matrix"]["python"]


def test_web_job_builds_with_lockfile():
    job = _workflow()["jobs"]["web"]
    cmds = _commands(job)
    assert "npm --prefix web ci" in cmds and "npm --prefix web run build" in cmds
    assert (ROOT / "web" / "package-lock.json").exists()
    assert "tsc -b" in (ROOT / "web" / "package.json").read_text()  # the build type-checks


def test_workflow_is_least_privilege_and_triggers_on_prs():
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    triggers = wf[True] if True in wf else wf["on"]  # PyYAML parses the bare key `on` as True
    assert "pull_request" in triggers and "push" in triggers
