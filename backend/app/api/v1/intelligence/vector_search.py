from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, UploadFile, File
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime
from typing import Optional
import uuid

from app.core.intelligence.vector_db import (
    VectorStore, EmbeddingProvider, Chunker, Retriever, Reranker, VectorDocument,
    SearchResult, VectorIndexType, VectorDistanceMetric, IndexConfig,
    create_vector_store, LocalVectorStore
)
from app.core.intelligence.rag_pipeline import (
    RAGPipeline, ConversationManager, CitationExtractor, QueryExpander,
    FactChecker, AnswerSynthesizer
)
from app.core.intelligence.semantic_search import (
    SemanticSearchEngine, SemanticCache, SemanticRouter
)
from app.core.intelligence.rag_pipeline import RAGPipeline
from app.api.deps import get_current_user
from app.models.organization import Organization
from app.models.user import User


router = APIRouter(prefix="/intelligence", tags=["intelligence"])


class VectorStoreConfig(BaseModel):
    connection_string: str
    index_config: Optional[Dict] = None


class EmbeddingConfig(BaseModel):
    provider: str = "openai"
    api_key: str = None
    model: str = "text-embedding-3-small"


class DocumentIngestRequest(BaseModel):
    document_id: str
    content: str
    metadata: Dict = {}
    chunk: bool = True
    chunk_size: int = 500
    chunk_overlap: int = 50


class DocumentSearchRequest(BaseModel):
    query: str
    k: int = 10
    threshold: float = 0.0
    filter_metadata: Dict = {}
    document_ids: List[str] = []
    hybrid: bool = False


class HybridSearchRequest(BaseModel):
    query_text: str
    query_embedding: List[float]
    limit: int = 10
    alpha: float = 0.5


class RAGQueryRequest(BaseModel):
    query: str
    k: int = 5
    hybrid: bool = False
    rerank: bool = False
    filter_metadata: Dict = {}
    conversation_id: Optional[str] = None


class SemanticSearchRequest(BaseModel):
    query: str
    k: int = 10
    filters: Dict = {}
    hybrid: bool = True
    rerank: bool = True


class RerankRequest(BaseModel):
    query: str
    results: List[Dict]
    top_n: Optional[int] = None


class ExpandQueryRequest(BaseModel):
    query: str
    num_expansions: int = 3


class FactCheckRequest(BaseModel):
    claim: str
    context: str
    sources: List[str] = []


class SynthesizeRequest(BaseModel):
    query: str
    sources: List[str]
    context: str = ""
    style: str = "comprehensive"
    citations: bool = True


class SemanticSearchRequest(BaseModel):
    query: str
    k: int = 10
    filters: Dict = {}
    hybrid: bool = True
    rerank: bool = True


class SemanticCacheGetRequest(BaseModel):
    query: str


class SemanticCacheSetRequest(BaseModel):
    query: str
    value: Any


class SemanticRouterRequest(BaseModel):
    query: str
    threshold: float = 0.7


vector_store: VectorStore = None
embedding_provider = None
chunker = None
retriever = None
reranker = None
rag_pipeline = None
conversation_manager = ConversationManager()
citation_extractor = CitationExtractor()
query_expander = None
fact_checker = None
answer_synthesizer = None
semantic_search_engine = None
semantic_cache = None
semantic_router = None


