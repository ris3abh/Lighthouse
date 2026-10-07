from __future__ import annotations

import json
from datetime import date

import pytest

from lighthouse_gc.core.models import Candidate, MetricRow
from lighthouse_gc.core.workspace import NotFound, WorkspaceError
from lighthouse_gc.scaffold import create_workspace, validate_workspace


def cand(fp="github:x/y:original_contributions", **kw) -> Candidate:
    base = dict(
        fingerprint=fp,
        source="github:x",
        evidence_type="open_source_project",
        proposed_criterion="original_contributions",
        title="Open-source project: x/y",
        summary="x/y — 500 stars",
        signals=["widely_adopted"],
        raw_url="https://github.com/x/y",
        facts={"stars": 500},
    )
    return Candidate(**{**base, **kw})


def test_init_creates_template(tmp_path):
    ws = create_workspace(tmp_path / "case", name="Test Person", profile="eb1a", git=True)
    root = ws.root
    for rel in (
        "lighthouse.yaml",
        "DASHBOARD.md",
        "AGENTS.md",
        ".gitignore",
        "data/metrics.csv",
        "data/criteria.json",
        "data/person.json",
        ".lighthouse/schemas/exhibits.schema.json",
        ".claude/skills",
        "drafts/letters",
        "evidence/judging",
        "evidence/display",
    ):
        assert (root / rel).exists(), rel
    gitignore = (root / ".gitignore").read_text()
    assert ".lighthouse/cache/" in gitignore and "*.db" in gitignore and ".env" in gitignore
    assert json.loads((root / "data/person.json").read_text())["name"] == "Test Person"
    assert ws.config().profile == "eb1a"
    assert (root / "data/metrics.csv").read_text() == "date,source,item,metric,value\n"
    hook = root / ".git/hooks/pre-commit"
    assert hook.exists() and "gitleaks" in hook.read_text() and hook.stat().st_mode & 0o111
    assert validate_workspace(ws) == []


def test_init_refuses_non_empty_dir(tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "x" / "file.txt").write_text("hi")
    with pytest.raises(WorkspaceError):
        create_workspace(tmp_path / "x", git=False)


def test_init_rejects_unknown_profile(tmp_path):
    with pytest.raises(WorkspaceError):
        create_workspace(tmp_path / "y", profile="h1b", git=False)


def test_add_candidates_dedupes(ws):
    assert len(ws.add_candidates([cand(), cand()])) == 1
    assert ws.add_candidates([cand()]) == []
    assert len(ws.pending_candidates()) == 1


def test_accept_creates_exhibit_file_and_rescores(ws):
    c = ws.add_candidates([cand()])[0]
    exhibit = ws.accept_candidate(c.id, date=date(2026, 10, 6))
    assert (
        exhibit.file
        == "evidence/original_contributions/original_contributions_2026-10-06_open-source-project-x-y.md"
    )
    body = (ws.root / exhibit.file).read_text()
    assert "https://github.com/x/y" in body and "| stars | 500 |" in body
    assert [e.id for e in ws.exhibits().exhibits] == [exhibit.id]
    assert ws.inbox().candidates == []
    row = next(c for c in ws.scoreboard().criteria if c.id == "original_contributions")
    assert row.status == "building" and row.exhibit_count == 1
    assert "1 building" in (ws.root / "DASHBOARD.md").read_text()
    # accepted fingerprints never come back
    assert ws.add_candidates([cand()]) == []
    assert ws.naming_check() == []


def test_accept_with_edits(ws):
    c = ws.add_candidates([cand()])[0]
    exhibit = ws.accept_candidate(
        c.id,
        proposed_criterion="judging",
        evidence_type="judge_invite",
        title="Judge at HackX",
        date=date(2026, 1, 2),
    )
    assert exhibit.criterion == "judging"
    assert exhibit.file.startswith("evidence/judging/judging_2026-01-02_judge-at-hackx")


def test_accept_rejects_unknown_criterion(ws):
    c = ws.add_candidates([cand()])[0]
    with pytest.raises(WorkspaceError):
        ws.accept_candidate(c.id, proposed_criterion="vibes")


def test_reject_is_remembered(ws):
    c = ws.add_candidates([cand()])[0]
    ws.reject_candidate(c.id)
    assert ws.pending_candidates() == []
    assert ws.add_candidates([cand()]) == []


