"""Organization timeline service (Phase 19.2) — travel through company history.

The timeline records every meaningful event across all modules (hiring,
projects, releases, meetings, knowledge, learning, community, innovation,
customers, finance, leadership). Users can browse by category, date range and
actor, and workers auto-record entries from the event bus.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.publisher import publish_background_event
from app.models.company_memory import OrganizationTimeline

TIMELINE_CATEGORIES = (
    "hiring", "projects", "releases", "meetings", "knowledge", "learning",
    "community", "innovation", "customers", "finance", "leadership", "system", "health",
)

# events that auto-populate the timeline (name -> category)
TIMELINE_EVENT_MAP: dict[str, str] = {
    "employee.joined": "hiring",
    "employee.offboarded": "hiring",
    "employee.promoted": "hiring",
    "project.created": "projects",
    "milestone.completed": "releases",
    "deployment.completed": "releases",
    "meeting.ended": "meetings",
    "document.approved": "knowledge",
    "policy.approved": "knowledge",
    "wiki.updated": "knowledge",
    "course.completed": "learning",
    "certification.issued": "learning",
    "community.posted": "community",
    "recognition.given": "community",
    "innovation.submitted": "innovation",
    "opportunity.won": "customers",
    "contract.signed": "customers",
    "invoice.received": "finance",
    "payment.completed": "finance",
    "decision.made": "leadership",
    "decision.analyzed": "leadership",
    "intelligence.brief": "leadership",
    "health.updated": "health",
    "company.health.updated": "health",
    "organization.evolved": "system",
}


class TimelineService:
    async def record(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        event_type: str,
        title: str,
        category: Optional[str] = None,
        detail: Optional[str] = None,
        occurred_at: Optional[datetime] = None,
        actor_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if category is None:
            category = TIMELINE_EVENT_MAP.get(event_type, "system")
        if category not in TIMELINE_CATEGORIES:
            raise ValueError(f"category must be one of {TIMELINE_CATEGORIES}")
        row = OrganizationTimeline(
            organization_id=organization_id,
            event_type=event_type,
            category=category,
            title=title,
            detail=detail,
            occurred_at=ensure_aware(occurred_at or utcnow()),
            actor_id=actor_id,
            entity_type=entity_type,
            entity_id=entity_id,
            metadata_json=metadata or {},
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="timeline.recorded", organization_id=organization_id,
            payload={"entry_id": row.id, "category": category, "title": title[:120]},
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    async def list(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        category: Optional[str] = None,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        actor_id: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(OrganizationTimeline).where(OrganizationTimeline.organization_id == organization_id)
        if category:
            stmt = stmt.where(OrganizationTimeline.category == category)
        if start:
            stmt = stmt.where(OrganizationTimeline.occurred_at >= ensure_aware(start))
        if end:
            stmt = stmt.where(OrganizationTimeline.occurred_at <= ensure_aware(end))
        if actor_id:
            stmt = stmt.where(OrganizationTimeline.actor_id == actor_id)
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(
                or_(
                    OrganizationTimeline.title.ilike(pattern),
                    OrganizationTimeline.detail.ilike(pattern),
                )
            )
        rows = (
            await db.execute(stmt.order_by(OrganizationTimeline.occurred_at.desc()).limit(limit))
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    async def get(self, db: AsyncSession, organization_id: str, entry_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(OrganizationTimeline).where(
                    OrganizationTimeline.organization_id == organization_id,
                    OrganizationTimeline.id == entry_id,
                )
            )
        ).scalars().first()
        return self.serialize(row) if row else None

    async def summary(self, db: AsyncSession, organization_id: str) -> dict[str, Any]:
        """Per-category counts + most recent milestones for the timeline view."""
        from sqlalchemy import func

        rows = (
            await db.execute(
                select(OrganizationTimeline.category, func.count(OrganizationTimeline.id))
                .where(OrganizationTimeline.organization_id == organization_id)
                .group_by(OrganizationTimeline.category)
            )
        ).all()
        categories = {c: int(n) for c, n in rows}
        latest = await self.list(db, organization_id, limit=10)
        return {
            "organization_id": organization_id,
            "total": sum(categories.values()),
            "categories": categories,
            "latest": latest,
        }

    def serialize(self, row: OrganizationTimeline) -> dict[str, Any]:
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "event_type": row.event_type,
            "category": row.category,
            "title": row.title,
            "detail": row.detail,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
            "actor_id": row.actor_id,
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "metadata": row.metadata_json or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


timeline_service = TimelineService()
