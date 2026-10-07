"""Design system guard (ADR 0007): pages use semantic tokens, never raw palette colors, `dark:` overrides or drop
shadows, and every token is defined for both themes."""

from __future__ import annotations

import re
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "web" / "src"
PALETTE = re.compile(
    r"(?<![\w-])(?:[a-z-]+:)*(?:bg|text|border|ring|fill|stroke|divide|decoration|outline|from|to|via|accent|caret|placeholder)"
    r"-(?:zinc|amber|emerald|red|sky|blue|green|yellow|orange|slate|gray|rose|indigo|purple|teal|violet|lime|neutral|stone"
    r"|white|black)(?:-\d{2,3})?(?:/\d+)?(?![\w-])"
)
DARK_VARIANT = re.compile(r"(?<![\w-])dark:[\w\[\]/.-]+")
SHADOW = re.compile(r"(?<![\w-])shadow(?:-(?!none)[\w\[\]]+)?(?![\w-])")
TOKENS = (
    "paper",
    "surface",
    "sunken",
    "ink",
    "ink-2",
    "muted",
    "line",
    "frame",
    "alert",
    "alert-soft",
    "on-ink",
    "on-alert",
)


def _sources():
    return sorted(p for p in WEB.rglob("*.tsx"))


def _class_strings(text: str):
    return re.findall(r'"[^"\n]*"|`[^`]*`', text)


def test_pages_use_tokens_not_palette_colors():
    offenders = []
    for path in _sources():
        for s in _class_strings(path.read_text(encoding="utf-8")):
            for pattern in (PALETTE, DARK_VARIANT, SHADOW):
                for m in pattern.finditer(s):
                    offenders.append(f"{path.relative_to(WEB)}: {m.group(0)}")
    assert offenders == []


def test_every_token_is_defined_for_light_and_dark():
    css = (WEB / "index.css").read_text(encoding="utf-8")
    light = css[css.index(":root {") : css.index("}", css.index(":root {"))]
    dark = css[css.index(".dark {") : css.index("}", css.index(".dark {"))]
    for token in TOKENS:
        assert f"--{token}:" in light, token
        assert f"--{token}:" in dark, token
        assert f"--color-{token}: var(--{token})" in css, token


def test_one_accent_reduced_motion_and_theme_choice():
    css = (WEB / "index.css").read_text(encoding="utf-8")
    hexes = set(re.findall(r"#[0-9a-f]{6}", css[: css.index("@theme")]))
    assert len(hexes) <= 24  # monochrome ramp plus one red in each theme
    assert "@media (prefers-reduced-motion: reduce)" in css
    hooks = (WEB / "hooks.ts").read_text(encoding="utf-8")
    assert '"system" | "light" | "dark"' in hooks and "prefers-color-scheme: dark" in hooks
    html = (WEB.parent / "index.html").read_text(encoding="utf-8")
    assert 'localStorage.getItem("lh-theme")' in html  # applied before first paint


EMOJI = re.compile("[←-⇿⌀-⏿①-➿⬀-⯿\U0001f000-\U0001faff＋■-◿♥★]")


def test_no_emoji_or_glyph_icons_in_the_dashboard():
    """Icons are lucide line icons (ADR 0007), never emoji or text glyphs."""
    offenders = [
        f"{path.relative_to(WEB)}:{n}: {line.strip()[:80]}"
        for path in _sources()
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if EMOJI.search(line)
    ]
    assert offenders == []
