"""I2: the chat-import adapter hook. A new export layout is one registered adapter (the owner's dated-file Claude
export waits for a redacted sample); unknown files say how to get one added. Everything here is invented."""

from __future__ import annotations

import json

import pytest

from areao1.sources import chat_intake
from areao1.sources.chat_export import Conversation, ExportError, Message


@pytest.fixture(autouse=True)
def clean_registry(monkeypatch):
    monkeypatch.setattr(chat_intake, "ADAPTERS", [])


DATED = {"conversation_uuid": "c-1", "title": "O-1A plan", "turns": [
    {"speaker": "human", "text": "I judged Example Hacks on 2026-03-02."},
    {"speaker": "assistant", "text": "Noted."}]}  # fmt: skip


def _parse(item):
    return Conversation(provider="claude", id=item["conversation_uuid"], title=item["title"], created=None,
                        messages=[Message("user" if t["speaker"] == "human" else "assistant", t["text"], None)
                                  for t in item["turns"]])  # fmt: skip


def test_an_unknown_layout_is_named_with_how_to_add_it():
    with pytest.raises(ExportError) as err:
        chat_intake.read([("2026-03-02/c-1.json", json.dumps(DATED).encode())])
    assert "redacted sample" in str(err.value) or "docs/chat-import.md" in str(err.value)


def test_a_registered_adapter_reads_a_new_layout_before_the_built_in_ones():
    chat_intake.register_adapter(chat_intake.Adapter("claude_dated", "Claude conversations (dated files)",
                                                     lambda i: isinstance(i, dict) and "turns" in i, _parse))  # fmt: skip
    intake = chat_intake.read([("2026-03-02/c-1.json", json.dumps(DATED).encode())])
    [conv] = intake.conversations
    assert conv.title == "O-1A plan" and conv.messages[0].text.startswith("I judged")
    assert "Claude conversations (dated files)" in intake.formats
    chat_intake.register_adapter(chat_intake.Adapter("claude_dated", "again", lambda i: False, _parse))
    assert [a.label for a in chat_intake.ADAPTERS] == ["again"]  # registering by name replaces


def test_the_docs_explain_the_hook():
    from pathlib import Path

    doc = (Path(__file__).parents[1] / "docs" / "manual" / "connectors" / "chat-imports.md").read_text()
    assert "register_adapter" in doc and "redacted sample" in doc
