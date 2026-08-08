"""Roadmap service (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.project import Epic, Milestone, Roadmap


class RoadmapService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any], actor: Optional[Employee] = None
    ) -> Roadmap:
        roadmap = Roadmap(
            organization_id=organization_id,
            name=data["name"],
            description=data.get("description"),
            owner_id=data.get("owner_id"),
            timeframe=data.get("timeframe", "quarter"),
            status=data.get("status", "draft"),
        )
        db.add(roadmap)
        await db.flush()
        return roadmap

    async def get(self, db, *, organization_id: str, roadmap_id: str) -> Optional[Roadmap]:
        return (
            await db.execute(
                select(Roadmap).where(
                    Roadmap.organization_id == organization_id, Roadmap.id == roadmap_id
                )
            )
        ).scalar_one_or_none()

    async def list_all(self, db, *, organization_id: str) -> list[Roadmap]:
        rows = await db.execute(
            select(Roadmap)
            .where(Roadmap.organization_id == organization_id)
            .order_by(desc(Roadmap.updated_at))
        )
        roadmaps = list(rows.scalars().all())
        owner_ids = [r.owner_id for r in roadmaps if r.owner_id]
        owners = {}
        if owner_ids:
            owners = {e.id: e for e in (await db.execute(select(Employee).where(Employee.id.in_(owner_ids)))).scalars().all()}
        for r in roadmaps:
            r.owner_name = owners[r.owner_id].full_name if r.owner_id and owners.get(r.owner_id) else None
            r.epics_count = 0
            r.milestones_count = 0
        if roadmaps:
            from sqlalchemy import func

            epic_counts = dict(
                (await db.execute(
                    select(Epic.roadmap_id, func.count(Epic.id))
                    .where(Epic.organization_id == organization_id, Epic.roadmap_id.in_([r.id for r in roadmaps]))
                    .group_by(Epic.roadmap_id)
                )).all()
            )
            ms_counts = dict(
                (await db.execute(
                    select(Milestone.roadmap_id, func.count(Milestone.id))
                    .where(Milestone.organization_id == organization_id, Milestone.roadmap_id.in_([r.id for r in roadmaps]))
                    .group_by(Milestone.roadmap_id)
                )).all()
            )
            for r in roadmaps:
                r.epics_count = epic_counts.get(r.id, 0)
                r.milestones_count = ms_counts.get(r.id, 0)
        return roadmaps

    async def update(self, db, *, roadmap: Roadmap, data: dict[str, Any]) -> Roadmap:
        for key, value in data.items():
            if hasattr(roadmap, key):
                setattr(roadmap, key, value)
        roadmap.updated_at = utcnow()
        return roadmap

    async def delete(self, db, *, roadmap: Roadmap):
        await db.delete(roadmap)


roadmap_service = RoadmapService()

