"""Scholarly connectors (Semantic Scholar, OpenAlex, arXiv, ORCID): recorded fixtures in the live APIs'
shapes (fictional "Alex Rivera"), no network."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from conftest import TODAY

from areao1 import sources
from areao1.jobs.sync import import_source
from areao1.sources import arxiv, openalex, orcid, semantic_scholar
from areao1.sources.base import paper_candidate
from areao1.sources.http import HttpClient, SourceError

FIX = Path(__file__).parent / "fixtures" / "scholarly"
S2_ID, OA_ID, ARXIV_ID, ORCID_ID = "999999999999", "A0000000001", "rivera_a_1", "0000-0000-4242-4240"


def fx(name: str):
    text = (FIX / name).read_text()
    return json.loads(text) if name.endswith(".json") else text


def mock_scholarly(router) -> None:
    s2 = "https://api.semanticscholar.org/graph/v1/author/" + S2_ID
    router.get(s2).respond(json=fx("s2_author.json"))
    router.get(s2 + "/papers", params__contains={"offset": "0"}).respond(json=fx("s2_papers_0.json"))
    router.get(s2 + "/papers", params__contains={"offset": "3"}).respond(json=fx("s2_papers_3.json"))
    router.get(f"https://api.openalex.org/authors/{OA_ID}").respond(json=fx("openalex_author.json"))
    router.get("https://api.openalex.org/works", params__contains={"filter": f"author.id:{OA_ID}"}).respond(
        json=fx("openalex_works.json")
    )
    router.get(f"https://arxiv.org/a/{ARXIV_ID}.atom").respond(
        text=fx(f"arxiv_{ARXIV_ID}.atom"), headers={"content-type": "application/atom+xml; charset=UTF-8"}
    )
    router.get(f"https://pub.orcid.org/v3.0/{ORCID_ID}/person").respond(json=fx("orcid_person.json"))
    router.get(f"https://pub.orcid.org/v3.0/{ORCID_ID}/works").respond(json=fx("orcid_works.json"))


def make(module, cls):
    return cls(http=HttpClient(module.API, kind=cls.kind, headers=module.HEADERS, sleep=lambda s: None),
               today=lambda: TODAY)  # fmt: skip


S2 = (semantic_scholar, semantic_scholar.SemanticScholarSource)
OA = (openalex, openalex.OpenAlexSource)
AX = (arxiv, arxiv.ArxivSource)
OR = (orcid, orcid.OrcidSource)


# ----------------------------------------------------------------------------- input


@pytest.mark.parametrize(
    ("text", "kind", "handle"),
    [
        ("https://www.semanticscholar.org/author/Alex-Rivera/999999999999", "semantic_scholar", S2_ID),
        ("https://www.semanticscholar.org/author/999999999999", "semantic_scholar", S2_ID),
        ("s2:999999999999", "semantic_scholar", S2_ID),
        ("https://openalex.org/A0000000001", "openalex", OA_ID),
        ("https://openalex.org/authors/a0000000001", "openalex", OA_ID),
        ("https://api.openalex.org/authors/A0000000001", "openalex", OA_ID),
        ("openalex:A0000000001", "openalex", OA_ID),
        ("https://arxiv.org/a/rivera_a_1", "arxiv", ARXIV_ID),
        ("https://arxiv.org/a/rivera_a_1.atom2", "arxiv", ARXIV_ID),
        ("arxiv:rivera_a_1", "arxiv", ARXIV_ID),
        ("https://orcid.org/0000-0000-4242-4240", "orcid", ORCID_ID),
        ("0000-0000-4242-4240", "orcid", ORCID_ID),
        ("orcid:0000-0000-4242-4240", "orcid", ORCID_ID),
        ("https://github.com/arivera-demo", "github", "arivera-demo"),
        ("https://huggingface.co/arivera-demo", "huggingface", "arivera-demo"),
    ],
)
def test_detect_and_parse(text, kind, handle):
    assert sources.detect(text) == kind
    assert sources.build(kind).parse(text) == handle


@pytest.mark.parametrize(
    "text",
    [
        "https://www.semanticscholar.org/paper/a1b2c3",  # a paper, not an author
        "https://arxiv.org/abs/2509.04321",  # a paper
        "arxiv:2509.04321",
        "https://openalex.org/W4400000042",  # a work
        "0000-0000-4242-4241",  # bad ORCID check digit
        "https://orcid.org/0000-0000-4242",
    ],
)
def test_rejects(text):
    """Not an author profile: handles are refused, and other URLs are left to the website connector."""
    if text.startswith("https://"):
        assert sources.detect(text) == "website"
    else:
        with pytest.raises(ValueError, match="No connector"):
            sources.detect(text)


# ----------------------------------------------------------------------------- discover + snapshot


def test_semantic_scholar_pages_through_papers_and_snapshots_profile_metrics(http_mock):
    mock_scholarly(http_mock)
    src = make(*S2)
    items = src.discover(S2_ID, None)
    assert [i.kind for i in items] == ["author", "paper", "paper", "paper", "paper"]  # 3 + 1 on page two
    assert (
        items[0].title == "Alex Rivera"
        and items[0].url == "https://www.semanticscholar.org/author/999999999999"
    )
    rows = {r.metric: r.value for r in src.snapshot(items[0], None)}
    assert rows == {"citations": 92.0, "h_index": 3.0, "papers": 4.0}
    sgc = next(i for i in items if i.title == "Sparse Gradient Compression at Scale")
    [row] = src.snapshot(sgc, None)
    assert (row.metric, row.value, row.source) == ("citations", 71.0, "semantic_scholar")
    assert row._evidence.claims[0].excerpt == '"title": "Sparse Gradient Compression at Scale"'


def test_openalex_h_index_comes_from_summary_stats(http_mock):
    mock_scholarly(http_mock)
    src = make(*OA)
    author, *papers = src.discover(OA_ID, None)
    rows = {r.metric: r for r in src.snapshot(author, None)}
    assert {m: r.value for m, r in rows.items()} == {"citations": 89.0, "h_index": 3.0, "papers": 3.0}
    h = next(c for c in rows["h_index"]._evidence.claims if c.predicate == "h_index")
    assert h.excerpt == '"h_index": 3' and h.value == 3  # quoted from the nested summary_stats
    assert {p.name for p in papers} == {
        f"{OA_ID}/W4411111111",
        f"{OA_ID}/W4400000042",
        f"{OA_ID}/W4400000071",
    }
    request = next(c.request for c in http_mock.calls if c.request.url.path == "/works")
    assert "mailto" not in str(request.url) and "@" not in str(request.url)  # no contact email sent


def test_arxiv_feed_and_orcid_have_no_citation_metrics(http_mock):
    mock_scholarly(http_mock)
    ax = make(*AX)
    author, *papers = ax.discover(ARXIV_ID, None)
    assert author.title == "Alex Rivera" and [r.value for r in ax.snapshot(author, None)] == [2.0]
    assert {p.title for p in papers} == {"RoboGrasp-10k: A Benchmark for Low-Cost Grasping",
                                         "Sparse Gradient Compression at Scale"}  # fmt: skip
    assert all(ax.snapshot(p, None) == [] for p in papers)
    oc = make(*OR)
    author, *works = oc.discover(ORCID_ID, None)
    assert author.title == "Alex Rivera" and oc.snapshot(author, None) == [] and len(works) == 3


def test_arxiv_refuses_feeds_with_a_dtd():
    with pytest.raises(SourceError, match="DTD"):
        arxiv.parse_feed(
            '<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><feed xmlns="http://www.w3.org/2005/Atom"/>'
        )


# ----------------------------------------------------------------------------- candidates


def _cands(src, handle):
    return {
        c.title.removeprefix("Paper: "): c
        for i in src.discover(handle, None)
        for c in src.candidates(i, None)
    }


def test_candidates_classify_venue_type_and_stage(http_mock):
    mock_scholarly(http_mock)
    s2 = _cands(make(*S2), S2_ID)
    sgc = s2["Sparse Gradient Compression at Scale"]
    assert (sgc.evidence_type, sgc.stage, sgc.proposed_criterion) == (
        "conference_paper",
        "published",
        "scholarly_articles",
    )
    assert sgc.signals == ["peer_reviewed", "cited"] and sgc.facts["citations"] == 71
    assert (
        sgc.fingerprint == "paper:arxiv:2502.01234:scholarly_articles"
        and sgc.source == f"semantic_scholar:{S2_ID}"
    )
    assert "confirm you are an author" in sgc.summary and sgc.confidence == 0.5
    tvlm = s2["TinyVLM: Vision-Language Models on a Budget"]
    assert (
        tvlm.evidence_type == "journal_article"
        and tvlm.fingerprint == "paper:doi:10.5555/tmlr.2026.0042:scholarly_articles"
    )
    robo = s2["RoboGrasp-10k: A Benchmark for Low-Cost Grasping"]
    assert (robo.evidence_type, robo.stage, robo.signals) == ("preprint", "preprint", ["cited"])
    assert "add the venue if it was published" in robo.summary
    notes = s2["Notes on Gradient Sparsity in Federated Training"]  # named venue, unknown type, no ids
    assert (notes.evidence_type, notes.stage, notes.signals) == ("paper", "published", [])
    assert notes.fingerprint == "paper:d4e5f60718293a4b5c6d7e8f9012345678912a3b:scholarly_articles"

    oa = _cands(make(*OA), OA_ID)
    assert (
        oa["Sparse Gradient Compression at Scale"].fingerprint == "paper:arxiv:2502.01234:scholarly_articles"
    )
    assert oa["RoboGrasp-10k: A Benchmark for Low-Cost Grasping"].stage == "preprint"
    assert (
        oa["TinyVLM: Vision-Language Models on a Budget"].facts["venue"]
        == "Transactions on Machine Learning Research"
    )

    ax = _cands(make(*AX), ARXIV_ID)
    ref = ax["Sparse Gradient Compression at Scale"]
    assert (ref.evidence_type, ref.stage) == ("paper", "published") and "ICML 2025" in ref.facts[
        "journal_ref"
    ]
    assert ax["RoboGrasp-10k: A Benchmark for Low-Cost Grasping"].stage == "preprint"
    assert ref.confidence == 0.7

    oc = _cands(make(*OR), ORCID_ID)
    assert oc["TinyVLM: Vision-Language Models on a Budget"].evidence_type == "journal_article"
    assert oc["Sparse Gradient Compression at Scale"].evidence_type == "conference_paper"
    assert (
        oc["RoboGrasp-10k: A Benchmark for Low-Cost Grasping"].fingerprint
        == "paper:arxiv:2509.04321:scholarly_articles"
    )


def test_same_fingerprint_as_github_and_hugging_face_paper_links():
    linked = paper_candidate("2509.04321", "huggingface:arivera-demo", "x", "linked from a model card")
    assert linked.fingerprint == "paper:arxiv:2509.04321:scholarly_articles"


def test_importing_all_four_proposes_each_paper_once_with_verifiable_claims(ws, http_mock):
    mock_scholarly(http_mock)
    for url in ("https://www.semanticscholar.org/author/Alex-Rivera/999999999999", "https://openalex.org/A0000000001",
                "https://arxiv.org/a/rivera_a_1", "https://orcid.org/0000-0000-4242-4240"):  # fmt: skip
        report = import_source(ws, url, sleep=lambda s: None)
        assert report.errors == []
    pending = [c for c in ws.pending_candidates() if c.proposed_criterion == "scholarly_articles"]
    assert sorted(c.fingerprint for c in pending) == sorted([
        "paper:arxiv:2509.04321:scholarly_articles", "paper:arxiv:2502.01234:scholarly_articles",
        "paper:doi:10.5555/tmlr.2026.0042:scholarly_articles",
        "paper:d4e5f60718293a4b5c6d7e8f9012345678912a3b:scholarly_articles"])  # fmt: skip
    assert {s.kind for s in ws.sources().sources} == {"semantic_scholar", "openalex", "arxiv", "orcid"}
    metrics = {(r.source, r.item, r.metric): r.value for r in ws.metrics()}
    assert (
        metrics[("semantic_scholar", S2_ID, "h_index")] == 3
        and metrics[("openalex", OA_ID, "citations")] == 89
    )
    assert ws.memory.verify() == []  # every claim's quote is in its snapshot


def test_not_found_author_is_a_clear_error(ws, http_mock):
    http_mock.get("https://api.semanticscholar.org/graph/v1/author/123").respond(
        404, json={"error": "Author not found"}
    )
    with pytest.raises(SourceError, match="Author not found"):
        import_source(ws, "s2:123", sleep=lambda s: None)
    assert ws.sources().sources == []


def test_rate_limits_back_off(http_mock):
    route = http_mock.get("https://api.semanticscholar.org/graph/v1/author/" + S2_ID)
    route.side_effect = [
        httpx.Response(429, headers={"retry-after": "1"}),
        httpx.Response(200, json=fx("s2_author.json")),
    ]
    waits: list[float] = []
    src = semantic_scholar.SemanticScholarSource(
        http=HttpClient(semantic_scholar.API, kind="semantic_scholar", sleep=waits.append)
    )
    assert src.author(S2_ID)[0]["hIndex"] == 3 and waits == [1.0]
