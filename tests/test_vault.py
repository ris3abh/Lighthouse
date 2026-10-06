"""Knowledge vault (SPEC 5a): manifest, fetch + content-addressed snapshots, chunk index, freshness (TTL
registry), change watch. Recorded fixtures of the real Tier 1 / Tier 2 pages; no live network."""

from __future__ import annotations

import gzip
import hashlib
import re
import socket
from datetime import date, timedelta
from pathlib import Path

import anyio
import httpx
import pytest
from typer.testing import CliRunner

from lighthouse_gc import notify
from lighthouse_gc.cli import app
from lighthouse_gc.core.models import utcnow
from lighthouse_gc.jobs import JOBS
from lighthouse_gc.vault import Vault, load_manifest
from lighthouse_gc.vault import store as vault_store
from lighthouse_gc.vault.store import chunk_text
from lighthouse_gc.vault.watch import run_watch

FIX = Path(__file__).parent / "fixtures" / "vault"
HTML = {"content-type": "text/html; charset=utf-8"}
TITLES = {"titles": [{"number": 8, "name": "Aliens and Nationality", "latest_issue_date": "2026-10-01",
                      "up_to_date_as_of": "2026-10-05"}]}  # fmt: skip
GENERIC = ("<html><head><title>{title}</title></head><body><main><h1>{title}</h1>"
           + "<p>{body} This page explains eligibility, how to file and what evidence to submit.</p>" * 4
           + "</main></body></html>")  # fmt: skip


def fixture(name: str) -> bytes:
    path = FIX / name
    if path.exists():
        return path.read_bytes()
    return gzip.decompress((FIX / f"{name}.gz").read_bytes())


class Pages:
    """Serve the recorded pages for every source in the bundled manifest."""

    def __init__(self, router):
        self.router = router
        self.overrides: dict[str, tuple[int, bytes, str]] = {}
        self.calls: list[str] = []
        m = load_manifest()
        self.urls = {s.id: s.url for s in m.sources}

    def page(self, source_id: str, body: bytes, ctype: str = "text/html; charset=utf-8", status: int = 200):
        self.overrides[source_id] = (status, body, ctype)

    def install(self):
        r = self.router
        r.get("https://www.ecfr.gov/api/versioner/v1/titles.json").respond(json=TITLES)
        served = {
            "ecfr-8cfr-214-2-o": (200, fixture("ecfr-214.2.xml"), "text/xml"),
            "ecfr-8cfr-204-5-h": (200, fixture("ecfr-204.5.xml"), "text/xml"),
            "ina-101-a-15-o": (503, b"Service Unavailable", "text/plain"),
            "ina-203-b-1-a": (503, b"Service Unavailable", "text/plain"),
            "uscis-pm-2-m-4": (200, fixture("uscis-pm-o1.html"), HTML["content-type"]),
            "uscis-pm-6-f-2": (200, fixture("uscis-pm-eb1-extraordinary.html"), HTML["content-type"]),
            "uscis-i-129": (200, fixture("uscis-i-129.html"), HTML["content-type"]),
            "uscis-g-1055": (200, fixture("uscis-g-1055-fees.html"), HTML["content-type"]),
            "uscis-processing-times": (403, fixture("cloudflare-403.html"), HTML["content-type"]),
            "visa-bulletin": (403, fixture("cloudflare-403.html"), HTML["content-type"]),
            "federal-register-uscis": (200, fixture("federal-register-uscis.json"), "application/json"),
            "kazarian-v-uscis": (200, fixture("kazarian.pdf"), "application/pdf"),
            "matter-of-chawathe": (200, fixture("chawathe.pdf"), "application/pdf"),
        }
        for sid, url in self.urls.items():
            pattern = re.sub(r"\\\{\w+\\\}", ".+?", re.escape(url)) + "$"
            status, body, ctype = (
                self.overrides.get(sid)
                or served.get(sid)
                or (
                    200,
                    GENERIC.format(title=sid, body=f"Generic text for {sid}.").encode(),
                    HTML["content-type"],
                )
            )

            def respond(request, sid=sid, status=status, body=body, ctype=ctype):
                self.calls.append(sid)
                return httpx.Response(status, content=body, headers={"content-type": ctype})

            r.get(url__regex=pattern).mock(side_effect=respond)


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [(2, 1, 6, "", ("93.184.216.34", p))])


@pytest.fixture
def pages(http_mock, public_dns):
    p = Pages(http_mock)
    p.install()
    return p


def _sync(vault, **kw):
    return anyio.run(lambda: vault.sync(**kw))


