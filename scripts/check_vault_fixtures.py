"""Check the vault test fixtures against the live sources they were copied from (network; dev-only, not run by
the test suite). For each entry in tests/fixtures/vault/SOURCES.json: fetch the source, extract its text the way
the vault does, and confirm the fixture is genuine: a PDF byte-identical to the court's, or a page whose every
sentence (over 60 characters) is in today's live page. Then confirm every final-merits quote in profiles/ is word
for word in the live text.

    python scripts/check_vault_fixtures.py [--report report.md]

Exit status: 0 everything matches; 1 a source's wording changed (a fixture sentence or a quoted passage is no
longer in the live text, or the court's PDF differs); 2 a source couldn't be fetched (nothing was concluded about
its wording). Run weekly by .github/workflows/vault-fixtures.yml, never on push: it uses the network.
"""

from __future__ import annotations

import argparse
import gzip
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "vault"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"
SOURCE_IDS = {"uscis-pm-eb1-extraordinary.html.gz": "uscis-pm-6-f-2", "uscis-pm-o1.html.gz": "uscis-pm-2-m-4",
              "kazarian.pdf": "kazarian-v-uscis"}  # fmt: skip


def fetch(url: str) -> bytes:
    """With curl: uscis.gov answers Python's HTTP client with 403 but serves curl."""
    return subprocess.run(
        ["curl", "-sSfL", "--max-time", "60", "-A", UA, url], check=True, capture_output=True
    ).stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", help="also write the findings as Markdown to this file")
    args = ap.parse_args()
    lines: list[str] = []

    def say(line: str) -> None:
        print(line)
        lines.append(line)

    from areao1.criteria.case import Case
    from areao1.criteria.engine import load_profiles
    from areao1.criteria.merits import passage_text, quoted_in
    from areao1.scaffold import create_workspace
    from areao1.vault.store import Vault

    vault = Vault(Case(create_workspace(Path(tempfile.mkdtemp()) / "ws", name="", git=False).root))

    def text(sid: str, data: bytes) -> str:
        name = "x.pdf" if data[:4] == b"%PDF" else "x.html"
        return vault.snapshot_text(vault.import_file(sid, data, filename=name).sha256)

    ok, unreachable = True, False
    live_texts: dict[str, str] = {}
    for row in json.loads((FIXTURES / "SOURCES.json").read_text())["fixtures"]:
        raw = (FIXTURES / row["file"]).read_bytes()
        fixture = gzip.decompress(raw) if row["file"].endswith(".gz") else raw
        try:
            live = fetch(row["source_url"])
        except subprocess.CalledProcessError as exc:
            say(
                f"- {row['file']}: couldn't fetch {row['source_url']} ({exc.stderr.decode(errors='replace').strip()[:200]})"
            )
            unreachable = True
            continue
        sid = SOURCE_IDS[row["file"]]
        live_texts[sid] = text(sid, live)
        if fixture[:4] == b"%PDF":
            same = fixture == live
            say(
                f"- {row['file']}: {'byte-identical to the source' if same else 'DIFFERS from the source PDF'}"
            )
            ok &= same
            continue
        whole = passage_text(live_texts[sid])
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", passage_text(text(sid, fixture))) if len(s) > 60]
        missing = [s for s in sentences if s not in whole]
        say(
            f"- {row['file']}: {len(sentences) - len(missing)} of {len(sentences)} sentences in the live page "
            f"({row['source_url']})"
        )
        for s in missing[:10]:
            say(f"  - no longer live: “{s[:300]}”")
        ok &= not missing
    for profile in load_profiles().values():
        for cite in profile.final_merits.standard if profile.final_merits else []:
            if cite.source_id not in live_texts:
                continue  # its source couldn't be fetched: nothing to conclude
            found = quoted_in(cite.quote, live_texts[cite.source_id])
            say(
                f"- {profile.id} {cite.source_id}: {'word for word' if found else 'NOT FOUND'}: “{cite.quote[:90]}…” "
                f"({cite.section})"
            )
            ok &= found
    if args.report:
        Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1 if not ok else 2 if unreachable else 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
