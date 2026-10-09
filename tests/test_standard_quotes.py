"""The standard on the Final merits page and in the packet is quoted, never paraphrased: every passage is a whole
sentence copied word for word from its source, with a section citation, and "verified" means exactly that it is
a substring of the stored snapshot's text. The vault fixtures are real copies of the sources
(tests/fixtures/vault/SOURCES.json; scripts/check_vault_fixtures.py re-checks them against the live sites)."""

from __future__ import annotations

import gzip
import hashlib
import json
import re
from pathlib import Path

import pytest

from areao1.criteria import merits
from areao1.criteria.engine import load_profiles
from areao1.criteria.merits import passage_text, quoted_in

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "vault"
FILE_FOR = {"uscis-pm-6-f-2": "uscis-pm-eb1-extraordinary.html.gz", "uscis-pm-2-m-4": "uscis-pm-o1.html.gz",
            "kazarian-v-uscis": "kazarian.pdf"}  # fmt: skip
CITES = [
    (p.id, c) for p in load_profiles().values() for c in (p.final_merits.standard if p.final_merits else [])
]


def _bytes(name: str) -> bytes:
    raw = (FIXTURES / name).read_bytes()
    return gzip.decompress(raw) if name.endswith(".gz") else raw


@pytest.fixture
def vault(ws):
    from areao1.vault.store import Vault

    v = Vault(ws)
    for sid, name in FILE_FOR.items():
        v.import_file(sid, _bytes(name), filename=name.removesuffix(".gz"))
    return v


def _text(vault, sid: str) -> str:
    st = next(s for s in vault.status() if s["id"] == sid)
    return vault.snapshot_text(st["sha256"])


def test_fixtures_are_the_recorded_copies_of_the_real_sources():
    rows = json.loads((FIXTURES / "SOURCES.json").read_text())["fixtures"]
    assert {r["file"] for r in rows} == set(FILE_FOR.values())
    for r in rows:
        assert hashlib.sha256((FIXTURES / r["file"]).read_bytes()).hexdigest() == r["sha256"], r["file"]
        assert r["source_url"].startswith(
            ("https://www.uscis.gov/policy-manual/", "https://cdn.ca9.uscourts.gov/")
        )
    assert _bytes("kazarian.pdf").startswith(b"%PDF")  # the court's own PDF (byte-identical when checked)


@pytest.mark.parametrize(("profile", "cite"), CITES, ids=[f"{p}-{i}" for i, (p, _) in enumerate(CITES)])
def test_every_passage_is_a_whole_sentence_word_for_word_with_its_section(profile, cite, vault):
    assert cite.source_id in FILE_FOR, cite.source_id
    assert re.match(r"[A-Z“\"]", cite.quote) and cite.quote.rstrip().endswith((".", ".”")), (
        cite.quote
    )  # whole
    assert cite.section and (cite.section.startswith("USCIS Policy Manual, Vol.") or "F.3d" in cite.section)
    assert quoted_in(cite.quote, _text(vault, cite.source_id)), cite.quote
    assert not cite.text  # no paraphrase stands in for the source


def test_verified_means_an_exact_substring_of_the_stored_snapshot(ws, vault):
    from fastapi.testclient import TestClient

    from areao1.server.app import create_app

    for pid in ("o1a", "eb1a"):
        TestClient(create_app(ws, allowed_hosts=["testserver"])).put("/api/profile", headers={"X-AreaO1": "1"},
                                                                     json={"id": pid})  # fmt: skip
        out = merits.check_standard(ws.profile(), vault)
        assert out and all(s.status == "verified" for s in out), [(s.quote[:40], s.why) for s in out]
        for s in out:
            assert re.sub(r"\s+", " ", s.quote) in passage_text(_text(vault, s.source_id))
            assert s.section


def test_a_paraphrase_or_a_changed_word_is_not_verified(ws, vault):
    profile = ws.profile()
    first = profile.final_merits.standard[0]
    first.quote = (
        first.quote.replace("must", "should", 1) if "must" in first.quote else first.quote + " Indeed."
    )
    [changed, *_] = merits.check_standard(profile, vault)
    assert changed.status == "unverified" and "isn't in the current copy" in changed.why


def test_passage_text_only_joins_hyphenated_line_breaks_and_spaces():
    assert passage_text("a peti-\ntioner is  here\n\nnow") == "a petitioner is here now"
    assert passage_text("well-known") == "well-known"  # a real hyphen stays
    assert not quoted_in("short", "short")  # too short to mean anything


def test_the_community_snapshots_carry_the_same_passages(vault, ws):
    """The filming workspace and new vaults use the community library's copies: the O-1 and EB-1 chapters there
    contain every passage too."""
    manifest = json.loads((ROOT / "community-vault" / "manifest.json").read_text())
    for snap in manifest["snapshots"]:
        mine = [c for _, c in CITES if c.source_id == snap["source_id"]]
        if not mine:
            continue
        data = (ROOT / "community-vault" / snap["file"]).read_bytes()
        st = vault.import_file(snap["source_id"], data, filename="page.html")
        text = vault.snapshot_text(st.sha256)
        assert all(quoted_in(c.quote, text) for c in mine), snap["source_id"]
