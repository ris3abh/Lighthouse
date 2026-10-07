"""Gmail (E2, ADR 0014 §2): only threads with your contacts, headers only, one redacted line each; last touch
follows the newest thread; nothing without the Gmail permission. Google is mocked."""

from __future__ import annotations

import json
import time
from datetime import date

import pytest

from areao1.core.secrets import set_secret
from areao1.criteria import contacts
from areao1.google import auth, gmail


def _connect(scopes=("gmail_read",)):
    set_secret(
        auth.CLIENT_REF, json.dumps({"client_id": "x.apps.googleusercontent.com", "client_secret": "s"})
    )
    set_secret(auth.TOKEN_REF, json.dumps({"refresh_token": "r", "access_token": "ya29.t", "expires_at": time.time() + 600,
                                           "scope": " ".join(auth.SCOPES[s] for s in scopes), "email": "alex@example.com"}))  # fmt: skip


def _msg(frm, to, at, subject="Re: HackSeattle judging", snippet="Thanks for judging!"):
    return {"internalDate": str(at), "snippet": snippet,
            "payload": {"headers": [{"name": "From", "value": frm}, {"name": "To", "value": to},
                                    {"name": "Subject", "value": subject}]}}  # fmt: skip


@pytest.fixture
def people(ws):
    a = ws.add_contact(
        name="Omar Haddad", emails=["omar@mlh.example"], relationship="organizer", last_touch=date(2026, 9, 1)
    )
    b = ws.add_contact(
        name="Dr. Priya Natarajan", emails=["priya@lakeshore.example"], relationship="recommender"
    )
    ws.add_contact(name="No email yet")
    return a, b


def test_only_threads_with_contacts_headers_only_redacted(ws, people, http_mock):
    omar, priya = people
    _connect()
    lists = http_mock.get(f"{gmail.API}/threads").respond(
        json={"threads": [{"id": "t1"}, {"id": "t2"}, {"id": "t3"}]}
    )
    oct3, oct5 = 1759500000000, 1759680000000
    http_mock.get(f"{gmail.API}/threads/t1").respond(json={"id": "t1", "messages": [
        _msg("Alex <alex@example.com>", "Omar <omar@mlh.example>", oct3),
        _msg("Omar Haddad <omar@mlh.example>", "alex@example.com", oct5, snippet="Call me at 206-555-0100 or omar.h@gmail.com"),
    ]})  # fmt: skip
    http_mock.get(f"{gmail.API}/threads/t2").respond(json={"id": "t2", "messages": [
        _msg("alex@example.com", "priya@lakeshore.example, someone@else.example", oct3, subject="Letter draft")]})  # fmt: skip
    http_mock.get(f"{gmail.API}/threads/t3").respond(
        json={
            "id": "t3",
            "messages": [_msg("newsletter@shop.example", "alex@example.com", oct5, subject="Sale")],
        }
    )  # a match Google made, no contact on it
    lines = gmail.sync(ws)
    assert "2 threads" in lines[0]
    queries = sorted(c.request.url.params["q"] for c in lists.calls)
    assert queries == [
        f"(from:{e} OR to:{e} OR cc:{e}) newer_than:365d"
        for e in ("omar@mlh.example", "priya@lakeshore.example")
    ]
    for call in http_mock.calls:
        if "/threads/" in str(call.request.url):
            assert call.request.url.params["format"] == "metadata"  # never bodies or attachments
    stored = {t.id: t for t in ws.threads().threads}
    assert set(stored) == {"t1", "t2"}
    t1 = stored["t1"]
    assert t1.contact_ids == [omar.id] and t1.last_from == "them" and t1.messages == 2
    assert "206-555-0100" not in t1.snippet and "omar.h@gmail.com" not in t1.snippet
    assert stored["t2"].last_from == "you" and stored["t2"].contact_ids == [priya.id]
    raw = (ws.root / "data" / "threads.json").read_text()
    assert "body" not in raw and "Sale" not in raw


def test_last_touch_never_goes_back(ws, people, http_mock):
    omar, priya = people
    _connect()
    http_mock.get(f"{gmail.API}/threads").respond(json={"threads": [{"id": "t1"}]})
    http_mock.get(f"{gmail.API}/threads/t1").respond(
        json={"id": "t1", "messages": [_msg("omar@mlh.example", "alex@example.com", 1756000000000)]}
    )  # 2025-08-24: older than the stored touch
    gmail.sync(ws)
    assert next(c for c in ws.contacts().contacts if c.id == omar.id).last_touch == date(2026, 9, 1)


def test_nothing_happens_without_the_gmail_permission(ws, people, http_mock):
    _connect(scopes=("calendar",))
    route = http_mock.get(f"{gmail.API}/threads").respond(json={"threads": []})
    assert "isn't connected" in gmail.sync(ws)[0] and not route.called
    assert ws.threads().threads == []


def test_contacts_show_their_threads(ws, people, http_mock):
    omar, _ = people
    _connect()
    http_mock.get(f"{gmail.API}/threads").respond(json={"threads": [{"id": "t1"}]})
    http_mock.get(f"{gmail.API}/threads/t1").respond(
        json={"id": "t1", "messages": [_msg("omar@mlh.example", "alex@example.com", 1791000000000)]}
    )  # 2026-10-03
    gmail.sync(ws)
    view = next(v for v in contacts.views(ws) if v["id"] == omar.id)
    assert view["threads"][0]["subject"] == "Re: HackSeattle judging"
    assert next(c for c in ws.contacts().contacts if c.id == omar.id).last_touch == date(2026, 10, 3)
    assert ws.changes()[-1].actor == "gmail" and ws.changes()[-1].action == "contact.update"
