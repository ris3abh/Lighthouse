"""The crawler: every route, every interactive element, used once. Records uncaught errors, console errors, failed
requests, dead controls (no change on screen, no request, no file chooser, download or new tab), broken links and
controls the keyboard can't reach, and a reason for every control it doesn't exercise.

Each route gets a fresh copy of Maya's filming workspace, so one route's clicks never leak into the next. A control
is identified within its nearest stable container (a criterion card, an Inbox candidate, a checklist), so re-renders
elsewhere don't shift it; anything that vanished after an earlier action gets a second try on a reloaded page. Risky
controls (delete, reject, restart, disconnect) go last."""

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
MAX_PER_ROUTE = 600
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"

# A control's key: what it is and says, inside its nearest stable container, plus its position there.
KEY_JS = """
  const CONTAINER = '[data-proof-item],[id^="crit-"],[id^="proof-"],[data-candidate],[data-letter-draft],[data-panel],[role=dialog],article,li,tr';
  const name = (el) => (el.getAttribute('aria-label') || el.textContent || el.getAttribute('placeholder')
                       || el.getAttribute('title') || el.getAttribute('name') || '').replace(/\\s+/g, ' ').trim().slice(0, 70);
  const where = (el) => { const c = el.parentElement && el.parentElement.closest(CONTAINER); if (!c) return '';
    return c.id || c.getAttribute('data-proof-item') || c.getAttribute('data-candidate') || c.getAttribute('data-letter-draft') || c.getAttribute('data-panel')
           || (c.getAttribute('role') === 'dialog' ? 'dialog' : c.tagName.toLowerCase() + ':' + name(c).slice(0, 30)); };
  const keyOf = (el) => [where(el), el.tagName.toLowerCase(), el.getAttribute('type') || '', el.getAttribute('role') || '',
                         name(el), el.getAttribute('href') || ''].join('|');
"""
DESCRIBE = (
    "(sel) => {"
    + KEY_JS
    + """
  const vis = (el) => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && !el.closest('[inert]')
           && !el.closest('[aria-hidden=true]'); };
  const seen = {};
  return [...document.querySelectorAll(sel)].map((el) => {
    const key = keyOf(el);
    seen[key] = (seen[key] || 0) + 1;
    return { key, n: seen[key] - 1, tag: el.tagName.toLowerCase(), type: el.getAttribute('type') || '',
             role: el.getAttribute('role') || '', name: name(el), href: el.getAttribute('href') || '',
             visible: vis(el), disabled: !!el.disabled || el.getAttribute('aria-disabled') === 'true',
             focusable: el.tabIndex >= 0, draggable: el.getAttribute('draggable') === 'true' };
  });
}"""
)
FIND = (
    "([sel, key, n]) => {"
    + KEY_JS
    + """
  return [...document.querySelectorAll(sel)].filter((el) => keyOf(el) === key)[n] || null;
}"""
)
FOCUSED = (
    "() => {"
    + KEY_JS
    + """
  const el = document.activeElement; if (!el || el === document.body) return null; return keyOf(el);
}"""
)


def _keyboard_reached(page: Any, limit: int = 900) -> set[str]:
    """Tab through the page and collect the keys of everything that took focus, until focus comes back to the same
    element it started on (keys repeat across the page, elements don't)."""
    page.evaluate("document.activeElement && document.activeElement.blur(); window.__qaFirst = null")
    reached: set[str] = set()
    for _ in range(limit):
        page.keyboard.press("Tab")
        back = page.evaluate("() => { const e = document.activeElement; if (!e || e === document.body) return false;"
                             " if (!window.__qaFirst) { window.__qaFirst = e; return false; } return e === window.__qaFirst; }")  # fmt: skip
        if back:
            break
        key = page.evaluate(FOCUSED)
        if key is not None:
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
        el.click(timeout=4000)
        return "toggle"
    if tag == "input" and typ in ("date", "month"):
        el.fill("2026-12-15" if typ == "date" else "2027-03")
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
    el.click(timeout=4000)
    return "click"


class _Effects:
    """What a click caused beyond the page: a file chooser, a download, a new tab, a dialog."""

    def __init__(self, page: Any):
        self.n = 0
        for event in ("filechooser", "download", "popup", "dialog"):
            page.on(event, self._hit)
        page.context.on("page", self._hit)

    def _hit(self, *_: Any) -> None:
        self.n += 1


def _reason(handle: Any) -> str:
    """Why a found control can't be used now ("" when it can)."""
    if handle is None:
        return "vanished after an earlier action"
    if not handle.is_visible():
        return "hidden (in a collapsed section or a closed menu)"
    if not handle.is_enabled():
        return "disabled in this state"
    return ""