def test_snooze_hides_until_date(ws):
    c = ws.add_candidates([cand()])[0]
    ws.snooze_candidate(c.id, date(2026, 10, 20))
    assert ws.pending_candidates(date(2026, 10, 10)) == []
    assert len(ws.pending_candidates(date(2026, 10, 20))) == 1


def test_edit_candidate(ws):
    c = ws.add_candidates([cand()])[0]
    ws.edit_candidate(c.id, summary="better summary")
    assert ws.inbox().candidates[0].summary == "better summary"
    with pytest.raises(WorkspaceError):
        ws.edit_candidate(c.id, status="pending")
    with pytest.raises(NotFound):
        ws.edit_candidate("cand_nope", summary="x")


def test_upload_and_remap(ws):
    exhibit = ws.add_exhibit_file(
        content=b"%PDF-1.4 fake",
        filename="Invite.PDF",
        criterion="judging",
        evidence_type="judge_invite",
        title="HackX judge invite",
        on=date(2026, 3, 1),
        signals=["selective_event"],
    )
    assert exhibit.file == "evidence/judging/judging_2026-03-01_hackx-judge-invite.pdf"
    assert (ws.root / exhibit.file).read_bytes() == b"%PDF-1.4 fake"
    moved = ws.remap_exhibit(exhibit.id, "press", "press_article")
    assert moved.file == "evidence/press/press_2026-03-01_hackx-judge-invite.pdf"
    assert (ws.root / moved.file).exists() and not (ws.root / exhibit.file).exists()
    assert ws.naming_check() == []


def test_upload_name_collision_gets_suffix(ws):
    kw = dict(
        content=b"x",
        filename="a.txt",
        criterion="awards",
        evidence_type="award_notice",
        title="Same",
        on=date(2026, 1, 1),
    )
    a, b = ws.add_exhibit_file(**kw), ws.add_exhibit_file(**kw)
    assert a.file != b.file and b.file.endswith("same-2.txt")


def test_naming_check_flags_problems(ws):
    (ws.evidence_dir / "awards" / "My Award.pdf").write_bytes(b"x")
    (ws.evidence_dir / "awards" / "awards_2026-01-01_ok.pdf").write_bytes(b"x")
    problems = {(i["file"], i["problem"]) for i in ws.naming_check()}
    assert ("evidence/awards/My Award.pdf", "bad_name") in problems
    assert ("evidence/awards/awards_2026-01-01_ok.pdf", "unlogged") in problems


def test_resolve_inside_blocks_traversal(ws):
    with pytest.raises(WorkspaceError):
        ws.resolve_inside("../../etc/passwd")


def test_metrics_upsert(ws):
    d = date(2026, 10, 6)
    rows = [MetricRow(date=d, source="github", item="x/y", metric="stars", value=10)]
    assert ws.append_metrics(rows) == 1
    assert ws.append_metrics(rows) == 0  # same value, same day: no duplicate
    assert ws.append_metrics([MetricRow(date=d, source="github", item="x/y", metric="stars", value=11)]) == 1
    assert (
        ws.append_metrics(
            [MetricRow(date=date(2026, 10, 7), source="github", item="x/y", metric="stars", value=12)]
        )
        == 1
    )
    assert [(r.date.day, r.value) for r in ws.metrics()] == [(6, 11), (7, 12)]
    assert ws.metrics_path.read_text().splitlines()[1] == "2026-10-06,github,x/y,stars,11"


def test_profile_switch_rescores_without_recollecting(demo_ws):
    before = demo_ws.exhibits().model_dump()
    o1a = demo_ws.scoreboard()
    eb1a = demo_ws.set_profile("eb1a")
    assert o1a.profile == "o1a" and eb1a.profile == "eb1a"
    assert eb1a.banked < o1a.banked
    assert demo_ws.exhibits().model_dump() == before
    assert demo_ws.config().profile == "eb1a"


def test_override_roundtrip(ws):
    ws.set_override("press", "dropped")
    assert ws.config().overrides == {"o1a": {"press": "dropped"}}
    assert next(c for c in ws.scoreboard().criteria if c.id == "press").status == "dropped"
    ws.set_override("press", None)
    assert ws.config().overrides == {}
    with pytest.raises(NotFound):
        ws.set_override("display", "gap")  # display is EB-1A only
