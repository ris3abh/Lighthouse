"""The CI workflow runs every check the spec requires (SPEC 12: lint, type-check, tests, web build,
schema validation of the fixture workspaces), on the oldest and a current supported Python."""

from __future__ import annotations

import ast
import sys
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
    for needle in ("ruff check .", "ruff format --check .", "mypy", "pytest", "areao1 validate",
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
    assert "npm --prefix web test" in cmds  # the navigation unit tests (back / forward) run in CI
    assert (ROOT / "web" / "package-lock.json").exists()
    assert "tsc -b" in (ROOT / "web" / "package.json").read_text()  # the build type-checks


def test_workflow_is_least_privilege_and_triggers_on_prs():
    wf = _workflow()
    assert wf["permissions"] == {"contents": "read"}
    triggers = wf[True] if True in wf else wf["on"]  # PyYAML parses the bare key `on` as True
    assert "pull_request" in triggers and "push" in triggers


# ---------------------------------------------------------------- the wheel is the product (ADR 0013, S2)

RELEASE = ROOT / ".github" / "workflows" / "release.yml"
SMOKE = ROOT / "scripts" / "smoke_wheel.py"


def _triggers(wf: dict) -> dict:
    return wf[True] if True in wf else wf["on"]


def _builds_and_smoke_tests_the_wheel(job: dict) -> None:
    cmds = _commands(job)
    for needle in ("npm --prefix web ci", "npm --prefix web run build", "python -m build", "python -m venv",
                   "pip install dist/*.whl", "scripts/smoke_wheel.py"):  # fmt: skip
        assert needle in cmds, needle
    assert "pip install -e" not in cmds  # the installed wheel, never the checkout
    # the UI is built before the wheel, and the wheel before the smoke test
    assert (
        cmds.index("npm --prefix web run build") < cmds.index("python -m build") < cmds.index("smoke_wheel")
    )


def test_ci_installs_the_wheel_in_a_clean_venv_and_smoke_tests_it():
    _builds_and_smoke_tests_the_wheel(_workflow()["jobs"]["wheel"])


def test_release_builds_from_tags_and_smoke_tests_before_publishing():
    wf = yaml.safe_load(RELEASE.read_text())
    triggers = _triggers(wf)
    assert set(triggers) == {"push", "workflow_dispatch"}
    assert triggers["push"] == {"tags": ["v*"]}  # never from a branch push
    assert wf["permissions"] == {"contents": "read"}
    jobs = wf["jobs"]
    _builds_and_smoke_tests_the_wheel(jobs["build"])
    assert "GITHUB_REF_NAME" in _commands(jobs["build"])  # the tag must match the package version
    for name in ("github-release", "pypi"):
        assert jobs[name]["needs"] == "build"
        assert "startsWith(github.ref, 'refs/tags/v')" in jobs[name]["if"]  # a manual run publishes nothing
    assert jobs["github-release"]["permissions"] == {"contents": "write"}
    assert "gh release" in _commands(jobs["github-release"])


def test_pypi_uses_trusted_publishing_and_waits_for_the_owner():
    job = yaml.safe_load(RELEASE.read_text())["jobs"]["pypi"]
    assert "vars.PYPI_PUBLISH == 'true'" in job["if"]
    assert job["permissions"] == {"id-token": "write"}
    assert any(s.get("uses", "").startswith("pypa/gh-action-pypi-publish") for s in job["steps"])
    assert not any("password" in s.get("with", {}) for s in job["steps"])  # no API token


def test_sdist_carries_the_built_ui():
    # `python -m build` makes the wheel from the sdist, so the sdist must keep the gitignored UI build.
    hatch = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"]
    for target in ("wheel", "sdist"):
        assert "areao1/server/static/**" in hatch[target]["artifacts"], target


def test_smoke_script_needs_only_the_standard_library_and_localhost():
    tree = ast.parse(SMOKE.read_text())
    modules = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    modules |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    assert modules <= set(sys.stdlib_module_names) | {"__future__"}, modules
    text = SMOKE.read_text()
    assert "http://127.0.0.1" in text and "https://" not in text
    for needle in ("/api/health", "/api/onboarding", '<div id="root">', "--no-open", "--no-scheduler",
                   "AREAO1_CONFIG_DIR"):  # fmt: skip
        assert needle in text, needle
