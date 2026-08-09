"""Workload & Work Analytics API — capacity, My Work, Executive dashboard (Phase 3)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.work.intelligence_service import intelligence_service
from app.work.workload_service import workload_service

router = APIRouter(tags=["Workload"])


@router.get("/workload/me")
async def my_workload(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("workload:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    return await workload_service.compute_for_employee(db, organization_id=org.id, employee_id=actor.id)


@router.get("/workload/employees/{employee_id}")
async def employee_workload(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("workload:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.models.employee import Employee

    emp = await db.get(Employee, employee_id)
    if emp is None or emp.organization_id != org.id:
        raise HTTPException(404, "Employee not found")
    return await workload_service.compute_for_employee(db, organization_id=org.id, employee_id=employee_id)


@router.post("/workload/snapshot")
async def snapshot_week(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("workload:read")),
    db: AsyncSession = Depends(get_db),
):
    created = await workload_service.snapshot_week(db, organization_id=org.id)
    await db.commit()
    return {"snapshots_created": created}


@router.get("/workload/teams")
async def team_load(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("workload:read")),
    db: AsyncSession = Depends(get_db),
):
    return await workload_service.team_load_summary(db, organization_id=org.id)


@router.get("/workload/organization")
async def organization_load(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    return await intelligence_service.organization_load(db, organization_id=org.id)


@router.get("/my-work")
async def my_work(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("workload:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    return await intelligence_service.my_work(db, organization_id=org.id, employee_id=actor.id)


@router.get("/analytics/executive")
async def executive_dashboard(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("analytics:read")),
    db: AsyncSession = Depends(get_db),
):
    return await intelligence_service.executive_dashboard(db, organization_id=org.id)
