"""Epic service (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.project import Epic
from app.models.task import Task


class EpicService:
    async def create(
        self, db, *, organization_id: str, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Epic:
        roadmap_id = data.get("roadmap_id")
        if not roadmap_id and data.get("project_id"):
            from app.models.project import Project

            project = await db.get(Project, data["project_id"])
            if project is not None:
                roadmap_id = project.roadmap_id
        epic = Epic(
            organization_id=organization_id,
            project_id=data.get("project_id"),
            roadmap_id=roadmap_id,
            name=data["name"],
            description=data.get("description"),
            status=data.get("status", "planned"),
            priority=data.get("priority", "medium"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
        )
        db.add(epic)
        await db.flush()
        await self._emit(db, "epic.created", organization_id, actor, ip_address, epic)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="epic.created",
            actor=actor, ip_address=ip_address,
            resource_type="epic", resource_id=epic.id,
            details={"name": epic.name, "project_id": epic.project_id},
        )
        return epic

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], epic: Epic):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={"epic_id": epic.id, "name": epic.name, "project_id": epic.project_id},
        )

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

    async def _validate_ref(self, db, organization_id: str, key: str, value: str):
        from app.models.project import Project, Roadmap

        model = {"project_id": Project, "roadmap_id": Roadmap}.get(key)
        if model is None:
            return
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {key} reference")

    async def update(
        self, db, *, organization_id: str, epic: Epic, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Epic:
        from app.work.guards import apply_editable

        for key in ("project_id", "roadmap_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        if "status" in data and data["status"] != epic.status:
            raise ValueError("Use the start/complete endpoints to change epic status")
        apply_editable(epic, data)
        epic.updated_at = utcnow()
        await db.flush()
        await self._emit(db, "epic.updated", organization_id, actor, ip_address, epic)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="epic.updated",
            actor=actor, ip_address=ip_address,
            resource_type="epic", resource_id=epic.id,
            details={"name": epic.name},
        )
        return epic

    async def start(
        self, db, *, organization_id: str, epic: Epic,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Epic:
        if epic.status != "planned":
            raise ValueError("Only a planned epic can be started")
        epic.status = "in_progress"
        epic.updated_at = utcnow()
        await db.flush()
        await self._emit(db, "epic.started", organization_id, actor, ip_address, epic)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="epic.started",
            actor=actor, ip_address=ip_address,
            resource_type="epic", resource_id=epic.id,
            details={"name": epic.name},
        )
        return epic

    async def complete(
        self, db, *, organization_id: str, epic: Epic,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Epic:
        if epic.status == "completed":
            raise ValueError("Epic is already completed")
        if epic.status not in ("planned", "in_progress"):
            raise ValueError("Only a planned or in-progress epic can be completed")
        from app.work.progress_rollup import rollup_epic

        progress = await rollup_epic(db, organization_id=organization_id, epic_id=epic.id)
        epic.status = "completed"
        epic.progress = progress
        epic.updated_at = utcnow()
        await db.flush()
        await self._emit(db, "epic.completed", organization_id, actor, ip_address, epic)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="epic.completed",
            actor=actor, ip_address=ip_address,
            resource_type="epic", resource_id=epic.id,
            details={"name": epic.name, "progress": progress},
        )
        return epic

    async def delete(
        self, db, *, organization_id: str, epic: Epic,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        from app.services.work_audit import record

        tasks = (
            await db.execute(
                select(func.count(Task.id)).where(Task.organization_id == organization_id, Task.epic_id == epic.id)
            )
        ).scalar() or 0
        if tasks:
            raise ValueError(f"Epic has {tasks} task(s); move or complete them before deleting")
        await record(
            db, organization_id=organization_id, action="epic.deleted",
            actor=actor, ip_address=ip_address,
            resource_type="epic", resource_id=epic.id,
            details={"name": epic.name},
        )
        await self._emit(db, "epic.deleted", organization_id, actor, ip_address, epic)
        await db.delete(epic)


epic_service = EpicService()

