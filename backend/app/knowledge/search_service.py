"""Semantic search over the knowledge base — the "Ask the Company" brain (Phase 4.8).

Supports keyword, semantic (embedding cosine) and hybrid modes over every
knowledge kind through the KnowledgeIndex table. Optional filters (kind,
status, author, project, tags) are resolved against the source entity tables.
"""

import json
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.knowledge import knowledge_base as kb
from app.knowledge.embedding import embed_text, keywords
from app.models.knowledge import KnowledgeIndex, KnowledgeItemTag, KnowledgeTag

SEARCH_MODES = ("keyword", "semantic", "hybrid")


class KnowledgeSearchService:
    async def search(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        mode: str = "hybrid",
        kind: Optional[str] = None,
        kinds: Optional[list[str]] = None,
        tags: Optional[list[str]] = None,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        author_id: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> dict[str, Any]:
        mode = mode if mode in SEARCH_MODES else "hybrid"
        query = (query or "").strip()
        if not query:
            return {"results": [], "total": 0, "mode": mode}

        allowed: Optional[set[tuple[str, str]]] = None
        kinds = kinds or ([kind] if kind else [])
        filter_kinds = [k for k in kinds if k in kb.KIND_MODELS] or None

        if status or project_id or author_id or tags or filter_kinds:
            allowed = await self._allowed_ids(
                db, organization_id=organization_id,
                kinds=filter_kinds, status=status, project_id=project_id,
                author_id=author_id, tags=tags,
            )

        stmt = select(KnowledgeIndex).where(KnowledgeIndex.organization_id == organization_id)
        if allowed is not None:
            pairs = [f"{t}:{i}" for t, i in allowed]
            stmt = stmt.where((KnowledgeIndex.entity_type + ":" + KnowledgeIndex.entity_id).in_(pairs))

        scored: list[tuple[KnowledgeIndex, float]] = []
        qv = embed_text(query)
        kws = {word: 1 for word in keywords(query, limit=20)}
        for row in (await db.execute(stmt)).scalars().all():
            semantic = _cosine_sim(qv, _load_embedding(row))
            if mode == "semantic":
                scored.append((row, semantic))
                continue
            kw = _keyword_score(kws, row)
            scored.append((row, 0.6 * semantic + 0.4 * kw if mode == "hybrid" else kw))

        scored.sort(key=lambda pair: pair[1], reverse=True)
        total = len(scored)
        ranked = [row for row, _ in scored][offset:offset + limit]
        entities = await self._load_entities(db, organization_id=organization_id, rows=ranked)
        scores = {row.id: score for row, score in scored}
        results = [self._to_result(row, entities.get((row.entity_type, row.entity_id)), scores[row.id]) for row in ranked]
        return {"results": results, "total": total, "mode": mode}

    async def _allowed_ids(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        kinds: Optional[list[str]],
        status: Optional[str],
        project_id: Optional[str],
        author_id: Optional[str],
        tags: Optional[list[str]],
    ) -> set[tuple[str, str]]:
        allowed: set[tuple[str, str]] = set()
        for k, model in (kb.KIND_MODELS.items() if kinds is None else ((kk, kb.KIND_MODELS[kk]) for kk in kinds)):
            filters = [model.organization_id == organization_id]
            if status and hasattr(model, "status"):
                filters.append(model.status == status)
            if project_id and hasattr(model, "project_id"):
                filters.append(model.project_id == project_id)
            if author_id and hasattr(model, "author_id"):
                filters.append(model.author_id == author_id)
            ids = (await db.execute(select(model.id).where(*filters))).scalars().all()
            allowed.update((k, i) for i in ids)
        if tags:
            tagged = (
                await db.execute(
                    select(KnowledgeItemTag.entity_type, KnowledgeItemTag.entity_id)
                    .join(KnowledgeTag, KnowledgeTag.id == KnowledgeItemTag.tag_id)
                    .where(
                        KnowledgeItemTag.organization_id == organization_id,
                        KnowledgeTag.name.in_(tags),
                    )
                )
            ).all()
            tagged_set = {(t, i) for t, i in tagged}
            allowed = allowed & tagged_set if allowed else tagged_set
        return allowed

    async def _load_entities(
        self, db: AsyncSession, *, organization_id: str, rows: list[KnowledgeIndex],
    ) -> dict[tuple[str, str], Any]:
        out: dict[tuple[str, str], Any] = {}
        by_kind: dict[str, list[str]] = {}
        for row in rows:
            by_kind.setdefault(row.entity_type, []).append(row.entity_id)
        for k, ids in by_kind.items():
            model = kb.KIND_MODELS.get(k)
            if model is None:
                continue
            entities = (
                await db.execute(
                    select(model).where(model.organization_id == organization_id, model.id.in_(ids))
                )
            ).scalars().all()
            for entity in entities:
                out[(k, entity.id)] = entity
        return out

    @staticmethod
    def _to_result(row: KnowledgeIndex, entity: Optional[Any], score: float) -> dict[str, Any]:
        keywords_json: list[str] = []
        try:
            if row.keywords_json:
                keywords_json = json.loads(row.keywords_json)
        except (TypeError, ValueError):
            keywords_json = []
        return {
            "id": row.entity_id,
            "type": row.entity_type,
            "title": row.title,
            "summary": entity.summary if entity is not None else None,
            "status": entity.status if entity is not None else None,
            "author_id": getattr(entity, "author_id", None)
            if entity is not None and hasattr(entity, "author_id")
            else (getattr(entity, "owner_id", None) if entity is not None else None),
            "project_id": getattr(entity, "project_id", None) if entity is not None else None,
            "score": round(score, 4),
            "url": kb.entity_url(row.entity_type, row.entity_id),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "matched_keywords": keywords_json[:5],
        }


def _load_embedding(row: KnowledgeIndex) -> list[float]:
    try:
        return json.loads(row.embedding_json) if row.embedding_json else []
    except (TypeError, ValueError):
        return []


def _cosine_sim(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _keyword_score(kw: dict[str, int], row: KnowledgeIndex) -> float:
    score = 0.0
    title = (row.title or "").lower()
    content = (row.content or "")[:4000].lower()
    keywords_text = (row.keywords_json or "").lower()
    for word, weight in kw.items():
        if word in title:
            score += 3.0 * weight
        elif word in keywords_text:
            score += 1.5 * weight
        elif word in content:
            score += 0.8 * weight
    return score


knowledge_search_service = KnowledgeSearchService()
