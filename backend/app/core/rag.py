"""
RAG (Retrieval-Augmented Generation) Pipeline for VCOS Intelligence Layer.

Provides:
- Document ingestion and processing
- Vector storage and retrieval
- Context-aware generation with citations
- Query rewriting and expansion
- Multi-hop reasoning
- Evaluation metrics
"""

import asyncio
import hashlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Tuple, Callable

from app.core.vector_db import VectorDatabase, VectorDocument, SearchResult, HybridSearchResult
from app.core.embeddings import EmbeddingPipeline, DocumentChunk, EmbeddingProvider, EmbeddingConfig

logger = logging.getLogger(__name__)


class RetrievalStrategy(str, Enum):
    """Retrieval strategies."""
    VECTOR = "vector"
    KEYWORD = "keyword"
    HYBRID = "hybrid"
    MULTI_QUERY = "multi_query"
    RECURSIVE = "recursive"


class GenerationModel(str, Enum):
    """Generation model providers."""
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    LOCAL = "local"
    AZURE_OPENAI = "azure_openai"


@dataclass
class IngestionConfig:
    """Document ingestion configuration."""
    chunk_size: int = 1000
    chunk_overlap: int = 200
    max_chunk_size: int = 8000
    min_chunk_size: int = 100
    embedding_model: str = "text-embedding-3-small"
    collection_name: str = "documents"
    extract_metadata: bool = True
    generate_summaries: bool = False


@dataclass
class RetrievalConfig:
    """Retrieval configuration."""
    strategy: RetrievalStrategy = RetrievalStrategy.HYBRID
    top_k: int = 10
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    similarity_threshold: float = 0.5
    metadata_filters: Dict[str, Any] = field(default_factory=dict)
    rerank: bool = True
    rerank_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    max_context_tokens: int = 4000


@dataclass
class GenerationConfig:
    """Generation configuration."""
    model: GenerationModel = GenerationModel.OPENAI
    model_name: str = "gpt-4-turbo-preview"
    temperature: float = 0.1
    max_tokens: int = 2000
    system_prompt: str = ""
    citation_format: str = "[{index}]"
    include_sources: bool = True


@dataclass
class Document:
    """Source document for ingestion."""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RetrievedContext:
    """Retrieved context for generation."""
    chunks: List[SearchResult]
    total_tokens: int
    sources: List[Dict[str, Any]]


@dataclass
class RAGResponse:
    """RAG pipeline response."""
    answer: str
    citations: List[Dict[str, Any]]
    contexts: List[SearchResult]
    confidence: float
    tokens_used: int
    latency_ms: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryAnalysis:
    """Analyzed query for retrieval."""
    original_query: str
    rewritten_query: str
    sub_queries: List[str]
    intent: str
    entities: List[str]
    keywords: List[str]


class DocumentProcessor:
    """Process documents for ingestion."""

    def __init__(self, embedding_pipeline: EmbeddingPipeline, config: IngestionConfig):
        self.embedding_pipeline = embedding_pipeline
        self.config = config

    async def process_document(self, document: Document) -> List[DocumentChunk]:
        """Process a single document into chunks with embeddings."""
        # Prepare metadata
        metadata = {
            **document.metadata,
            "source_id": document.id,
            "source": document.source,
            "ingested_at": datetime.utcnow().isoformat(),
        }

        # Chunk and embed
        chunks = await self.embedding_pipeline.embed_document(
            content=document.content,
            metadata=metadata,
            max_tokens=self.config.max_chunk_size,
            overlap=self.config.chunk_overlap,
        )

        return chunks

    async def process_documents_batch(
        self,
        documents: List[Document],
        batch_size: int = 50,
    ) -> List[DocumentChunk]:
        """Process multiple documents in batches."""
        all_chunks = []
        
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            
            # Prepare documents for embedding pipeline
            doc_dicts = [
                {
                    "id": doc.id,
                    "content": doc.content,
                    "metadata": {
                        **doc.metadata,
                        "source_id": doc.id,
                        "source": doc.source,
                    },
                }
                for doc in batch
            ]
            
            chunks = await self.embedding_pipeline.embed_documents_batch(
                doc_dicts,
                max_tokens=self.config.max_chunk_size,
                overlap=self.config.chunk_overlap,
            )
            
            all_chunks.extend(chunks)

        return all_chunks


