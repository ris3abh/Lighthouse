"""Local embeddings for vault search. The default is feature hashing: deterministic, offline, no model
download. It catches shared wording ("three of the following", "sustained national or international acclaim");
full-text search covers exact terms. A dense model can be plugged in behind the same interface."""

from __future__ import annotations

import hashlib
import math
import re
from array import array
from typing import Protocol

_TOKEN = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")
_STOP = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "has",
        "have",
        "in",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "which",
        "with",
    ]
)


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[array]: ...


def tokens(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


class HashingEmbedder:
    """Signed feature hashing of unigrams and bigrams, log term frequency, L2-normalized."""

    def __init__(self, dim: int = 512):
        self.dim = dim
        self.name = f"hashing-{dim}-v1"

    def _slot(self, feature: str) -> tuple[int, float]:
        h = int.from_bytes(hashlib.blake2b(feature.encode(), digest_size=8).digest(), "little")
        return h % self.dim, 1.0 if (h >> 63) & 1 else -1.0

    def embed(self, texts: list[str]) -> list[array]:
        out = []
        for text in texts:
            toks = tokens(text)
            counts: dict[str, int] = {}
            for i, t in enumerate(toks):
                counts[t] = counts.get(t, 0) + 1
                if i:
                    bigram = f"{toks[i - 1]} {t}"
                    counts[bigram] = counts.get(bigram, 0) + 1
            vec = [0.0] * self.dim
            for feature, n in counts.items():
                slot, sign = self._slot(feature)
                vec[slot] += sign * (1.0 + math.log(n))
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append(array("f", (v / norm for v in vec)))
        return out


def dot(a: array, b: array) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def default_embedder() -> Embedder:
    return HashingEmbedder()
