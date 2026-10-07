"""Hugging Face connector — models, datasets, Spaces and linked Papers via the public Hub API.

No auth for public repos; a *read* token (https://huggingface.co/settings/tokens) for private or gated ones.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any

from lighthouse_gc.core import clock
from lighthouse_gc.core.models import Candidate, ConnectorConfig, Evidence, MetricRow, TrackedItem
from lighthouse_gc.sources.base import Creds, artifact_id, field_claims, paper_candidate
from lighthouse_gc.sources.http import HttpClient

API = "https://huggingface.co"
HEADERS: dict[str, str] = {}
TOKEN_URL = "https://huggingface.co/settings/tokens/new?tokenType=read"

_URL_RE = re.compile(r"^(?:https?://)?(?:www\.)?(?:huggingface\.co|hf\.co)/(?P<path>[^?#\s]+)", re.I)
_HANDLE_RE = re.compile(r"^(?:hf|huggingface):(?P<path>\S+)$", re.I)
_NAME_RE = re.compile(r"^[\w.\-]+$")
_RESERVED = {
    "models",
    "docs",
    "blog",
    "pricing",
    "settings",
    "join",
    "login",
    "papers",
    "tasks",
    "learn",
    "posts",
}

# HF repo kinds: (item kind, URL/metrics prefix, API collection)
KINDS = {"model": ("", "models"), "dataset": ("datasets/", "datasets"), "space": ("spaces/", "spaces")}
EXPAND = [("expand[]", f) for f in ("downloads", "downloadsAllTime", "likes", "tags", "private")]
SPACE_EXPAND = [("expand[]", f) for f in ("likes", "tags", "private")]


def _split(name: str) -> tuple[str, str]:
    """'datasets/octo/x' -> ('dataset', 'octo/x'); 'octo/x' -> ('model', 'octo/x')."""
    for kind, (prefix, _) in KINDS.items():
        if prefix and name.startswith(prefix):
            return kind, name[len(prefix) :]
    return "model", name


class HuggingFaceSource:
    kind = "huggingface"

    def __init__(
        self,
        http: HttpClient | None = None,
        config: ConnectorConfig | None = None,
        today: Callable[[], date] = clock.today,
    ):
        self.http = http or HttpClient(API, kind=self.kind)
        self.config = config or ConnectorConfig()
        self.today = today

    # -- input -------------------------------------------------------------------------------

    @classmethod
    def detect(cls, url_or_handle: str) -> bool:
        try:
            cls.parse(url_or_handle)
            return True
        except ValueError:
            return False

    @staticmethod
    def parse(url_or_handle: str) -> str:
        text = url_or_handle.strip()
        m = _HANDLE_RE.match(text) or _URL_RE.match(text)
        if not m:
            raise ValueError(f"not a Hugging Face URL or handle: {text!r}")
        parts = [p for p in m["path"].split("/") if p]
        if parts and parts[0] in ("datasets", "spaces"):
            prefix, parts = parts[0] + "/", parts[1:]
            if len(parts) < 2:
                # /datasets/<owner> isn't a page; treat it as the account.
                parts, prefix = parts[:1], ""
        else:
            prefix = ""
            if parts and parts[0] == "organizations":
                parts = parts[1:2]
        if not parts or parts[0].lower() in _RESERVED or not all(_NAME_RE.match(p) for p in parts[:2]):
            raise ValueError(f"not a Hugging Face account or repo: {text!r}")
        return prefix + "/".join(parts[:2]) if len(parts) >= 2 else parts[0]

    def source_url(self, handle: str) -> str:
        return f"https://huggingface.co/{handle}"

    # -- discover ----------------------------------------------------------------------------

    def discover(self, handle: str, creds: Creds) -> list[TrackedItem]:
        if "/" in handle:
            kind, repo_id = _split(handle)
            return [self._item(kind, self._info(kind, repo_id, creds))]
        items: list[TrackedItem] = []
        for kind, (_, collection) in KINDS.items():
            listing = self.http.get(
                f"/api/{collection}", params={"author": handle, "limit": 100}, token=creds
            )
            items.extend(self._item(kind, repo) for repo in listing.data or [])
        return sorted(items, key=lambda i: i.id)

    def _item(self, kind: str, repo: dict[str, Any]) -> TrackedItem:
        repo_id = repo.get("id") or repo["modelId"]
        name = KINDS[kind][0] + repo_id
        return TrackedItem(
            id=f"{self.kind}:{name}",
            kind=kind,
            name=name,
            url=f"https://huggingface.co/{name}",
            title=(repo.get("cardData") or {}).get("pretty_name", "")
            if isinstance(repo.get("cardData"), dict)
            else "",
            private=bool(repo.get("private")),
        )

    def _info(self, kind: str, repo_id: str, creds: Creds) -> dict[str, Any]:
        params = SPACE_EXPAND if kind == "space" else EXPAND
        data: dict[str, Any] = self.http.get(
            f"/api/{KINDS[kind][1]}/{repo_id}", params=params, token=creds
        ).data
        return data

    @staticmethod
    def _arxiv_ids(info: dict[str, Any]) -> list[str]:
        return sorted({t.split(":", 1)[1] for t in info.get("tags") or [] if t.startswith("arxiv:")})

    def _paper(self, arxiv_id: str, creds: Creds) -> dict[str, Any] | None:
        resp = self.http.get(f"/api/papers/{arxiv_id}", token=creds, allow=(404,))
        return resp.data if resp.ok else None

    # -- snapshot ----------------------------------------------------------------------------

    def snapshot(self, item: TrackedItem, creds: Creds) -> list[MetricRow]:
        kind, repo_id = _split(item.name)
        info = self._info(kind, repo_id, creds)
        today = self.today()

        def row(metric: str, value: float, name: str = item.name) -> MetricRow:
            return MetricRow(date=today, source=self.kind, item=name, metric=metric, value=value)

        evidence = self._info_evidence(item, kind, repo_id, info)
        rows = []
        if kind != "space":
            if info.get("downloads") is not None:
                rows.append(row("downloads", info["downloads"]).with_evidence(evidence))  # rolling 30 days
            if info.get("downloadsAllTime") is not None:
                rows.append(row("downloads_all_time", info["downloadsAllTime"]).with_evidence(evidence))
        rows.append(row("likes", info.get("likes", 0)).with_evidence(evidence))
        for arxiv_id in self._arxiv_ids(info):
            paper = self._paper(arxiv_id, creds)
            if paper and paper.get("upvotes") is not None:
                rows.append(
                    row("upvotes", paper["upvotes"], f"papers/{arxiv_id}").with_evidence(
                        self._paper_evidence(arxiv_id, paper)
                    )
                )
        return rows

    def _info_evidence(self, item: TrackedItem, kind: str, repo_id: str, info: dict[str, Any]) -> Evidence:
        fields = {"likes": "likes"} if kind == "space" else {
            "downloads_30d": "downloads", "downloads_all_time": "downloadsAllTime", "likes": "likes"}  # fmt: skip
        return Evidence(
            connector=self.kind,
            tier="platform",
            source_url=f"{API}/api/{KINDS[kind][1]}/{repo_id}",
            payload=info,
            claims=field_claims(
                artifact_id(self.kind, item.name), item.name, item.url, info, fields, self.today()
            ),
        )

    def _paper_evidence(self, arxiv_id: str, paper: dict[str, Any]) -> Evidence:
        return Evidence(
            connector=self.kind,
            tier="platform",
            source_url=f"{API}/api/papers/{arxiv_id}",
            payload=paper,
            claims=field_claims(
                artifact_id("arxiv", arxiv_id), paper.get("title") or f"arXiv {arxiv_id}",
                f"https://arxiv.org/abs/{arxiv_id}", paper, {"title": "title", "hf_upvotes": "upvotes"}, self.today(),
            ),
        )  # fmt: skip

    # -- candidates --------------------------------------------------------------------------

    def candidates(self, item: TrackedItem, creds: Creds) -> list[Candidate]:
        kind, repo_id = _split(item.name)
        info = self._info(kind, repo_id, creds)
        source_id = f"{self.kind}:{repo_id.split('/')[0]}"
        likes = info.get("likes", 0)
        downloads = info.get("downloads", 0) or 0
        all_time = info.get("downloadsAllTime", downloads) or 0
        out: list[Candidate] = []

        qualifies = (
            likes >= 10
            if kind == "space"
            else (all_time >= self.config.min_downloads_for_candidate or likes >= 10)
        )
        if qualifies:
            signals = []
            if all_time >= 10_000 or downloads >= 1_000 or likes >= 100:
                signals.append("widely_adopted")
            facts: dict[str, Any] = {"likes": likes}
            if kind == "model":
                derivatives = self._derivative_count(repo_id, creds)
                if derivatives:
                    signals.append("used_by_others")
                    facts["derivative_models"] = derivatives
            if kind != "space":
                facts |= {"downloads_30d": downloads, "downloads_all_time": all_time}
            noun = {"model": "Model", "dataset": "Dataset", "space": "Space"}[kind]
            stats = (
                f"♥ {likes:,}"
                if kind == "space"
                else f"{all_time:,} downloads ({downloads:,} last 30d) · ♥ {likes:,}"
            )
            out.append(
                Candidate(
                    fingerprint=f"huggingface:{item.name.lower()}:original_contributions",
                    source=source_id,
                    item_id=item.id,
                    evidence_type={"model": "ml_model", "dataset": "dataset", "space": "open_source_project"}[
                        kind
                    ],
                    proposed_criterion="original_contributions",
                    title=f"Hugging Face {noun.lower()}: {repo_id}",
                    summary=f"{noun} {repo_id} — {stats}"
                    + (
                        f" · {facts['derivative_models']} derivative models"
                        if "derivative_models" in facts
                        else ""
                    ),
                    confidence=0.7 if signals else 0.45,
                    raw_url=item.url,
                    signals=signals,
                    facts=facts,
                ).with_evidence(self._info_evidence(item, kind, repo_id, info))
            )

        for arxiv_id in self._arxiv_ids(info):
            paper = self._paper(arxiv_id, creds) or {}
            facts = {"hf_upvotes": paper["upvotes"]} if paper.get("upvotes") is not None else {}
            title = paper.get("title")
            out.append(
                paper_candidate(
                    arxiv_id,
                    source_id,
                    item.id,
                    f"linked from Hugging Face {kind} {repo_id}",
                    title=f"Paper: {title}" if title else None,
                    facts=facts,
                    evidence=self._paper_evidence(arxiv_id, paper) if paper else None,
                )
            )
        return out

    def _derivative_count(self, repo_id: str, creds: Creds) -> int:
        resp = self.http.get(
            "/api/models",
            params={"filter": f"base_model:{repo_id}", "limit": 100},
            token=creds,
            allow=(400, 404),
        )
        return len(resp.data) if resp.ok and isinstance(resp.data, list) else 0
