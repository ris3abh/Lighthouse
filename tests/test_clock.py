"""One clock: "today" is the person's local day. Frozen at 23:59 and 00:01, local and UTC, east and west of
Greenwich, every date-dependent feature agrees with the local calendar."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from test_memory import evidence

from areao1.agent.runner import _render_turn
from areao1.core import clock
from areao1.core.memory import Memory
from areao1.jobs import alerts
from areao1.server.app import create_app, pipeline_view
from areao1.service import Service
from areao1.vault.store import _date_values

# (label, the instant, the person's zone, their calendar day at that instant)
SCENARIOS = [
    ("23:59 local, west", datetime(2026, 10, 7, 6, 59, tzinfo=UTC), "America/Los_Angeles", date(2026, 10, 6)),
    ("00:01 local, west", datetime(2026, 10, 7, 7, 1, tzinfo=UTC), "America/Los_Angeles", date(2026, 10, 7)),
    ("23:59 local, east", datetime(2026, 10, 6, 18, 29, tzinfo=UTC), "Asia/Kolkata", date(2026, 10, 6)),
    ("00:01 local, east", datetime(2026, 10, 6, 18, 31, tzinfo=UTC), "Asia/Kolkata", date(2026, 10, 7)),
    ("23:59 UTC, west", datetime(2026, 10, 6, 23, 59, tzinfo=UTC), "America/Los_Angeles", date(2026, 10, 6)),
    ("00:01 UTC, west", datetime(2026, 10, 7, 0, 1, tzinfo=UTC), "America/Los_Angeles", date(2026, 10, 6)),
    ("23:59 UTC, east", datetime(2026, 10, 6, 23, 59, tzinfo=UTC), "Asia/Kolkata", date(2026, 10, 7)),
    ("00:01 UTC, east", datetime(2026, 10, 7, 0, 1, tzinfo=UTC), "Asia/Kolkata", date(2026, 10, 7)),
    ("23:59 UTC, in UTC", datetime(2026, 10, 6, 23, 59, tzinfo=UTC), "UTC", date(2026, 10, 6)),
    ("00:01 UTC, in UTC", datetime(2026, 10, 7, 0, 1, tzinfo=UTC), "UTC", date(2026, 10, 7)),
]


@pytest.fixture(params=SCENARIOS, ids=[s[0] for s in SCENARIOS])
def frozen(request):
    _, at, zone, day = request.param
    undo = clock.freeze(at, ZoneInfo(zone))
    yield at, ZoneInfo(zone), day
    undo()


def test_the_clock(frozen):
    at, _, day = frozen
    assert clock.today() == day and clock.utcnow() == at and clock.local_date(at) == day
    assert (
        clock.now().date() == day
        and clock.now().utcoffset() == clock.now().astimezone(clock.local_tz()).utcoffset()
    )
    assert clock.end_of_day_utc(day - timedelta(days=1)) <= at < clock.end_of_day_utc(day)
    assert clock.local_date(at.replace(tzinfo=None)) == day  # naive timestamps are UTC


def test_deadlines_count_local_days(frozen, ws):
    _, _, day = frozen
    svc = Service(ws)
    svc.add_deadline(title="File the I-129", due=day)
    svc.add_deadline(title="Letters back", due=day + timedelta(days=1))
    client = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    left = {d["title"]: d["days_left"] for d in client.get("/api/deadlines").json()}
    assert left == {"File the I-129": 0, "Letters back": 1}
    assert [i["days_left"] for i in alerts.due_items(ws, clock.today())][:2] == [0, 1]


def test_memory_as_of_today_includes_what_was_just_recorded(frozen, tmp_path):
    _, _, day = frozen
    mem = Memory(tmp_path, tmp_path / ".cache")
    [claim] = mem.record(
        evidence("hf", {"downloads": 7}, key="downloads", value=7, valid_from=date(2020, 1, 1))
    )
    assert claim.recorded_at == clock.utcnow()
    assert len(mem.query_claims(subject="artifact:x", predicate="downloads", as_of=clock.today())) == 1
    assert mem.query_claims(subject="artifact:x", predicate="downloads", as_of=day - timedelta(days=1)) == []


def test_agent_is_told_the_local_date(frozen, ws):
    _, _, day = frozen
    assert _render_turn("hi", [], ws, None).startswith(f"Today is {day.isoformat()}.")


def test_pipeline_staleness_counts_local_days(frozen, ws):
    at, zone, day = frozen
    item = Service(ws).add_pipeline_item(title="IEEE Senior Member", stage="applied")
    assert item.moved_at == at
    undo = clock.freeze(at + timedelta(days=14), zone)
    try:
        [view] = [p for p in pipeline_view(ws) if p["id"] == item.id]
        assert view["days_since_move"] == 14 and view["stale"] is True
    finally:
        undo()


@pytest.mark.parametrize(
    ("at", "month", "fy"),
    [
        (datetime(2026, 11, 1, 6, 59, tzinfo=UTC), "october", 2027),  # Oct 31, 23:59 in Los Angeles
        (
            datetime(2026, 10, 1, 6, 59, tzinfo=UTC),
            "september",
            2026,
        ),  # Sep 30, 23:59: still last fiscal year
        (datetime(2026, 10, 1, 7, 1, tzinfo=UTC), "october", 2027),  # Oct 1, 00:01
    ],
)
def test_visa_bulletin_month_and_fiscal_year_follow_the_local_day(at, month, fy):
    undo = clock.freeze(at, ZoneInfo("America/Los_Angeles"))
    try:
        values = _date_values()
        assert (values["month"], values["fy"]) == (month, fy)
    finally:
        undo()


def test_tz_environment_variable_sets_the_zone(monkeypatch):
    monkeypatch.setenv("TZ", "Asia/Kolkata")
    assert str(clock.local_tz()) == "Asia/Kolkata"
    monkeypatch.setenv("TZ", "America/Los_Angeles")
    assert str(clock.local_tz()) == "America/Los_Angeles"


def test_nothing_reads_the_date_around_the_clock():
    """Every "today" goes through areao1.core.clock (one place, the person's time zone)."""
    root = Path(__file__).resolve().parents[1] / "areao1"
    banned = re.compile(
        r"\bdate\.today\b|\bdatetime\.now\(|\bdatetime\.utcnow\(|\btime\.localtime\(|\.astimezone\(\)"
    )
    utc_day = re.compile(r"\.date\(\)")
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "clock.py":
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if banned.search(line) or (utc_day.search(line) and 'point["timestamp"]' not in line):
                offenders.append(f"{path.relative_to(root)}:{n}: {line.strip()}")
    assert offenders == []
