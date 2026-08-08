"""Tasks API — the task engine with dependencies (Phase 3)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.work import DependencyOut, TaskCreate, TaskOut, TaskUpdate
from app.work.dependency_service import dependency_service
from app.work.task_service import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


def _task_payload(t) -> dict[str, Any]:
    return {
        "id": t.id,
        "project_id": t.project_id,
        "project_name": getattr(t, "project_name", None),
        "epic_id": t.epic_id,
        "milestone_id": t.milestone_id,
        "sprint_id": t.sprint_id,
        "parent_task_id": t.parent_task_id,
        "title": t.title,
        "description": t.description,
        "status": t.status,
        "priority": t.priority,
        "assignee_id": t.assignee_id,
        "assignee_name": getattr(t, "assignee_name", None),
        "assignee_avatar_url": getattr(t, "assignee_avatar_url", None),
        "reporter_id": t.reporter_id,
        "reporter_name": getattr(t, "reporter_name", None),
        "estimate_hours": t.estimate_hours,
        "spent_hours": t.spent_hours or 0,
        "start_date": t.start_date,
        "due_date": t.due_date,
        "completed_at": t.completed_at,
        "progress": t.progress,
        "ai_summary": t.ai_summary,
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    project_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    sort: str = "updated",
    include_archived: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    tasks = await task_service.list_all(
        db, organization_id=org.id, project_id=project_id, assignee_id=assignee_id,
        status=status, priority=priority, search=search, sort=sort,
        include_archived=include_archived,
    )
    return [TaskOut.model_validate(_task_payload(t)) for t in tasks]


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    data = payload.model_dump(exclude_unset=True)
    try:
        task = await task_service.create(
            db, organization_id=org.id, data=data, actor=actor, ip_address=get_client_ip(request),
        )
        for dep in payload.dependencies or []:
            try:
                await dependency_service.add(
                    db, organization_id=org.id, task_id=task.id,
                    depends_on_task_id=dep["depends_on_task_id"], kind=dep.get("kind", "finish_to_start"),
                )
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    task = await task_service.get(db, organization_id=org.id, task_id=task.id)
    return TaskOut.model_validate(_task_payload(task))


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(
    task_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    payload = _task_payload(task)
    payload["dependencies"] = getattr(task, "dependencies", [])
    payload["blocking_tasks"] = getattr(task, "blocking_tasks", [])
    return TaskOut.model_validate(payload)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:manage")),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        task = await task_service.update(
            db, organization_id=org.id, task=task,
            data=payload.model_dump(exclude_unset=True), actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    return TaskOut.model_validate(_task_payload(task))


@router.post("/{task_id}/transition", response_model=TaskOut)
async def transition_task(
    task_id: str,
    payload: dict,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:manage")),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        task = await task_service.transition(
            db, organization_id=org.id, task=task, status=payload["status"],
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    return TaskOut.model_validate(_task_payload(task))


@router.delete("/{task_id}", response_model=Message)
async def delete_task(
    task_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:manage")),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    await task_service.delete(db, organization_id=org.id, task=task)
    await db.commit()
    return Message(message="Task deleted")


# --------------------------------------------------------------------------- Dependencies

@router.get("/{task_id}/dependencies", response_model=list[DependencyOut])
async def list_dependencies(
    task_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    return await dependency_service.dependencies(db, organization_id=org.id, task_id=task_id)


@router.post("/{task_id}/dependencies", response_model=DependencyOut, status_code=201)
async def add_dependency(
    task_id: str,
    payload: dict,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:manage")),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    try:
        dep = await dependency_service.add(
            db, organization_id=org.id, task_id=task_id,
            depends_on_task_id=payload["depends_on_task_id"], kind=payload.get("kind", "finish_to_start"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    dep = await dependency_service.get(db, organization_id=org.id, dependency_id=dep.id)
    return dep


@router.delete("/{task_id}/dependencies/{dependency_id}", response_model=Message)
async def remove_dependency(
    task_id: str,
    dependency_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:manage")),
    db: AsyncSession = Depends(get_db),
):
    dep = await dependency_service.get(db, organization_id=org.id, dependency_id=dependency_id)
    if dep is None:
        raise HTTPException(404, "Dependency not found")
    await dependency_service.remove(
        db, organization_id=org.id,
        task_id=dep.task_id, depends_on_task_id=dep.depends_on_task_id,
    )
    await db.commit()
    return Message(message="Dependency removed")
