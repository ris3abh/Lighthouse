"""Flow tests: what a person does, end to end, in a real browser, on throwaway fictional workspaces. Each flow
checks what changed on the page and in the workspace (through the API), and that nothing errored on the way."""

from __future__ import annotations

import json
import re
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from .harness import ROOT, new_page, open_route

PERSONAS = ROOT / "tests" / "fixtures" / "personas"
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
W = {"X-AreaO1": "1", "content-type": "application/json"}


def api(srv: Any, path: str, body: Any = None, method: str | None = None) -> Any:
    req = urllib.request.Request(srv.base + "/api" + path, data=None if body is None else json.dumps(body).encode(),
                                 headers=W, method=method or ("POST" if body is not None else "GET"))  # fmt: skip
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read() or b"null")


@contextmanager
def step(qa: Any, page: Any, name: str):
    """A named step: a failure is recorded with a screenshot, then raised."""
    qa.where = name
    try:
        yield
    except Exception as exc:
        qa.add(
            "flow",
            f"{name}: {str(exc).splitlines()[0][:300]}",
            screenshot=qa.shot(page, re.sub(r"\W+", "-", name)[:60]),
        )
        raise


def soft(qa: Any, page: Any, ok: bool, message: str) -> bool:
    """A check that records a bug (with a screenshot) but lets the flow carry on."""
    if not ok:
        qa.add("flow", message, screenshot=qa.shot(page, re.sub(r"\W+", "-", message)[:60]))
    return ok


def button(page: Any, name: str, exact: bool = False) -> Any:
    return page.get_by_role(
        "button", name=re.compile(name if not exact else f"^{re.escape(name)}$", re.I)
    ).first


def no_errors(qa: Any) -> None:
    errors = qa.errors()  # including bugs a soft check recorded
    assert not errors, "\n".join(f"{f['kind']}: {f['where']}: {f['message']}" for f in errors[:15])


def drop_files(page: Any, target: Any, files: list[tuple[str, bytes, str]]) -> None:
    """Drop files onto an element the way a browser does (a DataTransfer with File objects)."""
    payload = [{"name": n, "type": t, "data": list(b)} for n, b, t in files]
    dt = page.evaluate_handle("""(files) => { const dt = new DataTransfer();
        for (const f of files) dt.items.add(new File([new Uint8Array(f.data)], f.name, { type: f.type }));
        return dt; }""", payload)  # fmt: skip
    for ev in ("dragenter", "dragover", "drop"):
        target.dispatch_event(ev, {"dataTransfer": dt})


# ------------------------------------------------------------------------------------------- onboarding


def _drive_onboarding(page: Any, qa: Any, pdf: Path | None) -> list[str]:
    """Answer everything the conversation asks (yes / O-1A / a month), skip lookups, chats and mail, finish the tour."""
    seen: list[str] = []
    dialog = page.get_by_role("dialog", name=re.compile("Getting started"))
    with step(qa, page, "onboarding opens on an empty workspace"):
        dialog.wait_for(timeout=15000)
    if pdf:
        with step(qa, page, "upload the LinkedIn PDF"):
            dialog.locator("input[type=file]").set_input_files(str(pdf))
            page.wait_for_timeout(1200)
    for _ in range(40):
        page.wait_for_timeout(350)
        if not dialog.is_visible():
            break
        q = dialog.locator("h1, h2, [role=log] p").last.text_content(timeout=2000) or ""
        seen.append(q.strip()[:80])
        month = dialog.locator("input[type=month]")
        if month.count() and month.first.is_visible():
            month.first.fill("2027-03")
            button(dialog, "^Save").click()
            continue
        for name in ("Not now, continue", "Later, in Settings", "Skip for now", "^Continue", "Keep my answers and continue",
                     "^Yes$", "^Yes, that's right", "O-1A"):  # fmt: skip
            b = button(dialog, name)
            if b.count() and b.is_visible() and b.is_enabled():
                b.click()
                break
        else:
            page.wait_for_timeout(600)
    with step(qa, page, "the tour and the finale lead to the dashboard"):
        tour = page.get_by_role("dialog", name="Guided tour")
        idle = 0
        for _ in range(40):
            for b in (tour.get_by_role("button", name="Next"), tour.get_by_role("button", name="Finish"),
                      button(page, "Open my dashboard")):  # fmt: skip
                if b.count() and b.first.is_visible():
                    b.first.click()
                    page.wait_for_timeout(400)
                    idle = 0
                    break
            else:
                idle += 1
                if idle > 6:
                    break
                page.wait_for_timeout(500)
        page.get_by_text("Criteria scoreboard").first.wait_for(timeout=10000)
    return seen


