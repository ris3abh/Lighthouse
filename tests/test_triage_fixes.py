"""QA fixes (F4) that live on the server: letter writers merge into the contact they already are (B6), and one
source's unexpected error never fails the whole vault check (B14). Browser-side fixes (B1, B5, B7, B8, B20) are in
tests/e2e/test_flows.py. Everything here is invented."""

from __future__ import annotations

import anyio
from fastapi.testclient import TestClient

from areao1.criteria import contacts
from areao1.server.app import create_app
from areao1.vault.store import Vault

W = {"X-AreaO1": "1"}


def test_a_letter_writer_who_is_a_contact_shows_once(ws):
    ws.add_contact(
        name="Priya Natarajan, PhD", emails=["priya@university.example"], relationship="recommender"
    )
    lt = ws.add_letter(name="Dr. Priya Natarajan", relationship="independent", criteria=["judging"])
    other = ws.add_letter(name="Prof. Omar Haddad", relationship="independent")
    views = contacts.views(ws)
    priya = [v for v in views if contacts.person_key(v["name"]) == "priya natarajan"]
    assert len(priya) == 1 and not priya[0]["virtual"] and [x["id"] for x in priya[0]["letters"]] == [lt.id]
    assert any(
        v["virtual"] and v["letter_ids"] == [other.id] for v in views
    )  # not a contact yet: still listed
    assert contacts.person_key("Dr. Priya  Natarajan") == contacts.person_key("priya natarajan, PhD")
    assert contacts.person_key("Priya Nataraj") != contacts.person_key("Priya Natarajan")


def test_send_to_the_writer_finds_the_merged_contact(ws):
    from datetime import date

    from areao1.core.models import ClaimDraft, Evidence

    payload = "Judged Example Hacks round 1 in 2026."
    [c] = ws.memory.record(Evidence(connector="upload", source_url="upload:j.txt", payload=payload, media_type="text/plain",
                                    claims=[ClaimDraft(subject="event:x", subject_kind="event", subject_name="Example Hacks",
                                                       predicate="judged_event", value="round 1", excerpt=payload,
                                                       event_date=date(2026, 1, 1))]))  # fmt: skip
    ws.memory.decide([c.id], "approved", rationale="ok")
    ws.add_contact(name="Priya Natarajan", emails=["priya@university.example"], relationship="recommender")
    lt = ws.add_letter(name="Dr. Priya Natarajan", relationship="independent", criteria=["judging"])
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        client.post(f"/api/letters/{lt.id}/draft", headers=W)
        d = client.post(f"/api/letters/{lt.id}/send", headers=W, json={}).json()
    assert d["to"] == "priya@university.example"  # "Dr." on one side and not the other is the same person


def test_one_sources_unexpected_error_doesnt_fail_the_whole_check(ws, monkeypatch):
    vault = Vault(ws)
    ids = [s.id for s in vault.manifest.sources if s.enabled][:3]
    calls: list[str] = []

    async def fetch(self, source, client, cache, prev):  # type: ignore[no-untyped-def]
        calls.append(source.id)
        if source.id == ids[1]:
            raise OSError("something nobody planned for")
        return self._failed(source, source.url, "unreadable", "blocked (test)", prev)

    monkeypatch.setattr(Vault, "_fetch", fetch)
    results = anyio.run(lambda: vault.sync(ids, force=True))
    by = {r.source_id: r for r in results}
    assert set(by) == set(ids) and sorted(calls) == sorted(ids)
    assert by[ids[1]].status == "error" and "OSError: something nobody planned for" in by[ids[1]].error
    assert by[ids[0]].status == by[ids[2]].status == "unreadable"