class QueryAnalyzer:
    """Analyze and rewrite queries for better retrieval."""

    def __init__(self, generation_model: GenerationModel = GenerationModel.OPENAI):
        self.generation_model = generation_model

    async def analyze(self, query: str, context: Optional[Dict[str, Any]] = None) -> QueryAnalysis:
        """Analyze query for retrieval optimization."""
        # For now, return basic analysis
        # In production, use LLM to rewrite/expand query
        
        keywords = query.lower().split()
        
        return QueryAnalysis(
            original_query=query,
            rewritten_query=query,
            sub_queries=[query],
            intent="question_answering",
            entities=[],
            keywords=keywords,
        )

    async def expand_query(self, query: str, num_variations: int = 3) -> List[str]:
        """Generate query variations for multi-query retrieval."""
        # Simple expansion - in production use LLM
        variations = [query]
        
        # Add synonyms/related terms
        if "how" in query.lower():
            variations.append(query.replace("how", "what is the process"))
        if "what" in query.lower():
            variations.append(query.replace("what", "define"))
        
        return variations[:num_variations]


class Retriever:
    """Retrieve relevant documents for queries."""

    def __init__(
        self,
        vector_db: VectorDatabase,
        embedding_pipeline: EmbeddingPipeline,
        config: RetrievalConfig,
    ):
        self.vector_db = vector_db
        self.embedding_pipeline = embedding_pipeline
        self.config = config

    async def retrieve(
        self,
        query: str,
        collection: Optional[str] = None,
        config: Optional[RetrievalConfig] = None,
    ) -> RetrievedContext:
        """Retrieve relevant chunks for query."""
        cfg = config or self.config
        collection = collection or cfg.metadata_filters.get("collection", "documents")
        
        # Generate query embedding
        response = await self.embedding_pipeline.embed_texts([query])
        query_vector = response.embeddings[0]

        # Search based on strategy
        if cfg.strategy == RetrievalStrategy.VECTOR:
            results = await self.vector_db.search(
                collection=collection,
                query_vector=query_vector,
                limit=cfg.top_k,
                filter_metadata=cfg.metadata_filters,
            )
        elif cfg.strategy == RetrievalStrategy.KEYWORD:
            # Use metadata search as keyword fallback
            results = await self.vector_db.search_by_metadata(
                collection=collection,
                filter_metadata=cfg.metadata_filters,
                limit=cfg.top_k,
            )
        elif cfg.strategy == RetrievalStrategy.HYBRID:
            results = await self.vector_db.search_hybrid(
                collection=collection,
                query_vector=query_vector,
                query_text=query,
                limit=cfg.top_k,
                vector_weight=cfg.vector_weight,
                keyword_weight=cfg.keyword_weight,
                filter_metadata=cfg.metadata_filters,
            )
        elif cfg.strategy == RetrievalStrategy.MULTI_QUERY:
            results = await self._multi_query_retrieve(query, collection, cfg)
        else:
            results = await self.vector_db.search(
                collection=collection,
                query_vector=query_vector,
                limit=cfg.top_k,
            )

        # Filter by similarity threshold
        filtered = [r for r in results if r.score >= cfg.similarity_threshold]

        # Rerank if enabled
        if cfg.rerank and filtered:
            filtered = await self._rerank(query, filtered)

        # Build context
        return self._build_context(filtered)

    async def _multi_query_retrieve(
        self,
        query: str,
        collection: str,
        cfg: RetrievalConfig,
    ) -> List[SearchResult]:
        """Retrieve using multiple query variations."""
        analyzer = QueryAnalyzer()
        sub_queries = await analyzer.expand_query(query)
        
        all_results = []
        for sub_query in sub_queries:
            response = await self.embedding_pipeline.embed_texts([sub_query])
            sub_vector = response.embeddings[0]
            
            results = await self.vector_db.search(
                collection=collection,
                query_vector=sub_vector,
                limit=cfg.top_k,
                filter_metadata=cfg.metadata_filters,
            )
            all_results.extend(results)

        # Deduplicate and merge scores
        seen = {}
        for result in all_results:
            if result.id not in seen or result.score > seen[result.id].score:
                seen[result.id] = result

        merged = list(seen.values())
        merged.sort(key=lambda x: x.score, reverse=True)
        return merged[:cfg.top_k]

    async def _rerank(
        self,
        query: str,
        results: List[SearchResult],
    ) -> List[SearchResult]:
        """Rerank results using cross-encoder."""
        try:
            from sentence_transformers import CrossEncoder
            reranker = CrossEncoder(self.config.rerank_model)
            
            pairs = [(query, r.content) for r in results]
            scores = reranker.predict(pairs)
            
            for result, score in zip(results, scores):
                result.score = float(score)
            
            results.sort(key=lambda x: x.score, reverse=True)
        except Exception as e:
            logger.warning(f"Reranking failed: {e}")
        
        return results

    def _build_context(self, results: List[SearchResult]) -> RetrievedContext:
        """Build context from retrieved results."""
        total_tokens = 0
        sources = []
        chunks = []

        for i, result in enumerate(results):
            # Estimate tokens
            tokens = len(result.content.split()) * 1.3  # Rough estimate
            if total_tokens + tokens > self.config.max_context_tokens:
                break
            
            total_tokens += int(tokens)
            chunks.append(result)
            
            sources.append({
                "index": i + 1,
                "id": result.id,
                "content": result.content[:200] + "..." if len(result.content) > 200 else result.content,
                "metadata": result.metadata,
                "score": result.score,
            })

        return RetrievedContext(
            chunks=chunks,
            total_tokens=total_tokens,
            sources=sources,
        )


