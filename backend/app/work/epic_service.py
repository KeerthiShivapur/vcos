"""Epic service (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.project import Epic
from app.models.task import Task


class EpicService:
    async def create(self, db, *, organization_id: str, data: dict[str, Any]) -> Epic:
        epic = Epic(
            organization_id=organization_id,
            project_id=data.get("project_id"),
            roadmap_id=data.get("roadmap_id"),
            name=data["name"],
            description=data.get("description"),
            status=data.get("status", "planned"),
            priority=data.get("priority", "medium"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
        )
        db.add(epic)
        await db.flush()
        return epic

    async def get(self, db, *, organization_id: str, epic_id: str) -> Optional[Epic]:
        return (
            await db.execute(
                select(Epic).where(Epic.organization_id == organization_id, Epic.id == epic_id)
            )
        ).scalar_one_or_none()

    async def list_all(self, db, *, organization_id: str, project_id: Optional[str] = None) -> list[Epic]:
        stmt = select(Epic).where(Epic.organization_id == organization_id)
        if project_id:
            stmt = stmt.where(Epic.project_id == project_id)
        rows = await db.execute(stmt.order_by(desc(Epic.updated_at)))
        epics = list(rows.scalars().all())
        ids = [e.id for e in epics]
        if ids:
            completed = dict(
                (await db.execute(
                    select(Task.epic_id, func.count(Task.id))
                    .where(Task.organization_id == organization_id, Task.epic_id.in_(ids), Task.status == "completed")
                    .group_by(Task.epic_id)
                )).all()
            )
            total = dict(
                (await db.execute(
                    select(Task.epic_id, func.count(Task.id))
                    .where(Task.organization_id == organization_id, Task.epic_id.in_(ids))
                    .group_by(Task.epic_id)
                )).all()
            )
            for e in epics:
                e.tasks_count = total.get(e.id, 0)
                e.progress = int(completed.get(e.id, 0) / total[e.id] * 100) if total.get(e.id) else e.progress
        return epics

    async def update(self, db, *, epic: Epic, data: dict[str, Any]) -> Epic:
        for key, value in data.items():
            if hasattr(epic, key):
                setattr(epic, key, value)
        epic.updated_at = utcnow()
        return epic

    async def delete(self, db, *, epic: Epic):
        await db.delete(epic)


epic_service = EpicService()

