"""Banter rules (ADR 0010 §4): only where listed, never on serious surfaces, "alien" only about us or in the legal
term, never mocking USCIS, attorneys or other companies, at most one line per screen."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from areao1.banter import LINES

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"
LANDING = ROOT / "docs" / "site" / "index.html"

# key -> the files allowed to show it (landing-page lines are checked below; notifications arrive with Part F,
# the constellation with Part H)
PLACES = {
    "disclaimer": {"App.tsx"},
    "empty_inbox": {"pages/Inbox.tsx"},
    "banked": {"pages/Inbox.tsx"},
    "finish": {"components/Finale.tsx"},
    "not_found": {"pages/NotFound.tsx"},
    "eb1a_first_switch": {"App.tsx"},
}
LANDING_LINES = {"hero", "tagline_visit", "tagline_billing", "disclaimer"}
LATER = {"constellation_loading", "signal_verified", "signal_unverified"}
# Serious surfaces: deadlines and countdowns, rule-check warnings, conflicts, refusals, errors, status, filing.
SERIOUS_FILES = ["pages/Overview.tsx", "pages/Evidence.tsx", "pages/Calendar.tsx", "pages/Knowledge.tsx",
                 "pages/Agent.tsx", "components/RuleCheck.tsx", "components/Briefing.tsx",
                 "components/TrackerCard.tsx", "components/Claims.tsx"]  # fmt: skip
USE = re.compile(r"""<Banter\s+id="(\w+)"|banterText\("(\w+)"\)""")


def _uses() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for f in WEB.rglob("*.tsx"):
        for m in USE.finditer(f.read_text()):
            out.setdefault(m.group(1) or m.group(2), set()).add(str(f.relative_to(WEB)))
    return out


def test_every_line_is_used_only_where_it_is_listed():
    assert set(LINES) == set(PLACES) | LANDING_LINES | LATER
    for key, files in _uses().items():
        assert files <= PLACES.get(key, set()), f"{key} used in {files - PLACES.get(key, set())}"
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    for key, text in LINES.items():  # no copy of a line outside the registry and the landing page
        stem = text.split("{")[0][:30]
        for f in tracked:
            if f.endswith((".json", ".pdf", ".png", ".woff2", ".test.ts")) or f.startswith(
                ("docs/adr", "tests/", "CHANGELOG", "TODO")
            ):
                continue
            if f.removeprefix("web/src/") in PLACES.get(
                key, set()
            ):  # its own place (with its plain fallback)
                continue
            if f == "docs/site/index.html" and key in LANDING_LINES:
                continue
            body = (ROOT / f).read_text(errors="ignore")
            assert stem not in body, f"{key!r} copied into {f}"


def test_no_banter_on_serious_surfaces():
    for f in SERIOUS_FILES:
        text = (WEB / f).read_text()
        assert "Banter" not in text and "banterText" not in text, f
    assert "data-serious" in (WEB / "components" / "RuleCheck.tsx").read_text()
    ui = (WEB / "components" / "ui.tsx").read_text()
    assert (
        "data-serious" in ui.split("export function ErrorBox", 1)[1].split("\n}\n", 1)[0]
    )  # errors (404 aside)
    app = (WEB / "App.tsx").read_text()
    assert "data-serious={SERIOUS_PAGES.has(page)" in app
    pages = re.search(
        r"SERIOUS_PAGES = new Set\(\[([^\]]+)\]", (WEB / "lib" / "banter.ts").read_text()
    ).group(1)
    for page in ("overview", "evidence", "calendar", "knowledge", "agent"):
        assert f'"{page}"' in pages


def test_alien_only_about_us_or_in_the_legal_term():
    for key, text in LINES.items():
        for m in re.finditer(r"\balien", text, re.I):
            around = text[max(0, m.start() - 20) : m.end() + 30].lower()
            assert re.search(r"extraordinary aliens?|aliens? of extraordinary ability", around), (key, text)
        assert not re.search(r"\byou(?:'re| are)?\b[^.]*\balien", text, re.I), (key, text)


def test_never_mocking_uscis_attorneys_or_companies():
    for key, text in LINES.items():
        assert not re.search(r"attorney|lawyer|law firm|counsel|paralegal", text, re.I), (key, text)
        if key != "disclaimer":  # the only mention of USCIS is saying we're not affiliated
            assert not re.search(r"USCIS|DHS|government|Google|OpenAI|Anthropic|LinkedIn", text), (key, text)
    assert LINES["disclaimer"].startswith("Not affiliated with USCIS")


def test_at_most_one_line_per_screen():
    for f in WEB.rglob("*.tsx"):
        if f.name in ("Banter.tsx",):
            continue
        n = len(re.findall(r"<Banter\s", f.read_text()))
        assert n <= 1, f"{f.relative_to(WEB)} renders {n} lines"
    page = LANDING.read_text()
    blocks = re.findall(r'data-banter="(\w+)"', page)
    assert blocks == ["hero", "disclaimer"]  # the hero block (headline and its taglines), and the footer
    hero = page.split('data-banter="hero"', 1)[1].split("</div>", 1)[0]
    for key in ("hero", "tagline_visit", "tagline_billing"):
        assert LINES[key].split(".")[0] in hero
