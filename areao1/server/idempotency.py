"""Run once (B3): requests that cost money or send something (letter drafts, sends, missions, chat, lookups, mail
refreshes, the vault sync) do one thing however many times they arrive.

A request with an ``Idempotency-Key`` header gets the first response for that key for ten minutes. Without one,
the same method, path and body within ``WINDOW`` seconds counts as the same request (a double click, a retry from
another tab) as long as nothing else was written in between: any other write (an Undo send, an edit) clears
those, so doing something again after a change runs again. A duplicate that arrives while the first is still running is answered at once with 409 (it never
runs, and nothing waits on it); one that arrives after gets the first response again. Error responses (4xx / 5xx)
aren't kept, so a failed request can be tried again. Keep ONCE in step with
web/src/api.ts."""

from __future__ import annotations

import hashlib
import json
import re
import threading
import time
from typing import Any

ONCE = [re.compile(p) for p in (
    r"^/api/letters/[^/]+/(draft|send)$", r"^/api/outreach(/[^/]+/send)?$", r"^/api/opportunities/run$",
    r"^/api/(gmail|mail)/sync$", r"^/api/agent/(chat|runs|missions/[^/]+/run)$", r"^/api/knowledge/sync$",
    r"^/api/onboarding/lookups/[^/]+$", r"^/api/metrics/snapshot$",
)]  # fmt: skip
WINDOW = 10.0  # seconds a body-identical request counts as the same one
KEYED = 600.0  # seconds a keyed response is kept


def once(path: str) -> bool:
    return any(p.match(path) for p in ONCE)


BUSY = json.dumps(
    {"detail": "Already running: this is the same request again, so it was not repeated."}
).encode()


class RunOnce:
    """Pure ASGI middleware (the body has to be read before the app sees it, then replayed)."""

    def __init__(self, app: Any):
        self.app = app
        self.done: dict[str, tuple[float, list[dict[str, Any]]]] = {}
        self.running: set[str] = set()
        self.guard = (
            threading.Lock()
        )  # check-and-claim is atomic even across event loops (the test client's threads)

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope["type"] != "http" or scope["method"] in ("GET", "HEAD", "OPTIONS"):
            await self.app(scope, receive, send)
            return
        if scope["method"] != "POST" or not once(scope["path"]):
            with self.guard:  # another write: a body-identical repeat after it is a new request
                self.done = {k: v for k, v in self.done.items() if k.startswith("k:")}
            await self.app(scope, receive, send)
            return
        chunks = []
        while True:
            msg = await receive()
            chunks.append(msg.get("body", b""))
            if not msg.get("more_body"):
                break
        body = b"".join(chunks)
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
        given = headers.get("idempotency-key")
        same = "b:" + hashlib.sha256(scope["path"].encode() + b"\0" + body).hexdigest()
        keys = [same, *(["k:" + given] if given else [])]  # the same key, or the same request: either one
        with self.guard:
            now = time.monotonic()
            self.done = {k: v for k, v in self.done.items() if v[0] > now}
            hit = next((self.done[k] for k in keys if k in self.done), None)
            busy = hit is None and any(k in self.running for k in keys)
            if hit is None and not busy:
                self.running.update(keys)
        if hit:
            for m in hit[1]:
                await send(m)
            return
        if busy:
            await send({"type": "http.response.start", "status": 409,
                        "headers": [(b"content-type", b"application/json"), (b"content-length", str(len(BUSY)).encode())]})  # fmt: skip
            await send({"type": "http.response.body", "body": BUSY})
            return
        sent: list[dict[str, Any]] = []

        async def replay_body() -> dict[str, Any]:
            return {"type": "http.request", "body": body, "more_body": False}

        async def capture(message: dict[str, Any]) -> None:
            sent.append(message)
            await send(message)

        try:
            await self.app(scope, replay_body, capture)
        finally:
            start = next((m for m in sent if m["type"] == "http.response.start"), None)
            with self.guard:
                self.running.difference_update(keys)
                if start and start["status"] < 400:
                    for k in keys:
                        self.done[k] = (time.monotonic() + (KEYED if k.startswith("k:") else WINDOW), sent)
