"""C1 (ADR 0008): no fake data ships; fictional cases live only in tests/fixtures; a new workspace is empty."""

from __future__ import annotations

import importlib.util
import json
import tomllib
from pathlib import Path

from typer.testing import CliRunner

import lighthouse_gc.resources as resources
from lighthouse_gc.cli import app
from lighthouse_gc.scaffold import create_workspace

ROOT = Path(__file__).resolve().parents[1]
PERSONAS = Path(__file__).parent / "fixtures" / "personas"


def test_no_demo_workspace_or_flag():
    assert not (ROOT / "examples").exists()
    assert not hasattr(resources, "demo_workspace_dir")
    force = tomllib.loads((ROOT / "pyproject.toml").read_text())["tool"]["hatch"]["build"]["targets"][
        "wheel"
    ]["force-include"]
    assert not any("demo" in k or "fixtures" in k for k in force)
    help_text = CliRunner().invoke(app, ["up", "--help"]).output
    assert "--demo" not in help_text


def test_a_new_workspace_starts_empty(tmp_path):
    ws = create_workspace(tmp_path / "case", name="", git=False)
    assert ws.person().name == "" and ws.inbox().candidates == [] and ws.exhibits().exhibits == []
    assert ws.deadlines().deadlines == [] and ws.pipeline().items == [] and ws.metrics() == []


def test_personas_are_fictional_and_their_pdfs_reproducible(tmp_path):
    spec = importlib.util.spec_from_file_location("make_pdfs", PERSONAS / "make_pdfs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    names = set()
    for folder in sorted(p.parent for p in PERSONAS.glob("*/persona.json")):
        persona = json.loads((folder / "persona.json").read_text())
        names.add(persona["id"])
        lines = (folder / "linkedin.txt").read_text().splitlines()
        out = tmp_path / f"{folder.name}.pdf"
        mod.write_pdf(out, lines, f"{persona['name']} | LinkedIn")
        assert out.read_bytes() == (folder / "linkedin.pdf").read_bytes()  # committed PDF is up to date
        text = (folder / "linkedin.txt").read_text()
        assert all(e.endswith("@example.com") for e in persona["redacted"] if "@" in e)
        assert all(" 555 " in p for p in persona["redacted"] if "@" not in p)
        assert all(r in text for r in persona["redacted"])
    assert names == {"maya", "ravi", "lena"}
