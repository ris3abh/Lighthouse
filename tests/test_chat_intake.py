"""Chat-history import that works with real exports (C14): any drop (a .zip, several .json files, a folder),
manifests followed, Claude and ChatGPT adapters, unknown files named; a local relevance filter with readable
reasons; a picker where unticked items leave nothing behind; extraction on picked items only, every item quoting
the person's own sentence. Fixtures are synthetic; no real model or network."""

from __future__ import annotations

import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient

from lighthouse_gc.scaffold import create_workspace
from lighthouse_gc.server.app import create_app
from lighthouse_gc.sources import chat_intake, chat_relevance
from lighthouse_gc.sources.chat_export import ExportError

W = {"X-Lighthouse": "1"}


def claude_conv(uid, name, user_texts, when="2026-08-01T10:00:00Z"):
    msgs = []
    for i, t in enumerate(user_texts):
        msgs += [{"sender": "human", "text": t, "created_at": when},
                 {"sender": "assistant", "text": f"(assistant reply {i}) You should definitely apply.", "created_at": when}]  # fmt: skip
    return {"uuid": uid, "name": name, "created_at": when, "chat_messages": msgs}


def chatgpt_conv(cid, title, user_text, ts=1754000000):
    return {"conversation_id": cid, "title": title, "create_time": ts, "current_node": "b",
            "mapping": {"a": {"message": {"author": {"role": "user"}, "content": {"parts": [user_text]}, "create_time": ts}, "parent": None},
                        "b": {"message": {"author": {"role": "assistant"}, "content": {"parts": ["Noted."]}, "create_time": ts + 5}, "parent": "a"}}}  # fmt: skip


CASE = claude_conv("c-case", "O-1A plan", [
    "My lawyer says the O-1A petition needs stronger judging evidence.",
    "I judged HackSeattle 2025 and Dr. Priya Natarajan offered to write my recommendation letter.",
    "The NeurIPS reviewer sign-up deadline is 2026-10-20, remind me before then.",
])  # fmt: skip
RECIPE = claude_conv("c-food", "Weeknight dal", ["How long should I soak lentils for dal?"])
FOLLOWUP = claude_conv(
    "c-letter", "Letter drafts", ["Dr. Priya Natarajan wants a draft of the letter by Friday."]
)
PROJECT = {"uuid": "p-1", "name": "Green card", "prompt_template": "Help me organize evidence for EB-1A.",
           "docs": [{"filename": "awards.md", "content": "Northwind Engineering Excellence Award 2024."}], "created_at": "2026-07-01T00:00:00Z"}  # fmt: skip


