"""Every name in one place (ADR 0010 §1): files that can't read areao1/core/names.json agree with it, and the old
name survives only where it should (history, migration, the deprecated alias)."""

from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

from areao1.core import names

ROOT = Path(__file__).resolve().parents[1]
# Where "Lighthouse" / "lighthouse-gc" may still appear: history, the migration and its tests, the alias.
OLD_NAME_ALLOWED = re.compile(
    r"^(CHANGELOG\.md|docs/adr/(?!0010).*|TODO\.md|areao1/core/names\.json|areao1/core/migrate\.py|"
    r"areao1/core/secrets\.py|areao1/core/workspace\.py|areao1/home\.py|areao1/agent/routing\.py|areao1/server/app\.py|areao1/onboarding/models\.py|areao1/onboarding/api\.py|"
    r"areao1/cli\.py|pyproject\.toml|scripts/check_repo\.py|tests/test_(migration|names|connect_ai)\.py|"
    r"tests/conftest\.py|docs/adr/0010-area-o1\.md|docs/manual/reference/lighthouse\.md|mkdocs\.yml|SPEC\.md|README\.md)$"
)


def _tracked() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    return [f for f in out.splitlines() if f and (ROOT / f).is_file()]


def test_files_that_cant_import_the_names_agree_with_them():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert project["name"] == names.PACKAGE and project["scripts"][names.CLI] == f"{names.PACKAGE}.cli:app"
    assert project["scripts"][names.PREVIOUS["cli"]] == f"{names.PACKAGE}.cli:deprecated"
    for f, needles in {
        "install.sh": [names.REPO, f"{names.ENV_PREFIX}SPEC", f'"$(uv tool dir --bin)/{names.CLI}"'],
        "install.ps1": [names.REPO, f"{names.ENV_PREFIX}SPEC", names.CLI],
        "docs/site/index.html": [names.PRODUCT, names.REPO],
        "README.md": [f"# {names.PRODUCT}", names.REPO],
        "CITATION.cff": [names.PRODUCT],
        "web/index.html": [f"<title>{names.PRODUCT}</title>"],
        ".github/workflows/release.yml": [names.CLI],
        ".github/workflows/ci.yml": [names.PACKAGE],
    }.items():
        text = (ROOT / f).read_text()
        for n in needles:
            assert n in text, f"{f}: {n}"


def test_the_old_name_is_gone_except_where_it_belongs():
    old = re.compile(rf"{names.PREVIOUS['product']}|{names.PREVIOUS['cli']}|lighthouse_gc|LIGHTHOUSE_", re.I)
    stray = []
    for f in _tracked():
        if OLD_NAME_ALLOWED.match(f) or f.endswith((".pdf", ".png", ".woff2", ".ico")):
            continue
        try:
            text = (ROOT / f).read_text()
        except UnicodeDecodeError:
            continue
        stray += [f"{f}: {m.group(0)}" for m in old.finditer(text)]
    assert not stray, stray[:20]


def test_the_web_app_reads_the_same_names():
    text = (ROOT / "web" / "src" / "names.ts").read_text()
    assert "areao1/core/names.json" in text and "names.product" in text
