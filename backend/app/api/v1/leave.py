"""Leave API (Phase 11.3 — Leave Management).

Leave types, balances, requests with the Employee → Manager → HR approval
workflow, calendar aggregation and org-wide summaries.
"""

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.leave_service import leave_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.services.permission_service import permission_service

router = APIRouter(prefix="/leave", tags=["HR Leave"])


async def _employee_id(db: AsyncSession, org: Organization, user: User) -> str:
    employee = (
        await db.execute(
            select(Employee).where(Employee.organization_id == org.id, Employee.user_id == str(user.id))
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee.id


# ------------------------------------------------------------------ types

@router.get("/types")
async def list_types(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    types = await leave_service.list_types(db, organization_id=org.id)
    await db.commit()  # persists default leave type seeding
    return [
        {
            "id": leave_type.id,
            "name": leave_type.name,
            "code": leave_type.code,
            "color": leave_type.color,
            "days_per_year": leave_type.days_per_year,
            "carry_over": leave_type.carry_over,
            "requires_approval": leave_type.requires_approval,
            "is_paid": leave_type.is_paid,
            "is_active": leave_type.is_active,
        }
        for leave_type in types
    ]


@router.post("/types")
async def create_type(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    leave_type = await leave_service.create_type(db, organization_id=org.id, data=payload)
    await db.commit()
    return {"id": leave_type.id, "name": leave_type.name, "code": leave_type.code}


@router.patch("/types/{leave_type_id}")
async def update_type(
    leave_type_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    leave_type = await leave_service.update_type(db, organization_id=org.id, leave_type_id=leave_type_id, data=payload)
    if leave_type is None:
        raise HTTPException(status_code=404, detail="Leave type not found")
    await db.commit()
    return {"id": leave_type.id, "name": leave_type.name}


# ------------------------------------------------------------------ balances

@router.get("/balances")
async def my_balances(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    year: Optional[int] = Query(None),
):
    employee_id = await _employee_id(db, org, user)
    balances = await leave_service.balances(db, organization_id=org.id, employee_id=employee_id, year=year)
    await db.commit()  # persists balance rows created on first access
    return balances


@router.get("/balances/{employee_id}")
async def employee_balances(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    year: Optional[int] = Query(None),
):
    balances = await leave_service.balances(db, organization_id=org.id, employee_id=employee_id, year=year)
    await db.commit()  # persists balance rows created on first access
    return balances


# ------------------------------------------------------------------ requests

@router.post("/requests")
async def request_leave(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    try:
        request = await leave_service.request(db, organization_id=org.id, employee_id=employee_id, data=payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {
        "id": request.id,
        "start_date": request.start_date.isoformat(),
        "end_date": request.end_date.isoformat(),
        "days": request.days,
        "status": request.status,
    }


@router.get("/requests")
async def list_requests(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    start: Optional[date] = Query(None),
    end: Optional[date] = Query(None),
    mine: bool = Query(False),
):
    if mine:
        employee_id = await _employee_id(db, org, user)
    return await leave_service.list_requests(
        db, organization_id=org.id, employee_id=employee_id, status=status, start=start, end=end
    )


@router.get("/requests/{request_id}")
async def get_request(
    request_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    request = await leave_service.get_request(db, organization_id=org.id, request_id=request_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    return request


@router.get("/pending")
async def pending_requests(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    """HR sees everything; managers see their reports' pending requests."""
    codes = await permission_service.user_permission_codes(db, user.id, org.id)
    if "hr:manage" in codes:
        return await leave_service.pending_requests(db, organization_id=org.id)
    manager = (
        await db.execute(
            select(Employee).where(Employee.organization_id == org.id, Employee.user_id == str(user.id))
        )
    ).scalar_one_or_none()
    if manager is None:
        return []
    has_reports = (
        await db.execute(select(Employee.id).where(Employee.manager_id == manager.id).limit(1))
    ).scalars().first()
    if not has_reports:
        return []
    return await leave_service.pending_requests(db, organization_id=org.id, manager_employee_id=manager.id)


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        request = await leave_service.approve(
            db, organization_id=org.id, request_id=request_id, reviewer_id=user.id, note=payload.get("note")
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    await db.commit()
    return {"id": request.id, "status": request.status}


@router.post("/requests/{request_id}/reject")
async def reject_request(
    request_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    request = await leave_service.reject(
        db, organization_id=org.id, request_id=request_id, reviewer_id=user.id, note=payload.get("note")
    )
    if request is None:
        raise HTTPException(status_code=404, detail="Leave request not found")
    await db.commit()
    return {"id": request.id, "status": request.status}


@router.post("/requests/{request_id}/cancel")
async def cancel_request(
    request_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    request = await leave_service.cancel(db, organization_id=org.id, request_id=request_id, employee_id=employee_id)
    if request is None:
        raise HTTPException(status_code=404, detail="Leave request not found or cannot be cancelled")
    await db.commit()
    return {"id": request.id, "status": request.status}


# ------------------------------------------------------------------ calendar & summary

@router.get("/calendar")
async def leave_calendar(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    start: date = Query(...),
    end: date = Query(...),
):
    return await leave_service.calendar(db, organization_id=org.id, start=start, end=end)


@router.get("/summary")
async def leave_summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    return await leave_service.summary(db, organization_id=org.id)
