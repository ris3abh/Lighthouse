"""Design system guard (ADR 0007): pages use semantic tokens, never raw palette colors, `dark:` overrides or drop
shadows, and every token is defined for both themes. Monochrome plus exactly three status colors (green banked,
amber building, red attention), and green / amber appear only in the status components."""

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
    "banked",
    "banked-soft",
    "building",
    "building-soft",
    "on-status",
)
# The only colored tokens; everything else is a neutral ramp.
STATUS_TOKENS = {
    "alert",
    "alert-soft",
    "on-alert",
    "banked",
    "banked-soft",
    "building",
    "building-soft",
    "on-status",
}
# Green and amber mean banked and building, nothing else: only these files may use them.
STATUS_COLOR = re.compile(
    r"(?<![\w-])(?:[a-z-]+:)*[a-z]+-(?:banked|building)(?:-soft)?(?![\w-])|var\(--(?:banked|building)"
)
STATUS_FILES = {"components/ui.tsx", "pages/Overview.tsx"}


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


def _hue(hex_color: str) -> str | None:
    """None for a neutral (near-gray) color, otherwise "red", "amber" or "green"."""
    import colorsys

    r, g, b = (int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5))
    if max(r, g, b) - min(r, g, b) < 0.06:  # warm grays (paper, line) are neutral
        return None
    h, _, _ = colorsys.rgb_to_hls(r, g, b)
    deg = h * 360
    return (
        "red" if deg < 25 or deg > 335 else "amber" if deg < 55 else "green" if 90 <= deg <= 160 else "other"
    )


def test_monochrome_plus_three_status_colors():
    css = (WEB / "index.css").read_text(encoding="utf-8")
    for selector in (":root {", ".dark {"):
        start = css.index(selector)
        tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-f]{6})", css[start : css.index("}", start)]))
        colored = {name: _hue(value) for name, value in tokens.items() if _hue(value)}
        assert set(colored) <= STATUS_TOKENS, (selector, colored)
        assert set(colored.values()) == {"red", "amber", "green"}, (selector, colored)
        assert {colored[n] for n in ("alert", "alert-soft")} == {"red"}
        assert {colored[n] for n in ("building", "building-soft")} == {"amber"}
        assert {colored[n] for n in ("banked", "banked-soft")} == {"green"}
    stray = [f"{p.relative_to(WEB)}: {m.group(0)}" for p in _sources() if str(p.relative_to(WEB)) not in STATUS_FILES
             for m in STATUS_COLOR.finditer(p.read_text(encoding="utf-8"))]  # fmt: skip
    assert stray == []  # green / amber are for status only


def test_reduced_motion_and_theme_choice():
    css = (WEB / "index.css").read_text(encoding="utf-8")
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


def _ms(value: str, unit: str) -> float:
    return float(value) * (1000 if unit == "s" else 1)


def test_motion_is_short_and_respects_reduced_motion():
    """ADR 0007: motion is 150–400ms and eased; only a running tool call's pulse loops; reduced motion = instant."""
    css = (WEB / "index.css").read_text(encoding="utf-8")
    durations = []
    for path in [WEB / "index.css", *_sources(), *sorted(WEB.rglob("*.ts"))]:
        text = path.read_text(encoding="utf-8")
        reduced = text.find("@media (prefers-reduced-motion")
        if reduced >= 0:
            text = text[:reduced]
        durations += [
            (path.name, _ms(v, "ms")) for v in re.findall(r"(?<![\w-])duration-(\d+)(?![\w-])", text)
        ]
        durations += [
            (path.name, _ms(v, u)) for v, u in re.findall(r"duration-\[(\d+(?:\.\d+)?)(ms|s)\]", text)
        ]
        durations += [
            (path.name, float(v)) for v in re.findall(r"(?:animationDuration=\{|duration = )(\d+)", text)
        ]
        for line in text.splitlines():
            if "tool-pulse" in line and "infinite" in line:
                continue  # the one loop: a running tool call
            durations += [
                (path.name, _ms(v, u))
                for v, u in re.findall(
                    r"(?:--animate-[\w-]+:|animation:)\s*(?:[a-z][\w-]*\s+)?(\d+(?:\.\d+)?)(ms|s)", line
                )
            ]
            durations += [
                (path.name, _ms(v, u))
                for v, u in re.findall(r"animation-duration:\s*(\d+(?:\.\d+)?)(ms|s)", line)
            ]
    assert durations, "no durations found; the regexes are stale"
    assert [d for d in durations if not 150 <= d[1] <= 400] == []
    assert "infinite" not in css.replace("tool-pulse 1.4s ease-in-out infinite", "")
    block = css[css.index("@media (prefers-reduced-motion: reduce)") :]
    for rule in (
        "animation-duration: 0.01ms",
        "transition-duration: 0.01ms",
        "animation-delay: 0s",
        "transition-delay: 0s",
    ):
        assert rule in block
    assert "::view-transition-group(*)" in block
    motion = (WEB / "lib" / "motion.tsx").read_text(encoding="utf-8")
    assert "prefersReducedMotion()" in motion[motion.index("export function withViewTransition") :]
    for component in ("components/TrendChart.tsx", "components/Sparkline.tsx"):
        assert "useReducedMotion" in (WEB / component).read_text(encoding="utf-8"), component
    assert "reduced" in motion[motion.index("export function useCountUp") : motion.index("function format")]


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_tokens_meet_wcag_aa_in_both_themes():
    css = (WEB / "index.css").read_text(encoding="utf-8")
    for selector in (":root {", ".dark {"):
        start = css.index(selector)
        tokens = dict(re.findall(r"--([\w-]+):\s*(#[0-9a-f]{6})", css[start : css.index("}", start)]))
        for fg in ("ink", "ink-2", "muted", "alert"):
            for bg in ("paper", "surface", "sunken"):
                assert _contrast(tokens[fg], tokens[bg]) >= 4.5, (selector, fg, bg)
        assert _contrast(tokens["on-ink"], tokens["ink"]) >= 4.5, selector
        assert _contrast(tokens["on-alert"], tokens["alert"]) >= 4.5, selector
        assert _contrast(tokens["alert"], tokens["alert-soft"]) >= 4.5, selector
        for status in ("banked", "building"):
            for bg in ("paper", "surface", "sunken"):
                assert _contrast(tokens[status], tokens[bg]) >= 4.5, (selector, status, bg)  # status text
            assert _contrast(tokens[status], tokens[f"{status}-soft"]) >= 4.5, (selector, status)  # badges
            assert _contrast(tokens["on-status"], tokens[status]) >= 4.5, (selector, status)  # filled


def test_the_chat_modal_blurs_everything_behind_it_evenly():
    """Checkpoint 3 follow-up: nothing behind the open chat stays sharp, not even a panel a tool call just changed
    (a mark on top shows that). In Chrome, 75 to 133 elements stayed sharp under the old per-column rule."""
    css = (Path(__file__).resolve().parents[1] / "web" / "src" / "index.css").read_text()
    rule = css[css.index(".lh-chat-modal > .lh-nav") : css.index("}", css.index(".lh-chat-modal > .lh-nav"))]
    assert ".lh-chat-modal .lh-content" in rule and "main > footer" in rule and "blur(" in rule
    assert ":has(.lh-reveal)" not in css and ":not(.lh-reveal)" not in css  # no exemption from the blur
