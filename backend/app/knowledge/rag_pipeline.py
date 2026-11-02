"""RAG Pipeline - Retrieval-Augmented Generation with Citations.

Implements the complete RAG pipeline:
1. Query understanding and expansion
2. Hybrid retrieval (semantic + lexical)
3. Context assembly with citation tracking
4. LLM generation with grounded responses
5. Citation validation and formatting
"""

import json
import logging
from dataclasses import dataclass
from typing import Any, AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge.vector_db import vector_db_service
from app.knowledge.embeddings import get_embedding_provider
from app.knowledge.semantic_search import search as semantic_search
from app.models.intelligence import KnowledgeVector
from app.core.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    """Single retrieval result with citation metadata."""
    source_type: str
    source_id: str
    chunk_index: int
    chunk_text: str
    similarity: float
    metadata: dict
    citation_id: int


@dataclass
class RAGContext:
    """Assembled context for LLM generation."""
    query: str
    results: list[RetrievalResult]
    total_tokens: int
    max_context_tokens: int = 4000
    
    def to_prompt_context(self) -> str:
        """Format context for LLM prompt with citation markers."""
        lines = ["<context>"]
        for i, result in enumerate(self.results, 1):
            lines.append(f"[{i}] {result.chunk_text[:500]}")
            lines.append(f"    Source: {result.source_type}/{result.source_id}, chunk {result.chunk_index}")
        lines.append("</context>")
        return "\n".join(lines)


class RAGPipeline:
    """End-to-end RAG pipeline with citations."""
    
    def __init__(self):
        self.settings = get_settings()
        self.provider = get_embedding_provider()
        self.max_context_tokens = 4000
        self.max_chunks = 10
    
    async def retrieve(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        query: str,
        kinds: Optional[list[str]] = None,
        limit: int = 10,
    ) -> list[RetrievalResult]:
        """Hybrid retrieval with governance scoping."""
        # Use existing semantic search for governance-scoped retrieval
        search_results = await semantic_search(
            db=db,
            organization_id=organization_id,
            user=user,
            query=query,
            kinds=kinds,
            limit=limit,
        )
        
        results = []
        for i, r in enumerate(search_results.get("results", [])):
            results.append(RetrievalResult(
                source_type=r.get("source_type", ""),
                source_id=r.get("source_id", ""),
                chunk_index=r.get("chunk_index", 0),
                chunk_text=r.get("snippet", ""),
                similarity=r.get("retrieval_score", 0.0),
                metadata={
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "status": r.get("status", ""),
                    "scope": r.get("scope", ""),
                },
                citation_id=i + 1,
            ))
        
        return results
    
    async def retrieve_vectors(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        source_types: Optional[list[str]] = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[RetrievalResult]:
        """Direct vector search without governance (for internal use)."""
        query_vector = (await self.provider.embed_many([query]))[0]
        results = await vector_db_service.search_vectors(
            db=db,
            organization_id=organization_id,
            query_vector=query_vector,
            source_types=source_types,
            limit=limit,
            threshold=threshold,
        )
        
        output = []
        for i, r in enumerate(results):
            output.append(RetrievalResult(
                source_type=r["source_type"],
                source_id=r["source_id"],
                chunk_index=r["chunk_index"],
                chunk_text=r["chunk_text"],
                similarity=r["similarity"],
                metadata=r["metadata"],
                citation_id=i + 1,
            ))
        
        return output
    
    def assemble_context(
        self,
        query: str,
        results: list[RetrievalResult],
        max_tokens: Optional[int] = None,
    ) -> RAGContext:
        """Assemble retrieval results into LLM context with token budgeting."""
        max_t = max_tokens or self.max_context_tokens
        context = RAGContext(
            query=query,
            results=[],
            total_tokens=0,
            max_context_tokens=max_t,
        )
        
        # Rough token estimation: 1 token ~ 4 chars
        for result in results:
            estimated_tokens = len(result.chunk_text) // 4
            if context.total_tokens + estimated_tokens > max_t:
                break
            context.results.append(result)
            context.total_tokens += estimated_tokens
        
        return context
    
    async def generate_answer(
        self,
        context: RAGContext,
        system_prompt: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """Generate streaming answer with citations."""
        from app.core.ai_client import get_ai_client
        
        client = get_ai_client()
        
        system = system_prompt or (
            "You are a helpful AI assistant for organizational knowledge. "
            "Answer based ONLY on the provided context. "
            "Cite sources using [1], [2], etc. "
            "If the context doesn't contain the answer, say so."
        )
        
        user_prompt = f"""Question: {context.query}

{context.to_prompt_context()}

Answer with citations:"""
        
        async for chunk in client.stream_chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1024,
        ):
            yield chunk
    
    async def generate_answer_with_citations(
        self,
        context: RAGContext,
        system_prompt: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate complete answer with structured citations."""
        from app.core.ai_client import get_ai_client
        
        client = get_ai_client()
        
        system = system_prompt or (
            "You are a helpful AI assistant for organizational knowledge. "
            "Answer based ONLY on the provided context. "
            "Cite sources using [1], [2], etc. "
            "If the context doesn't contain the answer, say so."
        )
        
        user_prompt = f"""Question: {context.query}

{context.to_prompt_context()}

Answer with citations:"""
        
        response = await client.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.3,
            max_tokens=1024,
        )
        
        answer = response.get("content", "")
        
        citations = []
        for result in context.results:
            citations.append({
                "id": result.citation_id,
                "source_type": result.source_type,
                "source_id": result.source_id,
                "title": result.metadata.get("title", ""),
                "url": result.metadata.get("url", ""),
                "snippet": result.chunk_text[:200],
                "similarity": round(result.similarity, 4),
            })
        
        return {
            "answer": answer,
            "citations": citations,
            "context_used": len(context.results),
            "total_tokens_estimate": context.total_tokens,
        }
    
    async def query(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user: Any,
        query: str,
        kinds: Optional[list[str]] = None,
        limit: int = 10,
        stream: bool = False,
    ) -> dict[str, Any] | AsyncGenerator[str, None]:
        """Full RAG query: retrieve + generate."""
        # Retrieve
        results = await self.retrieve(
            db=db,
            organization_id=organization_id,
            user=user,
            query=query,
            kinds=kinds,
            limit=limit,
        )
        
        if not results:
            return {
                "answer": "I couldn't find relevant information to answer your question.",
                "citations": [],
                "context_used": 0,
                "query": query,
            }
        
        # Assemble context
        context = self.assemble_context(query, results)
        
        # Generate
        if stream:
            return self.generate_answer(context)
        else:
            return await self.generate_answer_with_citations(context)


rag_pipeline = RAGPipeline()