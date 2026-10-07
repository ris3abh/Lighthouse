"""Claude / ChatGPT export import: conversations -> snapshots; the user's own words -> self-reported tracker
candidates that can organize work but can NEVER count toward a criterion."""

from __future__ import annotations

import io
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from lighthouse_gc.cli import app
from lighthouse_gc.core.models import Candidate, Exhibit
from lighthouse_gc.core.workspace import WorkspaceError
from lighthouse_gc.criteria.engine import score
from lighthouse_gc.jobs.chats import import_chats
from lighthouse_gc.mcp import tools
from lighthouse_gc.server.app import create_app
from lighthouse_gc.sources import chat_export as ce

CHATS = Path(__file__).parent / "fixtures" / "chats"
CLAUDE = (CHATS / "claude_conversations.json").read_bytes()
CHATGPT = (CHATS / "chatgpt_conversations.json").read_bytes()


def _zip(data: bytes, inner: str = "export/conversations.json") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(inner, data)
        zf.writestr("export/users.json", "[]")
    return buf.getvalue()


def _board(ws):
    return {(c.id, c.status, c.exhibit_count) for c in ws.recompute().criteria}


# ----------------------------------------------------------------------------- parsing


def test_parses_claude_export():
    provider, convs, sha = ce.load_export(CLAUDE)
    assert provider == "claude" and len(convs) == 3  # the empty conversation is skipped
    assert convs[0].title == "O-1 planning" and convs[0].url == "chat:claude:c0a1-planning"
    assert convs[0].messages[2].text.startswith("I asked Dr. Priya Natarajan")  # text from content[]
    assert len(sha) == 64


def test_parses_chatgpt_export_along_the_current_branch():
    provider, convs, _ = ce.load_export(CHATGPT)
    assert provider == "chatgpt" and len(convs) == 1
    texts = [m.text for m in convs[0].messages]
    assert not any("abandoned regeneration" in t for t in texts)  # off-branch node ignored
    assert [m.role for m in convs[0].messages] == ["user", "assistant", "user", "assistant"]
    assert convs[0].messages[0].at.date() == date(2026, 9, 15)


def test_zip_export_is_read_in_memory():
    provider, convs, _ = ce.load_export(_zip(CLAUDE), "data-2026-10-06.zip")
    assert provider == "claude" and len(convs) == 3


@pytest.mark.parametrize(
    "data",
    [b"not json", b'{"a": 1}', b'[{"something": "else"}]', _zip(b"[]", "export/other.json")],
    ids=["invalid-json", "not-a-list", "unknown-format", "zip-without-conversations"],
)
def test_rejects_non_exports(data):
    with pytest.raises(ce.ExportError):
        ce.load_export(data, "file.zip" if data[:2] == b"PK" else "file.json")


# ----------------------------------------------------------------------------- extraction


def test_extracts_only_the_users_own_words():
    _, convs, _ = ce.load_export(CLAUDE)
    items = [e for c in convs for e in ce.extract(c)]
    titles = {e.title for e in items}
    assert "Applied: IEEE Senior Member program" in titles
    assert "Invited: MLH Fall Hackathon" in titles
    assert "Done: HackMIT 2026" in titles
    assert "Letter writer: Dr. Priya Natarajan (asked)" in titles
    assert "Letter writer: Marcus Webb (drafting)" in titles
    deadlines = {e.proposal["due"]: e.proposal for e in items if e.kind == "deadline"}
    assert set(deadlines) == {"2026-10-14", "2026-11-01"}  # year inferred for "November 1"
    assert deadlines["2026-11-01"]["kind"] == "application"
    # The assistant said "I judged the ACM Hackathon", "ACM Distinguished Member by December 1" and gave an
    # I-129 date. None of that is the user's claim.
    joined = " ".join(e.sentence for e in items)
    assert "ACM" not in joined and "I-129" not in joined and "December" not in joined


def test_extractions_carry_stage_and_quote_their_sentence():
    _, convs, _ = ce.load_export(CLAUDE)
    by_title = {e.title: e for c in convs for e in ce.extract(c)}
    invited = by_title["Invited: MLH Fall Hackathon"]
    assert invited.stage == "invited" and invited.proposal["stage"] == "waiting"
    assert invited.claim.excerpt == "I was invited to judge the MLH Fall Hackathon."
    assert invited.claim.confidence == "low"
    done = by_title["Done: HackMIT 2026"]
    assert done.stage == "completed"  # self-reported completion is still only self-reported
    webb = by_title["Letter writer: Marcus Webb (drafting)"]
    assert webb.proposal["relationship"] == "employer"