@pytest.mark.parametrize("pid", ["maya", "ravi", "lena"])
def test_onboarding_for_each_persona(pid, browser, serve, qa):
    srv = serve("empty")
    page = new_page(browser, qa)
    open_route(page, srv.base, "overview")
    _drive_onboarding(page, qa, PERSONAS / pid / "linkedin.pdf")
    persona = json.loads((PERSONAS / pid / "persona.json").read_text())
    with step(qa, page, "the profile and the scoreboard show"):
        state = api(srv, "/onboarding")
        assert state["state"]["status"] == "done", state["state"]
        assert persona["name"] in page.locator("header").first.text_content()
    no_errors(qa)


def test_onboarding_skip_everything(browser, serve, qa):
    srv = serve("empty")
    page = new_page(browser, qa)
    open_route(page, srv.base, "overview")
    with step(qa, page, "Skip setup closes onboarding"):
        button(page, "Skip setup").click()
        page.wait_for_timeout(800)
        for name in ("Skip the tour", "^Finish", "Open my dashboard"):
            b = button(page, name)
            if b.count() and b.is_visible():
                b.click()
                page.wait_for_timeout(300)
        assert not page.get_by_role("dialog", name=re.compile("Getting started")).is_visible()
        assert api(srv, "/onboarding")["state"]["status"] in ("done", "skipped")
    no_errors(qa)


def test_onboarding_back_and_browser_history(browser, serve, qa):
    srv = serve("empty")
    page = new_page(browser, qa)
    open_route(page, srv.base, "overview")
    dialog = page.get_by_role("dialog", name=re.compile("Getting started"))
    dialog.wait_for()
    dialog.locator("input[type=file]").set_input_files(str(PERSONAS / "maya" / "linkedin.pdf"))
    page.wait_for_timeout(1500)
    with step(qa, page, "answer one question, then Back returns to it"):
        before = api(srv, "/onboarding")["question"]
        assert before, "no question after the PDF"
        button(dialog, "^Yes").click()
        page.wait_for_timeout(800)
        after = api(srv, "/onboarding")["question"]
        assert after and after["id"] != before["id"]
        dialog.get_by_role("button", name="Back").click()
        page.wait_for_timeout(800)
        assert api(srv, "/onboarding")["question"]["id"] == before["id"]
    with step(qa, page, "browser back and forward keep onboarding usable"):
        page.go_back()
        page.wait_for_timeout(600)
        page.go_forward()
        page.wait_for_timeout(600)
        page.reload()
        dialog.wait_for(timeout=10000)
        assert button(dialog, "^Yes").is_visible() or dialog.locator("input[type=month]").count()
    no_errors(qa)


# ------------------------------------------------------------------------------------------- inbox, upload


