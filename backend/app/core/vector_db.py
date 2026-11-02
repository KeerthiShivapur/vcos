"""
Vector Database Integration for VCOS Intelligence Layer.

Provides:
- pgvector PostgreSQL extension for vector storage
- Embedding generation and storage
- Vector similarity search
- Hybrid search (BM25 + Vector)
- Collection/namespace management
- Metadata filtering
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

import asyncpg
import numpy as np
from pgvector.asyncpg import register_vector

from app.core.config import settings

logger = logging.getLogger(__name__)


class DistanceMetric(str, Enum):
    """Vector distance metrics."""
    COSINE = "cosine"
    EUCLIDEAN = "l2"
    INNER_PRODUCT = "inner"
    MANHATTAN = "l1"


class IndexType(str, Enum):
    """Vector index types."""
    IVFFLAT = "ivfflat"
    HNSW = "hnsw"
    NONE = "none"


@dataclass
class VectorConfig:
    """Vector database configuration."""
    host: str = "localhost"
    port: int = 5432
    database: str = "vcos"
    user: str = "postgres"
    password: str = "postgres"
    pool_size: int = 20
    dimensions: int = 1536  # OpenAI ada-002 default
    distance_metric: DistanceMetric = DistanceMetric.COSINE
    index_type: IndexType = IndexType.HNSW
    index_params: Dict[str, Any] = field(default_factory=lambda: {"m": 16, "ef_construction": 64})


@dataclass
class Collection:
    """Vector collection/namespace."""
    name: str
    dimensions: int
    distance_metric: DistanceMetric
    description: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class VectorDocument:
    """Document with vector embedding."""
    id: str
    collection: str
    vector: List[float]
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SearchResult:
    """Vector search result."""
    id: str
    score: float
    content: str
    metadata: Dict[str, Any]
    distance: float


@dataclass
class HybridSearchResult:
    """Hybrid search result combining vector and keyword."""
    id: str
    vector_score: float
    keyword_score: float
    combined_score: float
    content: str
    metadata: Dict[str, Any]


class VectorDatabase:
    """
    Vector Database using pgvector.

    Features:
    - Collection management
    - Vector CRUD operations
    - Similarity search with metadata filtering
    - Hybrid search (vector + keyword)
    - Batch operations
    - Index management
    """

    def __init__(self, config: VectorConfig):
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None
        self._collections_cache: Dict[str, Collection] = {}

    async def initialize(self):
        """Initialize connection pool and register pgvector."""
        self._pool = await asyncpg.create_pool(
            host=self.config.host,
            port=self.config.port,
            database=self.config.database,
            user=self.config.user,
            password=self.config.password,
            min_size=5,
            max_size=self.config.pool_size,
            init=self._init_connection,
        )
        await self._ensure_extension()
        await self._load_collections()
        logger.info("Vector Database initialized")

    async def _init_connection(self, conn: asyncpg.Connection):
        """Initialize pgvector for each connection."""
        await register_vector(conn)

    async def _ensure_extension(self):
        """Ensure pgvector extension is installed."""
        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    async def _load_collections(self):
        """Load collection metadata."""
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT name, dimensions, distance_metric, description, metadata, created_at, updated_at FROM vector_collections"
            )
            for row in rows:
                self._collections_cache[row["name"]] = Collection(
                    name=row["name"],
                    dimensions=row["dimensions"],
                    distance_metric=DistanceMetric(row["distance_metric"]),
                    description=row["description"],
                    metadata=row["metadata"] or {},
                    created_at=row["created_at"],
                    updated_at=row["updated_at"],
                )

    async def close(self):
        """Close connection pool."""
        if self._pool:
            await self._pool.close()

    # ==================== Collection Management ====================

    async def create_collection(
        self,
        name: str,
        dimensions: Optional[int] = None,
        distance_metric: Optional[DistanceMetric] = None,
        description: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Collection:
        """Create a new vector collection."""
        dimensions = dimensions or self.config.dimensions
        distance_metric = distance_metric or self.config.distance_metric

        async with self._pool.acquire() as conn:
            # Create collection metadata table
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS vector_collections (
                    name TEXT PRIMARY KEY,
                    dimensions INTEGER NOT NULL,
                    distance_metric TEXT NOT NULL,
                    description TEXT,
                    metadata JSONB DEFAULT '{}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            await conn.execute("""
                INSERT INTO vector_collections (name, dimensions, distance_metric, description, metadata)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (name) DO UPDATE SET
                    dimensions = EXCLUDED.dimensions,
                    distance_metric = EXCLUDED.distance_metric,
                    description = EXCLUDED.description,
                    metadata = EXCLUDED.metadata,
                    updated_at = NOW()
            """, name, dimensions, distance_metric.value, description, metadata or {})

            # Create vectors table for this collection
            table_name = f"vectors_{name.replace('-', '_')}"
            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS {table_name} (
                    id UUID PRIMARY KEY,
                    vector vector({dimensions}) NOT NULL,
                    content TEXT NOT NULL,
                    metadata JSONB DEFAULT '{{}}',
                    created_at TIMESTAMPTZ DEFAULT NOW(),
                    updated_at TIMESTAMPTZ DEFAULT NOW()
                )
            """)

            # Create index
            await self._create_index(conn, table_name, dimensions, distance_metric)

        collection = Collection(
            name=name,
            dimensions=dimensions,
            distance_metric=distance_metric,
            description=description,
            metadata=metadata or {},
        )
        self._collections_cache[name] = collection
        return collection

    async def _create_index(
        self,
        conn: asyncpg.Connection,
        table_name: str,
        dimensions: int,
        distance_metric: DistanceMetric,
    ):
        """Create vector index."""
        index_name = f"idx_{table_name}_vector"
        
        if self.config.index_type == IndexType.HNSW:
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS {index_name} 
                ON {table_name} 
                USING hnsw (vector vector_{distance_metric.value}_ops)
                WITH (m = {self.config.index_params.get('m', 16)}, 
                      ef_construction = {self.config.index_params.get('ef_construction', 64)})
            """)
        elif self.config.index_type == IndexType.IVFFLAT:
            await conn.execute(f"""
                CREATE INDEX IF NOT EXISTS {index_name} 
                ON {table_name} 
                USING ivfflat (vector vector_{distance_metric.value}_ops)
                WITH (lists = {self.config.index_params.get('lists', 100)})
            """)

    async def get_collection(self, name: str) -> Optional[Collection]:
        """Get collection by name."""
        return self._collections_cache.get(name)

    async def list_collections(self) -> List[Collection]:
        """List all collections."""
        return list(self._collections_cache.values())

    async def delete_collection(self, name: str) -> bool:
        """Delete a collection and all its vectors."""
        if name not in self._collections_cache:
            return False

        table_name = f"vectors_{name.replace('-', '_')}"
        async with self._pool.acquire() as conn:
            await conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            await conn.execute("DELETE FROM vector_collections WHERE name = $1", name)

        del self._collections_cache[name]
        return True

    # ==================== Vector Operations ====================

    async def upsert(
        self,
        collection: str,
        vectors: List[VectorDocument],
    ) -> List[str]:
        """Insert or update vectors."""
        if collection not in self._collections_cache:
            raise ValueError(f"Collection not found: {collection}")

        table_name = f"vectors_{collection.replace('-', '_')}"
        ids = []

        async with self._pool.acquire() as conn:
            async with conn.transaction():
                for doc in vectors:
                    doc_id = doc.id or str(uuid.uuid4())
                    ids.append(doc_id)
                    
                    vector_array = np.array(doc.vector, dtype=np.float32)
                    
                    await conn.execute(f"""
                        INSERT INTO {table_name} (id, vector, content, metadata, updated_at)
                        VALUES ($1, $2, $3, $4, NOW())
                        ON CONFLICT (id) DO UPDATE SET
                            vector = EXCLUDED.vector,
                            content = EXCLUDED.content,
                            metadata = EXCLUDED.metadata,
                            updated_at = NOW()
                    """, doc_id, vector_array, doc.content, doc.metadata)

        return ids

    async def upsert_batch(
        self,
        collection: str,
        documents: List[Dict[str, Any]],
        batch_size: int = 100,
    ) -> List[str]:
        """Batch upsert for better performance."""
        all_ids = []
        for i in range(0, len(documents), batch_size):
            batch = documents[i:i + batch_size]
            vectors = [
                VectorDocument(
                    id=d.get("id"),
                    collection=collection,
                    vector=d["vector"],
                    content=d["content"],
                    metadata=d.get("metadata", {}),
                )
                for d in batch
            ]
            ids = await self.upsert(collection, vectors)
            all_ids.extend(ids)
        return all_ids

    async def get(
        self,
        collection: str,
        ids: List[str],
    ) -> List[VectorDocument]:
        """Get vectors by IDs."""
        if collection not in self._collections_cache:
            raise ValueError(f"Collection not found: {collection}")

        table_name = f"vectors_{collection.replace('-', '_')}"
        placeholders = ",".join([f"${i+1}" for i in range(len(ids))])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, vector, content, metadata, created_at, updated_at
                FROM {table_name}
                WHERE id IN ({placeholders})
            """, *ids)

        return [
            VectorDocument(
                id=row["id"],
                collection=collection,
                vector=list(row["vector"]),
                content=row["content"],
                metadata=row["metadata"] or {},
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def delete(self, collection: str, ids: List[str]) -> int:
        """Delete vectors by IDs."""
        if collection not in self._collections_cache:
            raise ValueError(f"Collection not found: {collection}")

        table_name = f"vectors_{collection.replace('-', '_')}"
        placeholders = ",".join([f"${i+1}" for i in range(len(ids))])

        async with self._pool.acquire() as conn:
            result = await conn.execute(f"""
                DELETE FROM {table_name}
                WHERE id IN ({placeholders})
            """, *ids)
            return int(result.split()[-1])

    # ==================== Search Operations ====================

    async def search(
        self,
        collection: str,
        query_vector: List[float],
        limit: int = 10,
        filter_metadata: Optional[Dict[str, Any]] = None,
        distance_metric: Optional[DistanceMetric] = None,
    ) -> List[SearchResult]:
        """Vector similarity search with optional metadata filter."""
        if collection not in self._collections_cache:
            raise ValueError(f"Collection not found: {collection}")

        table_name = f"vectors_{collection.replace('-', '_')}"
        metric = distance_metric or self.config.distance_metric
        
        # Build distance function
        distance_func = {
            DistanceMetric.COSINE: "vector <=> $1",
            DistanceMetric.EUCLIDEAN: "vector <-> $1",
            DistanceMetric.INNER_PRODUCT: "vector <#> $1",
            DistanceMetric.MANHATTAN: "vector <+> $1",
        }[metric]

        query = f"""
            SELECT id, vector, content, metadata, 
                   ({distance_func}) as distance
            FROM {table_name}
        """
        params = [np.array(query_vector, dtype=np.float32)]
        param_idx = 2

        if filter_metadata:
            conditions = []
            for key, value in filter_metadata.items():
                conditions.append(f"metadata->>'{key}' = ${param_idx}")
                params.append(str(value))
                param_idx += 1
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY distance ASC LIMIT ${param_idx}"
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        results = []
        for row in rows:
            distance = float(row["distance"])
            # Convert distance to similarity score (0-1)
            if metric == DistanceMetric.COSINE:
                score = 1 - distance
            elif metric == DistanceMetric.INNER_PRODUCT:
                score = max(0, min(1, (distance + 1) / 2))
            else:
                score = 1 / (1 + distance)
            
            results.append(SearchResult(
                id=str(row["id"]),
                score=score,
                content=row["content"],
                metadata=row["metadata"] or {},
                distance=distance,
            ))

        return results

    async def search_hybrid(
        self,
        collection: str,
        query_vector: List[float],
        query_text: str,
        limit: int = 10,
        vector_weight: float = 0.7,
        keyword_weight: float = 0.3,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[HybridSearchResult]:
        """Hybrid search combining vector similarity and keyword matching."""
        if collection not in self._collections_cache:
            raise ValueError(f"Collection not found: {collection}")

        table_name = f"vectors_{collection.replace('-', '_')}"
        metric = self.config.distance_metric
        distance_func = {
            DistanceMetric.COSINE: "vector <=> $1",
            DistanceMetric.EUCLIDEAN: "vector <-> $1",
            DistanceMetric.INNER_PRODUCT: "vector <#> $1",
        }[metric]

        # Use pg_trgm for keyword search
        query = f"""
            SELECT 
                id, vector, content, metadata,
                ({distance_func}) as vector_distance,
                similarity(content, $2) as keyword_similarity
            FROM {table_name}
        """
        params = [np.array(query_vector, dtype=np.float32), query_text]
        param_idx = 3

        if filter_metadata:
            conditions = []
            for key, value in filter_metadata.items():
                conditions.append(f"metadata->>'{key}' = ${param_idx}")
                params.append(str(value))
                param_idx += 1
            if conditions:
                query += " WHERE " + " AND ".join(conditions)

        query += f" ORDER BY (vector_distance * {1 - vector_weight} - keyword_similarity * {keyword_weight}) ASC LIMIT ${param_idx}"
        params.append(limit)

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        results = []
        for row in rows:
            vector_distance = float(row["vector_distance"])
            keyword_similarity = float(row["keyword_similarity"])
            
            if metric == DistanceMetric.COSINE:
                vector_score = 1 - vector_distance
            else:
                vector_score = 1 / (1 + vector_distance)
            
            keyword_score = keyword_similarity
            combined_score = vector_weight * vector_score + keyword_weight * keyword_score
            
            results.append(HybridSearchResult(
                id=str(row["id"]),
                vector_score=vector_score,
                keyword_score=keyword_score,
                combined_score=combined_score,
                content=row["content"],
                metadata=row["metadata"] or {},
            ))

        return sorted(results, key=lambda x: x.combined_score, reverse=True)

    async def search_by_metadata(
        self,
        collection: str,
        filter_metadata: Dict[str, Any],
        limit: int = 100,
        offset: int = 0,
    ) -> List[VectorDocument]:
        """Search vectors by metadata only."""
        if collection not in self._collections_cache:
            raise ValueError(f"Collection not found: {collection}")

        table_name = f"vectors_{collection.replace('-', '_')}"
        
        conditions = []
        params = []
        for i, (key, value) in enumerate(filter_metadata.items(), 1):
            conditions.append(f"metadata->>'{key}' = ${i}")
            params.append(str(value))
        
        where_clause = " WHERE " + " AND ".join(conditions) if conditions else ""
        
        query = f"""
            SELECT id, vector, content, metadata, created_at, updated_at
            FROM {table_name}
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${len(params) + 1} OFFSET ${len(params) + 2}
        """
        params.extend([limit, offset])

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(query, *params)

        return [
            VectorDocument(
                id=row["id"],
                collection=collection,
                vector=list(row["vector"]),
                content=row["content"],
                metadata=row["metadata"] or {},
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    # ==================== Stats & Management ====================

    async def get_collection_stats(self, collection: str) -> Dict[str, Any]:
        """Get collection statistics."""
        if collection not in self._collections_cache:
            raise ValueError(f"Collection not found: {collection}")

        table_name = f"vectors_{collection.replace('-', '_')}"
        
        async with self._pool.acquire() as conn:
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
            
            # Get index info
            index_info = await conn.fetch("""
                SELECT indexname, indexdef 
                FROM pg_indexes 
                WHERE tablename = $1 AND indexname LIKE 'idx_%_vector'
            """, table_name)

        coll = self._collections_cache[collection]
        return {
            "name": collection,
            "dimensions": coll.dimensions,
            "distance_metric": coll.distance_metric.value,
            "document_count": count,
            "indexes": [{"name": i["indexname"], "definition": i["indexdef"]} for i in index_info],
        }

    async def vacuum_analyze(self, collection: str):
        """Run VACUUM ANALYZE on collection table."""
        table_name = f"vectors_{collection.replace('-', '_')}"
        async with self._pool.acquire() as conn:
            await conn.execute(f"VACUUM ANALYZE {table_name}")


# Global vector database instance
_vector_db: Optional[VectorDatabase] = None


def get_vector_db() -> VectorDatabase:
    """Get or create vector database singleton."""
    global _vector_db
    if _vector_db is None:
        _vector_db = VectorDatabase(VectorConfig())
    return _vector_db


def init_vector_db(
    host: str = "localhost",
    port: int = 5432,
    database: str = "vcos",
    user: str = "postgres",
    password: str = "postgres",
    dimensions: int = 1536,
    distance_metric: DistanceMetric = DistanceMetric.COSINE,
    index_type: IndexType = IndexType.HNSW,
) -> VectorDatabase:
    """Initialize vector database."""
    global _vector_db
    config = VectorConfig(
        host=host,
        port=port,
        database=database,
        user=user,
        password=password,
        dimensions=dimensions,
        distance_metric=distance_metric,
        index_type=index_type,
    )
    _vector_db = VectorDatabase(config)
    return _vector_db