"""Project service â€” intelligent workspaces (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.project import Milestone, Project, ProjectMember, ProjectTimeline  # noqa: F401
from app.models.task import Task as TaskModel
from app.work.timeline_service import timeline_service

TASK_WEIGHTS = {"completed": 1.0, "review": 0.8, "in_progress": 0.5, "blocked": 0.3, "todo": 0.1, "backlog": 0.0, "archived": 0.0}


class ProjectService:
    async def _validate_ref(self, db: AsyncSession, organization_id: str, key: str, value: str):
        from app.models.department import Department
        from app.models.team import Team
        from app.models.project import Roadmap

        model = {
            "owner_id": Employee,
            "department_id": Department,
            "team_id": Team,
            "roadmap_id": Roadmap,
        }.get(key)
        if model is None:
            return
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {key} reference")

    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        data: dict[str, Any],
        actor: Optional[Employee] = None,
        ip_address: Optional[str] = None,
    ) -> Project:
        for key in ("owner_id", "department_id", "team_id", "roadmap_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        project = Project(
            organization_id=organization_id,
            code=data.get("code") or f"PRJ-{utcnow().strftime('%y%m%d%H%M%S')}",
            name=data["name"],
            description=data.get("description"),
            status=data.get("status", "draft"),
            priority=data.get("priority", "medium"),
            owner_id=data.get("owner_id"),
            department_id=data.get("department_id"),
            team_id=data.get("team_id"),
            roadmap_id=data.get("roadmap_id"),
            start_date=data.get("start_date"),
            end_date=data.get("end_date"),
            budget=data.get("budget"),
            tags=data.get("tags"),
        )
        db.add(project)
        await db.flush()
        await timeline_service.add(
            db, organization_id=organization_id, project_id=project.id,
            kind="project.created", title="Project created", description=project.name,
            meta={"code": project.code},
        )
        await self._emit(db, "project.created", organization_id, actor, ip_address,
                         {"project_id": project.id, "name": project.name, "code": project.code})
        if data.get("owner_id"):
            await self.add_member(db, organization_id=organization_id, project_id=project.id,
                                  employee_id=data["owner_id"], role="owner")
        return project

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], payload: dict):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id, payload=payload,
        )

    async def get(self, db: AsyncSession, *, organization_id: str, project_id: str) -> Optional[Project]:
        row = await db.execute(
            select(Project).where(
                Project.organization_id == organization_id, Project.id == project_id
            )
        )
        project = row.scalar_one_or_none()
        if project:
            project.owner_name = None
            project.department_name = None
            project.team_name = None
            project.members_count = (
                await db.execute(
                    select(func.count(ProjectMember.id)).where(
                        ProjectMember.organization_id == organization_id,
                        ProjectMember.project_id == project.id,
                    )
                )
            ).scalar() or 0
            project.tasks_count = (
                await db.execute(
                    select(func.count(TaskModel.id)).where(
                        TaskModel.organization_id == organization_id,
                        TaskModel.project_id == project.id,
                    )
                )
            ).scalar() or 0
            project.completed_count = (
                await db.execute(
                    select(func.count(TaskModel.id)).where(
                        TaskModel.organization_id == organization_id,
                        TaskModel.project_id == project.id,
                        TaskModel.status == "completed",
                    )
                )
            ).scalar() or 0
            if project.owner_id:
                owner = await db.get(Employee, project.owner_id)
                project.owner_name = owner.full_name if owner else None
            if project.department_id:
                from app.models.department import Department

                dept = await db.get(Department, project.department_id)
                project.department_name = dept.name if dept else None
            if project.team_id:
                from app.models.team import Team

                team = await db.get(Team, project.team_id)
                project.team_name = team.name if team else None
        return project

    async def list_all(
        self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None,
        search: Optional[str] = None, sort: str = "updated", limit: int = 200,
    ) -> list[Project]:
        stmt = select(Project).where(Project.organization_id == organization_id)
        if status:
            stmt = stmt.where(Project.status == status)
        if search:
            pattern = f"%{search.lower()}%"
            from sqlalchemy import or_

            stmt = stmt.where(
                or_(
                    func.lower(Project.name).like(pattern),
                    func.lower(Project.code).like(pattern),
                    func.lower(Project.description).like(pattern) if Project.description is not None else True,
                )
            )
        order = {
            "updated": desc(Project.updated_at),
            "created": desc(Project.created_at),
            "name": Project.name.asc(),
            "progress": desc(Project.progress),
        }.get(sort, desc(Project.updated_at))
        rows = await db.execute(stmt.order_by(order).limit(limit))
        projects = list(rows.scalars().all())
        return await self._hydrate(db, organization_id, projects)

    async def _hydrate(self, db, organization_id, projects):
        from app.models.department import Department
        from app.models.team import Team

        ids = [p.id for p in projects]
        member_counts = dict(
            (await db.execute(
                select(ProjectMember.project_id, func.count(ProjectMember.id))
                .where(ProjectMember.organization_id == organization_id, ProjectMember.project_id.in_(ids))
                .group_by(ProjectMember.project_id)
            )).all()
        )
        task_counts = dict(
            (await db.execute(
                select(TaskModel.project_id, func.count(TaskModel.id))
                .where(TaskModel.organization_id == organization_id, TaskModel.project_id.in_(ids))
                .group_by(TaskModel.project_id)
            )).all()
        )
        completed = dict(
            (await db.execute(
                select(TaskModel.project_id, func.count(TaskModel.id))
                .where(
                    TaskModel.organization_id == organization_id,
                    TaskModel.project_id.in_(ids),
                    TaskModel.status == "completed",
                )
                .group_by(TaskModel.project_id)
            )).all()
        )
        owner_ids = [p.owner_id for p in projects if p.owner_id]
        dept_ids = [p.department_id for p in projects if p.department_id]
        team_ids = [p.team_id for p in projects if p.team_id]
        owners = {}
        if owner_ids:
            owners = {e.id: e for e in (await db.execute(select(Employee).where(Employee.id.in_(owner_ids)))).scalars().all()}
        depts = {}
        if dept_ids:
            depts = {d.id: d.name for d in (await db.execute(select(Department).where(Department.id.in_(dept_ids)))).scalars().all()}
        teams = {}
        if team_ids:
            teams = {t.id: t.name for t in (await db.execute(select(Team).where(Team.id.in_(team_ids)))).scalars().all()}
        for p in projects:
            p.members_count = member_counts.get(p.id, 0)
            p.tasks_count = task_counts.get(p.id, 0)
            total = task_counts.get(p.id, 0)
            p.completed_count = completed.get(p.id, 0)
            p.progress = int((completed.get(p.id, 0) / total) * 100) if total else p.progress or 0
            p.owner_name = owners[p.owner_id].full_name if p.owner_id and owners.get(p.owner_id) else None
            p.department_name = depts.get(p.department_id)
            p.team_name = teams.get(p.team_id)
        return projects

    async def update(
        self, db: AsyncSession, *, organization_id: str, project: Project,
        data: dict[str, Any], actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Project:
        for key, value in data.items():
            if hasattr(project, key):
                setattr(project, key, value)
        project.updated_at = utcnow()
        await db.flush()
        await timeline_service.add(
            db, organization_id=organization_id, project_id=project.id,
            kind="project.updated", title="Project updated", description=project.name,
        )
        await self._emit(db, "project.updated", organization_id, actor, ip_address,
                         {"project_id": project.id, "name": project.name})
        return project

    async def add_member(
        self, db: AsyncSession, *, organization_id: str, project_id: str,
        employee_id: str, role: Optional[str] = None,
    ) -> ProjectMember:
        exists = await db.execute(
            select(ProjectMember).where(
                ProjectMember.organization_id == organization_id,
                ProjectMember.project_id == project_id,
                ProjectMember.employee_id == employee_id,
            )
        )
        if exists.scalar_one_or_none():
            raise ValueError("Employee is already a project member")
        member = ProjectMember(
            organization_id=organization_id, project_id=project_id,
            employee_id=employee_id, role=role, joined_at=utcnow(),
        )
        db.add(member)
        await db.flush()
        await timeline_service.add(
            db, organization_id=organization_id, project_id=project_id,
            kind="project.member_added", title="Member added",
            description=employee_id, meta={"employee_id": employee_id, "role": role},
        )
        return member

    async def remove_member(
        self, db: AsyncSession, *, organization_id: str, project_id: str, employee_id: str,
    ):
        row = await db.execute(
            select(ProjectMember).where(
                ProjectMember.organization_id == organization_id,
                ProjectMember.project_id == project_id,
                ProjectMember.employee_id == employee_id,
            )
        )
        member = row.scalar_one_or_none()
        if member:
            await db.delete(member)

    async def members(self, db: AsyncSession, *, organization_id: str, project_id: str) -> list[dict]:
        rows = await db.execute(
            select(ProjectMember, Employee)
            .join(Employee, Employee.id == ProjectMember.employee_id)
            .where(ProjectMember.organization_id == organization_id, ProjectMember.project_id == project_id)
        )
        out = []
        for member, emp in rows.all():
            out.append({
                "id": member.id,
                "employee_id": member.employee_id,
                "name": emp.full_name,
                "designation": emp.designation,
                "avatar_url": emp.avatar_url,
                "role": member.role,
                "joined_at": member.joined_at,
            })
        return out

    async def stats(self, db: AsyncSession, *, organization_id: str, project_id: str) -> dict[str, Any]:
        counts = dict(
            (await db.execute(
                select(TaskModel.status, func.count(TaskModel.id))
                .where(TaskModel.organization_id == organization_id, TaskModel.project_id == project_id)
                .group_by(TaskModel.status)
            )).all()
        )
        total = sum(counts.values())
        completed = counts.get("completed", 0)
        blocked = counts.get("blocked", 0)
        in_progress = counts.get("in_progress", 0)
        milestones = (
            await db.execute(
                select(func.count(Milestone.id))
                .where(Milestone.organization_id == organization_id, Milestone.project_id == project_id)
            )
        ).scalar() or 0
        milestones_done = (
            await db.execute(
                select(func.count(Milestone.id))
                .where(
                    Milestone.organization_id == organization_id,
                    Milestone.project_id == project_id,
                    Milestone.status == "completed",
                )
            )
        ).scalar() or 0
        return {
            "project_id": project_id,
            "total_tasks": total,
            "completed_tasks": completed,
            "in_progress_tasks": in_progress,
            "blocked_tasks": blocked,
            "progress": int((completed / total) * 100) if total else 0,
            "milestones_total": milestones,
            "milestones_completed": milestones_done,
            "status_breakdown": {k: counts.get(k, 0) for k in ("backlog", "todo", "in_progress", "review", "blocked", "completed")},
        }

    async def timeline(self, db: AsyncSession, *, organization_id: str, project_id: str, limit: int = 100):
        return await timeline_service.list_all(db, organization_id=organization_id, project_id=project_id, limit=limit)

    async def delete(self, db: AsyncSession, *, organization_id: str, project: Project):
        await db.delete(project)


project_service = ProjectService()

