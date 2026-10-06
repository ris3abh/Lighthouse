from __future__ import annotations

import pytest
from conftest import mock_github
from fastapi.testclient import TestClient

from lighthouse_gc.criteria.dashboard import render
from lighthouse_gc.server.app import create_app

W = {"X-Lighthouse": "1"}


@pytest.fixture
def client(demo_ws):
    return TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))


def test_overview(client):
    data = client.get("/api/overview").json()
    assert data["person"]["name"] == "Alex Rivera"
    board = data["scoreboard"]
    assert board["profile"] == "o1a" and board["banked"] == 2 and board["threshold"] == 3
    assert data["inbox_pending"] == 12  # 5 evidence + 7 self-reported trackers from the demo chat export
    assert {p["id"] for p in data["profiles"]} >= {"o1a", "eb1a"}
    assert data["sparklines"] and data["sparklines"][0]["points"]
    assert len(data["deadlines"]) <= 3


def test_switch_profile(client, demo_ws):
    r = client.put("/api/profile", json={"id": "eb1a"}, headers=W)
    assert r.status_code == 200 and r.json()["profile"] == "eb1a"
    assert demo_ws.config().profile == "eb1a"
    assert client.put("/api/profile", json={"id": "nope"}, headers=W).status_code == 400


def test_writes_require_header(client):
    assert client.put("/api/profile", json={"id": "eb1a"}).status_code == 403


def test_foreign_host_rejected(demo_ws):
    c = TestClient(create_app(demo_ws), base_url="http://evil.example")
    assert c.get("/api/overview").status_code == 400
    ok = TestClient(create_app(demo_ws), base_url="http://127.0.0.1:7777")
    assert ok.get("/api/health").status_code == 200


def test_inbox_accept_flow(client, demo_ws):
    pending = [c for c in client.get("/api/inbox").json() if c["kind"] == "evidence"]
    assert len(pending) == 5 and pending[0]["confidence"] >= pending[-1]["confidence"]
    target = next(c for c in pending if c["evidence_type"] == "ml_model")
    r = client.post(f"/api/inbox/{target['id']}/accept", json={"date": "2026-10-06"}, headers=W)
    assert r.status_code == 200, r.text
    exhibit = r.json()
    assert (demo_ws.root / exhibit["file"]).exists()
    assert len([c for c in client.get("/api/inbox").json() if c["kind"] == "evidence"]) == 4
    row = next(
        c for c in client.get("/api/scoreboard").json()["criteria"] if c["id"] == "original_contributions"
    )
    assert row["exhibit_count"] == 2 and row["status"] == "banked"
    assert client.get("/api/overview").json()["scoreboard"]["banked"] == 3


def test_inbox_edit_reject_snooze(client):
    ids = [c["id"] for c in client.get("/api/inbox").json()]
    r = client.patch(f"/api/inbox/{ids[0]}", json={"summary": "edited"}, headers=W)
    assert r.json()["summary"] == "edited"
    assert client.post(f"/api/inbox/{ids[1]}/reject", headers=W).json()["status"] == "rejected"
    assert (
        client.post(f"/api/inbox/{ids[2]}/snooze", json={"until": "2099-01-01"}, headers=W).status_code == 200
    )
    assert len(client.get("/api/inbox").json()) == 12 - 2  # edit keeps it, reject + snooze hide two
    assert client.post("/api/inbox/cand_missing/reject", headers=W).status_code == 404


def test_evidence_listing_and_upload(client, demo_ws):
    data = client.get("/api/exhibits").json()
    judging = next(c for c in data["criteria"] if c["id"] == "judging")
    assert judging["status"] == "banked" and len(judging["exhibits"]) == 3
    assert judging["exhibit_count"] == 2 and judging["in_progress_count"] == 1  # the MLH invitation
    assert "judge_invite" in judging["evidence_types"]
    assert data["naming_issues"] == []

    r = client.post(
        "/api/exhibits/upload",
        files={"file": ("press.pdf", b"%PDF-1.4", "application/pdf")},
        data={
            "criterion": "press",
            "evidence_type": "press_article",
            "title": "Profile in ML Weekly",
            "date": "2026-10-01",
            "signals": "about_the_person, major_media",
        },
        headers=W,
    )
    assert r.status_code == 200, r.text
    assert r.json()["file"] == "evidence/press/press_2026-10-01_profile-in-ml-weekly.pdf"
    assert r.json()["signals"] == ["about_the_person", "major_media"]

    preview = client.get(f"/api/files/{r.json()['file']}")
    assert preview.status_code == 200 and preview.headers["content-security-policy"] == "sandbox"