@router.on_event("startup")
async def startup():
    global vector_store, embedding_provider, chunker, retriever, reranker, rag_pipeline
    global query_expander, fact_checker, answer_synthesizer
    global semantic_search_engine, semantic_cache, semantic_router
    
    # Use local embedding provider for development (no API key required)
    import os
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key and openai_key != "test-key":
        embedding_provider = EmbeddingProvider(provider="openai", api_key=openai_key, model="text-embedding-3-small")
    else:
        embedding_provider = EmbeddingProvider(provider="local")
    
    chunker = Chunker(chunk_size=500, chunk_overlap=50)
    
    from app.core.config import get_settings
    settings = get_settings()
    db_url = settings.DATABASE_URL
    
    # Initialize vector store using factory (works with both PostgreSQL and SQLite)
    vector_store = create_vector_store(
        connection_string=db_url,
        index_config=IndexConfig(
            dimension=1536,
            distance_metric=VectorDistanceMetric.COSINE
        )
    )
    await vector_store.initialize()
    
    retriever = Retriever(vector_store, embedding_provider)
    
    # Use local reranker to avoid API dependency
    reranker = Reranker(provider="local")
    
    rag_pipeline = RAGPipeline(
        vector_store=vector_store,
        embedder=embedding_provider,
        chunker=chunker,
        retriever=retriever,
        reranker=reranker
    )

    query_expander = QueryExpander(llm_client=None)
    fact_checker = FactChecker(llm_client=None)
    answer_synthesizer = AnswerSynthesizer(llm_client=None)

    semantic_search_engine = SemanticSearchEngine(
        vector_store=vector_store,
        embedder=embedding_provider
    )

    semantic_cache = SemanticCache(vector_store, embedding_provider)

    semantic_router = SemanticRouter(
        vector_store=vector_store,
        embedder=embedding_provider,
        routes={
            "search": "search for information",
            "question": "answer a question",
            "summarize": "summarize content",
            "analyze": "analyze data"
        }
    )
    # Initialize semantic router with error handling
    try:
        await semantic_router.initialize()
    except Exception as e:
        print(f"Warning: Semantic router initialization failed: {e}")
        # Continue without semantic router


@router.on_event("shutdown")
async def shutdown():
    global vector_store
    if vector_store:
        await vector_store.close()


@router.post("/vector-store/initialize", status_code=status.HTTP_201_CREATED)
async def initialize_vector_store(
    config: VectorStoreConfig,
    current_user: User = Depends(get_current_user),
):
    global vector_store
    vector_store = VectorStore(
        connection_string=config.connection_string,
        index_config=IndexConfig(**config.index_config) if config.index_config else IndexConfig()
    )
    await vector_store.initialize()
    await vector_store.create_hnsw_index()
    return {"success": True, "message": "Vector store initialized"}


@router.post("/documents/ingest", status_code=status.HTTP_201_CREATED)
async def ingest_document(
    request: DocumentIngestRequest,
    current_user: User = Depends(get_current_user),
):
    chunks = await rag_pipeline.ingest_document(
        document_id=request.document_id,
        content=request.content,
        metadata={**request.metadata, "ingested_by": current_user.id, "ingested_at": datetime.utcnow().isoformat()},
        chunk=request.chunk
    )
    return {"success": True, "chunks_ingested": len(chunks), "document_id": request.document_id}


@router.post("/documents/search")
async def search_documents(
    request: DocumentSearchRequest,
    current_user: User = Depends(get_current_user),
):
    if request.hybrid:
        query_embedding = (await embedding_provider.embed([request.query]))[0]
        results = await vector_store.hybrid_search(
            query_text=request.query,
            query_embedding=query_embedding,
            limit=request.k,
            alpha=0.5
        )
    else:
        query_embedding = (await embedding_provider.embed([request.query]))[0]
        results = await vector_store.search(
            query_embedding=query_embedding,
            limit=request.k,
            threshold=request.threshold,
            filter_metadata=request.filter_metadata,
            document_ids=request.document_ids
        )
    
    return {
        "query": request.query,
        "results": [
            {
                "document": {
                    "id": r.document.id,
                    "document_id": r.document.document_id,
                    "chunk_index": r.document.chunk_index,
                    "content": r.document.content,
                    "metadata": r.document.metadata,
                    "created_at": r.document.created_at,
                    "updated_at": r.document.updated_at
                },
                "score": r.score,
                "distance": r.distance
            }
            for r in results
        ]
    }


@router.post("/documents/hybrid-search")
async def hybrid_search(
    request: HybridSearchRequest,
    current_user: User = Depends(get_current_user),
):
    results = await vector_store.hybrid_search(
        query_text=request.query_text,
        query_embedding=request.query_embedding,
        limit=request.limit,
        alpha=request.alpha
    )
    
    return {
        "query_text": request.query_text,
        "results": [
            {
                "document": {
                    "id": r.document.id,
                    "document_id": r.document.document_id,
                    "chunk_index": r.document.chunk_index,
                    "content": r.document.content,
                    "metadata": r.document.metadata,
                    "created_at": r.document.created_at,
                    "updated_at": r.document.updated_at
                },
                "score": r.score,
                "distance": r.distance
            }
            for r in results
        ]
    }


