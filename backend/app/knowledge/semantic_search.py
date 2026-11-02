"""Slice 4D.2 — hybrid semantic knowledge retrieval under governance.

The retrieval pipeline is bounded at every stage (4D laws):

1. Caller access is resolved governance-first (``resolve_caller_access``).
2. Candidate entities per kind are fetched with a hard SQL limit, most
   recently updated first — never a full-org scan.
3. Candidates are filtered by the caller's access *before* any scoring or
   exposure (tenant isolation is part of retrieval, not post-processing).
4. Chunk vectors are fetched with a hard cap and scored in Python (hybrid:
   semantic cosine + lexical token overlap). No ``LIKE '%q%'`` anywhere.
5. Only the provider-matching vectors are scored with cosine; a changed
   embedding configuration degrades to lexical ranking instead of comparing
   vectors from different spaces.

Every returned result carries evidence lineage: the canonical source row,
source_updated_at, indexed_at, the configured provider and explicit scores —
retrieval_score is a retrieval signal, never a claim confidence.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import literal, select

from app.intelligence.company_context import resolve_caller_access
from app.knowledge import knowledge_base as kb
from app.knowledge.embeddings import get_embedding_provider
from app.models.intelligence import KnowledgeVector

logger = logging.getLogger("vcos.knowledge.semantic_search")

PER_KIND_CANDIDATES = 50
MAX_CANDIDATE_ENTITIES = 200
MAX_CHUNK_CANDIDATES = 600
DEFAULT_LIMIT = 10
MAX_LIMIT = 25

PUBLISHED_STATUSES = ("published", "approved", "made", "implemented", "reviewed")

_SEMANTIC_WEIGHT = 0.6
_LEXICAL_WEIGHT = 0.4
_SEMANTIC_FLOOR = 0.08  # deterministic hashing noise floor; below = no real overlap


def _query_tokens(query: str) -> list[str]:
    from app.knowledge.embedding import tokenize

    tokens = tokenize(query)
    return [t for t in tokens if len(t) > 2][:24]


def _lexical_score(query_tokens: list[str], chunk: KnowledgeVector) -> float:
    """Normalized token overlap against title, metadata and chunk text."""
    if not query_tokens:
        return 0.0
    title = ""
    content = chunk.chunk_text or ""
    if chunk.metadata_json:
        try:
            title = (json.loads(chunk.metadata_json).get("title") or "")[:240]
        except (TypeError, ValueError):
            title = ""
    hay = f"{title}\n{content}".lower()
    hits = sum(1 for token in query_tokens if token in hay)
    return hits / len(query_tokens)


def _load_embedding(chunk: KnowledgeVector) -> list[float]:
    try:
        return json.loads(chunk.embedding) if chunk.embedding else []
    except (TypeError, ValueError):
        return []


def _to_result(
    chunk: KnowledgeVector,
    *,
    semantic: float,
    lexical: float,
    retrieval: float,
    scope: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    if chunk.metadata_json:
        try:
            metadata = json.loads(chunk.metadata_json)
        except (TypeError, ValueError):
            metadata = {}
    return {
        "source_type": chunk.source_type,
        "source_id": chunk.source_id,
        "title": metadata.get("title") or chunk.source_id,
        "snippet": (chunk.chunk_text or "")[:280],
        "chunk_index": chunk.chunk_index,
        "url": metadata.get("url") or f"/knowledge/{chunk.source_type}/{chunk.source_id}",
        "status": metadata.get("status"),
        "project_id": metadata.get("project_id"),
        "category": metadata.get("category"),
        "scope": scope,
        "provider": chunk.provider,
        "semantic_score": round(semantic, 4),
        "lexical_score": round(lexical, 4),
        "retrieval_score": round(retrieval, 4),
        "updated_at": chunk.source_updated_at.isoformat() if chunk.source_updated_at else None,
        "indexed_at": chunk.indexed_at.isoformat() if chunk.indexed_at else None,
    }


async def search(
    db,
    *,
    organization_id: str,
    user: Any,
    query: str,
    kinds: Optional[list[str]] = None,
    limit: int = DEFAULT_LIMIT,
) -> dict[str, Any]:
    """Governance-scoped hybrid knowledge search (bounded, deterministic)."""
    query = (query or "").strip()
    kinds = [k for k in (kinds or list(kb.KINDS)) if k in kb.KIND_MODELS]
    limit = max(1, min(limit or DEFAULT_LIMIT, MAX_LIMIT))
    if not query or not kinds:
        return {"query": query, "results": [], "total": 0, "limit": limit,
                "provider": None, "truncated": False}

    access = await resolve_caller_access(db, organization_id=organization_id, user=user)

    accessible: list[tuple[str, str]] = []
    for kind in kinds:
        model = kb.KIND_MODELS[kind]
        project_col = getattr(model, "project_id", None)
        statement = (
            select(model.id, project_col)
            if project_col is not None
            else select(model.id, literal(None).label("project_id"))
        )
        rows = (
            await db.execute(
                statement.where(
                    model.organization_id == organization_id,
                    model.status.in_(PUBLISHED_STATUSES),
                )
                .order_by(model.updated_at.desc())
                .limit(PER_KIND_CANDIDATES)
            )
        ).all()
        for entity_id, project_id in rows:
            if access.org_wide or (
                project_id is not None and project_id in access.project_ids
            ):
                accessible.append((kind, entity_id))
    accessible = accessible[:MAX_CANDIDATE_ENTITIES]
    if not accessible:
        return {"query": query, "results": [], "total": 0, "limit": limit,
                "provider": None, "truncated": False}

    by_kind: dict[str, list[str]] = {}
    for kind, entity_id in accessible:
        by_kind.setdefault(kind, []).append(entity_id)

    chunks: list[KnowledgeVector] = []
    for kind, entity_ids in by_kind.items():
        rows = (
            await db.execute(
                select(KnowledgeVector)
                .where(
                    KnowledgeVector.organization_id == organization_id,
                    KnowledgeVector.source_type == kind,
                    KnowledgeVector.source_id.in_(entity_ids),
                )
                .order_by(
                    KnowledgeVector.source_type,
                    KnowledgeVector.source_id,
                    KnowledgeVector.chunk_index,
                )
                .limit(MAX_CHUNK_CANDIDATES)
            )
        ).scalars().all()
        chunks.extend(rows)
    if not chunks:
        return {"query": query, "results": [], "total": 0, "limit": limit,
                "provider": None, "truncated": False}

    provider = get_embedding_provider()
    query_tokens = _query_tokens(query)
    query_vector = (await provider.embed_many([query]))[0]

    scored: list[tuple[float, float, float, KnowledgeVector]] = []
    for chunk in chunks:
        if chunk.provider == provider.name:
            semantic = provider.cosine(query_vector, _load_embedding(chunk))
        else:
            semantic = 0.0
        lexical = _lexical_score(query_tokens, chunk)
        retrieval = _SEMANTIC_WEIGHT * semantic + _LEXICAL_WEIGHT * lexical
        # Relevance gate: at least one real token overlap (lexical) or a cosine
        # clearly above the deterministic hashing noise floor — zero-overlap
        # and collision-noise chunks never surface.
        if retrieval > 0.0 and (lexical > 0.0 or semantic >= _SEMANTIC_FLOOR):
            scored.append((semantic, lexical, retrieval, chunk))
    scored.sort(key=lambda pair: pair[2], reverse=True)

    best_by_source: dict[tuple[str, str], tuple[float, float, KnowledgeVector]] = {}
    for semantic, lexical, retrieval, chunk in scored:
        key = (chunk.source_type, chunk.source_id)
        if key not in best_by_source:
            best_by_source[key] = (semantic, lexical, chunk)
    ranked = list(best_by_source.values())

    scope = "org" if access.org_wide else "project"
    results = [
        _to_result(
            chunk,
            semantic=semantic,
            lexical=lexical,
            retrieval=_SEMANTIC_WEIGHT * semantic + _LEXICAL_WEIGHT * lexical,
            scope=scope,
        )
        for semantic, lexical, chunk in ranked[:limit]
    ]
    return {
        "query": query,
        "results": results,
        "total": len(ranked),
        "limit": limit,
        "provider": provider.name,
        "truncated": len(ranked) > limit,
    }
