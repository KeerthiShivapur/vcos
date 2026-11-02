from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import json
import uuid
import asyncio
import math
import aiosqlite
from contextlib import asynccontextmanager


class VectorDistanceMetric(str, Enum):
    COSINE = "cosine"
    EUCLIDEAN = "l2"
    INNER_PRODUCT = "inner_product"


@dataclass
class VectorDocument:
    id: str
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    document_id: Optional[str] = None
    chunk_index: int = 0
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SearchResult:
    document: VectorDocument
    score: float
    distance: float


class LocalVectorStore:
    """SQLite-based vector store for development without PostgreSQL/pgvector."""
    
    def __init__(self, db_path: str = "./local_vectors.db", dimension: int = 1536):
        self.db_path = db_path
        self.dimension = dimension
        self._initialized = False
        self._conn: Optional[aiosqlite.Connection] = None
    
    async def initialize(self):
        self._conn = await aiosqlite.connect(self.db_path)
        self._conn.row_factory = aiosqlite.Row
        
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS vector_documents (
                id TEXT PRIMARY KEY,
                document_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL DEFAULT 0,
                content TEXT NOT NULL,
                embedding TEXT NOT NULL,
                metadata TEXT DEFAULT '{}',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(document_id, chunk_index)
            );
        """)
        
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vector_documents_document_id 
            ON vector_documents(document_id);
        """)
        
        await self._conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vector_documents_created_at 
            ON vector_documents(created_at DESC);
        """)
        
        await self._conn.commit()
        self._initialized = True
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(y * y for y in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot_product / (norm_a * norm_b)
    
    def _euclidean_distance(self, a: List[float], b: List[float]) -> float:
        """Compute Euclidean distance between two vectors."""
        return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))
    
    def _inner_product(self, a: List[float], b: List[float]) -> float:
        """Compute inner product between two vectors."""
        return sum(x * y for x, y in zip(a, b))
    
    async def upsert_documents(self, documents: List[VectorDocument]) -> int:
        if not self._initialized:
            await self.initialize()
        
        if not documents:
            return 0
        
        count = 0
        for doc in documents:
            embedding_json = json.dumps(doc.embedding)
            metadata_json = json.dumps(doc.metadata)
            
            await self._conn.execute("""
                INSERT INTO vector_documents (id, document_id, chunk_index, content, embedding, metadata, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (document_id, chunk_index) DO UPDATE SET
                    content = excluded.content,
                    embedding = excluded.embedding,
                    metadata = excluded.metadata,
                    updated_at = excluded.updated_at
            """, (
                doc.id, doc.document_id, doc.chunk_index, doc.content,
                embedding_json, metadata_json,
                doc.created_at.isoformat(), doc.updated_at.isoformat()
            ))
            count += 1
        
        await self._conn.commit()
        return count
    
    async def delete_documents(self, document_ids: List[str]) -> int:
        if not self._initialized:
            await self.initialize()
        
        if not document_ids:
            return 0
        
        placeholders = ",".join("?" * len(document_ids))
        cursor = await self._conn.execute(
            f"DELETE FROM vector_documents WHERE document_id IN ({placeholders})",
            document_ids
        )
        await self._conn.commit()
        return cursor.rowcount
    
    async def search(
        self,
        query_embedding: List[float],
        limit: int = 10,
        threshold: float = 0.0,
        filter_metadata: Dict[str, Any] = None,
        document_ids: List[str] = None,
        distance_metric: VectorDistanceMetric = VectorDistanceMetric.COSINE
    ) -> List[SearchResult]:
        if not self._initialized:
            await self.initialize()
        
        # Build query with filters
        where_clauses = []
        params = []
        
        if document_ids:
            placeholders = ",".join("?" * len(document_ids))
            where_clauses.append(f"document_id IN ({placeholders})")
            params.extend(document_ids)
        
        if filter_metadata:
            for key, value in filter_metadata.items():
                where_clauses.append(f"json_extract(metadata, '$.{key}') = ?")
                params.append(str(value))
        
        where_clause = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
            SELECT id, document_id, chunk_index, content, embedding, metadata, created_at, updated_at
            FROM vector_documents
            {where_clause}
        """
        
        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        
        results = []
        for row in rows:
            doc = VectorDocument(
                id=row["id"],
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                embedding=json.loads(row["embedding"]),
                metadata=json.loads(row["metadata"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"])
            )
            
            # Compute similarity/distance
            if distance_metric == VectorDistanceMetric.COSINE:
                similarity = self._cosine_similarity(query_embedding, doc.embedding)
                distance = 1.0 - similarity
                score = similarity
            elif distance_metric == VectorDistanceMetric.EUCLIDEAN:
                distance = self._euclidean_distance(query_embedding, doc.embedding)
                score = 1.0 / (1.0 + distance)
            else:  # INNER_PRODUCT
                score = self._inner_product(query_embedding, doc.embedding)
                distance = 1.0 - score
            
            if score >= threshold:
                results.append(SearchResult(document=doc, score=score, distance=distance))
        
        # Sort by score descending
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
    
    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        limit: int = 10,
        alpha: float = 0.5,
        filter_metadata: Dict[str, Any] = None
    ) -> List[SearchResult]:
        """
        Hybrid search combining vector similarity with BM25-like text search.
        alpha: weight for vector search (1-alpha for text search)
        """
        if not self._initialized:
            await self.initialize()
        
        # Simple text search using SQLite FTS-like approach
        where_clauses = []
        params = []
        
        if filter_metadata:
            for key, value in filter_metadata.items():
                where_clauses.append(f"json_extract(metadata, '$.{key}') = ?")
                params.append(str(value))
        
        # Add text search
        where_clauses.append("(content LIKE ? OR content LIKE ?)")
        params.extend([f"%{query_text}%", f"%{query_text.lower()}%"])
        
        where_clause = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
            SELECT id, document_id, chunk_index, content, embedding, metadata, created_at, updated_at
            FROM vector_documents
            {where_clause}
        """
        
        cursor = await self._conn.execute(query, params)
        rows = await cursor.fetchall()
        
        results = []
        for row in rows:
            doc = VectorDocument(
                id=row["id"],
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                embedding=json.loads(row["embedding"]),
                metadata=json.loads(row["metadata"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"])
            )
            
            # Vector similarity
            vector_score = self._cosine_similarity(query_embedding, doc.embedding)
            
            # Text score (simple TF-IDF-like scoring)
            text_score = self._compute_text_score(query_text, doc.content)
            
            # Combined score
            combined_score = alpha * vector_score + (1 - alpha) * text_score
            distance = 1.0 - combined_score
            
            results.append(SearchResult(document=doc, score=combined_score, distance=distance))
        
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:limit]
    
    def _compute_text_score(self, query: str, content: str) -> float:
        """Simple text relevance scoring."""
        query_terms = query.lower().split()
        content_lower = content.lower()
        
        if not query_terms:
            return 0.0
        
        matches = sum(1 for term in query_terms if term in content_lower)
        return matches / len(query_terms)
    
    async def get_document_chunks(self, document_id: str) -> List[VectorDocument]:
        if not self._initialized:
            await self.initialize()
        
        cursor = await self._conn.execute(
            "SELECT id, document_id, chunk_index, content, embedding, metadata, created_at, updated_at "
            "FROM vector_documents WHERE document_id = ? ORDER BY chunk_index",
            (document_id,)
        )
        rows = await cursor.fetchall()
        
        return [
            VectorDocument(
                id=row["id"],
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                content=row["content"],
                embedding=json.loads(row["embedding"]),
                metadata=json.loads(row["metadata"]),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=datetime.fromisoformat(row["updated_at"])
            )
            for row in rows
        ]
    
    async def close(self):
        if self._conn:
            await self._conn.close()
            self._initialized = False