@router.delete("/documents/{document_id}")
async def delete_document(
    document_id: str,
    current_user: User = Depends(get_current_user),
):
    count = await vector_store.delete_documents([document_id])
    return {"success": True, "chunks_deleted": count}


@router.post("/rag/query")
async def rag_query(
    request: RAGQueryRequest,
    current_user: User = Depends(get_current_user),
):
    result = await rag_pipeline.query(
        query=request.query,
        k=request.k,
        hybrid=request.hybrid,
        rerank=request.rerank,
        filter_metadata=request.filter_metadata
    )
    
    if request.conversation_id:
        conversation_manager.add_message(request.conversation_id, LLMMessage(role="user", content=request.query))
        if result.get("answer"):
            conversation_manager.add_message(request.conversation_id, LLMMessage(role="assistant", content=result["answer"]))
    
    return result


@router.post("/rag/conversation")
async def manage_conversation(
    conversation_id: str,
    action: str = Body(...),
    message: str = Body(None),
    current_user: User = Depends(get_current_user),
):
    if action == "get":
        messages = conversation_manager.get_conversation(conversation_id)
        return {"conversation_id": conversation_id, "messages": [m.__dict__ for m in conversation_manager.get_conversation(conversation_id)]}
    elif action == "clear":
        conversation_manager.clear_conversation(conversation_id)
        return {"success": True}
    elif action == "add" and message:
        conversation_manager.add_message(conversation_id, LLMMessage(role="user", content=message))
        return {"success": True}
    raise HTTPException(status_code=400, detail="Invalid action")


@router.post("/semantic/search")
async def semantic_search(
    request: SemanticSearchRequest,
    current_user: User = Depends(get_current_user),
):
    results = await semantic_search_engine.search(
        query=request.query,
        k=request.k,
        filters=request.filters,
        hybrid=request.hybrid,
        rerank=request.rerank
    )
    
    return {
        "query": request.query,
        "results": [
            {
                "document": {
                    "id": r.document.id,
                    "document_id": r.document.document_id,
                    "chunk_index": r.document.chunk_index,
                    "content": r.document.content,
                    "metadata": r.document.metadata,
                    "created_at": r.document.created_at,
                    "updated_at": r.document.updated_at
                },
                "score": r.score,
                "distance": r.distance
            }
            for r in results
        ]
    }


@router.post("/semantic/multi-query")
async def multi_query_search(
    queries: List[str] = Body(...),
    k: int = Body(10),
    deduplicate: bool = Body(True),
    current_user: User = Depends(get_current_user),
):
    results = await semantic_search_engine.multi_query_search(queries, k, deduplicate)
    return {
        "queries": queries,
        "results": [
            {
                "document": {
                    "id": r.document.id,
                    "document_id": r.document.document_id,
                    "chunk_index": r.document.chunk_index,
                    "content": r.document.content,
                    "metadata": r.document.metadata,
                    "created_at": r.document.created_at,
                    "updated_at": r.document.updated_at
                },
                "score": r.score,
                "distance": r.distance
            }
            for r in results
        ]
    }


@router.post("/rerank")
async def rerank_results(
    request: RerankRequest,
    current_user: User = Depends(get_current_user),
):
    results = [
        SearchResult(
            document=VectorDocument(**r["document"]),
            score=r["score"],
            distance=r["distance"]
        )
        for r in request.results
    ]
    
    reranked = await reranker.rerank(request.query, results)
    
    if request.top_n:
        reranked = reranked[:request.top_n]
    
    return {
        "query": request.query,
        "results": [
            {
                "document": {
                    "id": r.document.id,
                    "document_id": r.document.document_id,
                    "chunk_index": r.document.chunk_index,
                    "content": r.document.content,
                    "metadata": r.document.metadata,
                    "created_at": r.document.created_at,
                    "updated_at": r.document.updated_at
                },
                "score": r.score,
                "distance": r.distance
            }
            for r in reranked
        ]
    }