def _count(reasons: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in reasons:
        head = r.split(":")[0]
        out[head] = out.get(head, 0) + 1
    return out


@pytest.mark.parametrize("route", ROUTES)
def test_every_control_on_the_route(route, browser, serve, qa, tmp_path):
    srv = serve("film")
    page = new_page(browser, qa, label=f"#/{route}")
    effects = _Effects(page)
    open_route(page, srv.base, route, qa)
    url = page.url
    page.evaluate(
        "document.querySelectorAll('details:not([open])').forEach((d) => { d.open = true; })"
    )  # open sections
    found = page.evaluate(DESCRIBE, INTERACTIVE)
    skipped: dict[str, str] = {}  # control -> why it wasn't exercised
    elements = []
    for e in found:
        ident = f"{e['key']}#{e['n']}"
        if not e["visible"]:
            skipped[ident] = "hidden on load (a collapsed section, a closed menu, another width)"
        elif e["disabled"]:
            skipped[ident] = "disabled on load"
        else:
            elements.append(e)
    for e in elements[MAX_PER_ROUTE:]:
        skipped[f"{e['key']}#{e['n']}"] = f"over the crawler's cap of {MAX_PER_ROUTE} per page"
    elements = elements[:MAX_PER_ROUTE]
    reached = _keyboard_reached(page)
    for e in elements:
        if not e["focusable"] or (e["key"] not in reached and e["tag"] != "canvas"):
            qa.add(
                "keyboard_unreachable", f"{e['tag']} “{e['name']}” isn't reachable with Tab", element=e["key"]
            )
    elements.sort(key=lambda e: bool(RISKY.search(e["name"])))  # risky ones last
    counts = {"exercised": 0, "static": 0}
    retry: list[dict[str, Any]] = []

    def use(e: dict[str, Any], second: bool) -> None:
        ident = f"{e['key']}#{e['n']}"
        if page.url != url:
            open_route(page, srv.base, route)
        if page.locator("[role=dialog][aria-modal=true]").count():  # a dialog left open by an earlier control
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)
            if page.locator("[role=dialog][aria-modal=true]").count():
                page.reload()
                open_route(page, srv.base, route)
        page.evaluate("document.querySelectorAll('details:not([open])').forEach((d) => { d.open = true; })")
        handle = page.evaluate_handle(FIND, [INTERACTIVE, e["key"], e["n"]]).as_element()
        why = _reason(handle)
        if why:
            if not second and why.startswith("vanished"):
                retry.append(e)
            else:
                skipped[ident] = why
            return
        href = e["href"]
        if (
            e["tag"] == "a"
            and href.startswith(("http://", "https://", "mailto:", "webcal:"))
            and "127.0.0.1" not in href
        ):
            counts["static"] += 1  # external: checked, not followed (offline)
            return
        if e["draggable"]:
            counts["static"] += 1  # drag and drop: covered by the flow tests
            return
        current = handle.evaluate("(el) => el.getAttribute('aria-pressed') === 'true' || el.getAttribute('aria-checked') === 'true' "
                                  "|| el.getAttribute('aria-current') === 'page' || el.getAttribute('aria-selected') === 'true'")  # fmt: skip
        before = page.evaluate("() => [window.__qa.mut, location.href]")
        reqs, side = qa.requests, effects.n
        n_findings = len(qa.findings)
        qa.where = f"#/{route} → {e['tag']} “{e['name']}”"
        try:
            how = _exercise(page, handle, e, tmp_path)
        except Exception as exc:
            if not second:
                retry.append(e)
            else:
                skipped[ident] = f"couldn't be used: {str(exc).splitlines()[0][:160]}"
            return
        counts["exercised"] += 1
        page.wait_for_timeout(450)
        try:
            after = page.evaluate("() => [window.__qa.mut, location.href]")
        except Exception:
            after = [None, page.url]
        changed = after[0] != before[0] or after[1] != before[1] or qa.requests != reqs or effects.n != side
        if not changed and how == "click" and (current or (href and url.endswith(href))):
            qa.add(
                "self_link",
                f"{e['tag']} “{e['name']}” is already selected or links to this page",
                element=e["key"],
            )
        elif not changed and how == "click":
            qa.add("dead_control", f"{e['tag']} “{e['name']}” did nothing (no change on screen, no request)",
                   element=e["key"], screenshot=qa.shot(page, f"dead-{route}-{counts['exercised']}"))  # fmt: skip
        if (
            e["tag"] == "a"
            and href.startswith("#/")
            and page.locator("text=The address doesn't match any page here.").count()
        ):
            qa.add("broken_link", f"link “{e['name']}” goes to {href}, which isn't a page", element=e["key"])
        if any(f["error"] for f in qa.findings[n_findings:]):
            qa.findings[-1]["screenshot"] = qa.shot(page, f"err-{route}-{counts['exercised']}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(100)

    for e in elements:
        use(e, second=False)
    if retry:  # a second try on a reloaded page for what vanished or couldn't be used the first time
        open_route(page, srv.base, route)
        for e in retry:
            use(e, second=True)
    qa.coverage = {"route": route, "elements": len(found), "exercised": counts["exercised"], "static": counts["static"],
                   "skipped": len(skipped), "reasons": _count(skipped.values()),
                   "skips": [{"control": k, "reason": v} for k, v in sorted(skipped.items())]}  # fmt: skip
    assert counts["exercised"] + counts["static"] + len(skipped) >= len(found), "a control with no outcome"
    errors = qa.errors()
    assert not errors, "\n".join(f"{f['kind']}: {f['where']}: {f['message']}" for f in errors[:20])


def test_report_dir_is_writable():
    OUT.mkdir(parents=True, exist_ok=True)
    assert OUT.is_dir()
