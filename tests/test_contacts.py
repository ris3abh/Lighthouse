"""Contacts (E4, ADR 0014 §4): stored contacts plus every letter writer not yet linked to one; editing a letter
writer's entry makes it a stored contact; changes go through the service layer and can be undone; a contact never
counts toward a criterion."""

from __future__ import annotations

from fastapi.testclient import TestClient

from areao1.server.app import create_app
from areao1.service import Service

W = {"X-AreaO1": "1"}


def _client(ws):
    return TestClient(create_app(ws, allowed_hosts=["testserver"]))


def test_letter_writers_show_up_as_contacts_until_you_add_them(demo_ws):
    c = _client(demo_ws)
    letters = demo_ws.letters().letters
    views = c.get("/api/contacts").json()
    virtual = {v["letter_ids"][0]: v for v in views if v["virtual"]}
    assert set(virtual) == {lt.id for lt in letters}
    first = letters[0]
    v = virtual[first.id]
    assert (
        v["id"] == f"letter:{first.id}"
        and v["relationship"] == "recommender"
        and v["letters"][0]["status"] == first.status
    )
    # adding an email makes it a stored contact, linked to the letter; the virtual entry goes away
    out = c.patch(
        f"/api/contacts/letter:{first.id}", headers=W, json={"emails": ["Priya@Lakeshore.example"]}
    ).json()
    assert (
        out["name"] == first.name
        and out["letter_ids"] == [first.id]
        and out["emails"] == ["priya@lakeshore.example"]
    )
    views = c.get("/api/contacts").json()
    assert not [x for x in views if x["virtual"] and x["letter_ids"] == [first.id]]
    assert [x for x in views if not x["virtual"] and x["name"] == first.name][0]["letters"][0][
        "id"
    ] == first.id


def test_contacts_are_added_changed_and_undone_through_the_service(demo_ws):
    c = _client(demo_ws)
    pipe = demo_ws.pipeline().items[0]
    added = c.post("/api/contacts", headers=W, json={"name": "Omar Haddad", "emails": ["omar@mlh.example"],
                                                    "relationship": "organizer", "pipeline_ids": [pipe.id],
                                                    "next_follow_up": "2026-10-20"}).json()  # fmt: skip
    assert added["tier"] == "self_reported"
    [view] = [v for v in c.get("/api/contacts").json() if v["id"] == added["id"]]
    assert view["pipeline"][0]["title"] == pipe.title
    c.patch(f"/api/contacts/{added['id']}", headers=W, json={"asks": ["Confirm my judging in writing"]})
    change = demo_ws.changes()[-1]
    assert change.action == "contact.update" and change.actor == "user"
    Service(demo_ws).undo(change.id)
    assert next(x for x in demo_ws.contacts().contacts if x.id == added["id"]).asks == []
    assert c.delete(f"/api/contacts/{added['id']}", headers=W).status_code == 200
    assert not [x for x in demo_ws.contacts().contacts if x.id == added["id"]]


def test_bad_emails_are_refused(demo_ws):
    r = _client(demo_ws).post("/api/contacts", headers=W, json={"name": "X", "emails": ["not an email"]})
    assert r.status_code >= 400


def test_a_contact_never_counts_toward_a_criterion(demo_ws):
    before = {(x.id, x.status, x.exhibit_count) for x in demo_ws.recompute().criteria}
    c = _client(demo_ws)
    for rel in ("recommender", "organizer", "editor"):
        c.post(
            "/api/contacts",
            headers=W,
            json={"name": f"Someone {rel}", "relationship": rel, "notes": "judged with me"},
        )
    assert {(x.id, x.status, x.exhibit_count) for x in demo_ws.recompute().criteria} == before
