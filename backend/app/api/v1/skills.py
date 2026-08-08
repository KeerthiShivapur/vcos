"""Skills API (Phase 10.4 — Skills Graph, Gap Analysis, Organization Skill Map).

Builds on the Phase 3 expertise engine (Skill / EmployeeSkill / ExpertiseScore)
with learning-derived boosts, gap detection against role frameworks and the
Organization Skill Map snapshots.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.learning.skill_service import skill_service
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning/skills", tags=["Learning"])


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


@router.get("")
async def skill_graph(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
):
    employee = employee_id or await _employee_id(db, org, user)
    return await skill_service.graph(db, organization_id=org.id, employee_id=employee)


@router.get("/org-map")
async def org_skill_map(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    snapshot_date: Optional[str] = Query(None),
):
    return await skill_service.org_skill_map(db, organization_id=org.id, snapshot_date=snapshot_date)


@router.post("/snapshot/refresh")
async def refresh_snapshot(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    snapshot = await skill_service.refresh_snapshot(db, organization_id=org.id)
    await db.commit()
    if snapshot is None:
        return {"snapshot_id": None, "date": None, "skill_count": 0}
    from sqlalchemy import func as _func

    from app.models.skill_gap import SkillSnapshot
    count = (
        await db.execute(
            select(_func.count(SkillSnapshot.id)).where(
                SkillSnapshot.organization_id == org.id,
                SkillSnapshot.snapshot_date == snapshot.snapshot_date,
            )
        )
    ).scalar() or 0
    return {"snapshot_id": snapshot.id, "date": str(snapshot.snapshot_date), "skill_count": count}


@router.get("/gaps")
async def list_gaps(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    status: str = Query("open"),
    employee_id: Optional[str] = Query(None),
):
    employee = employee_id or await _employee_id(db, org, user)
    return await skill_service.list_gaps(
        db, organization_id=org.id, employee_id=employee, status=status
    )


@router.post("/gaps/refresh")
async def refresh_gaps(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
):
    employee = employee_id or await _employee_id(db, org, user)
    gaps = await skill_service.detect_gaps(db, organization_id=org.id, employee_id=employee)
    await db.commit()
    return {"employee_id": employee, "gaps": len(gaps)}


@router.post("/gaps/{gap_id}/close")
async def close_gap(
    gap_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    status: str = Query("closed"),
):
    gap = await skill_service.close_gap(
        db, organization_id=org.id, gap_id=gap_id, status=status
    )
    if gap is None:
        raise HTTPException(status_code=404, detail="Skill gap not found")
    await db.commit()
    return {"id": gap.id, "skill_name": gap.skill_name, "status": gap.status}


@router.get("/who/{skill_name}")
async def who_has_skill(
    skill_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    min_level: int = Query(3, ge=1, le=5),
    limit: int = Query(20, ge=1, le=50),
):
    return await skill_service.who_has_skill(
        db, organization_id=org.id, skill_name=skill_name,
        min_level=min_level, limit=limit,
    )


@router.get("/mentors/{skill_name}")
async def can_mentor(
    skill_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    min_level: int = Query(4, ge=1, le=5),
):
    return await skill_service.can_mentor(
        db, organization_id=org.id, skill_name=skill_name, min_level=min_level
    )


@router.post("/{skill_name}/boost")
async def boost_skill(
    skill_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    payload: Optional[dict[str, Any]] = None,
):
    employee_id = (payload or {}).get("employee_id") or await _employee_id(db, org, user)
    points = float((payload or {}).get("points", 1.0))
    reason = (payload or {}).get("reason")
    emp_skill = await skill_service.boost_skill(
        db, organization_id=org.id, employee_id=employee_id,
        skill_name=skill_name, points=points, source="manual", reason=reason,
    )
    await db.commit()
    return {"skill_name": skill_name, "level": emp_skill.level, "verified": emp_skill.verified}


@router.post("/{skill_name}/set-level")
async def set_skill_level(
    skill_name: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:manage")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = payload.get("employee_id") or await _employee_id(db, org, user)
    level = int(payload.get("level", 3))
    emp_skill = await skill_service.set_skill_level(
        db, organization_id=org.id, employee_id=employee_id,
        skill_name=skill_name, level=level, source="manual",
    )
    await db.commit()
    return {"skill_name": skill_name, "level": emp_skill.level, "verified": emp_skill.verified}
