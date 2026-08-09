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
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="milestone.created",
            actor=actor, ip_address=ip_address,
            resource_type="milestone", resource_id=milestone.id,
            details={"name": milestone.name, "project_id": milestone.project_id},
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

    async def _validate_ref(self, db, organization_id: str, key: str, value: str):
        from app.models.project import Project, Roadmap

        model = {"project_id": Project, "roadmap_id": Roadmap}.get(key)
        if model is None:
            return
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {key} reference")

    async def update(
        self, db, *, organization_id: str, milestone: Milestone, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Milestone:
        from app.work.guards import apply_editable

        for key in ("project_id", "roadmap_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        if "status" in data and data["status"] != milestone.status:
            raise ValueError("Use the complete endpoint to finish a milestone")
        if milestone.status == "completed":
            raise ValueError("A completed milestone cannot be edited")
        apply_editable(milestone, data)
        milestone.updated_at = utcnow()
        await db.flush()
        if milestone.project_id:
            from app.services.event_service import event_service

            await event_service.emit(
                db, name="milestone.updated", actor_id=actor.user_id if actor else None,
                organization_id=organization_id,
                payload={"project_id": milestone.project_id, "milestone_id": milestone.id, "name": milestone.name},
            )
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="milestone.updated",
            actor=actor, ip_address=ip_address,
            resource_type="milestone", resource_id=milestone.id,
            details={"name": milestone.name},
        )
        return milestone

    async def complete(self, db, *, organization_id: str, milestone: Milestone, actor: Optional[Employee] = None) -> Milestone:
        if milestone.status == "completed":
            raise ValueError("Milestone is already completed")
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
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="milestone.completed",
            actor=actor,
            resource_type="milestone", resource_id=milestone.id,
            details={"name": milestone.name},
        )
        return milestone

    async def delete(
        self, db, *, organization_id: str, milestone: Milestone,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        from app.services.work_audit import record

        tasks = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id, Task.milestone_id == milestone.id
                )
            )
        ).scalar() or 0
        if tasks:
            raise ValueError(f"Milestone has {tasks} task(s); move or complete them before deleting")
        await record(
            db, organization_id=organization_id, action="milestone.deleted",
            actor=actor, ip_address=ip_address,
            resource_type="milestone", resource_id=milestone.id,
            details={"name": milestone.name},
        )
        if milestone.project_id:
            from app.services.event_service import event_service

            await event_service.emit(
                db, name="milestone.deleted", actor_id=actor.user_id if actor else None,
                organization_id=organization_id,
                payload={"project_id": milestone.project_id, "milestone_id": milestone.id, "name": milestone.name},
            )
        await db.delete(milestone)


milestone_service = MilestoneService()
