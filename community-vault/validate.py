"""Validate the community snapshot library: structure, official URLs, hashes. Run by CI on every push and PR.

    python validate.py            # exit 1 with the problems listed, 0 when everything checks out
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
LICENSE = "public-domain-us-gov"
MAX_BYTES = 5 * 1024 * 1024
FILE = re.compile(r"^snapshots/([0-9a-f]{64})\.(html|pdf|txt)$")
KEYS = {"source_id", "url", "captured_at", "sha256", "file", "license", "note"}
# Per-visit tokens must be emptied before sharing (Area O1 does it): they can be tied to whoever captured the page.
VOLATILE = re.compile(
    rb'(?:data-feedback-token|data-form-build-id|nonce|data-nonce)="[^"]+"'
    rb'|name="(?:form_build_id|form_token|csrf_token|_token|authenticity_token|csrfmiddlewaretoken)"[^>]*?value="[^"]+"',
    re.I,
)


def problems(root: Path = ROOT) -> list[str]:
    out: list[str] = []
    try:
        manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [f"manifest.json: {exc}"]
    if manifest.get("version") != 1:
        out.append("manifest.json: version must be 1")
    official = manifest.get("official_domains") or []
    if not official:
        out.append("manifest.json: official_domains is empty")
    seen: set[tuple[str, str]] = set()
    listed: set[str] = set()
    for i, e in enumerate(manifest.get("snapshots") or []):
        where = f"snapshots[{i}]"
        if not isinstance(e, dict):
            out.append(f"{where}: not an object")
            continue
        extra = set(e) - KEYS
        if extra:
            out.append(f"{where}: unknown keys {sorted(extra)}")
        missing = [k for k in KEYS - {"note"} if not e.get(k)]
        if missing:
            out.append(f"{where}: missing {missing}")
            continue
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{1,79}", e["source_id"]):
            out.append(f"{where}: bad source_id {e['source_id']!r}")
        u = urlparse(e["url"])
        host = (u.hostname or "").lower()
        if u.scheme != "https" or not (host.endswith(".gov") or any(host == d or host.endswith("." + d) for d in official)):
            out.append(f"{where}: {e['url']} isn't on an official U.S. government domain")
        if e["license"] != LICENSE:
            out.append(f"{where}: license must be {LICENSE} (U.S. government works, 17 U.S.C. § 105)")
        try:
            datetime.fromisoformat(e["captured_at"])
        except ValueError:
            out.append(f"{where}: captured_at must be ISO 8601")
        m = FILE.match(e["file"])
        if not m or m.group(1) != e["sha256"]:
            out.append(f"{where}: file must be snapshots/<sha256>.<html|pdf|txt>")
            continue
        path = root / e["file"]
        if not path.is_file():
            out.append(f"{where}: {e['file']} is missing")
            continue
        data = path.read_bytes()
        if len(data) > MAX_BYTES:
            out.append(f"{where}: {e['file']} is over 5 MB")
        if hashlib.sha256(data).hexdigest() != e["sha256"]:
            out.append(f"{where}: {e['file']} doesn't match its sha256")
        if VOLATILE.search(data):
            out.append(f"{where}: {e['file']} still has per-visit tokens (form / feedback / CSRF); empty them")
        key = (e["source_id"], e["sha256"])
        if key in seen:
            out.append(f"{where}: duplicate of an earlier entry")
        seen.add(key)
        listed.add(e["file"])
    for f in sorted((root / "snapshots").glob("*")):
        if f.name != ".gitkeep" and f"snapshots/{f.name}" not in listed:
            out.append(f"snapshots/{f.name}: not in manifest.json")
    return out


if __name__ == "__main__":
    found = problems()
    for p in found:
        print(p)
    print("ok" if not found else f"{len(found)} problem(s)")
    sys.exit(1 if found else 0)