def test_remap_and_override(client):
    exhibit = client.get("/api/exhibits").json()["criteria"][0]["exhibits"][0]
    r = client.patch(f"/api/exhibits/{exhibit['id']}", json={"criterion": "press"}, headers=W)
    assert r.json()["file"].startswith("evidence/press/")
    r = client.put("/api/criteria/membership/override", json={"status": "dropped"}, headers=W)
    assert next(c for c in r.json()["criteria"] if c["id"] == "membership")["status"] == "dropped"


def test_file_preview_is_confined_to_evidence(client):
    assert client.get("/api/files/lighthouse.yaml").status_code == 404
    assert client.get("/api/files/../../etc/passwd").status_code in (400, 404)
    assert client.get("/api/files/evidence/%2e%2e/lighthouse.yaml").status_code in (400, 404)


def test_metrics_and_export(client):
    series = client.get("/api/metrics").json()["series"]
    stars = next(s for s in series if s["item"] == "arivera-demo/fastgrad" and s["metric"] == "stars")
    assert stars["value"] == 1840 and stars["delta"] > 0 and stars["url"].startswith("https://github.com/")
    csv_text = client.get("/api/metrics/export.csv").text
    assert csv_text.startswith("date,source,item,metric,value\n")


def test_sources_add_and_remove(client, http_mock):
    mock_github(http_mock)
    r = client.post("/api/sources", json={"input": "https://github.com/arivera-demo/fastgrad"}, headers=W)
    assert r.status_code == 200, r.text
    ids = [s["id"] for s in client.get("/api/sources").json()]
    assert "github:arivera-demo/fastgrad" in ids
    assert client.post("/api/sources", json={"input": "https://example.com"}, headers=W).status_code == 400
    assert client.delete("/api/sources/github:arivera-demo/fastgrad", headers=W).status_code == 200
    assert "github:arivera-demo/fastgrad" not in [s["id"] for s in client.get("/api/sources").json()]


def test_unknown_api_route_is_404(client):
    assert client.get("/api/nope").status_code == 404


def test_demo_renders_with_no_network(demo_ws, http_mock):
    """The demo workspace must render (API + DASHBOARD.md) without a single HTTP request."""
    c = TestClient(create_app(demo_ws, allowed_hosts=["testserver"]))
    for path in (
        "/api/overview",
        "/api/inbox",
        "/api/exhibits",
        "/api/metrics",
        "/api/sources",
        "/api/profiles",
    ):
        assert c.get(path).status_code == 200, path
    text = render(demo_ws)
    assert "2 banked / 3 needed" in text and "not legal advice" in text
    assert http_mock.calls.call_count == 0


def test_api_responses_are_not_cached(client):
    assert client.get("/api/overview").headers["cache-control"] == "no-store"


def test_claims_api_shows_provenance(client):
    pending = client.get("/api/inbox").json()
    model = next(c for c in pending if c["evidence_type"] == "ml_model")
    claims = client.get(f"/api/claims?ids={','.join(model['claim_ids'])}").json()
    assert claims and {c["status"] for c in claims} == {"proposed"}
    downloads = next(c for c in claims if c["predicate"] == "downloads_all_time")
    assert downloads["excerpt"] == '"downloadsAllTime": 118000'
    assert downloads["source_url"].startswith("https://huggingface.co/api/models/")
    client.post(f"/api/inbox/{model['id']}/accept", json={}, headers=W)
    after = client.get(f"/api/claims?ids={','.join(model['claim_ids'])}").json()
    assert {c["status"] for c in after} == {"approved"}
    summary = client.get("/api/memory").json()
    assert summary["problems"] == [] and summary["by_status"]["approved"] >= 1


def test_upload_with_stage(client):
    r = client.post(
        "/api/exhibits/upload",
        files={"file": ("i.pdf", b"%PDF", "application/pdf")},
        data={
            "criterion": "judging",
            "evidence_type": "judge_invite",
            "title": "Invite",
            "date": "2026-10-01",
            "stage": "invited",
        },
        headers=W,
    )
    assert r.json()["stage"] == "invited"
    judging = next(c for c in client.get("/api/scoreboard").json()["criteria"] if c["id"] == "judging")
    assert judging["in_progress_count"] == 2  # the demo's MLH invitation + this one
