"""End to end: `import <url>` auto-detects the connector; sync and metrics-snapshot write the workspace."""

from __future__ import annotations

import pytest
from conftest import mock_github, mock_hf
from typer.testing import CliRunner

from lighthouse_gc import sources
from lighthouse_gc.cli import app
from lighthouse_gc.jobs import sync as jobs
from lighthouse_gc.sources.http import SourceError


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("https://github.com/arivera-demo", "github"),
        ("gh:arivera-demo/fastgrad", "github"),
        ("https://huggingface.co/arivera-demo", "huggingface"),
        ("https://huggingface.co/datasets/arivera-demo/robo-grasp-10k", "huggingface"),
        ("hf:arivera-demo", "huggingface"),
    ],
)
def test_detect_routes_to_connector(text, kind):
    assert sources.detect(text) == kind


def test_detect_unknown():
    with pytest.raises(ValueError, match="No connector"):
        sources.detect("https://linkedin.com/in/someone")


def test_import_github_public(ws, http_mock):
    mock_github(http_mock)
    report = jobs.import_source(ws, "https://github.com/arivera-demo", sleep=lambda s: None)
    assert report.items == 2 and report.new_items == 2 and not report.errors
    src = ws.sources().sources[0]
    assert src.id == "github:arivera-demo" and src.auth == "none" and src.last_sync
    metrics = {(r.item, r.metric) for r in ws.metrics()}
    assert ("arivera-demo/fastgrad", "stars") in metrics and ("arivera-demo/tinyserve", "forks") in metrics
    titles = {c.title for c in ws.pending_candidates()}
    assert "Open-source project: arivera-demo/fastgrad" in titles
    assert "Open-source project: arivera-demo/tinyserve" in titles
    assert "arXiv 2502.01234" in titles
    assert "github:arivera-demo" in (ws.root / "DASHBOARD.md").read_text()


def test_import_is_idempotent(ws, http_mock):
    mock_github(http_mock)
    jobs.import_source(ws, "https://github.com/arivera-demo", sleep=lambda s: None)
    n_rows, n_cands = len(ws.metrics()), len(ws.inbox().candidates)
    again = jobs.import_source(ws, "https://github.com/arivera-demo", sleep=lambda s: None)
    assert again.new_items == 0 and again.candidates_added == 0
    assert len(ws.metrics()) == n_rows and len(ws.inbox().candidates) == n_cands
    assert len(ws.sources().sources) == 1


def test_import_with_pat_stores_token_in_keychain_only(ws, http_mock, fake_keyring):
    mock_github(http_mock, authed=True)
    report = jobs.import_source(ws, "github:arivera-demo", token="github_pat_SECRET123", sleep=lambda s: None)
    assert report.items == 3  # includes the private repo
    assert fake_keyring[("lighthouse-gc", "github:arivera-demo")] == "github_pat_SECRET123"
    src = ws.sources().sources[0]
    assert src.auth == "token" and src.secret_ref == "github:arivera-demo"
    for path in ws.root.rglob("*"):
        if path.is_file() and ".lighthouse/cache" not in path.as_posix():
            assert b"github_pat_SECRET123" not in path.read_bytes(), path
    assert any(r.metric == "views" for r in ws.metrics())


def test_import_huggingface_dedupes_shared_paper(ws, http_mock):
    mock_hf(http_mock)
    report = jobs.import_source(ws, "https://huggingface.co/arivera-demo", sleep=lambda s: None)
    assert report.items == 4
    pending = ws.pending_candidates()
    papers = [c for c in pending if c.proposed_criterion == "scholarly_articles"]
    assert len(papers) == 1  # model and dataset both link arXiv:2509.04321
    kinds = {c.evidence_type for c in pending}
    assert {"ml_model", "dataset", "open_source_project", "preprint"} == kinds


def test_import_bad_handle_is_not_saved(ws, http_mock):
    http_mock.route(method="GET", host="api.github.com", path="/users/ghost-404").respond(404, json={})
    with pytest.raises(SourceError, match="token"):
        jobs.import_source(ws, "https://github.com/ghost-404", sleep=lambda s: None)
    assert ws.sources().sources == []


def test_sync_and_snapshot_jobs(ws, http_mock):
    mock_github(http_mock)
    jobs.import_source(ws, "https://github.com/arivera-demo", snapshot=False, sleep=lambda s: None)
    assert ws.metrics() == []
    [snap] = jobs.snapshot(ws, sleep=lambda s: None)
    assert snap.metrics_written > 0 and snap.candidates_added == 0
    [sync] = jobs.sync(ws, sleep=lambda s: None)
    assert sync.metrics_written == 0 and sync.candidates_added == 0  # already proposed on import


def test_sync_records_errors_per_source(ws, http_mock):
    mock_github(http_mock)
    jobs.import_source(ws, "https://github.com/arivera-demo", sleep=lambda s: None)
    http_mock.routes.clear()
    http_mock.route(method="GET", host="api.github.com").respond(500)
    [report] = jobs.sync(ws, sleep=lambda s: None)
    assert report.errors
    assert ws.sources().sources[0].last_error


def test_missing_token_is_reported(ws, http_mock, fake_keyring):
    mock_github(http_mock, authed=True)
    jobs.import_source(ws, "github:arivera-demo", token="tok", sleep=lambda s: None)
    fake_keyring.clear()
    [report] = jobs.sync(ws, sleep=lambda s: None)
    assert "token missing" in report.errors[0]


# ----------------------------------------------------------------------------- CLI


def test_cli_init_import_run(tmp_path, http_mock):
    mock_github(http_mock)
    runner = CliRunner()
    case = tmp_path / "my-case"
    result = runner.invoke(app, ["init", str(case), "--name", "Test Person", "--no-git"])
    assert result.exit_code == 0, result.output

    result = runner.invoke(app, ["import", "https://github.com/arivera-demo", "-w", str(case)])
    assert result.exit_code == 0, result.output
    assert "Detected github" in result.output and "2 item(s)" in result.output

    result = runner.invoke(app, ["run", "metrics-snapshot", "-w", str(case)])
    assert result.exit_code == 0, result.output
    assert "github:arivera-demo" in result.output

    result = runner.invoke(app, ["run", "dashboard", "-w", str(case)])
    assert "0 banked / 3 needed" in result.output

    result = runner.invoke(app, ["validate", "-w", str(case)])
    assert result.exit_code == 0, result.output


def test_cli_import_unknown_url(ws):
    result = CliRunner().invoke(app, ["import", "https://example.com/me", "-w", str(ws.root)])
    assert result.exit_code == 1 and "No connector" in result.output


def test_cli_run_unknown_job(ws):
    result = CliRunner().invoke(app, ["run", "nope", "-w", str(ws.root)])
    assert result.exit_code == 1


def test_cli_finds_workspace_from_env(ws, monkeypatch):
    monkeypatch.setenv("LIGHTHOUSE_GC_WORKSPACE", str(ws.root))
    result = CliRunner().invoke(app, ["validate"])
    assert result.exit_code == 0, result.output
