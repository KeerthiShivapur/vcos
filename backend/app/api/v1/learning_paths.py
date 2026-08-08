"""Learning Paths API (Phase 10.3 — Personalized Career-Focused Learning Paths).

Paths are curated course sequences; employees enroll and complete steps.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.learning.learning_path_service import learning_path_service
from app.models.employee import Employee
from app.models.learning_path import PathEnrollment
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning/paths", tags=["Learning"])


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
        "category": path.category,
        "target_role": path.target_role,
        "difficulty": path.difficulty,
        "estimated_days": path.estimated_days,
        "status": path.status,
        "tags": path.tags or [],
        "step_count": step_count,
    }


@router.get("")
async def list_paths(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    status: str = Query("published"),
    search: str = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    employee_id = await _employee_id(db, org, user)
    paths = await learning_path_service.list_paths(
        db, organization_id=org.id, status=status, search=search, limit=limit
    )
    result = []
    for path in paths:
        enrollment = (
            await db.execute(
                select(PathEnrollment).where(
                    PathEnrollment.organization_id == org.id,
                    PathEnrollment.path_id == path.id,
                    PathEnrollment.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        payload = _path_payload(path, step_count=len(path.steps or []))
        payload["enrolled"] = enrollment is not None
        payload["my_progress"] = enrollment.progress if enrollment else 0.0
        result.append(payload)
    return result


@router.post("", status_code=201)
async def create_path(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    path = await learning_path_service.create_path(db, organization_id=org.id, data=payload)
    await db.commit()
    return _path_payload(path, step_count=len(payload.get("steps") or []))


@router.get("/my/enrollments")
async def my_enrollments(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    enrollments = await learning_path_service.my_enrollments(
        db, organization_id=org.id, employee_id=employee_id
    )
    result = []
    for enrollment in enrollments:
        path = await learning_path_service.get_path(
            db, organization_id=org.id, path_id=enrollment.path_id
        )
        if path is None:
            continue
        result.append(
            {
                "id": enrollment.id,
                "path_id": path.id,
                "title": path.title,
                "target_role": path.target_role,
                "status": enrollment.status,
                "progress": enrollment.progress,
                    "completed_step_ids": enrollment.completed_step_ids or [],
                    "started_at": enrollment.started_at.isoformat(),
                    "completed_at": enrollment.completed_at.isoformat() if enrollment.completed_at else None,
            }
        )
    return result


@router.get("/{path_id}")
async def path_detail(
    path_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    path = await learning_path_service.get_path(db, organization_id=org.id, path_id=path_id)
    if path is None:
        raise HTTPException(status_code=404, detail="Learning path not found")
    employee_id = await _employee_id(db, org, user)
    enrollment = (
        await db.execute(
            select(PathEnrollment).where(
                PathEnrollment.organization_id == org.id,
                PathEnrollment.path_id == path.id,
                PathEnrollment.employee_id == employee_id,
            )
        )
    ).scalar_one_or_none()
    payload = _path_payload(path, step_count=len(path.steps or []))
    payload["enrolled"] = enrollment is not None
    payload["my_progress"] = enrollment.progress if enrollment else 0.0
    payload["steps"] = [
        {
            "id": step.id,
            "title": step.title,
            "description": step.description,
                "course_id": step.course_id,
                "position": step.position,
                "done": bool(enrollment and step.id in (enrollment.completed_step_ids or [])),
        }
        for step in sorted(path.steps or [], key=lambda s: (s.position or 0))
    ]
    return payload


@router.post("/{path_id}/steps", status_code=201)
async def add_step(
    path_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    step = await learning_path_service.add_step(
        db, organization_id=org.id, path_id=path_id, data=payload
    )
    if step is None:
        raise HTTPException(status_code=404, detail="Learning path not found")
    await db.commit()
    return {"id": step.id, "title": step.title, "order": step.position}


@router.post("/{path_id}/enroll", status_code=201)
async def enroll(
    path_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    enrollment = await learning_path_service.enroll(
        db, organization_id=org.id, path_id=path_id, employee_id=employee_id
    )
    if enrollment is None:
        raise HTTPException(status_code=404, detail="Learning path not available")
    await db.commit()
    return {"id": enrollment.id, "path_id": path_id, "status": enrollment.status}


@router.post("/enrollments/{enrollment_id}/steps/{step_id}/complete")
async def complete_step(
    enrollment_id: str,
    step_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    enrollment = await learning_path_service.complete_step(
        db, organization_id=org.id, path_id="", employee_id=employee_id,
        step_id=step_id,
    )
    if enrollment is None:
        # try resolving via enrollment id instead of path id
        row = (
            await db.execute(
                select(PathEnrollment).where(
                    PathEnrollment.organization_id == org.id,
                    PathEnrollment.id == enrollment_id,
                    PathEnrollment.employee_id == employee_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Enrollment or step not found")
        enrollment = await learning_path_service.complete_step(
            db, organization_id=org.id, path_id=row.path_id, employee_id=employee_id,
            step_id=step_id,
        )
        if enrollment is None:
            raise HTTPException(status_code=404, detail="Enrollment or step not found")
    await db.commit()
    return {"id": enrollment.id, "status": enrollment.status, "progress": enrollment.progress}
