"""Accessibility fixes that a source scan can hold (F5); the browser suite runs axe-core on every page in both themes
at both widths (tests/e2e/test_pages.py)."""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web" / "src"


def _tsx() -> dict[str, str]:
    return {str(p.relative_to(WEB)): p.read_text() for p in WEB.rglob("*.tsx")}


def test_no_button_inside_a_link():
    for name, text in _tsx().items():
        assert not re.search(r"<a\b[^>]*>\s*<Button\b", text), (
            f"{name}: a Button inside a link (use ButtonLink)"
        )


def test_every_page_has_a_main_heading():
    pages = _tsx()
    for name in ("pages/Overview.tsx", "pages/NotFound.tsx"):
        assert "<h1" in pages[name] or "PageHeader" in pages[name], name


def test_no_aria_label_on_a_plain_span_or_drop_zone():
    for name, text in _tsx().items():
        for m in re.finditer(r"<span\b[^>]*\baria-label=[^>]*>", text):
            assert "role=" in m.group(0), (
                f"{name}: aria-label on a plain span (use sr-only text, or give it a role)"
            )
    assert (
        "aria-label={label}" not in (WEB / "components" / "DropZone.tsx").read_text()
    )  # its visible text names it
