"""Onboarding lookups that failed in a real run (item 10), rebuilt with fictional data: LinkedIn's wrapped sidebar
lines, a link typed with its scheme, a paper title with a venue tail or an arXiv link, a web search that finished
after the person moved on, and sites that can't be reached or block us. No real network, no real model."""

from __future__ import annotations

import socket
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from test_onboarding import W, arxiv_feed, fresh  # noqa: F401  (fixture)

from lighthouse_gc.onboarding import flow
from lighthouse_gc.onboarding.linkedin import parse_linkedin
from lighthouse_gc.onboarding.models import OnboardingState, ProfileField
from lighthouse_gc.server.app import create_app

WRAPPED = Path(__file__).parent / "fixtures" / "linkedin" / "wrapped.txt"


@pytest.fixture
def public_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [(2, 1, 6, "", ("93.184.216.34", p))])


def test_wrapped_sidebar_lines_are_one_entry():
    parsed = parse_linkedin(WRAPPED.read_text())
    assert parsed["awards"]["value"] == [
        "Civic Data Hackathon Philadelphia",
        "Dean's List",
    ]  # not "Philadelphia"
    assert parsed["publications"]["value"] == ["Forecasting clinic demand with gradient boosted ensembles"]
    assert parsed["awards"]["quote"] in WRAPPED.read_text()  # the quote is still verbatim
    assert parsed["skills"]["value"] == ["LinkedIn Ads", "Multi-Agent Systems"]  # skills are never joined


def _at_lookups(ws, fields, profile="o1a"):
    state = OnboardingState(status="in_progress", step="questions", target_profile=profile, target_date="skipped",
                            fields=[ProfileField(key=k, label=k, value=v, quote="", status="fixed") for k, v in fields.items()])  # fmt: skip
    state.lookups = flow.offer_lookups(state)
    state.step = "lookups"
    ws.save_onboarding(state)
    return TestClient(create_app(ws, allowed_hosts=["testserver"]))


def test_a_link_typed_with_https_is_not_doubled(fresh):  # noqa: F811
    state = OnboardingState(fields=[ProfileField(key="links", label="Links", status="fixed",
                                                 value=["https://www.jordan-example.example/", "jordan-portfolio.example/"])])  # fmt: skip
    assert [lk.targets for lk in flow.offer_lookups(state)] == [
        ["https://www.jordan-example.example/"],
        ["https://jordan-portfolio.example/"],
    ]


@pytest.mark.parametrize(
    "item,ref",
    [
        ("When Does Selection Help? A Test of Agent Memory, Arxiv Preprint", ("title", "When Does Selection Help? A Test of Agent Memory")),
        ("Forecasting Demand (preprint)", ("title", "Forecasting Demand")),
        ("No this one did not get published, I have a preprint here: https://arxiv.org/abs/2609.34227", ("arxiv", "2609.34227")),
        ("arXiv:2507.01111v2", ("arxiv", "2507.01111")),
        ("2507.01111", ("arxiv", "2507.01111")),
        ("Published at https://doi.org/10.1145/3580305.3599999.", ("doi", "10.1145/3580305.3599999")),
        ("Sparse Mixture Routing for Efficient Transformers", ("title", "Sparse Mixture Routing for Efficient Transformers")),
    ],
)  # fmt: skip
def test_paper_entries_point_at_the_right_thing(item, ref):
    assert flow.paper_ref(item) == ref


def test_papers_are_found_by_arxiv_link_or_clean_title(fresh, http_mock):  # noqa: F811
    fresh.save_person(fresh.person().model_copy(update={"name": "Jordan Example"}))
    c = _at_lookups(fresh, {"publications": [
        "I have a preprint here: https://arxiv.org/abs/2609.34227",
        "Forecasting Clinic Demand with Ensembles, Arxiv Preprint"]})  # fmt: skip
    queries = []

    def arxiv(request):
        queries.append(dict(request.url.params))
        if request.url.params.get("id_list") == "2609.34227":
            feed = arxiv_feed([("2609.34227", "When Does Selection Help?", "Jordan Example, Ana Costa")])
        else:
            feed = arxiv_feed([("2601.00042", "Forecasting Clinic Demand with Ensembles", "Jordan Example")])
        return httpx.Response(200, text=feed, headers={"content-type": "application/atom+xml"})

    http_mock.get(url__regex=r"https://export\.arxiv\.org/api/query.*").mock(side_effect=arxiv)
    view = c.post("/api/onboarding/lookups/papers", headers=W, json={"accept": True}).json()
    lk = view["state"]["lookups"][0]
    assert lk["status"] == "found" and lk["result"].startswith("2 papers found"), lk["result"]
    assert {"id_list": "2609.34227", "max_results": "1"} in queries
    assert any(
        q.get("search_query") == 'ti:"Forecasting Clinic Demand with Ensembles"' for q in queries
    )  # no tail


def test_nothing_found_is_said_plainly_never_reported_as_done(fresh, http_mock):  # noqa: F811
    c = _at_lookups(fresh, {"publications": ["An Unpublished Title, Arxiv Preprint"]})
    http_mock.get(url__regex=r"https://export\.arxiv\.org/api/query.*").respond(
        200, text=arxiv_feed([]), headers={"content-type": "application/atom+xml"})  # fmt: skip
    lk = c.post("/api/onboarding/lookups/papers", headers=W, json={"accept": True}).json()["state"][
        "lookups"
    ][0]
    assert lk["status"] == "nothing_found" and "Not on arXiv: An Unpublished Title" in lk["result"]


