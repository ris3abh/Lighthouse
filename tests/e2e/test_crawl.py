"""The crawler: every route, every interactive element, used once. Records uncaught errors, console errors, failed
requests, dead controls (no visible change, no request), broken links and controls the keyboard can't reach.

Each route gets a fresh copy of Maya's filming workspace, so one route's clicks never leak into the next. Risky
controls (delete, reject, restart, disconnect) go last on their page."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from .harness import OUT, ROUTES, new_page, open_route

INTERACTIVE = ("a[href], button, input:not([type=hidden]), select, textarea, summary, [role=button], [role=switch], "
               "[role=tab], [role=menuitem], [role=checkbox], [role=link], [draggable=true], canvas[tabindex], "
               "[contenteditable=true]")  # fmt: skip
RISKY = re.compile(r"delete|remove|reject|restart|onboarding again|disconnect|forget|unlink|clear|drop$|mark gap|"
                   r"send|approve", re.I)  # fmt: skip
MAX_PER_ROUTE = 160
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

DESCRIBE = """(sel) => {
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.closest('[inert]')
           && !el.closest('[aria-hidden=true]'); };
  const name = (el) => (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder')
                       || el.getAttribute('title') || el.getAttribute('name') || '').replace(/\\s+/g, ' ').trim().slice(0, 70);
  const seen = {};
  return [...document.querySelectorAll(sel)].map((el) => {
    const key = [el.tagName.toLowerCase(), el.getAttribute('type') || '', el.getAttribute('role') || '', name(el),
                 el.getAttribute('href') || ''].join('|');
    seen[key] = (seen[key] || 0) + 1;
    return { key, n: seen[key] - 1, tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '',
             role: el.getAttribute('role') || '', name: name(el), href: el.getAttribute('href') || '',
             visible: vis(el), disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
             focusable: el.tabIndex >= 0, draggable: el.getAttribute('draggable') === 'true' };
  });
}"""
FIND = """([sel, key, n]) => {
  const name = (el) => (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder')
                       || el.getAttribute('title') || el.getAttribute('name') || '').replace(/\\s+/g, ' ').trim().slice(0, 70);
  const all = [...document.querySelectorAll(sel)].filter((el) => [el.tagName.toLowerCase(), el.getAttribute('type') || '',
    el.getAttribute('role') || '', name(el), el.getAttribute('href') || ''].join('|') === key);
  return all[n] || null;
}"""


def _keyboard_reached(page: Any, limit: int = 400) -> set[str]:
    """Tab through the page and collect the descriptor keys of everything that took focus."""
    page.evaluate("document.activeElement && document.activeElement.blur()")
    page.locator("body").focus() if page.locator("body").count() else None
    reached: set[str] = set()
    first = None
    for _ in range(limit):
        page.keyboard.press("Tab")
        key = page.evaluate("""() => { const el = document.activeElement; if (!el || el === document.body) return null;
          const name = (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder')
            || el.getAttribute('title') || el.getAttribute('name') || '').replace(/\\s+/g, ' ').trim().slice(0, 70);
          return [el.tagName.toLowerCase(), el.getAttribute('type') || '', el.getAttribute('role') || '', name,
                  el.getAttribute('href') || ''].join('|'); }""")
        if key is None:
            continue
        if key == first:
            break
        first = first or key
        reached.add(key)
    return reached


def _exercise(page: Any, el: Any, d: dict[str, Any], tmp: Path) -> str:
    """Use one control the way a person would. Returns what was done."""
    tag, typ = d["tag"], d["type"]
    if tag == "input" and typ == "file":
        f = tmp / "qa-upload.pdf"
        f.write_bytes(PDF)
        el.set_input_files(str(f))
        return "file"
    if tag == "input" and typ in ("checkbox", "radio"):
        el.click(timeout=3000)
        return "toggle"
    if tag == "input" and typ == "date":
        el.fill("2026-12-15")
        return "fill"
    if tag == "input" and typ == "month":
        el.fill("2027-03")
        return "fill"
    if tag == "input" and typ == "range":
        el.focus()
        page.keyboard.press("ArrowLeft")
        return "range"
    if tag in ("input", "textarea") or d["role"] == "textbox":
        el.fill("QA test: a fairly long piece of text to see how the control copes " * 2)
        el.press("Tab")
        return "fill"
    if tag == "select":
        opts = el.evaluate("(s) => [...s.options].map((o) => o.value)")
        if len(opts) > 1:
            el.select_option(opts[1])
        return "select"
    el.click(timeout=3000)
    return "click"


@pytest.mark.parametrize("route", ROUTES)
def test_every_control_on_the_route(route, browser, serve, qa, tmp_path):
    srv = serve("film")
    page = new_page(browser, qa, label=f"#/{route}")
    open_route(page, srv.base, route, qa)
    url = page.url
    elements = page.evaluate(DESCRIBE, INTERACTIVE)
    elements = [e for e in elements if e["visible"] and not e["disabled"]][:MAX_PER_ROUTE]
    reached = _keyboard_reached(page)
    for e in elements:
        if not e["focusable"] or (e["key"] not in reached and e["tag"] != "canvas"):
            qa.add(
                "keyboard_unreachable", f"{e['tag']} “{e['name']}” isn't reachable with Tab", element=e["key"]
            )
    elements.sort(key=lambda e: bool(RISKY.search(e["name"])))  # risky ones last
    exercised, statically, skipped = 0, 0, 0
    for e in elements:
        if page.url != url:
            open_route(page, srv.base, route)
        handle = page.evaluate_handle(FIND, [INTERACTIVE, e["key"], e["n"]]).as_element()
        if handle is None or not handle.is_visible():
            skipped += 1  # gone after an earlier action (e.g. a card that was accepted)
            continue
        href = e["href"]
        if (
            e["tag"] == "a"
            and href.startswith(("http://", "https://", "mailto:", "webcal:"))
            and "127.0.0.1" not in href
        ):
            statically += 1  # external: checked, not followed (offline)
            continue
        if e["draggable"]:
            statically += 1  # drag and drop: covered by the flow tests
            continue
        current = handle.evaluate(
            "(el) => el.getAttribute('aria-pressed') === 'true' || el.getAttribute('aria-checked') === 'true' "
            "|| el.getAttribute('aria-current') === 'page' || el.getAttribute('aria-selected') === 'true'"
        )
        before = page.evaluate("() => [window.__qa.mut, location.href]")
        reqs = qa.requests
        n_findings = len(qa.findings)
        qa.where = f"#/{route} → {e['tag']} “{e['name']}”"
        try:
            how = _exercise(page, handle, e, tmp_path)
        except Exception as exc:
            qa.add(
                "unusable",
                f"couldn't use {e['tag']} “{e['name']}”: {str(exc).splitlines()[0][:200]}",
                element=e["key"],
            )
            skipped += 1
            continue
        exercised += 1
        page.wait_for_timeout(450)
        try:
            after = page.evaluate("() => [window.__qa.mut, location.href]")
        except Exception:
            after = [None, page.url]
        changed = after[0] != before[0] or after[1] != before[1] or qa.requests != reqs
        if not changed and how == "click" and (current or (href and url.endswith(href))):
            qa.add(
                "self_link",
                f"{e['tag']} “{e['name']}” is already selected or links to this page",
                element=e["key"],
            )
        elif not changed and how == "click":
            qa.add("dead_control", f"{e['tag']} “{e['name']}” did nothing (no change on screen, no request)",
                   element=e["key"], screenshot=qa.shot(page, f"dead-{route}-{exercised}"))  # fmt: skip
        if (
            e["tag"] == "a"
            and href.startswith("#/")
            and page.locator("text=The address doesn't match any page here.").count()
        ):
            qa.add("broken_link", f"link “{e['name']}” goes to {href}, which isn't a page", element=e["key"])
        if any(f["error"] for f in qa.findings[n_findings:]):
            qa.findings[-1]["screenshot"] = qa.shot(page, f"err-{route}-{exercised}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)
    total = len(elements)
    qa.coverage = {
        "route": route,
        "elements": total,
        "exercised": exercised,
        "static": statically,
        "skipped": skipped,
    }
    errors = qa.errors()
    assert not errors, "\n".join(f"{f['kind']}: {f['where']}: {f['message']}" for f in errors[:20])


def test_report_dir_is_writable():
    OUT.mkdir(parents=True, exist_ok=True)
    assert OUT.is_dir()
