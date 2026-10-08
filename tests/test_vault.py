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

from areao1 import notify
from areao1.cli import app
from areao1.core import clock
from areao1.core.models import utcnow
from areao1.jobs import JOBS
from areao1.vault import Vault, load_manifest
from areao1.vault import store as vault_store
from areao1.vault.store import chunk_text
from areao1.vault.watch import run_watch

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

    def install(
        self, rules: list | None = None, versions: dict | None = None, community: tuple | None = None
    ):
        r = self.router
        r.get("https://www.ecfr.gov/api/versioner/v1/titles.json").respond(json=TITLES)
        # the community library (ADR 0011 §3): empty by default; ``community`` = (entries, {path: bytes})
        lib = "https://raw.githubusercontent.com/ris3abh/areao1-community-vault/main"
        entries, files = community or ([], {})
        r.get(f"{lib}/manifest.json").respond(json={"version": 1, "snapshots": entries})
        for path, body in files.items():
            r.get(f"{lib}/{path}").respond(content=body)
        # change signals (ADR 0011): Federal Register final rules and eCFR amendment dates, none by default
        r.get("https://www.federalregister.gov/api/v1/documents.json",
              params__contains={"conditions[type][]": "RULE"}).respond(json={"results": rules or []})  # fmt: skip
        r.get("https://www.ecfr.gov/api/versioner/v1/versions/title-8.json").mock(
            side_effect=lambda req: httpx.Response(
                200, json={"content_versions": (versions or {}).get(req.url.params["part"], [])}
            )
        )
        served = {
            "ecfr-8cfr-214-2-o": (200, fixture("ecfr-214.2.xml"), "text/xml"),
            "ecfr-8cfr-204-5-h": (200, fixture("ecfr-204.5.xml"), "text/xml"),
            "ecfr-8cfr-106-2": (200, fixture("ecfr-106.2.xml"), "text/xml"),
            "ecfr-8cfr-106-4": (200, fixture("ecfr-106.4.xml"), "text/xml"),
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
    assert (ws.root / "vault" / "log.jsonl").exists() and not (ws.root / ".areao1").is_relative_to(
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


def test_watch_reminds_to_reimport_manual_sources_when_their_window_lapses(ws, pages, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": rec})
    m = load_manifest()
    manual = {s.id for s in m.sources if s.manual}
    assert {
        "uscis-i-129",
        "uscis-g-1055",
        "uscis-pm-6-f-2",
        "visa-bulletin",
        "uscis-processing-times",
    } <= manual
    assert not any(s.manual for s in m.sources if "ecfr.gov" in s.url or s.tier == 3)

    # uscis.gov refuses the client; the person imports a saved copy of the I-129 page.
    pages.page("uscis-i-129", fixture("cloudflare-403.html"), status=403)
    pages.router.routes.clear()
    pages.install()
    vault = Vault(ws)
    vault.import_file("uscis-i-129", fixture("uscis-i-129.html"), "Form I-129.html")
    run_watch(ws)
    # Never-imported manual sources (the visa bulletin, processing times) don't nag; the fresh import doesn't either.
    assert not any(n.title.startswith("Re-import") for n in rec.sent)
    assert vault.lapsed_manual() == []

    # Eight days later, past the forms window, but no relevant rule changed: the I-129 page has a change signal
    # (ADR 0011), so nothing asks for a re-import.
    _at(monkeypatch, timedelta(days=8))
    lines = run_watch(ws)
    assert not any(n.title.startswith("Re-import") for n in rec.sent) and vault.lapsed_manual() == []
    assert "signals: no new changes" in lines and any("uscis-i-129: unreadable" in line for line in lines)

    # A fee rule that touches Form I-129 takes effect on day 9: one reminder, naming the change, with the link.
    effective = clock.local_date(utcnow() + timedelta(days=9)).isoformat()
    rule = {"document_number": "2026-12345", "title": "U.S. Citizenship and Immigration Services Fee Schedule and "
            "Changes to Form I-129", "abstract": "Adjusts fees.", "effective_on": effective,
            "html_url": "https://www.federalregister.gov/d/2026-12345", "cfr_references": [{"title": 8, "part": 106}]}  # fmt: skip
    pages.router.routes.clear()
    pages.install(rules=[rule])
    _at(monkeypatch, timedelta(days=10))
    run_watch(ws)
    [note] = [n for n in rec.sent if n.title.startswith("Re-import")]
    assert (
        note.title
        == "Re-import: Form I-129, Petition for a Nonimmigrant Worker (edition, instructions, where to file)"
    )
    assert note.url == "https://www.uscis.gov/i-129" and "https://www.uscis.gov/i-129" in note.body
    assert (
        f"changed since: U.S. Citizenship and Immigration Services Fee Schedule and Changes to Form I-129 (in effect {effective})"
        in note.body
    )
    assert "#/knowledge" in note.body and "last imported" in note.body and note.event == "vault"
    # The next day's run doesn't repeat it (same lapse).
    _at(monkeypatch, timedelta(days=11))
    run_watch(ws)
    assert len([n for n in rec.sent if n.title.startswith("Re-import")]) == 1
    # Re-importing clears it.
    vault.import_file("uscis-i-129", fixture("uscis-i-129.html"), "Form I-129.html")
    assert vault.lapsed_manual() == []


def test_sources_without_a_signal_keep_their_timer_and_stale_signals_fall_back_to_timers(
    ws, pages, monkeypatch
):
    vault = Vault(ws)
    rows = "".join(
        f"<tr><td>Form I-{100 + n}</td><td>Service Center {n}</td><td>{n + 2} months</td></tr>"
        for n in range(40)
    )
    times = f"<html><body><h1>Check case processing times</h1><table>{rows}</table></body></html>".encode()
    vault.import_file("uscis-processing-times", times, "Processing times.html")  # no signal
    vault.import_file("uscis-i-129", fixture("uscis-i-129.html"), "Form I-129.html")  # signal: forms
    from areao1.vault import signals

    assert anyio.run(signals.check, vault, None) == ["signals: no new changes"]
    _at(monkeypatch, timedelta(days=8))
    anyio.run(signals.check, vault, None)  # the daily watch checks the feeds again: nothing relevant changed
    assert [s.id for s, _ in vault.lapsed_manual()] == ["uscis-processing-times"]  # 7-day timer
    _at(monkeypatch, timedelta(days=12))  # no check for four days (offline): timers decide
    assert {s.id for s, _ in vault.lapsed_manual()} == {"uscis-processing-times", "uscis-i-129"}


def test_an_unrelated_rule_changes_nothing_and_an_unreachable_feed_is_said(ws, pages, monkeypatch):
    from areao1.vault import signals

    other = {"document_number": "2026-1", "title": "Temporary Agricultural Workers (H-2A)", "abstract": "Farm labor.",
             "effective_on": "2026-01-01", "html_url": "x", "cfr_references": [{"title": 8, "part": 655}]}  # fmt: skip
    pages.router.routes.clear()
    pages.install(
        rules=[other],
        versions={"214": [{"identifier": "214.2", "amendment_date": "2024-04-01", "substantive": True}]},
    )
    vault = Vault(ws)
    assert anyio.run(signals.check, vault, None) == ["signals: 1 new change"]  # the eCFR baseline for 214.2
    assert [e["signal"] for e in signals.load(vault)["events"]] == ["o1"]  # H-2A matched nothing
    pages.router.routes.clear()
    pages.router.get(signals.FR_URL).respond(503)
    assert "Federal Register unreachable" in anyio.run(signals.check, vault, None)[0]


def test_manual_source_links_resolve_this_months_url(ws):
    vault = Vault(ws)
    bulletin = vault.manifest.source("visa-bulletin")
    link = vault.link(bulletin)
    assert "{" not in link and link.startswith("https://travel.state.gov/") and link.endswith(".html")
    assert vault.link(vault.manifest.source("uscis-i-129")) == "https://www.uscis.gov/i-129"


def test_fee_regulation_is_the_primary_fee_source(ws, pages):
    m = load_manifest()
    primary, page = m.source("ecfr-8cfr-106-2"), m.source("uscis-g-1055")
    assert primary.tier == 1 and primary.kind == "fees" and not primary.manual
    assert m.source("ecfr-8cfr-106-4").kind == "fees"
    assert page.secondary_to == "ecfr-8cfr-106-2" and page.manual
    with pytest.raises(ValueError, match="secondary_to"):
        type(m).model_validate({"sources": [{**page.model_dump(), "secondary_to": "no-such-source"}]})

    vault = Vault(ws)
    results = {r.source_id: r for r in _sync(vault)}
    assert results["ecfr-8cfr-106-2"].status == "new" and results["ecfr-8cfr-106-2"].effective_date == date(
        2026, 10, 5
    )
    text = vault.snapshot_text(results["ecfr-8cfr-106-2"].sha256)
    assert text.startswith("§ 106.2 USCIS fees.")
    assert "Petition for O Nonimmigrant Worker with 1 to 25 named beneficiaries: $1,055." in text
    assert "Immigrant Petition for Alien Worker, Form I-140." in text and "$715." in text
    premium = vault.snapshot_text(results["ecfr-8cfr-106-4"].sha256)
    assert "section 101(a)(15)(O)(i) or (ii) of the INA—$2,965." in premium
    hits = vault.search("Form I-129 O petition filing fee", k=5, kinds={"fees"})
    assert hits[0].source_id == "ecfr-8cfr-106-2"
    status = {s["id"]: s for s in vault.status()}
    assert (
        status["uscis-g-1055"]["secondary_to"] == "ecfr-8cfr-106-2"
        and status["uscis-g-1055"]["manual"] is True
    )
    # A workspace override may point a source of its own at a bundled primary.
    (ws.root / "vault").mkdir(exist_ok=True)
    (ws.root / "vault" / "sources.yaml").write_text(
        "version: 1\nsources:\n  - {id: my-fee-page, title: My fee page, url: 'https://www.uscis.gov/fees', "
        "tier: 1, kind: fees, manual: true, secondary_to: ecfr-8cfr-106-2}\n"
    )
    assert (
        load_manifest(ws.root / "vault" / "sources.yaml").source("my-fee-page").secondary_to
        == "ecfr-8cfr-106-2"
    )


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


def test_one_reminder_only_when_a_relevant_change_has_no_newer_snapshot_anywhere(ws, pages, monkeypatch):
    """G4 (ADR 0011 §4): a rule change makes the saved I-129 page stale; a newer community snapshot (or a capture)
    settles it silently; only when none exists does one notification go out, with a direct link."""
    import hashlib

    rec = _Recorder()
    monkeypatch.setattr(notify, "CHANNELS", lambda: {"desktop": rec})
    pages.page("uscis-i-129", fixture("cloudflare-403.html"), status=403)
    vault = Vault(ws)
    vault.import_file("uscis-i-129", fixture("uscis-i-129.html"), "Form I-129.html")
    effective = clock.local_date(utcnow() + timedelta(days=2)).isoformat()
    rule = {"document_number": "2026-777", "title": "Fee Schedule; Form I-129 changes", "abstract": "",
            "effective_on": effective, "html_url": "https://www.federalregister.gov/d/2026-777",
            "cfr_references": [{"title": 8, "part": 106}]}  # fmt: skip
    fresh = fixture("uscis-i-129.html").replace(
        b"</body>", b"<p>Edition 11/01/26 after the fee rule.</p></body>"
    )
    sha = hashlib.sha256(fresh).hexdigest()
    newer = {"source_id": "uscis-i-129", "url": "https://www.uscis.gov/i-129", "sha256": sha,
             "captured_at": (utcnow() + timedelta(days=3)).isoformat(), "file": f"snapshots/{sha}.html",
             "license": "public-domain-us-gov"}  # fmt: skip

    # A newer snapshot exists in the community library: imported, nothing to ask.
    pages.router.routes.clear()
    pages.install(rules=[rule], community=([newer], {newer["file"]: fresh}))
    _at(monkeypatch, timedelta(days=4))
    lines = run_watch(ws)
    assert "community library: 1 newer snapshot imported" in lines
    assert not [n for n in rec.sent if n.title.startswith("Re-import")]

    # Another relevant rule later, and no newer snapshot anywhere: exactly one reminder, with the page's link.
    later = {**rule, "document_number": "2026-888", "title": "Form I-129 edition update",
             "effective_on": clock.local_date(utcnow() + timedelta(days=6)).isoformat()}  # fmt: skip
    pages.router.routes.clear()
    pages.install(rules=[rule, later], community=([newer], {newer["file"]: fresh}))
    _at(monkeypatch, timedelta(days=7))
    run_watch(ws)
    _at(monkeypatch, timedelta(days=8))
    run_watch(ws)
    [note] = [n for n in rec.sent if n.title.startswith("Re-import")]
    assert note.url == "https://www.uscis.gov/i-129" and "Form I-129 edition update" in note.body

    # Visiting the page with the capture extension settles it too.
    from areao1.vault import capture

    capture.capture(ws, "https://www.uscis.gov/i-129", "I-129", fresh.decode() + "<!-- visited -->")
    assert vault.lapsed_manual() == []


def test_broad_cfr_parts_dont_count_as_o1_or_fee_changes(ws, pages):
    """Found live: rules on bonds and public charge (part 103) and on another visa class (part 214) aren't changes
    to O-1 pages or fees; only a rule naming them, or the fee schedule (part 106), is."""
    from areao1.vault import signals

    def rule(n, title, parts):
        return {"document_number": n, "title": title, "abstract": "", "effective_on": "2026-08-01", "html_url": "x",
                "cfr_references": [{"title": 8, "part": p} for p in parts]}  # fmt: skip

    pages.router.routes.clear()
    pages.install(rules=[rule("1", "Immigration Bonds; Technical Amendment", [103]),
                         rule("2", "Changes for Lightering Vessel Crew Nonimmigrants", [214]),
                         rule("3", "Fee Schedule Adjustment", [106]),
                         rule("4", "Updates to the O-1 Classification", [214])])  # fmt: skip
    vault = Vault(ws)
    anyio.run(signals.check, vault, None)
    got = sorted(
        (e["id"].split(":")[1], e["signal"])
        for e in signals.load(vault)["events"]
        if e["feed"] == "federal_register"
    )
    assert got == [("3", "fees"), ("3", "forms"), ("4", "o1")]
