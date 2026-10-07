"""Core/profile split (SPEC 2.7, Phase 0): ``areao1.core`` is domain-agnostic.

The core may import only the standard library, third-party packages and ``areao1.core`` itself,
and its source must not mention any immigration profile. Domain knowledge lives in
``areao1.criteria`` and the YAML profiles.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

import areao1

CORE = Path(areao1.__file__).parent / "core"
CORE_FILES = sorted(CORE.rglob("*.py"))
DOMAIN_TERMS = re.compile(r"\b(o-?1a|eb-?1a|uscis|immigration|petition|8 cfr|visa)\b", re.I)


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out += [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            out.append(node.module)
        elif isinstance(node, ast.ImportFrom) and node.level:
            out.append("." * node.level + (node.module or ""))
    return out


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: p.relative_to(CORE).as_posix())
def test_core_imports_only_core(path):
    bad = [m for m in _imports(path) if m.startswith("areao1") and not m.startswith("areao1.core")]
    bad += [m for m in _imports(path) if m.startswith(".")]  # relative imports could escape core
    assert not bad, f"{path.name} imports outside areao1.core: {bad}"


@pytest.mark.parametrize("path", CORE_FILES, ids=lambda p: p.relative_to(CORE).as_posix())
def test_core_source_has_no_domain_terms(path):
    hits = DOMAIN_TERMS.findall(path.read_text(encoding="utf-8"))
    assert not hits, f"{path.name} mentions domain terms {sorted(set(hits))}; move that to areao1.criteria"


def test_core_works_without_the_domain_layer(tmp_path):
    """A bare core Workspace stores evidence with no profile loaded."""
    from datetime import date

    from areao1.core.workspace import Workspace

    ws = Workspace(tmp_path)
    ws.add_exhibit_file(
        content=b"x",
        filename="a.txt",
        criterion="any_rubric_item",
        evidence_type="note",
        title="T",
        on=date(2026, 1, 1),
    )
    assert ws.exhibits().exhibits[0].criterion == "any_rubric_item"