def _at(monkeypatch, delta: timedelta):
    now = utcnow() + delta
    monkeypatch.setattr(vault_store, "utcnow", lambda: now)
    return now


# ----------------------------------------------------------------------------- manifest


def test_manifest_covers_every_kind_and_tier():
    m = load_manifest()
    assert {s.tier for s in m.sources} == {1, 2, 3}
    for s in m.sources:
        assert s.kind in m.ttl_days, s.id
        if s.tier == 1:
            host = re.sub(r"^https?://([^/]+)/.*", r"\1", s.url)
            assert any(host == d or host.endswith("." + d) for d in m.tier1_domains), s.id
    volatile = {k: m.ttl_days[k] for k in ("fees", "form", "processing_times", "visa_bulletin")}
    assert volatile == {"fees": 7, "form": 7, "processing_times": 7, "visa_bulletin": "monthly"}
    assert m.ttl_days["regulation"] == 30
    kinds = {s.kind for s in m.sources}
    assert {"regulation", "statute", "policy", "form", "fees", "processing_times", "visa_bulletin",
            "federal_register", "case_law", "decisions", "secondary"} <= kinds  # fmt: skip


def test_monthly_ttl_expires_at_the_start_of_next_month():
    m = load_manifest()
    vb = m.source("visa-bulletin")
    checked = utcnow().replace(year=2026, month=10, day=14)
    assert m.expires_at(vb, checked).date() == date(2026, 11, 1)
    fees = m.source("uscis-g-1055")
    assert m.expires_at(fees, checked) - checked == timedelta(days=7)


def test_workspace_manifest_overrides(ws):
    (ws.root / "vault").mkdir()
    (ws.root / "vault" / "sources.yaml").write_text(
        "version: 1\nttl_days: {secondary: 14}\nsources:\n"
        "  - {id: wikipedia-o-1, title: 'off', url: 'https://en.wikipedia.org/wiki/O-1_visa', tier: 3, kind: secondary, enabled: false}\n"
        "  - {id: my-firm-guide, title: My attorney's checklist, url: 'https://firm.example/o1', tier: 3, kind: secondary}\n"
    )
    m = Vault(ws).manifest
    assert m.source("my-firm-guide") is not None and m.source("wikipedia-o-1").enabled is False
    assert m.ttl_days["secondary"] == 14 and m.ttl_days["fees"] == 7


def test_chunks_are_exact_slices():
    text = "Heading\n\n" + "\n".join(f"Line {i}. " + "word " * 40 for i in range(30)) + "\n" + "x. " * 900
    spans = chunk_text(text)
    assert spans and all(0 <= s < e <= len(text) for s, e in spans)
    assert all(e - s <= 1600 for s, e in spans)
    joined = " ".join(text[s:e] for s, e in spans)
    assert "Line 29." in joined and "Heading" in joined


# ----------------------------------------------------------------------------- sync


def test_sync_snapshots_indexes_and_logs(ws, pages):
    vault = Vault(ws)
    results = {r.source_id: r for r in _sync(vault)}
    assert results["ecfr-8cfr-214-2-o"].status == "new"
    assert (
        results["uscis-processing-times"].status == "unreadable"
        and "HTTP 403" in results["uscis-processing-times"].error
    )
    assert results["visa-bulletin"].status == "unreadable"
    assert results["ina-101-a-15-o"].status == "error" and "503" in results["ina-101-a-15-o"].error
    assert results["kazarian-v-uscis"].status == "new"  # PDF

    # Content-addressed: the snapshot file is named by the sha256 of its text.
    r = results["ecfr-8cfr-214-2-o"]
    text = vault.snapshot_text(r.sha256)
    assert hashlib.sha256(text.encode()).hexdigest() == r.sha256
    # Cut to paragraph (o): starts at (o), stops before (p).
    assert text.startswith("(o) Aliens of extraordinary ability or achievement") and "(p) Artists" not in text
    assert "sustained national or international acclaim" in text
    assert r.effective_date == date(2026, 10, 5)  # eCFR "up to date as of"
    assert results["uscis-i-129"].effective_date == date(2026, 9, 9)  # USCIS "Last Reviewed/Updated"
    assert results["uscis-g-1055"].effective_date == date(2026, 10, 1)

    log = vault.log()
    assert {e.source_id for e in log} == set(results)  # first fetch of everything is logged
    assert (ws.root / "vault" / "log.jsonl").exists() and not (ws.root / ".lighthouse").is_relative_to(
        ws.root / "vault"
    )
    assert (ws.cache_dir / "vault" / "vault.db").exists()

    # Nothing fresh is fetched again; only the unreadable / failed ones are retried.
    pages.calls.clear()
    again = _sync(vault)
    assert {x.source_id for x in again} == {
        "uscis-processing-times",
        "visa-bulletin",
        "ina-101-a-15-o",
        "ina-203-b-1-a",
    }
    assert len(vault.log()) == len(log) + 4