def test_inbox_edit_reject_accept(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "inbox")
    pending = [c for c in api(srv, "/inbox") if c.get("status", "pending") == "pending"]
    assert len(pending) >= 3, [c["title"] for c in pending]
    with step(qa, page, "Edit a candidate's summary"):
        button(page, "^Edit$").click()
        box = page.get_by_label(re.compile("^Summary")).first
        box.fill("Edited by the QA suite")
        button(page, "Save without accepting").click()
        page.wait_for_timeout(700)
        assert any(c["summary"] == "Edited by the QA suite" for c in api(srv, "/inbox"))
        page.wait_for_timeout(2300)
        card = page.locator("article, section, li", has=page.get_by_text("Edited by the QA suite")).last
        if not soft(qa, page, card.get_by_role("button", name="Reject").is_enabled(),
                    "after Save without accepting, the card's buttons stay disabled"):  # fmt: skip
            page.reload()
            page.wait_for_timeout(800)
    with step(qa, page, "Reject removes one"):
        n = len([c for c in api(srv, "/inbox") if c.get("status", "pending") == "pending"])
        button(page, "^Reject$").click()
        page.wait_for_timeout(700)
        assert len([c for c in api(srv, "/inbox") if c.get("status", "pending") == "pending"]) == n - 1
    with step(qa, page, "Accept files an exhibit"):
        exhibits = sum(len(c["exhibits"]) for c in api(srv, "/exhibits")["criteria"])
        button(page, "^Accept$").click()
        page.wait_for_timeout(1000)
        assert sum(len(c["exhibits"]) for c in api(srv, "/exhibits")["criteria"]) == exhibits + 1
    no_errors(qa)


def test_drag_and_drop_upload_and_eml_import(browser, serve, qa):
    from .serve import thank_you_eml

    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "evidence")
    before = len(api(srv, "/inbox"))
    with step(qa, page, "drop a PDF on Evidence: it goes to the Inbox"):
        drop_files(
            page,
            page.locator("text=Drop certificates").first,
            [("qa-certificate.pdf", PDF.replace(b"1 0 obj", b"1 0 obj % qa"), "application/pdf")],
        )  # new bytes
        page.wait_for_url(re.compile("#/inbox"), timeout=10000)
        assert len(api(srv, "/inbox")) == before + 1
    with step(qa, page, "drop an .eml on the Inbox: checked for a verified sender"):
        eml = thank_you_eml("Maya Chen", "Lakeview Jam 2026")
        drop_files(
            page, page.locator("text=Drop files or emails").first, [("lakeview.eml", eml, "message/rfc822")]
        )
        page.wait_for_timeout(1500)
        cand = next(c for c in api(srv, "/inbox") if "Lakeview Jam 2026" in c["title"])
        assert (
            "Verified sender" in cand["summary"] or cand.get("facts", {}).get("sender_check") == "verified"
        ), cand
        assert page.locator("text=Lakeview Jam 2026").first.is_visible()
    no_errors(qa)


# ------------------------------------------------------------------------------------------- evidence


def test_proof_recipe_checklist(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "evidence")
    first = api(srv, "/proof")["checklists"][0]
    anchor = first["anchor"]
    panel = page.locator(f"[id='proof-{anchor}']")
    with step(qa, page, "mark an item not applicable, with a reason"):
        row = panel.locator("li", has=page.get_by_text(first["items"][1]["label"], exact=True)).first
        button(row, "Not applicable").click()
        row.get_by_placeholder("Why it doesn't apply").fill("The organizer never sent one")
        button(row, "^Save$").click()
        page.wait_for_timeout(700)
        item = next(
            i
            for c in api(srv, "/proof")["checklists"]
            if c["anchor"] == anchor
            for i in c["items"]
            if i["id"] == first["items"][1]["id"]
        )
        assert item["status"] == "waived"
    with step(qa, page, "upload from the checklist links the new exhibit"):
        missing = next(
            i
            for c in api(srv, "/proof")["checklists"]
            if c["anchor"] == anchor
            for i in c["items"]
            if i["status"] == "missing"
        )
        row = panel.locator("li", has=page.get_by_text(missing["label"], exact=True)).first
        button(row, "^Upload$").click()
        modal = page.get_by_role("dialog")
        f = Path(srv.dir) / "proof.pdf"
        f.write_bytes(PDF)
        modal.locator("input[type=file]").set_input_files(str(f))
        button(modal, "File exhibit").click()
        page.wait_for_timeout(1000)
        item = next(
            i
            for c in api(srv, "/proof")["checklists"]
            if c["anchor"] == anchor
            for i in c["items"]
            if i["id"] == missing["id"]
        )
        assert item["status"] == "done" and item["via"] == "linked"
    no_errors(qa)


