"""Tasks API — the task engine with dependencies (Phase 3)."""

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.work import (
    DependencyOut,
    TaskAttachmentCreate,
    TaskAttachmentOut,
    TaskCommentCreate,
    TaskCommentOut,
    TaskCreate,
    TaskOut,
    TaskTransition,
    TaskUpdate,
)
from app.work.dependency_service import dependency_service
from app.work.task_service import task_service

router = APIRouter(prefix="/tasks", tags=["Tasks"])


async def _task_actor(
    db: AsyncSession, *, organization_id: str, user: User,
) -> tuple[bool, Optional[Any]]:
    """Who may act on a task.

    `tasks:manage` grants full control; otherwise the assigned employee
    (with `tasks:read`) may execute their own task — transition it, edit
    fields, comment and attach material. Everything else stays forbidden.
    """
    from app.people.employee_service import employee_service
    from app.services.permission_service import permission_service

    actor = await employee_service.get_by_user(db, organization_id=organization_id, user_id=user.id)
    perms = await permission_service.user_permission_codes(db, user.id, organization_id)
    if "tasks:manage" in perms:
        return True, actor
    if "tasks:read" in perms and actor is not None:
        return False, actor
    return False, None


def _require_editor(can_manage: bool, actor: Any, task: Any) -> Optional[Any]:
    if can_manage:
        return actor
    if actor is not None and task.assignee_id == actor.id:
        return actor
    return None


def _task_payload(t) -> dict[str, Any]:
    return {
        "id": t.id,
        "project_id": t.project_id,
        "project_name": getattr(t, "project_name", None),
        "epic_id": t.epic_id,
        "milestone_id": t.milestone_id,
        "sprint_id": t.sprint_id,
        "parent_task_id": t.parent_task_id,
        "parent_title": getattr(t, "parent_title", None),
        "subtasks_count": getattr(t, "subtasks_count", 0),
        "subtasks_completed": getattr(t, "subtasks_completed", 0),
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
        "tags": t.tags,
        "ai_summary": t.ai_summary,
        "dependencies": getattr(t, "dependencies", []),
        "blocking_tasks": getattr(t, "blocking_tasks", []),
        "blocked_by": getattr(t, "blocked_by", []),
        "created_at": t.created_at,
        "updated_at": t.updated_at,
    }


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    project_id: Optional[str] = None,
    assignee_id: Optional[str] = None,
    reporter_id: Optional[str] = None,
    epic_id: Optional[str] = None,
    milestone_id: Optional[str] = None,
    sprint_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    tag: Optional[str] = None,
    search: Optional[str] = None,
    due_from: Optional[date] = None,
    due_to: Optional[date] = None,
    sort: str = "updated",
    limit: int = 200,
    offset: int = 0,
    include_archived: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    tasks = await task_service.list_all(
        db, organization_id=org.id, project_id=project_id, assignee_id=assignee_id,
        reporter_id=reporter_id, epic_id=epic_id, milestone_id=milestone_id,
        sprint_id=sprint_id, parent_task_id=parent_task_id, status=status,
        priority=priority, tag=tag, search=search, due_from=due_from,
        due_to=due_to, sort=sort, limit=limit,
        offset=offset, include_archived=include_archived,
    )
    if tasks:
        await _enrich_blocked_by(db, organization_id=org.id, tasks=tasks)
    return [TaskOut.model_validate(_task_payload(t)) for t in tasks]


