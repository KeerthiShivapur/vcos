"""Wellbeing API (Phase 11.11 — Wellbeing).

Pattern-based workload & engagement check-ins. Not a health system.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.wellbeing_service import wellbeing_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/wellbeing", tags=["HR Wellbeing"])


async def _employee_id(db: AsyncSession, org: Organization, user: User) -> str:
    employee = (
        await db.execute(
            select(Employee).where(Employee.organization_id == org.id, Employee.user_id == str(user.id))
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee.id


@router.post("/check-ins")
async def check_in(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    check = await wellbeing_service.check_in(db, organization_id=org.id, employee_id=employee_id, data=payload)
    await db.commit()
    return {
        "id": check.id,
        "check_date": check.check_date.isoformat(),
        "risk_level": check.risk_level,
        "signals": check.signals or [],
    }


@router.get("/my")
async def my_checks(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    checks = await wellbeing_service.my_checks(db, organization_id=org.id, employee_id=employee_id)
    return [
        {
            "id": check.id,
            "check_date": check.check_date.isoformat(),
            "risk_level": check.risk_level,
            "signals": check.signals or [],
            "metrics": check.metrics or {},
            "notes": check.notes,
        }
        for check in checks
    ]


@router.get("")
async def list_checks(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    risk_level: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    return await wellbeing_service.list_checks(db, organization_id=org.id, risk_level=risk_level, limit=limit)


@router.get("/overview")
async def wellbeing_overview(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    return await wellbeing_service.overview(db, organization_id=org.id)


@router.get("/recommendations")
async def wellbeing_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    return await wellbeing_service.recommendations(db, organization_id=org.id)