def test_dates_and_year_inference():
    ref = date(2026, 12, 20)
    assert ce.find_date("due Jan 5", ref) == date(2027, 1, 5)
    assert ce.find_date("by 3rd of March 2027", ref) == date(2027, 3, 3)
    assert ce.find_date("closes 2027-02-01", ref) == date(2027, 2, 1)
    assert ce.find_date("by 2/14/2027", ref) == date(2027, 2, 14)
    assert ce.find_date("no date here", ref) is None


# ----------------------------------------------------------------------------- import job


def test_only_conversations_with_suggestions_are_saved(ws):
    report = import_chats(ws, CLAUDE, "conversations.json")
    assert report.provider == "claude" and report.conversations == 3
    assert report.snapshots_new == 2 and report.skipped == 1
    assert "1 without suggestions not saved" in report.line()
    obs = ws.memory.observations()
    transcripts = [o for o in obs if o.source_url.startswith("chat:claude:")]
    assert {o.source_url for o in transcripts} == {"chat:claude:c0a1-planning", "chat:claude:c0a2-letters"}
    # The poem conversation leaves no content anywhere in the workspace.
    for path in ws.root.rglob("*"):
        if path.is_file():
            assert b"Monongahela" not in path.read_bytes() and b"autumn leaves" not in path.read_bytes(), path
    [manifest] = [o for o in obs if o.source_url == "file:conversations.json"]
    payload = json.loads((ws.root / manifest.snapshot).read_text())
    assert payload["conversations"] == 3 and payload["snapshotted"] == ["c0a1-planning", "c0a2-letters"]
    assert {o.tier for o in obs} == {"self_reported"}
    assert all(o.media_type == "text/markdown" for o in transcripts)
    assert ws.memory.verify() == []  # every claim quotes its transcript verbatim
    assert report.candidates_added == {"deadline": 2, "letter": 2, "pipeline": 3}


def test_keep_all_saves_every_conversation(ws):
    report = import_chats(ws, CLAUDE, keep_all=True)
    assert report.snapshots_new == 3 and report.skipped == 0
    assert any(o.source_url == "chat:claude:c0a4-poem" for o in ws.memory.observations())


def test_cli_keep_all_flag(ws, tmp_path):
    export = tmp_path / "conversations.json"
    export.write_bytes(CLAUDE)
    result = CliRunner().invoke(app, ["import", str(export), "--keep-all", "-w", str(ws.root)])
    assert result.exit_code == 0, result.output
    assert "3 snapshotted" in result.output


def test_reimport_adds_nothing(ws):
    import_chats(ws, CLAUDE)
    files = sorted((ws.root / "memory").glob("*.jsonl"))
    lines = [p.read_text() for p in files]
    again = import_chats(ws, CLAUDE)  # same file again
    assert again.candidates_added == {} and again.snapshots_new == 0
    assert [p.read_text() for p in files] == lines  # nothing appended anywhere

    # The same export under another file name is a new source: only its manifest is recorded.
    renamed = import_chats(ws, _zip(CLAUDE), "export.zip")
    assert renamed.candidates_added == {} and renamed.snapshots_new == 0
    assert len(ws.inbox().candidates) == 7
    new_obs = ws.memory.observations()[-1]
    assert new_obs.source_url == "file:export.zip"
    assert [p.read_text() for p in files if p.name != "observations.jsonl"] == [
        line for p, line in zip(files, lines, strict=True) if p.name != "observations.jsonl"
    ]


def test_accepting_tracker_candidates_updates_trackers(ws):
    import_chats(ws, CLAUDE)
    import_chats(ws, CHATGPT)
    for cand in list(ws.pending_candidates()):
        ws.accept_candidate(cand.id)
    deadlines = {d.due.isoformat(): d for d in ws.deadlines().deadlines}
    assert set(deadlines) == {"2026-10-14", "2026-11-01", "2026-10-20"}
    stages = {p.title: p.stage for p in ws.pipeline().items}
    assert stages["Invited: MLH Fall Hackathon"] == "waiting" and stages["Done: HackMIT 2026"] == "done"
    letters = {lt.name: lt for lt in ws.letters().letters}
    assert letters["Lena Okafor"].status == "declined" and letters["Marcus Webb"].relationship == "employer"
    assert set(ws.memory.statuses().values()) == {"approved"}
    assert ws.pending_candidates() == []


def test_edited_tracker_proposal_is_validated(ws):
    import_chats(ws, CLAUDE)
    dl = next(c for c in ws.pending_candidates() if c.kind == "deadline")
    ws.edit_candidate(dl.id, proposal={**dl.proposal, "due": "not-a-date"})
    with pytest.raises(WorkspaceError, match="invalid deadline"):
        ws.accept_candidate(dl.id)


