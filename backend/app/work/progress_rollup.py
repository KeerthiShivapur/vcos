"""Progress rollup — project/epic/milestone/roadmap from task reality.

Progress is not typed in; it is derived. Every time work completes, the
affected containers recompute their progress from the tasks underneath them
so managers see numbers that always match execution.
"""

from typing import Optional

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Epic, Milestone, Project, Roadmap, Sprint
from app.models.task import Task


async def _container_progress(db: AsyncSession, *, organization_id: str, filters: dict) -> int:
    """Percent of completed tasks among the container's tasks."""
    stmt = select(func.count(Task.id), func.sum(case((Task.status == "completed", 1), else_=0))).where(
        Task.organization_id == organization_id
    )
    for column, value in filters.items():
        stmt = stmt.where(column == value)
    total, completed = (await db.execute(stmt)).one()
    total = int(total or 0)
    completed = int(completed or 0)
    if total == 0:
        return 0
    return round(completed * 100 / total)


async def rollup_epic(db: AsyncSession, *, organization_id: str, epic_id: str) -> int:
    epic = await db.get(Epic, epic_id)
    if epic is None:
        return 0
    progress = await _container_progress(db, organization_id=organization_id, filters={Task.epic_id: epic_id})
    epic.progress = progress
    await db.flush()
    return progress


async def rollup_milestone(db: AsyncSession, *, organization_id: str, milestone_id: str) -> int:
    milestone = await db.get(Milestone, milestone_id)
    if milestone is None:
        return 0
    progress = await _container_progress(db, organization_id=organization_id, filters={Task.milestone_id: milestone_id})
    milestone.progress = progress
    if progress == 100 and milestone.status != "completed":
        from app.work.milestone_service import milestone_service

        await milestone_service.complete(db, organization_id=organization_id, milestone=milestone)
    await db.flush()
    return progress


async def rollup_project(db: AsyncSession, *, organization_id: str, project_id: str) -> int:
    project = await db.get(Project, project_id)
    if project is None:
        return 0
    tasks_progress = await _container_progress(db, organization_id=organization_id, filters={Task.project_id: project_id})
    milestone_total = (
        await db.execute(
            select(func.count(Milestone.id)).where(
                Milestone.organization_id == organization_id, Milestone.project_id == project_id
            )
        )
    ).scalar() or 0
    milestone_done = (
        await db.execute(
            select(func.count(Milestone.id)).where(
                Milestone.organization_id == organization_id,
                Milestone.project_id == project_id,
                Milestone.status == "completed",
            )
        )
    ).scalar() or 0
    if milestone_total:
        progress = round(tasks_progress * 0.7 + (milestone_done * 100 / milestone_total) * 0.3)
    else:
        progress = tasks_progress
    project.progress = progress
    await db.flush()
    return progress


async def rollup_roadmap(db: AsyncSession, *, organization_id: str, roadmap_id: str) -> int:
    roadmap = await db.get(Roadmap, roadmap_id)
    if roadmap is None:
        return 0
    epics = (
        await db.execute(
            select(Epic).where(Epic.organization_id == organization_id, Epic.roadmap_id == roadmap_id)
        )
    ).scalars().all()
    if epics:
        progress = round(sum(e.progress or 0 for e in epics) / len(epics))
    else:
        projects = (
            await db.execute(
                select(Project).where(
                    Project.organization_id == organization_id, Project.roadmap_id == roadmap_id
                )
            )
        ).scalars().all()
        progress = round(sum(p.progress or 0 for p in projects) / len(projects)) if projects else 0
    roadmap.progress = progress
    await db.flush()
    return progress


async def rollup_sprint(db: AsyncSession, *, organization_id: str, sprint_id: str) -> int:
    sprint = await db.get(Sprint, sprint_id)
    if sprint is None:
        return 0
    progress = await _container_progress(db, organization_id=organization_id, filters={Task.sprint_id: sprint_id})
    sprint.progress = progress
    await db.flush()
    return progress


async def rollup_parent(db: AsyncSession, *, organization_id: str, parent_id: str) -> int:
    """Parent progress is derived from its subtasks when any exist."""
    parent = await db.get(Task, parent_id)
    if parent is None:
        return 0
    total, done = (
        await db.execute(
            select(
                func.count(Task.id),
                func.sum(case((Task.status == "completed", 1), else_=0)),
            ).where(Task.organization_id == organization_id, Task.parent_task_id == parent_id)
        )
    ).one()
    total = int(total or 0)
    done = int(done or 0)
    if total == 0:
        return parent.progress or 0
    progress = round(done * 100 / total)
    parent.progress = progress
    await db.flush()
    return progress


async def rollup_for_task(
    db: AsyncSession, *, organization_id: str, task_id: str,
) -> dict[str, Optional[int]]:
    """Roll up every container a task belongs to (task must still exist)."""
    task = await db.get(Task, task_id)
    if task is None:
        return {}
    result: dict[str, Optional[int]] = {}
    if task.epic_id:
        result["epic"] = await rollup_epic(db, organization_id=organization_id, epic_id=task.epic_id)
    if task.milestone_id:
        result["milestone"] = await rollup_milestone(
            db, organization_id=organization_id, milestone_id=task.milestone_id
        )
    if task.project_id:
        result["project"] = await rollup_project(
            db, organization_id=organization_id, project_id=task.project_id
        )
    if task.sprint_id:
        result["sprint"] = await rollup_sprint(
            db, organization_id=organization_id, sprint_id=task.sprint_id
        )
    if task.parent_task_id:
        result["parent"] = await rollup_parent(
            db, organization_id=organization_id, parent_id=task.parent_task_id
        )
    return result


async def rollup_roadmap_of_project(db: AsyncSession, *, organization_id: str, project_id: str) -> Optional[int]:
    project = await db.get(Project, project_id)
    if project is not None and project.roadmap_id:
        return await rollup_roadmap(db, organization_id=organization_id, roadmap_id=project.roadmap_id)
    return None