@router.post("/query/expand")
async def expand_query(
    request: ExpandQueryRequest,
    current_user: User = Depends(get_current_user),
):
    global query_expander
    if not query_expander:
        raise HTTPException(status_code=503, detail="Query expander not initialized")
    
    expansions = await query_expander.expand(request.query, request.num_expansions)
    return {"original_query": request.query, "expansions": expansions}


@router.post("/fact-check")
async def fact_check(
    request: FactCheckRequest,
    current_user: User = Depends(get_current_user),
):
    global fact_checker
    if not fact_checker:
        raise HTTPException(status_code=503, detail="Fact checker not initialized")
    
    result = await fact_checker.verify_claim(request.claim, request.context, request.sources)
    return result


@router.post("/synthesize")
async def synthesize_answer(
    request: SynthesizeRequest,
    current_user: User = Depends(get_current_user),
):
    global answer_synthesizer
    if not answer_synthesizer:
        raise HTTPException(status_code=503, detail="Answer synthesizer not initialized")
    
    answer = await answer_synthesizer.synthesize(
        query=request.query,
        sources=request.sources,
        context=request.context,
        style=request.style,
        citations=request.citations
    )
    return {"query": request.query, "answer": answer}


@router.post("/semantic/cache/get")
async def semantic_cache_get(
    request: SemanticCacheGetRequest,
    current_user: User = Depends(get_current_user),
):
    value = await semantic_cache.get(request.query)
    return {"found": value is not None, "value": value}


@router.post("/semantic/cache/set")
async def semantic_cache_set(
    request: SemanticCacheSetRequest,
    current_user: User = Depends(get_current_user),
):
    await semantic_cache.set(request.query, request.value)
    return {"success": True}


@router.post("/semantic/cache/invalidate")
async def semantic_cache_invalidate(
    query: str = Body(None),
    current_user: User = Depends(get_current_user),
):
    semantic_cache.invalidate(query)
    return {"success": True}


@router.post("/semantic/route")
async def semantic_route(
    request: SemanticRouterRequest,
    current_user: User = Depends(get_current_user),
):
    route = await semantic_router.route(request.query, request.threshold)
    return {"query": request.query, "route": route, "threshold": request.threshold}


@router.post("/semantic/router/initialize")
async def initialize_semantic_router(
    routes: Dict[str, str] = Body(...),
    current_user: User = Depends(get_current_user),
):
    global semantic_router
    semantic_router = SemanticRouter(
        vector_store=vector_store,
        embedder=embedding_provider,
        routes=routes
    )
    await semantic_router.initialize()
    return {"success": True, "routes": list(routes.keys())}


@router.post("/documents/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    metadata: str = Body("{}"),
    chunk: bool = Body(True),
    chunk_size: int = Body(500),
    chunk_overlap: int = Body(50),
    current_user: User = Depends(get_current_user),
):
    import json
    metadata_dict = json.loads(metadata) if metadata else {}
    metadata_dict.update({
        "filename": file.filename,
        "content_type": file.content_type,
        "uploaded_by": current_user.id,
        "uploaded_at": datetime.utcnow().isoformat()
    })
    
    content = (await file.read()).decode("utf-8", errors="ignore")
    document_id = str(uuid.uuid4())
    
    chunks = await rag_pipeline.ingest_document(
        document_id=document_id,
        content=content,
        metadata=metadata_dict,
        chunk=True
    )
    
    return {"success": True, "document_id": document_id, "chunks_ingested": len(chunks)}


@router.get("/documents/{document_id}/chunks")
async def get_document_chunks(
    document_id: str,
    current_user: User = Depends(get_current_user),
):
    chunks = await vector_store.get_document_chunks(document_id)
    return {
        "document_id": document_id,
        "chunks": [
            {
                "id": c.id,
                "chunk_index": c.chunk_index,
                "content": c.content,
                "metadata": c.metadata
            }
            for c in chunks
        ]
    }