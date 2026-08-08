"""Deterministic text embeddings (Phase 4).

When no external embedding provider is configured we still need *semantic*
search — keyword-only search misses synonyms and related wording. This module
produces a stable, content-addressable bag-of-words + bigram vector (256 dims)
so cosine similarity over the index gives real lexical-semantic ranking
without any network dependency. If an OpenAI-compatible provider is configured
with an embeddings endpoint, `embed_text` can be swapped for it later without
changing callers.
"""

import hashlib
import math
import re
import unicodedata
from typing import Iterable

DIM = 256

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "but", "by", "can", "could",
    "did", "do", "does", "for", "from", "had", "has", "have", "how", "i",
    "if", "in", "into", "is", "it", "its", "may", "more", "not", "of", "on",
    "or", "our", "shall", "should", "so", "that", "the", "their", "them",
    "then", "there", "these", "they", "this", "to", "was", "we", "were",
    "what", "when", "where", "which", "who", "why", "will", "with", "you",
    "your", "s", "t", "d", "ll", "ve", "re",
}


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii", "ignore")
    return _TOKEN_RE.findall(text.lower())


def keywords(text: str, limit: int = 8) -> list[str]:
    """Top tokens by term frequency, minus stopwords."""
    tokens = tokenize(text)
    counts: dict[str, int] = {}
    for token in tokens:
        if token in _STOPWORDS or len(token) < 3:
            continue
        counts[token] = counts.get(token, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return [token for token, _ in ranked[:limit]]


def _hash_index(text: str) -> int:
    return int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16) % DIM


def embed_text(text: str) -> list[float]:
    """256-dim vector: unigram tf weighting + bigram signal, L2-normalized."""
    tokens = tokenize(text)
    if not tokens:
        return [0.0] * DIM
    vec = [0.0] * DIM
    counts: dict[str, int] = {}
    for token in tokens:
        counts[token] = counts.get(token, 0) + 1
    for token, count in counts.items():
        weight = 1.0 + math.log(count)
        vec[_hash_index(token)] += weight
    for i in range(len(tokens) - 1):
        bigram = f"{tokens[i]}|{tokens[i + 1]}"
        vec[_hash_index(bigram)] += 0.5
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def cosine(a: Iterable[float], b: Iterable[float]) -> float:
    av = list(a)
    bv = list(b)
    if len(av) != len(bv):
        return 0.0
    dot = sum(x * y for x, y in zip(av, bv))
    na = math.sqrt(sum(x * x for x in av)) or 1.0
    nb = math.sqrt(sum(x * x for x in bv)) or 1.0
    return dot / (na * nb)


def snippet(text: str, limit: int = 160) -> str:
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text.strip())
    return text[:limit] + ("…" if len(text) > limit else "")
