"""Shared helpers for the browser suite (see conftest.py)."""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.environ.get("AREAO1_QA_OUT", ROOT / "tests" / "e2e" / ".out"))
AXE = ROOT / "web" / "node_modules" / "axe-core" / "axe.min.js"
CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
SIZES = {"laptop": {"width": 1440, "height": 900}, "phone": {"width": 390, "height": 844}}
ROUTES = ["overview", "inbox", "evidence", "metrics", "pipeline", "letters", "contacts", "contacts?view=mail",
          "calendar", "agent", "memory", "knowledge", "sources", "settings", "not-a-page"]  # fmt: skip
ERROR_KINDS = {"pageerror", "console_error", "http_5xx", "broken_link", "axe", "overflow", "flow"}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class Server:
    """One scenario on its own port, in its own process, on a fresh throwaway workspace."""

    def __init__(self, scenario: str):
        self.scenario = scenario
        self.dir = Path(tempfile.mkdtemp(prefix="areao1-qa-"))
        self.port = _free_port()
        self.log = self.dir / "server.log"
        self._log = self.log.open("w")
        self.proc = subprocess.Popen([sys.executable, str(ROOT / "tests" / "e2e" / "serve.py"), scenario,
                                      str(self.dir / "ws"), str(self.port)],
                                     stdin=subprocess.PIPE, stdout=self._log, stderr=subprocess.STDOUT, text=True)  # fmt: skip
        deadline = time.time() + 180
        while time.time() < deadline and "READY" not in self.log.read_text():
            if self.proc.poll() is not None:
                raise RuntimeError(f"{scenario} exited: {self.log.read_text()[-2000:]}")
            time.sleep(0.1)
        if "READY" not in self.log.read_text():
            self.close()
            raise RuntimeError(f"{scenario} didn't start: {self.log.read_text()[-2000:]}")
        self.base = f"http://127.0.0.1:{self.port}"
        self.ws = self.dir / "ws"

    def tail(self, n: int = 3000) -> str:
        return self.log.read_text(errors="ignore")[-n:] if self.log.exists() else ""

    def close(self) -> None:
        if self.proc.poll() is None:
            try:
                if self.proc.stdin:
                    self.proc.stdin.close()
                self.proc.terminate()
                self.proc.wait(10)
            except Exception:
                self.proc.kill()
        shutil.rmtree(self.dir, ignore_errors=True)


INIT = """
try { localStorage.setItem('lh-chat-open', '0'); localStorage.setItem('lh-tour-done', '1'); localStorage.setItem('lh-theme', 'system');
      if (window.__qaTheme) localStorage.setItem('lh-theme', window.__qaTheme); } catch (e) {}
window.__qa = { mut: 0 };
new MutationObserver((m) => { window.__qa.mut += m.length; })
  .observe(document, { subtree: true, childList: true, attributes: true, characterData: true });
"""


class QA:
    """Collects what a page did: errors, failed requests, timings; and the findings a test records."""

    def __init__(self, test: str):
        self.test = test
        self.findings: list[dict[str, Any]] = []
        self.requests = 0
        self.where = ""
        self.coverage: dict[str, Any] = {}

    def attach(self, page: Any, label: str = "") -> Any:
        self.where = label

        def on_console(m: Any) -> None:
            if m.type == "error" and "favicon" not in m.text:
                self.add("console_error", m.text[:500])

        page.on("pageerror", lambda e: self.add("pageerror", str(e)[:800]))
        page.on("console", on_console)
        page.on("request", lambda r: setattr(self, "requests", self.requests + 1))
        page.on(
            "requestfailed",
            lambda r: (
                self.add("request_failed", f"{r.method} {r.url} {r.failure}") if "/api/" in r.url else None
            ),
        )

        def on_response(r: Any) -> None:
            if r.status >= 500:
                self.add("http_5xx", f"{r.request.method} {r.url} -> {r.status}")
            elif r.status >= 400 and "/api/" in r.url:
                self.add("http_4xx", f"{r.request.method} {r.url} -> {r.status}")

        page.on("response", on_response)
        page.on("dialog", lambda d: d.accept())
        return page

    def add(self, kind: str, message: str, **detail: Any) -> None:
        self.findings.append({"test": self.test, "kind": kind, "where": self.where, "message": message,
                              "error": kind in ERROR_KINDS, **detail})  # fmt: skip

    def shot(self, page: Any, name: str) -> str:
        path = OUT / "shots" / f"{self.test}-{name}.png".replace("/", "_").replace("?", "_")
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(path))
        except Exception:
            return ""
        return str(path.relative_to(OUT))

    def errors(self) -> list[dict[str, Any]]:
        return [f for f in self.findings if f["error"]]


def new_page(browser: Any, qa: QA, *, theme: str = "light", size: str = "laptop", label: str = "") -> Any:
    ctx = browser.new_context(viewport=SIZES[size], color_scheme=theme, reduced_motion="reduce",
                              is_mobile=size == "phone", has_touch=size == "phone", accept_downloads=True)  # fmt: skip
    ctx.add_init_script(INIT)
    page = ctx.new_page()
    qa.attach(page, label)
    return page


def open_route(page: Any, base: str, route: str, qa: QA | None = None) -> float:
    """Go to a route and wait until it settles. Returns seconds until the page shows content."""
    t0 = time.time()
    page.goto(f"{base}/#/{route}", wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        if qa:
            qa.add("slow", f"#/{route} didn't settle within 10s")
    page.wait_for_function("document.querySelector('main, .lh-content') !== null", timeout=10000)
    page.wait_for_timeout(250)
    return time.time() - t0


def axe(page: Any) -> list[dict[str, Any]]:
    page.add_script_tag(content=AXE.read_text(encoding="utf-8"))
    res = page.evaluate("async () => (await axe.run(document, {resultTypes: ['violations']})).violations")
    return [{"id": v["id"], "impact": v["impact"], "help": v["help"], "nodes": len(v["nodes"]),
             "targets": [n["target"] for n in v["nodes"][:5]]} for v in res]  # fmt: skip


def overflow(page: Any) -> int:
    return page.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
