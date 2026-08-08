"""Knowledge analytics service — metrics for the "brain health" dashboard (Phase 4.11)."""

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.knowledge import knowledge_base as kb
from app.models.knowledge import KnowledgeQuality, KnowledgeRelation


class AnalyticsService:
    async def overview(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        counts: dict[str, int] = {}
        total = 0
        for k, model in kb.KIND_MODELS.items():
            n = (await db.execute(select(func.count()).select_from(model).where(getattr(model, "organization_id") == organization_id))).scalar_one()
            counts[k] = int(n)
            total += int(n)
        relations = (await db.execute(select(func.count()).select_from(KnowledgeRelation).where(KnowledgeRelation.organization_id == organization_id))).scalar_one()
        quality_rows = (await db.execute(select(KnowledgeQuality).where(KnowledgeQuality.organization_id == organization_id))).scalars().all()
        avg_quality = round(sum(q.score or 0 for q in quality_rows) / len(quality_rows), 2) if quality_rows else 0.0
        return {
            "totals": counts,
            "total_items": total,
            "total_relations": int(relations),
            "avg_quality_score": avg_quality,
            "quality_scanned": len(quality_rows),
        }

    async def growth(self, db: AsyncSession, *, organization_id: str, days: int = 30) -> dict[str, Any]:
        cutoff = utcnow() - timedelta(days=days)
        series: dict[str, int] = {}
        by_kind: dict[str, int] = {}
        for k, model in kb.KIND_MODELS.items():
            rows = (
                await db.execute(
                    select(model.created_at).where(
                        getattr(model, "organization_id") == organization_id,
                        getattr(model, "created_at") >= cutoff,
                    )
                )
            ).scalars().all()
            for created_at in rows:
                day = created_at.date().isoformat()
                series[day] = series.get(day, 0) + 1
                by_kind[k] = by_kind.get(k, 0) + 1
        return {
            "days": sorted(series.keys()),
            "counts": [series[d] for d in sorted(series.keys())],
            "by_kind": by_kind,
        }

    async def top_viewed(self, db: AsyncSession, *, organization_id: str, limit: int = 10) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for k, model in kb.KIND_MODELS.items():
            rows = (
                await db.execute(
                    select(model)
                    .where(getattr(model, "organization_id") == organization_id)
                    .order_by(getattr(model, "view_count").desc())
                    .limit(limit)
                )
            ).scalars().all()
            for row in rows:
                results.append(
                    {
                        "id": row.id,
                        "type": k,
                        "title": row.title,
                        "views": getattr(row, "view_count") or 0,
                        "url": kb.entity_url(k, row.id),
                    }
                )
        results.sort(key=lambda r: r["views"], reverse=True)
        return results[:limit]

    async def contributors(self, db: AsyncSession, *, organization_id: str, limit: int = 10) -> list[dict[str, Any]]:
        tally: dict[str, int] = {}
        for k, model in kb.KIND_MODELS.items():
            col = getattr(model, "author_id", None) or getattr(model, "owner_id", None)
            if col is None:
                continue
            rows = (
                await db.execute(
                    select(col).where(getattr(model, "organization_id") == organization_id)
                )
            ).scalars().all()
            for author_id in rows:
                if author_id:
                    tally[author_id] = tally.get(author_id, 0) + 1
        ranked = sorted(tally.items(), key=lambda item: item[1], reverse=True)[:limit]
        names = await kb.employee_names(db, employee_ids=[aid for aid, _ in ranked])
        return [{"employee_id": aid, "name": names.get(aid, "Unknown"), "count": count} for aid, count in ranked]

    async def coverage(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        """How many projects/departments have knowledge attached."""
        projects_with_kb = set()
        for k, model in kb.KIND_MODELS.items():
            if not hasattr(model, "project_id"):
                continue
            rows = (
                await db.execute(
                    select(getattr(model, "project_id")).where(
                        getattr(model, "organization_id") == organization_id,
                        getattr(model, "project_id").isnot(None),
                    )
                )
            ).scalars().all()
            projects_with_kb.update(rows)
        return {"projects_with_knowledge": len(projects_with_kb)}

    async def quality(self, db: AsyncSession, *, organization_id: str, limit: int = 20) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(KnowledgeQuality)
                .where(KnowledgeQuality.organization_id == organization_id)
                .order_by(KnowledgeQuality.score.asc())
                .limit(limit)
            )
        ).scalars().all()
        return {
            "lowest": [
                {
                    "id": q.id,
                    "entity_type": q.entity_type,
                    "entity_id": q.entity_id,
                    "score": q.score,
                    "issues": (
                        (["duplicate"] if q.duplicate_of else [])
                        + (["overdue"] if q.review_status == "overdue" else [])
                        + (["low_score"] if q.score < 40 else [])
                    ),
                }
                for q in rows
            ]
        }

    async def search_trends(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        return {"top_terms": [], "total_searches": 0}

    async def duplicates(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        rows = (
            await db.execute(
                select(KnowledgeQuality)
                .where(
                    KnowledgeQuality.organization_id == organization_id,
                    KnowledgeQuality.duplicate_of.isnot(None),
                )
            )
        ).scalars().all()
        return {"count": len(rows), "items": [{"entity_type": q.entity_type, "entity_id": q.entity_id, "duplicate_of": q.duplicate_of} for q in rows[:50]]}


analytics_service = AnalyticsService()
