"""Onboarding API (Phase 10.10 — New Hire Onboarding).

Auto-generated onboarding plans with checklist tasks (intro, policies,
security, wiki, team meetings, projects, courses, mentoring, quiz, goals)
that roll learning profile data forward as tasks are completed.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.learning.onboarding_service import onboarding_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning/onboarding", tags=["Learning"])


async def _employee_id(db: AsyncSession, org: Organization, user: User) -> str:
    employee = (
        await db.execute(
            select(Employee).where(
                Employee.organization_id == org.id, Employee.user_id == str(user.id)
            )
        )
    ).scalar_one_or_none()
    if employee is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    return employee.id


@router.post("/plans", status_code=201)
async def create_plan(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = payload.get("employee_id")
    if not employee_id:
        raise HTTPException(status_code=400, detail="employee_id is required")
    plan = await onboarding_service.create_plan(
        db, organization_id=org.id, employee_id=employee_id,
        target_days=int(payload.get("target_days", 14)),
    )
    if plan is None:
        raise HTTPException(status_code=404, detail="Employee not found")
    await db.commit()
    return {"id": plan.id, "employee_id": plan.employee_id, "status": plan.status}


@router.get("/plans")
async def list_plans(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    status: str = Query("active"),
):
    return await onboarding_service.list_plans(db, organization_id=org.id, status=status)


@router.get("/plans/{plan_id}")
async def plan_detail(
    plan_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    plan = await onboarding_service.get_plan(db, organization_id=org.id, plan_id=plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail="Onboarding plan not found")
    employee_id = await _employee_id(db, org, user)
    if plan.get("employee_id") != employee_id:
        raise HTTPException(status_code=403, detail="Not your onboarding plan")
    return plan


@router.post("/plans/{plan_id}/tasks/{task_id}/complete")
async def complete_task(
    plan_id: str,
    task_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    result = await onboarding_service.complete_task(
        db, organization_id=org.id, plan_id=plan_id, task_id=task_id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Plan or task not found")
    await db.commit()
    return {
        "plan_id": plan_id,
        "task_id": task_id,
        "plan_progress": result.get("plan_progress"),
        "plan_status": result.get("plan_status"),
    }
