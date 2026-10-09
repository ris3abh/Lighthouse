"""Watching the wording of the standard (ADR 0019, amended 2026-10-09): do the sources Area O1 quotes still say
what it quotes?

The passages of the standard (profiles' ``final_merits.standard``) are quoted word for word from the USCIS Policy
Manual and Kazarian. This module checks a source's current text against them, and against the newest hash-verified
copy in the community library (sentence by sentence), wherever the check runs:

- **On your Mac** (``vault-watch``, daily): uscis.gov serves your browser and curl, so the live pages are read. A
  wording change opens a GitHub issue with ``gh`` when you opted in (``vault.report_wording``), and, when you opted in
  to sharing (``vault.share_captures``), pushes the fresh snapshot to the community library, which also happens when
  the library's newest copy is over 30 days old, so the weekly CI check stays current.
- **In CI** (``scripts/check_vault_fixtures.py``, weekly): uscis.gov blocks GitHub's runners, so a blocked source is
  compared through the community library's newest hash-verified snapshot instead ("checked via community snapshot,
  captured <date>"). Only a real mismatch fails; a source with neither a live copy nor a snapshot newer than 30 days
  is reported "stale", as a warning.

Nothing here writes to the vault or the workspace's evidence; the only outside writes are the opt-in issue and push.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from areao1.core import clock

STALE_DAYS = 30
MIN_SENTENCE = 60
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"


class FetchError(Exception):
    """The source couldn't be read (blocked, down): nothing can be concluded about its wording."""


def passage_text(text: str) -> str:
    from areao1.criteria.merits import passage_text as pt

    return pt(text)


def sentences(text: str) -> list[str]:
    """The sentences worth comparing: over 60 characters, after joining hyphenated breaks and spaces."""
    return [s for s in re.split(r"(?<=[.!?])\s+", passage_text(text)) if len(s) > MIN_SENTENCE]


def missing(reference: str, current: str) -> list[str]:
    """Sentences of ``reference`` that ``current`` no longer has."""
    whole = passage_text(current)
    return [s for s in sentences(reference) if s not in whole]


def text_of(source: Any, content: bytes) -> str:
    """A source's text exactly as the vault extracts it (format, then its start/end cut), without storing it."""
    from areao1.vault.extract import cut, to_text

    ctype = "application/pdf" if content[:4] == b"%PDF" else "text/html"
    return cut(to_text(content, ctype, source.format)[1], source.start, source.end)


def fetch(url: str) -> bytes:
    """With curl and a browser's user agent: uscis.gov answers Python HTTP clients with 403."""
    if shutil.which("curl") is None:
        raise FetchError("curl isn't installed")
    try:
        return subprocess.run(["curl", "-sSfL", "--compressed", "--max-time", "60", "-A", UA, url], check=True,
                              capture_output=True).stdout  # fmt: skip
    except subprocess.CalledProcessError as exc:
        raise FetchError(
            exc.stderr.decode(errors="replace").strip()[:200] or f"curl exit {exc.returncode}"
        ) from exc


def cited(profiles: Any = None) -> dict[str, list[Any]]:
    """Source id -> the passages quoted from it, across every profile."""
    from areao1.criteria.engine import load_profiles

    out: dict[str, list[Any]] = {}
    for p in (profiles or load_profiles()).values():
        for c in p.final_merits.standard if p.final_merits else []:
            out.setdefault(c.source_id, []).append(c)
    return out


# --------------------------------------------------------------------------------------------- community library


@dataclass
class Snapshot:
    source_id: str
    captured_at: datetime
    sha256: str
    url: str
    content: bytes

    def age_days(self, now: datetime) -> int:
        return (now - self.captured_at).days


def repo_of(community_url: str) -> tuple[str, str, str]:
    """(owner/repo, branch, raw base) from a raw.githubusercontent.com community_url."""
    parts = urlparse(community_url).path.strip("/").split("/")
    if urlparse(community_url).hostname != "raw.githubusercontent.com" or len(parts) < 3:
        raise ValueError(f"community_url isn't a raw.githubusercontent.com address: {community_url}")
    return f"{parts[0]}/{parts[1]}", parts[2], community_url.rstrip("/")


