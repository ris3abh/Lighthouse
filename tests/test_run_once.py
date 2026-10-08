"""Run once (B3): every action that costs money or sends something does one thing when it arrives twice: a double
click, a retry, another tab. The real routes are checked against the list, and the guard is exercised on a toy app
(each route counting its calls) so every case is visible. Everything here is invented."""

from __future__ import annotations

import threading
import time

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from areao1.server import idempotency
from areao1.server.app import create_app

# Every route that costs a model call, reads the network on your behalf or sends something.
COSTLY = ["/api/letters/{letter_id}/draft", "/api/letters/{letter_id}/send", "/api/outreach", "/api/outreach/{draft_id}/send",
          "/api/opportunities/run", "/api/gmail/sync", "/api/mail/sync", "/api/agent/chat", "/api/agent/runs",
          "/api/agent/missions/{name}/run", "/api/knowledge/sync", "/api/onboarding/lookups/{lookup_id}",
          "/api/metrics/snapshot", "/api/merits/benchmarks"]  # fmt: skip


def test_every_costly_route_is_guarded_and_nothing_else(ws):
    app = create_app(ws, allowed_hosts=["testserver"])
    posts = {r.path for r in app.routes if "POST" in (getattr(r, "methods", None) or ())}
    assert set(COSTLY) <= posts
    sample = {p: p.replace("{letter_id}", "lt_1").replace("{draft_id}", "od_1").replace("{name}", "scout")
              .replace("{lookup_id}", "lk_1") for p in posts}  # fmt: skip
    guarded = {p for p in posts if idempotency.once(sample[p])}
    assert guarded == set(COSTLY), guarded ^ set(COSTLY)
    from pathlib import Path

    web = Path(__file__).resolve().parents[1] / "web" / "src" / "api.ts"
    assert "export const ONCE" in web.read_text()  # the client coalesces the same list


def _toy(delay: float = 0.0):
    calls = {"n": 0}
    app = FastAPI()

    @app.post("/api/agent/chat")
    async def chat(request: Request) -> dict:
        calls["n"] += 1
        if delay:
            import anyio

            await anyio.sleep(delay)
        return {"run": calls["n"], "message": (await request.json())["message"]}

    @app.post("/api/agent/runs/{run_id}/stop")
    async def other() -> dict:
        return {"ok": True}

    app.add_middleware(idempotency.RunOnce)
    return TestClient(app, raise_server_exceptions=False), calls


def test_a_double_click_runs_once_and_both_get_the_answer():
    c, calls = _toy()
    a = c.post("/api/agent/chat", json={"message": "Where do I stand?"})
    b = c.post("/api/agent/chat", json={"message": "Where do I stand?"})
    assert calls["n"] == 1 and a.json() == b.json() == {"run": 1, "message": "Where do I stand?"}
    c.post("/api/agent/chat", json={"message": "Something else"})
    assert calls["n"] == 2  # a different request runs


def test_concurrent_duplicates_are_refused_not_repeated():
    c, calls = _toy(delay=0.3)
    codes: list[int] = []
    threads = [threading.Thread(target=lambda: codes.append(c.post("/api/agent/chat", json={"message": "go"}).status_code))
               for _ in range(4)]  # fmt: skip
    for t in threads:
        t.start()
        time.sleep(0.02)
    for t in threads:
        t.join()
    assert calls["n"] == 1 and sorted(codes) == [200, 409, 409, 409]


def test_doing_it_again_after_another_change_runs_again():
    c, calls = _toy()
    c.post("/api/agent/chat", json={"message": "go"})
    c.post("/api/agent/runs/run_1/stop")  # e.g. Undo send between two approvals
    c.post("/api/agent/chat", json={"message": "go"})
    assert calls["n"] == 2


def test_idempotency_keys_and_errors():
    c, calls = _toy()
    h = {"Idempotency-Key": "k-1"}
    c.post("/api/agent/chat", json={"message": "a"}, headers=h)
    c.post("/api/agent/runs/run_1/stop")
    c.post(
        "/api/agent/chat", json={"message": "a"}, headers=h
    )  # same key: the same click, even after a change
    assert calls["n"] == 1
    c.post("/api/agent/chat", json={"message": "a"}, headers={"Idempotency-Key": "k-2"})
    assert calls["n"] == 2  # a new key after a change is a new action
    bad = c.post("/api/agent/chat", json={})  # an error isn't kept: it can be tried again
    again = c.post("/api/agent/chat", json={})
    assert bad.status_code >= 400 and again.status_code >= 400


def test_the_window_expires(monkeypatch):
    c, calls = _toy()
    monkeypatch.setattr(idempotency, "WINDOW", 0.05)
    c.post("/api/agent/chat", json={"message": "go"})
    time.sleep(0.1)
    c.post("/api/agent/chat", json={"message": "go"})
    assert calls["n"] == 2
