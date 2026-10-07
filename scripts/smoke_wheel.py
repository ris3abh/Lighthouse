"""Smoke-test an installed Area O1 (ADR 0013): the wheel must serve the dashboard with no checkout or Node.

    python scripts/smoke_wheel.py [path/to/areao1]

Uses the ``areao1`` on PATH when no path is given. Creates a throwaway workspace and config directory,
starts ``up`` on a free localhost port, checks /api/health, that / serves the built dashboard and that
/api/onboarding answers, then stops the server. Standard library only, no network beyond 127.0.0.1.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=5) as r:
        return r.status, r.read().decode("utf-8")


def _wait_for_health(base: str, proc: subprocess.Popen, timeout: float = 90) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise SystemExit(f"areao1 up exited early with code {proc.returncode}")
        try:
            status, body = _get(f"{base}/api/health")
            if status == 200:
                return json.loads(body)
        except (urllib.error.URLError, ConnectionError, TimeoutError):
            pass
        time.sleep(0.5)
    raise SystemExit(f"no answer from {base}/api/health after {timeout:.0f}s")


def smoke(exe: str) -> None:
    tmp = Path(tempfile.mkdtemp(prefix="areao1-smoke-"))
    # Keep the user's config untouched: init and up remember the workspace they open.
    env = {**os.environ, "AREAO1_CONFIG_DIR": str(tmp / "config"), "PYTHONUTF8": "1"}
    env.pop("AREAO1_WORKSPACE", None)
    ws = tmp / "case"
    proc = None
    try:
        subprocess.run([exe, "--version"], check=True, env=env, cwd=tmp)
        subprocess.run([exe, "init", str(ws), "--no-git"], check=True, env=env, cwd=tmp)
        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        cmd = [exe, "up", "-w", str(ws), "--port", str(port), "--no-open", "--no-scheduler"]
        proc = subprocess.Popen(cmd, env=env, cwd=tmp)
        health = _wait_for_health(base, proc)
        assert health.get("ok") is True, health
        print(f"health: {health}")

        status, html = _get(f"{base}/")
        assert status == 200, status
        assert '<div id="root">' in html, "/ did not serve the built dashboard"
        assert "<script" in html and "/src/main.tsx" not in html, "/ served the unbuilt index.html"
        print("dashboard: served")

        status, body = _get(f"{base}/api/onboarding")
        assert status == 200 and isinstance(json.loads(body), dict), body[:200]
        print("onboarding: answers")
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        shutil.rmtree(tmp, ignore_errors=True)
    print("smoke test passed")


if __name__ == "__main__":
    exe = sys.argv[1] if len(sys.argv) > 1 else shutil.which("areao1")
    if not exe:
        raise SystemExit("areao1 not found on PATH; pass its path")
    smoke(exe)