def test_preflight_run_and_dismiss(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "evidence")
    with step(qa, page, "Run preflight lists issues"):
        button(page, "Run preflight").click()
        page.get_by_text(re.compile(r"Preflight · \d+ open issue")).wait_for(timeout=15000)
        report = api(srv, "/preflight")["report"]
        assert report and report["issues"]
    with step(qa, page, "dismiss one with a reason; it stays dismissed after a rerun"):
        n = sum(1 for i in report["issues"] if not i["dismissed"])
        page.get_by_text("Not a problem…").first.click()
        page.get_by_placeholder("Why it isn't a problem").fill("Checked with my attorney")
        button(page, "^Dismiss$").click()
        page.wait_for_timeout(700)
        button(page, "Run again").click()
        page.wait_for_timeout(1500)
        again = api(srv, "/preflight")["report"]
        assert sum(1 for i in again["issues"] if not i["dismissed"]) == n - 1
    no_errors(qa)


# ------------------------------------------------------------------------------------------- agent


def test_chat_action_and_undo(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "overview")
    with step(qa, page, "ask a question; the answer streams with its tool calls"):
        button(page, "^Ask$").click()
        page.get_by_label("Message").fill("Where do I stand?")
        page.get_by_role("button", name="Send").click()
        page.get_by_text("Here's where you stand").first.wait_for(timeout=30000)
    with step(qa, page, "the chat's change can be undone from the chat"):
        assert any(d["title"] == "QA follow-up deadline" for d in api(srv, "/deadlines"))
        button(page, "^Undo$").click()
        page.get_by_text("Undone").first.wait_for(timeout=10000)
        assert not any(d["title"] == "QA follow-up deadline" for d in api(srv, "/deadlines"))
    no_errors(qa)


def test_approve_and_send_with_the_undo_window(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "contacts")
    with step(qa, page, "Approve & send starts the undo window; Undo send stops it"):
        button(page, "Approve & send").click()
        button(page, "Undo send").wait_for(timeout=5000)
        button(page, "Undo send").click()
        page.wait_for_timeout(800)
        assert button(page, "Approve & send").is_visible()
        assert api(srv, "/outreach")["sent_today"] == 0
    with step(qa, page, "approved again, it sends when the window ends"):
        button(page, "Approve & send").click()
        page.wait_for_timeout(6500)
        assert api(srv, "/outreach")["sent_today"] == 1
        assert page.get_by_text("1 of 10 sent today").is_visible()
    no_errors(qa)


# ------------------------------------------------------------------------------------------- trackers


def test_calendar_drag_and_edit(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "calendar")
    dl = sorted(api(srv, "/deadlines"), key=lambda d: d["due"])[0]
    with step(qa, page, "drag a deadline to another day"):
        import datetime as dt

        chip = page.locator("[draggable=true]", has_text=dl["title"][:12]).first
        due = dt.date.fromisoformat(dl["due"])
        target = due + dt.timedelta(days=2 if due.day < 26 else -2)
        cell = page.locator(
            f"xpath=//div[contains(@class,'min-h-28')][./*[1][normalize-space()='{target.day}']]"
        ).first
        chip.drag_to(cell)
        page.wait_for_timeout(800)
        assert next(d for d in api(srv, "/deadlines") if d["id"] == dl["id"])["due"] == target.isoformat()
    with step(qa, page, "click a deadline to edit its title"):
        page.locator("[draggable=true]", has_text=dl["title"][:12]).first.click()
        modal = page.get_by_role("dialog")
        modal.get_by_label("Title").fill("Renamed by QA")
        button(modal, "^Save").click()
        page.wait_for_timeout(700)
        assert next(d for d in api(srv, "/deadlines") if d["id"] == dl["id"])["title"] == "Renamed by QA"
    no_errors(qa)


