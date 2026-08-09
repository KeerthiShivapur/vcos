"""Task dependency service — validation, cycles, and blocking detection (Phase 3)."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.employee import Employee
from app.models.task import Task, TaskDependency

VALID_KINDS = ("finish_to_start", "start_to_start", "finish_to_finish", "blocking", "related")


class DependencyService:
    async def _load(self, db, *, organization_id: str, task_id: str) -> Optional[Task]:
        return (
            await db.execute(
                select(Task).where(Task.organization_id == organization_id, Task.id == task_id)
            )
        ).scalar_one_or_none()

    async def add(
        self, db, *, organization_id: str, task_id: str, depends_on_task_id: str, kind: str = "finish_to_start",
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> TaskDependency:
        if kind not in VALID_KINDS:
            raise ValueError(f"Invalid dependency kind: {kind}")
        task = await self._load(db, organization_id=organization_id, task_id=task_id)
        if task is None:
            raise ValueError("Task not found")
        dep = await self._load(db, organization_id=organization_id, task_id=depends_on_task_id)
        if dep is None:
            raise ValueError("Dependency task not found")
        if task_id == depends_on_task_id:
            raise ValueError("A task cannot depend on itself")
        exists = await db.execute(
            select(TaskDependency).where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task_id,
                TaskDependency.depends_on_task_id == depends_on_task_id,
            )
        )
        if exists.scalar_one_or_none():
            raise ValueError("Dependency already exists")
        if await self._would_cycle(db, organization_id=organization_id, task_id=task_id, target=depends_on_task_id):
            raise ValueError("Dependency would create a cycle")
        link = TaskDependency(
            organization_id=organization_id,
            task_id=task_id,
            depends_on_task_id=depends_on_task_id,
            kind=kind,
            created_at=utcnow(),
        )
        db.add(link)
        await db.flush()
        await self._emit(db, "dependency.added", organization_id, actor, ip_address, task_id, depends_on_task_id, kind)
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="dependency.added",
            actor=actor, ip_address=ip_address,
            resource_type="task", resource_id=task_id,
            details={"depends_on_task_id": depends_on_task_id, "kind": kind},
        )
        return link

    async def _emit(self, db, name: str, organization_id: str, actor: Optional[Employee], ip: Optional[str],
                    task_id: str, depends_on_task_id: str, kind: Optional[str] = None):
        from app.services.event_service import event_service

        await event_service.emit(
            db, name=name, actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={"task_id": task_id, "depends_on_task_id": depends_on_task_id, "kind": kind},
        )

    async def _would_cycle(self, db, *, organization_id: str, task_id: str, target: str) -> bool:
        """True if adding task_id -> target would create a cycle (target already reaches task_id)."""
        visited: set[str] = set()
        stack = [target]
        while stack:
            current = stack.pop()
            if current == task_id:
                return True
            if current in visited:
                continue
            visited.add(current)
            rows = await db.execute(
                select(TaskDependency.depends_on_task_id).where(
                    TaskDependency.organization_id == organization_id,
                    TaskDependency.task_id == current,
                )
            )
            stack.extend(rows.scalars().all())
        return False

    async def unsatisfied_blockers(
        self, db, *, organization_id: str, task_id: str, kinds: Optional[tuple[str, ...]] = None,
    ) -> list[Task]:
        """Incomplete dependencies that still stand in the way (default: blocking kinds)."""
        rows = await db.execute(
            select(Task)
            .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
            .where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task_id,
                TaskDependency.kind.in_(kinds or ("blocking", "finish_to_start")),
                Task.status != "completed",
            )
        )
        return list(rows.scalars().all())

    async def remove(
        self, db, *, organization_id: str, task_id: str, depends_on_task_id: str,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        row = await db.execute(
            select(TaskDependency).where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task_id,
                TaskDependency.depends_on_task_id == depends_on_task_id,
            )
        )
        link = row.scalar_one_or_none()
        if link:
            await self._emit(db, "dependency.removed", organization_id, actor, ip_address, task_id, depends_on_task_id)
            from app.services.work_audit import record

            await record(
                db, organization_id=organization_id, action="dependency.removed",
                actor=actor, ip_address=ip_address,
                resource_type="task", resource_id=task_id,
                details={"depends_on_task_id": depends_on_task_id},
            )
            await db.delete(link)
            dependent = await self._load(db, organization_id=organization_id, task_id=task_id)
            if dependent is not None and dependent.status == "blocked":
                remaining = await self.unsatisfied_blockers(
                    db, organization_id=organization_id, task_id=task_id
                )
                if not remaining:
                    await self._unblock(db, organization_id=organization_id, task=dependent,
                                        actor=actor, ip_address=ip_address)

    async def _unblock(
        self, db, *, organization_id: str, task: Task,
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ):
        """Move a blocked task back to todo and broadcast the unblocking."""
        from app.core.timeutils import utcnow

        task.status = "todo"
        task.updated_at = utcnow()
        await db.flush()
        from app.services.event_service import event_service

        await event_service.emit(
            db, name="task.unblocked", actor_id=actor.user_id if actor else None,
            organization_id=organization_id,
            payload={"task_id": task.id, "title": task.title, "assignee_id": task.assignee_id},
        )
        from app.services.work_audit import record

        await record(
            db, organization_id=organization_id, action="task.unblocked",
            actor=actor, ip_address=ip_address,
            resource_type="task", resource_id=task.id,
            details={"title": task.title, "status": "todo"},
        )
        if task.assignee_id:
            from app.services.work_alerts import notify_employee

            await notify_employee(
                db, organization_id=organization_id,
                employee_id=task.assignee_id,
                type="task.unblocked",
                title=f"Task unblocked: {task.title}",
                body="All blocking dependencies are now complete.",
                actor_id=actor.user_id if actor else None,
                entity_type="task", entity_id=task.id,
                link=f"/tasks/{task.id}",
                priority="normal",
            )

    async def sync(
        self, db, *, organization_id: str, task_id: str,
        dependencies: list[dict],
        actor: Optional[Employee] = None, ip_address: Optional[str] = None,
    ) -> list[dict]:
        """Atomically replace the dependency set of a task."""
        task = await self._load(db, organization_id=organization_id, task_id=task_id)
        if task is None:
            raise ValueError("Task not found")
        desired = {(d["depends_on_task_id"], d.get("kind", "finish_to_start")) for d in dependencies}
        existing = (
            await db.execute(
                select(TaskDependency).where(
                    TaskDependency.organization_id == organization_id,
                    TaskDependency.task_id == task_id,
                )
            )
        ).scalars().all()
        keep = set()
        for link in existing:
            if (link.depends_on_task_id, link.kind) not in desired:
                await self.remove(
                    db, organization_id=organization_id, task_id=task_id,
                    depends_on_task_id=link.depends_on_task_id,
                    actor=actor, ip_address=ip_address,
                )
            else:
                keep.add(link.depends_on_task_id)
        for d in dependencies:
            if d["depends_on_task_id"] in keep:
                continue
            try:
                await self.add(
                    db, organization_id=organization_id, task_id=task_id,
                    depends_on_task_id=d["depends_on_task_id"],
                    kind=d.get("kind", "finish_to_start"),
                    actor=actor, ip_address=ip_address,
                )
            except ValueError as exc:
                raise ValueError(f"Invalid dependency {d.get('depends_on_task_id')}: {exc}") from exc
        return await self.dependencies(db, organization_id=organization_id, task_id=task_id)

    async def critical_path(
        self, db, *, organization_id: str, project_id: Optional[str] = None,
    ) -> dict:
        """Longest weighted chain through the dependency graph (weight = estimate hours, min 1).

        A task's duration is its own estimate; the chain accumulates the
        estimates of everything that must happen before it can finish.
        """
        tasks = (await db.execute(
            select(Task).where(
                Task.organization_id == organization_id,
                Task.status != "archived",
                *( (Task.project_id == project_id,) if project_id else () ),
            )
        )).scalars().all()
        by_id = {t.id: t for t in tasks}
        links = (await db.execute(
            select(TaskDependency).where(TaskDependency.organization_id == organization_id)
        )).scalars().all()
        depends_on: dict[str, list[str]] = {}
        waited_for: dict[str, list[str]] = {}
        for link in links:
            if link.task_id in by_id and link.depends_on_task_id in by_id:
                depends_on.setdefault(link.task_id, []).append(link.depends_on_task_id)
                waited_for.setdefault(link.depends_on_task_id, []).append(link.task_id)

        memo: dict[str, tuple[float, list[str]]] = {}

        def _longest(node: str) -> tuple[float, list[str]]:
            if node in memo:
                return memo[node]
            weight = max(by_id[node].estimate_hours or 0, 1.0)
            best_dur, best_path = 0.0, []
            for dependent in waited_for.get(node, []):
                dur, path = _longest(dependent)
                if dur > best_dur:
                    best_dur, best_path = dur, [dependent] + path
            memo[node] = (weight + best_dur, best_path)
            return memo[node]

        best_node, best_dur, best_path = None, 0.0, []
        for t in tasks:
            dur, path = _longest(t.id)
            if dur > best_dur:
                best_node, best_dur, best_path = t.id, dur, path
        path_ids = ([best_node] + best_path) if best_node else []
        return {
            "total_hours": round(best_dur, 1) if path_ids else 0.0,
            "task_ids": path_ids,
            "path": [
                {"task_id": t_id, "title": by_id[t_id].title, "estimate_hours": by_id[t_id].estimate_hours}
                for t_id in path_ids
            ],
            "critical_task_ids": set(path_ids),
        }

    async def ready_to_start(
        self, db, *, organization_id: str, project_id: Optional[str] = None, limit: int = 50,
    ) -> list[dict]:
        """Tasks whose dependencies are satisfied and that are not yet started."""
        stmt = select(Task).where(
            Task.organization_id == organization_id,
            Task.status.in_(("backlog", "todo")),
        )
        if project_id:
            stmt = stmt.where(Task.project_id == project_id)
        rows = await db.execute(stmt)
        out = []
        for task in rows.scalars().all():
            if not await self.unsatisfied_blockers(db, organization_id=organization_id, task_id=task.id):
                out.append({
                    "task_id": task.id, "title": task.title, "priority": task.priority,
                    "due_date": task.due_date, "project_id": task.project_id,
                })
            if len(out) >= limit:
                break
        out.sort(key=lambda t: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(t["priority"], 9))
        return out

    async def get(self, db, *, organization_id: str, dependency_id: str) -> Optional[TaskDependency]:
        return (
            await db.execute(
                select(TaskDependency).where(
                    TaskDependency.organization_id == organization_id,
                    TaskDependency.id == dependency_id,
                )
            )
        ).scalar_one_or_none()

    async def dependencies(self, db, *, organization_id: str, task_id: str) -> list[dict]:
        """Dependencies of a task, hydrated with the depends-on title."""
        rows = await db.execute(
            select(TaskDependency, Task)
            .join(Task, Task.id == TaskDependency.depends_on_task_id)
            .where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task_id,
            )
        )
        return [
            {
                "id": d.id,
                "task_id": d.task_id,
                "depends_on_task_id": d.depends_on_task_id,
                "depends_on_title": dep.title,
                "kind": d.kind,
                "created_at": d.created_at,
            }
            for d, dep in rows.all()
        ]

    async def blockers_for(self, db, *, organization_id: str, task_id: str) -> list[Task]:
        rows = await db.execute(
            select(Task)
            .join(TaskDependency, TaskDependency.depends_on_task_id == Task.id)
            .where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task_id,
                Task.status != "completed",
            )
        )
        return list(rows.scalars().all())

    async def is_blocked(self, db, *, organization_id: str, task_id: str) -> bool:
        return bool(await self.blockers_for(db, organization_id=organization_id, task_id=task_id))

    async def blocked_tasks(self, db, *, organization_id: str, project_id: Optional[str] = None) -> list[dict]:
        """Detect tasks whose uncompleted dependencies block them."""
        rows = await db.execute(
            select(Task)
            .where(
                Task.organization_id == organization_id,
                Task.status != "completed",
                Task.status != "archived",
            )
        )
        if project_id:
            rows = await db.execute(
                select(Task).where(
                    Task.organization_id == organization_id,
                    Task.project_id == project_id,
                    Task.status != "completed",
                    Task.status != "archived",
                )
            )
        out = []
        for task in rows.scalars().all():
            blockers = await self.blockers_for(db, organization_id=organization_id, task_id=task.id)
            if blockers:
                depth = await self._chain_depth(db, organization_id=organization_id, task_id=task.id)
                out.append({
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "blocked_by": [{"task_id": b.id, "title": b.title, "status": b.status} for b in blockers],
                    "chain_depth": depth,
                    "deeply_blocked": depth > 0,
                })
        return out

    async def _chain_depth(self, db, *, organization_id: str, task_id: str) -> int:
        """How many consecutive blocked links stand between this task and progress."""
        depth = 0
        level = [task_id]
        visited = {task_id}
        while level:
            nxt = []
            for current in level:
                blockers = await self.blockers_for(db, organization_id=organization_id, task_id=current)
                for b in blockers:
                    if b.status == "blocked" and b.id not in visited:
                        visited.add(b.id)
                        nxt.append(b.id)
            if nxt:
                depth += 1
                level = nxt
            else:
                level = []
        return depth


dependency_service = DependencyService()
