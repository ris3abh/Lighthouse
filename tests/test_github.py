from __future__ import annotations

from datetime import date

import httpx
import pytest
from conftest import TODAY, mock_github

from lighthouse_gc.sources import github
from lighthouse_gc.sources.github import GitHubSource
from lighthouse_gc.sources.http import HttpClient, SourceError


def make(cache_dir=None, sleep=lambda s: None) -> GitHubSource:
    http = HttpClient(github.API, kind="github", headers=github.HEADERS, cache_dir=cache_dir, sleep=sleep)
    return GitHubSource(http=http, today=lambda: TODAY)


@pytest.mark.parametrize(
    ("text", "handle"),
    [
        ("https://github.com/arivera-demo", "arivera-demo"),
        ("github.com/arivera-demo/", "arivera-demo"),
        ("https://www.github.com/arivera-demo/fastgrad", "arivera-demo/fastgrad"),
        ("https://github.com/arivera-demo/fastgrad.git", "arivera-demo/fastgrad"),
        ("https://github.com/arivera-demo/fastgrad/tree/main/src", "arivera-demo/fastgrad"),
        ("https://github.com/orgs/fernhill-demo/repositories", "fernhill-demo"),
        ("gh:arivera-demo", "arivera-demo"),
        ("github:arivera-demo/fastgrad", "arivera-demo/fastgrad"),
    ],
)
def test_parse(text, handle):
    assert GitHubSource.detect(text)
    assert GitHubSource.parse(text) == handle


@pytest.mark.parametrize(
    "text", ["https://huggingface.co/arivera-demo", "https://github.com/settings/tokens", "arivera-demo", ""]
)
def test_detect_rejects(text):
    assert not GitHubSource.detect(text)


def test_discover_public_skips_forks(http_mock):
    mock_github(http_mock)
    items = make().discover("arivera-demo", None)
    assert [i.name for i in items] == ["arivera-demo/fastgrad", "arivera-demo/tinyserve"]
    assert items[0].id == "github:arivera-demo/fastgrad"
    assert items[0].url == "https://github.com/arivera-demo/fastgrad"
    assert not any(i.private for i in items)


def test_discover_with_pat_includes_private_repos(http_mock):
    mock_github(http_mock, authed=True)
    items = make().discover("arivera-demo", "github_pat_fake")
    names = {i.name: i for i in items}
    assert "arivera-demo/thesis-code" in names and names["arivera-demo/thesis-code"].private
    sent = [c.request for c in http_mock.calls if c.request.url.path == "/user/repos"]
    assert sent and sent[0].headers["authorization"] == "Bearer github_pat_fake"


def test_discover_single_repo(http_mock):
    mock_github(http_mock)
    items = make().discover("arivera-demo/fastgrad", None)
    assert [i.id for i in items] == ["github:arivera-demo/fastgrad"]


def test_snapshot_public(http_mock):
    mock_github(http_mock)
    src = make()
    item = src.discover("arivera-demo/fastgrad", None)[0]
    rows = {r.metric: r for r in src.snapshot(item, None)}
    assert rows["stars"].value == 1840 and rows["stars"].date == TODAY
    assert rows["forks"].value == 212
    assert rows["watchers"].value == 44
    assert rows["contributors"].value == 37  # from the Link rel="last" page number
    assert rows["releases"].value == 12
    assert "views" not in rows  # traffic needs a token
    assert {r.source for r in rows.values()} == {"github"}
    assert {r.item for r in rows.values()} == {"arivera-demo/fastgrad"}


def test_snapshot_with_pat_keeps_daily_traffic(http_mock):
    mock_github(http_mock, authed=True)
    src = make()
    item = src.discover("arivera-demo/fastgrad", "tok")[0]
    rows = src.snapshot(item, "tok")
    views = sorted((r for r in rows if r.metric == "views"), key=lambda r: r.date)
    assert len(views) == 14
    assert views[0].date == date(2026, 9, 22) and views[-1].date == date(2026, 10, 5)
    assert any(r.metric == "clones_unique" for r in rows)


def test_snapshot_traffic_forbidden_is_skipped(http_mock):
    mock_github(http_mock, authed=True)
    src = make()
    item = src.discover("arivera-demo/tinyserve", "tok")[0]
    metrics = {r.metric for r in src.snapshot(item, "tok")}
    assert "views" not in metrics and "stars" in metrics
    assert {r.metric: r.value for r in src.snapshot(item, "tok")}["releases"] == 0


def test_candidates(http_mock):
    mock_github(http_mock)
    src = make()
    item = src.discover("arivera-demo/fastgrad", None)[0]
    cands = src.candidates(item, None)
    project = next(c for c in cands if c.proposed_criterion == "original_contributions")
    assert project.evidence_type == "open_source_project"
    assert set(project.signals) == {"widely_adopted", "used_by_others", "sustained_activity"}
    assert project.raw_url == "https://github.com/arivera-demo/fastgrad"
    assert project.facts["stars"] == 1840
    assert 0 < project.confidence <= 0.9
    paper = next(c for c in cands if c.proposed_criterion == "scholarly_articles")
    assert paper.fingerprint == "paper:arxiv:2502.01234:scholarly_articles"
    assert len([c for c in cands if c.proposed_criterion == "scholarly_articles"]) == 1  # abs + pdf deduped


def test_candidates_below_threshold(http_mock):
    mock_github(http_mock, authed=True)
    src = make()
    item = src.discover("arivera-demo/thesis-code", "tok")[0]
    assert src.candidates(item, "tok") == []


def test_not_found_raises_source_error(http_mock):
    http_mock.route(method="GET", host="api.github.com", path="/users/nobody-here").respond(
        404, json={"message": "Not Found"}
    )
    with pytest.raises(SourceError) as err:
        make().discover("nobody-here", None)
    assert err.value.status == 404


def test_etag_conditional_request_uses_cache(tmp_path, http_mock):
    route = http_mock.route(method="GET", host="api.github.com", path="/repos/arivera-demo/fastgrad")
    body = {"full_name": "arivera-demo/fastgrad", "stargazers_count": 1}
    route.side_effect = [
        httpx.Response(200, json=body, headers={"etag": '"abc"'}),
        httpx.Response(304),
    ]
    first = make(cache_dir=tmp_path).http.get("/repos/arivera-demo/fastgrad")
    second = make(cache_dir=tmp_path).http.get("/repos/arivera-demo/fastgrad")  # new run, same disk cache
    assert first.data == second.data == body
    assert route.calls[1].request.headers["if-none-match"] == '"abc"'


def test_backoff_retries_rate_limit(http_mock):
    waits: list[float] = []
    route = http_mock.route(method="GET", host="api.github.com", path="/users/arivera-demo")
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "3"}),
        httpx.Response(502),
        httpx.Response(200, json={"login": "arivera-demo"}),
    ]
    resp = make(sleep=waits.append).http.get("/users/arivera-demo")
    assert resp.data == {"login": "arivera-demo"}
    assert waits == [3.0, 2.0]


def test_long_rate_limit_fails_fast(http_mock):
    http_mock.route(method="GET", host="api.github.com", path="/users/arivera-demo").respond(
        403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "9999999999"}
    )
    with pytest.raises(SourceError, match="rate limited"):
        make().http.get("/users/arivera-demo")
