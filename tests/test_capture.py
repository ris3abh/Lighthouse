"""The capture extension (ADR 0011 §2): pairing with a one-time code, a token kept only as a hash, captures only for
listed URLs, and an extension that can't browse on its own or talk to anything but the local app."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_vault import fixture

from areao1.server.app import create_app
from areao1.vault import capture
from areao1.vault.store import Vault, load_manifest

W = {"X-AreaO1": "1"}
EXT = Path(__file__).parents[1] / "areao1" / "extension"


@pytest.fixture
def c(ws):
    with TestClient(create_app(ws, allowed_hosts=["testserver"])) as client:
        yield client


def _pair(c):
    code = c.post("/api/vault/capture/code", headers=W).json()["code"]
    return c.post("/api/vault/capture/pair", headers=W, json={"code": code}).json()


def test_pairing_is_one_time_and_only_a_hash_is_kept(c, ws):
    code = c.post("/api/vault/capture/code", headers=W).json()["code"]
    assert re.fullmatch(r"[0-9A-F]{4}-[0-9A-F]{4}", code)
    out = c.post("/api/vault/capture/pair", headers=W, json={"code": code.lower()}).json()
    token = out["token"]
    assert len(token) > 30 and any(s["id"] == "uscis-i-129" for s in out["sources"])
    assert c.post("/api/vault/capture/pair", headers=W, json={"code": code}).status_code == 403  # used once
    assert c.post("/api/vault/capture/pair", headers=W, json={"code": "0000-0000"}).status_code == 403
    for f in ws.root.rglob("*"):
        if f.is_file():
            assert token.encode() not in f.read_bytes(), f  # never stored as is
    assert c.get("/api/vault/capture/status").json()["paired"] is True
    c.delete("/api/vault/capture", headers=W)
    assert (
        c.get("/api/vault/capture/sources", headers={"Authorization": f"Bearer {token}"}).status_code == 401
    )


def test_the_watch_list_is_the_vault_sources(c, ws):
    token = _pair(c)["token"]
    srcs = c.get("/api/vault/capture/sources", headers={"Authorization": f"Bearer {token}"}).json()["sources"]
    by_id = {s["id"]: s for s in srcs}
    assert "uscis.gov/i-129" in by_id["uscis-i-129"]["keys"] and by_id["uscis-i-129"]["manual"] is True
    assert "federal-register-uscis" not in by_id  # an API feed isn't a page to visit
    assert len(srcs) == len([s for s in load_manifest().sources if s.enabled and "/api/" not in s.url])
    assert c.get("/api/vault/capture/sources").status_code == 401
    assert c.get("/api/vault/capture/sources", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_a_visited_listed_page_is_imported_and_nothing_else(c, ws):
    auth = {"Authorization": f"Bearer {_pair(c)['token']}", **W}
    html = fixture("uscis-i-129.html").decode()
    r = c.post("/api/vault/capture/page", headers=auth,
               json={"url": "https://www.uscis.gov/i-129/#edition", "title": "I-129 | USCIS", "html": html})  # fmt: skip
    assert r.status_code == 200 and r.json()["source_id"] == "uscis-i-129" and r.json()["status"] == "new"
    assert any(e.origin == "manual" and e.source_id == "uscis-i-129" for e in Vault(ws).log())
    other = c.post("/api/vault/capture/page", headers=auth,
                   json={"url": "https://www.uscis.gov/news", "title": "News", "html": html})  # fmt: skip
    assert other.status_code == 404 and "isn't in your vault" in other.json()["detail"]
    nope = c.post(
        "/api/vault/capture/page", headers=W, json={"url": "https://www.uscis.gov/i-129", "html": html}
    )
    assert nope.status_code == 401


@pytest.mark.parametrize(
    "url",
    ["https://www.uscis.gov/i-129/", "HTTPS://WWW.USCIS.GOV/I-129#x", "https://travel.state.gov/a/b.html?x=1",
     "http://127.0.0.1:7911/uscis-o1/", "ftp://uscis.gov/x", "not a url"],
)  # fmt: skip
def test_the_extension_compares_urls_exactly_like_the_app(url):
    node = shutil.which("node")
    if node is None:
        pytest.skip("node isn't installed")
    script = f"import('{(EXT / 'shared.js').as_uri()}').then(m => console.log(JSON.stringify(m.urlKey({json.dumps(url)}))))"
    out = subprocess.run(
        [node, "--input-type=module", "-e", script], capture_output=True, text=True, check=True
    )
    assert json.loads(out.stdout) == capture.key(url)


def test_the_extension_only_reads_the_tab_youre_on_and_only_talks_to_the_local_app():
    manifest = json.loads((EXT / "manifest.json").read_text())
    assert manifest["manifest_version"] == 3 and set(manifest["permissions"]) == {"storage", "scripting"}
    m = load_manifest()
    allowed = {f"*://*.{d}/*" for d in [*m.tier1_domains, *m.tier2_domains]} | {"http://127.0.0.1/*"}
    assert set(manifest["host_permissions"]) <= allowed  # official domains and this computer, nothing else
    code = "\n".join((EXT / f).read_text() for f in ("background.js", "popup.js", "shared.js"))
    for never in (
        "tabs.create",
        "tabs.update",
        "tabs.reload",
        "windows.create",
        "XMLHttpRequest",
        "navigate(",
    ):
        assert never not in code, never  # it never browses on its own
    for call in re.findall(r"fetch\(([^,)]+)", code):
        assert call.strip().startswith("`${localApp(") or call.strip().startswith("`${app}"), call
    assert "localApp" in (EXT / "shared.js").read_text() and "127.0.0.1" in (EXT / "shared.js").read_text()
