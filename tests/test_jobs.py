"""deadline-check, digest, biweekly snapshots, sync alerts and the scheduler (fixed dates, fake channels)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from conftest import mock_github
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from lighthouse_gc import notify
from lighthouse_gc.cli import app
from lighthouse_gc.core.models import Deadline, Deadlines, Pipeline, PipelineItem
from lighthouse_gc.core.workspace import _atomic_write, dump_model
from lighthouse_gc.jobs import JOBS, alerts, scheduler
from lighthouse_gc.scaffold import validate_workspace
from lighthouse_gc.server.app import create_app

TODAY = date(2026, 10, 6)


class Recorder:
    def __init__(self):
        self.sent = []

    def send(self, note, cfg, secret):
        self.sent.append(note)


@pytest.fixture
def sent(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(
        notify, "CHANNELS", lambda: {k: rec for k in ("desktop", "email", "slack", "discord", "ntfy")}
    )
    return rec.sent


def _deadlines(ws, *items):
    _atomic_write(ws.data_dir / "deadlines.json", dump_model(Deadlines(deadlines=list(items))))


def _dl(i, days, **kw):
    return Deadline(id=f"dl_{i}", title=f"Deadline {i}", due=TODAY + timedelta(days=days), **kw)


# ----------------------------------------------------------------------------- deadline-check


def test_alert_buckets(ws):
    _deadlines(ws, _dl("a", 10), _dl("b", 3), _dl("c", 0), _dl("d", -2), _dl("e", 20), _dl("f", 1, done=True),
               _dl("g", -40))  # fmt: skip
    buckets = {i["id"]: i["bucket"] for i in alerts.due_items(ws, TODAY)}
    assert buckets == {"dl_a": "14", "dl_b": "3", "dl_c": "0", "dl_d": "overdue"}


def test_followups_alert_within_three_days(ws):
    pl = Pipeline(items=[
        PipelineItem(id="p1", title="IEEE", stage="applied", follow_up=TODAY + timedelta(days=2)),
        PipelineItem(id="p2", title="Later", stage="waiting", follow_up=TODAY + timedelta(days=6)),
        PipelineItem(id="p3", title="Done", stage="done", follow_up=TODAY),
    ])  # fmt: skip
    _atomic_write(ws.data_dir / "pipeline.json", dump_model(pl))
    items = alerts.due_items(ws, TODAY)
    assert [(i["title"], i["bucket"]) for i in items] == [("Follow up: IEEE", "3")]


def test_each_threshold_alerts_once(ws, sent):
    _deadlines(ws, _dl("ieee", 3, url="https://example.org/ieee"))
    alerts.deadline_check(ws, TODAY)
    assert [n.title for n in sent] == ["Deadline ieee: due in 3 days"]
    assert sent[0].priority == "default" and sent[0].key == "deadline:dl_ieee:3"
    alerts.deadline_check(ws, TODAY)
    assert len(sent) == 1  # same bucket: no repeat
    alerts.deadline_check(ws, TODAY + timedelta(days=2))  # 1 day left: next bucket
    assert sent[-1].title == "Deadline ieee: due in 1 day" and sent[-1].priority == "high"
    alerts.deadline_check(ws, TODAY + timedelta(days=4))
    assert sent[-1].title == "Deadline ieee: overdue by 1 day"


def test_minimal_alert_has_no_title(ws, sent):
    _deadlines(ws, _dl("secret-sauce", 0))
    alerts.deadline_check(ws, TODAY)
    assert "secret-sauce" not in sent[0].minimal_body


def test_failed_send_is_retried_next_run(ws, monkeypatch):
    class Broken:
        def send(self, *a):
            raise RuntimeError("offline")

    _deadlines(ws, _dl("x", 3))
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": Broken()})
    alerts.deadline_check(ws, TODAY)
    rec = Recorder()
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": rec})
    alerts.deadline_check(ws, TODAY)
    assert len(rec.sent) == 1  # nothing was delivered the first time, so it goes out now


# ----------------------------------------------------------------------------- digest


def test_digest_lists_stale_items_deadlines_and_actions(demo_ws, sent):
    pl = demo_ws.pipeline()
    pl.items[0].moved_at = datetime(2026, 9, 1, tzinfo=UTC)  # 35 days without movement
    _atomic_write(demo_ws.data_dir / "pipeline.json", dump_model(pl))
    d = alerts.build_digest(demo_ws, TODAY, since=date(2026, 10, 1))
    text = d["text"]
    assert "2 banked / 3 needed" in text
    assert "IEEE Senior Member (applied, 35 days)" in text
    assert "2026-10-09: Send draft letter to Dr. Priya Natarajan" in text
    assert "arivera-demo/fastgrad stars: 1751 → 1840 (+89)" in text
    assert "Inbox: 12 pending." in text
    assert d["minimal"].startswith("Weekly digest: 12 to review")

    lines = alerts.digest(demo_ws, TODAY)
    assert sent[-1].event == "digest" and sent[-1].key == "digest:2026-10-06"
    assert lines[-1].startswith("sent → desktop: sent")


# ----------------------------------------------------------------------------- the job wrappers


def test_scheduled_snapshot_is_biweekly(demo_ws, http_mock):
    _, run = JOBS["metrics-snapshot"]
    assert run(demo_ws, True)[0].startswith("skipped: last snapshot")  # demo's last snapshot is today
    mock_github(http_mock)
    http_mock.route(host="huggingface.co").respond(json={})
    manual = run(demo_ws, False)
    assert not manual[0].startswith("skipped")  # a person pressing "Snapshot now" always runs


def test_sync_job_alerts_on_new_candidates_and_errors(ws, http_mock, sent):
    from lighthouse_gc.jobs.sync import import_source

    mock_github(http_mock)
    import_source(ws, "https://github.com/arivera-demo", sleep=lambda s: None)
    ws.save_inbox(ws.inbox().model_copy(update={"candidates": []}))  # pretend they were never seen
    http_mock.route(method="GET", host="api.github.com", path="/repos/arivera-demo/tinyserve").respond(
        404, json={}
    )
    _, run = JOBS["sync"]
    run(ws, True)
    events = [n.event for n in sent]
    assert "new_candidates" in events and "sync_error" in events


# ----------------------------------------------------------------------------- scheduler


def test_scheduler_registers_jobs_from_config(demo_ws):
    sched = scheduler.start(demo_ws)
    try:
        ids = {j.id for j in sched.get_jobs() if not j.id.startswith("catchup-")}
        assert ids == {"sync", "metrics-snapshot", "deadline-check", "digest"}
        digest = sched.get_job("digest")
        assert digest.next_run_time.weekday() == 4 and digest.next_run_time.hour == 17  # Friday 17:00
    finally:
        sched.shutdown(wait=False)


def test_missed_runs_catch_up(ws):
    tz = scheduler.get_localzone()
    now = datetime(2026, 10, 6, 12, 0, tzinfo=tz)
    state = {
        "deadline-check": {"last_run": datetime(2026, 10, 4, 6, 0, tzinfo=tz).isoformat()},  # missed 2 runs
        "digest": {"last_run": datetime(2026, 10, 2, 18, 0, tzinfo=tz).isoformat()},
    }  # next is Fri 10-09
    scheduler._save_state(ws, state)
    assert scheduler.missed(ws, now) == ["deadline-check"]


def test_run_job_records_state_and_survives_failures(ws, monkeypatch):
    result = scheduler.run_job(ws, "dashboard")
    assert result["ok"] and "DASHBOARD.md written" in result["summary"][0]
    monkeypatch.setitem(JOBS, "dashboard", ("boom", lambda ws, s: 1 / 0))
    bad = scheduler.run_job(ws, "dashboard")
    assert not bad["ok"] and "ZeroDivisionError" in bad["summary"][0]
    assert scheduler.load_state(ws)["dashboard"]["ok"] is False


def test_jobs_status_and_bad_cron(ws):
    status = {j["name"]: j for j in scheduler.jobs_status(ws)}
    assert status["digest"]["schedule"] == "0 17 * * fri" and status["digest"]["next_run"]
    assert status["dashboard"]["schedule"] is None
    cfg = ws.config()
    cfg.schedules["digest"] = "every friday"
    cfg.schedules["gardening"] = "0 1 * * *"
    ws.save_config(cfg)
    problems = validate_workspace(ws)
    assert any("schedules.digest" in p for p in problems)
    assert any("unknown job 'gardening'" in p for p in problems)


def test_cli_and_api(ws, sent):
    _deadlines(ws, _dl("soon", 1))
    result = CliRunner().invoke(app, ["run", "deadline-check", "-w", str(ws.root)])
    assert result.exit_code == 0, result.output
    assert "Deadline soon: due in 1 day" in result.output
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    names = {j["name"] for j in c.get("/api/jobs").json()}
    assert {"sync", "metrics-snapshot", "deadline-check", "digest", "dashboard"} == names
    r = c.post("/api/jobs/dashboard/run", headers={"X-Lighthouse": "1"})
    assert r.status_code == 200 and r.json()["ok"]
    assert c.post("/api/jobs/nope/run", headers={"X-Lighthouse": "1"}).status_code == 404
