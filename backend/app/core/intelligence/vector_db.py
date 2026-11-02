from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any, List
import json
import hashlib
import uuid
import asyncio
from contextlib import asynccontextmanager

try:
    import asyncpg
    ASYNCPG_AVAILABLE = True
except ImportError:
    ASYNCPG_AVAILABLE = False

try:
    import pgvector
    PGVECTOR_AVAILABLE = True
except ImportError:
    PGVECTOR_AVAILABLE = False

# Import local vector store for SQLite development
from app.core.intelligence.local_vector_store import LocalVectorStore


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


class VectorIndexType(str, Enum):
    FLAT = "flat"
    IVF_FLAT = "ivf_flat"
    IVF_SQ8 = "ivf_sq8"
    HNSW = "hnsw"
    ANNOY = "annoy"


@dataclass
class IndexConfig:
    index_type: VectorIndexType = VectorIndexType.HNSW
    dimension: int = 1536
    distance_metric: VectorDistanceMetric = VectorDistanceMetric.COSINE
    m: int = 16
    ef_construction: int = 200
    ef_search: int = 100
    nlist: int = 100


class VectorStore:
    def __init__(self, connection_string: str, index_config: IndexConfig = None):
        self.connection_string = connection_string
        self.index_config = index_config or IndexConfig()
        self.pool: Optional[asyncpg.Pool] = None
        self._initialized = False

    async def initialize(self):
        if not ASYNCPG_AVAILABLE:
            raise RuntimeError("asyncpg not installed. Install with: pip install asyncpg pgvector")
        
        self.pool = await asyncpg.create_pool(self.connection_string, min_size=2, max_size=10)
        
        async with self.pool.acquire() as conn:
            await self._create_extension(conn)
            await self._create_tables(conn)
            await self._create_indexes(conn)
        
        self._initialized = True

    async def _create_extension(self, conn):
        await conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    async def _create_tables(self, conn):
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vector_documents (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                document_id TEXT NOT NULL,
                chunk_index INT NOT NULL DEFAULT 0,
                content TEXT NOT NULL,
                embedding vector(1536) NOT NULL,
                metadata JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW(),
                updated_at TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(document_id, chunk_index)
            );
        """)

        await conn.execute("""
            CREATE TABLE IF NOT EXISTS vector_indexes (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                name TEXT NOT NULL UNIQUE,
                table_name TEXT NOT NULL DEFAULT 'vector_documents',
                column_name TEXT NOT NULL DEFAULT 'embedding',
                index_type TEXT NOT NULL,
                dimension INT NOT NULL,
                distance_metric TEXT NOT NULL,
                config JSONB DEFAULT '{}',
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        """)

    async def _create_indexes(self, conn):
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vector_documents_document_id 
            ON vector_documents(document_id);
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vector_documents_metadata 
            ON vector_documents USING GIN (metadata);
        """)
        
        await conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_vector_documents_created_at 
            ON vector_documents(created_at DESC);
        """)

    async def create_hnsw_index(self, name: str = "vector_documents_embedding_idx") -> bool:
        if not self._initialized:
            await self.initialize()
        
        config = self.index_config
        async with self.pool.acquire() as conn:
            try:
                await conn.execute(f"""
                    CREATE INDEX IF NOT EXISTS {name} 
                    ON vector_documents USING hnsw (embedding vector_cosine_ops)
                    WITH (m = {config.m}, ef_construction = {config.ef_construction});
                """)
                return True
            except Exception as e:
                print(f"Failed to create HNSW index: {e}")
                return False

    async def upsert_documents(self, documents: List[VectorDocument]) -> int:
        if not self._initialized:
            await self.initialize()
        
        if not documents:
            return 0
        
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                count = 0
                for doc in documents:
                    await conn.execute("""
                        INSERT INTO vector_documents (id, document_id, chunk_index, content, embedding, metadata, created_at, updated_at)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                        ON CONFLICT (document_id, chunk_index) DO UPDATE SET
                            content = EXCLUDED.content,
                            embedding = EXCLUDED.embedding,
                            metadata = EXCLUDED.metadata,
                            updated_at = EXCLUDED.updated_at
                    """, 
                        doc.id, doc.document_id, doc.chunk_index, doc.content, 
                        doc.embedding, json.dumps(doc.metadata), 
                        doc.created_at, doc.updated_at
                    )
                    count += 1
                return count

    async def delete_documents(self, document_ids: List[str]) -> int:
        if not self._initialized:
            await self.initialize()
        
        if not document_ids:
            return 0
        
        async with self.pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM vector_documents WHERE document_id = ANY($1)",
                document_ids
            )
            return int(result.split()[-1])

    async def search(
        self,
        query_embedding: List[float],
        limit: int = 10,
        threshold: float = 0.0,
        filter_metadata: Dict[str, Any] = None,
        document_ids: List[str] = None
    ) -> List[SearchResult]:
        if not self._initialized:
            await self.initialize()
        
        query_vector = "[" + ",".join(map(str, query_embedding)) + "]"
        
        where_clauses = ["embedding <=> $1 < $2"]
        params = [f"[{','.join(map(str, query_embedding))}]", threshold]
        param_idx = 3
        
        if document_ids:
            where_clauses.append(f"document_id = ANY(${param_idx})")
            params.append(document_ids)
            param_idx += 1
        
        if filter_metadata:
            for key, value in filter_metadata.items():
                where_clauses.append(f"metadata->>'{key}' = ${param_idx}")
                params.append(str(value))
                param_idx += 1
        
        where_clause = " AND ".join(where_clauses)
        
        query = f"""
            SELECT id, document_id, chunk_index, content, embedding, metadata, created_at, updated_at,
                   (embedding <=> $1) as distance
            FROM vector_documents
            WHERE {where_clause}
            ORDER BY distance ASC
            LIMIT {limit}
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            
            results = []
            for row in rows:
                doc = VectorDocument(
                    id=str(row['id']),
                    document_id=row['document_id'],
                    chunk_index=row['chunk_index'],
                    content=row['content'],
                    embedding=list(row['embedding']),
                    metadata=row['metadata'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                distance = float(row['distance'])
                score = 1.0 - distance
                results.append(SearchResult(document=doc, score=score, distance=distance))
            
            return results

    async def hybrid_search(
        self,
        query_text: str,
        query_embedding: List[float],
        limit: int = 10,
        alpha: float = 0.5,
        filter_metadata: Dict[str, Any] = None
    ) -> List[SearchResult]:
        if not self._initialized:
            await self.initialize()
        
        text_query = """
            SELECT id, document_id, chunk_index, content, embedding, metadata, created_at, updated_at,
                   (embedding <=> $1) as vector_distance,
                   (tsvector(content) @@ plainto_tsquery($2)) as text_match,
                   ts_rank_cd(tsvector(content), plainto_tsquery($2)) as text_score
            FROM vector_documents
            WHERE tsvector(content) @@ plainto_tsquery($2)
            ORDER BY (vector_distance * $3 + (1 - ts_rank_cd(tsvector(content), plainto_tsquery($2))) * $4) ASC
            LIMIT $5
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                text_query,
                f"[{','.join(map(str, query_embedding))}]",
                query_text,
                alpha,
                1 - alpha,
                limit
            )
            
            results = []
            for row in rows:
                doc = VectorDocument(
                    id=str(row['id']),
                    document_id=row['document_id'],
                    chunk_index=row['chunk_index'],
                    content=row['content'],
                    embedding=list(row['embedding']),
                    metadata=row['metadata'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                distance = float(row['vector_distance'])
                score = 1.0 - distance
                results.append(SearchResult(document=doc, score=score, distance=distance))
            
            return results

    async def get_document_chunks(self, document_id: str) -> List[VectorDocument]:
        if not self._initialized:
            await self.initialize()
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, document_id, chunk_index, content, embedding, metadata, created_at, updated_at "
                "FROM vector_documents WHERE document_id = $1 ORDER BY chunk_index",
                document_id
            )
            
            return [
                VectorDocument(
                    id=str(row['id']),
                    document_id=row['document_id'],
                    chunk_index=row['chunk_index'],
                    content=row['content'],
                    embedding=list(row['embedding']),
                    metadata=row['metadata'],
                    created_at=row['created_at'],
                    updated_at=row['updated_at']
                )
                for row in rows
            ]

    async def close(self):
        if self.pool:
            await self.pool.close()


class EmbeddingProvider:
    def __init__(self, provider: str = "openai", api_key: str = None, model: str = "text-embedding-3-small"):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.dimension = 1536
    
    async def embed(self, texts: List[str]) -> List[List[float]]:
        if self.provider == "openai":
            return await self._embed_openai(texts)
        elif self.provider == "local":
            return await self._embed_local(texts)
        else:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    async def _embed_openai(self, texts: List[str]) -> List[List[float]]:
        import openai
        client = openai.AsyncOpenAI(api_key=self.api_key)
        
        response = await client.embeddings.create(
            model=self.model,
            input=texts
        )
        return [d.embedding for d in response.data]
    
    async def _embed_local(self, texts: List[str]) -> List[List[float]]:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer('all-MiniLM-L6-v2')
        embeddings = model.encode(texts)
        return [e.tolist() for e in embeddings]


class Chunker:
    def __init__(self, chunk_size: int = 500, chunk_overlap: int = 50):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def chunk_text(self, text: str, metadata: Dict = None) -> List[VectorDocument]:
        chunks = []
        words = text.split()
        
        for i in range(0, len(words), self.chunk_size - self.chunk_overlap):
            chunk_words = words[i:i + self.chunk_size]
            chunk_text = " ".join(chunk_words)
            
            doc = VectorDocument(
                id=str(uuid.uuid4()),
                content=chunk_text,
                embedding=[],
                metadata={
                    **(metadata or {}),
                    "chunk_start": i,
                    "chunk_end": min(i + self.chunk_size, len(words))
                },
                chunk_index=len(chunks)
            )
            chunks.append(doc)
        
        return chunks
    
    def chunk_markdown(self, text: str, metadata: Dict = None) -> List[VectorDocument]:
        import re
        sections = re.split(r'\n#{1,3}\s+', text)
        chunks = []
        
        for i, section in enumerate(sections):
            if not section.strip():
                continue
            chunks.extend(self.chunk_text(section.strip(), {
                **(metadata or {}),
                "section_index": i
            }))
        
        return chunks


class Retriever:
    def __init__(self, vector_store, embedder: EmbeddingProvider):
        self.vector_store = vector_store
        self.embedder = embedder
    
    async def retrieve(
        self,
        query: str,
        k: int = 10,
        threshold: float = 0.0,
        filter_metadata: Dict = None,
        hybrid: bool = False,
        alpha: float = 0.5
    ) -> List[SearchResult]:
        query_embedding = (await self.embedder.embed([query]))[0]
        
        if hybrid:
            return await self.vector_store.hybrid_search(
                query_text=query,
                query_embedding=query_embedding,
                limit=k,
                alpha=0.5,
                filter_metadata=filter_metadata
            )
        else:
            return await self.vector_store.search(
                query_embedding=query_embedding,
                limit=k,
                threshold=threshold,
                filter_metadata=filter_metadata
            )
    
    async def retrieve_with_rerank(
        self,
        query: str,
        k: int = 10,
        rerank_k: int = 50,
        reranker=None
    ) -> List[SearchResult]:
        initial_results = await self.retrieve(query, k=rerank_k)
        
        if reranker and len(initial_results) > 1:
            reranked = await reranker.rerank(query, initial_results)
            return reranked[:k]
        
        return initial_results[:k]


class Reranker:
    def __init__(self, provider: str = "cohere", api_key: str = None, model: str = "rerank-english-v3.0"):
        self.provider = provider
        self.api_key = api_key
        self.model = model
    
    async def rerank(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        if self.provider == "cohere":
            return await self._rerank_cohere(query, results)
        elif self.provider == "cross_encoder":
            return await self._rerank_cross_encoder(query, results)
        elif self.provider == "local":
            return await self._rerank_local(query, results)
        else:
            return results
    
    async def _rerank_cohere(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        import cohere
        client = cohere.AsyncClient(self.api_key)
        
        documents = [r.document.content for r in results]
        response = await client.rerank(
            model=self.model,
            query=query,
            documents=documents,
            top_n=len(results)
        )
        
        reranked = []
        for r in response.results:
            original = results[r.index]
            original.document.metadata["rerank_score"] = r.relevance_score
            reranked.append(original)
        
        return sorted(reranked, key=lambda x: x.document.metadata.get("rerank_score", 0), reverse=True)
    
    async def _rerank_cross_encoder(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        from sentence_transformers import CrossEncoder
        model = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
        
        pairs = [[query, r.document.content] for r in results]
        scores = model.predict(pairs)
        
        for i, r in enumerate(results):
            r.document.metadata["rerank_score"] = float(scores[i])
        
        return sorted(results, key=lambda x: x.document.metadata.get("rerank_score", 0), reverse=True)
    
    async def _rerank_local(self, query: str, results: List[SearchResult]) -> List[SearchResult]:
        """Local reranking using simple keyword overlap and vector similarity."""
        query_terms = set(query.lower().split())
        
        for r in results:
            content_terms = set(r.document.content.lower().split())
            overlap = len(query_terms & content_terms)
            total = len(query_terms | content_terms)
            jaccard = overlap / total if total > 0 else 0
            
            # Combine with existing vector score
            vector_score = r.score
            combined_score = 0.7 * vector_score + 0.3 * jaccard
            r.document.metadata["rerank_score"] = combined_score
        
        return sorted(results, key=lambda x: x.document.metadata.get("rerank_score", 0), reverse=True)


class RAGPipeline:
    def __init__(
        self,
        vector_store: VectorStore,
        embedder: EmbeddingProvider,
        chunker: Chunker = None,
        retriever: Retriever = None,
        reranker: Reranker = None,
        llm_client=None
    ):
        self.vector_store = vector_store
        self.embedder = embedder
        self.chunker = chunker or Chunker()
        self.retriever = retriever or Retriever(vector_store, embedder)
        self.reranker = reranker
        self.llm_client = llm_client
    
    async def ingest_document(
        self,
        document_id: str,
        content: str,
        metadata: Dict = None,
        chunk: bool = True
    ) -> List[VectorDocument]:
        if chunk:
            chunks = self.chunker.chunk_text(content, metadata)
            # Set document_id on all chunks
            for chunk in chunks:
                chunk.document_id = document_id
        else:
            chunks = [VectorDocument(
                id=str(uuid.uuid4()),
                document_id=document_id,
                content=content,
                embedding=[],
                metadata=metadata or {},
                chunk_index=0
            )]
        
        texts = [c.content for c in chunks]
        embeddings = await self.embedder.embed(texts)
        
        for chunk, embedding in zip(chunks, embeddings):
            chunk.embedding = embedding
        
        await self.vector_store.upsert_documents(chunks)
        return chunks
    
    async def query(
        self,
        query: str,
        k: int = 5,
        hybrid: bool = False,
        rerank: bool = False,
        filter_metadata: Dict = None
    ) -> Dict:
        results = await self.retriever.retrieve(query, k=k * 2 if rerank else k, hybrid=hybrid)
        
        if rerank and self.reranker:
            results = await self.reranker.rerank(query, results)
        
        results = results[:k]
        
        context = "\n\n".join([r.document.content for r in results])
        
        return {
            "query": query,
            "results": results,
            "context": context,
            "answer": await self._generate_answer(query, context) if self.llm_client else None
        }
    
    async def _generate_answer(self, query: str, context: str) -> str:
        if not self.llm_client:
            return "No LLM client configured"
        
        prompt = f"""Answer the question based on the provided context.

Context:
{context}

Question: {query}

Answer:"""
        
        return await self.llm_client.generate(prompt)


def create_vector_store(connection_string: str, index_config: IndexConfig = None):
    """Factory function to create appropriate vector store based on connection string."""
    if connection_string.startswith("postgresql"):
        if not ASYNCPG_AVAILABLE:
            raise RuntimeError("asyncpg not installed. Install with: pip install asyncpg pgvector")
        return VectorStore(connection_string, index_config)
    else:
        # Use local SQLite-based vector store for development
        from app.core.intelligence.local_vector_store import LocalVectorStore
        db_path = connection_string.replace("sqlite+aiosqlite:///", "").replace("sqlite:///", "")
        if db_path.startswith("./"):
            db_path = db_path[2:]
        return LocalVectorStore(db_path=db_path, dimension=index_config.dimension if index_config else 1536)


__all__ = [
    "VectorDistanceMetric",
    "VectorDocument",
    "SearchResult",
    "VectorIndexType",
    "IndexConfig",
    "VectorStore",
    "LocalVectorStore",
    "EmbeddingProvider",
    "Chunker",
    "Retriever",
    "Reranker",
    "RAGPipeline",
    "create_vector_store",
]