# ----------------------------------------------------------------------------- the rule


def test_self_reported_items_can_never_count_toward_a_criterion(demo_ws):
    """Import both exports into the demo, accept every self-reported candidate: the scoreboard must not move,
    no exhibit may appear, and no route (forged evidence candidate, edits, a hand-edited exhibit) may count."""
    before_board, before_exhibits = _board(demo_ws), demo_ws.exhibits().model_dump()
    import_chats(demo_ws, CLAUDE)
    import_chats(demo_ws, CHATGPT)
    chat_cands = [c for c in demo_ws.pending_candidates() if c.source_tier == "self_reported"]
    assert chat_cands and {c.kind for c in chat_cands} <= {"deadline", "pipeline", "letter"}
    for cand in chat_cands:
        demo_ws.accept_candidate(cand.id)
    assert _board(demo_ws) == before_board
    assert demo_ws.exhibits().model_dump() == before_exhibits
    # Even the self-reported "I judged HackMIT" (stage completed) only became a pipeline entry.
    assert any(p.title == "Done: HackMIT 2026" for p in demo_ws.pipeline().items)

    # A forged evidence candidate with a self-reported tier cannot be accepted as an exhibit...
    forged = Candidate(kind="evidence", fingerprint="forged", source="chat:claude", evidence_type="panel_letter",
                       proposed_criterion="judging", title="I judged everything", summary="trust me",
                       stage="completed", signals=["selective_event"], source_tier="self_reported")  # fmt: skip
    demo_ws.add_candidates([forged])
    with pytest.raises(WorkspaceError, match="self-reported"):
        demo_ws.accept_candidate(forged.id)
    # ...and its kind / tier can't be edited away.
    for field in ("kind", "source_tier"):
        with pytest.raises(WorkspaceError, match="not editable"):
            demo_ws.edit_candidate(forged.id, **{field: "evidence" if field == "kind" else "user"})
    assert _board(demo_ws) == before_board


def test_engine_ignores_self_reported_exhibits_however_they_got_there(ws):
    """Defense in depth: a hand-edited exhibits.json entry marked self_reported never counts."""
    judging = [
        Exhibit(criterion="judging", evidence_type="panel_letter", title=f"j{i}", date=date(2026, 1, i),
                file=f"evidence/judging/judging_2026-01-0{i}_j{i}.md", stage="completed",
                signals=["selective_event", "documented_scoring"], source_tier="self_reported")
        for i in (1, 2, 3)
    ]  # fmt: skip
    for profile in ("o1a", "eb1a"):
        row = next(c for c in score(ws.profile(profile), judging).criteria if c.id == "judging")
        assert row.status == "gap" and row.exhibit_count == 0
        assert "self-reported" in row.reason


def test_trackers_never_show_up_as_evidence_gaps(demo_ws):
    import_chats(demo_ws, CLAUDE)
    pending = [p for g in tools.list_gaps(demo_ws)["gaps"] for p in g["pending_in_inbox"]]
    chat_ids = {c.id for c in demo_ws.pending_candidates() if c.source_tier == "self_reported"}
    assert not chat_ids & {p["id"] for p in pending}


# ----------------------------------------------------------------------------- entry points


def test_cli_import_detects_an_export_file(ws, tmp_path):
    export = tmp_path / "conversations.json"
    export.write_bytes(CHATGPT)
    result = CliRunner().invoke(app, ["import", str(export), "-w", str(ws.root)])
    assert result.exit_code == 0, result.output
    assert "chatgpt: 1 conversation read" in result.output and "never counts" in result.output
    bad = tmp_path / "notes.json"
    bad.write_text(json.dumps({"x": 1}))
    assert CliRunner().invoke(app, ["import", str(bad), "-w", str(ws.root)]).exit_code == 1


def test_api_import(demo_ws):
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    r = c.post("/api/imports/chats", files={"file": ("claude-export.zip", _zip(CLAUDE), "application/zip")},
               headers={"X-Lighthouse": "1"})  # fmt: skip
    assert r.status_code == 200, r.text
    assert (
        r.json()["conversations"] == 3 and r.json()["skipped"] == 1 and "never counts" in r.json()["summary"]
    )
    tracker = next(x for x in c.get("/api/inbox").json() if x["kind"] == "deadline")
    accepted = c.post(f"/api/inbox/{tracker['id']}/accept", json={}, headers={"X-Lighthouse": "1"})
    assert accepted.status_code == 200 and accepted.json()["due"] in ("2026-10-14", "2026-11-01")
    bad = c.post("/api/imports/chats", files={"file": ("x.json", b"[]", "application/json")},
                 headers={"X-Lighthouse": "1"})  # fmt: skip
    assert bad.status_code == 400
