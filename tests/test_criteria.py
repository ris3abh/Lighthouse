from __future__ import annotations

from datetime import date

import pytest

from lighthouse_gc.core.models import Exhibit
from lighthouse_gc.criteria.engine import load_profiles, score
from lighthouse_gc.criteria.models import Profile


@pytest.fixture(scope="module")
def profiles() -> dict[str, Profile]:
    return load_profiles()


def ex(criterion: str, etype: str, signals=(), n: int = 0) -> Exhibit:
    return Exhibit(
        criterion=criterion,
        evidence_type=etype,
        title=f"{criterion} {n}",
        date=date(2026, 1, 1),
        file=f"evidence/{criterion}/{criterion}_2026-01-01_x{n}.md",
        signals=list(signals),
    )


def status(board, crit):
    return next(c for c in board.criteria if c.id == crit)


def test_shipped_profiles_load(profiles):
    assert {"o1a", "eb1a"} <= set(profiles)
    o1a, eb1a = profiles["o1a"], profiles["eb1a"]
    assert o1a.threshold == 3 and len(o1a.criteria) == 8
    assert eb1a.threshold == 3 and len(eb1a.criteria) == 10
    # Same criterion ids across profiles, so switching re-scores the same evidence.
    assert {c.id for c in o1a.criteria} <= {c.id for c in eb1a.criteria}
    assert all(c.regulation for p in (o1a, eb1a) for c in p.criteria)
    assert eb1a.narrative and eb1a.narrative[0].id == "final_merits"


def test_profile_accepts_plain_string_signals():
    p = Profile.model_validate(
        {
            "id": "x",
            "name": "X",
            "threshold": 1,
            "target": 1,
            "criteria": [
                {
                    "id": "scholarly_articles",
                    "label": "Articles",
                    "evidence_types": ["paper"],
                    "strength_signals": ["peer-reviewed", "citations > 0"],
                }
            ],
        }
    )
    assert [s.id for s in p.criteria[0].strength_signals] == ["peer_reviewed", "citations_0"]


def test_empty_is_all_gaps(profiles):
    board = score(profiles["o1a"], [])
    assert board.banked == 0 and board.building == 0
    assert {c.status for c in board.criteria} == {"gap"}


def test_banked_needs_exhibits_and_signals(profiles):
    o1a = profiles["o1a"]
    one = score(o1a, [ex("judging", "judge_invite", ["selective_event"])])
    assert status(one, "judging").status == "building"
    assert status(one, "judging").needed_exhibits == 1

    two = score(o1a, [ex("judging", "judge_invite", n=1), ex("judging", "reviewer_record", n=2)])
    j = status(two, "judging")
    # multiple_instances is derived automatically from two counted exhibits
    assert j.status == "banked" and j.matched_signals == ["multiple_instances"]


def test_signal_shortfall_keeps_building(profiles):
    board = score(profiles["o1a"], [ex("awards", "hackathon_win")])
    a = status(board, "awards")
    assert a.status == "building" and "strength signal" in a.reason


def test_off_type_exhibits_do_not_count(profiles):
    board = score(profiles["o1a"], [ex("scholarly_articles", "pay_stub", ["peer_reviewed"])])
    s = status(board, "scholarly_articles")
    assert s.status == "gap" and "evidence type" in s.reason


def test_overrides_win(profiles):
    exhibits = [ex("scholarly_articles", "paper", ["peer_reviewed"])]
    board = score(profiles["o1a"], exhibits, {"scholarly_articles": "dropped", "press": "gap"})
    s = status(board, "scholarly_articles")
    assert s.status == "dropped" and s.overridden and "banked" in s.reason
    assert board.banked == 0


def test_eb1a_is_stricter_on_same_evidence(profiles):
    exhibits = [
        ex("judging", "judge_invite", ["selective_event"], 1),
        ex("judging", "reviewer_record", [], 2),
        ex("scholarly_articles", "conference_paper", ["peer_reviewed", "major_venue"], 3),
    ]
    o1a = score(profiles["o1a"], exhibits)
    eb1a = score(profiles["eb1a"], exhibits)
    assert o1a.banked == 2
    assert eb1a.banked == 0
    assert status(eb1a, "judging").status == "building"


def test_threshold_counts(profiles):
    exhibits = [
        ex("judging", "judge_invite", ["selective_event"], 1),
        ex("judging", "panel_letter", [], 2),
        ex("scholarly_articles", "paper", ["peer_reviewed"], 3),
        ex("awards", "award_certificate", ["selective"], 4),
    ]
    board = score(profiles["o1a"], exhibits)
    assert board.banked == 3 >= board.threshold


def staged(criterion, etype, stage, signals=(), n=0):
    e = ex(criterion, etype, signals, n)
    e.stage = stage
    return e


def test_invitation_is_not_completion(profiles):
    board = score(profiles["o1a"], [staged("judging", "judge_invite", "invited", ["selective_event"], 1),
                                    staged("judging", "judge_invite", "invited", [], 2)])  # fmt: skip
    j = status(board, "judging")
    assert j.status == "building" and j.exhibit_count == 0 and j.in_progress_count == 2
    assert "not counted until completed" in j.reason and "invited" in j.reason


def test_completed_stages_count(profiles):
    board = score(profiles["o1a"], [staged("judging", "judge_invite", "completed", ["selective_event"], 1),
                                    staged("judging", "reviewer_record", None, [], 2),
                                    staged("judging", "judge_invite", "invited", [], 3)])  # fmt: skip
    j = status(board, "judging")
    assert j.status == "banked" and j.exhibit_count == 2 and j.in_progress_count == 1


def test_preprint_is_not_publication(profiles):
    board = score(profiles["o1a"], [staged("scholarly_articles", "preprint", "preprint", ["cited"])])
    assert status(board, "scholarly_articles").status == "building"
    board = score(
        profiles["o1a"], [staged("scholarly_articles", "conference_paper", "published", ["peer_reviewed"])]
    )
    assert status(board, "scholarly_articles").status == "banked"