def test_bot_check_page_with_http_200_is_unreadable(ws, pages):
    pages.page("uscis-o1", fixture("ecfr-request-access.html"))
    pages.router.routes.clear()
    pages.install()
    r = {x.source_id: x for x in _sync(Vault(ws), ids=["uscis-o1"])}["uscis-o1"]
    assert r.status == "unreadable" and "bot-protection page (Federal Register :: Request Access)" in r.error
    assert Vault(ws).status()[0]["snapshots"] == 0 or all(
        s["snapshots"] == 0 for s in Vault(ws).status() if s["id"] == "uscis-o1"
    )


def test_private_addresses_are_refused(ws, http_mock, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [(2, 1, 6, "", ("10.0.0.5", p))])
    [r] = _sync(Vault(ws), ids=["uscis-o1"])
    assert r.status == "error" and "private or local" in r.error
    assert not list((ws.cache_dir / "vault").glob("snapshots/*/*"))


# ----------------------------------------------------------------------------- search


def test_hybrid_search_finds_the_rule_and_cites_exact_offsets(ws, pages):
    vault = Vault(ws)
    _sync(vault)
    [top, *_] = vault.search(
        "EB-1A evidence of at least three of the following criteria", k=5, tiers={1}, topics={"eb1a"}
    )
    assert top.tier == 1 and top.source_id in ("ecfr-8cfr-204-5-h", "uscis-pm-6-f-2")
    hits = vault.search("at least three of the following", k=8, tiers={1})
    assert any(
        h.source_id == "ecfr-8cfr-204-5-h" and "at least three of the following" in h.text for h in hits
    )
    for h in hits:
        assert vault.snapshot_text(h.sha256)[h.start : h.end] == h.text  # exact slice: quotes are checkable
        assert h.fresh and h.url.startswith("https://")
    chawathe = vault.search("preponderance of the evidence standard", k=3, tiers={2})
    assert chawathe[0].source_id == "matter-of-chawathe"
    kazarian = vault.search("final merits determination two-part analysis", k=3, tiers={2})
    assert kazarian[0].source_id == "kazarian-v-uscis"
    assert vault.chunk(hits[0].chunk_id).text == hits[0].text
    assert vault.search("anything", tiers={1}, kinds={"no-such-kind"}) == []


def test_freshness_windows(ws, pages, monkeypatch):
    vault = Vault(ws)
    _sync(vault)
    _at(monkeypatch, timedelta(days=8))
    status = {s["id"]: s for s in vault.status()}
    assert status["uscis-g-1055"]["fresh"] is False and status["uscis-i-129"]["fresh"] is False  # 7-day facts
    assert status["ecfr-8cfr-214-2-o"]["fresh"] is True  # regulations: 30 days
    assert status["kazarian-v-uscis"]["fresh"] is True  # case law: a year
    stale = vault.search("Form I-129 edition", k=10, tiers={1}, kinds={"form"})
    assert stale and not any(h.fresh for h in stale)
    assert vault.search("Form I-129 edition", k=10, tiers={1}, kinds={"form"}, fresh_only=True) == []
    # Expired facts are due for re-fetch; fresh ones are not.
    pages.calls.clear()
    _sync(vault)
    assert "uscis-i-129" in pages.calls and "uscis-g-1055" in pages.calls
    assert "ecfr-8cfr-214-2-o" not in pages.calls and "kazarian-v-uscis" not in pages.calls


# ----------------------------------------------------------------------------- watch


class _Recorder:
    def __init__(self):
        self.sent = []

    def send(self, note, cfg, secret):
        self.sent.append(note)


