"""RAG and Semantic Search API endpoints."""

import json
import time
from typing import Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel


class KnowledgeSearchResult(BaseModel):
    id: str
    kind: str
    title: str
    url: str
    subtitle: str
    score: float


class KnowledgeSearchResponse(BaseModel):
    query: str
    results: List[KnowledgeSearchResult]
    total: int
    limit: int
    provider: str
    took_ms: float


from app.api.deps import get_current_user, get_db
from app.knowledge.rag_pipeline import rag_pipeline
from app.knowledge.vector_db import vector_db_service
from app.knowledge.embeddings import get_embedding_provider
from app.models.organization import Organization
from app.models.user import User
from app.models.intelligence import KnowledgeVector, KnowledgeSource, KnowledgeClaim, KnowledgeTopic
from app.services.permission_service import permission_service

router = APIRouter(prefix="/knowledge", tags=["Knowledge RAG"])


async def get_current_organization(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get current organization from user."""
    org = await db.get(Organization, user.organization_id)
    if org is None or org.status != "active":
        raise HTTPException(status_code=403, detail="Organization is not active")
    return org


class RequirePermission:
    """Dependency to require a specific permission."""
    
    def __init__(self, permission: str):
        self.permission = permission
    
    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        codes = await permission_service.user_permission_codes(db, user.id, user.organization_id)
        if self.permission not in codes:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {self.permission}",
            )
        return user


def require_permission(permission: str) -> RequirePermission:
    return RequirePermission(permission)


@router.get("/search/semantic", response_model=KnowledgeSearchResponse)
async def semantic_search_pgvector(
    q: str = Query(..., min_length=1, max_length=500, description="Search query"),
    kind: Optional[str] = Query(None, description="Knowledge kind filter"),
    source_types: Optional[str] = Query(None, description="Comma-separated source types"),
    limit: int = Query(10, ge=1, le=50),
    threshold: float = Query(0.7, ge=0.0, le=1.0),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    """Semantic vector search using pgvector (bypasses governance for internal use)."""
    started = time.monotonic()
    
    provider = get_embedding_provider()
    query_vector = (await provider.embed_many([q]))[0]
    
    source_type_list = source_types.split(",") if source_types else None
    
    results = await vector_db_service.search_vectors(
        db=db,
        organization_id=org.id,
        query_vector=query_vector,
        source_types=source_type_list,
        limit=limit,
        threshold=threshold,
    )
    
    search_results = [
        KnowledgeSearchResult(
            id=f"{r['source_type']}:{r['source_id']}:{r['chunk_index']}",
            kind=r["source_type"],
            title=r["metadata"].get("title", r["source_id"]),
            url=r["metadata"].get("url", f"/knowledge/{r['source_type']}/{r['source_id']}"),
            subtitle=r["chunk_text"][:200],
            score=r["similarity"],
        )
        for r in results
    ]
    
    return KnowledgeSearchResponse(
        query=q,
        results=search_results,
        total=len(search_results),
        limit=limit,
        provider=provider.name,
        took_ms=round((time.monotonic() - started) * 1000, 2),
    )


@router.get("/search/hybrid", response_model=KnowledgeSearchResponse)
async def hybrid_search(
    q: str = Query(..., min_length=1, max_length=500),
    kind: Optional[str] = Query(None),
    source_types: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=50),
    semantic_weight: float = Query(0.7, ge=0.0, le=1.0),
    lexical_weight: float = Query(0.3, ge=0.0, le=1.0),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    """Hybrid search combining semantic vector + lexical BM25."""
    started = time.monotonic()
    
    provider = get_embedding_provider()
    query_vector = (await provider.embed_many([q]))[0]
    
    source_type_list = source_types.split(",") if source_types else None
    
    results = await vector_db_service.hybrid_search(
        db=db,
        organization_id=org.id,
        query=q,
        query_vector=query_vector,
        source_types=source_type_list,
        limit=limit,
        semantic_weight=semantic_weight,
        lexical_weight=lexical_weight,
    )
    
    search_results = [
        KnowledgeSearchResult(
            id=f"{r['source_type']}:{r['source_id']}:{r['chunk_index']}",
            kind=r["source_type"],
            title=r["metadata"].get("title", r["source_id"]),
            url=r["metadata"].get("url", f"/knowledge/{r['source_type']}/{r['source_id']}"),
            subtitle=r["chunk_text"][:200],
            score=r["combined_score"],
        )
        for r in results
    ]
    
    return KnowledgeSearchResponse(
        query=q,
        results=search_results,
        total=len(search_results),
        limit=limit,
        provider=provider.name,
        took_ms=round((time.monotonic() - started) * 1000, 2),
    )


@router.post("/rag/query")
async def rag_query(
    query: str,
    kinds: Optional[str] = None,
    limit: int = 10,
    stream: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:read")),
    db: AsyncSession = Depends(get_db),
):
    """RAG query with citations."""
    kind_list = kinds.split(",") if kinds else None
    
    if stream:
        async def event_generator():
            async for chunk in await rag_pipeline.query(
                db=db,
                organization_id=org.id,
                user=user,
                query=query,
                kinds=kind_list,
                limit=limit,
                stream=True,
            ):
                yield f"data: {json.dumps({'content': chunk})}\n\n"
            yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
        )
    else:
        result = await rag_pipeline.query(
            db=db,
            organization_id=org.id,
            user=user,
            query=query,
            kinds=kind_list,
            limit=limit,
            stream=False,
        )
        return result


@router.post("/rag/index")
async def index_document(
    source_type: str,
    source_id: str,
    text: str,
    metadata: Optional[dict] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:write")),
    db: AsyncSession = Depends(get_db),
):
    """Index a document into the vector database."""
    chunks = vector_db_service.chunk_text(text)
    
    if not chunks:
        raise HTTPException(400, "No content to index")
    
    count = await vector_db_service.upsert_vectors(
        db=db,
        organization_id=org.id,
        source_type=source_type,
        source_id=source_id,
        chunks=chunks,
        metadata=metadata,
    )
    
    return {"indexed_chunks": count, "source_type": source_type, "source_id": source_id}


@router.delete("/rag/index")
async def delete_index(
    source_type: str,
    source_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("knowledge:write")),
    db: AsyncSession = Depends(get_db),
):
    """Delete all vectors for a document."""
    count = await vector_db_service.delete_vectors(
        db=db,
        organization_id=org.id,
        source_type=source_type,
        source_id=source_id,
    )
    
    return {"deleted_chunks": count, "source_type": source_type, "source_id": source_id}


@router.post("/rag/index/create")
async def create_vector_index(
    index_type: str = "hnsw",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:system")),
    db: AsyncSession = Depends(get_db),
):
    """Create HNSW or IVFFlat index on vector column."""
    success = await vector_db_service.ensure_index(db, index_type=index_type)
    return {"success": success, "index_type": index_type}