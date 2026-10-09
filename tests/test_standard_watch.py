"""Watching the wording of the quoted standard (areao1/vault/standard.py): the weekly CI check falls back to the
community library's hash-verified snapshot when uscis.gov blocks the runner and goes red only on a real mismatch;
"stale" is a warning; vault-watch on the person's machine reads the live pages, opens an issue with gh only when
opted in, and pushes a fresh snapshot only when sharing is on. No network: pages come from the fixtures and the
in-repo copy of the community library, and gh is a recorder. Everything here is public U.S. government text."""

from __future__ import annotations

import gzip
import hashlib
import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from areao1.vault import standard

ROOT = Path(__file__).parents[1]
FIX = ROOT / "tests" / "fixtures" / "vault"
LIB = ROOT / "community-vault"
BASE = "https://raw.githubusercontent.com/ris3abh/areao1-community-vault/main"
PM6 = "https://www.uscis.gov/policy-manual/volume-6-part-f-chapter-2"
PM2 = "https://www.uscis.gov/policy-manual/volume-2-part-m-chapter-4"
KAZ = "https://cdn.ca9.uscourts.gov/datastore/opinions/2010/03/04/07-56774.pdf"
NOW = datetime(2026, 10, 9, tzinfo=UTC)


def _live(url: str, *, change: bool = False) -> bytes:
    page = {PM6: gzip.decompress((FIX / "uscis-pm-eb1-extraordinary.html.gz").read_bytes()),
            PM2: gzip.decompress((FIX / "uscis-pm-o1.html.gz").read_bytes()),
            KAZ: (FIX / "kazarian.pdf").read_bytes()}[url]  # fmt: skip
    if change and url == PM2:
        page = page.replace(
            b"totality of the evidence submitted demonstrates", b"evidence submitted demonstrates"
        )
    return page


class Library:
    """The community library over HTTP, from the in-repo copy; snapshots can be aged, altered or corrupted."""

    def __init__(self, captured: str | None = None, alter: bool = False, corrupt: bool = False):
        self.manifest = json.loads((LIB / "manifest.json").read_text())
        self.files = {e["file"]: (LIB / e["file"]).read_bytes() for e in self.manifest["snapshots"]}
        for e in self.manifest["snapshots"]:
            if captured:
                e["captured_at"] = captured
            if alter and e["source_id"] == "uscis-pm-2-m-4":
                body = self.files[e["file"]].replace(b"totality of the evidence submitted demonstrates",
                                                     b"evidence submitted demonstrates")  # fmt: skip
                sha = hashlib.sha256(body).hexdigest()
                e["sha256"], e["file"] = sha, f"snapshots/{sha}.html"
                self.files[e["file"]] = body
            if corrupt and e["source_id"] == "uscis-pm-6-f-2":
                self.files[e["file"]] = self.files[e["file"]] + b"<!-- tampered -->"

    def get(self, url: str) -> bytes:
        rel = url.removeprefix(BASE + "/")
        if rel == "manifest.json":
            return json.dumps(self.manifest).encode()
        return self.files[rel]


def _runner(lib: Library, *, kaz_ok: bool = True):
    """GitHub's runners: uscis.gov answers 403; the court's site and the library answer."""

    def get(url: str) -> bytes:
        if "uscis.gov" in url or (url == KAZ and not kaz_ok):
            raise standard.FetchError("curl: (22) The requested URL returned error: 403")
        return _live(url) if url == KAZ else lib.get(url)

    return get


