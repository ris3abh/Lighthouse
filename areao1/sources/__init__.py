"""Connector registry. To add a platform, implement :class:`~areao1.sources.base.Source` in one module
and register it in ``CONNECTORS``."""

from __future__ import annotations

import time
from collections.abc import Callable
from types import ModuleType
from typing import Any

from areao1.core.workspace import Workspace
from areao1.sources import arxiv, github, huggingface, openalex, orcid, semantic_scholar, website
from areao1.sources.base import Source
from areao1.sources.http import HttpClient, SourceError

# kind -> (connector class, module with API / HEADERS / TOKEN_URL)
CONNECTORS: dict[str, tuple[Any, ModuleType]] = {
    "github": (github.GitHubSource, github),
    "huggingface": (huggingface.HuggingFaceSource, huggingface),
    "semantic_scholar": (semantic_scholar.SemanticScholarSource, semantic_scholar),
    "openalex": (openalex.OpenAlexSource, openalex),
    "arxiv": (arxiv.ArxivSource, arxiv),
    "orcid": (orcid.OrcidSource, orcid),
    "website": (website.WebsiteSource, website),  # last: any other http(s) URL
}

__all__ = ["CONNECTORS", "Source", "SourceError", "build", "detect", "token_help"]


def build(kind: str, ws: Workspace | None = None, sleep: Callable[[float], None] = time.sleep) -> Source:
    if kind not in CONNECTORS:
        raise ValueError(f"unknown connector {kind!r}")
    cls, module = CONNECTORS[kind]
    http = HttpClient(
        module.API, kind=kind, cache_dir=ws.cache_dir if ws else None, headers=module.HEADERS, sleep=sleep
    )
    extra: dict[str, Any] = {}
    if kind == "website":  # mention matching needs the person's name (and aliases)
        person = getattr(ws, "person", None)
        if callable(person):
            p = person()
            extra["names"] = [p.name, *p.aliases]
    connector: Source = cls(http=http, config=ws.config().connectors if ws else None, **extra)
    return connector


def detect(url_or_handle: str) -> str:
    """Return the connector kind that can handle the input."""
    for kind, (cls, _) in CONNECTORS.items():
        if cls.detect(url_or_handle):
            return kind
    raise ValueError(
        f"No connector recognizes {url_or_handle!r}. Supported: GitHub (github.com/<user>[/<repo>]), "
        "Hugging Face (huggingface.co/<user>[/<repo>]), Semantic Scholar (semanticscholar.org/author/<name>/<id>), "
        "OpenAlex (openalex.org/A<id>), arXiv (arxiv.org/a/<id>), ORCID (orcid.org/<iD>), or any http(s) page."
    )


def token_help(kind: str) -> str | None:
    return getattr(CONNECTORS[kind][1], "TOKEN_URL", None) if kind in CONNECTORS else None
