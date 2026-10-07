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
    c: TestClient, view: dict, target: str = "o1a", when: str = "2027-03"
) -> tuple[dict, list[str]]:
    asked = []
    while view["question"]:
        q = view["question"]
        asked.append(q["text"])
        value = {"confirm": None, "choice": target, "month": when}[q["kind"]]
        r = c.post("/api/onboarding/answer", headers=W, json={"id": q["id"], "action": "yes", "value": value})
        assert r.status_code == 200, r.text
        view = r.json()
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
        "github"
    ]
    assert not http_mock.calls  # nothing went to the web yet

    http_mock.get("https://api.github.com/users/mayachen-example").respond(
        json={"login": "mayachen-example", "type": "User"}
    )
    http_mock.get("https://api.github.com/users/mayachen-example/repos").respond(json=[])
    view = c.post("/api/onboarding/lookups/github", headers=W, json={"accept": True}).json()
    lk = view["state"]["lookups"][0]
    assert lk["status"] == "done" and "github:mayachen-example" in lk["result"]
    assert view["state"]["step"] == "chats"
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
    assert kinds == ["papers", "orcid"]
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
        papers["status"] == "done"
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
    assert view["state"]["lookups"][1]["status"] == "declined" and view["state"]["step"] == "chats"
    assert not any("orcid" in str(call.request.url) for call in http_mock.calls)


@pytest.mark.usefixtures("public_dns")
def test_lena_business_analytics_lead_website(fresh, http_mock):
    c = client_for(fresh)
    view, asked = answer_all(c, upload(c, "lena"))
    assert any("You list 1 certification: Certified Analytics Professional (CAP)" in q for q in asked)
    assert any("Your profile links to lenavogel.example. Is this yours?" in q for q in asked)
    [lk] = view["state"]["lookups"]
    assert lk["kind"] == "website" and lk["targets"] == ["https://lenavogel.example"]
    page = ("<html><head><title>Lena Vogel</title></head><body><article><h1>Lena Vogel</h1>"
            + "<p>Lena Vogel won the Analytics Leader of the Year award from the Midwest Data Council in 2025.</p>" * 4
            + "</article></body></html>")  # fmt: skip
    http_mock.get("https://lenavogel.example/").respond(200, text=page, headers={"content-type": "text/html"})
    view = c.post(f"/api/onboarding/lookups/{lk['id']}", headers=W, json={"accept": True}).json()
    assert view["state"]["lookups"][0]["status"] == "done"
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
    assert view["state"]["step"] == "chats" and view["state"]["lookups"] == []
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
