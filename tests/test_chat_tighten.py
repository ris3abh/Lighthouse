"""Chat-import tightening (F10): a note is proposed only when it names a person, a date or deadline, or a case item;
near-identical items are merged (within an import and against the Inbox); notes are low priority. Deadlines,
pipeline ideas and letter writers always come through. Everything here is invented."""

from __future__ import annotations

from areao1.core.models import Candidate
from areao1.sources import chat_extract as cx


def _note(i: int, text: str, topic: str = "decision") -> Candidate:
    return Candidate(kind="context", fingerprint=f"chatx:context:{i}", source="chat:chatgpt", evidence_type="self_report",
                     proposed_criterion="", source_tier="self_reported", confidence=0.2,
                     title=f"{topic.capitalize()}: {text[:60]}", summary=f'"{text}"',
                     proposal={"id": str(i), "text": text, "client": "ChatGPT export", "topic": topic})  # fmt: skip


def test_a_note_needs_a_person_a_date_a_deadline_or_a_case_item(ws):
    ws.add_contact(name="Dr. Omar Haddad", emails=["omar@example.org"], relationship="organizer")
    names = cx.names_in(ws)
    keep = ["I agreed to judge the spring hackathon finals.", "Reviews for the systems workshop are due Friday.",
            "Haddad said he can introduce me to the chairs.", "Call the lab on March 3 about the dataset.",
            "Decided to write the letter draft myself first."]  # fmt: skip
    drop = ["I prefer dark roast coffee in the morning.", "Decided to refactor the parser to use a state machine.",
            "Switched my editor theme to something calmer."]  # fmt: skip
    for text in keep:
        assert cx.worth_noting(_note(1, text), names), text
    for text in drop:
        assert not cx.worth_noting(_note(1, text), names), text
    assert cx.worth_noting(
        _note(1, "Sam is great at Rust", topic="person"), names
    )  # a person is always worth it


def test_trackers_always_come_through_and_near_duplicates_merge(ws):
    deadline = Candidate(kind="deadline", fingerprint="chatx:deadline:1", source="chat:chatgpt", evidence_type="self_report",
                         proposed_criterion="", title="Reviews due", summary="s", proposal={"title": "Reviews due", "due": "2026-12-01"})  # fmt: skip
    a = _note(1, "I agreed to judge the spring hackathon finals in Seattle.")
    b = _note(2, "I agreed to judge the spring hackathon finals in Seattle!")  # the same, again
    c = _note(3, "My cat knocked my coffee over.")
    ws.add_candidates([_note(9, "Reviews for the systems workshop are due Friday.")])  # already in the Inbox
    d = _note(4, "Reviews for the systems workshop are due Friday")
    kept, counts = cx.tighten(ws, [deadline, a, b, c, d])
    assert [x.fingerprint for x in kept] == ["chatx:deadline:1", "chatx:context:1"]
    assert counts == {"left_out": 1, "merged": 2}


def test_notes_are_low_priority_from_the_extractor():
    from types import SimpleNamespace

    from areao1.core.models import Evidence

    source = SimpleNamespace(url="chatgpt://c/1", title="Planning", messages=[])
    snap = Evidence(connector="chatgpt_export", source_url="chatgpt://c/1", payload="I decided to judge the finals.",
                    media_type="text/markdown", tier="self_reported")  # fmt: skip
    [cand] = cx.candidates(source, [{"type": "decision", "title": "Judge the finals", "quote": "I decided to judge the finals."}],
                           snap, "ChatGPT")  # fmt: skip
    assert cand.kind == "context" and cand.confidence == 0.2
    assert "names a person, a date or" in cx.SYSTEM  # the model is asked for the same
