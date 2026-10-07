"""Gmail threads with case contacts (E2, ADR 0014 §2 and its amendment): subjects are redacted, last touch only
moves forward through the service layer, and contacts show their threads. Gmail is the fake in mail_fakes.py."""

from __future__ import annotations

from datetime import date

import pytest
from mail_fakes import FakeGmail

from areao1.criteria import contacts
from areao1.google import gmail, mail


@pytest.fixture
def fake(monkeypatch):
    g = FakeGmail().install(monkeypatch)
    mail.connect(g.email, g.password)
    return g


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


def test_subjects_are_redacted(ws, people, fake):
    fake.add(1, "03-Oct-2026 09:00:00 +0000", "omar@mlh.example", "alex@gmail.com",
             "Call me at 206-555-0100 about judging")  # fmt: skip
    gmail.sync(ws)
    [t] = ws.threads().threads
    assert "206-555-0100" not in t.subject and "judging" in t.subject


def test_last_touch_never_goes_back(ws, people, fake):
    omar, _ = people
    fake.add(
        1, "24-Aug-2025 09:00:00 +0000", "omar@mlh.example", "alex@gmail.com", "Old"
    )  # before the stored touch
    gmail.sync(ws)
    assert next(c for c in ws.contacts().contacts if c.id == omar.id).last_touch == date(2026, 9, 1)


def test_nothing_happens_without_gmail(ws, people):
    assert "isn't connected" in gmail.sync(ws)[0]  # the conftest guard fails any real IMAP connection
    assert ws.threads().threads == []


def test_contacts_show_their_threads(ws, people, fake):
    omar, _ = people
    fake.add(1, "03-Oct-2026 09:00:00 +0000", "omar@mlh.example", "alex@gmail.com", "Re: HackSeattle judging")
    gmail.sync(ws)
    view = next(v for v in contacts.views(ws) if v["id"] == omar.id)
    assert view["threads"][0]["subject"] == "Re: HackSeattle judging"
    assert next(c for c in ws.contacts().contacts if c.id == omar.id).last_touch == date(2026, 10, 3)
    assert ws.changes()[-1].actor == "gmail" and ws.changes()[-1].action == "contact.update"
