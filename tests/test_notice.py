"""I3: a NOTICE file (Area O1, created by Rishabh Sharma) that built packages carry (Apache-2.0 section 4(d))."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_notice_names_the_product_and_its_creator():
    text = (ROOT / "NOTICE").read_text()
    assert text.startswith("Area O1\n") and "created by Rishabh Sharma" in text and "Apache License" in text


def test_built_packages_carry_it():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert "NOTICE" in project["project"]["license-files"]  # the wheel's .dist-info/licenses/
    assert "NOTICE" in project["tool"]["hatch"]["build"]["targets"]["sdist"]["include"]  # the source package
