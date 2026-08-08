"""Task engine â€” the heart of the Work Execution Engine (Phase 3)."""

from typing import Any, Optional

from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.task import Task, TaskDependency

VALID_STATUSES = ("backlog", "todo", "in_progress", "review", "blocked", "completed", "archived")


class TaskService:
    async def _validate_ref(self, db, organization_id: str, key: str, value: str):
        from app.models.goal import Goal
        from app.models.project import Epic, Milestone, Project, Sprint

        model = {
            "project_id": Project,
            "epic_id": Epic,
            "milestone_id": Milestone,
            "sprint_id": Sprint,
            "assignee_id": Employee,
            "reporter_id": Employee,
            "parent_task_id": Task,
            "goal_id": Goal,
        }.get(key)
        if model is None:
            return
        obj = await db.get(model, value)
        if obj is None or getattr(obj, "organization_id", None) != organization_id:
            raise ValueError(f"Invalid {key} reference")

    async def create(
        self, db, *, organization_id: str, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Task:
        for key in ("project_id", "epic_id", "milestone_id", "sprint_id", "assignee_id", "reporter_id", "parent_task_id", "goal_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        task = Task(
            organization_id=organization_id,
            project_id=data.get("project_id"),
            epic_id=data.get("epic_id"),
            milestone_id=data.get("milestone_id"),
            sprint_id=data.get("sprint_id"),
            parent_task_id=data.get("parent_task_id"),
            title=data["title"],
            description=data.get("description"),
            status=data.get("status", "backlog"),
            priority=data.get("priority", "medium"),
            assignee_id=data.get("assignee_id"),
            reporter_id=data.get("reporter_id") or (actor.id if actor else None),
            estimate_hours=data.get("estimate_hours"),
            start_date=data.get("start_date"),
            due_date=data.get("due_date"),
            progress=data.get("progress", 0),
        )
        db.add(task)
        await db.flush()
        await self._emit(db, "task.created", organization_id, actor, ip_address, task)
        await self._alert_assigned(db, organization_id, task, actor)
        return task

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], task: Task):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={
                "task_id": task.id, "title": task.title,
                "project_id": task.project_id, "status": task.status,
                "assignee_id": task.assignee_id,
            },
        )

    async def get(self, db, *, organization_id: str, task_id: str) -> Optional[Task]:
        row = await db.execute(
            select(Task).where(Task.organization_id == organization_id, Task.id == task_id)
        )
        task = row.scalar_one_or_none()
        if task:
            await self._hydrate_one(db, organization_id, task)
        return task

    async def _hydrate_one(self, db, organization_id, task):
        if task.assignee_id:
            emp = await db.get(Employee, task.assignee_id)
            task.assignee_name = emp.full_name if emp else None
        if task.reporter_id:
            emp = await db.get(Employee, task.reporter_id)
            task.reporter_name = emp.full_name if emp else None
        blockers = await db.execute(
            select(TaskDependency, Task)
            .join(Task, Task.id == TaskDependency.depends_on_task_id)
            .where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task.id,
            )
        )
        task.dependencies = [
            {"id": d.id, "task_id": dep.id, "title": dep.title, "status": dep.status, "kind": d.kind}
            for d, dep in blockers.all()
        ]
        blocking = await db.execute(
            select(TaskDependency, Task)
            .join(Task, Task.id == TaskDependency.task_id)
            .where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.depends_on_task_id == task.id,
            )
        )
        task.blocking_tasks = [
            {"id": d.id, "task_id": t.id, "title": t.title, "status": t.status, "kind": d.kind}
            for d, t in blocking.all()
        ]

    async def list_all(
        self, db, *, organization_id: str, project_id: Optional[str] = None,
        assignee_id: Optional[str] = None, status: Optional[str] = None,
        priority: Optional[str] = None, search: Optional[str] = None,
        sort: str = "updated", limit: int = 200, include_archived: bool = False,
    ) -> list[Task]:
        stmt = select(Task).where(Task.organization_id == organization_id)
        if project_id:
            stmt = stmt.where(Task.project_id == project_id)
        if assignee_id:
            stmt = stmt.where(Task.assignee_id == assignee_id)
        if status:
            stmt = stmt.where(Task.status == status)
        if priority:
            stmt = stmt.where(Task.priority == priority)
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(or_(func.lower(Task.title).like(pattern), func.lower(Task.description).like(pattern) if Task.description is not None else True))
        if not include_archived:
            stmt = stmt.where(Task.status != "archived")
        order = {
            "updated": desc(Task.updated_at),
            "created": desc(Task.created_at),
            "due": Task.due_date.asc().nulls_last(),
            "priority": Task.priority.desc(),
        }.get(sort, desc(Task.updated_at))
        rows = await db.execute(stmt.order_by(order).limit(limit))
        tasks = list(rows.scalars().all())
        for task in tasks:
            await self._hydrate_one(db, organization_id, task)
        return tasks

    async def update(
        self, db, *, organization_id: str, task: Task, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Task:
        for key in ("project_id", "epic_id", "milestone_id", "sprint_id", "assignee_id", "reporter_id", "parent_task_id", "goal_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        old_status = task.status
        for key, value in data.items():
            if hasattr(task, key) and key not in ("id", "organization_id", "created_at"):
                setattr(task, key, value)
        if task.status == "completed" and old_status != "completed":
            task.completed_at = utcnow()
            task.progress = 100
        elif task.status != "completed":
            task.completed_at = None
        task.updated_at = utcnow()
        await db.flush()
        await self._emit(db, "task.updated", organization_id, actor, ip_address, task)
        if task.status == "completed" and old_status != "completed":
            await self._emit(db, "task.completed", organization_id, actor, ip_address, task)
            await self._alert_completed(db, organization_id, task, actor)
        if "assignee_id" in data and task.assignee_id:
            await self._alert_assigned(db, organization_id, task, actor)
        return task

    async def transition(
        self, db, *, organization_id: str, task: Task, status: str,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> Task:
        if status not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {status}")
        if status == "blocked":
            blockers = await db.execute(
                select(Task).join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
                .where(
                    TaskDependency.organization_id == organization_id,
                    TaskDependency.task_id == task.id,
                    Task.status != "completed",
                )
            )
            if blockers.scalars().all():
                await self._emit(db, "task.blocked", organization_id, actor, ip_address, task)
        return await self.update(
            db, organization_id=organization_id, task=task, data={"status": status},
            actor=actor, ip_address=ip_address,
        )

    async def delete(self, db, *, organization_id: str, task: Task):
        await db.delete(task)

    async def _alert_assigned(self, db, organization_id: str, task: Task, actor: Optional[Employee]):
        if not task.assignee_id:
            return
        if actor and task.assignee_id == actor.id:
            return
        from app.services.work_alerts import notify_employee

        await notify_employee(
            db,
            organization_id=organization_id,
            employee_id=task.assignee_id,
            type="task.assigned",
            title=f"Task assigned to you: {task.title}",
            body=f"Status: {task.status}" + (f" · Due {task.due_date.isoformat()}" if task.due_date else ""),
            actor_id=actor.user_id if actor else None,
            entity_type="task",
            entity_id=task.id,
            link=f"/tasks/{task.id}",
            metadata={"project_id": task.project_id},
        )

    async def _alert_completed(self, db, organization_id: str, task: Task, actor: Optional[Employee]):
        from app.services.work_alerts import notify_employee

        await notify_employee(
            db,
            organization_id=organization_id,
            employee_id=task.reporter_id,
            type="task.completed",
            title=f"Task completed: {task.title}",
            body="The task you reported has been marked complete.",
            actor_id=actor.user_id if actor else None,
            entity_type="task",
            entity_id=task.id,
            link=f"/tasks/{task.id}",
            priority="high",
        )


task_service = TaskService()

