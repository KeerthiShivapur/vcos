"""Slice 4D.2 — change-driven semantic indexer over ``KnowledgeVector``.

The single implementation that keeps the chunk-level vector index in sync
with the canonical knowledge tables. It is invoked from the event bus
handlers (create / update / restore / publish / delete) and from the bounded
scheduled sweep (:mod:`app.workers.indexing_worker`), and it is safe to call
from any transaction:

* Idempotent — the unique key (organization_id, source_type, source_id,
  chunk_index) makes re-runs a no-op when nothing changed.
* Stale-chunk deletion — chunks that no longer exist in the source content
  are deleted, so removed content can never resurface through search.
* Never commits — the caller (event bus or worker) owns the transaction.
* Bounded — at most ``MAX_CHUNKS_PER_ENTITY`` chunks per entity, one entity
  per call.
"""

import json
import logging
from typing import Any, Optional

from sqlalchemy import delete, func, select

from app.core.timeutils import utcnow
from app.knowledge import knowledge_base as kb
from app.knowledge.chunking import (
    MAX_CHUNKS_PER_ENTITY,
    chunk_text,
    content_hash,
)
from app.knowledge.embeddings import embedding_to_json, get_embedding_provider
from app.models.knowledge import KnowledgeVector

logger = logging.getLogger("vcos.knowledge.semantic_indexer")

MAX_BODY_CHARS = 60_000  # hard cap on indexed body length per entity


def _chunk_candidates(entity: Any) -> list[str]:
    """Deterministic chunk list for one entity (title + searchable body)."""
    title = getattr(entity, "title", "") or ""
    body = kb.entity_text(entity) or ""
    text = f"{title}\n\n{body}".strip()[:MAX_BODY_CHARS]
    chunks = chunk_text(text)
    if not chunks:
        chunks = [title or "untitled"]
    return chunks[:MAX_CHUNKS_PER_ENTITY]


def _metadata(entity: Any) -> dict[str, Any]:
    project_id = getattr(entity, "project_id", None)
    return {
        "title": getattr(entity, "title", None),
        "status": getattr(entity, "status", None),
        "category": getattr(entity, "category", None),
        "project_id": project_id,
        "summary": getattr(entity, "summary", None) or getattr(entity, "ai_summary", None),
    }


def _entity_url(kind: str, entity_id: str) -> str:
    from app.schemas.knowledge import entity_url

    return entity_url(kind, entity_id)


async def _existing_rows(
    db, *, organization_id: str, kind: str, entity_id: str
) -> dict[int, KnowledgeVector]:
    rows = (
        await db.execute(
            select(KnowledgeVector)
            .where(
                KnowledgeVector.organization_id == organization_id,
                KnowledgeVector.source_type == kind,
                KnowledgeVector.source_id == entity_id,
            )
            .order_by(KnowledgeVector.chunk_index)
        )
    ).scalars().all()
    return {row.chunk_index: row for row in rows}


async def index_status(
    db, *, organization_id: str, kind: str, entity_id: str
) -> dict[str, Any]:
    """Diagnostics: what the vector index holds for one source."""
    rows = list((await _existing_rows(db, organization_id=organization_id, kind=kind, entity_id=entity_id)).values())
    if not rows:
        return {"indexed": False, "chunks": 0}
    return {
        "indexed": True,
        "chunks": len(rows),
        "provider": rows[0].provider,
        "dim": rows[0].dim,
        "source_updated_at": rows[0].source_updated_at.isoformat() if rows[0].source_updated_at else None,
        "indexed_at": rows[0].indexed_at.isoformat() if rows[0].indexed_at else None,
    }


async def is_fresh(
    db, *, organization_id: str, kind: str, entity_id: str, source_updated_at: Any
) -> bool:
    """True when every current chunk of the source is already indexed."""
    if source_updated_at is None:
        return False
    row = (
        await db.execute(
            select(
                func.count(KnowledgeVector.id),
                func.max(KnowledgeVector.source_updated_at),
            ).where(
                KnowledgeVector.organization_id == organization_id,
                KnowledgeVector.source_type == kind,
                KnowledgeVector.source_id == entity_id,
            )
        )
    ).one()
    count, newest = row
    return bool(count) and newest is not None and newest >= source_updated_at


async def reindex_entity(
    db, *, organization_id: str, kind: str, entity_id: str
) -> int:
    """Recompute and persist the chunk vectors for one entity (idempotent).

    Returns the number of vector rows written (0 when already current).
    Never commits.
    """
    entity = await kb.resolve_entity(db, organization_id=organization_id, kind=kind, entity_id=entity_id)
    if entity is None:
        await delete_entity(db, organization_id=organization_id, kind=kind, entity_id=entity_id)
        return 0
    chunks = _chunk_candidates(entity)
    provider = get_embedding_provider()
    existing = await _existing_rows(db, organization_id=organization_id, kind=kind, entity_id=entity_id)

    hashes = [content_hash(c) for c in chunks]
    unchanged = (
        len(existing) == len(chunks)
        and all(
            existing.get(index) is not None and existing[index].content_hash == hashes[index]
            for index in range(len(chunks))
        )
        and all(existing[index].provider == provider.name for index in range(len(chunks)))
    )
    if unchanged:
        return 0

    try:
        vectors = await provider.embed_many(chunks)
    except Exception as exc:  # noqa: BLE001 - surfaced to caller for per-entity isolation
        logger.warning("embedding failed for %s/%s: %s", kind, entity_id, exc)
        raise

    source_updated_at = getattr(entity, "updated_at", None)
    metadata = _metadata(entity)
    metadata["url"] = _entity_url(kind, entity_id)
    metadata_json = json.dumps(metadata, separators=(",", ":"), default=str)
    written = 0
    for index, chunk in enumerate(chunks):
        row = existing.get(index)
        if row is None:
            row = KnowledgeVector(
                organization_id=organization_id,
                source_type=kind,
                source_id=entity_id,
                chunk_index=index,
            )
            db.add(row)
        row.chunk_text = chunk
        row.content_hash = hashes[index]
        row.embedding = embedding_to_json(vectors[index])
        row.provider = provider.name
        row.dim = len(vectors[index])
        row.source_updated_at = source_updated_at
        row.indexed_at = utcnow()
        row.metadata_json = metadata_json
        written += 1
    stale = [i for i in existing if i >= len(chunks)]
    if stale:
        await db.execute(
            delete(KnowledgeVector).where(
                KnowledgeVector.organization_id == organization_id,
                KnowledgeVector.source_type == kind,
                KnowledgeVector.source_id == entity_id,
                KnowledgeVector.chunk_index.in_(stale),
            )
        )
    await db.flush()
    return written


async def delete_entity(
    db, *, organization_id: str, kind: str, entity_id: str
) -> bool:
    """Remove every vector for a source (deleted content stays deleted)."""
    result = await db.execute(
        delete(KnowledgeVector).where(
            KnowledgeVector.organization_id == organization_id,
            KnowledgeVector.source_type == kind,
            KnowledgeVector.source_id == entity_id,
        )
    )
    return bool(result.rowcount)
