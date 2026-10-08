"""The community snapshot library (ADR 0011 §3): hash-verified snapshots of public-domain U.S. government pages that
block automated reading. vault-watch pulls the library's manifest and imports a snapshot for a manual source only
when it's newer than the local copy and its SHA-256 matches. Sharing is opt-in and local: captures of Tier 1 pages are
written to an outbox with the exact manifest entry to contribute."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

import httpx

from areao1.core.models import utcnow
from areao1.core.workspace import Workspace

MAX_BYTES = 5 * 1024 * 1024
LICENSE = "public-domain-us-gov"  # 17 U.S.C. § 105
FILE = re.compile(r"^snapshots/[0-9a-f]{64}\.(html|pdf|txt)$")
# Per-visit values a page carries (form, feedback and CSRF tokens, nonces): emptied before sharing, since they can be
# tied to whoever captured it. The library's validate.py rejects snapshots that still have them.
VOLATILE = re.compile(
    rb'((?:data-feedback-token|data-form-build-id|nonce|data-nonce)=")[^"]*(")'
    rb'|(name="(?:form_build_id|form_token|csrf_token|_token|authenticity_token|csrfmiddlewaretoken)"[^>]*?value=")[^"]*(")',
    re.I,
)


def sanitize(content: bytes) -> bytes:
    return VOLATILE.sub(lambda m: (m.group(1) or m.group(3)) + (m.group(2) or m.group(4)), content)


def entry_problems(e: Any, official: list[str]) -> list[str]:
    """What's wrong with one manifest entry (the library's CI runs the same checks)."""
    from urllib.parse import urlparse

    out = []
    if not isinstance(e, dict):
        return ["not an object"]
    for k in ("source_id", "url", "captured_at", "sha256", "file", "license"):
        if not e.get(k):
            out.append(f"missing {k}")
    if out:
        return out
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,79}", e["source_id"]):
        out.append("bad source_id")
    host = (urlparse(e["url"]).hostname or "").lower()
    if urlparse(e["url"]).scheme != "https" or not (host.endswith(".gov") or host == "gov"
                                                     or any(host == d or host.endswith("." + d) for d in official)):  # fmt: skip
        out.append(f"{host or e['url']} isn't an official U.S. government domain")
    if not re.fullmatch(r"[0-9a-f]{64}", e["sha256"]):
        out.append("bad sha256")
    if not FILE.match(e["file"]) or e["file"].split("/")[1].split(".")[0] != e["sha256"]:
        out.append("file must be snapshots/<sha256>.<html|pdf|txt>")
    if e["license"] != LICENSE:
        out.append(f"license must be {LICENSE}")
    try:
        datetime.fromisoformat(e["captured_at"])
    except (TypeError, ValueError):
        out.append("bad captured_at")
    return out


async def pull(ws: Workspace, vault: Any, client: httpx.AsyncClient | None = None) -> list[str]:
    """Import newer, hash-verified snapshots for manual sources. Returns report lines."""
    cfg = ws.config().vault
    if not cfg.community:
        return []
    base = cfg.community_url.rstrip("/")
    own = client is None
    client = client or httpx.AsyncClient(timeout=30, headers={"User-Agent": "AreaO1 vault"})
    lines: list[str] = []
    try:
        try:
            r = await client.get(f"{base}/manifest.json")
            r.raise_for_status()
            entries = r.json().get("snapshots") or []
        except (httpx.HTTPError, ValueError) as exc:
            return [f"community library unreachable ({type(exc).__name__})"]
        state = vault.state()
        official = [*vault.manifest.tier1_domains, *vault.manifest.tier2_domains]
        newest: dict[str, dict[str, Any]] = {}
        for e in entries:
            if entry_problems(e, official):
                continue
            src = vault.manifest.source(e["source_id"])
            if src is None or not src.manual or not src.enabled:
                continue
            if e["source_id"] not in newest or e["captured_at"] > newest[e["source_id"]]["captured_at"]:
                newest[e["source_id"]] = e
        imported = 0
        for sid, e in newest.items():
            captured = datetime.fromisoformat(e["captured_at"])
            local = (state.get(sid) or {}).get("checked_at")
            if local and datetime.fromisoformat(local) >= captured:
                continue  # ours is as new
            try:
                f = await client.get(f"{base}/{e['file']}")
                f.raise_for_status()
            except httpx.HTTPError:
                continue
            if len(f.content) > MAX_BYTES or hashlib.sha256(f.content).hexdigest() != e["sha256"]:
                lines.append(f"community snapshot for {sid} failed its hash check; ignored")
                continue
            ext = e["file"].rsplit(".", 1)[-1]
            try:
                vault.import_file(sid, f.content, f"{sid}.{ext}", checked_at=captured, origin="community")
            except ValueError as exc:
                lines.append(f"community snapshot for {sid} unusable ({exc})")
                continue
            imported += 1
        if imported:
            lines.append(
                f"community library: {imported} newer snapshot{'s' if imported != 1 else ''} imported"
            )
    finally:
        if own:
            await client.aclose()
    return lines


def outbox(ws: Workspace) -> Any:
    return ws.cache_dir / "community-outbox"


def stage_share(
    ws: Workspace, vault: Any, source_id: str, url: str, content: bytes, ext: str = "html"
) -> dict[str, Any] | None:
    """Opt-in sharing: a capture of a Tier 1 page goes to the local outbox as the exact file and manifest entry to
    contribute. Nothing is uploaded. Returns the entry, or None when it isn't shareable."""
    src = vault.manifest.source(source_id)
    official = [*vault.manifest.tier1_domains, *vault.manifest.tier2_domains]
    content = sanitize(content)
    sha = hashlib.sha256(content).hexdigest()
    entry = {"source_id": source_id, "url": url, "captured_at": utcnow().isoformat(timespec="seconds"),
             "sha256": sha, "file": f"snapshots/{sha}.{ext}", "license": LICENSE}  # fmt: skip
    if src is None or src.tier != 1 or entry_problems(entry, official) or len(content) > MAX_BYTES:
        return None
    box = outbox(ws)
    (box / "snapshots").mkdir(parents=True, exist_ok=True)
    (box / entry["file"]).write_bytes(content)
    (box / f"{sha}.json").write_text(json.dumps(entry, indent=2), encoding="utf-8")
    return entry


def shared(ws: Workspace) -> list[dict[str, Any]]:
    box = outbox(ws)
    return (
        [json.loads(p.read_text(encoding="utf-8")) for p in sorted(box.glob("*.json"))]
        if box.exists()
        else []
    )
