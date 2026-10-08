"""Zero-click capture (ADR 0011 §2): the browser extension saves the vault's official pages when the person visits
them. The app pairs with it once (a one-time code shown in the app, exchanged for a capture token whose hash is kept
in the workspace cache), tells it which pages to watch, and imports what it sends, only for listed URLs."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from typing import Any
from urllib.parse import urlparse

from areao1.core.models import utcnow
from areao1.core.workspace import Workspace
from areao1.vault.store import Vault

CODE_TTL = 600  # a pairing code is good for ten minutes, once
_codes: dict[str, float] = {}


def new_code() -> str:
    """A one-time pairing code (shown in Settings > Knowledge, typed into the extension)."""
    now = time.time()
    for c, at in list(_codes.items()):
        if now - at > CODE_TTL:
            _codes.pop(c, None)
    code = "-".join(secrets.token_hex(2).upper() for _ in range(2))
    _codes[code] = now
    return code


def _path(ws: Workspace) -> Any:
    return ws.cache_dir / "vault" / "capture.json"


def _sha(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def pair(ws: Workspace, code: str) -> str:
    """Exchange a pairing code for a capture token (returned once; only its hash is kept). Pairing again replaces the
    previous extension."""
    code = code.strip().upper()
    at = _codes.pop(code, None)
    if at is None or time.time() - at > CODE_TTL:
        raise PermissionError("That pairing code is wrong or expired. Get a new one in Settings > Knowledge.")
    token = secrets.token_urlsafe(32)
    p = _path(ws)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps({"token_sha256": _sha(token), "paired_at": utcnow().isoformat()}), encoding="utf-8"
    )
    return token


def status(ws: Workspace) -> dict[str, Any]:
    try:
        data = json.loads(_path(ws).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"paired": False, "paired_at": None}
    return {"paired": bool(data.get("token_sha256")), "paired_at": data.get("paired_at")}


def unpair(ws: Workspace) -> None:
    _path(ws).unlink(missing_ok=True)


def authorized(ws: Workspace, header: str | None) -> bool:
    if not header or not header.startswith("Bearer "):
        return False
    try:
        data = json.loads(_path(ws).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return secrets.compare_digest(data.get("token_sha256", ""), _sha(header.removeprefix("Bearer ").strip()))


def key(url: str) -> str | None:
    """A URL as the extension compares it: host without www, path without trailing slash, the query; no fragment,
    case-insensitive. The extension's background.js does exactly this."""
    try:
        u = urlparse(url)
    except ValueError:
        return None
    if u.scheme not in ("http", "https") or not u.hostname:
        return None
    host = u.hostname.lower().removeprefix("www.")
    port = f":{u.port}" if u.port else ""
    path = u.path.rstrip("/")
    return f"{host}{port}{path}{'?' + u.query if u.query else ''}".lower()


def watched(ws: Workspace) -> list[dict[str, Any]]:
    """The pages to capture: every enabled source (not the agent's findings, not API feeds), with its keys."""
    vault = Vault(ws)
    out = []
    for s in vault.manifest.sources:
        if not s.enabled or s.finding or "/api/" in s.url:
            continue
        urls = {vault.link(s), vault.state_url(s)} | ({s.url} if "{" not in s.url else set())
        keys = sorted({k for u in urls if (k := key(u))})
        if keys:
            out.append({"id": s.id, "title": s.title, "manual": s.manual, "keys": keys})
    return out


def capture(ws: Workspace, url: str, title: str, html: str) -> dict[str, Any]:
    """Import a page the extension saved, if its URL is one of the watched pages."""
    k = key(url)
    hit = next((w for w in watched(ws) if k and k in w["keys"]), None)
    if hit is None:
        raise LookupError("That page isn't in your vault's source list; nothing was saved.")
    if not html.strip():
        raise ValueError("The page was empty.")
    result = Vault(ws).import_file(hit["id"], html.encode("utf-8"), f"{(title or hit['title'])[:80]}.html")
    return {"source_id": hit["id"], "status": result.status, "sha256": result.sha256}
