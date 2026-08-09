"""Sprint service (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.project import Sprint
from app.models.task import Task


class SprintService:
    async def create(
        self, db, *, organization_id: str, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Sprint:
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
        await self._emit(db, "sprint.created", organization_id, actor, ip_address, sprint)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="sprint.created",
            actor=actor, ip_address=ip_address,
            resource_type="sprint", resource_id=sprint.id,
            details={"name": sprint.name, "project_id": sprint.project_id},
        )
        return sprint

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], sprint: Sprint):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={"sprint_id": sprint.id, "name": sprint.name, "project_id": sprint.project_id},
        )

    async def _progress(self, db, *, organization_id: str, sprint_id: str) -> int:
        from sqlalchemy import case, func

        total, done = (
            await db.execute(
                select(func.count(Task.id), func.sum(case((Task.status == "completed", 1), else_=0)))
                .where(Task.organization_id == organization_id, Task.sprint_id == sprint_id)
            )
        ).one()
        total = int(total or 0)
        done = int(done or 0)
        if total == 0:
            return 0
        return round(done * 100 / total)

    async def _counts(self, db, *, organization_id: str, sprint_id: str) -> tuple[int, int]:
        total = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id, Task.sprint_id == sprint_id
                )
            )
        ).scalar() or 0
        done = (
            await db.execute(
                select(func.count(Task.id)).where(
                    Task.organization_id == organization_id,
                    Task.sprint_id == sprint_id,
                    Task.status == "completed",
                )
            )
        ).scalar() or 0
        return int(total or 0), int(done or 0)

    async def get(self, db, *, organization_id: str, sprint_id: str) -> Optional[Sprint]:
        sprint = (
            await db.execute(
                select(Sprint).where(Sprint.organization_id == organization_id, Sprint.id == sprint_id)
            )
        ).scalar_one_or_none()
        if sprint is not None:
            total, done = await self._counts(db, organization_id=organization_id, sprint_id=sprint_id)
            sprint.tasks_count = total
            sprint.completed_tasks = done
            if sprint.status == "completed":
                sprint.progress = sprint.progress or 100
            else:
                sprint.progress = await self._progress(
                    db, organization_id=organization_id, sprint_id=sprint_id
                )
        return sprint

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
                if s.status == "completed":
                    s.progress = s.progress or 100
                else:
                    total = int(counts.get(s.id, 0) or 0)
                    done = int(completed.get(s.id, 0) or 0)
                    s.progress = round(done * 100 / total) if total else 0
        return sprints

    async def _validate_ref(self, db, organization_id: str, key: str, value: str):
        from app.models.project import Project

        model = {"project_id": Project}.get(key)
        if model is None:
            return
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {key} reference")

    async def update(
        self, db, *, organization_id: str, sprint: Sprint, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Sprint:
        from app.work.guards import apply_editable

        if data.get("project_id"):
            await self._validate_ref(db, organization_id, "project_id", data["project_id"])
        if "status" in data and data["status"] != sprint.status:
            raise ValueError("Use the start/complete endpoints to change sprint status")
        apply_editable(sprint, data)
        sprint.updated_at = utcnow()
        await self._emit(db, "sprint.updated", organization_id, actor, ip_address, sprint)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="sprint.updated",
            actor=actor, ip_address=ip_address,
            resource_type="sprint", resource_id=sprint.id,
            details={"name": sprint.name},
        )
        return sprint

    async def start(
        self, db, *, organization_id: str, sprint: Sprint,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Sprint:
        if sprint.status != "planned":
            raise ValueError("Only a planned sprint can be started")
        sprint.status = "active"
        sprint.updated_at = utcnow()
        await db.flush()
        if sprint.project_id:
            from app.work.timeline_service import timeline_service

            await timeline_service.add(
                db, organization_id=organization_id, project_id=sprint.project_id,
                kind="sprint.started", title=f"Sprint started: {sprint.name}",
                description=sprint.goal, meta={"sprint_id": sprint.id},
            )
        await self._emit(db, "sprint.started", organization_id, actor, ip_address, sprint)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="sprint.started",
            actor=actor, ip_address=ip_address,
            resource_type="sprint", resource_id=sprint.id,
            details={"name": sprint.name},
        )
        return sprint

    async def complete(
        self, db, *, organization_id: str, sprint: Sprint,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Sprint:
        if sprint.status == "completed":
            raise ValueError("Sprint is already completed")
        if sprint.status not in ("planned", "active"):
            raise ValueError("Only a planned or active sprint can be completed")
        from app.work.progress_rollup import rollup_sprint

        await rollup_sprint(db, organization_id=organization_id, sprint_id=sprint.id)
        unfinished = (
            await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.sprint_id == sprint.id,
                    Task.status != "completed",
                )
            )
        ).scalars().all()
        for task in unfinished:
            task.sprint_id = None
            task.updated_at = utcnow()
        sprint.status = "completed"
        sprint.completed_at = utcnow()
        sprint.updated_at = utcnow()
        await db.flush()
        if sprint.project_id:
            from app.work.timeline_service import timeline_service

            await timeline_service.add(
                db, organization_id=organization_id, project_id=sprint.project_id,
                kind="sprint.completed", title=f"Sprint completed: {sprint.name}",
                description=f"{sprint.progress}% of the sprint work finished"
                if sprint.progress != 100
                else "All sprint work completed",
                meta={"sprint_id": sprint.id, "progress": sprint.progress,
                      "returned_to_backlog": len(unfinished)},
            )
        await self._emit(db, "sprint.completed", organization_id, actor, ip_address, sprint)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="sprint.completed",
            actor=actor, ip_address=ip_address,
            resource_type="sprint", resource_id=sprint.id,
            details={"name": sprint.name, "progress": sprint.progress,
                     "returned_to_backlog": len(unfinished)},
        )
        return sprint

    async def delete(
        self, db, *, organization_id: str, sprint: Sprint,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        from app.services.work_audit import record

        if sprint.status == "active":
            raise ValueError("An active sprint cannot be deleted; complete it first")
        tasks = (
            await db.execute(
                select(Task).where(Task.organization_id == organization_id, Task.sprint_id == sprint.id)
            )
        ).scalars().all()
        for task in tasks:
            task.sprint_id = None
            task.updated_at = utcnow()
        await record(
            db, organization_id=organization_id, action="sprint.deleted",
            actor=actor, ip_address=ip_address,
            resource_type="sprint", resource_id=sprint.id,
            details={"name": sprint.name, "tasks_detached": len(tasks)},
        )
        await db.delete(sprint)


sprint_service = SprintService()

