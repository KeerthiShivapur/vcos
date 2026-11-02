"""
Embedding Pipeline for VCOS Intelligence Layer.

Provides:
- Multiple embedding providers (OpenAI, Cohere, local models)
- Batch embedding generation
- Caching and rate limiting
- Chunking strategies for large documents
- Embedding versioning
"""

import asyncio
import hashlib
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable
from uuid import uuid4

import aiohttp
import tiktoken

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingProvider(str, Enum):
    """Embedding model providers."""
    OPENAI = "openai"
    COHERE = "cohere"
    HUGGINGFACE = "huggingface"
    LOCAL = "local"
    VERTEX_AI = "vertex_ai"
    AZURE_OPENAI = "azure_openai"


@dataclass
class EmbeddingConfig:
    """Embedding model configuration."""
    provider: EmbeddingProvider = EmbeddingProvider.OPENAI
    model: str = "text-embedding-3-small"
    dimensions: int = 1536
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    batch_size: int = 100
    max_retries: int = 3
    timeout: int = 30
    cache_enabled: bool = True
    rate_limit_rpm: int = 3000


@dataclass
class EmbeddingRequest:
    """Request for embedding generation."""
    texts: List[str]
    model: Optional[str] = None
    dimensions: Optional[int] = None
    user_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EmbeddingResponse:
    """Response from embedding generation."""
    embeddings: List[List[float]]
    model: str
    dimensions: int
    usage: Dict[str, int]
    cached: bool = False
    latency_ms: int = 0


@dataclass
class DocumentChunk:
    """Document chunk for embedding."""
    id: str
    content: str
    metadata: Dict[str, Any]
    token_count: int
    chunk_index: int
    parent_id: Optional[str] = None