def test_vault_watch_notifies_only_on_tier1_changes_and_keeps_old_snapshots(ws, pages, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": rec})
    assert "vault-watch" in JOBS and ws.config().schedules["vault-watch"] == "0 6 * * *"

    first = run_watch(ws)
    assert (
        first[0].startswith("vault: ") and "new" in first[0] and rec.sent == []
    )  # first fetch: nothing "changed"

    # A day later the I-129 page has a new edition date; a Tier 3 page changed too.
    new_page = fixture("uscis-i-129.html").replace(
        b"edition date:&nbsp;09/09/26", b"edition date:&nbsp;11/02/26"
    )
    pages.page("uscis-i-129", new_page)
    pages.page("wikipedia-o-1", GENERIC.format(title="O-1", body="Rewritten secondary page.").encode())
    pages.router.routes.clear()
    pages.install()
    _at(monkeypatch, timedelta(hours=21))
    lines = run_watch(ws)
    assert "1 changed" in lines[0]  # Tier 1 re-checked daily; the Tier 3 page isn't due yet
    [note] = rec.sent
    assert note.event == "vault" and note.title.startswith("Tier 1 source changed: Form I-129")
    assert "11/02/26" in note.body and note.url.endswith("#/knowledge")

    vault = Vault(ws)
    entry = next(e for e in reversed(vault.log()) if e.source_id == "uscis-i-129")
    assert entry.status == "changed" and entry.previous_sha256 and entry.diff.added >= 1
    assert vault.snapshot_text(entry.previous_sha256) != vault.snapshot_text(entry.sha256)  # history kept
    assert next(s for s in vault.status() if s["id"] == "uscis-i-129")["snapshots"] == 2
    assert all(
        "11/02/26" in h.text
        for h in vault.search("edition date", k=5, kinds={"form"})
        if "edition date:" in h.text
    )

    # A forced Tier 3 change is recorded but never notified.
    forced = _sync(vault, ids=["wikipedia-o-1"], force=True)
    assert forced[0].status == "changed" and len(rec.sent) == 1


def test_watch_respects_the_off_switch(ws, http_mock):
    cfg = ws.config()
    cfg.vault.enabled = False
    ws.save_config(cfg)
    assert run_watch(ws)[0].startswith("skipped")


def test_reindex_rebuilds_from_snapshots(ws, pages):
    vault = Vault(ws)
    _sync(vault, ids=["ecfr-8cfr-204-5-h", "matter-of-chawathe"])
    before = vault.search("preponderance of the evidence", k=3)
    assert vault.reindex() == 2
    assert [h.chunk_id for h in vault.search("preponderance of the evidence", k=3)] == [
        h.chunk_id for h in before
    ]


def test_cli(ws, pages):
    r = CliRunner().invoke(app, ["vault", "sync", "-s", "ecfr-8cfr-204-5-h", "-w", str(ws.root)])
    assert r.exit_code == 0, r.output
    assert "new  ecfr-8cfr-204-5-h" in r.output
    r = CliRunner().invoke(app, ["vault", "search", "at least three of the following", "-w", str(ws.root)])
    assert "8 CFR 204.5(h)" in r.output and "fresh" in r.output
    r = CliRunner().invoke(app, ["vault", "status", "-w", str(ws.root)])
    assert "ecfr-8cfr-204-5-h" in r.output
    r = CliRunner().invoke(app, ["vault", "sync", "-s", "nope", "-w", str(ws.root)])
    assert r.exit_code != 0 and "unknown" in r.output


def test_blocked_sources_can_be_imported_from_a_saved_page(ws, pages):
    pages.page("uscis-i-129", fixture("cloudflare-403.html"), status=403)
    pages.router.routes.clear()
    pages.install()
    vault = Vault(ws)
    [blocked] = _sync(vault, ids=["uscis-i-129"])
    assert blocked.status == "unreadable"
    with pytest.raises(ValueError, match="bot-check page"):
        vault.import_file("uscis-i-129", fixture("ecfr-request-access.html"), "saved.html")
    with pytest.raises(ValueError, match="unknown vault source"):
        vault.import_file("nope", b"x", "x.html")
    entry = vault.import_file("uscis-i-129", fixture("uscis-i-129.html"), "Form I-129.html")
    assert entry.status == "new" and entry.origin == "manual" and entry.effective_date == date(2026, 9, 9)
    status = next(s for s in vault.status() if s["id"] == "uscis-i-129")
    assert status["fresh"] and status["status"] == "ok"
    assert any(
        h.source_id == "uscis-i-129" for h in vault.search("Form I-129 edition date", k=5, kinds={"form"})
    )
    r = CliRunner().invoke(
        app, ["vault", "import", "uscis-i-129", str(FIX / "federal-register-uscis.json"), "-w", str(ws.root)]
    )
    assert r.exit_code == 0 and "changed" in r.output


def test_maintenance_pages_are_unreadable(ws, pages):
    pages.page(
        "uscis-o1",
        b"<html><head><title>Under Maintenance</title></head><body>"
        + b"Back soon. " * 40
        + b"</body></html>",
    )
    pages.router.routes.clear()
    pages.install()
    [r] = _sync(Vault(ws), ids=["uscis-o1"])
    assert r.status == "unreadable" and "site unavailable (Under Maintenance)" in r.error
