"""Every page in light and dark, at laptop and phone width, for the filming workspace and the three personas:
uncaught errors, console errors, failed requests, axe-core violations (serious and critical fail), horizontal
overflow, and pages that take more than a second to show."""

from __future__ import annotations

import pytest

from .harness import ROUTES, axe, new_page, open_route, overflow

SCENARIOS = ["film", "persona:maya", "persona:ravi", "persona:lena"]


@pytest.mark.parametrize("size", ["laptop", "phone"])
@pytest.mark.parametrize("theme", ["light", "dark"])
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_every_page(scenario, theme, size, browser, shared, qa):
    srv = shared(scenario)
    page = new_page(browser, qa, theme=theme, size=size)
    for route in ROUTES:
        qa.where = f"{scenario} #/{route} {theme} {size}"
        took = open_route(page, srv.base, route, qa)
        if took > 1.0:
            qa.add("slow", f"#/{route} took {took:.1f}s to show", seconds=round(took, 2))
        over = overflow(page)
        if over > 1:
            qa.add(
                "overflow",
                f"#/{route} scrolls sideways by {over}px",
                screenshot=qa.shot(page, f"overflow-{route}"),
            )
        for v in axe(page):
            serious = v["impact"] in ("serious", "critical")
            qa.add("axe" if serious else "axe_minor", f"{v['id']} ({v['impact']}): {v['help']} on {v['nodes']} element(s)",
                   targets=v["targets"])  # fmt: skip
            if serious:
                qa.findings[-1]["error"] = True
    page.context.close()
    errors = qa.errors()
    assert not errors, "\n".join(f"{f['kind']}: {f['where']}: {f['message']}" for f in errors[:25])
