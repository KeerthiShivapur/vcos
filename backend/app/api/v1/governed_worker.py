"""Governed AI Worker API (Slice 4).

Endpoints for governed AI tasks: research briefs and authorization-required
recommendations. Reads and writes require the existing ``ai:use`` permission;
consequential actions additionally require a granted approval which is
revalidated at the execution boundary.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.governed_worker import WorkerTaskCreate
from app.services.governed_worker_service import (
    WorkerError,
    WorkerNotExecutable,
    WorkerNotFound,
    WorkerNotRunnable,
    governed_worker_service,
)

router = APIRouter(prefix="/governed-worker", tags=["Governed AI Worker"])


async def _actor(db: AsyncSession, org: Organization, user: User):
    from app.people.employee_service import employee_service

    return await employee_service.get_by_user(
        db, organization_id=org.id, user_id=user.id
    )


def _http_error(exc: WorkerError) -> HTTPException:
    if isinstance(exc, WorkerNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    return HTTPException(status_code=400, detail=str(exc))


@router.get("/tasks")
async def list_tasks(
    limit: int = 50,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    return await governed_worker_service.list_tasks(
        db, organization_id=org.id, limit=min(limit, 200)
    )


@router.post("/tasks", status_code=201)
async def create_task(
    payload: WorkerTaskCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    try:
        operation = await governed_worker_service.create_task(
            db,
            organization_id=org.id,
            data=payload,
            actor=actor,
            ip_address=get_client_ip(request),
        )
    except WorkerError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return await governed_worker_service.get_task_detail(
        db, organization_id=org.id, operation_id=operation.id
    )


@router.get("/tasks/{operation_id}")
async def get_task(
    operation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await governed_worker_service.get_task_detail(
            db, organization_id=org.id, operation_id=operation_id
        )
    except WorkerNotFound as exc:
        raise _http_error(exc) from exc


@router.post("/tasks/{operation_id}/run")
async def run_task(
    operation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    try:
        operation = await governed_worker_service.run_task(
            db, organization_id=org.id, operation_id=operation_id, actor=actor
        )
    except WorkerError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return await governed_worker_service.get_task_detail(
        db, organization_id=org.id, operation_id=operation.id
    )


@router.post("/tasks/{operation_id}/cancel")
async def cancel_task(
    operation_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    try:
        operation = await governed_worker_service.cancel_task(
            db,
            organization_id=org.id,
            operation_id=operation_id,
            actor=actor,
            ip_address=get_client_ip(request),
        )
    except WorkerError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    return await governed_worker_service.get_task_detail(
        db, organization_id=org.id, operation_id=operation.id
    )


@router.post("/actions/{operation_id}/execute")
async def execute_action(
    operation_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("ai:use")),
    db: AsyncSession = Depends(get_db),
):
    actor = await _actor(db, org, user)
    try:
        action = await governed_worker_service.execute_action(
            db,
            organization_id=org.id,
            operation_id=operation_id,
            actor=actor,
            ip_address=get_client_ip(request),
        )
    except WorkerNotExecutable as exc:
        raise _http_error(exc) from exc
    except WorkerNotFound as exc:
        raise _http_error(exc) from exc
    except WorkerError as exc:
        raise _http_error(exc) from exc
    await db.commit()
    parent_id = (action.payload or {}).get("parent_operation_id")
    return await governed_worker_service.get_task_detail(
        db, organization_id=org.id, operation_id=parent_id or operation_id
    )