class EmbeddingProviderBase(ABC):
    """Base class for embedding providers."""

    def __init__(self, config: EmbeddingConfig):
        self.config = config
        self._session: Optional[aiohttp.ClientSession] = None

    async def initialize(self):
        """Initialize HTTP session."""
        timeout = aiohttp.ClientTimeout(total=self.config.timeout)
        self._session = aiohttp.ClientSession(timeout=timeout)

    async def close(self):
        """Close HTTP session."""
        if self._session:
            await self._session.close()

    @abstractmethod
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generate embeddings for texts."""
        pass

    @abstractmethod
    def get_dimensions(self) -> int:
        """Get embedding dimensions."""
        pass


class OpenAIEmbeddingProvider(EmbeddingProviderBase):
    """OpenAI embedding provider."""

    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self.api_key = config.api_key or getattr(settings, 'OPENAI_API_KEY', None)
        self.api_base = config.api_base or "https://api.openai.com/v1"
        self.model = config.model
        self._encoding = tiktoken.get_encoding("cl100k_base")

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not self._session:
            await self.initialize()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "input": texts,
            "model": self.model,
        }

        if self.config.dimensions and self.model in ["text-embedding-3-small", "text-embedding-3-large"]:
            payload["dimensions"] = self.config.dimensions

        for attempt in range(self.config.max_retries):
            try:
                async with self._session.post(
                    f"{self.api_base}/embeddings",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", "60"))
                        await asyncio.sleep(retry_after)
                        continue
                    
                    if resp.status >= 400:
                        error = await resp.text()
                        raise Exception(f"OpenAI API error: {resp.status} - {error}")
                    
                    data = await resp.json()
                    return [item["embedding"] for item in data["data"]]
                    
            except asyncio.TimeoutError:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise
            except Exception as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

        raise Exception("Max retries exceeded")

    def get_dimensions(self) -> int:
        return self.config.dimensions

    def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self._encoding.encode(text))

    def chunk_text(
        self,
        text: str,
        max_tokens: int = 8000,
        overlap: int = 200,
    ) -> List[str]:
        """Chunk text into token-limited pieces."""
        tokens = self._encoding.encode(text)
        chunks = []
        
        for i in range(0, len(tokens), max_tokens - overlap):
            chunk_tokens = tokens[i:i + max_tokens]
            chunks.append(self._encoding.decode(chunk_tokens))
            
        return chunks


class CohereEmbeddingProvider(EmbeddingProviderBase):
    """Cohere embedding provider."""

    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self.api_key = config.api_key or getattr(settings, 'COHERE_API_KEY', None)
        self.api_base = config.api_base or "https://api.cohere.ai/v1"
        self.model = config.model or "embed-english-v3.0"

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        if not self._session:
            await self.initialize()

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "texts": texts,
            "model": self.model,
            "input_type": "search_document",
        }

        for attempt in range(self.config.max_retries):
            try:
                async with self._session.post(
                    f"{self.api_base}/embed",
                    headers=headers,
                    json=payload,
                ) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", "60"))
                        await asyncio.sleep(retry_after)
                        continue
                    
                    if resp.status >= 400:
                        error = await resp.text()
                        raise Exception(f"Cohere API error: {resp.status} - {error}")
                    
                    data = await resp.json()
                    return data["embeddings"]
                    
            except Exception as e:
                if attempt < self.config.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)
                    continue
                raise

        raise Exception("Max retries exceeded")

    def get_dimensions(self) -> int:
        return self.config.dimensions


class LocalEmbeddingProvider(EmbeddingProviderBase):
    """Local embedding provider using sentence-transformers."""

    def __init__(self, config: EmbeddingConfig):
        super().__init__(config)
        self.model_name = config.model or "sentence-transformers/all-MiniLM-L6-v2"
        self._model = None

    async def initialize(self):
        """Load local model."""
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
            logger.info(f"Loaded local embedding model: {self.model_name}")
        except ImportError:
            raise Exception("sentence-transformers not installed. Run: pip install sentence-transformers")

    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        if self._model is None:
            await self.initialize()
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None, 
            self._model.encode, 
            texts, 
            {'convert_to_numpy': True, 'show_progress_bar': False}
        )
        return embeddings.tolist()

    def get_dimensions(self) -> int:
        if self._model:
            return self._model.get_sentence_embedding_dimension()
        return self.config.dimensions


class EmbeddingPipeline:
    """
    Embedding Pipeline with caching, batching, and multiple providers.

    Features:
    - Multiple provider support
    - Redis-based caching
    - Automatic batching
    - Rate limiting
    - Document chunking
    - Token counting
    """

    def __init__(
        self,
        config: EmbeddingConfig,
        redis_url: Optional[str] = None,
    ):
        self.config = config
        self.redis_url = redis_url
        self._provider: Optional[EmbeddingProviderBase] = None
        self._redis = None
        self._cache: Dict[str, List[float]] = {}
        self._token_counter = tiktoken.get_encoding("cl100k_base")
        self._rate_limit_tokens = config.rate_limit_rpm
        self._rate_limit_last = time.time()

    async def initialize(self):
        """Initialize provider and Redis."""
        # Create provider
        if self.config.provider == EmbeddingProvider.OPENAI:
            self._provider = OpenAIEmbeddingProvider(self.config)
        elif self.config.provider == EmbeddingProvider.COHERE:
            self._provider = CohereEmbeddingProvider(self.config)
        elif self.config.provider == EmbeddingProvider.LOCAL:
            self._provider = LocalEmbeddingProvider(self.config)
        else:
            raise ValueError(f"Unsupported provider: {self.config.provider}")

        await self._provider.initialize()

        # Initialize Redis for caching
        if self.config.cache_enabled and self.redis_url:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                await self._redis.ping()
                logger.info("Embedding cache initialized with Redis")
            except Exception as e:
                logger.warning(f"Redis not available, using in-memory cache: {e}")

    async def close(self):
        """Close connections."""
        if self._provider:
            await self._provider.close()
        if self._redis:
            await self._redis.close()

    def _get_cache_key(self, text: str, model: str) -> str:
        """Generate cache key for text."""
        content = f"{model}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()

    async def _get_cached(self, key: str) -> Optional[List[float]]:
        """Get embedding from cache."""
        if self._redis:
            data = await self._redis.get(key)
            if data:
                import json
                return json.loads(data)
        return self._cache.get(key)

    async def _set_cache(self, key: str, embedding: List[float], ttl: int = 86400 * 7):
        """Set embedding in cache."""
        import json
        data = json.dumps(embedding)
        if self._redis:
            await self._redis.setex(key, ttl, data)
        else:
            self._cache[key] = embedding

    async def _rate_limit(self, token_count: int):
        """Apply rate limiting."""
        now = time.time()
        elapsed = now - self._rate_limit_last
        
        # Refill tokens
        self._rate_limit_tokens = min(
            self.config.rate_limit_rpm,
            self._rate_limit_tokens + elapsed * (self.config.rate_limit_rpm / 60)
        )
        
        if self._rate_limit_tokens < token_count:
            wait_time = (token_count - self._rate_limit_tokens) / (self.config.rate_limit_rpm / 60)
            await asyncio.sleep(wait_time)
            self._rate_limit_tokens = 0
        else:
            self._rate_limit_tokens -= token_count
        
        self._rate_limit_last = now

    def chunk_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        max_tokens: int = 8000,
        overlap: int = 200,
        parent_id: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """Chunk document into token-limited pieces."""
        if hasattr(self._provider, 'chunk_text'):
            chunks_text = self._provider.chunk_text(content, max_tokens, overlap)
        else:
            # Fallback chunking
            tokens = self._token_counter.encode(content)
            chunks_text = []
            for i in range(0, len(tokens), max_tokens - overlap):
                chunk_tokens = tokens[i:i + max_tokens]
                chunks_text.append(self._token_counter.decode(chunk_tokens))

        chunks = []
        for i, chunk_text in enumerate(chunks_text):
            token_count = len(self._token_counter.encode(chunk_text))
            chunks.append(DocumentChunk(
                id=str(uuid4()),
                content=chunk_text,
                metadata={**metadata, "chunk_index": i, "total_chunks": len(chunks_text)},
                token_count=token_count,
                chunk_index=i,
                parent_id=parent_id,
            ))

        return chunks

    async def embed_texts(
        self,
        texts: List[str],
        model: Optional[str] = None,
        use_cache: bool = True,
    ) -> EmbeddingResponse:
        """Generate embeddings for texts with caching."""
        start_time = time.time()
        model = model or self.config.model
        embeddings = []
        cached_count = 0
        to_embed = []
        to_embed_indices = []

        # Check cache
        if use_cache and self.config.cache_enabled:
            for i, text in enumerate(texts):
                key = self._get_cache_key(text, model)
                cached = await self._get_cached(key)
                if cached:
                    embeddings.append(cached)
                    cached_count += 1
                else:
                    to_embed.append(text)
                    to_embed_indices.append(i)
        else:
            to_embed = texts
            to_embed_indices = list(range(len(texts)))

        # Generate embeddings for uncached texts
        if to_embed:
            # Rate limiting
            total_tokens = sum(len(self._token_counter.encode(t)) for t in to_embed)
            await self._rate_limit(total_tokens)

            new_embeddings = await self._provider.generate_embeddings(to_embed)

            # Cache new embeddings
            if use_cache and self.config.cache_enabled:
                for text, embedding in zip(to_embed, new_embeddings):
                    key = self._get_cache_key(text, model)
                    await self._set_cache(key, embedding)

            # Merge embeddings in correct order
            final_embeddings = [None] * len(texts)
            for i, cached_emb in enumerate(embeddings):
                # Find original index
                pass
            
            # Rebuild in order
            embed_idx = 0
            cache_idx = 0
            for i in range(len(texts)):
                if i in to_embed_indices:
                    final_embeddings[i] = new_embeddings[embed_idx]
                    embed_idx += 1
                else:
                    # Find cached embedding
                    key = self._get_cache_key(texts[i], model)
                    cached = await self._get_cached(key)
                    final_embeddings[i] = cached
                    cache_idx += 1
            
            embeddings = final_embeddings

        latency_ms = int((time.time() - start_time) * 1000)

        return EmbeddingResponse(
            embeddings=embeddings,
            model=model,
            dimensions=self._provider.get_dimensions(),
            usage={
                "total_tokens": sum(len(self._token_counter.encode(t)) for t in texts),
                "cached_tokens": sum(len(self._token_counter.encode(texts[i])) for i in range(len(texts)) if i not in to_embed_indices),
                "request_count": len(to_embed),
            },
            cached=cached_count > 0,
            latency_ms=latency_ms,
        )

    async def embed_document(
        self,
        content: str,
        metadata: Dict[str, Any],
        max_tokens: int = 8000,
        overlap: int = 200,
    ) -> List[DocumentChunk]:
        """Chunk and embed a document."""
        chunks = self.chunk_document(content, metadata, max_tokens, overlap)
        
        if not chunks:
            return []

        texts = [chunk.content for chunk in chunks]
        response = await self.embed_texts(texts)
        
        for chunk, embedding in zip(chunks, response.embeddings):
            chunk.metadata["embedding"] = embedding
            chunk.metadata["embedding_model"] = response.model
            chunk.metadata["embedding_dimensions"] = response.dimensions

        return chunks

    async def embed_documents_batch(
        self,
        documents: List[Dict[str, Any]],
        max_tokens: int = 8000,
        overlap: int = 200,
        batch_size: int = 50,
    ) -> List[DocumentChunk]:
        """Embed multiple documents in batches."""
        all_chunks = []
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            
            # Chunk all documents
            batch_chunks = []
            chunk_to_doc = []
            
            for doc in batch:
                chunks = self.chunk_document(
                    doc["content"],
                    doc.get("metadata", {}),
                    max_tokens,
                    overlap,
                    doc.get("id"),
                )
                for chunk in chunks:
                    batch_chunks.append(chunk)
                    chunk_to_doc.append(doc.get("id"))
            
            if not batch_chunks:
                continue
            
            # Embed chunks
            texts = [c.content for c in batch_chunks]
            response = await self.embed_texts(texts)
            
            for chunk, embedding in zip(batch_chunks, response.embeddings):
                chunk.metadata["embedding"] = embedding
                chunk.metadata["embedding_model"] = response.model
                chunk.metadata["embedding_dimensions"] = response.dimensions
                all_chunks.append(chunk)

        return all_chunks

    def get_token_count(self, text: str) -> int:
        """Get token count for text."""
        return len(self._token_counter.encode(text))

    def estimate_cost(self, token_count: int) -> float:
        """Estimate cost in USD."""
        # OpenAI pricing (approximate)
        if self.config.provider == EmbeddingProvider.OPENAI:
            if "3-small" in self.config.model:
                return (token_count / 1_000_000) * 0.02
            elif "3-large" in self.config.model:
                return (token_count / 1_000_000) * 0.13
            elif "ada-002" in self.config.model:
                return (token_count / 1_000_000) * 0.10
        return 0.0


# Global embedding pipeline instance
_embedding_pipeline: Optional[EmbeddingPipeline] = None


def get_embedding_pipeline() -> EmbeddingPipeline:
    """Get or create embedding pipeline singleton."""
    global _embedding_pipeline
    if _embedding_pipeline is None:
        _embedding_pipeline = EmbeddingPipeline(EmbeddingConfig())
    return _embedding_pipeline


def init_embedding_pipeline(
    provider: EmbeddingProvider = EmbeddingProvider.OPENAI,
    model: str = "text-embedding-3-small",
    dimensions: int = 1536,
    api_key: Optional[str] = None,
    redis_url: str = "redis://localhost:6379/0",
) -> EmbeddingPipeline:
    """Initialize embedding pipeline."""
    global _embedding_pipeline
    config = EmbeddingConfig(
        provider=provider,
        model=model,
        dimensions=dimensions,
        api_key=api_key,
        redis_url=redis_url,
    )
    _embedding_pipeline = EmbeddingPipeline(config)
    return _embedding_pipeline