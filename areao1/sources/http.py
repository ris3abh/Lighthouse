"""Polite HTTP for connectors: conditional requests (ETag / Last-Modified), exponential backoff,
a per-source on-disk cache, and an in-run memo so one sync never fetches the same URL twice."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx

from areao1 import __version__
from areao1.core import clock

USER_AGENT = f"areao1/{__version__} (+https://github.com/ris3abh/areao1)"
MAX_WAIT_SECONDS = 60.0


class SourceError(Exception):
    """A connector failed in a way the user should see (bad handle, auth, rate limit)."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class Response:
    def __init__(self, status: int, data: Any, headers: dict[str, str]):
        self.status = status
        self.data = data
        self.headers = headers

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class HttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        kind: str,
        cache_dir: Path | None = None,
        headers: dict[str, str] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 4,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 20.0,
    ):
        self.kind = kind
        self.sleep = sleep
        self.max_retries = max_retries
        self._client = httpx.Client(
            base_url=base_url,
            headers={"User-Agent": USER_AGENT, **(headers or {})},
            timeout=timeout,
            follow_redirects=True,
            transport=transport,
        )
        self._cache_path = cache_dir / "http" / f"{kind}.json" if cache_dir else None
        self._cache: dict[str, dict[str, Any]] | None = None
        self._memo: dict[str, Response] = {}
        self.requests_made = 0

    # -- cache ------------------------------------------------------------------------------

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        if self._cache is None:
            self._cache = {}
            if self._cache_path and self._cache_path.exists():
                try:
                    self._cache = json.loads(self._cache_path.read_text())
                except (OSError, ValueError):
                    self._cache = {}
        return self._cache

    def _store(self, key: str, resp: httpx.Response, data: Any) -> None:
        if not self._cache_path:
            return
        etag, modified = resp.headers.get("etag"), resp.headers.get("last-modified")
        if not etag and not modified:
            return
        cache = self._load_cache()
        cache[key] = {"etag": etag, "last_modified": modified, "data": data, "headers": _keep_headers(resp)}
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(cache))

    # -- requests ---------------------------------------------------------------------------

    def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | list[tuple[str, Any]] | None = None,
        token: str | None = None,
        accept: str | None = None,
        raw: bool = False,
        allow: tuple[int, ...] = (),
    ) -> Response:
        """GET ``path``. Non-2xx statuses in ``allow`` are returned instead of raised."""
        request = self._client.build_request("GET", path, params=params)
        key = f"{'raw:' if raw else ''}{request.url}"
        if key in self._memo:
            return self._memo[key]

        headers: dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        if accept:
            headers["Accept"] = accept
        cached = self._load_cache().get(key)
        if cached:
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]

        resp = self._send(request.url, headers)
        if resp.status_code == 304 and cached:
            out = Response(200, cached["data"], cached.get("headers", {}))
        elif resp.is_success:
            data: Any = resp.text if raw else (resp.json() if resp.content else None)
            self._store(key, resp, data)
            out = Response(resp.status_code, data, _keep_headers(resp))
        elif resp.status_code in allow:
            out = Response(resp.status_code, None, _keep_headers(resp))
        else:
            raise SourceError(_error_message(self.kind, resp), resp.status_code)
        self._memo[key] = out
        return out

    def _send(self, url: httpx.URL, headers: dict[str, str]) -> httpx.Response:
        attempt = 0
        while True:
            self.requests_made += 1
            try:
                resp = self._client.get(url, headers=headers)
            except httpx.TransportError as exc:
                if attempt >= self.max_retries:
                    raise SourceError(f"{self.kind}: network error: {exc}") from exc
                self.sleep(min(MAX_WAIT_SECONDS, 2**attempt))
                attempt += 1
                continue
            wait = _retry_after(resp, attempt)
            if wait is None or attempt >= self.max_retries:
                return resp
            if wait > MAX_WAIT_SECONDS:
                raise SourceError(
                    f"{self.kind}: rate limited for another {int(wait)}s; try again later", resp.status_code
                )
            self.sleep(wait)
            attempt += 1

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _keep_headers(resp: httpx.Response) -> dict[str, str]:
    return {k: v for k, v in resp.headers.items() if k.lower() in ("link", "x-total-count")}


def _retry_after(resp: httpx.Response, attempt: int) -> float | None:
    """Seconds to wait before retrying, or None if the response shouldn't be retried."""
    status = resp.status_code
    rate_limited = status == 429 or (status == 403 and resp.headers.get("x-ratelimit-remaining") == "0")
    if not rate_limited and status < 500:
        return None
    if resp.headers.get("retry-after", "").isdigit():
        return float(resp.headers["retry-after"])
    reset = resp.headers.get("x-ratelimit-reset")
    if rate_limited and reset and reset.isdigit():
        return max(1.0, int(reset) - clock.utcnow().timestamp())
    return float(min(MAX_WAIT_SECONDS, 2**attempt))


def _error_message(kind: str, resp: httpx.Response) -> str:
    detail = ""
    try:
        body = resp.json()
        if isinstance(body, dict):
            detail = body.get("message") or body.get("error") or ""
    except ValueError:
        pass
    hint = {401: "token missing or invalid", 403: "forbidden (token scope?)", 404: "not found (or private)"}
    msg = f"{kind}: HTTP {resp.status_code} for {resp.request.url.path}"
    extra = detail or hint.get(resp.status_code, "")
    return f"{msg}: {extra}" if extra else msg
