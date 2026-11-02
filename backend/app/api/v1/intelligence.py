"""
Intelligence Layer API Routes.

Provides endpoints for:
- Document ingestion
- Vector search
- RAG query
- Collection management
- Embedding generation
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.core.vector_db import (
    VectorDatabase,
    DistanceMetric,
    IndexType,
    get_vector_db,
)
from app.core.embeddings import (
    EmbeddingPipeline,
    EmbeddingProvider,
    EmbeddingConfig,
    get_embedding_pipeline,
)
from app.core.rag import (
    RAGPipeline,
    IngestionConfig,
    RetrievalConfig,
    GenerationConfig,
    RetrievalStrategy,
    GenerationModel,
    Document,
    get_rag_pipeline,
)
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["Intelligence Layer"])

logger = logging.getLogger(__name__)


# ==================== Models ====================

class CollectionCreate(BaseModel):
    name: str
    dimensions: Optional[int] = None
    distance_metric: str = "cosine"
    description: str = ""
    metadata: Dict[str, Any] = {}


class CollectionResponse(BaseModel):
    name: str
    dimensions: int
    distance_metric: str
    description: str
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str
    document_count: int = 0


class EmbeddingRequest(BaseModel):
    texts: List[str]
    model: Optional[str] = None
    use_cache: bool = True


class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]
    model: str
    dimensions: int
    usage: Dict[str, int]
    cached: bool
    latency_ms: int


class DocumentIngest(BaseModel):
    content: str
    metadata: Dict[str, Any] = {}
    source: str = "api"


class DocumentIngestResponse(BaseModel):
    document_id: str
    chunks_created: int
    chunk_ids: List[str]


class SearchRequest(BaseModel):
    query: str
    collection: Optional[str] = None
    limit: int = 10
    strategy: str = "hybrid"
    vector_weight: float = 0.7
    keyword_weight: float = 0.3
    similarity_threshold: float = 0.5
    metadata_filters: Dict[str, Any] = {}


class SearchResultResponse(BaseModel):
    id: str
    score: float
    content: str
    metadata: Dict[str, Any]
    distance: float


class SearchResponse(BaseModel):
    results: List[SearchResultResponse]
    query: str
    strategy: str
    total_results: int


class RAGQueryRequest(BaseModel):
    question: str
    collection: Optional[str] = None
    retrieval_config: Optional[Dict[str, Any]] = None
    generation_config: Optional[Dict[str, Any]] = None


class RAGQueryResponse(BaseModel):
    answer: str
    citations: List[Dict[str, Any]]
    contexts: List[SearchResultResponse]
    confidence: float
    tokens_used: int
    latency_ms: int
    metadata: Dict[str, Any]


class RAGStreamRequest(BaseModel):
    question: str
    collection: Optional[str] = None


# ==================== Collection Management ====================

@router.post("/intelligence/collections", response_model=CollectionResponse)
async def create_collection(
    request: CollectionCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new vector collection."""
    vector_db = get_vector_db()
    
    try:
        metric = DistanceMetric(request.distance_metric)
    except ValueError:
        raise HTTPException(400, f"Invalid distance metric: {request.distance_metric}")
    
    collection = await vector_db.create_collection(
        name=request.name,
        dimensions=request.dimensions,
        distance_metric=metric,
        description=request.description,
        metadata=request.metadata,
    )
    
    stats = await vector_db.get_collection_stats(collection.name)
    
    return CollectionResponse(
        name=collection.name,
        dimensions=collection.dimensions,
        distance_metric=collection.distance_metric.value,
        description=collection.description,
        metadata=collection.metadata,
        created_at=collection.created_at.isoformat(),
        updated_at=collection.updated_at.isoformat(),
        document_count=stats.get("document_count", 0),
    )


