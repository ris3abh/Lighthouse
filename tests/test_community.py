"""The community snapshot library (ADR 0011 §3): community-vault/ validates; installs pull newer, hash-verified
snapshots of blocked official pages; sharing is opt-in and local. HTTP is respx; nothing leaves."""

from __future__ import annotations

import importlib.util
import json
import shutil
from datetime import datetime
from pathlib import Path

import anyio
import pytest
from fastapi.testclient import TestClient
from test_capture import _pair
from test_vault import fixture

from areao1.server.app import create_app
from areao1.vault import community
from areao1.vault.store import Vault

LIB = Path(__file__).parents[1] / "community-vault"
BASE = "https://raw.githubusercontent.com/ris3abh/areao1-community-vault/main"
W = {"X-AreaO1": "1"}


def _validate():
    spec = importlib.util.spec_from_file_location("community_validate", LIB / "validate.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_library_validates_and_holds_only_public_domain_government_pages():
    assert _validate().problems(LIB) == []
    manifest = json.loads((LIB / "manifest.json").read_text())
    assert manifest["snapshots"] and all(
        e["license"] == "public-domain-us-gov" for e in manifest["snapshots"]
    )
    assert (LIB / ".github" / "workflows" / "validate.yml").is_file() and "17 U.S.C." in (
        LIB / "README.md"
    ).read_text()


@pytest.mark.parametrize(
    ("mutate", "says"),
    [
        (lambda m, d: m["snapshots"][0].update(url="https://immigration-blog.example/page"), "official U.S. government"),
        (lambda m, d: m["snapshots"][0].update(license="CC-BY"), "license must be"),
        (lambda m, d: (d / m["snapshots"][0]["file"]).write_bytes(b"tampered"), "doesn't match its sha256"),
        (lambda m, d: (d / "snapshots" / ("0" * 64 + ".html")).write_bytes(b"x"), "not in manifest.json"),
        (lambda m, d: m["snapshots"].append(dict(m["snapshots"][0])), "duplicate"),
        (lambda m, d: m["snapshots"][0].pop("sha256"), "missing"),
    ],
)  # fmt: skip
def test_the_validator_catches_bad_entries(tmp_path, mutate, says):
    lib = tmp_path / "lib"
    shutil.copytree(LIB, lib)
    m = json.loads((lib / "manifest.json").read_text())
    mutate(m, lib)
    (lib / "manifest.json").write_text(json.dumps(m))
    assert any(says in p for p in _validate().problems(lib)), _validate().problems(lib)


def _serve(http_mock, entries, files):
    http_mock.get(f"{BASE}/manifest.json").respond(json={"version": 1, "snapshots": entries})
    for name, body in files.items():
        http_mock.get(f"{BASE}/{name}").respond(content=body)


def _entry(
    sid="uscis-i-129", data=None, captured="2026-10-06T12:00:00+00:00", url="https://www.uscis.gov/i-129"
):
    import hashlib

    data = data if data is not None else fixture("uscis-i-129.html")
    sha = hashlib.sha256(data).hexdigest()
    return {"source_id": sid, "url": url, "captured_at": captured, "sha256": sha, "file": f"snapshots/{sha}.html",
            "license": "public-domain-us-gov"}, {f"snapshots/{sha}.html": data}  # fmt: skip


def test_installs_pull_a_newer_verified_snapshot_for_a_blocked_page(ws, http_mock):
    e, files = _entry()
    _serve(http_mock, [e], files)
    vault = Vault(ws)
    assert anyio.run(community.pull, ws, vault, None) == ["community library: 1 newer snapshot imported"]
    st = vault.state()["uscis-i-129"]
    assert datetime.fromisoformat(st["checked_at"]) == datetime.fromisoformat(
        e["captured_at"]
    )  # as old as the copy
    assert any(x.origin == "community" for x in vault.log())
    assert anyio.run(community.pull, ws, vault, None) == []  # nothing newer: nothing imported


def test_a_snapshot_that_fails_its_hash_or_isnt_newer_or_isnt_blocked_is_ignored(ws, http_mock):
    vault = Vault(ws)
    vault.import_file("uscis-g-1055", fixture("uscis-g-1055-fees.html"), "fees.html")  # ours: now
    bad, _ = _entry()
    older, older_files = _entry(
        "uscis-g-1055", fixture("uscis-g-1055-fees.html"), url="https://www.uscis.gov/g-1055"
    )
    ecfr, ecfr_files = _entry(
        "ecfr-8cfr-106-2", b"<html>x</html>", url="https://www.ecfr.gov/x"
    )  # not a manual source
    _serve(http_mock, [bad, older, ecfr], {bad["file"]: b"tampered", **older_files, **ecfr_files})
    lines = anyio.run(community.pull, ws, vault, None)
    assert lines == ["community snapshot for uscis-i-129 failed its hash check; ignored"]
    assert "uscis-i-129" not in vault.state()
    assert not any(x.origin == "community" for x in vault.log())


def test_pulling_can_be_turned_off_and_an_unreachable_library_is_said(ws, http_mock):
    http_mock.get(f"{BASE}/manifest.json").respond(503)
    assert anyio.run(community.pull, ws, Vault(ws), None)[0].startswith("community library unreachable")
    cfg = ws.config()
    cfg.vault.community = False
    ws.save_config(cfg)
    assert anyio.run(community.pull, ws, Vault(ws), None) == []


def test_sharing_is_opt_in_local_and_only_for_tier1_pages(ws):
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as c:
        auth = {"Authorization": f"Bearer {_pair(c)['token']}", **W}
        html = fixture("uscis-i-129.html").decode()
        r = c.post(
            "/api/vault/capture/page", headers=auth, json={"url": "https://www.uscis.gov/i-129", "html": html}
        )
        assert r.json()["shared"] is False and community.shared(ws) == []  # not opted in
        r = c.post("/api/vault/capture/page", headers=auth,
                   json={"url": "https://www.uscis.gov/i-129", "html": html, "share": True})  # fmt: skip
        assert r.json()["shared"] is True
    [entry] = community.shared(ws)
    assert entry["license"] == "public-domain-us-gov" and community.entry_problems(entry, ["uscis.gov"]) == []
    assert (community.outbox(ws) / entry["file"]).read_bytes() == community.sanitize(html.encode())


def test_the_watch_pulls_before_it_decides_what_to_remind(ws, monkeypatch):
    calls = []

    async def fake_pull(ws_, vault, client=None):
        calls.append("pull")
        return []

    async def fake_check(vault, client=None):
        calls.append("signals")
        return []

    from areao1.vault import signals, watch

    monkeypatch.setattr(community, "pull", fake_pull)
    monkeypatch.setattr(signals, "check", fake_check)
    monkeypatch.setattr(Vault, "sync", lambda self, **k: _noop())
    watch.run_watch(ws)
    assert calls == ["signals", "pull"]


async def _noop():
    return []


def test_per_visit_tokens_are_emptied_before_sharing_and_the_library_rejects_them(tmp_path):
    page = (b'<form data-feedback-token="visit-value"><input type="hidden" name="form_build_id" '
            b'value="form-xyz"><script nonce="n0nc3">x()</script></form>')  # fmt: skip
    clean = community.sanitize(page)
    assert b"visit-value" not in clean and b"form-xyz" not in clean and b"n0nc3" not in clean
    assert b'data-feedback-token=""' in clean and b'name="form_build_id" value=""' in clean
    lib = tmp_path / "lib"
    shutil.copytree(LIB, lib)
    m = json.loads((lib / "manifest.json").read_text())
    import hashlib

    sha = hashlib.sha256(page).hexdigest()
    (lib / "snapshots" / f"{sha}.html").write_bytes(page)
    m["snapshots"].append({**m["snapshots"][0], "sha256": sha, "file": f"snapshots/{sha}.html"})
    (lib / "manifest.json").write_text(json.dumps(m))
    assert any("per-visit tokens" in p for p in _validate().problems(lib))