def test_pipeline_moves(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "pipeline")
    item = next(i for i in api(srv, "/pipeline") if i["stage"] == "idea")
    with step(qa, page, "Move right with the button"):
        card = page.locator("[draggable]", has_text=item["title"]).first
        card.get_by_role("button", name="Move right").click()
        page.wait_for_timeout(700)
        assert next(i for i in api(srv, "/pipeline") if i["id"] == item["id"])["stage"] == "applied"
    with step(qa, page, "drag it to Done"):
        card = page.locator("[draggable]", has_text=item["title"]).first
        card.drag_to(page.get_by_role("heading", name="Done").first)
        page.wait_for_timeout(800)
        assert next(i for i in api(srv, "/pipeline") if i["id"] == item["id"])["stage"] == "done"
    no_errors(qa)


def test_letters_add_draft_and_send(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "letters")
    with step(qa, page, "add a writer"):
        page.get_by_label(re.compile("^Name$")).last.fill("Prof. QA Writer")
        button(page, "Add writer").click()
        page.get_by_text("Prof. QA Writer").first.wait_for(timeout=5000)
    with step(qa, page, "draft from approved claims"):
        page.get_by_text("Draft from claims").first.click()
        page.wait_for_timeout(1500)
        lt = next(x for x in api(srv, "/letters")["letters"] if x["name"] == "Dr. Priya Natarajan")
        assert lt["draft_path"], lt
    with step(qa, page, "send to the writer waits for approval on Contacts"):
        sent = page.get_by_role("button", name=re.compile("^Send to"))
        sent.first.click()
        page.wait_for_timeout(1000)
        drafts = api(srv, "/outreach")["drafts"]
        assert any(d.get("drafted_by") == "letters" and d["status"] == "draft" for d in drafts)
    no_errors(qa)


def test_contacts_and_the_mail_view(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "contacts")
    with step(qa, page, "add a contact"):
        button(page, "Add a contact").click()
        card = page.locator("section", has=page.get_by_text("New contact", exact=True)).first
        card.get_by_label(re.compile("^Name")).fill("Dr. QA Contact")
        button(card, "^(Save|Add)").click()
        page.get_by_text("Dr. QA Contact").first.wait_for(timeout=5000)
    with step(qa, page, "Mail: filter a category, move a message, open its text"):
        page.get_by_role("button", name=re.compile("^Mail$")).first.click()
        page.wait_for_timeout(600)
        page.get_by_role("button", name=re.compile("Judging & hackathons")).first.click()
        page.wait_for_timeout(400)
        select = page.get_by_label("Move to").first
        select.select_option(index=1)
        page.wait_for_timeout(800)
        box = api(srv, "/mail")
        assert any(i["by"] == "you" for i in box["items"]), box["items"]
    no_errors(qa)


def test_knowledge_pairing_and_check(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "knowledge")
    with step(qa, page, "get a pairing code"):
        button(page, "Get a pairing code").click()
        page.get_by_text("Good for ten minutes, once.").wait_for(timeout=5000)
    with step(qa, page, "check what's due (offline: sources show as unreadable, nothing breaks)"):
        button(page, "Check what's due").click()
        page.wait_for_timeout(4000)
    no_errors(qa)


def test_constellation_filters_slider_and_star(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "memory")
    with step(qa, page, "filter by criterion and status"):
        page.locator("select").first.select_option("judging")
        button(page, "^Pending$").click()
        page.wait_for_timeout(400)
    with step(qa, page, "the time slider shows the case up to a date"):
        slider = page.get_by_label("Show the case up to this date")
        slider.focus()
        for _ in range(5):
            page.keyboard.press("ArrowLeft")
        page.wait_for_timeout(300)
    with step(qa, page, "click a star (from the list view) for its trail"):
        page.get_by_role("button", name=re.compile("^List$")).click()
        page.locator("main li button, main tr button, main [role=row]").first.click()
        page.get_by_label("Provenance").wait_for(timeout=5000)
    with step(qa, page, "a claim link opens its trail directly"):
        star = api(srv, "/memory/constellation")["stars"][0]
        open_route(page, srv.base, f"memory?claim={star['id']}")
        page.get_by_label("Provenance").wait_for(timeout=5000)
    no_errors(qa)


# ------------------------------------------------------------------------------------------- settings


