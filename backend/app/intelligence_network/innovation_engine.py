"""Innovation intelligence — tracks ideas, research, experiments and
recommends the next innovations.

The engine aggregates signals from community discussions, ideas and learning
activity, maintains the innovation funnel and proposes high-potential next
innovations.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.communication import CommunityPost
from app.models.innovation import Innovation, INNOVATION_CATEGORIES


class InnovationEngine:
    async def scan(self, db: AsyncSession, organization_id: str, *, commit: bool = False) -> dict[str, Any]:
        now = utcnow()
        month_ago = now - timedelta(days=30)
        tracked: dict[str, dict[str, Any]] = {}

        community_rows = (
            await db.execute(
                select(CommunityPost)
                .where(
                    CommunityPost.organization_id == organization_id,
                    CommunityPost.created_at >= month_ago,
                )
                .order_by(CommunityPost.created_at.desc())
                .limit(100)
            )
        ).scalars().all()

        for post in community_rows:
            title = getattr(post, "title", None)
            body = getattr(post, "content", None) or getattr(post, "body", None)
            if not title and not body:
                continue
            key = str(getattr(post, "community_id", ""))
            tracked.setdefault(key, {
                "category": "community",
                "count": 0,
                "example": str(title or str(body)[:80]),
            })
            tracked[key]["count"] += 1

        recommendations: list[dict[str, Any]] = []
        for category in INNOVATION_CATEGORIES:
            count = (
                await db.execute(
                    select(func.count(Innovation.id)).where(
                        Innovation.organization_id == organization_id,
                        Innovation.category == category,
                        Innovation.status == "active",
                    )
                )
            ).scalar() or 0
            if count >= 3 and category == "product":
                recommendations.append({
                    "category": category,
                    "title": "Prioritize the strongest product innovation",
                    "detail": "Multiple active product ideas — consolidate into one experiment.",
                    "confidence": 0.6,
                })

        new_innovations = 0
        for item in tracked.values():
            if item["count"] >= 3:
                row = Innovation(
                    organization_id=organization_id,
                    title=item["example"][:120],
                    category="community",
                    description=f"{item['count']} community posts about this topic.",
                    stage="idea",
                    status="active",
                    signals=[{"metric": "community_posts", "value": item["count"]}],
                )
                db.add(row)
                new_innovations += 1
        await db.flush()
        await publish_background_event(
            db, name="innovation.updated", organization_id=organization_id,
            payload={"tracked_topics": len(tracked), "new_innovations": new_innovations},
        )
        if commit:
            await db.commit()
        return {
            "tracked_topics": len(tracked),
            "new_innovations": new_innovations,
            "recommendations": recommendations,
        }

    async def list(
        self, db: AsyncSession, organization_id: str, *, stage: str | None = None, limit: int = 100
    ) -> dict[str, Any]:
        stmt = select(Innovation).where(Innovation.organization_id == organization_id)
        if stage:
            stmt = stmt.where(Innovation.stage == stage)
        rows = (
            await db.execute(stmt.order_by(Innovation.created_at.desc()).limit(limit))
        ).scalars().all()
        return {
            "total": len(rows),
            "innovations": [
                {
                    "id": r.id, "title": r.title, "category": r.category,
                    "description": r.description, "stage": r.stage,
                    "votes": r.votes, "status": r.status,
                    "signals": r.signals or [],
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ],
        }


innovation_engine = InnovationEngine()