@router.get("/intelligence/collections", response_model=List[CollectionResponse])
async def list_collections(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all vector collections."""
    vector_db = get_vector_db()
    collections = await vector_db.list_collections()
    
    response = []
    for collection in collections:
        stats = await vector_db.get_collection_stats(collection.name)
        response.append(CollectionResponse(
            name=collection.name,
            dimensions=collection.dimensions,
            distance_metric=collection.distance_metric.value,
            description=collection.description,
            metadata=collection.metadata,
            created_at=collection.created_at.isoformat(),
            updated_at=collection.updated_at.isoformat(),
            document_count=stats.get("document_count", 0),
        ))
    
    return response


@router.get("/intelligence/collections/{name}", response_model=CollectionResponse)
async def get_collection(
    name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get collection details."""
    vector_db = get_vector_db()
    collection = await vector_db.get_collection(name)
    
    if not collection:
        raise HTTPException(404, "Collection not found")
    
    stats = await vector_db.get_collection_stats(name)
    
    return CollectionResponse(
        name=collection.name,
        dimensions=collection.dimensions,
        distance_metric=collection.distance_metric.value,
        description=collection.description,
        metadata=collection.metadata,
        created_at=collection.created_at.isoformat(),
        updated_at=collection.updated_at.isoformat(),
        document_count=stats.get("document_count", 0),
    )


@router.delete("/intelligence/collections/{name}")
async def delete_collection(
    name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a collection."""
    vector_db = get_vector_db()
    success = await vector_db.delete_collection(name)
    
    if not success:
        raise HTTPException(404, "Collection not found")
    
    return {"success": True}


@router.get("/intelligence/collections/{name}/stats")
async def get_collection_stats(
    name: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get collection statistics."""
    vector_db = get_vector_db()
    return await vector_db.get_collection_stats(name)


# ==================== Embedding Generation ====================

@router.post("/intelligence/embeddings", response_model=EmbeddingResponse)
async def generate_embeddings(
    request: EmbeddingRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Generate embeddings for texts."""
    pipeline = get_embedding_pipeline()
    await pipeline.initialize()
    
    response = await pipeline.embed_texts(
        texts=request.texts,
        model=request.model,
        use_cache=request.use_cache,
    )
    
    return EmbeddingResponse(
        embeddings=response.embeddings,
        model=response.model,
        dimensions=response.dimensions,
        usage=response.usage,
        cached=response.cached,
        latency_ms=response.latency_ms,
    )


@router.get("/intelligence/embeddings/estimate-cost")
async def estimate_embedding_cost(
    token_count: int = Query(..., ge=1),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Estimate embedding cost."""
    pipeline = get_embedding_pipeline()
    await pipeline.initialize()
    
    cost = pipeline.estimate_cost(token_count)
    
    return {
        "token_count": token_count,
        "estimated_cost_usd": cost,
        "model": pipeline.config.model,
        "provider": pipeline.config.provider.value,
    }


# ==================== Document Ingestion ====================

@router.post("/intelligence/documents", response_model=DocumentIngestResponse)
async def ingest_document(
    request: DocumentIngest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest a document into the knowledge base."""
    pipeline = get_rag_pipeline()
    await pipeline.initialize()
    
    document = Document(
        id=str(uuid.uuid4()),
        content=request.content,
        metadata={**request.metadata, "user_id": user.id, "org_id": user.organization_id},
        source=request.source,
    )
    
    ids = await pipeline.ingest_document(document)
    
    return DocumentIngestResponse(
        document_id=document.id,
        chunks_created=len(ids),
        chunk_ids=ids,
    )


@router.post("/intelligence/documents/batch", response_model=DocumentIngestResponse)
async def ingest_documents_batch(
    documents: List[DocumentIngest],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Ingest multiple documents."""
    pipeline = get_rag_pipeline()
    await pipeline.initialize()
    
    docs = [
        Document(
            id=str(uuid.uuid4()),
            content=doc.content,
            metadata={**doc.metadata, "user_id": user.id, "org_id": user.organization_id},
            source=doc.source,
        )
        for doc in documents
    ]
    
    all_ids = []
    for doc in docs:
        ids = await pipeline.ingest_document(doc)
        all_ids.extend(ids)
    
    return DocumentIngestResponse(
        document_id="batch",
        chunks_created=len(all_ids),
        chunk_ids=all_ids,
    )


@router.post("/intelligence/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    collection: Optional[str] = Form(None),
    metadata: str = Form("{}"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload and ingest a document file."""
    import json
    import uuid
    
    content = await file.read()
    
    # Try to decode as text
    try:
        text_content = content.decode("utf-8")
    except UnicodeDecodeError:
        # Try other encodings or use OCR for PDFs
        text_content = content.decode("latin-1")
    
    meta = json.loads(metadata)
    meta["filename"] = file.filename
    meta["content_type"] = file.content_type
    
    pipeline = get_rag_pipeline()
    await pipeline.initialize()
    
    document = Document(
        id=str(uuid.uuid4()),
        content=text_content,
        metadata={**meta, "user_id": user.id, "org_id": user.organization_id},
        source=f"upload:{file.filename}",
    )
    
    ids = await pipeline.ingest_document(document)
    
    return DocumentIngestResponse(
        document_id=document.id,
        chunks_created=len(ids),
        chunk_ids=ids,
    )


@router.delete("/intelligence/documents/{document_id}")
async def delete_document(
    document_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a document by ID."""
    pipeline = get_rag_pipeline()
    await pipeline.initialize()
    
    count = await pipeline.delete_document(document_id)
    
    return {"success": True, "chunks_deleted": count}


# ==================== Vector Search ====================

@router.post("/intelligence/search", response_model=SearchResponse)
async def vector_search(
    request: SearchRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Vector similarity search."""
    vector_db = get_vector_db()
    pipeline = get_embedding_pipeline()
    await pipeline.initialize()
    
    # Generate query embedding
    response = await pipeline.embed_texts([request.query])
    query_vector = response.embeddings[0]
    
    collection = request.collection or "documents"
    
    try:
        strategy = RetrievalStrategy(request.strategy)
    except ValueError:
        raise HTTPException(400, f"Invalid search strategy: {request.strategy}")
    
    if strategy == RetrievalStrategy.VECTOR:
        results = await vector_db.search(
            collection=collection,
            query_vector=query_vector,
            limit=request.limit,
            filter_metadata=request.metadata_filters,
        )
    elif strategy == RetrievalStrategy.HYBRID:
        results = await vector_db.search_hybrid(
            collection=collection,
            query_vector=query_vector,
            query_text=request.query,
            limit=request.limit,
            vector_weight=request.vector_weight,
            keyword_weight=request.keyword_weight,
            filter_metadata=request.metadata_filters,
        )
    else:
        raise HTTPException(400, f"Strategy {strategy.value} not implemented via direct API")
    
    search_results = [
        SearchResultResponse(
            id=r.id,
            score=r.score,
            content=r.content,
            metadata=r.metadata,
            distance=r.distance,
        )
        for r in results
    ]
    
    return SearchResponse(
        results=search_results,
        query=request.query,
        strategy=request.strategy,
        total_results=len(search_results),
    )


@router.post("/intelligence/search/metadata")
async def search_by_metadata(
    collection: str = Query(...),
    filters: str = Query(..., description="JSON encoded filters"),
    limit: int = Query(100, le=1000),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Search vectors by metadata only."""
    import json
    filter_dict = json.loads(filters)
    vector_db = get_vector_db()
    
    results = await vector_db.search_by_metadata(
        collection=collection,
        filter_metadata=filter_dict,
        limit=limit,
        offset=offset,
    )
    
    return {
        "results": [
            SearchResultResponse(
                id=r.id,
                score=1.0,
                content=r.content,
                metadata=r.metadata,
                distance=0.0,
            )
            for r in results
        ],
        "total": len(results),
    }


# ==================== RAG Query ====================

@router.post("/intelligence/rag/query", response_model=RAGQueryResponse)
async def rag_query(
    request: RAGQueryRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Full RAG query pipeline."""
    pipeline = get_rag_pipeline()
    await pipeline.initialize()
    
    # Build configs from request
    retrieval_config = None
    if request.retrieval_config:
        retrieval_config = RetrievalConfig(**request.retrieval_config)
    
    generation_config = None
    if request.generation_config:
        generation_config = GenerationConfig(**request.generation_config)
    
    response = await pipeline.query(
        question=request.question,
        collection=request.collection,
        retrieval_config=retrieval_config,
        generation_config=generation_config,
    )
    
    return RAGQueryResponse(
        answer=response.answer,
        citations=response.citations,
        contexts=[
            SearchResultResponse(
                id=c.id,
                score=c.score,
                content=c.content,
                metadata=c.metadata,
                distance=c.distance,
            )
            for c in response.contexts
        ],
        confidence=response.confidence,
        tokens_used=response.tokens_used,
        latency_ms=response.latency_ms,
        metadata=response.metadata,
    )


@router.post("/intelligence/rag/stream")
async def rag_stream_query(
    request: RAGStreamRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stream RAG query response."""
    from fastapi.responses import StreamingResponse
    
    pipeline = get_rag_pipeline()
    await pipeline.initialize()
    
    async def generate():
        async for chunk in pipeline.stream_query(request.question, request.collection):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
        yield "data: [DONE]\n\n"
    
    import json
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


# ==================== Evaluation ====================

@router.post("/intelligence/rag/evaluate")
async def evaluate_rag(
    test_questions: List[Dict[str, Any]],
    collection: Optional[str] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate RAG pipeline on test questions."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    pipeline = get_rag_pipeline()
    await pipeline.initialize()
    
    results = await pipeline.evaluate(test_questions, collection)
    return results


# ==================== System ====================

@router.get("/intelligence/stats")
async def get_intelligence_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get intelligence layer statistics."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")
    
    vector_db = get_vector_db()
    collections = await vector_db.list_collections()
    
    total_docs = 0
    for coll in collections:
        stats = await vector_db.get_collection_stats(coll.name)
        total_docs += stats.get("document_count", 0)
    
    embedding_pipeline = get_embedding_pipeline()
    await embedding_pipeline.initialize()
    
    return {
        "collections": len(collections),
        "total_documents": total_docs,
        "embedding_model": embedding_pipeline.config.model,
        "embedding_provider": embedding_pipeline.config.provider.value,
        "embedding_dimensions": embedding_pipeline.config.dimensions,
    }


import uuid