"""The browser QA suite's plumbing (the suite itself runs with AREAO1_E2E=1): the report tells consistent failures
from flaky ones, per page, with coverage; CI runs it headless; `areao1 qa` exists."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("qa_report", ROOT / "tests" / "e2e" / "report.py")
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)  # type: ignore[union-attr]


def _run(d: Path, findings: list[dict], cov: list[dict]) -> Path:
    d.mkdir(parents=True)
    (d / "findings.jsonl").write_text("".join(json.dumps(f) + "\n" for f in findings))
    (d / "coverage.jsonl").write_text("".join(json.dumps(c) + "\n" for c in cov))
    return d


def test_the_report_separates_consistent_and_flaky_per_page(tmp_path):
    crash = {
        "test": "t",
        "kind": "http_5xx",
        "where": "#/knowledge → button",
        "message": "POST http://127.0.0.1:5001/api/knowledge/sync -> 500",
    }
    blip = {"test": "t", "kind": "console_error", "where": "#/inbox", "message": "net::ERR_ABORTED"}
    dead = {"test": "t", "kind": "dead_control", "where": "#/overview → a", "message": "a did nothing"}
    cov = [{"route": "knowledge", "elements": 10, "exercised": 8, "static": 1, "skipped": 1}]
    one = _run(tmp_path / "1", [crash, blip, dead], cov)
    two = _run(tmp_path / "2", [{**crash, "message": crash["message"].replace("5001", "6002")}, dead], cov)
    s = report.summarize([one, two])
    by = {(f["kind"], f["page"]): f for f in s["issues"]}
    assert (
        not by[("http_5xx", "knowledge")]["flaky"] and by[("http_5xx", "knowledge")]["runs"] == 2
    )  # ports ignored
    assert by[("console_error", "inbox")]["flaky"]
    assert by[("dead_control", "overview")]["warning"]
    pages = {p["page"]: p["status"] for p in s["pages"]}
    assert pages["knowledge"] == "broken" and pages["inbox"] == "warnings" and pages["overview"] == "warnings"
    assert pages["metrics"] == "pass" and s["coverage"] == {"elements": 10, "exercised": 9, "percent": 90.0}
    assert "| knowledge | broken | 1 | 0 | 9/10 |" in report.markdown(s)


def test_ci_runs_the_suite_headless_and_areao1_qa_exists():
    jobs = yaml.safe_load((ROOT / ".github" / "workflows" / "ci.yml").read_text())["jobs"]
    steps = " ".join(str(s.get("run", "")) for s in jobs["e2e"]["steps"])
    assert "playwright install --with-deps chromium" in steps and "pytest tests/e2e" in steps
    assert any(s.get("env", {}).get("AREAO1_E2E") == "1" for s in jobs["e2e"]["steps"])
    from areao1.cli import app

    names = {c.name or c.callback.__name__ for c in app.registered_commands}
    assert "qa" in names
    assert CliRunner().invoke(app, ["qa", "--help"]).exit_code == 0


def test_the_suite_never_touches_a_real_workspace_mailbox_or_key():
    serve = (ROOT / "tests" / "e2e" / "serve.py").read_text()
    assert "no_network()" in serve and "fake_keychain()" in serve and "film_engine" in serve
    harness = (ROOT / "tests" / "e2e" / "harness.py").read_text()
    assert "tempfile.mkdtemp" in harness  # every scenario on a fresh throwaway folder
