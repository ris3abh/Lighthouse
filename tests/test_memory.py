"""Evidence-aware graph memory (SPEC 5b): observations, exact-quote claims, review, provenance, time."""

from __future__ import annotations

from datetime import date

import pytest
from conftest import mock_github, mock_hf

from areao1.core.memory import Memory, MemoryError
from areao1.core.models import ClaimDraft, Evidence, json_excerpt
from areao1.jobs import sync as jobs


def _import(ws, http_mock, url="https://github.com/arivera-demo"):
    mock_github(http_mock)
    mock_hf(http_mock)
    return jobs.import_source(ws, url, sleep=lambda s: None)


def evidence(connector: str, payload: dict, **claim) -> Evidence:
    key, value = claim.pop("key"), claim.pop("value")
    return Evidence(
        connector=connector,
        source_url=f"https://{connector}.example/api",
        payload=payload,
        claims=[
            ClaimDraft(
                subject="artifact:x",
                subject_name="x",
                predicate=claim.pop("predicate", "downloads"),
                value=value,
                excerpt=json_excerpt(key, value),
                **claim,
            )
        ],
    )


def test_import_writes_observations_and_quoted_claims(ws, http_mock):
    _import(ws, http_mock)
    mem = ws.memory
    observations, claims = mem.observations(), mem.claims()
    assert observations and claims
    for obs in observations:
        assert (ws.root / obs.snapshot).exists()
        assert obs.snapshot.startswith("memory/sources/")
    stars = next(
        c for c in claims if c.subject == "artifact:github:arivera-demo/fastgrad" and c.predicate == "stars"
    )
    assert stars.value == 1840
    assert stars.excerpt == '"stargazers_count": 1840'
    obs = next(o for o in observations if o.id == stars.observation_id)
    assert mem.snapshot_text(obs)[stars.excerpt_start : stars.excerpt_end] == stars.excerpt
    assert stars.extracted_by.kind == "connector" and stars.extracted_by.name == "github"
    assert stars.confidence == "high"
    edges = {(e.type, e.src) for e in mem.edges()}
    assert ("DERIVED_FROM", stars.id) in edges and ("ABOUT", stars.id) in edges
    assert mem.verify() == []


def test_candidates_point_at_their_claims(ws, http_mock):
    _import(ws, http_mock)
    claims = {c.id: c for c in ws.memory.claims()}
    for cand in ws.pending_candidates():
        assert cand.claim_ids, cand.title
        assert all(cid in claims for cid in cand.claim_ids)
    paper = next(c for c in ws.pending_candidates() if c.proposed_criterion == "scholarly_articles")
    assert paper.stage == "preprint"
    link = claims[paper.claim_ids[0]]
    assert link.predicate == "links_paper" and link.excerpt == "arxiv.org/abs/2502.01234v2"
    assert link.confidence == "medium"


def test_reimport_appends_nothing_new(ws, http_mock):
    _import(ws, http_mock)
    before = [p.read_text() for p in sorted((ws.root / "memory").glob("*.jsonl"))]
    jobs.import_source(ws, "https://github.com/arivera-demo", sleep=lambda s: None)
    after = [p.read_text() for p in sorted((ws.root / "memory").glob("*.jsonl"))]
    assert before == after


def test_changed_value_supersedes_and_keeps_history(tmp_path):
    mem = Memory(tmp_path, tmp_path / ".cache")
    [old] = mem.record(evidence("huggingface", {"downloads": 100}, key="downloads", value=100,
                                valid_from=date(2026, 9, 1)))  # fmt: skip
    [new] = mem.record(evidence("huggingface", {"downloads": 128}, key="downloads", value=128,
                                valid_from=date(2026, 10, 6)))  # fmt: skip
    assert new.version == 2
    assert any(e.type == "SUPERSEDES" and e.src == new.id and e.dst == old.id for e in mem.edges())
    assert [c.value for c in mem.claims()] == [100, 128]  # nothing overwritten

    current = mem.query_claims(subject="artifact:x", predicate="downloads")
    assert [c.value for c, _ in current] == [128]
    # Knowledge time: on Sept 15 Area O1 hadn't recorded anything yet.
    assert mem.query_claims(subject="artifact:x", predicate="downloads", as_of=date(2026, 9, 15)) == []


def test_as_of_respects_valid_time(tmp_path):
    mem = Memory(tmp_path, tmp_path / ".cache")
    today = date.today()
    mem.record(evidence("hf", {"downloads": 100}, key="downloads", value=100, valid_from=date(2020, 1, 1)))
    mem.record(evidence("hf", {"downloads": 128}, key="downloads", value=128, valid_from=date(2099, 1, 1)))
    [(claim, _)] = mem.query_claims(subject="artifact:x", predicate="downloads", as_of=today)
    assert claim.value == 100  # the newer claim isn't valid in the world until 2099


