"""The landing page (ADR 0013, S5): one static page with the one line, a screenshot, what you need, the
privacy promise and the not-legal-advice note; the README opens with the same install lines."""

from __future__ import annotations

import html
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "docs" / "site"
PAGE = SITE / "index.html"


def _readme_install_lines() -> list[str]:
    readme = (ROOT / "README.md").read_text()
    section = readme.split("## Install and start", 1)[1].split("\n## ", 1)[0]
    return [b.strip() for b in re.findall(r"```(?:sh|powershell)\n(.*?)```", section, re.S)]


def test_readme_opens_with_what_it_is_the_one_line_and_what_you_need():
    readme = (ROOT / "README.md").read_text()
    heads = re.findall(r"^## .+", readme, re.M)
    assert heads[:2] == ["## Install and start", "## What you need"]
    lines = _readme_install_lines()
    assert len(lines) == 2
    assert lines[0].endswith("/install.sh | sh") and "install.ps1 | iex" in lines[1]


def test_page_shows_the_install_lines_exactly_as_the_readme():
    text = html.unescape(PAGE.read_text())
    for line in _readme_install_lines():
        assert f"<code>{line}</code>" in text, line


def test_page_has_the_legal_note_from_the_app_footer():
    footer = (ROOT / "web" / "src" / "App.tsx").read_text().split("<footer", 1)[1].split("</footer>", 1)[0]
    from areao1.core.names import PRODUCT

    note = " ".join(footer.split(">", 1)[1].split()).replace("{PRODUCT}", PRODUCT)
    page = " ".join(html.unescape(PAGE.read_text()).split())
    assert note.startswith("Area O1 is not legal advice") and note in page


def test_page_has_what_you_need_privacy_and_a_screenshot():
    text = html.unescape(PAGE.read_text())
    assert "Claude Code login" not in text  # claude.ai login isn't offered (ADR 0013 §4)
    for needle in ("LinkedIn profile as a PDF", "Anthropic API key", "127.0.0.1", "~/AreaO1"):
        assert needle in text, needle
    for img in re.findall(r'(?:src|srcset)="([^"]+\.png)"', text):
        assert (SITE / img).is_file(), img
    assert 'width="1440" height="900"' in text  # sized, so the page doesn't jump while it loads


def test_page_is_self_contained():
    text = PAGE.read_text()
    assert not re.search(r"<script[^>]*\bsrc=", text)  # no external scripts
    assert "<script" not in text  # and none inline: a static page
    assert not re.search(r'<link[^>]+rel="stylesheet"', text)  # CSS is inline
    assert "prefers-color-scheme: dark" in text  # light and dark
    for ref in re.findall(r'url\("([^"]+)"\)|href="([^"#:]+)"', text):
        local = next(r for r in ref if r)
        assert (SITE / local).is_file(), local  # fonts and icon ship with the page
    assert (SITE / "fonts" / "LICENSE-archivo.txt").exists()  # OFL fonts travel with their license


def test_pages_workflow_deploys_docs_site_from_main():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "pages.yml").read_text())
    triggers = wf[True] if True in wf else wf["on"]
    assert triggers["push"]["branches"] == ["main"] and "docs/site/**" in triggers["push"]["paths"]
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["deploy"]
    assert job["permissions"]["pages"] == "write" and job["permissions"]["id-token"] == "write"
    steps = {s.get("uses", "").split("@")[0]: s for s in job["steps"]}
    assert steps["actions/upload-pages-artifact"]["with"]["path"] == "docs/site"
    assert "actions/deploy-pages" in steps
