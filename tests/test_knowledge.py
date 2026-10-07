"""Knowledge page API: sources and freshness, recent changes, open conflicts, re-fetch, import, promote."""

from __future__ import annotations

import anyio
import yaml
from agent_fakes import FakeEngine
from fastapi.testclient import TestClient
from test_rulecheck import QUOTE, RULE, FakeJudge
from test_vault import FIX, Pages, fixture, public_dns  # noqa: F401  (fixture)

from lighthouse_gc import notify
from lighthouse_gc.server.app import create_app
from lighthouse_gc.vault import Vault

W = {"X-Lighthouse": "1"}


class _Quiet:
    def send(self, note, cfg, secret):
        pass


def _client(ws, http_mock, sync=True):
    Pages(http_mock).install()
    if sync:
        anyio.run(lambda: Vault(ws).sync())
    app = create_app(ws, allowed_hosts=["testserver"], engine=FakeEngine([("text", RULE)]))
    return app, TestClient(app)


def test_sources_freshness_and_recent_changes(ws, http_mock, public_dns):  # noqa: F811
    _, c = _client(ws, http_mock)
    k = c.get("/api/knowledge").json()
    assert k["enabled"] is True and "uscis.gov" in k["tier1_domains"] and "finding" not in k["kinds"]
    by_id = {s["id"]: s for s in k["sources"]}
    assert by_id["ecfr-8cfr-214-2-o"]["fresh"] is True and by_id["ecfr-8cfr-214-2-o"]["tier"] == 1
    assert by_id["visa-bulletin"]["status"] == "unreadable" and by_id["visa-bulletin"]["fresh"] is False
    assert by_id["uscis-g-1055"]["ttl"] == 7 and by_id["visa-bulletin"]["ttl"] == "monthly"
    assert by_id["uscis-i-129"]["effective_date"] == "2026-09-09"
    recent = k["recent"]
    assert recent and recent[0]["fetched_at"] >= recent[-1]["fetched_at"]
    assert any(r["status"] == "unreadable" and r["title"].startswith("Visa Bulletin") for r in recent)
    assert k["conflicts"] == []

    detail = c.get("/api/knowledge/sources/uscis-i-129").json()
    [snap] = detail["snapshots"]
    text = c.get(f"/api/knowledge/snapshots/{snap['sha']}").text
    assert "Petition for a Nonimmigrant Worker" in text
    assert c.get("/api/knowledge/snapshots/" + "0" * 64).status_code == 404
    assert c.get("/api/knowledge/snapshots/..%2F..%2Fsecret").status_code == 404
    assert c.get("/api/knowledge/sources/nope").status_code == 404


def test_refetch_import_and_off_switch(ws, http_mock, public_dns):  # noqa: F811
    _, c = _client(ws, http_mock, sync=False)
    r = c.post("/api/knowledge/sync", json={"sources": ["uscis-i-129"], "force": True}, headers=W)
    assert r.status_code == 200 and [x["status"] for x in r.json()] == ["new"]
    assert c.post("/api/knowledge/sync", json={"sources": ["nope"]}, headers=W).status_code == 400

    files = {"file": ("bulletin.html", fixture("uscis-pm-eb1-extraordinary.html"), "text/html")}
    r = c.post("/api/knowledge/import/visa-bulletin", files=files, headers=W)
    assert r.status_code == 200 and r.json()["origin"] == "manual"
    bot = {"file": ("saved.html", (FIX / "cloudflare-403.html").read_bytes(), "text/html")}
    assert c.post("/api/knowledge/import/uscis-o1", files=bot, headers=W).status_code == 400

    cfg = ws.config()
    cfg.vault.enabled = False
    ws.save_config(cfg)
    assert c.get("/api/knowledge").json()["enabled"] is False
    assert c.post("/api/knowledge/sync", json={}, headers=W).status_code == 400


def test_open_conflicts_list_where_they_appeared(ws, http_mock, public_dns, monkeypatch):  # noqa: F811
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": _Quiet()})
    app, c = _client(ws, http_mock)
    app.state.runner._judge = FakeJudge(rules=[
        ("three of the ten", QUOTE, "entails", "Volume 6"),
        ("three of the ten", "A petitioner relying on evidence that is comparable", "contradicts", "Volume 2"),
    ])  # fmt: skip

    async def go():
        runner = app.state.runner
        return await runner.wait((await runner.start("manual", "what does EB-1A need?")).id)

    run = anyio.run(go)
    [conflict] = c.get("/api/knowledge").json()["conflicts"]
    assert conflict["where"] == {"type": "run", "id": run.id, "label": "what does EB-1A need?"}
    assert {x["verdict"] for x in conflict["claim"]["citations"]} == {"entails", "contradicts"}


def test_promoting_a_finding_makes_it_a_source(ws, http_mock, public_dns):  # noqa: F811
    _, c = _client(ws, http_mock)
    text = f"New guidance. {QUOTE} for this classification, USCIS says. " * 6
    found = Vault(ws).add_finding(
        "https://www.uscis.gov/newsroom/alerts/new-guidance", "USCIS alert", text, "run_1"
    )
    k = c.get("/api/knowledge").json()
    [f] = [s for s in k["sources"] if s["finding"]]
    assert f["id"] == found.source_id and f["tier"] == 1

    assert (
        c.post(f"/api/knowledge/findings/{f['id']}/promote", json={"kind": "finding"}, headers=W).status_code
        == 400
    )
    assert (
        c.post("/api/knowledge/findings/uscis-i-129/promote", json={"kind": "form"}, headers=W).status_code
        == 400
    )
    r = c.post(f"/api/knowledge/findings/{f['id']}/promote", json={"kind": "guidance"}, headers=W)
    assert r.status_code == 200 and r.json()["kind"] == "guidance"
    saved = yaml.safe_load((ws.root / "vault" / "sources.yaml").read_text())
    assert [s["id"] for s in saved["sources"]] == [f["id"]]
    assert ws.changes()[-1].action == "vault.promote"
    vault = Vault(ws)
    promoted = vault.manifest.source(f["id"])
    assert promoted.finding is False and promoted.kind == "guidance"
    assert not any(s["finding"] for s in c.get("/api/knowledge").json()["sources"])
    # Before promotion rule-check's retrieval skipped it; now it's offered like any source.
    hits = vault.search("new guidance for this classification USCIS says", k=20, findings=False)
    assert any(h.source_id == f["id"] for h in hits)
