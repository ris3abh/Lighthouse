from __future__ import annotations

import pytest
from conftest import TODAY, mock_hf

from lighthouse_gc.sources import huggingface
from lighthouse_gc.sources.http import HttpClient
from lighthouse_gc.sources.huggingface import HuggingFaceSource


def make() -> HuggingFaceSource:
    return HuggingFaceSource(
        http=HttpClient(huggingface.API, kind="huggingface", sleep=lambda s: None), today=lambda: TODAY
    )


@pytest.mark.parametrize(
    ("text", "handle"),
    [
        ("https://huggingface.co/arivera-demo", "arivera-demo"),
        ("https://huggingface.co/arivera-demo/tiny-vlm", "arivera-demo/tiny-vlm"),
        ("https://huggingface.co/arivera-demo/tiny-vlm/tree/main", "arivera-demo/tiny-vlm"),
        (
            "https://huggingface.co/datasets/arivera-demo/robo-grasp-10k",
            "datasets/arivera-demo/robo-grasp-10k",
        ),
        ("https://huggingface.co/spaces/arivera-demo/tiny-vlm-demo", "spaces/arivera-demo/tiny-vlm-demo"),
        ("https://hf.co/arivera-demo", "arivera-demo"),
        ("https://huggingface.co/organizations/fernhill-demo", "fernhill-demo"),
        ("hf:arivera-demo", "arivera-demo"),
    ],
)
def test_parse(text, handle):
    assert HuggingFaceSource.detect(text)
    assert HuggingFaceSource.parse(text) == handle


@pytest.mark.parametrize(
    "text",
    [
        "https://github.com/arivera-demo",
        "https://huggingface.co/papers/2509.04321",
        "https://huggingface.co/docs",
    ],
)
def test_detect_rejects(text):
    assert not HuggingFaceSource.detect(text)


def test_discover_account(http_mock):
    mock_hf(http_mock)
    items = make().discover("arivera-demo", None)
    assert {(i.kind, i.name) for i in items} == {
        ("model", "arivera-demo/tiny-vlm"),
        ("model", "arivera-demo/scratch-model"),
        ("dataset", "datasets/arivera-demo/robo-grasp-10k"),
        ("space", "spaces/arivera-demo/tiny-vlm-demo"),
    }
    ds = next(i for i in items if i.kind == "dataset")
    assert ds.id == "huggingface:datasets/arivera-demo/robo-grasp-10k"
    assert ds.url == "https://huggingface.co/datasets/arivera-demo/robo-grasp-10k"


def test_discover_single_dataset(http_mock):
    mock_hf(http_mock)
    items = make().discover("datasets/arivera-demo/robo-grasp-10k", None)
    assert [i.kind for i in items] == ["dataset"]


def test_snapshot_model_with_paper(http_mock):
    mock_hf(http_mock)
    src = make()
    item = src.discover("arivera-demo/tiny-vlm", None)[0]
    rows = {(r.item, r.metric): r.value for r in src.snapshot(item, None)}
    assert rows[("arivera-demo/tiny-vlm", "downloads")] == 15400
    assert rows[("arivera-demo/tiny-vlm", "downloads_all_time")] == 118000
    assert rows[("arivera-demo/tiny-vlm", "likes")] == 233
    assert rows[("papers/2509.04321", "upvotes")] == 42
    request = next(
        c.request for c in http_mock.calls if c.request.url.path == "/api/models/arivera-demo/tiny-vlm"
    )
    assert "downloadsAllTime" in str(request.url)


def test_snapshot_space_has_only_likes(http_mock):
    mock_hf(http_mock)
    src = make()
    item = src.discover("spaces/arivera-demo/tiny-vlm-demo", None)[0]
    assert {r.metric for r in src.snapshot(item, None)} == {"likes"}


def test_candidates_model(http_mock):
    mock_hf(http_mock)
    src = make()
    item = src.discover("arivera-demo/tiny-vlm", None)[0]
    cands = src.candidates(item, None)
    model = next(c for c in cands if c.proposed_criterion == "original_contributions")
    assert model.evidence_type == "ml_model"
    assert set(model.signals) == {"widely_adopted", "used_by_others"}
    assert model.facts["derivative_models"] == 14
    paper = next(c for c in cands if c.proposed_criterion == "scholarly_articles")
    assert paper.fingerprint == "paper:arxiv:2509.04321:scholarly_articles"
    assert paper.title.startswith("Paper: RoboGrasp-10k")
    assert paper.facts["hf_upvotes"] == 42


def test_low_signal_model_gives_no_candidate(http_mock):
    mock_hf(http_mock)
    src = make()
    item = src.discover("arivera-demo/scratch-model", None)[0]
    assert src.candidates(item, None) == []


def test_token_sent_as_bearer(http_mock):
    mock_hf(http_mock)
    make().discover("arivera-demo", "hf_fake")
    assert all(c.request.headers.get("authorization") == "Bearer hf_fake" for c in http_mock.calls)
