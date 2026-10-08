"""The capture extension in a real Chrome (ADR 0011 §2), driven by extension-e2e/e2e.mjs: it pairs with a running
Area O1, ignores a page the vault doesn't list, and saves one it does. Runs only with AREAO1_E2E=1, node, Chrome and
`npm install` in extension-e2e/; everything is on 127.0.0.1."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
CHROME = os.environ.get("AREAO1_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
PAGE = ("<html><head><title>Example official page</title></head><body><h1>Form X-1 instructions</h1>"
        + "<p>Edition 10/01/26. File Form X-1 with the filing fee shown on the fee schedule.</p>" * 20
        + "</body></html>")  # fmt: skip

pytestmark = pytest.mark.skipif(
    not (os.environ.get("AREAO1_E2E") and shutil.which("node") and Path(CHROME).exists()
         and (ROOT / "extension-e2e" / "node_modules" / "puppeteer-core").exists()),
    reason="set AREAO1_E2E=1 with node, Chrome and extension-e2e/node_modules",
)  # fmt: skip


def _port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def test_the_extension_saves_only_listed_pages(ws, monkeypatch):
    import uvicorn

    from areao1.server.app import create_app
    from areao1.vault.store import Vault

    site_port, app_port = _port(), _port()

    class Site(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    site = ThreadingHTTPServer(("127.0.0.1", site_port), Site)
    threading.Thread(target=site.serve_forever, daemon=True).start()
    listed = f"http://127.0.0.1:{site_port}/forms/x-1"
    (ws.root / "vault").mkdir(exist_ok=True)
    (ws.root / "vault" / "sources.yaml").write_text(
        f"sources:\n  - id: example-form-x1\n    title: Form X-1 (test page)\n    url: {listed}\n    tier: 3\n"
        "    kind: form\n    manual: true\n"
    )
    server = uvicorn.Server(
        uvicorn.Config(create_app(ws), host="127.0.0.1", port=app_port, log_level="warning")
    )
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    try:
        out = subprocess.run(["node", "e2e.mjs", f"http://127.0.0.1:{app_port}", listed + "/",
                              f"http://127.0.0.1:{site_port}/news", str(ROOT / "areao1" / "extension"), CHROME],
                             cwd=ROOT / "extension-e2e", capture_output=True, text=True, timeout=120)  # fmt: skip
        assert out.returncode == 0, out.stderr
        report = json.loads(out.stdout.strip().splitlines()[-1])
    finally:
        server.should_exit = True
        site.shutdown()
    assert report["paired"].startswith("Paired. Watching")
    assert report["last"].startswith("Saved: Form X-1 (test page)")
    log = [e for e in Vault(ws).log() if e.source_id == "example-form-x1"]
    assert len(log) == 1 and log[0].origin == "manual"  # the listed page once; the unlisted one never