def newest_snapshot(base: str, source_id: str, get: Any = None) -> Snapshot | None:
    """The community library's newest valid snapshot of a source, hash-verified; None when it has none. ``get(url)``
    returns bytes (defaults to fetch)."""
    from areao1.vault.community import entry_problems

    get = get or fetch
    manifest = json.loads(get(f"{base.rstrip('/')}/manifest.json"))
    official = manifest.get("official_domains") or []
    entries = [e for e in manifest.get("snapshots") or [] if isinstance(e, dict)
               and e.get("source_id") == source_id and not entry_problems(e, official)]  # fmt: skip
    for e in sorted(entries, key=lambda e: e["captured_at"], reverse=True):
        content = get(f"{base.rstrip('/')}/{e['file']}")
        if hashlib.sha256(content).hexdigest() != e["sha256"]:
            continue  # a snapshot that fails its hash is never used
        at = datetime.fromisoformat(e["captured_at"])
        return Snapshot(
            source_id, at if at.tzinfo else at.replace(tzinfo=UTC), e["sha256"], e["url"], content
        )
    return None


# ------------------------------------------------------------------------------------------------------- checks


@dataclass
class SourceCheck:
    source_id: str
    how: str  # "live", "community snapshot", "unchecked"
    captured_at: datetime | None = None
    gone: list[str] = field(default_factory=list)  # reference sentences the current text no longer has
    quotes_missing: list[str] = field(default_factory=list)  # quoted passages not word for word any more
    note: str = ""
    stale: bool = False
    compared: str = ""  # what was compared, e.g. "245 sentences of the reference, 4 quoted passages"

    @property
    def changed(self) -> bool:
        return bool(self.gone or self.quotes_missing)

    def line(self) -> str:
        if self.how == "live":
            how = "checked live"
        elif self.how == "community snapshot":
            day = clock.local_date(self.captured_at).isoformat() if self.captured_at else "?"
            how = f"checked via community snapshot, captured {day}"
        else:
            how = "not checked"
        state = (
            "WORDING CHANGED"
            if self.changed
            else "matches (stale)"
            if self.stale and self.how != "unchecked"
            else "stale"
            if self.stale
            else "matches"
        )
        extra = "; ".join(x for x in (self.compared, self.note) if x)
        return f"{self.source_id}: {state}, {how}" + (f" ({extra})" if extra else "")


def compare(source_id: str, current: str, how: str, *, reference: str | None, quotes: list[Any],
            captured_at: datetime | None = None) -> SourceCheck:  # fmt: skip
    from areao1.criteria.merits import quoted_in

    parts = [f"{len(sentences(reference))} sentences of the reference" if reference else "",
             f"{len(quotes)} quoted passage{'s' if len(quotes) != 1 else ''}" if quotes else ""]  # fmt: skip
    return SourceCheck(source_id=source_id, how=how, captured_at=captured_at,
                       gone=missing(reference, current) if reference else [],
                       quotes_missing=[c.quote for c in quotes if not quoted_in(c.quote, current)],
                       compared=", ".join(x for x in parts if x))  # fmt: skip


def report_markdown(checks: list[SourceCheck]) -> str:
    out = []
    for c in checks:
        out.append(f"- {c.line()}")
        out += [f"  - quoted passage not found: “{q[:300]}”" for q in c.quotes_missing]
        out += [f"  - no longer in the source: “{s[:300]}”" for s in c.gone[:10]]
        if len(c.gone) > 10:
            out.append(f"  - and {len(c.gone) - 10} more sentences")
    return "\n".join(out)


# ------------------------------------------------------------------------------------------- outside, opt-in


def gh(*args: str, input: bytes | None = None) -> str:
    """Run the GitHub CLI (it carries your login); raises RuntimeError with its message."""
    if shutil.which("gh") is None:
        raise RuntimeError("the GitHub CLI (gh) isn't installed")
    r = subprocess.run(["gh", *args], input=input, capture_output=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.decode(errors="replace").strip()[:300] or f"gh exit {r.returncode}")
    return r.stdout.decode(errors="replace")


LABEL = "vault-wording"


def open_issue(repo: str, body: str, run: Any = None) -> str:
    """Open an issue labeled vault-wording, or comment on the one already open. Returns a line."""
    run = run or gh
    run("label", "create", LABEL, "--repo", repo, "--color", "B60205", "--force",
        "--description", "A vault source's wording no longer matches what Area O1 quotes")  # fmt: skip
    found = run("issue", "list", "--repo", repo, "--label", LABEL, "--state", "open", "--json", "number",
                "-q", ".[0].number").strip()  # fmt: skip
    if found:
        run("issue", "comment", found, "--repo", repo, "--body", body)
        return f"standard: commented on {repo}#{found}"
    url = run("issue", "create", "--repo", repo, "--label", LABEL, "--title",
              f"Vault source wording changed ({clock.today().isoformat()})", "--body", body).strip()  # fmt: skip
    return f"standard: opened {url or 'an issue'}"


