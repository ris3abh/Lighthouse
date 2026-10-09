"""Check the vault test fixtures against the live sources they were copied from (network; dev-only, not run by
the test suite). For each entry in tests/fixtures/vault/SOURCES.json: fetch the source, extract its text the way
the vault does, and confirm the fixture is genuine: a PDF byte-identical to the court's, or a page whose every
sentence (over 60 characters) is in today's live page. Then confirm every final-merits quote in profiles/ is word
for word in the live text.

    python scripts/check_vault_fixtures.py
"""

from __future__ import annotations

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
    from areao1.criteria.case import Case
    from areao1.criteria.engine import load_profiles
    from areao1.criteria.merits import passage_text, quoted_in
    from areao1.scaffold import create_workspace
    from areao1.vault.store import Vault

    vault = Vault(Case(create_workspace(Path(tempfile.mkdtemp()) / "ws", name="", git=False).root))

    def text(sid: str, data: bytes) -> str:
        name = "x.pdf" if data[:4] == b"%PDF" else "x.html"
        return vault.snapshot_text(vault.import_file(sid, data, filename=name).sha256)

    ok = True
    live_texts: dict[str, str] = {}
    for row in json.loads((FIXTURES / "SOURCES.json").read_text())["fixtures"]:
        raw = (FIXTURES / row["file"]).read_bytes()
        fixture = gzip.decompress(raw) if row["file"].endswith(".gz") else raw
        live = fetch(row["source_url"])
        sid = SOURCE_IDS[row["file"]]
        live_texts[sid] = text(sid, live)
        if fixture[:4] == b"%PDF":
            same = fixture == live
            print(
                f"{row['file']}: {'byte-identical to the source' if same else 'DIFFERS from the source PDF'}"
            )
            ok &= same
            continue
        whole = passage_text(live_texts[sid])
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", passage_text(text(sid, fixture))) if len(s) > 60]
        missing = [s for s in sentences if s not in whole]
        print(
            f"{row['file']}: {len(sentences) - len(missing)} of {len(sentences)} sentences in the live page"
        )
        for s in missing[:5]:
            print(f"   not live: {s[:140]}")
        ok &= not missing
    for profile in load_profiles().values():
        for cite in profile.final_merits.standard if profile.final_merits else []:
            found = cite.source_id in live_texts and quoted_in(cite.quote, live_texts[cite.source_id])
            print(
                f"{profile.id} {cite.source_id}: {'word for word' if found else 'NOT FOUND'}: {cite.quote[:70]}…"
            )
            ok &= found
    return 0 if ok else 1


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
