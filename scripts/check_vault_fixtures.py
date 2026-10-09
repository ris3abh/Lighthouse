"""Check the vault test fixtures, and every quoted passage of the standard, against their sources (network;
dev-only, never run on push). Run weekly by .github/workflows/vault-fixtures.yml, and by hand:

    python scripts/check_vault_fixtures.py [--report report.md]

For each fixture in tests/fixtures/vault/SOURCES.json, the source's current text is read live; when the site blocks
the reader (uscis.gov blocks GitHub's runners), the community library's newest hash-verified snapshot stands in, and
the report says "checked via community snapshot, captured <date>". A court PDF must be byte-identical; a page must
still contain every sentence of the fixture; every quoted passage must still be word for word.

Exit status: 0 everything that could be checked matches (a source with neither a live copy nor a snapshot newer
than 30 days is reported "stale", as a warning); 1 a wording mismatch; 3 the check itself couldn't run. Being
blocked is never a failure by itself.
Area O1's vault-watch reads the live pages on your machine and keeps the community snapshots fresh
(areao1/vault/standard.py).
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "vault"
SOURCE_IDS = {"uscis-pm-eb1-extraordinary.html.gz": "uscis-pm-6-f-2", "uscis-pm-o1.html.gz": "uscis-pm-2-m-4",
              "kazarian.pdf": "kazarian-v-uscis"}  # fmt: skip


def check(get=None, now: datetime | None = None) -> list:  # type: ignore[no-untyped-def,type-arg]
    """One SourceCheck per fixture. ``get(url) -> bytes`` defaults to areao1.vault.standard.fetch."""
    from areao1.core.models import VaultConfig
    from areao1.criteria.case import Case
    from areao1.scaffold import create_workspace
    from areao1.vault import standard
    from areao1.vault.store import Vault

    get = get or standard.fetch
    now = now or datetime.now(UTC)
    manifest = Vault(
        Case(create_workspace(Path(tempfile.mkdtemp()) / "ws", name="", git=False).root)
    ).manifest
    _, _, base = standard.repo_of(VaultConfig().community_url)
    quotes = standard.cited()
    checks = []
    for row in json.loads((FIXTURES / "SOURCES.json").read_text())["fixtures"]:
        sid = SOURCE_IDS[row["file"]]
        source = manifest.source(sid)
        raw = (FIXTURES / row["file"]).read_bytes()
        fixture = gzip.decompress(raw) if row["file"].endswith(".gz") else raw
        reference = standard.text_of(source, fixture)
        try:
            live = get(row["source_url"])
            c = standard.compare(sid, standard.text_of(source, live), "live", reference=reference,
                                 quotes=quotes.get(sid, []))  # fmt: skip
            if fixture[:4] == b"%PDF" and live != fixture:
                c.gone = c.gone or ["(the court's PDF is no longer byte-identical to the fixture)"]
        except standard.FetchError as exc:
            blocked = f"live page blocked: {exc}"
            try:
                snap = standard.newest_snapshot(base, sid, get)
            except (standard.FetchError, ValueError) as err:
                snap, blocked = None, f"{blocked}; community library unreachable: {err}"
            if snap is None:
                c = standard.SourceCheck(
                    sid, "unchecked", note=f"{blocked}; no community snapshot", stale=True
                )
            else:
                c = standard.compare(sid, standard.text_of(source, snap.content), "community snapshot",
                                     reference=reference, quotes=quotes.get(sid, []), captured_at=snap.captured_at)  # fmt: skip
                c.note = blocked
                c.stale = snap.age_days(now) > standard.STALE_DAYS
                if c.stale:
                    c.note += f"; the newest snapshot is {snap.age_days(now)} days old"
        checks.append(c)
    return checks


def main() -> int:
    from areao1.vault import standard

    ap = argparse.ArgumentParser()
    ap.add_argument("--report", help="also write the findings as Markdown to this file")
    args = ap.parse_args()
    try:
        checks = check()
    except Exception as exc:  # the check itself broke: a bug to fix, never reported as a wording change
        print(f"the check couldn't run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 3
    report = standard.report_markdown(checks)
    print(report)
    if args.report:
        Path(args.report).write_text(report + "\n", encoding="utf-8")
    return 1 if any(c.changed for c in checks) else 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
