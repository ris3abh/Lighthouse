"""Drag-and-drop uploads: file -> memory snapshot -> Inbox candidate -> (accept) exhibit with the real bytes."""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient

from areao1.core.workspace import WorkspaceError
from areao1.criteria.classify import classify
from areao1.server.app import create_app

PDF = b"%PDF-1.4\n% fictional test document\n"
W = {"X-AreaO1": "1"}


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("HackMIT 2026 judge invitation.pdf", ("judging", "judge_invite", "invited")),
        ("hackmit-judging-confirmation.pdf", ("judging", "judge_invite", "completed")),
        ("NeurIPS_reviewer_assignments.pdf", ("judging", "reviewer_record", "completed")),
        ("Best Paper Award 2025.png", ("awards", "award_certificate", None)),
        ("IEEE membership certificate.pdf", ("membership", "membership_certificate", None)),
        ("TechCrunch interview.pdf", ("press", "press_article", None)),
        ("offer-letter-2026.pdf", ("high_salary", "pay_stub", None)),
        ("IMG_2048.jpg", ("", "document", None)),
    ],
)
def test_classify_guesses(ws, name, expected):
    assert classify(name, ws.profile()) == expected


def test_drop_creates_snapshot_and_candidate_not_exhibit(ws):
    cand = ws.stage_upload(PDF, "HackMIT 2026 judge invitation.pdf")
    assert ws.exhibits().exhibits == []  # nothing filed until the user accepts
    assert cand.kind == "evidence" and cand.source == "upload" and cand.source_tier == "user"
    assert (cand.proposed_criterion, cand.evidence_type, cand.stage) == ("judging", "judge_invite", "invited")
    obs = ws.memory.observation(cand.attachment)
    assert obs and obs.filename == "HackMIT 2026 judge invitation.pdf" and obs.tier == "user"
    assert (ws.root / obs.snapshot).read_bytes() == PDF
    assert ws.memory.verify() == []
    assert ws.pending_candidates() == [cand]


def test_same_file_twice_is_one_candidate(ws):
    a = ws.stage_upload(PDF, "a.pdf")
    b = ws.stage_upload(PDF, "renamed copy.pdf")
    assert a.id == b.id and len(ws.inbox().candidates) == 1


def test_accept_files_the_original_bytes(ws):
    cand = ws.stage_upload(PDF, "hackmit judging confirmation.pdf")
    exhibit = ws.accept_candidate(cand.id, date=date(2026, 3, 16))
    assert exhibit.file == "evidence/judging/judging_2026-03-16_hackmit-judging-confirmation.pdf"
    assert (ws.root / exhibit.file).read_bytes() == PDF
    assert exhibit.stage == "completed" and exhibit.source_tier == "user"
    assert ws.naming_check() == []
    assert next(c for c in ws.scoreboard().criteria if c.id == "judging").exhibit_count == 1
    with pytest.raises(WorkspaceError, match="already filed"):
        ws.stage_upload(PDF, "again.pdf")


def test_unsorted_upload_needs_a_criterion(ws):
    cand = ws.stage_upload(b"\x89PNG fake", "IMG_2048.png")
    assert cand.proposed_criterion == ""
    with pytest.raises(WorkspaceError, match="choose a criterion"):
        ws.accept_candidate(cand.id)
    exhibit = ws.accept_candidate(cand.id, proposed_criterion="awards", evidence_type="award_certificate")
    assert exhibit.file.startswith("evidence/awards/awards_") and exhibit.file.endswith(".png")


def test_drop_on_a_criterion_overrides_the_guess(ws):
    cand = ws.stage_upload(PDF, "judge invitation.pdf", criterion="press")
    assert cand.proposed_criterion == "press" and cand.stage is None
    with pytest.raises(WorkspaceError):
        ws.stage_upload(PDF + b"x", "a.pdf", criterion="vibes")


def test_upload_limits(ws):
    with pytest.raises(WorkspaceError, match="empty"):
        ws.stage_upload(b"", "a.pdf")
    with pytest.raises(WorkspaceError, match="25 MB"):
        ws.stage_upload(b"0" * (ws.MAX_UPLOAD_BYTES + 1), "big.pdf")


def test_tampered_upload_is_detected(ws):
    cand = ws.stage_upload(PDF, "a.pdf")
    path = ws.root / ws.memory.observation(cand.attachment).snapshot
    path.write_bytes(PDF + b"tampered")
    assert any("sha256" in p for p in ws.memory.verify())


def test_api_drop_preview_accept(demo_ws):
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    r = c.post(
        "/api/inbox/upload",
        files=[("files", ("MLH judging confirmation.pdf", PDF, "application/pdf")),
               ("files", ("notes.txt", b"plain notes", "text/plain"))],
        headers=W,
    )  # fmt: skip
    assert r.status_code == 200, r.text
    first, second = r.json()
    assert first["proposed_criterion"] == "judging" and second["proposed_criterion"] == ""
    preview = c.get(f"/api/attachments/{first['attachment']}")
    assert preview.status_code == 200 and preview.content == PDF
    assert preview.headers["content-security-policy"] == "sandbox"
    assert c.get("/api/attachments/obs_doesnotexist").status_code == 404
    accepted = c.post(f"/api/inbox/{first['id']}/accept", json={"date": "2026-10-01"}, headers=W)
    assert accepted.status_code == 200 and accepted.json()["file"].endswith(".pdf")
    assert c.post(f"/api/inbox/{second['id']}/accept", json={}, headers=W).status_code == 400


def test_api_drop_targets_a_criterion(demo_ws):
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    r = c.post("/api/inbox/upload", files=[("files", ("x.pdf", PDF, "application/pdf"))],
               data={"criterion": "membership"}, headers=W)  # fmt: skip
    assert r.json()[0]["proposed_criterion"] == "membership"
    assert (
        c.post("/api/inbox/upload", files=[("files", ("x.pdf", PDF, "application/pdf"))]).status_code == 403
    )
