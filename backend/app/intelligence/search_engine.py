"""Phase 9.6 — Search improvement engine.

Continuously learns from search behavior:

    - successful vs failed searches
    - popular queries and documents
    - rising topics

The analytics worker aggregates SearchMetric rows into SearchInsight rows
(failed searches, popular queries, popular documents). The insights drive
search ranking hints surfaced in the intelligence center.
"""

import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.intelligence import SearchInsight, SearchMetric

logger = logging.getLogger("vcos.intelligence.search")

MIN_FAILURES = 3  # a query fails when it produced no clicks 3+ times


class SearchEngine:
    async def record_metric(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        query: str,
        user_id: Optional[str] = None,
        success: bool = True,
        result_count: int = 0,
        clicked_type: Optional[str] = None,
        clicked_id: Optional[str] = None,
        clicked_title: Optional[str] = None,
        latency_ms: Optional[int] = None,
    ) -> SearchMetric:
        row = SearchMetric(
            organization_id=organization_id,
            user_id=user_id,
            query=(query or "").strip()[:300],
            success=success,
            result_count=result_count,
            clicked_type=clicked_type,
            clicked_id=clicked_id,
            clicked_title=clicked_title,
            latency_ms=latency_ms,
        )
        db.add(row)
        await db.flush()
        return row

    async def aggregate(self, db: AsyncSession, *, organization_id: str, since_days: int = 14) -> int:
        """Aggregate recent search metrics into SearchInsight rows."""
        cutoff = utcnow() - timedelta(days=since_days)
        created = 0

        # failed searches: zero-result or no-click queries repeated enough
        rows = (
            await db.execute(
                select(
                    SearchMetric.query,
                    func.count(SearchMetric.id),
                )
                .where(
                    SearchMetric.organization_id == organization_id,
                    SearchMetric.created_at >= cutoff,
                    SearchMetric.success.is_(False),
                    func.length(SearchMetric.query) >= 3,
                )
                .group_by(SearchMetric.query)
                .having(func.count(SearchMetric.id) >= MIN_FAILURES)
            )
        ).all()
        for query, failures in rows:
            total_row = (
                await db.execute(
                    select(func.count(SearchMetric.id))
                    .where(
                        SearchMetric.organization_id == organization_id,
                        SearchMetric.created_at >= cutoff,
                        SearchMetric.query == query,
                    )
                )
            ).scalar() or 0
            failure_rate = (failures / total_row) if total_row else 1.0
            if failure_rate < 0.5:
                continue
            created += await self._upsert_insight(
                db, organization_id=organization_id, kind="failed_search",
                key=f"q:{query}", title=f'Failing search: "{query}"',
                detail=f"{failures} failed attempts out of {total_row} — a useful result is missing.",
                count=failures,
            )

        # popular queries
        popular = (
            await db.execute(
                select(
                    SearchMetric.query,
                    func.count(SearchMetric.id),
                    func.count(func.distinct(SearchMetric.user_id)),
                )
                .where(
                    SearchMetric.organization_id == organization_id,
                    SearchMetric.created_at >= cutoff,
                )
                .group_by(SearchMetric.query)
                .order_by(func.count(SearchMetric.id).desc())
                .limit(10)
            )
        ).all()
        for query, total, users in popular:
            created += await self._upsert_insight(
                db, organization_id=organization_id, kind="popular_query",
                key=f"q:{query}", title=f'Popular topic: "{query}"',
                detail=f"{total} searches by {users} people in the last {since_days} days.",
                count=total,
            )

        # popular documents
        docs = (
            await db.execute(
                select(
                    SearchMetric.clicked_id,
                    SearchMetric.clicked_title,
                    func.count(SearchMetric.id),
                    func.count(func.distinct(SearchMetric.user_id)),
                )
                .where(
                    SearchMetric.organization_id == organization_id,
                    SearchMetric.created_at >= cutoff,
                    SearchMetric.clicked_id.isnot(None),
                )
                .group_by(SearchMetric.clicked_id, SearchMetric.clicked_title)
                .order_by(func.count(SearchMetric.id).desc())
                .limit(10)
            )
        ).all()
        for doc_id, doc_title, total, users in docs:
            created += await self._upsert_insight(
                db, organization_id=organization_id, kind="popular_document",
                key=f"d:{doc_id}", title=f'Popular document: {doc_title or doc_id}',
                detail=f"{total} clicks by {users} people.",
                count=total,
            )
        if created:
            from app.events.publisher import publish_background_event

            await publish_background_event(
                db,
                name="search.optimized",
                organization_id=organization_id,
                payload={"new_insights": created},
            )
        return created

    async def _upsert_insight(
        self, db: AsyncSession, *, organization_id: str, kind: str, key: str,
        title: str, detail: str, count: int,
    ) -> int:
        row = (
            await db.execute(
                select(SearchInsight).where(
                    SearchInsight.organization_id == organization_id,
                    SearchInsight.kind == kind,
                    SearchInsight.key == key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            db.add(
                SearchInsight(
                    organization_id=organization_id,
                    kind=kind, key=key, title=title, detail=detail,
                    count=count, status="open",
                )
            )
            return 1
        row.count = count
        row.detail = detail
        row.status = "open"
        return 0

    async def list_insights(
        self, db: AsyncSession, *, organization_id: str, limit: int = 50,
        kind: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        filters = [SearchInsight.organization_id == organization_id]
        if kind:
            filters.append(SearchInsight.kind == kind)
        rows = (
            await db.execute(
                select(SearchInsight).where(*filters).order_by(
                    SearchInsight.count.desc()
                ).limit(limit)
            )
        ).scalars().all()
        return [
            {
                "id": r.id,
                "kind": r.kind,
                "key": r.key,
                "title": r.title,
                "detail": r.detail,
                "count": r.count,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    async def stats(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        total = (
            await db.execute(
                select(func.count(SearchMetric.id)).where(SearchMetric.organization_id == organization_id)
            )
        ).scalar() or 0
        failed = (
            await db.execute(
                select(func.count(SearchMetric.id)).where(
                    SearchMetric.organization_id == organization_id,
                    SearchMetric.success.is_(False),
                )
            )
        ).scalar() or 0
        return {
            "total_searches": total,
            "failed_searches": failed,
            "success_rate": round((1 - (failed / total if total else 0)) * 100, 1),
        }


search_engine = SearchEngine()
