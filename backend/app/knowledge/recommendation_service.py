"""Knowledge intelligence service — AI recommendations, experts, freshness (Phase 4.10)."""

from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge import knowledge_base as kb
from app.models.employee import Employee
from app.models.knowledge import DocumentFavorite, DocumentPresence, KnowledgeRelation


class RecommendationService:
    async def for_user(
        self, db: AsyncSession, *, organization_id: str, employee: Optional[Employee], limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Personalized feed: related items, fresh knowledge in user's areas, related items."""
        recs: list[dict[str, Any]] = []
        if employee and employee.user_id:
            favorites = (
                await db.execute(
                    select(DocumentFavorite)
                    .where(
                        DocumentFavorite.organization_id == organization_id,
                        DocumentFavorite.user_id == employee.user_id,
                    )
                    .order_by(DocumentFavorite.created_at.desc())
                    .limit(5)
                )
            ).scalars().all()
            seen: set[tuple[str, str]] = set()
            for fav in favorites:
                relations = (
                    await db.execute(
                        select(KnowledgeRelation).where(
                            KnowledgeRelation.organization_id == organization_id,
                            KnowledgeRelation.source_type == fav.entity_type,
                            KnowledgeRelation.source_id == fav.entity_id,
                        )
                    )
                ).scalars().all()
                for rel in relations:
                    target = await kb.resolve_entity(db, organization_id=organization_id, entity_type=rel.target_type, entity_id=rel.target_id)
                    if target is None or target.status not in kb.published_statuses(rel.target_type):
                        continue
                    key = (rel.target_type, rel.target_id)
                    if key in seen:
                        continue
                    seen.add(key)
                    recs.append(
                        {
                            "id": target.id,
                            "type": rel.target_type,
                            "title": target.title,
                            "summary": getattr(target, "summary", "") or "",
                            "url": kb.entity_url(rel.target_type, target.id),
                            "reason": f"Related to a document you favorited",
                            "score": 0.9,
                        }
                    )
                    if len(recs) >= limit:
                        return recs

        cutoff = utcnow() - timedelta(days=30)
        recs.sort(key=lambda r: r["score"], reverse=True)
        return recs[:limit]

    async def experts(
        self, db: AsyncSession, *, organization_id: str, topic: Optional[str] = None, limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Find the people who authored the most knowledge on a topic."""
        rows: list[tuple[str, int]] = []
        for k, model in kb.KIND_MODELS.items():
            col = getattr(model, "author_id", None) or getattr(model, "owner_id", None)
            if col is None:
                continue
            counts = (
                await db.execute(
                    select(
                        col,
                        getattr(model, "view_count"),
                    ).where(getattr(model, "organization_id") == organization_id)
                )
            ).all()
            tally: dict[str, int] = {}
            for author_id, views in counts:
                if not author_id:
                    continue
                tally[author_id] = tally.get(author_id, 0) + 1
            rows.extend(tally.items())

        totals: dict[str, int] = {}
        for author_id, count in rows:
            totals[author_id] = totals.get(author_id, 0) + count
        ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
        names = await kb.employee_names(db, employee_ids=[aid for aid, _ in ranked])
        return [
            {
                "employee_id": aid,
                "name": names.get(aid, "Unknown"),
                "documents_count": count,
                "expertise": topic or "knowledge",
            }
            for aid, count in ranked
        ]

    async def stale(
        self, db: AsyncSession, *, organization_id: str, days: int = 180, limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Items that haven't been updated in a while — candidates for review."""
        cutoff = utcnow() - timedelta(days=days)
        results: list[dict[str, Any]] = []
        for k, model in kb.KIND_MODELS.items():
            rows = (
                await db.execute(
                    select(model)
                    .where(
                        getattr(model, "organization_id") == organization_id,
                        getattr(model, "updated_at") < cutoff,
                    )
                    .order_by(getattr(model, "updated_at").asc())
                    .limit(limit)
                )
            ).scalars().all()
            for row in rows:
                results.append(
                    {
                        "id": row.id,
                        "type": k,
                        "title": row.title,
                        "status": getattr(row, "status", "") or "",
                        "url": kb.entity_url(k, row.id),
                        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    }
                )
                if len(results) >= limit:
                    return results
        return results


recommendation_service = RecommendationService()
