"""The landing page (ADR 0013, S5): one static page with the one line, a screenshot, what you need, the
privacy promise and the not-legal-advice note; the README, short, shows the same install lines."""

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
    section = readme.split("## Install in one line", 1)[1].split("\n## ", 1)[0]
    return [b.strip() for b in re.findall(r"```(?:sh|powershell)\n(.*?)```", section, re.S)]


def test_readme_is_short_and_points_to_the_docs():
    readme = (ROOT / "README.md").read_text()
    heads = re.findall(r"^## .+", readme, re.M)
    assert heads == ["## What it does", "## Install in one line", "## Connect Claude Code or Codex via MCP",
                     "## Privacy: runs on your machine", "## Contributing"]  # fmt: skip
    assert len(readme.splitlines()) < 120  # details live in the docs
    top = readme.split("## What it does", 1)[0]
    assert '<img src="docs/social-preview.png"' in top and "overview-dark.webp" in top  # banner, screenshot
    for badge in (
        "actions/workflows/ci.yml/badge.svg",
        "github/license",
        "github/v/release",
        "badge/python-3.11",
    ):
        assert badge in top, badge
    assert "https://ris3abh.github.io/areao1/docs/" in top
    for icon in re.findall(r'src="(docs/readme/icons/[^"]+)"', readme):
        assert (ROOT / icon).is_file(), icon
    for f in ("README.md", "docs/manual/getting-started/install.md"):
        assert "cd Area O1" not in (ROOT / f).read_text()  # the checkout folder is areao1
    lines = _readme_install_lines()
    assert len(lines) == 2
    assert lines[0].endswith("/install.sh | sh") and "install.ps1 | iex" in lines[1]
    assert "claude mcp add areao1 -- areao1 mcp" in readme and "codex mcp add areao1 -- areao1 mcp" in readme


def test_page_shows_the_install_lines_exactly_as_the_readme():
    text = html.unescape(PAGE.read_text())
    for line in _readme_install_lines():
        assert f"<code>{line}</code>" in text, line


def test_page_has_the_legal_note_from_the_app_footer():
    footer = (ROOT / "web" / "src" / "App.tsx").read_text().split("<footer", 1)[1].split("</footer>", 1)[0]
    from areao1.core.names import PRODUCT

    note = " ".join(footer.split(">", 1)[1].split()).replace("{PRODUCT}", PRODUCT)
    note = re.sub(
        r"\s*<Banter[^>]*/>", "", note
    ).strip()  # the tagged disclaimer line is checked in test_banter
    page = " ".join(html.unescape(PAGE.read_text()).split())
    assert note.startswith("Area O1 is not legal advice") and note in page


def test_page_has_what_you_need_privacy_and_a_screenshot():
    text = html.unescape(PAGE.read_text())
    assert "Claude Code login" not in text  # claude.ai login isn't offered (ADR 0013 §4)
    for needle in ("LinkedIn profile as a PDF", "OpenAI API key", "127.0.0.1", "~/AreaO1"):
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
    for ref in re.findall(r'url\("([^"]+)"\)|href="([^"#:]+)"|src="([^"#:]+)"', text):
        local = next(r for r in ref if r)
        if local == "./" or local.startswith("docs/"):  # the page itself; the docs are built beside it
            continue
        assert (SITE / local).is_file(), local  # fonts and icon ship with the page
    assert (SITE / "fonts" / "LICENSE-archivo.txt").exists()  # OFL fonts travel with their license


def test_page_uses_the_dashboard_logo_and_links_the_docs():
    text = PAGE.read_text()
    logo = (SITE / "favicon.svg").read_text()
    assert logo == (ROOT / "web" / "public" / "favicon.svg").read_text()  # the dashboard's O1 mark
    assert '<link rel="icon" type="image/svg+xml" href="favicon.svg">' in text
    header = text.split('<header class="top">', 1)[1].split("</header>", 1)[0]
    assert '<img src="favicon.svg"' in header and "<svg" not in header
    assert '<a class="docs" href="docs/">Docs</a>' in header  # in the header
    hero = text.split('<section class="hero">', 1)[1].split("</section>", 1)[0]
    assert 'href="docs/">Read the docs</a>' in hero  # and in the hero, before the install lines
    nav = yaml.dump(yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)["nav"])
    for href in re.findall(r'href="docs/([^"]*)"', text):  # each docs link is a page of the docs site
        assert href == "" or f"{href.rstrip('/')}/index.md" in nav, href


def test_pages_workflow_deploys_the_landing_page_and_the_docs_from_main():
    wf = yaml.safe_load((ROOT / ".github" / "workflows" / "pages.yml").read_text())
    triggers = wf[True] if True in wf else wf["on"]
    assert triggers["push"]["branches"] == ["main"]
    assert {"docs/site/**", "docs/manual/**", "mkdocs.yml"} <= set(triggers["push"]["paths"])
    assert wf["permissions"] == {"contents": "read"}
    job = wf["jobs"]["deploy"]
    assert job["permissions"]["pages"] == "write" and job["permissions"]["id-token"] == "write"
    steps = {s.get("uses", "").split("@")[0]: s for s in job["steps"]}
    assert steps["actions/upload-pages-artifact"]["with"]["path"] == "_site"
    assert "actions/deploy-pages" in steps
    build = next(s["run"] for s in job["steps"] if "mkdocs build" in s.get("run", ""))
    assert "cp -R docs/site/. _site/" in build  # the landing page at /
    assert "--strict --site-dir _site/docs" in build  # the docs at /docs/, broken links fail


def test_docs_site_config():
    cfg = yaml.load((ROOT / "mkdocs.yml").read_text(), Loader=yaml.BaseLoader)  # tolerates !!python tags
    assert cfg["docs_dir"] == "docs/manual" and cfg["site_url"].endswith("/docs/")
    assert cfg["theme"]["name"] == "material" and cfg["theme"]["font"] == "false"  # fonts ship with the site
    manual = ROOT / "docs" / "manual"
    assert (manual / cfg["theme"]["logo"]).read_text() == (
        ROOT / "web" / "public" / "favicon.svg"
    ).read_text()
    assert {p["scheme"] for p in cfg["theme"]["palette"]} == {"default", "slate"}  # light and dark
    assert "search" in cfg["plugins"]
    css = (manual / "stylesheets" / "brutalism.css").read_text()
    assert "archivo.woff2" in css and "jetbrains-mono.woff2" in css and "border-radius: 0" in css
    nav = yaml.dump(cfg["nav"])
    for page in re.findall(r"[\w/-]+\.md", nav):
        assert (manual / page).is_file(), page
    for shot in (manual / "assets" / "shots").glob("*-light.webp"):  # every screenshot in both themes
        assert shot.with_name(shot.name.replace("-light", "-dark")).is_file(), shot.name