@pytest.fixture
def ci():
    spec = importlib.util.spec_from_file_location(
        "check_vault_fixtures", ROOT / "scripts" / "check_vault_fixtures.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _by_id(checks):
    return {c.source_id: c for c in checks}


# ---------------------------------------------------------------------------------------------------- weekly CI


def test_ci_checks_blocked_chapters_through_the_community_snapshot_and_stays_green(ci):
    checks = _by_id(ci.check(_runner(Library()), NOW))
    for sid in ("uscis-pm-6-f-2", "uscis-pm-2-m-4"):
        c = checks[sid]
        assert c.how == "community snapshot" and not c.changed and not c.stale
        assert c.line().startswith(f"{sid}: matches, checked via community snapshot, captured 2026-10-06")
        assert "live page blocked" in c.line()
    assert checks["kazarian-v-uscis"].how == "live" and not checks["kazarian-v-uscis"].changed
    assert not any(c.changed for c in checks.values())  # blocked is never red


def test_an_old_snapshot_or_none_at_all_is_stale_a_warning_not_a_failure(ci):
    checks = _by_id(ci.check(_runner(Library(captured="2026-08-01T00:00:00+00:00")), NOW))
    c = checks["uscis-pm-2-m-4"]
    assert c.stale and not c.changed and "matches (stale)" in c.line() and "69 days old" in c.line()
    checks = _by_id(ci.check(_runner(Library(), kaz_ok=False), NOW))  # Kazarian blocked, no snapshot of it
    k = checks["kazarian-v-uscis"]
    assert (
        k.how == "unchecked" and k.stale and not k.changed and k.line().startswith("kazarian-v-uscis: stale")
    )


def test_a_real_wording_change_in_the_snapshot_is_red(ci, capsys, monkeypatch):
    checks = _by_id(ci.check(_runner(Library(alter=True)), NOW))
    c = checks["uscis-pm-2-m-4"]
    assert c.changed and c.quotes_missing and c.gone
    assert "WORDING CHANGED" in standard.report_markdown(
        [c]
    ) and "quoted passage not found" in standard.report_markdown([c])
    monkeypatch.setattr(ci, "check", lambda: list(checks.values()))
    monkeypatch.setattr("sys.argv", ["check_vault_fixtures.py"])
    assert ci.main() == 1


def test_a_snapshot_that_fails_its_hash_is_never_used(ci):
    c = _by_id(ci.check(_runner(Library(corrupt=True)), NOW))["uscis-pm-6-f-2"]
    assert c.how == "unchecked" and c.stale and "no community snapshot" in c.note


def test_live_pages_are_checked_live_when_they_load(ci):
    checks = ci.check(_live, NOW)
    assert all(c.how == "live" and not c.changed for c in checks)
    changed = _by_id(ci.check(lambda u: _live(u, change=True), NOW))["uscis-pm-2-m-4"]
    assert changed.changed and changed.how == "live"


def test_a_crash_is_its_own_exit_code_never_a_wording_change(ci, monkeypatch):
    def boom():
        raise RuntimeError("bug")

    monkeypatch.setattr(ci, "check", boom)
    monkeypatch.setattr("sys.argv", ["check_vault_fixtures.py"])
    assert ci.main() == 3


def test_push_ci_never_runs_the_live_check():
    ci_yml = (ROOT / ".github" / "workflows" / "ci.yml").read_text()
    weekly = (ROOT / ".github" / "workflows" / "vault-fixtures.yml").read_text()
    assert "check_vault_fixtures" not in ci_yml
    assert "schedule:" in weekly and "push:" not in weekly and "pull_request" not in weekly
    assert "code == '1'" in weekly  # only a mismatch opens an issue


# ------------------------------------------------------------------------------------------ vault-watch, locally


class Gh:
    def __init__(self, open_issue: str = ""):
        self.calls: list[tuple[str, ...]] = []
        self.open = open_issue
        self.manifest = json.loads((LIB / "manifest.json").read_text())

    def __call__(self, *args: str, input: bytes | None = None) -> str:
        import base64

        self.calls.append(args)
        if args[:2] == ("issue", "list"):
            return self.open
        if args[:2] == ("issue", "create"):
            return "https://github.com/ris3abh/areao1/issues/99"
        if args[0] == "api" and args[1].startswith("repos/") and "manifest.json?ref=" in args[1]:
            return json.dumps(
                {"sha": "abc", "content": base64.b64encode(json.dumps(self.manifest).encode()).decode()}
            )
        return ""

    def did(self, *prefix: str) -> list[tuple[str, ...]]:
        return [c for c in self.calls if c[: len(prefix)] == prefix]


def _watch(ws, *, change=False, lib=None, report=False, share=False, gh=None, live_ok=True):
    from areao1.vault.store import Vault

    cfg = ws.config()
    cfg.vault.report_wording, cfg.vault.share_captures = report, share
    ws.save_config(cfg)
    lib = lib or Library()
    gh = gh or Gh()

    def get(url: str) -> bytes:
        if url.startswith(BASE):
            return lib.get(url)
        if not live_ok:
            raise standard.FetchError("offline")
        return _live(url, change=change)

    return standard.watch(ws, Vault(ws), get=get, run=gh, now=NOW), gh


def test_unchanged_and_fresh_does_nothing_outside(ws):
    lines, gh = _watch(ws, report=True, share=True)
    assert [ln for ln in lines if "matches, checked live" in ln] and len(lines) == 3
    assert gh.calls == []  # no issue, no push: the library's copy is 3 days old


def test_a_change_is_reported_only_when_opted_in_and_only_once(ws):
    lines, gh = _watch(ws, change=True)
    assert any("WORDING CHANGED" in ln for ln in lines)
    assert any("turn on vault.report_wording" in ln for ln in lines) and gh.calls == []
    lines, gh = _watch(ws, change=True, report=True)
    assert gh.did("issue", "create") and "opened https://github.com/ris3abh/areao1/issues/99" in lines[-1]
    body = gh.did("issue", "create")[0]
    assert (
        "--repo" in body and "ris3abh/areao1" in body and any("quoted passage not found" in a for a in body)
    )
    lines, gh = _watch(ws, change=True, report=True)
    assert lines[-1] == "standard: wording change already reported" and gh.calls == []
    lines, gh = _watch(ws, change=True, report=True, gh=Gh(open_issue="12"))
    assert gh.calls == []  # same report: still not repeated


def test_a_change_pushes_the_fresh_snapshot_when_sharing_is_on(ws):
    lines, gh = _watch(ws, change=True, share=True)
    puts = [c for c in gh.did("api", "-X", "PUT")]
    assert len(puts) == 2 and puts[0][3].startswith(
        "repos/ris3abh/areao1-community-vault/contents/snapshots/"
    )
    assert puts[1][3] == "repos/ris3abh/areao1-community-vault/contents/manifest.json"
    assert any("pushed a fresh uscis-pm-2-m-4 snapshot" in ln for ln in lines)
    assert not any("kazarian" in c[3] for c in puts)  # Tier 2 isn't shared


def test_an_old_library_copy_is_refreshed_when_sharing_is_on(ws):
    lines, gh = _watch(ws, share=True, lib=Library(captured="2026-08-01T00:00:00+00:00"))
    assert len(gh.did("api", "-X", "PUT")) == 4  # both chapters: file and manifest each
    lines, gh = _watch(ws, share=False, lib=Library(captured="2026-08-01T00:00:00+00:00"))
    assert gh.calls == []  # sharing off: nothing leaves the machine


def test_an_unreadable_live_page_concludes_nothing(ws):
    lines, gh = _watch(ws, report=True, share=True, live_ok=False)
    assert (
        all("couldn't read the live page" in ln and "nothing concluded" in ln for ln in lines)
        and gh.calls == []
    )


def test_vault_watch_runs_the_check(ws, monkeypatch):
    from areao1.vault import watch

    monkeypatch.setattr(watch, "Vault", watch.Vault)
    calls = []
    monkeypatch.setattr(standard, "watch", lambda ws, vault: calls.append(1) or ["standard: x"])

    async def nothing(*a, **k):
        return []

    from areao1.vault import community, signals

    monkeypatch.setattr(signals, "check", nothing)
    monkeypatch.setattr(community, "pull", nothing)
    monkeypatch.setattr(watch.Vault, "sync", nothing)
    lines = watch.run_watch(ws)
    assert calls == [1] and lines[-1] == "standard: x"
