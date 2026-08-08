"""Timeline events for work entities (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.project import ProjectTimeline


class TimelineService:
    async def add(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        project_id: str,
        kind: str,
        title: str,
        description: Optional[str] = None,
        meta: Optional[dict[str, Any]] = None,
    ) -> ProjectTimeline:
        entry = ProjectTimeline(
            organization_id=organization_id,
            project_id=project_id,
            kind=kind,
            title=title,
            description=description,
            meta=meta,
            occurred_at=utcnow(),
        )
        db.add(entry)
        return entry

    async def list_all(
        self, db: AsyncSession, *, organization_id: str, project_id: str, limit: int = 100
    ) -> list[ProjectTimeline]:
        rows = await db.execute(
            select(ProjectTimeline)
            .where(
                ProjectTimeline.organization_id == organization_id,
                ProjectTimeline.project_id == project_id,
            )
            .order_by(desc(ProjectTimeline.occurred_at))
            .limit(limit)
        )
        return list(rows.scalars().all())


timeline_service = TimelineService()