class Generator:
    """Generate answers from retrieved context."""

    def __init__(self, config: GenerationConfig):
        self.config = config
        self._client = None

    async def initialize(self):
        """Initialize generation client."""
        if self.config.model in [GenerationModel.OPENAI, GenerationModel.AZURE_OPENAI]:
            import openai
            self._client = openai.AsyncOpenAI(
                api_key=getattr(settings, 'OPENAI_API_KEY', None),
                base_url=getattr(settings, 'OPENAI_API_BASE', None),
            )

    async def generate(
        self,
        query: str,
        context: RetrievedContext,
        config: Optional[GenerationConfig] = None,
    ) -> RAGResponse:
        """Generate answer from context."""
        start_time = time.time()
        cfg = config or self.config

        # Build prompt
        prompt = self._build_prompt(query, context, cfg)

        # Generate response
        answer = await self._generate_completion(prompt, cfg)

        # Extract citations
        citations = self._extract_citations(answer, context)

        # Calculate confidence (simple heuristic)
        confidence = min(1.0, len(context.chunks) * 0.15 + 0.3) if context.chunks else 0.1

        latency_ms = int((time.time() - start_time) * 1000)

        return RAGResponse(
            answer=answer,
            citations=citations,
            contexts=context.chunks,
            confidence=confidence,
            tokens_used=context.total_tokens,
            latency_ms=latency_ms,
            metadata={
                "model": cfg.model_name,
                "temperature": cfg.temperature,
                "retrieved_count": len(context.chunks),
            },
        )

    def _build_prompt(
        self,
        query: str,
        context: RetrievedContext,
        cfg: GenerationConfig,
    ) -> str:
        """Build generation prompt with context."""
        system_prompt = cfg.system_prompt or """You are a helpful AI assistant. Answer questions based only on the provided context. 
If the context doesn't contain enough information, say so. Always cite your sources using the format [1], [2], etc."""

        context_text = ""
        for i, source in enumerate(context.sources):
            citation_marker = cfg.citation_format.format(index=i+1)
            context_text += f"\n{citation_marker} Source {i+1}:\n{source['content']}\n"

        prompt = f"""{system_prompt}

Context:
{context_text}

Question: {query}

Answer:"""

        return prompt

    async def _generate_completion(self, prompt: str, cfg: GenerationConfig) -> str:
        """Generate completion using LLM."""
        if not self._client:
            await self.initialize()

        if self.config.model in [GenerationModel.OPENAI, GenerationModel.AZURE_OPENAI]:
            response = await self._client.chat.completions.create(
                model=cfg.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
            )
            return response.choices[0].message.content

        # Fallback for local models
        return "Generation not implemented for this model."

    def _extract_citations(
        self,
        answer: str,
        context: RetrievedContext,
    ) -> List[Dict[str, Any]]:
        """Extract citations from answer."""
        import re
        
        # Find citation markers like [1], [2], etc.
        citation_pattern = r'\[(\d+)\]'
        matches = re.findall(citation_pattern, answer)
        
        citations = []
        for match in matches:
            idx = int(match) - 1
            if 0 <= idx < len(context.sources):
                source = context.sources[idx]
                citations.append({
                    "index": idx + 1,
                    "source_id": source["id"],
                    "content": source["content"],
                    "metadata": source["metadata"],
                })

        return citations

    async def stream_generate(
        self,
        query: str,
        context: RetrievedContext,
        config: Optional[GenerationConfig] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream generation response."""
        cfg = config or self.config
        prompt = self._build_prompt(query, context, cfg)

        if self.config.model in [GenerationModel.OPENAI, GenerationModel.AZURE_OPENAI]:
            if not self._client:
                await self.initialize()

            stream = await self._client.chat.completions.create(
                model=cfg.model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=cfg.temperature,
                max_tokens=cfg.max_tokens,
                stream=True,
            )

            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content


class RAGPipeline:
    """
    Complete RAG Pipeline.

    Orchestrates:
    1. Document ingestion
    2. Query analysis
    3. Retrieval
    4. Generation
    5. Evaluation
    """

    def __init__(
        self,
        vector_db: VectorDatabase,
        embedding_pipeline: EmbeddingPipeline,
        ingestion_config: Optional[IngestionConfig] = None,
        retrieval_config: Optional[RetrievalConfig] = None,
        generation_config: Optional[GenerationConfig] = None,
    ):
        self.vector_db = vector_db
        self.embedding_pipeline = embedding_pipeline
        self.ingestion_config = ingestion_config or IngestionConfig()
        self.retrieval_config = retrieval_config or RetrievalConfig()
        self.generation_config = generation_config or GenerationConfig()

        self.processor = DocumentProcessor(embedding_pipeline, self.ingestion_config)
        self.analyzer = QueryAnalyzer()
        self.retriever = Retriever(vector_db, embedding_pipeline, self.retrieval_config)
        self.generator = Generator(self.generation_config)

    async def initialize(self):
        """Initialize all components."""
        await self.embedding_pipeline.initialize()
        await self.generator.initialize()
        
        # Ensure collection exists
        await self.vector_db.create_collection(
            name=self.ingestion_config.collection_name,
            dimensions=self.embedding_pipeline.config.dimensions,
        )

    async def close(self):
        """Close all connections."""
        await self.embedding_pipeline.close()

    # ==================== Ingestion ====================

    async def ingest_document(self, document: Document) -> List[str]:
        """Ingest a single document."""
        chunks = await self.processor.process_document(document)
        
        # Store in vector DB
        vectors = [
            VectorDocument(
                id=chunk.id,
                collection=self.ingestion_config.collection_name,
                vector=chunk.metadata["embedding"],
                content=chunk.content,
                metadata={k: v for k, v in chunk.metadata.items() if k != "embedding"},
            )
            for chunk in chunks
        ]
        
        ids = await self.vector_db.upsert(self.ingestion_config.collection_name, vectors)
        return ids

    async def ingest_documents(self, documents: List[Document]) -> List[str]:
        """Ingest multiple documents."""
        chunks = await self.processor.process_documents_batch(documents)
        
        vectors = [
            VectorDocument(
                id=chunk.id,
                collection=self.ingestion_config.collection_name,
                vector=chunk.metadata["embedding"],
                content=chunk.content,
                metadata={k: v for k, v in chunk.metadata.items() if k != "embedding"},
            )
            for chunk in chunks
        ]
        
        ids = await self.vector_db.upsert_batch(
            self.ingestion_config.collection_name,
            [asdict(v) for v in vectors],
        )
        return ids

    async def delete_document(self, document_id: str) -> int:
        """Delete document by source ID."""
        # Find chunks by source_id
        chunks = await self.vector_db.search_by_metadata(
            collection=self.ingestion_config.collection_name,
            filter_metadata={"source_id": document_id},
            limit=10000,
        )
        
        if not chunks:
            return 0
        
        ids = [c.id for c in chunks]
        return await self.vector_db.delete(self.ingestion_config.collection_name, ids)

    # ==================== Query ====================

    async def query(
        self,
        question: str,
        collection: Optional[str] = None,
        retrieval_config: Optional[RetrievalConfig] = None,
        generation_config: Optional[GenerationConfig] = None,
    ) -> RAGResponse:
        """Full RAG query pipeline."""
        # Analyze query
        analysis = await self.analyzer.analyze(question)
        
        # Retrieve
        context = await self.retriever.retrieve(
            query=analysis.rewritten_query,
            collection=collection,
            config=retrieval_config,
        )
        
        # Generate
        response = await self.generator.generate(
            query=question,
            context=context,
            config=generation_config,
        )
        
        return response

    async def stream_query(
        self,
        question: str,
        collection: Optional[str] = None,
        retrieval_config: Optional[RetrievalConfig] = None,
        generation_config: Optional[GenerationConfig] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream RAG query response."""
        analysis = await self.analyzer.analyze(question)
        context = await self.retriever.retrieve(
            query=analysis.rewritten_query,
            collection=collection,
            config=retrieval_config,
        )
        
        async for chunk in self.generator.stream_generate(
            query=question,
            context=context,
            config=generation_config,
        ):
            yield chunk

    # ==================== Evaluation ====================

    async def evaluate(
        self,
        test_questions: List[Dict[str, Any]],
        collection: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Evaluate RAG pipeline on test questions."""
        results = []
        total_latency = 0
        total_confidence = 0
        
        for test in test_questions:
            question = test["question"]
            expected_answer = test.get("answer", "")
            
            response = await self.query(question, collection)
            
            results.append({
                "question": question,
                "expected": expected_answer,
                "generated": response.answer,
                "confidence": response.confidence,
                "latency_ms": response.latency_ms,
                "citations_count": len(response.citations),
            })
            
            total_latency += response.latency_ms
            total_confidence += response.confidence

        return {
            "total_questions": len(test_questions),
            "avg_latency_ms": total_latency / len(test_questions) if test_questions else 0,
            "avg_confidence": total_confidence / len(test_questions) if test_questions else 0,
            "results": results,
        }


# Global RAG pipeline instance
_rag_pipeline: Optional[RAGPipeline] = None


def get_rag_pipeline() -> RAGPipeline:
    """Get or create RAG pipeline singleton."""
    global _rag_pipeline
    if _rag_pipeline is None:
        _rag_pipeline = RAGPipeline(
            vector_db=get_vector_db(),
            embedding_pipeline=get_embedding_pipeline(),
        )
    return _rag_pipeline


def init_rag_pipeline(
    vector_db: Optional[VectorDatabase] = None,
    embedding_pipeline: Optional[EmbeddingPipeline] = None,
    ingestion_config: Optional[IngestionConfig] = None,
    retrieval_config: Optional[RetrievalConfig] = None,
    generation_config: Optional[GenerationConfig] = None,
) -> RAGPipeline:
    """Initialize RAG pipeline."""
    global _rag_pipeline
    _rag_pipeline = RAGPipeline(
        vector_db=vector_db or get_vector_db(),
        embedding_pipeline=embedding_pipeline or get_embedding_pipeline(),
        ingestion_config=ingestion_config,
        retrieval_config=retrieval_config,
        generation_config=generation_config,
    )
    return _rag_pipeline


import time
from dataclasses import asdict