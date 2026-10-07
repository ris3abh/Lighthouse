"""Website connector: readability extraction, mentions of the person, bot-blocked pages marked unreadable, and
the same private-network guard as the agent's page reader. Recorded fixtures, no network."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
from test_vault import public_dns  # noqa: F401  (fixture)

from areao1 import sources, web
from areao1.jobs.sync import import_source, sync_source
from areao1.sources.http import SourceError
from areao1.sources.website import WebsiteSource

FIX = Path(__file__).parent / "fixtures" / "website"
VAULT = Path(__file__).parent / "fixtures" / "vault"
HTML = {"content-type": "text/html; charset=utf-8"}
PRESS = "https://ledger.example/2026/09/fastgrad-1800-stars"


def page(router, url: str, name: str, status: int = 200, folder: Path = FIX):
    return router.get(url).respond(status, content=(folder / name).read_bytes(), headers=HTML)


def _import(ws, url):
    return import_source(ws, url, sleep=lambda s: None)


def _cands(ws, url):
    return [c for c in ws.pending_candidates() if c.raw_url == url]


# ----------------------------------------------------------------------------- input + extraction


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        (PRESS, "website"),
        ("http://blog.example/post?id=4#comments", "website"),
        ("https://arxiv.org/abs/2509.04321", "website"),  # a paper page is just a page
        ("https://github.com/arivera-demo", "github"),
        ("https://orcid.org/0000-0000-4242-4240", "orcid"),
    ],
)
def test_any_other_http_url_is_a_website(text, kind):
    assert sources.detect(text) == kind


def test_parse_normalizes_and_rejects_non_urls():
    assert WebsiteSource.parse("HTTPS://Blog.Example/post?id=4#comments") == "https://blog.example/post?id=4"
    assert WebsiteSource.parse("https://blog.example") == "https://blog.example/"
    for bad in ("blog.example/post", "ftp://blog.example/x", "file:///etc/passwd", "javascript:alert(1)"):
        with pytest.raises(ValueError):
            WebsiteSource.parse(bad)


def test_readability_keeps_the_article_and_drops_the_chrome():
    a = web.readable((FIX / "press-article.html").read_text(), PRESS)
    assert a.title == "Open-source gradient library from Pittsburgh hits 1,800 stars"
    assert (a.published, a.author, a.site_name) == (
        "2026-09-12",
        "Jordan Lee",
        "Pittsburgh Tech Ledger (fictional)",
    )
    assert a.canonical == PRESS and a.description.startswith("fastgrad, a gradient-compression library")
    assert a.text.startswith("When Alex Rivera released fastgrad two years ago")
    assert (
        "Alex Rivera will present the work" in a.text
        and "Benchmarks published with the 2.0 release." in a.text
    )
    for chrome in ("Subscribe", "Startups", "Related", "engineers to watch", "Privacy", "window.analytics"):
        assert chrome not in a.text
    # Without <article> or <main>, the body minus navigation.
    b = web.readable((FIX / "passing-mention.html").read_text(), "https://meetup.example/nov")
    assert (
        b.title == "Pittsburgh ML Systems meetup: November lineup"
        and "Alex Rivera on gradient compression" in b.text
    )


# ----------------------------------------------------------------------------- candidates


def test_press_article_about_the_person(demo_ws, http_mock, public_dns):  # noqa: F811
    page(http_mock, PRESS, "press-article.html")
    report = _import(demo_ws, PRESS)
    assert report.errors == [] and report.candidates_added == 1
    [cand] = _cands(demo_ws, PRESS)
    assert (cand.proposed_criterion, cand.evidence_type, cand.stage) == (
        "press",
        "press_article",
        "published",
    )
    assert (
        cand.signals == ["about_the_person"] and cand.facts["mentions"] == 3
    )  # the aside's mention is chrome
    assert (
        cand.facts["site"] == "Pittsburgh Tech Ledger (fictional)" and cand.facts["published"] == "2026-09-12"
    )
    assert cand.fingerprint == f"website:{PRESS}:press" and cand.source == f"website:{PRESS}"
    assert "When Alex Rivera released fastgrad two years ago" in cand.summary
    [src] = [s for s in demo_ws.sources().sources if s.kind == "website"]
    assert src.items[0].title == "Open-source gradient library from Pittsburgh hits 1,800 stars"
    assert src.items[0].unreadable is None
    assert demo_ws.memory.verify() == []  # the quoted sentences are in the stored page text
    # Re-importing never duplicates.
    assert _import(demo_ws, PRESS).candidates_added == 0


def test_award_page_and_passing_mention(demo_ws, http_mock, public_dns):  # noqa: F811
    page(http_mock, "https://hack.example/fall-2026-winners", "award.html")
    page(http_mock, "https://meetup.example/nov", "passing-mention.html")
    _import(demo_ws, "https://hack.example/fall-2026-winners")
    [award] = _cands(demo_ws, "https://hack.example/fall-2026-winners")
    assert (award.proposed_criterion, award.evidence_type, award.stage) == (
        "awards",
        "award_notice",
        "granted",
    )
    assert "Alex Rivera won the Grand Prize" in award.summary and award.facts["published"] == "2026-10-03"
    _import(demo_ws, "https://meetup.example/nov")
    [mention] = _cands(demo_ws, "https://meetup.example/nov")
    assert (mention.evidence_type, mention.signals, mention.confidence) == ("media_mention", [], 0.3)


def test_a_page_that_doesnt_mention_you_is_tracked_without_a_proposal(demo_ws, http_mock, public_dns):  # noqa: F811
    page(http_mock, "https://ledger.example/2026/09/robotics-startups", "no-mention.html")
    report = _import(demo_ws, "https://ledger.example/2026/09/robotics-startups")
    assert report.items == 1 and report.candidates_added == 0 and report.errors == []


# ----------------------------------------------------------------------------- unreadable + guard


@pytest.mark.parametrize(
    ("name", "status", "folder", "reason"),
    [
        ("cloudflare-403.html", 403, VAULT, "HTTP 403"),
        ("ecfr-request-access.html", 200, VAULT, "bot-protection page"),  # a bot check served with HTTP 200
        ("js-only.html", 200, FIX, "almost no readable text (it may need JavaScript)"),
    ],
)
@pytest.mark.usefixtures("public_dns")
def test_bot_blocked_and_empty_pages_are_marked_unreadable(demo_ws, http_mock, name, status, folder, reason):
    url = "https://www.linkedin.example/in/alex"
    page(http_mock, url, name, status, folder)
    report = _import(demo_ws, url)
    assert report.errors == [] and report.candidates_added == 0
    [src] = [s for s in demo_ws.sources().sources if s.kind == "website"]
    assert reason in src.items[0].unreadable and src.items[0].title == url
    assert not any(o.source_url == url for o in demo_ws.memory.observations())  # nothing stored as content


def test_unreadable_page_recovers_on_the_next_sync(demo_ws, http_mock, public_dns):  # noqa: F811
    route = page(http_mock, PRESS, "cloudflare-403.html", 403, VAULT)
    _import(demo_ws, PRESS)
    route.respond(200, content=(FIX / "press-article.html").read_bytes(), headers=HTML)
    report = sync_source(demo_ws, f"website:{PRESS}", sleep=lambda s: None)
    assert report.candidates_added == 1
    [src] = [s for s in demo_ws.sources().sources if s.kind == "website"]
    assert src.items[0].unreadable is None


def test_private_and_local_addresses_are_refused(demo_ws, http_mock, monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda h, p, *a, **k: [(2, 1, 6, "", ("10.0.0.5", p))])
    with pytest.raises(SourceError, match="private or local address"):
        _import(demo_ws, "https://intranet.example/wiki")
    with pytest.raises(SourceError, match="only http"):
        WebsiteSource().read("ftp://intranet.example/x")
    assert not any(s.kind == "website" for s in demo_ws.sources().sources) and not http_mock.calls


def test_redirects_to_local_addresses_are_refused(demo_ws, http_mock, monkeypatch):
    def resolve(host, port, *a, **k):
        return [(2, 1, 6, "", ("127.0.0.1" if host == "localhost" else "93.184.216.34", port))]

    monkeypatch.setattr(socket, "getaddrinfo", resolve)
    http_mock.get("https://short.example/x").respond(
        302, headers={"location": "http://localhost:7777/api/inbox"}
    )
    with pytest.raises(SourceError, match="private or local address"):
        _import(demo_ws, "https://short.example/x")
    assert [str(c.request.url) for c in http_mock.calls] == ["https://short.example/x"]  # never followed


def test_a_missing_page_isnt_added(demo_ws, http_mock, public_dns):  # noqa: F811
    http_mock.get("https://ledger.example/typo").respond(404, text="not found")
    with pytest.raises(SourceError, match="HTTP 404"):
        _import(demo_ws, "https://ledger.example/typo")
    assert not any(s.kind == "website" for s in demo_ws.sources().sources)


# ----------------------------------------------------------------------------- sitemaps


def test_sitemap_tracks_same_site_pages(demo_ws, http_mock, public_dns):  # noqa: F811
    http_mock.get("https://ledger.example/sitemap.xml").respond(
        content=(FIX / "sitemap.xml").read_bytes(), headers={"content-type": "application/xml"}
    )
    page(http_mock, PRESS, "press-article.html")
    page(http_mock, "https://ledger.example/2026/09/robotics-startups", "no-mention.html")
    http_mock.get("https://ledger.example/profile/alex").respond(404, text="gone")
    report = _import(demo_ws, "https://ledger.example/sitemap.xml")
    assert report.items == 3 and report.candidates_added == 1 and report.errors == []
    [src] = [s for s in demo_ws.sources().sources if s.kind == "website"]
    by_url = {i.url: i for i in src.items}
    assert set(by_url) == {
        PRESS,
        "https://ledger.example/2026/09/robotics-startups",
        "https://ledger.example/profile/alex",
    }
    assert "HTTP 404" in by_url["https://ledger.example/profile/alex"].unreadable  # off-site <loc> ignored
    assert not any("elsewhere.example" in str(c.request.url) for c in http_mock.calls)


def test_sitemap_with_a_dtd_is_refused():
    with pytest.raises(ValueError, match="DTD"):
        web.sitemap_urls('<!DOCTYPE x [<!ENTITY e "x">]><urlset><url><loc>https://a.example/</loc></url></urlset>',
                         "https://a.example/")  # fmt: skip
