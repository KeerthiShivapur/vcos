"""
Core Intelligence Layer for VCOS.

Provides:
- Vector Database (pgvector + local SQLite fallback)
- RAG Pipeline (Retrieval + Generation + Citations)
- Semantic Search (Hybrid BM25 + Vector + Query Expansion + Fact Check + Synthesis)
"""

from app.core.intelligence.vector_db import (
    VectorStore,
    EmbeddingProvider,
    Chunker,
    Retriever,
    Reranker,
    VectorDocument,
    SearchResult,
    VectorIndexType,
    VectorDistanceMetric,
    IndexConfig,
    LocalVectorStore,
    create_vector_store,
)

from app.core.intelligence.rag_pipeline import (
    RAGPipeline,
    ConversationManager,
    CitationExtractor,
    QueryExpander,
    FactChecker,
    AnswerSynthesizer,
    LLMClient,
    LLMProvider,
    LLMMessage,
    LLMResponse,
)

from app.core.intelligence.semantic_search import (
    SemanticSearchEngine,
    SemanticCache,
    SemanticRouter,
)

__all__ = [
    # Vector DB
    "VectorStore",
    "EmbeddingProvider",
    "Chunker",
    "Retriever",
    "Reranker",
    "VectorDocument",
    "SearchResult",
    "VectorIndexType",
    "VectorDistanceMetric",
    "IndexConfig",
    "LocalVectorStore",
    "create_vector_store",
    # RAG Pipeline
    "RAGPipeline",
    "ConversationManager",
    "CitationExtractor",
    "QueryExpander",
    "FactChecker",
    "AnswerSynthesizer",
    "LLMClient",
    "LLMProvider",
    "LLMMessage",
    "LLMResponse",
    # Semantic Search
    "SemanticSearchEngine",
    "SemanticCache",
    "SemanticRouter",
]