def test_an_unreachable_site_says_why_and_can_be_retried(fresh, http_mock, monkeypatch):  # noqa: F811
    c = _at_lookups(fresh, {"links": ["https://www.jordan-example.example/"]})
    lk = c.get("/api/onboarding").json()["state"]["lookups"][0]

    def no_dns(*a, **k):
        raise socket.gaierror(8, "nodename nor servname provided")

    monkeypatch.setattr(socket, "getaddrinfo", no_dns)
    view = c.post(f"/api/onboarding/lookups/{lk['id']}", headers=W, json={"accept": True}).json()
    failed = view["state"]["lookups"][0]
    assert failed["status"] == "unreachable" and failed["result"].startswith("Couldn't reach the site")
    assert view["state"]["step"] == "lookups"
    assert (
        c.post("/api/onboarding/step", headers=W, json={"step": "lookups_done"}).status_code == 200
    )  # never blocks
    # Retry works from a failed state (back on the lookups step)
    state = fresh.onboarding()
    state.step = "lookups"
    fresh.save_onboarding(state)
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [(2, 1, 6, "", ("93.184.216.34", p))])
    page = (
        "<html><head><title>Jordan</title></head><body><article>"
        + "<p>Jordan Example builds AI systems.</p>" * 6
        + "</article></body></html>"
    )
    http_mock.get("https://www.jordan-example.example/").respond(
        200, text=page, headers={"content-type": "text/html"}
    )
    retried = c.post(f"/api/onboarding/lookups/{lk['id']}", headers=W, json={"accept": True}).json()["state"][
        "lookups"
    ][0]
    assert retried["status"] in ("found", "nothing_found") and "jordan-example" in retried["result"]


@pytest.mark.usefixtures("public_dns")
def test_a_site_that_blocks_us_is_named_as_blocked(fresh, http_mock):  # noqa: F811
    c = _at_lookups(fresh, {"links": ["jordan-example.example"]})
    http_mock.get("https://jordan-example.example/").respond(403, text="Forbidden")
    lk = c.get("/api/onboarding").json()["state"]["lookups"][0]
    out = c.post(f"/api/onboarding/lookups/{lk['id']}", headers=W, json={"accept": True}).json()["state"][
        "lookups"
    ][0]
    assert out["status"] in ("blocked", "nothing_found"), out
    if out["status"] == "blocked":
        assert "blocked automated reading" in out["result"]


def test_a_web_search_that_ends_after_you_move_on_is_still_saved(fresh):  # noqa: F811
    from agent_fakes import FakeEngine
    from test_onboarding import _finish_questions

    engine = FakeEngine([("text", "I couldn't find an official page that names Maya Chen.")])
    c, view = _finish_questions(fresh, "maya", engine)
    lk = next(x for x in view["state"]["lookups"] if x["kind"] == "find")
    view = c.post(f"/api/onboarding/lookups/{lk['id']}", headers=W, json={"accept": True}).json()
    assert next(x for x in view["state"]["lookups"] if x["id"] == lk["id"])["status"] == "searching"
    c.post("/api/onboarding/step", headers=W, json={"step": "lookups_done"})  # moved on while it ran
    for _ in range(100):
        saved = next(x for x in fresh.onboarding().lookups if x.id == lk["id"])
        if saved.status != "searching":
            break
        time.sleep(0.05)
    assert saved.status == "nothing_found" and saved.result.startswith("I couldn't find an official page")
    assert any(ch.action == "onboarding.lookup_result" for ch in fresh.changes())


def test_an_arxiv_link_shows_its_real_title_only_after_the_yes(fresh, http_mock):  # noqa: F811
    c = _at_lookups(fresh, {"publications": ["https://arxiv.org/abs/2609.34227"]})
    before = c.get("/api/onboarding").json()
    assert (
        before["state"]["lookups"][0]["resolved"] == {} and not http_mock.calls
    )  # nothing fetched to show it
    http_mock.get(url__regex=r"https://export\.arxiv\.org/api/query.*").respond(
        200, text=arxiv_feed([("2609.34227", "When Does Selection Help?", "Jordan Example")]),
        headers={"content-type": "application/atom+xml"})  # fmt: skip
    after = c.post("/api/onboarding/lookups/papers", headers=W, json={"accept": True}).json()
    assert after["state"]["lookups"][0]["resolved"] == {
        "https://arxiv.org/abs/2609.34227": "When Does Selection Help?"
    }
    assert fresh.onboarding().field("publications").value == [
        "https://arxiv.org/abs/2609.34227"
    ]  # the answer itself is kept


def test_a_list_answer_from_the_chip_input_is_kept_item_for_item(fresh):  # noqa: F811
    from test_onboarding import client_for, upload

    c = client_for(fresh)
    view = upload(c, "ravi")
    while view["question"]["id"] != "publications":
        view = c.post(
            "/api/onboarding/answer", headers=W, json={"id": view["question"]["id"], "action": "yes"}
        ).json()
    chips = ["Sparse Mixture Routing; for Efficient Transformers", "A third paper, with a comma"]
    view = c.post(
        "/api/onboarding/answer", headers=W, json={"id": "publications", "action": "fix", "value": chips}
    ).json()
    assert {line["key"]: line["value"] for line in view["panel"]}["publications"] == chips  # no re-splitting