def test_review_states(ws, http_mock):
    _import(ws, http_mock)
    project = next(c for c in ws.pending_candidates() if c.title.endswith("fastgrad"))
    tinyserve = next(c for c in ws.pending_candidates() if c.title.endswith("tinyserve"))
    exhibit = ws.accept_candidate(project.id)
    ws.reject_candidate(tinyserve.id)
    status = ws.memory.statuses()
    assert {status[c] for c in project.claim_ids} == {"approved"}
    assert {status[c] for c in tinyserve.claim_ids} == {"rejected"}
    assert exhibit.claim_ids == project.claim_ids
    cites = {(e.src, e.dst) for e in ws.memory.edges() if e.type == "CITES"}
    assert all((exhibit.id, c) in cites for c in project.claim_ids)
    decisions = ws.memory.decisions()
    assert {d.decision for d in decisions} == {"approved", "rejected"}
    approved = ws.memory.query_claims(status="approved")
    assert {c.id for c, _ in approved} >= set(project.claim_ids)


def test_two_independent_sources_corroborate(tmp_path):
    mem = Memory(tmp_path, tmp_path / ".cache")
    mem.record(evidence("huggingface", {"downloads": 128}, key="downloads", value=128))
    mem.record(evidence("papers_with_code", {"n": 1, "downloads": 128}, key="downloads", value=128))
    assert set(mem.statuses().values()) == {"corroborated"}
    assert not any(e.type == "SUPERSEDES" for e in mem.edges())


def test_excerpt_must_be_verbatim(tmp_path):
    mem = Memory(tmp_path, tmp_path / ".cache")
    bad = evidence("huggingface", {"downloads": 128}, key="downloads", value=999)
    with pytest.raises(MemoryError, match="excerpt not found"):
        mem.record(bad)
    assert mem.claims() == []


def test_verify_detects_tampered_snapshot(ws, http_mock):
    _import(ws, http_mock)
    obs = ws.memory.observations()[0]
    path = ws.root / obs.snapshot
    path.write_text(path.read_text().replace("1", "2"))
    problems = ws.memory.verify()
    assert any("sha256" in p for p in problems)


def test_index_is_rebuildable(ws, http_mock):
    _import(ws, http_mock)
    first = ws.memory.query_claims(predicate="stars")
    ws.memory.index_path.unlink()
    assert ws.memory.query_claims(predicate="stars") == first
    assert ws.memory.index_path.exists()
    assert ws.memory.index_path.is_relative_to(ws.root / ".areao1" / "cache")  # gitignored


def test_metrics_snapshot_records_metric_claims(ws, http_mock):
    mock_github(http_mock, authed=True)
    jobs.import_source(ws, "github:arivera-demo", token="tok", snapshot=True, sleep=lambda s: None)
    predicates = {c.predicate for c in ws.memory.claims()}
    assert {"stars", "forks", "views_14d", "clones_14d"} <= predicates
    assert ws.memory.verify() == []


def test_same_text_at_two_urls_keeps_both_sources(tmp_path):
    from areao1.core.models import Evidence

    mem = Memory(tmp_path, tmp_path / ".cache")
    a = mem.snapshot(
        Evidence(
            connector="agent", source_url="https://a.example/", payload="same text", media_type="text/plain"
        )
    )
    b = mem.snapshot(
        Evidence(
            connector="agent", source_url="https://b.example/", payload="same text", media_type="text/plain"
        )
    )
    again = mem.snapshot(
        Evidence(
            connector="agent", source_url="https://a.example/", payload="same text", media_type="text/plain"
        )
    )
    assert a.id != b.id and again.id == a.id
    assert (a.source_url, b.source_url) == ("https://a.example/", "https://b.example/")
    assert a.snapshot == b.snapshot  # one file on disk
    assert mem.verify() == []


def test_as_of_uses_the_local_day_not_the_utc_day(tmp_path, monkeypatch):
    """recorded_at is UTC; "as of <date>" means that date where the person is."""
    import os
    import time as _time
    from datetime import timedelta

    mem = Memory(tmp_path, tmp_path / ".cache")
    [claim] = mem.record(
        evidence("hf", {"downloads": 7}, key="downloads", value=7, valid_from=date(2020, 1, 1))
    )
    utc = claim.recorded_at
    # A zone where the local date differs from the UTC date at this moment.
    zone, shift = ("Etc/GMT+12", -12) if utc.hour < 12 else ("Etc/GMT-12", 12)
    local_day = (utc + timedelta(hours=shift)).date()
    monkeypatch.setenv("TZ", zone)
    _time.tzset()
    try:
        [(found, _)] = mem.query_claims(subject="artifact:x", predicate="downloads", as_of=local_day)
        assert found.value == 7
        assert (
            mem.query_claims(subject="artifact:x", predicate="downloads", as_of=local_day - timedelta(days=1))
            == []
        )
    finally:
        os.environ.pop("TZ", None)
        _time.tzset()
