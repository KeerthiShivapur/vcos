"""Roadmap service (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.project import Epic, Milestone, Project, Roadmap


class RoadmapService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
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
        await self._emit(db, "roadmap.created", organization_id, actor, ip_address, roadmap)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="roadmap.created",
            actor=actor, ip_address=ip_address,
            resource_type="roadmap", resource_id=roadmap.id,
            details={"name": roadmap.name},
        )
        return roadmap

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], roadmap: Roadmap):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={"roadmap_id": roadmap.id, "name": roadmap.name, "owner_id": roadmap.owner_id},
        )

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

    async def _validate_ref(self, db, organization_id: str, key: str, value: str):
        from app.models.employee import Employee

        model = {"owner_id": Employee}.get(key)
        if model is None:
            return
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {key} reference")

    async def update(
        self, db, *, organization_id: str, roadmap: Roadmap, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Roadmap:
        from app.work.guards import apply_editable

        if data.get("owner_id"):
            await self._validate_ref(db, organization_id, "owner_id", data["owner_id"])
        apply_editable(roadmap, data)
        roadmap.updated_at = utcnow()
        await db.flush()
        await self._emit(db, "roadmap.updated", organization_id, actor, ip_address, roadmap)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="roadmap.updated",
            actor=actor, ip_address=ip_address,
            resource_type="roadmap", resource_id=roadmap.id,
            details={"name": roadmap.name},
        )
        return roadmap

    async def lifecycle(
        self, db, *, organization_id: str, roadmap: Roadmap, action: str,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Roadmap:
        """activate: draft|archived -> active · complete: active -> completed · archive: completed -> archived."""
        allowed = {
            "activate": {"draft", "archived"},
            "complete": {"active"},
            "archive": {"completed"},
        }.get(action)
        if allowed is None:
            raise ValueError(f"Invalid lifecycle action: {action}")
        if roadmap.status not in allowed:
            raise ValueError(f"Cannot {action} a roadmap in status {roadmap.status}")
        new_status = {"activate": "active", "complete": "completed", "archive": "archived"}[action]
        event_name = {"activate": "roadmap.started", "complete": "roadmap.completed", "archive": "roadmap.archived"}[action]
        roadmap.status = new_status
        roadmap.updated_at = utcnow()
        if action == "complete":
            roadmap.progress = 100
        elif action == "activate":
            from app.work.progress_rollup import rollup_roadmap

            await rollup_roadmap(db, organization_id=organization_id, roadmap_id=roadmap.id)
        await db.flush()
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action=event_name,
            actor=actor, ip_address=ip_address,
            resource_type="roadmap", resource_id=roadmap.id,
            details={"name": roadmap.name, "from": roadmap.status, "to": new_status},
        )
        await self._emit(db, event_name, organization_id, actor, ip_address, roadmap)
        return roadmap

    async def detail(
        self, db, *, organization_id: str, roadmap_id: str,
    ) -> Optional[dict]:
        """Roadmap with its epics, linked projects and task pressure."""
        roadmap = await self.get(db, organization_id=organization_id, roadmap_id=roadmap_id)
        if roadmap is None:
            return None
        from sqlalchemy import func

        from app.models.task import Task

        epics = (
            await db.execute(
                select(Epic).where(Epic.organization_id == organization_id, Epic.roadmap_id == roadmap_id)
                .order_by(Epic.end_date.asc().nulls_last())
            )
        ).scalars().all()
        epic_ids = [e.id for e in epics]
        task_counts: dict[str, dict[str, int]] = {}
        if epic_ids:
            rows = await db.execute(
                select(Task.epic_id, Task.status, func.count(Task.id))
                .where(Task.organization_id == organization_id, Task.epic_id.in_(epic_ids))
                .group_by(Task.epic_id, Task.status)
            )
            for epic_id, status, count in rows.all():
                task_counts.setdefault(epic_id, {})[status] = count
        projects = (
            await db.execute(
                select(Project).where(Project.organization_id == organization_id, Project.roadmap_id == roadmap_id)
            )
        ).scalars().all()
        owner = None
        if roadmap.owner_id:
            owner = await db.get(Employee, roadmap.owner_id)
        return {
            "roadmap": {
                "id": roadmap.id, "name": roadmap.name, "description": roadmap.description,
                "owner_id": roadmap.owner_id, "owner_name": owner.full_name if owner else None,
                "timeframe": roadmap.timeframe, "status": roadmap.status,
                "progress": roadmap.progress,
                "created_at": roadmap.created_at, "updated_at": roadmap.updated_at,
            },
            "epics": [
                {
                    "id": e.id, "name": e.name, "status": e.status, "priority": e.priority,
                    "progress": e.progress, "start_date": e.start_date, "end_date": e.end_date,
                    "project_id": e.project_id,
                    "tasks_total": sum(task_counts.get(e.id, {}).values()),
                    "tasks_completed": task_counts.get(e.id, {}).get("completed", 0),
                    "tasks_blocked": task_counts.get(e.id, {}).get("blocked", 0),
                }
                for e in epics
            ],
            "projects": [
                {
                    "id": p.id, "code": p.code, "name": p.name, "status": p.status,
                    "progress": p.progress, "health": p.health,
                }
                for p in projects
            ],
        }

    async def delete(
        self, db, *, organization_id: str, roadmap: Roadmap,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        from app.services.work_audit import record

        from sqlalchemy import func

        linked = (
            await db.execute(
                select(func.count(Project.id)).where(
                    Project.organization_id == organization_id, Project.roadmap_id == roadmap.id
                )
            )
        ).scalar() or 0
        if linked:
            raise ValueError(
                f"Roadmap has {linked} linked project(s); unlink them before deleting"
            )
        await record(
            db, organization_id=organization_id, action="roadmap.deleted",
            actor=actor, ip_address=ip_address,
            resource_type="roadmap", resource_id=roadmap.id,
            details={"name": roadmap.name},
        )
        await self._emit(db, "roadmap.deleted", organization_id, actor, ip_address, roadmap)
        await db.delete(roadmap)


roadmap_service = RoadmapService()

