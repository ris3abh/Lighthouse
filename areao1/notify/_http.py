"""Shared HTTP post for webhook channels: short timeout, no redirects (a webhook that redirects is suspect)."""

from __future__ import annotations

from typing import Any

import httpx

from areao1 import __version__
from areao1.notify import NotifyError


def post(
    url: str, *, json: Any = None, content: bytes | None = None, headers: dict[str, str] | None = None
) -> None:
    try:
        resp = httpx.post(url, json=json, content=content, timeout=10.0, follow_redirects=False,
                          headers={"User-Agent": f"areao1/{__version__}", **(headers or {})})  # fmt: skip
    except httpx.HTTPError as exc:
        raise NotifyError(f"network error: {exc}") from exc
    if resp.status_code >= 300:
        raise NotifyError(f"HTTP {resp.status_code}: {resp.text[:120]}")