def test_settings_toggles_persist(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "settings")
    for label in ("Cheap mode", "Model sorting", "Daily opportunity check"):
        with step(qa, page, f"toggle {label} and it persists"):
            row = page.locator("div, section", has=page.get_by_text(label, exact=True)).last
            toggle = row.locator("button[aria-pressed]").first
            before = toggle.get_attribute("aria-pressed")
            toggle.click()
            page.wait_for_timeout(700)
            page.reload()
            open_route(page, srv.base, "settings")
            row = page.locator("div, section", has=page.get_by_text(label, exact=True)).last
            assert row.locator("button[aria-pressed]").first.get_attribute("aria-pressed") != before
    no_errors(qa)


def test_theme_switch(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "overview")
    with step(qa, page, "dark, then light, then reload keeps it"):
        page.locator("[title='Theme: dark']").first.click()
        assert "dark" in (page.locator("html").get_attribute("class") or "")
        page.locator("[title='Theme: light']").first.click()
        assert "dark" not in (page.locator("html").get_attribute("class") or "")
        page.reload()
        page.wait_for_timeout(500)
        assert "dark" not in (page.locator("html").get_attribute("class") or "")
    no_errors(qa)


def test_cheap_mode_from_the_chat(browser, serve, qa):
    srv = serve("film")
    page = new_page(browser, qa)
    open_route(page, srv.base, "overview")
    with step(qa, page, "cheap mode in the chat panel is the same setting"):
        button(page, "^Ask$").click()
        before = api(srv, "/agent/status").get("cheap_mode")
        page.get_by_role("button", name="Cheap mode").click()
        page.wait_for_timeout(700)
        assert api(srv, "/agent/status").get("cheap_mode") is (not before)
    no_errors(qa)


# ------------------------------------------------------------------------------------------- run once (B3)


def test_double_clicking_anything_that_costs_or_sends_does_it_once(browser, serve, qa):
    """Every action that costs a model call, reads the network or sends something, double-clicked: one request
    reaches the server (the button is busy, identical requests are merged) and one thing happens."""
    srv = serve("film")
    page = new_page(browser, qa)
    posts: list[str] = []
    page.on(
        "request",
        lambda r: (
            posts.append(r.url.split("/api", 1)[1].split("?")[0])
            if r.method == "POST" and "/api/" in r.url
            else None
        ),
    )

    def once(route: str, target: Any, path: str, settle: int = 1500) -> None:
        open_route(page, srv.base, route)
        posts.clear()
        with step(qa, page, f"double-click on {route}: {path}"):
            target().dblclick()
            page.wait_for_timeout(settle)
            n = sum(1 for p in posts if re.fullmatch(path, p))
            assert n == 1, f"{n} requests to {path}"

    once("letters", lambda: page.get_by_text("Draft from claims").first, r"/letters/[^/]+/draft", 2500)
    drafts = len(api(srv, "/outreach")["drafts"])
    once(
        "letters",
        lambda: page.get_by_role("button", name=re.compile("^Send to ")).first,
        r"/letters/[^/]+/send",
    )
    assert len(api(srv, "/outreach")["drafts"]) == drafts + 1
    runs = len(api(srv, "/agent/runs"))
    once("agent", lambda: button(page, "^Run now$"), r"/agent/missions/[^/]+/run")
    once("overview", lambda: button(page, "^Refresh$"), r"/agent/missions/what_changed/run")
    assert len(api(srv, "/agent/runs")) == runs + 2
    once("contacts", lambda: button(page, "Refresh threads"), r"/gmail/sync")
    once("contacts?view=mail", lambda: button(page, "Refresh mail"), r"/mail/sync")
    once("knowledge", lambda: button(page, "Check what's due"), r"/knowledge/sync", 4000)
    once(
        "settings",
        lambda: (
            page.locator("div", has=page.get_by_text("Daily opportunity check", exact=True))
            .get_by_role("button", name="Check now")
            .last
        ),
        r"/opportunities/run",
    )
    once("metrics", lambda: button(page, "Snapshot now"), r"/metrics/snapshot")
    sent = api(srv, "/outreach")["sent_today"]
    once("contacts", lambda: button(page, "Approve & send"), r"/outreach/[^/]+/send", 5500)
    assert api(srv, "/outreach")["sent_today"] == sent + 1  # one email, after the undo window
    with step(qa, page, "chat: Enter twice sends once"):
        open_route(page, srv.base, "overview")
        before = len(api(srv, "/agent/runs"))
        button(page, "^Ask$").click()
        box = page.get_by_label("Message")
        box.fill("Where do I stand?")
        posts.clear()
        box.press("Enter")
        box.press("Enter")
        page.wait_for_timeout(2500)
        assert sum(1 for p in posts if p == "/agent/chat") == 1 and len(api(srv, "/agent/runs")) == before + 1
    # Onboarding lookups, on a new workspace at the find-your-work step.
    fresh = serve("empty")
    open_route(page, fresh.base, "overview")
    dialog = page.get_by_role("dialog", name=re.compile("Getting started"))
    dialog.locator("input[type=file]").set_input_files(str(PERSONAS / "ravi" / "linkedin.pdf"))
    for _ in range(30):
        page.wait_for_timeout(400)
        if dialog.get_by_role("button", name=re.compile("^Yes, look")).count():
            break
        for name in ("^Yes$", "O-1A", "Later, in Settings"):
            b = button(dialog, name)
            if b.count() and b.is_visible() and b.is_enabled():
                b.click()
                break
        month = dialog.locator("input[type=month]")
        if month.count() and month.first.is_visible():
            month.first.fill("2027-03")
            button(dialog, "^Save").click()
    with step(qa, page, "onboarding: a lookup double-clicked starts once"):
        posts.clear()
        dialog.get_by_role("button", name=re.compile("^Yes, look")).first.dblclick()
        page.wait_for_timeout(1500)
        assert sum(1 for p in posts if p.startswith("/onboarding/lookups/")) == 1


