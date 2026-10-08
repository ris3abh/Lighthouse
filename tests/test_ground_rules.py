"""The ground rules (SPEC §2a), each with a guard. Features that draft, score or export add their own case here
(proof recipes, preflight, final merits and the review packet, ADRs 0017-0020). Everything here is invented."""

from __future__ import annotations

import re
import subprocess
from datetime import date
from pathlib import Path

from fastapi.testclient import TestClient

from areao1.agent.guardrails import guard_answer
from areao1.core.models import ClaimDraft, Evidence
from areao1.criteria import grounding, letters
from areao1.server.app import create_app

ROOT = Path(__file__).resolve().parents[1]
W = {"X-AreaO1": "1"}

# §2a.1: wording that would show, compute or export a chance of approval.
PROBABILITY = re.compile(
    r"(?:chances?|probabilit\w*|likelihood|odds) (?:of|for) (?:approval|success|being approved)"
    r"|(?:approval|success) (?:probabilit\w*|odds|likelihood|chances?|score)|likely to be approved"
    r"|\b(?:approval|success)_?(?:probability|likelihood|odds|score)\b",
    re.I,
)
# Files allowed to name the forbidden thing: the rules themselves, their guards and the guardrail patterns.
RULE_FILES = {
    "SPEC.md",
    "tests/test_ground_rules.py",
    "areao1/agent/guardrails.py",
    "TODO.md",
    "CHANGELOG.md",
}


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [
        f for f in out.splitlines() if f.endswith((".py", ".ts", ".tsx", ".md", ".html", ".yaml", ".json"))
    ]


def test_no_approval_probability_anywhere():
    hits = []
    for f in _tracked():
        if f in RULE_FILES or f.startswith(("docs/adr/", "tests/fixtures/")):
            continue
        path = ROOT / f
        if not path.is_file():
            continue
        text = path.read_text(errors="ignore")
        hits += [f"{f}: {m.group(0)}" for m in PROBABILITY.finditer(text)]
    assert not hits, hits


def test_the_agent_never_gives_a_probability():
    for said in ("Based on this, you have a 70% chance of approval.",
                 "Your approval odds look strong.",
                 "With three criteria banked you are likely to be approved.",
                 "I'd put the probability of approval at about 60%."):  # fmt: skip
        out, hits = guard_answer(said)
        assert hits and "chance" not in out.lower() and "%" not in out, said
    assert guard_answer("You have a chance to judge Example Hacks in May.")[1] == []  # not about approval


def test_generated_sentences_are_grounded_or_dropped():
    text = ("Dear Officer,\n\nMaya judged Example Hacks. [clm_aaaaaaaaaaaa] Maya led 40 engineers. "
            "Maya is widely admired. [clm_ffffffffffff] Maya clearly qualifies. [clm_aaaaaaaaaaaa] "
            "Her approval odds are high. [clm_aaaaaaaaaaaa]\n\n[WRITER: your own words]\n\nSincerely,")  # fmt: skip
    kept, cited, dropped = grounding.keep_grounded(text, {"clm_aaaaaaaaaaaa"})
    assert "Maya judged Example Hacks." in kept and cited == ["clm_aaaaaaaaaaaa"]
    for gone in (
        "40 engineers",
        "widely admired",
        "qualifies",
        "odds",
    ):  # uncited, unapproved, verdict, probability
        assert gone not in kept, gone
    assert "[WRITER: your own words]" in kept and len(dropped) == 4
    assert letters.keep_grounded is grounding.keep_grounded  # one filter for every draft


def test_letter_drafts_are_labeled_for_attorney_review(ws):
    payload = "Judged Example Hacks round 1 in 2026."
    (claim,) = ws.memory.record(Evidence(connector="upload", source_url="upload:j.txt", payload=payload,
                                         media_type="text/plain",
                                         claims=[ClaimDraft(subject="event:x", subject_kind="event", subject_name="Example Hacks",
                                                            predicate="judged_event", value="round 1", excerpt=payload,
                                                            event_date=date(2026, 1, 1))]))  # fmt: skip
    ws.memory.decide([claim.id], "approved", rationale="ok")
    lt = ws.add_letter(name="Dr. Example Writer", relationship="independent", criteria=["judging"])
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        client.post(f"/api/letters/{lt.id}/draft", headers=W)
        text = client.get(f"/api/letters/{lt.id}/draft").json()["text"]
        ws.add_contact(name="Dr. Example Writer", emails=["writer@example.edu"], relationship="recommender")
        body = client.post(f"/api/letters/{lt.id}/send", headers=W, json={}).json()["body"]
    assert grounding.LABEL == "Draft for attorney review"
    assert text.count(grounding.LABEL) >= 2 and grounding.LABEL in body


def test_self_reported_material_never_counts(ws):
    for tier in ("self_reported", None):
        ws.add_exhibit_file(content=b"%PDF-1.4 x", filename="a.pdf", criterion="awards", evidence_type="award_certificate",
                            title=f"Award {tier}", on=date(2026, 1, 1), signals=["national_or_international"])  # fmt: skip
    board = ws.recompute()
    assert (
        next(c for c in board.criteria if c.id == "awards").exhibit_count == 2
    )  # neither is self-reported yet
    ex = ws.exhibits()
    ex.exhibits[0].source_tier = "self_reported"
    ws.save_exhibits(ex)
    assert next(c for c in ws.recompute().criteria if c.id == "awards").exhibit_count == 1


def test_self_reported_material_never_satisfies_a_proof_item(ws):
    from areao1.criteria import proof
    from areao1.service import Service

    done = ws.add_exhibit_file(content=b"%PDF-1.4 x", filename="a.pdf", criterion="judging", evidence_type="panel_letter",
                               title="Judged Example Hacks", on=date(2026, 1, 1), stage="completed")  # fmt: skip
    note = ws.add_exhibit_file(content=b"%PDF-1.4 y", filename="b.pdf", criterion="judging", evidence_type="panel_letter",
                               title="My own note", on=date(2026, 1, 2))  # fmt: skip
    ex = ws.exhibits()
    next(e for e in ex.exhibits if e.id == note.id).source_tier = "self_reported"
    ws.save_exhibits(ex)
    Service(ws).link_proof(f"exhibit:{done.id}", "event_page", note.id)
    [c] = proof.checklists(ws)
    assert next(i for i in c["items"] if i["id"] == "event_page")["status"] == "self_reported"
