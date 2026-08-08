"""Task dependency service — validation, cycles, and blocking detection (Phase 3)."""

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
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
        return link

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

    async def remove(self, db, *, organization_id: str, task_id: str, depends_on_task_id: str):
        row = await db.execute(
            select(TaskDependency).where(
                TaskDependency.organization_id == organization_id,
                TaskDependency.task_id == task_id,
                TaskDependency.depends_on_task_id == depends_on_task_id,
            )
        )
        link = row.scalar_one_or_none()
        if link:
            await db.delete(link)

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
                out.append({
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "blocked_by": [{"task_id": b.id, "title": b.title, "status": b.status} for b in blockers],
                })
        return out


dependency_service = DependencyService()
