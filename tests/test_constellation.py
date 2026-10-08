"""The constellation memory map's data (ADR 0012): every claim a star in its criterion's cluster, with status,
confidence, conflict, superseded and date, and the provenance trail behind it."""

from __future__ import annotations

import time
from datetime import date, timedelta

from fastapi.testclient import TestClient

from areao1.core.models import ClaimDraft, Edge, Evidence
from areao1.criteria import constellation
from areao1.server.app import create_app


def test_every_claim_is_a_star_with_what_the_sky_needs(demo_ws):
    out = constellation.stars(demo_ws)
    claims = demo_ws.memory.claims()
    assert len(out["stars"]) == len(claims) > 0
    ids = {c["id"] for c in out["clusters"]}
    assert {c.id for c in demo_ws.profile().criteria} <= ids
    s = out["stars"][0]
    assert set(s) >= {
        "id",
        "criterion",
        "entity_name",
        "date",
        "confidence",
        "status",
        "conflict",
        "source",
        "exhibits",
    }
    assert all(x["criterion"] in ids for x in out["stars"])
    assert all(x["status"] in ("approved", "pending", "superseded", "rejected") for x in out["stars"])
    assert [x["date"] for x in out["stars"]] == sorted(
        x["date"] for x in out["stars"]
    )  # date order for the replay


def _record(ws, n=3, predicate="judged_event", conf="high"):
    payload = "\n".join(f"Fact number {i}: judged Example Hacks round {i}." for i in range(n))
    drafts = [ClaimDraft(subject=f"event:example-hacks-{i}", subject_kind="event", subject_name=f"Example Hacks {i}",
                         predicate=predicate, value=i, excerpt=f"Fact number {i}: judged Example Hacks round {i}.",
                         event_date=date(2026, 1, 1) + timedelta(days=i), confidence=conf) for i in range(n)]  # fmt: skip
    return ws.memory.record(Evidence(connector="upload", source_url="upload:judging.txt", payload=payload,
                                     media_type="text/plain", claims=drafts))  # fmt: skip


def test_status_conflict_superseded_criterion_and_confidence(ws):
    a, b, c = _record(ws)
    ws.memory.decide([a.id], "approved", rationale="ok")
    ws.memory._append("edges", [Edge(type="SUPERSEDES", src=c.id, dst=b.id),
                                      Edge(type="CONTRADICTS", src=a.id, dst=c.id)])  # fmt: skip
    by = {s["id"]: s for s in constellation.stars(ws)["stars"]}
    assert (
        by[a.id]["status"] == "approved"
        and by[b.id]["status"] == "superseded"
        and by[c.id]["status"] == "pending"
    )
    assert by[a.id]["conflict"] and by[c.id]["conflict"] and not by[b.id]["conflict"]
    assert by[a.id]["criterion"] == "judging"  # from the predicate when nothing cites it
    assert by[a.id]["confidence"] == 1.0 and by[a.id]["date"] == "2026-01-01"


def test_an_exhibit_citing_a_claim_decides_its_cluster(ws):
    [claim] = _record(ws, 1, predicate="mentioned_in")
    ex = ws.add_exhibit_file(content=b"%PDF-1.4 x", filename="a.pdf", criterion="awards", evidence_type="award_notice",
                             title="Example Prize 2026", on=date(2026, 3, 1))  # fmt: skip
    ws.memory.cite(ex.id, [claim.id])
    [s] = constellation.stars(ws)["stars"]
    assert s["criterion"] == "awards" and s["exhibits"] == [ex.id]


def test_the_api_serves_the_sky_and_each_trail(ws):
    [claim] = _record(ws, 1)
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as c:
        sky = c.get("/api/memory/constellation").json()
        assert [s["id"] for s in sky["stars"]] == [claim.id]
        p = c.get(f"/api/claims/{claim.id}/provenance").json()
        assert p["excerpt_verified"] is True and p["observation"]["connector"] == "upload"
        assert c.get("/api/claims/clm_nope/provenance").status_code == 404


def test_two_thousand_claims_are_served_quickly(ws):
    _record(ws, 2200, conf="medium")
    t0 = time.perf_counter()
    out = constellation.stars(ws)
    assert len(out["stars"]) == 2200 and time.perf_counter() - t0 < 3.0
