"""Career API (Phase 10.8 — Career Paths & Promotion Signals).

Defines role progression paths, computes employee readiness against the next
role, and surfaces promotion signals for managers.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.learning.career_service import career_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning/career", tags=["Learning"])


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


def _path_payload(path, step_count: int = 0) -> dict[str, Any]:
    return {
        "id": path.id,
        "title": path.title,
        "description": path.description,
        "department": path.department,
        "levels": path.levels or [],
        "status": path.status,
        "step_count": step_count,
    }


@router.get("")
async def list_paths(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    status: str = Query("published"),
    department: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    paths = await career_service.list_paths(
        db, organization_id=org.id, status=status, department=department
    )
    return [_path_payload(p) for p in paths][:limit]


@router.post("", status_code=201)
async def create_path(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    path = await career_service.create_path(db, organization_id=org.id, data=payload)
    await db.commit()
    return _path_payload(path, step_count=len(payload.get("steps") or []))


@router.get("/my/progress")
async def my_progress(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    return await career_service.progress_for(db, organization_id=org.id, employee_id=employee_id)


@router.get("/my/required-skills")
async def required_skills(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    return await career_service.required_skills_for_employee(
        db, organization_id=org.id, employee_id=employee_id
    )


@router.post("/my/promotion-signals/detect")
async def detect_signal(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    signal = await career_service.detect_promotion_signals(
        db, organization_id=org.id, employee_id=employee_id
    )
    await db.commit()
    if signal is None:
        return {"detected": False}
    return {
        "detected": True,
        "id": signal.id,
        "target_role": signal.target_role,
        "readiness": signal.readiness,
        "evidence": signal.evidence or [],
        "status": signal.status,
    }


@router.get("/signals")
async def signals(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
    status: str = Query("open"),
    employee_id: Optional[str] = Query(None),
):
    signals_list = await career_service.signals(
        db, organization_id=org.id, employee_id=employee_id, status=status
    )
    return signals_list


@router.post("/signals/{signal_id}/review")
async def review_signal(
    signal_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    status = payload.get("status", "approved")
    signal = await career_service.review_signal(
        db, organization_id=org.id, signal_id=signal_id, status=status
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Promotion signal not found")
    await db.commit()
    return {"id": signal.id, "status": signal.status}


@router.get("/{path_id}")
async def path_detail(
    path_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    path = await career_service.get_path(db, organization_id=org.id, path_id=path_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Career path not found")
    payload = _path_payload(path)
    payload["steps"] = [
        {
            "id": step.id,
            "title": step.title,
            "position": step.position,
            "level": step.level,
            "required_skills": step.required_skills or [],
            "required_years": step.required_years,
            "criteria": step.criteria or {},
        }
        for step in sorted(path.steps or [], key=lambda s: s.position or 0)
    ]
    return payload
