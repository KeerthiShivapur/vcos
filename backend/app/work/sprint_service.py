"""Sprint service (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.project import Sprint
from app.models.task import Task


class SprintService:
    async def create(self, db, *, organization_id: str, data: dict[str, Any]) -> Sprint:
        sprint = Sprint(
            organization_id=organization_id,
            project_id=data.get("project_id"),
            name=data["name"],
            goal=data.get("goal"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            status=data.get("status", "planned"),
        )
        db.add(sprint)
        await db.flush()
        return sprint

    async def get(self, db, *, organization_id: str, sprint_id: str) -> Optional[Sprint]:
        return (
            await db.execute(
                select(Sprint).where(Sprint.organization_id == organization_id, Sprint.id == sprint_id)
            )
        ).scalar_one_or_none()

    async def list_all(self, db, *, organization_id: str, project_id: Optional[str] = None) -> list[Sprint]:
        stmt = select(Sprint).where(Sprint.organization_id == organization_id)
        if project_id:
            stmt = stmt.where(Sprint.project_id == project_id)
        rows = await db.execute(stmt.order_by(desc(Sprint.start_date)))
        sprints = list(rows.scalars().all())
        ids = [s.id for s in sprints]
        if ids:
            counts = dict(
                (await db.execute(
                    select(Task.sprint_id, func.count(Task.id))
                    .where(Task.organization_id == organization_id, Task.sprint_id.in_(ids))
                    .group_by(Task.sprint_id)
                )).all()
            )
            completed = dict(
                (await db.execute(
                    select(Task.sprint_id, func.count(Task.id))
                    .where(Task.organization_id == organization_id, Task.sprint_id.in_(ids), Task.status == "completed")
                    .group_by(Task.sprint_id)
                )).all()
            )
            for s in sprints:
                s.tasks_count = counts.get(s.id, 0)
                s.completed_tasks = completed.get(s.id, 0)
        return sprints

    async def update(self, db, *, sprint: Sprint, data: dict[str, Any]) -> Sprint:
        for key, value in data.items():
            if hasattr(sprint, key):
                setattr(sprint, key, value)
        sprint.updated_at = utcnow()
        return sprint

    async def start(self, db, *, sprint: Sprint) -> Sprint:
        sprint.status = "active"
        sprint.updated_at = utcnow()
        return sprint

    async def complete(self, db, *, sprint: Sprint) -> Sprint:
        sprint.status = "completed"
        sprint.updated_at = utcnow()
        return sprint

    async def delete(self, db, *, sprint: Sprint):
        await db.delete(sprint)


sprint_service = SprintService()

