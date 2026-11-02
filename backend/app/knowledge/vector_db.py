"""Vector Database Service with pgvector support.

Provides high-performance vector operations using PostgreSQL pgvector extension.
Supports HNSW and IVFFlat indexes for scalable similarity search.
"""

import json
import logging
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from pgvector.sqlalchemy import Vector

from app.core.config import get_settings
from app.db.database import Base
from app.models.intelligence import KnowledgeVector
from app.knowledge.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1000
CHUNK_OVERLAP = 200
MAX_CHUNKS_PER_DOC = 100


class VectorDBService:
    """Vector database operations using pgvector."""
    
    def __init__(self):
        self.settings = get_settings()
        self.provider = get_embedding_provider()
    
    async def ensure_index(self, db: AsyncSession, index_type: str = "hnsw", 
                          m: int = 16, ef_construction: int = 64) -> bool:
        """Create HNSW or IVFFlat index on knowledge_vectors.embedding column."""
        try:
            if index_type == "hnsw":
                await db.execute(text(
                    f"CREATE INDEX IF NOT EXISTS idx_knowledge_vectors_hnsw "
                    f"ON knowledge_vectors USING hnsw (embedding vector_cosine_ops) "
                    f"WITH (m = {m}, ef_construction = {ef_construction})"
                ))
            elif index_type == "ivfflat":
                await db.execute(text(
                    f"CREATE INDEX IF NOT EXISTS idx_knowledge_vectors_ivfflat "
                    f"ON knowledge_vectors USING ivfflat (embedding vector_cosine_ops) "
                    f"WITH (lists = 100)"
                ))
            await db.commit()
            logger.info(f"Created {index_type} index on knowledge_vectors.embedding")
            return True
        except Exception as e:
            logger.error(f"Failed to create vector index: {e}")
            await db.rollback()
            return False
    
    async def upsert_vectors(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        source_type: str,
        source_id: str,
        chunks: list[dict[str, Any]],
        metadata: Optional[dict] = None,
        source_updated_at: Optional[Any] = None,
    ) -> int:
        """Upsert vector embeddings for document chunks."""
        if not chunks:
            return 0
        
        texts = [chunk["text"] for chunk in chunks]
        vectors = await self.provider.embed_many(texts)
        
        inserted = 0
        for i, (chunk, vector) in enumerate(zip(chunks, vectors)):
            content_hash = chunk.get("hash") or self._hash_text(chunk["text"])
            
            stmt = pg_insert(KnowledgeVector).values(
                id=str(uuid4()),
                organization_id=organization_id,
                source_type=source_type,
                source_id=source_id,
                chunk_index=i,
                chunk_text=chunk["text"],
                content_hash=content_hash,
                embedding=json.dumps(vector),
                provider=self.provider.name,
                dim=len(vector),
                source_updated_at=source_updated_at,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["organization_id", "source_type", "source_id", "chunk_index"],
                set_={
                    "chunk_text": chunk["text"],
                    "content_hash": content_hash,
                    "embedding": json.dumps(vector),
                    "provider": self.provider.name,
                    "dim": len(vector),
                    "source_updated_at": source_updated_at,
                    "metadata_json": json.dumps(metadata) if metadata else None,
                    "updated_at": func.now(),
                }
            )
            await db.execute(stmt)
            inserted += 1
        
        await db.commit()
        return inserted
    
    async def delete_vectors(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        source_type: str,
        source_id: str,
    ) -> int:
        """Delete all vectors for a source document."""
        result = await db.execute(
            delete(KnowledgeVector).where(
                KnowledgeVector.organization_id == organization_id,
                KnowledgeVector.source_type == source_type,
                KnowledgeVector.source_id == source_id,
            )
        )
        await db.commit()
        return result.rowcount
    
    async def search_vectors(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query_vector: list[float],
        source_types: Optional[list[str]] = None,
        limit: int = 10,
        threshold: float = 0.7,
    ) -> list[dict[str, Any]]:
        """Search vectors using cosine similarity with pgvector."""
        query = (
            select(KnowledgeVector)
            .where(KnowledgeVector.organization_id == organization_id)
        )
        
        if source_types:
            query = query.where(KnowledgeVector.source_type.in_(source_types))
        
        if self.provider.name != "deterministic":
            query = query.where(KnowledgeVector.provider == self.provider.name)
        
        query = query.order_by(
            KnowledgeVector.embedding.cosine_distance(query_vector)
        ).limit(limit)
        
        results = await db.execute(query)
        rows = results.scalars().all()
        
        output = []
        for row in rows:
            vector = json.loads(row.embedding) if row.embedding else []
            if vector:
                similarity = self.provider.cosine(query_vector, vector)
                if similarity >= threshold:
                    output.append({
                        "source_type": row.source_type,
                        "source_id": row.source_id,
                        "chunk_index": row.chunk_index,
                        "chunk_text": row.chunk_text,
                        "similarity": similarity,
                        "metadata": json.loads(row.metadata_json) if row.metadata_json else {},
                        "provider": row.provider,
                        "indexed_at": row.indexed_at,
                    })
        
        return output
    
    async def hybrid_search(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        query_vector: list[float],
        source_types: Optional[list[str]] = None,
        limit: int = 10,
        semantic_weight: float = 0.7,
        lexical_weight: float = 0.3,
    ) -> list[dict[str, Any]]:
        """Hybrid search combining semantic (vector) + lexical (BM25) scores."""
        from app.knowledge.semantic_search import _query_tokens, _lexical_score
        
        query_tokens = _query_tokens(query)
        
        query_obj = (
            select(KnowledgeVector)
            .where(KnowledgeVector.organization_id == organization_id)
        )
        
        if source_types:
            query_obj = query_obj.where(KnowledgeVector.source_type.in_(source_types))
        
        if self.provider.name != "deterministic":
            query_obj = query_obj.where(KnowledgeVector.provider == self.provider.name)
        
        query_obj = query_obj.limit(500)
        results = await db.execute(query_obj)
        rows = results.scalars().all()
        
        scored = []
        for row in rows:
            vector = json.loads(row.embedding) if row.embedding else []
            
            if vector and row.provider == self.provider.name:
                semantic = self.provider.cosine(query_vector, vector)
            else:
                semantic = 0.0
            
            lexical = _lexical_score(query_tokens, row)
            combined = semantic_weight * semantic + lexical_weight * lexical
            
            if combined > 0:
                scored.append({
                    "source_type": row.source_type,
                    "source_id": row.source_id,
                    "chunk_index": row.chunk_index,
                    "chunk_text": row.chunk_text,
                    "semantic_score": semantic,
                    "lexical_score": lexical,
                    "combined_score": combined,
                    "metadata": json.loads(row.metadata_json) if row.metadata_json else {},
                    "provider": row.provider,
                })
        
        scored.sort(key=lambda x: x["combined_score"], reverse=True)
        return scored[:limit]
    
    def _hash_text(self, text: str) -> str:
        import hashlib
        return hashlib.sha256(text.encode()).hexdigest()[:64]
    
    def chunk_text(self, text: str) -> list[dict[str, Any]]:
        """Split text into overlapping chunks."""
        if not text:
            return []
        
        words = text.split()
        chunks = []
        
        for i in range(0, len(words), CHUNK_SIZE - CHUNK_OVERLAP):
            chunk_words = words[i:i + CHUNK_SIZE]
            if not chunk_words:
                break
            chunk_text = " ".join(chunk_words)
            chunks.append({
                "text": chunk_text,
                "hash": self._hash_text(chunk_text),
            })
            if len(chunks) >= MAX_CHUNKS_PER_DOC:
                break
        
        return chunks


vector_db_service = VectorDBService()