def push_snapshot(repo: str, branch: str, entry: dict[str, Any], content: bytes, run: Any = None) -> str:
    """Add a snapshot file and its manifest entry to the community library (a commit through the GitHub API; the
    library's CI validates it). Needs push access. Returns a line."""
    run = run or gh
    path = entry["file"]
    run("api", "-X", "PUT", f"repos/{repo}/contents/{path}", "-f", f"message=Snapshot {entry['source_id']} "
        f"({entry['captured_at'][:10]}), from Area O1 vault-watch", "-f", f"content={base64.b64encode(content).decode()}",
        "-f", f"branch={branch}")  # fmt: skip
    current = json.loads(run("api", f"repos/{repo}/contents/manifest.json?ref={branch}"))
    manifest = json.loads(base64.b64decode(current["content"]))
    manifest.setdefault("snapshots", []).append(entry)
    body = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode()
    run("api", "-X", "PUT", f"repos/{repo}/contents/manifest.json", "-f",
        f"message=manifest: {entry['source_id']} {entry['captured_at'][:10]}", "-f",
        f"content={base64.b64encode(body).decode()}", "-f", f"sha={current['sha']}", "-f", f"branch={branch}")  # fmt: skip
    return f"standard: pushed a fresh {entry['source_id']} snapshot to {repo}"


# -------------------------------------------------------------------------------------------- vault-watch part


def watch(ws: Any, vault: Any, *, get: Any = None, run: Any = None, now: datetime | None = None) -> list[str]:
    """vault-watch's check of the standard, on your machine: each quoted source read live, compared with the quoted
    passages and with the community library's newest snapshot. Opt-in outside actions on a change (or a library
    copy over 30 days old): an issue, a pushed snapshot. Returns report lines; never raises."""
    from areao1.vault import community

    cfg = ws.config().vault
    get, run = get or fetch, run or gh
    now = now or clock.utcnow()
    lines: list[str] = []
    checks: list[SourceCheck] = []
    try:
        repo, branch, base = repo_of(cfg.community_url)
    except ValueError:
        repo = branch = base = ""
    for sid, quotes in sorted(cited().items()):
        source = vault.manifest.source(sid)
        if source is None or not source.enabled or "{" in source.url:
            continue
        try:
            raw = get(source.url)
            live = text_of(source, raw)
        except (FetchError, ValueError) as exc:
            lines.append(f"standard: {sid}: couldn't read the live page ({exc}); nothing concluded")
            continue
        snap = None
        if base and cfg.community:
            try:
                snap = newest_snapshot(base, sid, get)
            except (FetchError, ValueError) as exc:
                lines.append(f"standard: community library unreachable ({exc})")
        check = compare(
            sid, live, "live", reference=text_of(source, snap.content) if snap else None, quotes=quotes
        )
        checks.append(check)
        lines.append(f"standard: {check.line()}")
        old = snap is None or snap.age_days(now) > STALE_DAYS
        if cfg.share_captures and repo and source.tier == 1 and (check.changed or old):
            entry = community.stage_share(
                ws, vault, sid, source.url, raw, "pdf" if raw[:4] == b"%PDF" else "html"
            )
            if entry is None:
                lines.append(f"standard: {sid} isn't shareable (only Tier 1 official pages are)")
            else:
                try:
                    shared = community.sanitize(raw)
                    lines.append(push_snapshot(repo, branch, entry, shared, run))
                except RuntimeError as exc:
                    lines.append(f"standard: couldn't push the {sid} snapshot ({exc}); it's in the outbox")
    changed = [c for c in checks if c.changed]
    if changed:
        body = ("Area O1's vault-watch read the live sources and found wording that no longer matches what Area O1 "
                "quotes or the community library's copy.\n\n" + report_markdown(changed)
                + "\n\nUpdate the quoted passage (profiles/*.yaml) and the fixture (tests/fixtures/vault, "
                "SOURCES.json) from the new wording, with its new section if it moved.")  # fmt: skip
        key = hashlib.sha256(body.encode()).hexdigest()[:16]
        state_path = ws.cache_dir / "standard-watch.json"
        state = json.loads(state_path.read_text()) if state_path.exists() else {}
        if not cfg.report_wording:
            lines.append(
                "standard: wording changed; turn on vault.report_wording to open a GitHub issue for it"
            )
        elif state.get("reported") == key:
            lines.append("standard: wording change already reported")
        else:
            try:
                lines.append(open_issue(cfg.report_repo, body, run))
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps({"reported": key, "at": now.isoformat()}))
            except RuntimeError as exc:
                lines.append(f"standard: couldn't open the GitHub issue ({exc})")
    return lines
