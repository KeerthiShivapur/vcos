"""Milestone service (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.project import Milestone
from app.models.task import Task


class MilestoneService:
    async def create(
        self, db, *, organization_id: str, data: dict[str, Any], actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Milestone:
        milestone = Milestone(
            organization_id=organization_id,
            project_id=data.get("project_id"),
            roadmap_id=data.get("roadmap_id"),
            name=data["name"],
            description=data.get("description"),
            due_date=data.get("due_date"),
            status=data.get("status", "pending"),
        )
        db.add(milestone)
        await db.flush()
        if milestone.project_id:
            from app.services.event_service import event_service

            await event_service.emit(
                db, name="milestone.created", actor_id=actor.user_id if actor else None,
                organization_id=organization_id,
                payload={"project_id": milestone.project_id, "milestone_id": milestone.id, "name": milestone.name},
            )
        return milestone

    async def get(self, db, *, organization_id: str, milestone_id: str) -> Optional[Milestone]:
        return (
            await db.execute(
                select(Milestone).where(
                    Milestone.organization_id == organization_id, Milestone.id == milestone_id
                )
            )
        ).scalar_one_or_none()

    async def list_all(self, db, *, organization_id: str, project_id: Optional[str] = None) -> list[Milestone]:
        stmt = select(Milestone).where(Milestone.organization_id == organization_id)
        if project_id:
            stmt = stmt.where(Milestone.project_id == project_id)
        rows = await db.execute(stmt.order_by(Milestone.due_date.asc().nulls_last(), desc(Milestone.created_at)))
        milestones = list(rows.scalars().all())
        ids = [m.id for m in milestones]
        if ids:
            total = dict(
                (await db.execute(
                    select(Task.milestone_id, func.count(Task.id))
                    .where(Task.organization_id == organization_id, Task.milestone_id.in_(ids))
                    .group_by(Task.milestone_id)
                )).all()
            )
            completed = dict(
                (await db.execute(
                    select(Task.milestone_id, func.count(Task.id))
                    .where(
                        Task.organization_id == organization_id,
                        Task.milestone_id.in_(ids),
                        Task.status == "completed",
                    )
                    .group_by(Task.milestone_id)
                )).all()
            )
            for m in milestones:
                m.tasks_count = total.get(m.id, 0)
                m.completed_tasks = completed.get(m.id, 0)
                m.progress = int(completed.get(m.id, 0) / total[m.id] * 100) if total.get(m.id) else m.progress
        return milestones

    async def update(self, db, *, milestone: Milestone, data: dict[str, Any]) -> Milestone:
        for key, value in data.items():
            if hasattr(milestone, key):
                setattr(milestone, key, value)
        milestone.updated_at = utcnow()
        return milestone

    async def complete(self, db, *, organization_id: str, milestone: Milestone, actor: Optional[Employee] = None) -> Milestone:
        milestone.status = "completed"
        milestone.progress = 100
        milestone.completed_at = utcnow()
        milestone.updated_at = utcnow()
        await db.flush()
        if milestone.project_id:
            from app.services.event_service import event_service

            await event_service.emit(
                db, name="milestone.completed", actor_id=actor.user_id if actor else None,
                organization_id=organization_id,
                payload={"project_id": milestone.project_id, "milestone_id": milestone.id, "name": milestone.name},
            )
        return milestone

    async def delete(self, db, *, milestone: Milestone):
        await db.delete(milestone)


milestone_service = MilestoneService()

