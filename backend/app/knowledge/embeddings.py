"""Slice 4D.2 — config-selected embedding providers.

The embeddings provider is independent from the LLM provider (the AI gateway
boundary stays intact): a self-hosted or Groq-compatible ``/embeddings``
endpoint can back semantic knowledge search while the LLM gateway is
untouched, or the deterministic provider keeps the system fully offline.
No vendor-locked OpenAI API is used anywhere in this path. Every stored
vector records which provider produced it, and cosine similarity is only ever
computed between vectors of the same provider and dimension.

Providers:

* ``deterministic`` (default) — the stable content-addressable 256-dim
  bag-of-words + bigram vectors from :mod:`app.knowledge.embedding`. No
  network dependency, fully reproducible.
* ``api`` / ``groq`` — OpenAI-compatible ``POST {base}/embeddings`` against a
  self-hosted endpoint (e.g. Ollama, text-embeddings-inference) or a
  Groq-compatible gateway configured via ``EMBEDDING_BASE_URL``. Fails loudly
  with :class:`EmbeddingProviderError`; callers isolate per entity so the
  indexer never dies on one bad batch.
"""

import json
import logging
from typing import Any, Iterable, Optional, Protocol

import httpx

from app.core.config import get_settings
from app.knowledge.embedding import DIM as DETERMINISTIC_DIM
from app.knowledge.embedding import cosine, embed_text

logger = logging.getLogger("vcos.knowledge.embeddings")

DETERMINISTIC = "deterministic"
API_PROVIDERS = {"api", "groq"}

MAX_BATCH = 64
_REQUEST_TIMEOUT = 30.0


class EmbeddingProviderError(RuntimeError):
    """Raised when a configured provider cannot embed text."""


class EmbeddingProvider(Protocol):
    name: str
    dim: int

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` (bounded internally). Returns same-length vectors."""
        ...

    def cosine(self, a: Iterable[float], b: Iterable[float]) -> float:
        """Cosine similarity, 0.0 when dimensions or providers differ."""
        ...


class DeterministicEmbeddingProvider:
    """Offline, reproducible 256-dim vectors (wraps the Phase 4 hasher)."""

    name = DETERMINISTIC
    dim = DETERMINISTIC_DIM

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        return [embed_text(text or "") for text in texts]

    def cosine(self, a: Iterable[float], b: Iterable[float]) -> float:
        return cosine(a, b)


class EmbeddingsApiProvider:
    """OpenAI-compatible ``/embeddings`` client (config-gated, lazy).

    Points at a self-hosted embedding endpoint or a Groq-compatible gateway
    via ``EMBEDDING_BASE_URL``; never vendor-locked to any OpenAI model.
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = _REQUEST_TIMEOUT,
    ) -> None:
        if not base_url:
            raise EmbeddingProviderError(
                "EMBEDDING_PROVIDER=api/groq requires EMBEDDING_BASE_URL "
                "(self-hosted or Groq-compatible embedding endpoint)"
            )
        self.name = f"api:{model}"
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self.dim = 0  # resolved from the first response

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), MAX_BATCH):
            batch = texts[start : start + MAX_BATCH]
            payload = {"model": self._model, "input": batch}
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.post(
                        f"{self._base_url}/embeddings",
                        json=payload,
                        headers=self._headers(),
                    )
            except httpx.HTTPError as exc:
                raise EmbeddingProviderError(f"embedding request failed: {exc}") from exc
            if response.status_code != 200:
                raise EmbeddingProviderError(
                    f"embedding endpoint returned {response.status_code}: {response.text[:200]}"
                )
            data = response.json().get("data") or []
            if len(data) != len(batch):
                raise EmbeddingProviderError(
                    f"embedding endpoint returned {len(data)} vectors for {len(batch)} texts"
                )
            for item in data:
                vector = list(item.get("embedding") or [])
                if not vector:
                    raise EmbeddingProviderError("embedding endpoint returned an empty vector")
                vectors.append(vector)
        if vectors:
            self.dim = len(vectors[0])
        return vectors

    def cosine(self, a: Iterable[float], b: Iterable[float]) -> float:
        av = list(a)
        bv = list(b)
        if len(av) != len(bv) or (self.dim and len(av) != self.dim):
            return 0.0
        return cosine(av, bv)


_provider: Optional[EmbeddingProvider] = None


def get_embedding_provider() -> EmbeddingProvider:
    """Config-selected provider singleton (deterministic by default)."""
    global _provider
    if _provider is not None:
        return _provider
    settings = get_settings()
    kind = (settings.EMBEDDING_PROVIDER or DETERMINISTIC).strip().lower()
    if kind in API_PROVIDERS:
        _provider = EmbeddingsApiProvider(
            base_url=settings.EMBEDDING_BASE_URL or settings.AI_BASE_URL or "",
            api_key=settings.EMBEDDING_API_KEY or settings.AI_API_KEY or "",
            model=settings.EMBEDDING_MODEL,
        )
    else:
        _provider = DeterministicEmbeddingProvider()
    logger.info("embedding provider active: %s (dim %s)", _provider.name, _provider.dim)
    return _provider


def reset_embedding_provider_for_tests() -> None:
    """Test hook: force re-resolution of the configured provider."""
    global _provider
    _provider = None


def embedding_to_json(vector: list[float]) -> str:
    return json.dumps(vector, separators=(",", ":"))
