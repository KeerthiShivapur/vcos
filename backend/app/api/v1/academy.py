"""Academy API (Phase 10.9 — Corporate Academy).

Curated academy "channels" that group courses by learning track; employees
join academies and consume their curated course sets.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.learning.academy_service import academy_service
from app.models.academy import AcademyCourse
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning/academies", tags=["Learning"])


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


def _academy_payload(academy) -> dict[str, Any]:
    return {
        "id": academy.id,
        "name": academy.name,
        "description": academy.description,
        "category": academy.category,
        "status": academy.status,
        "curriculum": academy.curriculum or [],
        "member_count": len(academy.members or []),
        "course_count": len(academy.courses or []),
    }


@router.get("")
async def list_academies(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    category: Optional[str] = Query(None),
    status: str = Query("published"),
    limit: int = Query(50, ge=1, le=200),
):
    academies = await academy_service.list_academies(
        db, organization_id=org.id, category=category, status=status
    )
    return [_academy_payload(a) for a in academies[:limit]]


@router.post("", status_code=201)
async def create_academy(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    academy = await academy_service.create(db, organization_id=org.id, data=payload)
    await db.commit()
    academy = await academy_service.get(db, organization_id=org.id, academy_id=academy.id)
    return _academy_payload(academy)


@router.get("/my")
async def my_academies(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    return await academy_service.my_academies(db, organization_id=org.id, employee_id=employee_id)


@router.get("/{academy_id}")
async def academy_detail(
    academy_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    academy = await academy_service.get(db, organization_id=org.id, academy_id=academy_id)
    if academy is None:
        raise HTTPException(status_code=404, detail="Academy not found")
    payload = _academy_payload(academy)
    employee_id = await _employee_id(db, org, user)
    member = (
        await db.execute(
            select(AcademyCourse).where(
                AcademyCourse.organization_id == org.id,
                AcademyCourse.academy_id == academy.id,
            ).limit(0)
        )
    ).scalar_one_or_none()
    _ = member  # membership resolved via service
    members = await academy_service.my_academies(db, organization_id=org.id, employee_id=employee_id)
    payload["joined"] = any(m["id"] == academy.id for m in members)
    return payload


@router.post("/{academy_id}/courses", status_code=201)
async def add_course(
    academy_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    link = await academy_service.add_course(
        db, organization_id=org.id, academy_id=academy_id, course_id=payload["course_id"]
    )
    if link is None:
        raise HTTPException(status_code=404, detail="Academy or course not found")
    await db.commit()
    return {"id": link.id, "academy_id": academy_id, "course_id": payload["course_id"]}


@router.delete("/{academy_id}/courses/{course_id}")
async def remove_course(
    academy_id: str,
    course_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    removed = await academy_service.remove_course(
        db, organization_id=org.id, academy_id=academy_id, course_id=course_id
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Course link not found")
    await db.commit()
    return {"removed": True}


@router.post("/{academy_id}/join", status_code=201)
async def join(
    academy_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    membership = await academy_service.join(
        db, organization_id=org.id, academy_id=academy_id, employee_id=employee_id
    )
    if membership is None:
        raise HTTPException(status_code=404, detail="Academy not available")
    await db.commit()
    return {"id": membership.id, "academy_id": academy_id, "joined": True}


@router.post("/{academy_id}/leave")
async def leave(
    academy_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    removed = await academy_service.leave(
        db, organization_id=org.id, academy_id=academy_id, employee_id=employee_id
    )
    if not removed:
        raise HTTPException(status_code=404, detail="Membership not found")
    await db.commit()
    return {"left": True}
