"""Onboarding (ADR 0008, C2) end to end for the three fictional personas, plus skipping every step, fixing an
answer, resuming, re-running, the model fallback and namesake checks. No real network, no real model."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import anyio
import httpx
import pytest
from fastapi.testclient import TestClient
from test_vault import public_dns  # noqa: F401  (fixture)

from lighthouse_gc.criteria.case import Case
from lighthouse_gc.onboarding import flow
from lighthouse_gc.onboarding.linkedin import extract_with_model
from lighthouse_gc.scaffold import create_workspace
from lighthouse_gc.server.app import create_app

PERSONAS = Path(__file__).parent / "fixtures" / "personas"
W = {"X-Lighthouse": "1"}


def persona(pid: str) -> dict:
    return json.loads((PERSONAS / pid / "persona.json").read_text())


@pytest.fixture
def fresh(tmp_path) -> Case:
    return create_workspace(tmp_path / "case", name="", git=False)


def client_for(ws: Case) -> TestClient:
    return TestClient(create_app(ws, allowed_hosts=["testserver"]))


def upload(c: TestClient, pid: str) -> dict:
    pdf = (PERSONAS / pid / "linkedin.pdf").read_bytes()
    r = c.post("/api/onboarding/linkedin", headers=W, files={"file": ("Profile.pdf", pdf, "application/pdf")})
    assert r.status_code == 200, r.text
    return r.json()


def answer_all(
    c: TestClient, view: dict, target: str = "o1a", when: str = "2027-03", ai: str | None = "skip"
) -> tuple[dict, list[str]]:
    asked = []
    while view["question"]:
        q = view["question"]
        asked.append(q["text"])
        value = {"confirm": None, "choice": target, "month": when}[q["kind"]]
        r = c.post("/api/onboarding/answer", headers=W, json={"id": q["id"], "action": "yes", "value": value})
        assert r.status_code == 200, r.text
        view = r.json()
    if view["state"]["step"] == "ai" and ai:  # Connect your AI comes next; most tests choose "later"
        view = c.post("/api/onboarding/ai", headers=W, json={"choice": ai}).json()
    return view, asked


def arxiv_feed(entries: list[tuple[str, str, str]]) -> str:
    items = "".join(
        f"<entry><id>http://arxiv.org/abs/{aid}v1</id><published>2025-06-01T00:00:00Z</published><title>{title}</title>"
        + "".join(f"<author><name>{a}</name></author>" for a in authors.split(", "))
        + "</entry>"
        for aid, title, authors in entries
    )
    return f'<?xml version="1.0" encoding="UTF-8"?><feed xmlns="http://www.w3.org/2005/Atom"><title>arXiv Query</title>{items}</feed>'


# ----------------------------------------------------------------------------- the three personas


def test_maya_software_engineer(fresh, http_mock):
    c = client_for(fresh)
    assert c.get("/api/onboarding").json()["needed"] is True  # a new workspace opens into onboarding
    view = upload(c, "maya")
    state = view["state"]
    assert state["source"]["redactions"] == 2 and state["source"]["parser"] == "linkedin"
    first = view["question"]
    assert first["id"] == "name" and "Maya Chen" in first["text"]
    view, asked = answer_all(c, view)
    assert any(
        q.startswith("Thanks, Maya. Looks like you're at Northwind Cloud working as Senior Software Engineer")
        for q in asked
    )
    assert any("Judge, HackSeattle 2025" in q for q in asked)
    assert sum(q.startswith("Thanks") for q in asked) == 1  # thanked once, right after the name
    p = persona("maya")
    panel = {line["key"]: line["value"] for line in view["panel"]}
    for key in ("name", "headline", "location", "employer", "role", "education", "awards", "skills", "links"):
        assert panel[key] == p[key], key
    person = fresh.person()
    assert (person.name, person.location, person.field) == (p["name"], p["location"], p["headline"])
    assert str(person.filing_target.target_date) == "2027-03-01" and person.filing_target.profile == "o1a"
    assert view["state"]["step"] == "lookups" and [lk["kind"] for lk in view["state"]["lookups"]] == [
        "github",
        "find",
        "find",
    ]
    assert not http_mock.calls  # nothing went to the web yet

    http_mock.get("https://api.github.com/users/mayachen-example").respond(
        json={"login": "mayachen-example", "type": "User"}
    )
    http_mock.get("https://api.github.com/users/mayachen-example/repos").respond(json=[])
    view = c.post("/api/onboarding/lookups/github", headers=W, json={"accept": True}).json()
    lk = view["state"]["lookups"][0]
    assert lk["status"] == "nothing_found" and "github:mayachen-example" in lk["result"]
    view = c.post(
        "/api/onboarding/step", headers=W, json={"step": "lookups_done"}
    ).json()  # not the web searches
    assert view["state"]["step"] == "chats" and {lk["status"] for lk in view["state"]["lookups"][1:]} == {
        "declined"
    }
    view = c.post("/api/onboarding/step", headers=W, json={"step": "chats_skip"}).json()
    view = c.post("/api/onboarding/step", headers=W, json={"step": "tour_done"}).json()
    assert view["state"]["status"] == "done" and view["needed"] is False


def test_ravi_ai_researcher_papers_with_namesake_check(fresh, http_mock):
    c = client_for(fresh)
    view, asked = answer_all(c, upload(c, "ravi"), target="eb1a")
    assert any(
        q.endswith(
            "You mentioned 2 papers: Sparse Mixture Routing for Efficient Transformers; Calibrated Uncertainty in Vision-Language Models. Is that right?"
        )
        for q in asked
    )
    assert fresh.profile_id() == "eb1a" and fresh.person().filing_target.profile == "eb1a"
    kinds = [lk["kind"] for lk in view["state"]["lookups"]]
    assert kinds == ["papers", "orcid", "find", "find", "find"]
    assert view["state"]["lookups"][0]["prompt"] == "You mentioned 2 papers. Want me to find them on arXiv?"

    feeds = {
        "Sparse Mixture Routing for Efficient Transformers": arxiv_feed([("2507.01111", "Sparse Mixture Routing for Efficient Transformers", "Ravi Iyer, Ana Costa")]),
        "Calibrated Uncertainty in Vision-Language Models": arxiv_feed([("2510.02222", "Calibrated Uncertainty in Vision-Language Models", "Ravi K. Iyengar, Bo Li")]),
    }  # fmt: skip

    def arxiv(request):
        query = request.url.params["search_query"]
        title = next(t for t in feeds if t.split()[0] in query and t.split()[-1] in query)
        return httpx.Response(200, text=feeds[title], headers={"content-type": "application/atom+xml"})

    http_mock.get(url__regex=r"https://export\.arxiv\.org/api/query.*").mock(side_effect=arxiv)
    view = c.post("/api/onboarding/lookups/papers", headers=W, json={"accept": True}).json()
    papers = view["state"]["lookups"][0]
    assert (
        papers["status"] == "found"
        and papers["result"].startswith("2 papers found")
        and "1 flagged as a possible namesake" in papers["result"]
    )
    cands = {c.raw_url: c for c in fresh.pending_candidates() if c.proposed_criterion == "scholarly_articles"}
    own, other = cands["https://arxiv.org/abs/2507.01111"], cands["https://arxiv.org/abs/2510.02222"]
    assert own.facts["namesake_check"] == "passed" and own.confidence == 0.5 and own.stage == "preprint"
    assert (
        other.facts["namesake_check"] == "possible namesake"
        and other.confidence == 0.2
        and "Possible namesake" in other.summary
    )

    view = c.post(
        "/api/onboarding/lookups/orcid", headers=W, json={"accept": False}
    ).json()  # declined: never runs
    assert view["state"]["lookups"][1]["status"] == "declined" and view["state"]["step"] == "lookups"
    assert not any("orcid" in str(call.request.url) for call in http_mock.calls)


@pytest.mark.usefixtures("public_dns")
def test_lena_business_analytics_lead_website(fresh, http_mock):
    c = client_for(fresh)
    view, asked = answer_all(c, upload(c, "lena"))
    assert any("You list 1 certification: Certified Analytics Professional (CAP)" in q for q in asked)
    assert any("Your profile links to lenavogel.example. Is this yours?" in q for q in asked)
    lk = view["state"]["lookups"][0]
    assert [x["kind"] for x in view["state"]["lookups"]] == ["website", "find", "find", "find"]
    assert lk["kind"] == "website" and lk["targets"] == ["https://lenavogel.example"]
    page = ("<html><head><title>Lena Vogel</title></head><body><article><h1>Lena Vogel</h1>"
            + "<p>Lena Vogel won the Analytics Leader of the Year award from the Midwest Data Council in 2025.</p>" * 4
            + "</article></body></html>")  # fmt: skip
    http_mock.get("https://lenavogel.example/").respond(200, text=page, headers={"content-type": "text/html"})
    view = c.post(f"/api/onboarding/lookups/{lk['id']}", headers=W, json={"accept": True}).json()
    assert view["state"]["lookups"][0]["status"] == "found", view["state"]["lookups"][0]["result"]
    assert any(
        c.proposed_criterion == "awards" for c in fresh.pending_candidates()
    )  # via the Inbox, not the case
    assert fresh.exhibits().exhibits == []


# ----------------------------------------------------------------------------- privacy, skipping, resuming


def test_contact_details_never_leave_the_pdf(fresh):
    c = client_for(fresh)
    upload(c, "ravi")
    p = persona("ravi")
    stored = (fresh.data_dir / "onboarding.json").read_text()
    memory = "".join(f.read_text(errors="ignore") for f in (fresh.root / "memory").rglob("*") if f.is_file())
    for secret in p["redacted"]:
        assert secret not in stored and secret not in memory
    assert "[email]" in memory and "[phone]" in memory
    obs = [o for o in fresh.memory.observations() if o.connector == "linkedin"]
    assert (
        obs and obs[0].tier == "self_reported"
    )  # the PDF is self-reported: it never counts toward a criterion
    assert not (fresh.root / "memory" / "sources").exists() or not any(
        f.suffix == ".pdf" for f in (fresh.root / "memory").rglob("*.pdf")
    )  # the PDF itself isn't kept


def test_skip_everything(fresh, http_mock):
    c = client_for(fresh)
    view = c.post("/api/onboarding/step", headers=W, json={"step": "skip_linkedin"}).json()
    assert view["question"]["id"] == "target"  # with no PDF, only the petition question is left
    view = c.post("/api/onboarding/answer", headers=W, json={"id": "target", "action": "skip"}).json()
    assert view["question"]["id"] == "when" and view["question"]["kind"] == "month"
    view = c.post("/api/onboarding/answer", headers=W, json={"id": "when", "action": "skip"}).json()
    assert view["state"]["step"] == "ai" and view["state"]["lookups"] == []
    view = c.post("/api/onboarding/ai", headers=W, json={"choice": "skip"}).json()
    assert view["state"]["step"] == "chats" and view["state"]["ai"] == "skipped"
    assert fresh.person().filing_target.target_date is None
    view = c.post("/api/onboarding/step", headers=W, json={"step": "chats_skip"}).json()
    view = c.post("/api/onboarding/step", headers=W, json={"step": "tour_skip"}).json()
    assert view["state"]["status"] == "done" and view["needed"] is False
    assert fresh.person().name == "" and view["panel"][0]["status"] == "skipped"
    assert not http_mock.calls and fresh.inbox().candidates == []


def test_skipped_answers_stay_blank_and_fixes_are_kept(fresh):
    c = client_for(fresh)
    view = upload(c, "maya")
    view = c.post("/api/onboarding/answer", headers=W, json={"id": "name", "action": "skip"}).json()
    assert fresh.person().name == ""  # nothing guessed
    assert view["question"]["id"] == "role" and not view["question"]["text"].startswith("Thanks")
    view = c.post("/api/onboarding/answer", headers=W, json={"id": "role", "action": "fix",
                                                             "value": {"employer": "Northwind", "role": "Staff Engineer"}}).json()  # fmt: skip
    panel = {line["key"]: line for line in view["panel"]}
    assert panel["name"]["value"] == "" and panel["name"]["status"] == "skipped"
    assert (panel["employer"]["value"], panel["employer"]["status"]) == ("Northwind", "fixed")
    assert panel["role"]["value"] == "Staff Engineer"
    view = c.post(
        "/api/onboarding/answer",
        headers=W,
        json={"id": "location", "action": "fix", "value": "Seattle, Washington, United States"},
    ).json()
    assert {line["key"]: line["status"] for line in view["panel"]}[
        "location"
    ] == "confirmed"  # unchanged: not "edited"
    bad = c.post("/api/onboarding/answer", headers=W, json={"id": "awards", "action": "yes"})
    assert bad.status_code == 400 and "isn't the current one" in bad.text


def test_resumable_and_rerunnable_from_settings(fresh):
    c = client_for(fresh)
    upload(c, "lena")
    c.post("/api/onboarding/answer", headers=W, json={"id": "name", "action": "yes"})
    again = client_for(Case(fresh.root))  # a new server process
    view = again.get("/api/onboarding").json()
    assert (
        view["needed"] is True
        and view["question"]["id"] == "role"
        and "Thanks, Lena." in view["question"]["text"]
    )
    view = again.post("/api/onboarding/step", headers=W, json={"step": "skip_all"}).json()
    assert view["needed"] is False and view["state"]["status"] == "skipped"
    view = again.post("/api/onboarding/restart", headers=W).json()
    assert (
        view["needed"] is True and view["state"]["step"] == "linkedin" and fresh.person().name == "Lena Vogel"
    )
    actions = [ch.action for ch in fresh.changes()]
    assert actions[:2] == ["onboarding.linkedin", "onboarding.answer"] and actions[-1] == "onboarding.restart"


def test_existing_workspaces_dont_get_onboarding(demo_ws):
    assert client_for(demo_ws).get("/api/onboarding").json()["needed"] is False


# ----------------------------------------------------------------------------- model fallback, namesakes


class FakeJudge:
    def __init__(self, reply: str):
        self.reply, self.prompts = reply, []

    async def __call__(self, system, prompt, model):
        self.prompts.append(prompt)
        return type("R", (), {"text": self.reply})()


def test_other_pdfs_use_the_model_and_keep_only_quoted_fields(tmp_path):
    spec = importlib.util.spec_from_file_location("make_pdfs", PERSONAS / "make_pdfs.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = tmp_path / "cv.pdf"
    mod.write_pdf(out, ["Curriculum vitae", "Jordan Park, staff data scientist at Acme Robotics.", "jordan@example.com",
                        "+1 415 555 0100", "Winner of the 2024 Acme Innovation Prize."], "CV")  # fmt: skip
    text, count, parsed = flow.read_pdf(out.read_bytes())
    assert parsed == {} and count == 2 and "jordan@example.com" not in text
    judge = FakeJudge(json.dumps({"fields": {
        "name": {"value": "Jordan Park", "quote": "Jordan Park"},
        "awards": {"value": ["2024 Acme Innovation Prize"], "quote": "Winner of the 2024 Acme Innovation Prize"},
        "publications": {"value": ["A paper they never wrote"], "quote": "Published in Nature"},  # fabricated
        "role": {"value": "CTO", "quote": "chief technology officer"},  # not in the text
    }}))  # fmt: skip
    fields = anyio.run(lambda: extract_with_model(text, judge, "check-model"))
    assert set(fields) == {"name", "awards"}
    assert "@" not in judge.prompts[0] and "555" not in judge.prompts[0]  # the model only saw redacted text


def test_namesake_check():
    assert flow.is_author("Ravi Iyer", [], "Ravi Iyer, Ana Costa")
    assert flow.is_author("Ravi Iyer", [], "R. Iyer and B. Li")
    assert not flow.is_author("Ravi Iyer", [], "Ravi K. Iyengar, Bo Li")
    assert not flow.is_author("Ravi Iyer", [], "Priya Iyer")
    assert flow.is_author("Lena Vogel", ["Magdalena Vogel"], "Magdalena Vogel")
    assert flow.paper_matches(
        "Sparse Mixture Routing for Efficient Transformers",
        "Sparse mixture-routing for efficient transformers",
    )
    assert not flow.paper_matches("Sparse Mixture Routing", "Dense Attention Is All You Need")
    entry = {
        "id": "http://arxiv.org/abs/2510.02222v1",
        "title": "X",
        "authors": "Someone Else",
        "published": "2025",
    }
    cand = flow.paper_candidate(entry, "Ravi Iyer", [])
    assert cand.facts["namesake_check"] == "possible namesake" and cand.confidence == 0.2


# ----------------------------------------------------------------------------- the conversation (C6)


def test_onboarding_opens_with_a_warm_summary_and_keeps_the_conversation(fresh):
    c = client_for(fresh)
    view = upload(c, "ravi")
    [opening] = view["state"]["transcript"]
    assert opening["who"] == "lighthouse"
    assert opening["text"].startswith("I got quite a few things about you. Nice to meet you, Ravi!")
    assert "an award, a judging role, 2 papers and a membership" in opening["text"]
    assert "@" not in opening["text"] and "555" not in opening["text"]  # contact details never reach it
    q = view["question"]
    view = c.post("/api/onboarding/answer", headers=W, json={"id": q["id"], "action": "yes"}).json()
    q2 = view["question"]
    view = c.post("/api/onboarding/answer", headers=W, json={"id": q2["id"], "action": "fix",
                                                             "value": {"employer": "Lakeshore AI", "role": "Scientist"}}).json()  # fmt: skip
    turns = [(t["who"], t["text"]) for t in view["state"]["transcript"]]
    assert turns[1:] == [("lighthouse", q["text"]), ("you", "Yes"), ("lighthouse", q2["text"]),
                         ("you", "Not quite: Lakeshore AI; Scientist")]  # fmt: skip
    assert (
        client_for(fresh).get("/api/onboarding").json()["state"]["transcript"] == view["state"]["transcript"]
    )
    view, asked = answer_all(c, view, target="eb1a")
    assert any(q.endswith("You're a Senior Member of IEEE. Is that right?") for q in asked)
    assert {line["key"]: line["value"] for line in view["panel"]}["memberships"] == ["Senior Member, IEEE"]


def test_the_opening_adapts_to_what_the_pdf_held():
    few = flow.fields_from({"name": {"value": "Sam Lee", "quote": "Sam Lee"}})
    assert flow.opening(few, "linkedin").startswith("I got the basics from your PDF. Nice to meet you, Sam!")
    assert flow.opening(few, "model").startswith(
        "That wasn't a LinkedIn export, but I picked out a few things."
    )
    assert flow.opening([], "none").startswith("I couldn't read much from that PDF, so I'll just ask.")


def test_skipping_the_pdf_still_opens_the_conversation(fresh):
    c = client_for(fresh)
    view = c.post("/api/onboarding/step", headers=W, json={"step": "skip_linkedin"}).json()
    assert view["state"]["transcript"][0]["text"].startswith("No problem, we'll do without it.")
    assert view["question"]["id"] == "target"


# ----------------------------------------------------------------------------- to-dos from what you said (C7)


def _done(c, pid, target="o1a"):
    view, _ = answer_all(c, upload(c, pid), target=target)
    return view


def test_confirmed_items_become_self_reported_todos_linked_to_criteria(fresh):
    c = client_for(fresh)
    _done(c, "ravi", target="eb1a")
    todos = {t.kind: t for t in fresh.todos().todos}
    assert [t.title for t in fresh.todos().todos] == [
        "Upload proof of the Best Paper Award, Workshop on Efficient Machine Learning 2025",
        "Upload proof of your program committee member role at NeurIPS 2025",
        "Upload the published version of “Sparse Mixture Routing for Efficient Transformers”",
        "Upload the published version of “Calibrated Uncertainty in Vision-Language Models”",
        "Upload proof that you're a Senior Member of IEEE",
    ]
    assert {k: t.criterion for k, t in todos.items()} == {"award": "awards", "judging": "judging",
                                                         "publication": "scholarly_articles", "membership": "membership"}  # fmt: skip
    assert all(t.tier == "self_reported" and t.status == "open" for t in fresh.todos().todos)
    week = c.get("/api/overview").json()["tasks"]
    mine = [t for t in week if t["kind"] == "todo"]
    assert (
        len(mine) == 5
        and mine[1]["link"] == "#/evidence?c=judging"
        and mine[1]["criterion_label"] == "Judging"
    )


def test_maya_gets_the_hackseattle_judging_todo(fresh):
    c = client_for(fresh)
    _done(c, "maya")
    assert "Upload proof of HackSeattle 2025 judging" in [t.title for t in fresh.todos().todos]


def test_todos_are_never_evidence(fresh):
    c = client_for(fresh)
    board_before = fresh.scoreboard().model_dump()
    _done(c, "lena")
    assert fresh.todos().todos
    assert fresh.exhibits().exhibits == []
    assert [x.kind for x in fresh.pending_candidates()] == []  # nothing in the Inbox from answers alone
    board = fresh.scoreboard()
    assert board.banked == 0 and board.building == 0
    assert {c_.id: c_.exhibit_count for c_ in board.criteria} == {
        c_["id"]: c_["exhibit_count"] for c_ in board_before["criteria"]
    }
    todo = fresh.todos().todos[0]
    r = c.patch(f"/api/todos/{todo.id}", headers=W, json={"status": "done"})
    assert r.status_code == 200 and r.json()["closed"]
    assert fresh.scoreboard().banked == 0  # ticking it off doesn't bank anything either
    assert todo.id not in [t.get("id") for t in c.get("/api/overview").json()["tasks"]]


def test_skipped_items_make_no_todos_and_rerunning_adds_none_twice(fresh):
    c = client_for(fresh)
    view = upload(c, "maya")
    while view["question"]:
        q = view["question"]
        action = "skip" if q["id"] in ("awards", "judging") else "yes"
        value = {"confirm": None, "choice": "o1a", "month": "2027-03"}[q["kind"]]
        view = c.post(
            "/api/onboarding/answer", headers=W, json={"id": q["id"], "action": action, "value": value}
        ).json()
    assert fresh.todos().todos == []
    c.post("/api/onboarding/restart", headers=W)
    _done(c, "maya")
    _done_again = len(fresh.todos().todos)
    c.post("/api/onboarding/restart", headers=W)
    _done(c, "maya")
    assert len(fresh.todos().todos) == _done_again == 2


# ----------------------------------------------------------------------------- web lookups for those items (C8)


_open_clients: list = []


@pytest.fixture(autouse=True)
def _close_clients():
    yield
    while _open_clients:
        _open_clients.pop().__exit__(None, None, None)


def _finish_questions(ws, pid, engine):
    """A client held open for the whole test: a web search runs as a task on the server's event loop, and a client
    that isn't entered gives each request a loop of its own that closes (cancelling the search) when it returns.
    On a slow machine that cancelled the search before it read anything (seen on CI)."""
    from fastapi.testclient import TestClient as TC

    c = TC(create_app(ws, allowed_hosts=["testserver"], engine=engine)).__enter__()
    _open_clients.append(c)
    view, _ = answer_all(c, upload(c, pid))
    return c, view


def _judging_page(http_mock, names: str) -> str:
    url = "https://hackseattle.example/judges"
    body = (
        f"<p>HackSeattle 2025 judges</p><p>Thank you to everyone who judged HackSeattle 2025: {names}.</p>"
        * 3
    )
    http_mock.get(url).respond(
        200, text=f"<html><body><main>{body}</main></body></html>", headers={"content-type": "text/html"}
    )
    return url


def _script(url: str, quote: str):
    import re as _re

    def propose(outs):
        obs = _re.search(r'"observation_id": "([^"]+)"', outs[-1][2]).group(1)
        return {"criterion": "judging", "evidence_type": "program_committee", "title": "HackSeattle 2025 judge",
                "summary": "Listed among the HackSeattle 2025 judges.", "observation_id": obs, "quote": quote,
                "stage": "completed"}  # fmt: skip

    return [
        ("tool", "read_page", {"url": url}),
        ("tool", "propose_evidence", propose),
        ("text", "Found the judges page."),
    ]


def _wait(c, lookup_id):
    import time

    for _ in range(100):
        lk = next(x for x in c.get("/api/onboarding").json()["state"]["lookups"] if x["id"] == lookup_id)
        if lk["status"] != "searching":
            return lk
        time.sleep(0.05)
    raise AssertionError("the lookup never finished")


@pytest.mark.usefixtures("public_dns")
def test_a_yes_runs_one_web_search_for_the_official_page(fresh, http_mock):
    from agent_fakes import FakeEngine

    url = _judging_page(http_mock, "Maya Chen, Omar Haddad")
    engine = FakeEngine(
        _script(url, "Thank you to everyone who judged HackSeattle 2025: Maya Chen, Omar Haddad.")
    )
    c, view = _finish_questions(fresh, "maya", engine)
    finds = {x["targets"][0]: x for x in view["state"]["lookups"] if x["kind"] == "find"}
    lk = finds["Judge, HackSeattle 2025"]
    assert lk["prompt"] == "Want me to find the official HackSeattle 2025 page that lists you as a judge?"
    assert finds["Northwind Engineering Excellence Award 2024"]["prompt"] == (
        "Want me to look for the official announcement of the Northwind Engineering Excellence Award 2024?"
    )
    assert not engine.requests and not http_mock.calls  # nothing searched before the Yes
    view = c.post(f"/api/onboarding/lookups/{lk['id']}", headers=W, json={"accept": True}).json()
    assert view["state"]["step"] == "lookups"  # waits while the search runs (or Continue)
    done = _wait(c, lk["id"])
    assert done["status"] == "found" and done["result"].startswith("Found 1 page that may confirm it")
    [request] = engine.requests
    assert (
        '"Judge, HackSeattle 2025"' in request.prompt and "only if the page names Maya Chen" in request.prompt
    )
    [cand] = [x for x in fresh.pending_candidates() if x.proposed_criterion == "judging"]
    assert cand.facts["namesake_check"] == "passed" and cand.confidence == 0.5 and cand.raw_url == url
    assert fresh.exhibits().exhibits == []  # the Inbox decides, not the lookup
    view = c.post("/api/onboarding/step", headers=W, json={"step": "lookups_done"}).json()
    saved = next(x for x in view["state"]["lookups"] if x["id"] == lk["id"])
    assert saved["status"] == "found" and view["state"]["step"] == "chats"


@pytest.mark.usefixtures("public_dns")
def test_a_page_that_doesnt_name_you_is_flagged_as_a_possible_namesake(fresh, http_mock):
    from agent_fakes import FakeEngine

    url = _judging_page(http_mock, "M. Chen, Omar Haddad")
    engine = FakeEngine(
        _script(url, "Thank you to everyone who judged HackSeattle 2025: M. Chen, Omar Haddad.")
    )
    c, view = _finish_questions(fresh, "maya", engine)
    lk = next(x for x in view["state"]["lookups"] if x["targets"] == ["Judge, HackSeattle 2025"])
    c.post(f"/api/onboarding/lookups/{lk['id']}", headers=W, json={"accept": True})
    done = _wait(c, lk["id"])
    found = [x for x in fresh.pending_candidates() if x.proposed_criterion == "judging"]
    assert len(found) == 1, (done["status"], done["result"], engine.tool_outputs)
    [cand] = found
    assert cand.facts["namesake_check"] == "possible namesake" and cand.confidence == 0.2
    assert "Possible namesake" in cand.summary


def test_web_lookups_without_ai_say_so_and_search_nothing(fresh, http_mock):
    from agent_fakes import FakeEngine

    class Offline(FakeEngine):
        def available(self):
            return False, "no Claude login or API key"

    c, view = _finish_questions(fresh, "maya", Offline())
    lk = next(x for x in view["state"]["lookups"] if x["kind"] == "find")
    view = c.post(f"/api/onboarding/lookups/{lk['id']}", headers=W, json={"accept": True}).json()
    lk = next(x for x in view["state"]["lookups"] if x["id"] == lk["id"])
    assert lk["status"] == "failed" and lk["result"].startswith("This one needs your AI connected")
    assert not http_mock.calls and fresh.pending_candidates() == []


# ----------------------------------------------------------------------------- back and forth (C11)


def _goto(c, step, question=None):
    r = c.post("/api/onboarding/goto", headers=W, json={"step": step, "question": question})
    return r


def test_back_walks_through_every_question_and_keeps_the_answers(fresh):
    c = client_for(fresh)
    view = upload(c, "maya")
    assert view["nav"]["back"] == {"step": "linkedin"}  # the first question goes back to the PDF step
    view = c.post("/api/onboarding/answer", headers=W, json={"id": "name", "action": "yes"}).json()
    assert view["question"]["id"] == "role" and view["nav"]["back"] == {
        "step": "questions",
        "question": "name",
    }
    view = _goto(c, "questions", "name").json()
    assert (
        view["question"]["id"] == "name" and "Maya Chen" in view["question"]["text"]
    )  # the earlier answer, again
    assert {line["key"]: line["status"] for line in view["panel"]}["name"] == "confirmed"  # still answered
    view = c.post(
        "/api/onboarding/answer", headers=W, json={"id": "name", "action": "fix", "value": "Maya L. Chen"}
    ).json()
    assert view["question"]["id"] == "role"  # back to where it left off
    assert {line["key"]: line["value"] for line in view["panel"]}["name"] == "Maya L. Chen"
    assert fresh.person().name == "Maya L. Chen"


def test_changing_an_answer_on_the_way_back_reoffers_only_what_it_affects(fresh, http_mock):
    c = client_for(fresh)
    view, _ = answer_all(c, upload(c, "maya"))
    assert view["state"]["step"] == "lookups" and view["nav"]["back"] == {"step": "ai"}
    http_mock.get("https://api.github.com/users/mayachen-example").respond(
        json={"login": "mayachen-example", "type": "User"}
    )
    http_mock.get("https://api.github.com/users/mayachen-example/repos").respond(json=[])
    c.post("/api/onboarding/lookups/github", headers=W, json={"accept": True})
    judging = next(
        x
        for x in c.get("/api/onboarding").json()["state"]["lookups"]
        if x["targets"] == ["Judge, HackSeattle 2025"]
    )
    c.post(f"/api/onboarding/lookups/{judging['id']}", headers=W, json={"accept": False})
    before = {x["id"]: x["status"] for x in c.get("/api/onboarding").json()["state"]["lookups"]}

    view = _goto(c, "questions", "judging").json()
    assert view["question"]["id"] == "judging"
    view = c.post("/api/onboarding/answer", headers=W, json={"id": "judging", "action": "fix",
                                                             "value": "Judge, HackSeattle 2026"}).json()  # fmt: skip
    assert view["state"]["step"] == "lookups"
    after = {x["targets"][0]: x for x in view["state"]["lookups"]}
    assert after["Judge, HackSeattle 2026"]["status"] == "offered"  # the changed answer is offered again
    assert "Judge, HackSeattle 2025" not in after
    assert after["https://github.com/mayachen-example"]["status"] == before["github"]  # unchanged: kept
    titles = {t.title: t.status for t in fresh.todos().todos}
    assert titles["Upload proof of HackSeattle 2026 judging"] == "open"
    assert (
        titles["Upload proof of HackSeattle 2025 judging"] == "dismissed"
    )  # the old answer's to-do goes away


def test_a_skipped_answer_can_be_revisited_with_what_the_pdf_said(fresh):
    c = client_for(fresh)
    view = upload(c, "lena")
    c.post("/api/onboarding/answer", headers=W, json={"id": "name", "action": "yes"})
    c.post("/api/onboarding/answer", headers=W, json={"id": "role", "action": "skip"})
    assert {line["key"]: line["status"] for line in c.get("/api/onboarding").json()["panel"]}[
        "role"
    ] == "skipped"
    view = _goto(c, "questions", "role").json()
    assert "Brightline Retail" in view["question"]["text"]  # the PDF's words come back, not a blank
    view = c.post("/api/onboarding/answer", headers=W, json={"id": "role", "action": "yes"}).json()
    panel = {line["key"]: line for line in view["panel"]}
    assert panel["employer"]["value"] == "Brightline Retail" and panel["employer"]["status"] == "confirmed"


def test_the_step_bar_only_goes_to_steps_already_reached(fresh):
    c = client_for(fresh)
    view = upload(c, "maya")
    assert [s["reachable"] for s in view["nav"]["steps"]] == [True, True, False, False, False, False]
    assert _goto(c, "chats").status_code == 409
    assert _goto(c, "questions", "awards").status_code == 409  # can't skip ahead to an unanswered question
    view, _ = answer_all(c, view)
    view = c.post("/api/onboarding/step", headers=W, json={"step": "lookups_done"}).json()
    assert view["state"]["step"] == "chats" and view["nav"]["back"] == {"step": "lookups"}
    view = _goto(c, "linkedin").json()  # all the way back; nothing is lost
    assert (
        view["state"]["step"] == "linkedin"
        and len([x for x in view["panel"] if x["status"] != "pending"]) > 5
    )
    view = _goto(c, "chats").json()  # and forward again
    assert view["state"]["step"] == "chats"
    view = _goto(c, "questions").json()  # all answered: reopens the last question
    assert view["question"]["id"] == "when"