async def _enrich_blocked_by(
    db: AsyncSession, *, organization_id: str, tasks: list[Any],
) -> None:
    """Batch-populate blocked_by so list responses match the detail payload.

    One query covers every returned task instead of an N+1 per row.
    """
    from app.models.task import Task, TaskDependency
    from sqlalchemy import select

    ids = [t.id for t in tasks]
    rows = await db.execute(
        select(TaskDependency, Task)
        .join(Task, Task.id == TaskDependency.depends_on_task_id)
        .where(
            TaskDependency.organization_id == organization_id,
            TaskDependency.task_id.in_(ids),
        )
    )
    by_task: dict[str, list[dict]] = {}
    for dep, linked in rows.all():
        by_task.setdefault(dep.task_id, []).append(
            {"id": dep.id, "task_id": linked.id, "title": linked.title, "status": linked.status, "kind": dep.kind}
        )
    for t in tasks:
        deps = by_task.get(t.id, [])
        t.dependencies = deps
        t.blocked_by = [d for d in deps if d["status"] != "completed"]


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(
    payload: TaskCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    can_manage, actor = await _task_actor(db, organization_id=org.id, user=user)
    if not can_manage and not payload.parent_task_id:
        raise HTTPException(403, "Not allowed to create tasks")
    if not can_manage and payload.parent_task_id:
        parent = await task_service.get(db, organization_id=org.id, task_id=payload.parent_task_id)
        if parent is None:
            raise HTTPException(404, "Parent task not found")
        if actor is None or parent.assignee_id != actor.id:
            raise HTTPException(403, "Only the assignee of the parent task may add subtasks")
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
    payload["blocked_by"] = getattr(task, "blocked_by", [])
    return TaskOut.model_validate(payload)


@router.patch("/{task_id}", response_model=TaskOut)
async def update_task(
    task_id: str,
    payload: TaskUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    can_manage, actor = await _task_actor(db, organization_id=org.id, user=user)
    editor = _require_editor(can_manage, actor, task)
    if editor is None:
        raise HTTPException(403, "Only the assignee or a task manager may edit this task")
    try:
        task = await task_service.update(
            db, organization_id=org.id, task=task,
            data=payload.model_dump(exclude_unset=True), actor=editor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    return TaskOut.model_validate(_task_payload(task))


@router.post("/{task_id}/transition", response_model=TaskOut)
async def transition_task(
    task_id: str,
    payload: TaskTransition,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    can_manage, actor = await _task_actor(db, organization_id=org.id, user=user)
    editor = _require_editor(can_manage, actor, task)
    if editor is None:
        raise HTTPException(403, "Only the assignee or a task manager may transition this task")
    try:
        task = await task_service.transition(
            db, organization_id=org.id, task=task, status=payload.status, force=payload.force,
            actor=editor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    return TaskOut.model_validate(_task_payload(task))


@router.delete("/{task_id}", response_model=Message)
async def delete_task(
    task_id: str,
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
    await task_service.delete(db, organization_id=org.id, task=task, actor=actor, ip_address=get_client_ip(request))
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
        dep = await dependency_service.add(
            db, organization_id=org.id, task_id=task_id,
            depends_on_task_id=payload["depends_on_task_id"], kind=payload.get("kind", "finish_to_start"),
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    dep = await dependency_service.get(db, organization_id=org.id, dependency_id=dep.id)
    return dep


@router.put("/{task_id}/dependencies", response_model=list[DependencyOut])
async def sync_dependencies(
    task_id: str,
    payload: list[dict],
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Atomically replace the dependency set of a task."""
    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        deps = await dependency_service.sync(
            db, organization_id=org.id, task_id=task_id, dependencies=payload,
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return deps


@router.delete("/{task_id}/dependencies/{dependency_id}", response_model=Message)
async def remove_dependency(
    task_id: str,
    dependency_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:manage")),
    db: AsyncSession = Depends(get_db),
):
    dep = await dependency_service.get(db, organization_id=org.id, dependency_id=dependency_id)
    if dep is None:
        raise HTTPException(404, "Dependency not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    await dependency_service.remove(
        db, organization_id=org.id,
        task_id=dep.task_id, depends_on_task_id=dep.depends_on_task_id,
        actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return Message(message="Dependency removed")


# --------------------------------------------------------------------------- Collaboration

@router.post("/{task_id}/comments", response_model=TaskCommentOut, status_code=201)
async def add_comment(
    task_id: str,
    payload: TaskCommentCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.work.task_collab_service import task_collab_service

    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    can_manage, actor = await _task_actor(db, organization_id=org.id, user=user)
    if _require_editor(can_manage, actor, task) is None:
        raise HTTPException(403, "Only the assignee or a task manager may comment")
    comment = await task_collab_service.add_comment(
        db, organization_id=org.id, task_id=task_id, body=payload.body,
        author=actor, mentions=payload.mentions, ip_address=get_client_ip(request),
    )
    await db.commit()
    comments = await task_collab_service.list_comments(db, organization_id=org.id, task_id=task_id)
    for c in comments:
        if c.id == comment.id:
            comment = c
    return TaskCommentOut(
        id=comment.id, task_id=comment.task_id, author_id=comment.author_id,
        author_name=comment.author_name, body=comment.body, mentions=comment.mentions,
        created_at=comment.created_at,
    )


@router.get("/{task_id}/comments", response_model=list[TaskCommentOut])
async def list_comments(
    task_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.work.task_collab_service import task_collab_service

    comments = await task_collab_service.list_comments(db, organization_id=org.id, task_id=task_id)
    return [
        TaskCommentOut(
            id=c.id, task_id=c.task_id, author_id=c.author_id, author_name=c.author_name,
            body=c.body, mentions=c.mentions, created_at=c.created_at,
        )
        for c in comments
    ]


@router.delete("/{task_id}/comments/{comment_id}", response_model=Message)
async def delete_comment(
    task_id: str,
    comment_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.work.task_collab_service import task_collab_service

    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    comment = await db.get(__import__("app.models.task", fromlist=["TaskComment"]).TaskComment, comment_id)
    if comment is None or comment.task_id != task_id:
        raise HTTPException(404, "Comment not found")
    can_manage, actor = await _task_actor(db, organization_id=org.id, user=user)
    if _require_editor(can_manage, actor, task) is None:
        raise HTTPException(403, "Only the assignee or a task manager may manage comments")
    if not can_manage and actor is not None and comment.author_id != actor.id:
        raise HTTPException(403, "Only the author may delete their own comment")
    await task_collab_service.delete_comment(
        db, organization_id=org.id, comment=comment, actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return Message(message="Comment deleted")


@router.post("/{task_id}/attachments", response_model=TaskAttachmentOut, status_code=201)
async def add_attachment(
    task_id: str,
    payload: TaskAttachmentCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.work.task_collab_service import task_collab_service

    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    can_manage, actor = await _task_actor(db, organization_id=org.id, user=user)
    if _require_editor(can_manage, actor, task) is None:
        raise HTTPException(403, "Only the assignee or a task manager may attach files")
    attachment = await task_collab_service.add_attachment(
        db, organization_id=org.id, task_id=task_id, filename=payload.filename,
        url=payload.url, size_bytes=payload.size_bytes, kind=payload.kind,
        uploader=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    attachments = await task_collab_service.list_attachments(db, organization_id=org.id, task_id=task_id)
    for a in attachments:
        if a.id == attachment.id:
            attachment = a
    return TaskAttachmentOut(
        id=attachment.id, task_id=attachment.task_id, filename=attachment.filename,
        url=attachment.url, size_bytes=attachment.size_bytes, kind=attachment.kind,
        uploaded_by=attachment.uploaded_by, uploaded_by_name=attachment.uploaded_by_name,
        created_at=attachment.created_at,
    )


@router.get("/{task_id}/attachments", response_model=list[TaskAttachmentOut])
async def list_attachments(
    task_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.work.task_collab_service import task_collab_service

    attachments = await task_collab_service.list_attachments(db, organization_id=org.id, task_id=task_id)
    return [
        TaskAttachmentOut(
            id=a.id, task_id=a.task_id, filename=a.filename, url=a.url,
            size_bytes=a.size_bytes, kind=a.kind, uploaded_by=a.uploaded_by,
            uploaded_by_name=a.uploaded_by_name, created_at=a.created_at,
        )
        for a in attachments
    ]


@router.delete("/{task_id}/attachments/{attachment_id}", response_model=Message)
async def delete_attachment(
    task_id: str,
    attachment_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.work.task_collab_service import task_collab_service

    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    attachment = await db.get(
        __import__("app.models.task", fromlist=["TaskAttachment"]).TaskAttachment, attachment_id
    )
    if attachment is None or attachment.task_id != task_id:
        raise HTTPException(404, "Attachment not found")
    can_manage, actor = await _task_actor(db, organization_id=org.id, user=user)
    if _require_editor(can_manage, actor, task) is None:
        raise HTTPException(403, "Only the assignee or a task manager may manage attachments")
    if not can_manage and actor is not None and attachment.uploaded_by != actor.id:
        raise HTTPException(403, "Only the uploader may remove their own attachment")
    await task_collab_service.delete_attachment(
        db, organization_id=org.id, attachment=attachment, actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    return Message(message="Attachment deleted")


@router.get("/{task_id}/activity")
async def task_activity(
    task_id: str,
    limit: int = 50,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("tasks:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.work.task_collab_service import task_collab_service

    task = await task_service.get(db, organization_id=org.id, task_id=task_id)
    if task is None:
        raise HTTPException(404, "Task not found")
    return await task_collab_service.activity(db, organization_id=org.id, task_id=task_id, limit=limit)