def zipped(files: dict[str, object]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, value in files.items():
            zf.writestr(name, value if isinstance(value, (bytes, str)) else json.dumps(value))
    return buf.getvalue()


def _drop(files: dict[str, object]) -> list[tuple[str, bytes]]:
    return [
        (n, v if isinstance(v, bytes) else (v.encode() if isinstance(v, str) else json.dumps(v).encode()))
        for n, v in files.items()
    ]


# ----------------------------------------------------------------------------- intake


def test_a_claude_export_zip_with_projects_reads_and_skips_the_rest():
    data = zipped({"conversations.json": [CASE, RECIPE], "projects.json": [PROJECT], "users.json": [{"uuid": "u"}],
                   "attachments/photo.png": b"\x89PNG..."})  # fmt: skip
    intake = chat_intake.read([("data-2026-10-01.zip", data)])
    assert [c.title for c in intake.conversations] == ["O-1A plan", "Weeknight dal"]
    assert [p.name for p in intake.projects] == ["Green card"]
    assert "Claude conversations" in intake.formats and "Claude Projects" in intake.formats
    assert sorted(intake.skipped) == ["attachments/photo.png", "users.json"] and intake.unread == []


def test_several_files_and_both_providers_in_one_drop():
    intake = chat_intake.read(_drop({"claude/2026-08-01.json": CASE, "claude/2026-08-02.json": RECIPE,
                                     "chatgpt/conversations.json": [chatgpt_conv("g1", "Hackathon judging", "I judged HackSeattle 2025.")]}))  # fmt: skip
    assert {c.provider for c in intake.conversations} == {"claude", "chatgpt"} and len(
        intake.conversations
    ) == 3


def test_a_manifest_is_followed_to_its_dated_files():
    files = {"export/manifest.json": {"version": 2, "conversations": ["conversations/2026-08-02.json", "conversations/2026-08-01.json"]},
             "export/conversations/2026-08-01.json": CASE, "export/conversations/2026-08-02.json": FOLLOWUP,
             "export/conversations/2026-07-30.json": RECIPE}  # not in the manifest: still read  # fmt: skip
    intake = chat_intake.read(_drop(files))
    assert "followed manifest.json to 2 files" in intake.formats
    assert {c.id for c in intake.conversations} == {"c-case", "c-letter", "c-food"}


def test_a_newer_dated_file_wins_for_the_same_conversation():
    older = claude_conv("c-case", "O-1A plan", ["first draft"])
    intake = chat_intake.read(_drop({"a/2026-01-01.json": older, "a/2026-09-01.json": CASE}))
    [conv] = intake.conversations
    assert len(conv.messages) == 6


def test_unknown_files_are_named_never_dropped_silently():
    intake = chat_intake.read(
        _drop({"conversations.json": [CASE], "notes/odd.json": {"hello": "world"}, "broken.json": "{"})
    )
    assert dict(intake.unread) == {
        "notes/odd.json": "not a Claude or ChatGPT format I know",
        "broken.json": "not valid JSON",
    }
    with pytest.raises(ExportError, match="notes/odd.json: not a Claude or ChatGPT format I know"):
        chat_intake.read(_drop({"notes/odd.json": {"hello": "world"}}))


def _zip(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for n, b in entries.items():
            zf.writestr(n, b)
    return buf.getvalue()


@pytest.mark.parametrize(
    ("drop", "says"),
    [
        # the owner's run: a drop that yielded no readable file said "Files I couldn't read: nothing"
        ([("export.zip", _zip({"__MACOSX/._conversations.json": b"x", ".DS_Store": b"x"}))],
         ["export.zip/.DS_Store: a hidden or Mac metadata file"]),
        ([("manifest.json", json.dumps({"files": ["chats/2026-08-01.json", "chats/2026-08-02.json"]}).encode())],
         ["manifest.json: it lists 2 files and 2 of them weren't in what you dropped"]),
        ([("users.json", b"[]")], ["users.json: not a chat file"]),
        ([("empty.zip", _zip({}))], ["empty.zip: the .zip is empty"]),
    ],
)  # fmt: skip
def test_a_drop_with_no_chats_says_what_arrived_and_what_happened_to_each(drop, says):
    with pytest.raises(ExportError) as err:
        chat_intake.read(drop)
    msg = str(err.value)
    assert "nothing" not in msg
    assert f"({len(drop)} file" in msg and drop[0][0] in msg
    for s in says:
        assert s in msg


# ----------------------------------------------------------------------------- relevance (local, no model)


def test_case_chats_and_projects_rank_first_with_plain_reasons():
    intake = chat_intake.read(
        _drop({"conversations.json": [RECIPE, CASE, FOLLOWUP], "projects.json": [PROJECT]})
    )
    fields = {
        "employer": "Northwind Cloud",
        "judging": ["Judge, HackSeattle 2025"],
        "awards": ["Northwind Engineering Excellence Award 2024"],
    }
    matches = {m.title: m for m in chat_relevance.score(intake, ["Maya Chen"], fields)}
    case, food, project = matches["O-1A plan"], matches["Weeknight dal"], matches["Green card"]
    assert project.score > case.score > food.score and project.reasons[0].startswith("a Claude Project")
    assert any(r.startswith("mentions ") and "O-1A" in r for r in case.reasons)
    assert any(r.startswith("criteria words: ") and "judging" in r for r in case.reasons)
    assert "names from your profile: HackSeattle" in case.reasons
    assert "people you mention in other chats: Priya Natarajan" in case.reasons
    assert "1 dated deadline" in case.reasons
    assert case.ticked and project.ticked and not food.ticked and food.reasons == []


# ----------------------------------------------------------------------------- the picker and import


@pytest.fixture
def ws(tmp_path):
    return create_workspace(tmp_path / "case", name="Maya Chen", git=False)


def _scan(c, files):
    r = c.post(
        "/api/imports/chats/scan",
        headers=W,
        files=[("files", (n, d, "application/octet-stream")) for n, d in files],
    )
    assert r.status_code == 200, r.text
    return r.json()


def _everything(ws) -> str:
    return "".join(
        p.read_text(errors="ignore") for p in ws.root.rglob("*") if p.is_file() and ".git" not in p.parts
    )


def test_scanning_writes_nothing_and_unticked_items_leave_nothing(ws):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    before = _everything(ws)
    scan = _scan(
        c, [("export.zip", zipped({"conversations.json": [CASE, RECIPE], "projects.json": [PROJECT]}))]
    )
    assert _everything(ws) == before  # the scan is memory only
    items = {i["title"]: i for i in scan["items"]}
    assert (
        items["O-1A plan"]["ticked"]
        and not items["Weeknight dal"]["ticked"]
        and items["O-1A plan"]["reasons"]
    )
    out = c.post(
        f"/api/imports/chats/{scan['id']}/import", headers=W, json={"ids": [items["O-1A plan"]["id"]]}
    ).json()
    assert out["picked"] == 1 and out["extracted_by"] == "rules"
    text = _everything(ws)
    assert "soak lentils" not in text and "Weeknight dal" not in text  # unticked: nothing at all
    assert "Help me organize evidence for EB-1A" not in text  # the unticked project too
    assert "stronger judging evidence" in text  # the ticked chat is snapshotted
    pending = ws.pending_candidates()
    assert pending and all(c_.source_tier == "self_reported" for c_ in pending)
    assert (
        c.post(f"/api/imports/chats/{scan['id']}/import", headers=W, json={"ids": []}).status_code == 404
    )  # used up


def test_extraction_reads_only_picked_items_and_keeps_exact_quotes(ws):
    from agent_fakes import FakeEngine

    reply = json.dumps({"items": [
        {"type": "person", "title": "Priya Natarajan", "name": "Dr. Priya Natarajan", "relationship": "recommender",
         "quote": "I judged HackSeattle 2025 and Dr. Priya Natarajan offered to write my recommendation letter."},
        {"type": "deadline", "title": "NeurIPS reviewer sign-up", "due": "2026-10-20",
         "quote": "The NeurIPS reviewer sign-up deadline is 2026-10-20, remind me before then."},
        {"type": "decision", "title": "Paraphrased", "quote": "I decided to file in March."},  # not in the text: dropped
        {"type": "opportunity", "title": "You should definitely apply", "quote": "You should definitely apply."},  # the AI's words: dropped
    ]})  # fmt: skip
    engine = FakeEngine([("text", reply)])
    c = TestClient(create_app(ws, allowed_hosts=["testserver"], engine=engine))
    scan = _scan(c, [("conversations.json", json.dumps([CASE, RECIPE]).encode())])
    case_id = next(i["id"] for i in scan["items"] if i["title"] == "O-1A plan")
    out = c.post(f"/api/imports/chats/{scan['id']}/import", headers=W, json={"ids": [case_id]}).json()
    assert out["extracted_by"] == ws.config().agent.models.mundane and "Read by" in out["summary"]
    assert (
        len(engine.requests) == 1 and "soak lentils" not in engine.requests[0].prompt
    )  # only the picked chat
    assert "(assistant reply" not in engine.requests[0].prompt  # only the person's own words go to the model
    titles = {c_.title: c_ for c_ in ws.pending_candidates() if c_.fingerprint.startswith("chatx:")}
    assert set(titles) == {"Person: Dr. Priya Natarajan (recommender)", "NeurIPS reviewer sign-up"}
    person = titles["Person: Dr. Priya Natarajan (recommender)"]
    assert (
        person.kind == "context"
        and person.raw_url == "chat:claude:c-case"
        and person.source_tier == "self_reported"
    )
    assert "offered to write my recommendation letter" in person.summary
    assert titles["NeurIPS reviewer sign-up"].proposal["due"] == "2026-10-20"
    runs = [r for r in TestClient(create_app(ws, allowed_hosts=["testserver"])).get("/api/agent/runs").json()
            if "Chat-history extraction" in r["prompt"]]  # fmt: skip
    assert runs  # the model's cost shows on the Agent page


def test_imported_chat_items_never_count_toward_a_criterion(ws):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    scan = _scan(c, [("conversations.json", json.dumps([CASE]).encode())])
    c.post(f"/api/imports/chats/{scan['id']}/import", headers=W, json={"ids": [scan["items"][0]["id"]]})
    board = ws.scoreboard()
    assert board.banked == 0 and board.building == 0 and ws.exhibits().exhibits == []


def test_an_unknown_drop_says_which_files_it_couldnt_read(ws):
    c = TestClient(create_app(ws, allowed_hosts=["testserver"]))
    r = c.post(
        "/api/imports/chats/scan",
        headers=W,
        files=[("files", ("notes.json", b'{"a": 1}', "application/json"))],
    )
    assert r.status_code == 400 and "notes.json" in r.json()["detail"]


def test_letters_and_case_paperwork_count_and_acronyms_read_naturally():
    letters = claude_conv(
        "c-l",
        "Letters",
        ["Omar Haddad agreed to be a letter writer; I need two more recommendation letters."],
    )
    lawyer = claude_conv(
        "c-v", "Call", ["My lawyer filed the I-129 and USCIS sent an RFE about the o1a criteria."]
    )
    intake = chat_intake.read(_drop({"conversations.json": [letters, lawyer]}))
    m = {x.title: x for x in chat_relevance.score(intake, ["Maya Chen"], {})}
    assert m["Letters"].ticked and any(r.startswith("about your case: ") for r in m["Letters"].reasons)
    assert (
        "mentions I-129, O-1A, RFE, USCIS" in m["Call"].reasons
    )  # the first four, acronyms as written officially
    assert not any("critical role" in r for r in m["Call"].reasons)  # "filed the" isn't "led the"