# ------------------------------------------------------------------------------------------- QA fixes (F4)


def test_qa_fixes_in_the_browser(browser, serve, qa):
    """B5 Ask focuses the message box, B7 Evidence deep links land on the criterion, B8 long words wrap in a pipeline
    card, B20 the calendar subscribe link copes without clipboard permission. (B1 is in the Inbox flow.)"""
    srv = serve("film")
    page = new_page(browser, qa)
    with step(qa, page, "B5: Ask, then type"):
        open_route(page, srv.base, "overview")
        button(page, "^Ask$").click()
        page.wait_for_timeout(500)
        page.keyboard.type("Hello")
        assert page.get_by_label("Message").input_value() == "Hello"
        page.keyboard.press("Escape")
    with step(qa, page, "B7: #/evidence?c=membership lands on Membership"):
        open_route(page, srv.base, "overview")
        page.evaluate("location.hash = '#/evidence?c=membership'")
        page.wait_for_timeout(3500)
        top = page.evaluate("document.getElementById('crit-membership').getBoundingClientRect().top")
        assert -10 <= top <= 120, f"Membership is {top}px from the top"
    with step(qa, page, "B8: a long word wraps inside its pipeline card"):
        open_route(page, srv.base, "pipeline")
        box = page.get_by_label("New idea")
        box.fill("Keynote-" + "A" * 120 + " proposal")
        box.press("Enter")
        page.wait_for_timeout(800)
        card = page.locator("[draggable]", has_text="Keynote-").first
        spill = card.evaluate(
            "(c) => [...c.querySelectorAll('*')].some((x) => x.scrollWidth > c.clientWidth + 1)"
        )
        assert not spill
    with step(qa, page, "B20: no clipboard permission: the link is shown, nothing throws"):
        open_route(page, srv.base, "calendar")
        page.evaluate(
            "() => { navigator.clipboard.writeText = () => Promise.reject(new DOMException('Write permission denied.', 'NotAllowedError')); }"
        )
        n = len(qa.errors())
        button(page, "Subscribe link").click()
        page.get_by_text(re.compile("Copy this link into your calendar app: webcal://")).wait_for(
            timeout=3000
        )
        assert len(qa.errors()) == n
    no_errors(qa)
