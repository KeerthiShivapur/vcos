"""Task engine â€” the heart of the Work Execution Engine (Phase 3)."""

from datetime import date
from typing import Any, Optional

from sqlalchemy import String, case, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.task import Task, TaskDependency

VALID_STATUSES = ("backlog", "todo", "in_progress", "review", "blocked", "completed", "archived")


class TaskService:
    async def _validate_ref(self, db, organization_id: str, key: str, value: str):
        from app.models.goal import Goal
        from app.models.knowledge import Decision
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
            "decision_id": Decision,
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
        for key in ("project_id", "epic_id", "milestone_id", "sprint_id", "assignee_id", "reporter_id", "parent_task_id", "goal_id", "decision_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        task = Task(
            organization_id=organization_id,
            project_id=data.get("project_id"),
            epic_id=data.get("epic_id"),
            milestone_id=data.get("milestone_id"),
            sprint_id=data.get("sprint_id"),
            parent_task_id=data.get("parent_task_id"),
            decision_id=data.get("decision_id"),
            goal_id=data.get("goal_id"),
            title=data["title"],
            description=data.get("description"),
            status=data.get("status", "backlog"),
            priority=data.get("priority", "medium"),
            assignee_id=data.get("assignee_id"),
            reporter_id=data.get("reporter_id") or (actor.id if actor else None),
            estimate_hours=data.get("estimate_hours"),
            spent_hours=data.get("spent_hours", 0),
            start_date=data.get("start_date"),
            due_date=data.get("due_date"),
            progress=data.get("progress", 0),
            tags=data.get("tags"),
        )
        db.add(task)
        await db.flush()
        await self._emit(db, "task.created", organization_id, actor, ip_address, task)
        await self._alert_assigned(db, organization_id, task, actor)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="task.created",
            actor=actor, ip_address=ip_address,
            resource_type="task", resource_id=task.id,
            details={"title": task.title, "status": task.status, "project_id": task.project_id},
        )
        return task

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str], task: Task):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={
                "task_id": task.id, "title": task.title,
                "project_id": task.project_id, "status": task.status,
                "assignee_id": task.assignee_id, "parent_task_id": task.parent_task_id,
                "sprint_id": task.sprint_id,
                "decision_id": task.decision_id, "goal_id": task.goal_id,
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
        if task.parent_task_id:
            parent = await db.get(Task, task.parent_task_id)
            task.parent_title = parent.title if parent else None
        if task.goal_id:
            from app.models.goal import Goal

            goal = await db.get(Goal, task.goal_id)
            task.goal_name = goal.name if goal else None
        if task.decision_id:
            from app.models.knowledge import Decision

            decision = await db.get(Decision, task.decision_id)
            if decision is not None:
                task.decision = {
                    "id": decision.id,
                    "title": decision.title,
                    "context": decision.context,
                    "reason": decision.summary or decision.impact or decision.description,
                    "status": decision.status,
                    "decided_at": decision.decided_at,
                    "project_id": decision.project_id,
                }
        subtask_counts = await db.execute(
            select(func.count(Task.id), func.sum(case((Task.status == "completed", 1), else_=0)))
            .where(Task.organization_id == organization_id, Task.parent_task_id == task.id)
        )
        total_subs, done_subs = subtask_counts.one()
        task.subtasks_count = int(total_subs or 0)
        task.subtasks_completed = int(done_subs or 0)
        blockers = await db.execute(
            select(TaskDependency, Task)
            .join(Task, Task.id == TaskDependency.depends_on_task_id)
            .where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task.id,
            )
        )
        dep_rows = list(blockers.all())
        task.dependencies = [
            {"id": d.id, "task_id": dep.id, "title": dep.title, "status": dep.status, "kind": d.kind}
            for d, dep in dep_rows
        ]
        task.blocked_by = [
            {"id": d.id, "task_id": dep.id, "title": dep.title, "status": dep.status, "kind": d.kind}
            for d, dep in dep_rows
            if dep.status != "completed"
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
        assignee_id: Optional[str] = None, reporter_id: Optional[str] = None,
        epic_id: Optional[str] = None, milestone_id: Optional[str] = None,
        sprint_id: Optional[str] = None, parent_task_id: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None, tag: Optional[str] = None,
        search: Optional[str] = None, due_from: Optional[date] = None,
        due_to: Optional[date] = None,
        sort: str = "updated", limit: int = 200, offset: int = 0,
        include_archived: bool = False,
    ) -> list[Task]:
        stmt = select(Task).where(Task.organization_id == organization_id)
        if project_id:
            stmt = stmt.where(Task.project_id == project_id)
        if assignee_id:
            stmt = stmt.where(Task.assignee_id == assignee_id)
        if reporter_id:
            stmt = stmt.where(Task.reporter_id == reporter_id)
        if epic_id:
            stmt = stmt.where(Task.epic_id == epic_id)
        if milestone_id:
            stmt = stmt.where(Task.milestone_id == milestone_id)
        if sprint_id:
            stmt = stmt.where(Task.sprint_id == sprint_id)
        if parent_task_id:
            stmt = stmt.where(Task.parent_task_id == parent_task_id)
        else:
            stmt = stmt.where(Task.parent_task_id.is_(None))
        if due_from:
            stmt = stmt.where(Task.due_date >= due_from)
        if due_to:
            stmt = stmt.where(Task.due_date <= due_to)
        if status:
            stmt = stmt.where(Task.status == status)
        if priority:
            stmt = stmt.where(Task.priority == priority)
        if tag:
            stmt = stmt.where(Task.tags.is_not(None)).where(
                func.cast(Task.tags, String).like(f'%"{tag}"%')
            )
        if search:
            pattern = f"%{search.lower()}%"
            stmt = stmt.where(or_(func.lower(Task.title).like(pattern), func.lower(Task.description).like(pattern) if Task.description is not None else True))
        if not include_archived:
            stmt = stmt.where(Task.status != "archived")
        order = {
            "updated": desc(Task.updated_at),
            "created": desc(Task.created_at),
            "due": Task.due_date.asc().nulls_last(),
            "priority": case(
                (Task.priority == "critical", 4),
                (Task.priority == "high", 3),
                (Task.priority == "medium", 2),
                (Task.priority == "low", 1),
                else_=0,
            ).desc(),
        }.get(sort, desc(Task.updated_at))
        rows = await db.execute(stmt.order_by(order).offset(offset).limit(limit))
        tasks = list(rows.scalars().all())
        for task in tasks:
            await self._hydrate_one(db, organization_id, task)
        return tasks

    async def _unsatisfied_blockers(
        self, db, *, organization_id: str, task: Task, target_status: str,
    ) -> list[Task]:
        """Blockers that must be completed before the target status.

        starting work (in_progress) respects hard `blocking` links;
        completing work respects `blocking` and `finish_to_start` links.
        """
        kinds = {"blocking"} if target_status == "in_progress" else {"blocking", "finish_to_start"}
        rows = await db.execute(
            select(Task)
            .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
            .where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task.id,
                TaskDependency.kind.in_(kinds),
                Task.status != "completed",
            )
        )
        return list(rows.scalars().all())

    async def update(
        self, db, *, organization_id: str, task: Task, data: dict[str, Any],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
        force: bool = False,
    ) -> Task:
        for key in ("project_id", "epic_id", "milestone_id", "sprint_id", "assignee_id", "reporter_id", "parent_task_id", "goal_id", "decision_id"):
            if data.get(key):
                await self._validate_ref(db, organization_id, key, data[key])
        if data.get("parent_task_id"):
            # A task cannot become its own parent or the parent of its ancestor.
            cursor_id: Optional[str] = data["parent_task_id"]
            hops = 0
            while cursor_id:
                if cursor_id == task.id:
                    raise ValueError("Cannot set a task as its own parent (cycle)")
                if hops > 50:
                    break
                row = await db.execute(select(Task.id, Task.parent_task_id).where(
                    Task.organization_id == organization_id, Task.id == cursor_id
                ))
                cursor = row.one_or_none()
                cursor_id = cursor.parent_task_id if cursor else None
                hops += 1
        if data.get("status") in ("in_progress", "completed"):
            blockers = await self._unsatisfied_blockers(
                db, organization_id=organization_id, task=task, target_status=data["status"]
            )
            if blockers and not force:
                raise ValueError(
                    "Task has unsatisfied dependencies: "
                    + ", ".join(b.title for b in blockers[:5])
                    + (f" (+{len(blockers) - 5} more)" if len(blockers) > 5 else "")
                )
        if data.get("status") == "completed" and task.status != "completed" and not force:
            open_subtasks = (
                await db.execute(
                    select(func.count(Task.id)).where(
                        Task.organization_id == organization_id,
                        Task.parent_task_id == task.id,
                        Task.status != "completed",
                    )
                )
            ).scalar() or 0
            if open_subtasks:
                raise ValueError(
                    f"Cannot complete the parent task while {open_subtasks} subtask(s) are still open"
                )
        old_status = task.status
        changes: dict[str, list] = {}
        for key, value in data.items():
            if hasattr(task, key) and key not in ("id", "organization_id", "created_at"):
                changes[key] = [getattr(task, key), value]
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
            if task.decision_id:
                await self._refresh_decision(db, organization_id, task.decision_id, actor, ip_address)
        if "assignee_id" in data and task.assignee_id:
            await self._alert_assigned(db, organization_id, task, actor)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id,
            action=(
                "task.completed" if task.status == "completed" and old_status != "completed" and set(data) == {"status"}
                else "task.transitioned" if old_status != task.status and set(data) == {"status"}
                else "task.updated"
            ),
            actor=actor, ip_address=ip_address,
            resource_type="task", resource_id=task.id,
            details={
                "title": task.title, "status": task.status,
                "old_status": old_status, "project_id": task.project_id,
                "changes": {
                    k: [str(v[0]) if v[0] is not None else None, str(v[1]) if v[1] is not None else None]
                    for k, v in changes.items()
                } if changes else None,
            },
        )
        return task

    async def transition(
        self, db, *, organization_id: str, task: Task, status: str,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
        force: bool = False,
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
        if status != task.status:
            await self._emit(db, "task.transitioned", organization_id, actor, ip_address, task)
        return await self.update(
            db, organization_id=organization_id, task=task, data={"status": status},
            actor=actor, ip_address=ip_address, force=force,
        )

    async def delete(
        self, db, *, organization_id: str, task: Task,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="task.deleted",
            actor=actor, ip_address=ip_address,
            resource_type="task", resource_id=task.id,
            details={"title": task.title, "project_id": task.project_id},
        )
        await self._emit(db, "task.deleted", organization_id, actor, ip_address, task)
        await db.delete(task)

    async def _alert_assigned(self, db, organization_id: str, task: Task, actor: Optional[Employee]):
        if not task.assignee_id:
            return
        if actor and task.assignee_id == actor.id:
            return
        from app.services.work_alerts import notify_employee

        decision_title = None
        if task.decision_id:
            from app.models.knowledge import Decision

            decision = await db.get(Decision, task.decision_id)
            decision_title = decision.title if decision else None
        title = (
            f"Task assigned to you (from decision '{decision_title}'): {task.title}"
            if decision_title
            else f"Task assigned to you: {task.title}"
        )
        body = f"Status: {task.status}" + (f" · Due {task.due_date.isoformat()}" if task.due_date else "")
        if decision_title:
            body += " · This task was created from a follow-up action on the decision."
        await notify_employee(
            db,
            organization_id=organization_id,
            employee_id=task.assignee_id,
            type="task.assigned",
            title=title,
            body=body,
            actor_id=actor.user_id if actor else None,
            entity_type="task",
            entity_id=task.id,
            link=f"/tasks/{task.id}",
            metadata={"project_id": task.project_id, "decision_id": task.decision_id},
        )

    async def _refresh_decision(self, db, organization_id: str, decision_id: str, actor: Optional[Employee], ip_address: Optional[str]):
        """Close the decision → execution loop: when every follow-up task is
        done, the originating decision becomes `implemented`."""
        from app.knowledge.decision_service import decision_service

        await decision_service.refresh_status(
            db, organization_id=organization_id, decision_id=decision_id,
            actor=actor, ip_address=ip_address,
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

