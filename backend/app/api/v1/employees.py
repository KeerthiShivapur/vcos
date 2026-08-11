"""Employees API — the living people directory (Phase 2)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.people.employee_service import employee_service
from app.schemas.common import Message
from app.schemas.people import (
    AchievementCreate,
    AchievementOut,
    CertificationCreate,
    CertificationOut,
    EmployeeCreate,
    EmployeeOut,
    EmployeeSkillAdd,
    EmployeeSkillOut,
    EmployeeSummary,
    EmployeeUpdate,
    TimelineOut,
)

router = APIRouter(prefix="/employees", tags=["Employees"])


async def _get_employee_or_404(db: AsyncSession, org: Organization, employee_id: str, viewer: Optional[str] = None):
    employee = await employee_service.get(
        db, organization_id=org.id, employee_id=employee_id, viewer_employee_id=viewer
    )
    if employee is None:
        raise HTTPException(404, "Employee not found")
    return employee


def _summary_payload(emp) -> dict[str, Any]:
    return {
        "id": emp.id,
        "employee_number": emp.employee_number,
        "first_name": emp.first_name,
        "last_name": emp.last_name,
        "display_name": emp.display_name,
        "full_name": emp.full_name,
        "email": emp.email,
        "user_id": emp.user_id,
        "designation": emp.designation,
        "department_id": emp.department_id,
        "department_name": getattr(emp, "department_name", None),
        "team_id": emp.team_id,
        "team_name": getattr(emp, "team_name", None),
        "manager_id": emp.manager_id,
        "manager_name": getattr(emp, "manager_name", None),
        "location_id": emp.location_id,
        "location_name": getattr(emp, "location_name", None),
        "employment_type": emp.employment_type,
        "joining_date": emp.joining_date,
        "status": emp.status,
        "timezone": emp.timezone,
        "expertise_score": emp.expertise_score,
        "profile_completion": getattr(emp, "profile_completion", 0),
        "availability_status": getattr(emp, "availability_status", None),
        "presence_status": getattr(emp, "presence_status", None),
        "is_online": getattr(emp, "is_online", False),
        "top_skills": getattr(emp, "top_skills", []),
        "is_favorite": getattr(emp, "is_favorite", False),
    }


def _employee_payload(emp) -> dict[str, Any]:
    payload = _summary_payload(emp)
    payload.update(
        {
            "user_id": emp.user_id,
            "phone": emp.phone,
            "language": emp.language,
            "bio": emp.bio,
            "emergency_contact": emp.emergency_contact,
            "business_unit_id": emp.business_unit_id,
            "business_unit_name": getattr(emp, "business_unit_name", None),
            "ai_summary": emp.ai_summary,
            "skills": [
                {
                    "id": row.id,
                    "skill_id": row.skill_id,
                    "name": name,
                    "category": category,
                    "level": row.level,
                    "years_experience": row.years_experience,
                    "verified": row.verified,
                }
                for row, name, category in getattr(emp, "_skill_rows", [])
            ],
            "certifications": [
                {
                    "id": c.id,
                    "name": c.name,
                    "issuer": c.issuer,
                    "credential_id": c.credential_id,
                    "issue_date": c.issue_date,
                    "expiry_date": c.expiry_date,
                    "verified": c.verified,
                }
                for c in getattr(emp, "_certifications", [])
            ],
            "achievements": [
                {
                    "id": a.id,
                    "kind": a.kind,
                    "title": a.title,
                    "description": a.description,
                    "achieved_on": a.achieved_on,
                }
                for a in getattr(emp, "_achievements", [])
            ],
            "timeline_count": getattr(emp, "timeline_count", 0),
            "reports_count": getattr(emp, "reports_count", 0),
            "created_at": emp.created_at,
            "updated_at": emp.updated_at,
        }
    )
    return payload


@router.get("", response_model=list[EmployeeSummary])
async def list_employees(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:read")),
    db: AsyncSession = Depends(get_db),
    search: str = Query(None),
    department_id: str = Query(None),
    team_id: str = Query(None),
    location_id: str = Query(None),
    business_unit_id: str = Query(None),
    skill: str = Query(None),
    availability: str = Query(None),
    presence: str = Query(None),
    status: str = Query(None),
    sort: str = Query("name"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    viewer = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    employees, _ = await employee_service.list(
        db,
        organization_id=org.id,
        viewer_employee_id=viewer.id if viewer else None,
        search=search,
        department_id=department_id,
        team_id=team_id,
        location_id=location_id,
        business_unit_id=business_unit_id,
        skill=skill,
        availability=availability,
        presence=presence,
        status=status,
        sort=sort,
        page=page,
        page_size=page_size,
    )
    return [EmployeeSummary.model_validate(_summary_payload(e)) for e in employees]


@router.post("", response_model=EmployeeOut, status_code=201)
async def create_employee(
    payload: EmployeeCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:hire")),
    db: AsyncSession = Depends(get_db),
):
    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        employee = await employee_service.create(
            db,
            organization_id=org.id,
            data=payload.model_dump(exclude_unset=True),
            actor=actor,
            ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    employee = await employee_service.get(db, organization_id=org.id, employee_id=employee.id, viewer_employee_id=actor.id if actor else None)
    return EmployeeOut.model_validate(_employee_payload(employee))


@router.get("/me", response_model=EmployeeOut)
async def my_employee(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:profile")),
    db: AsyncSession = Depends(get_db),
):
    employee = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if employee is None:
        raise HTTPException(404, "No employee record for this user")
    employee = await employee_service.get(db, organization_id=org.id, employee_id=employee.id, viewer_employee_id=employee.id)
    return EmployeeOut.model_validate(_employee_payload(employee))


@router.get("/favorites", response_model=list[EmployeeSummary])
async def my_favorites(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("favorites:manage")),
    db: AsyncSession = Depends(get_db),
):
    viewer = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if viewer is None:
        raise HTTPException(404, "No employee record for this user")
    favorites = await employee_service.favorites(db, organization_id=org.id, employee_id=viewer.id)
    return [EmployeeSummary.model_validate(_summary_payload(e)) for e in favorites]


@router.get("/{employee_id}", response_model=EmployeeOut)
async def get_employee(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:read")),
    db: AsyncSession = Depends(get_db),
):
    viewer = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    employee = await _get_employee_or_404(db, org, employee_id, viewer.id if viewer else None)
    return EmployeeOut.model_validate(_employee_payload(employee))


@router.patch("/{employee_id}", response_model=EmployeeOut)
async def update_employee(
    employee_id: str,
    payload: EmployeeUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    employee = await _get_employee_or_404(db, org, employee_id, actor.id if actor else None)
    try:
        employee = await employee_service.update(
            db,
            organization_id=org.id,
            employee=employee,
            data=payload.model_dump(exclude_unset=True),
            actor=actor,
            ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    employee = await employee_service.get(db, organization_id=org.id, employee_id=employee.id, viewer_employee_id=actor.id if actor else None)
    return EmployeeOut.model_validate(_employee_payload(employee))


@router.post("/{employee_id}/archive", response_model=EmployeeOut)
async def archive_employee(
    employee_id: str,
    request: Request,
    payload: dict = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
):
    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    employee = await _get_employee_or_404(db, org, employee_id, actor.id if actor else None)
    employee = await employee_service.archive(
        db,
        organization_id=org.id,
        employee=employee,
        actor=actor,
        ip_address=get_client_ip(request),
        reason=(payload or {}).get("reason"),
    )
    await db.commit()
    return EmployeeOut.model_validate(_employee_payload(employee))


@router.get("/{employee_id}/timeline", response_model=list[TimelineOut])
async def employee_timeline(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    await _get_employee_or_404(db, org, employee_id)
    return await employee_service.timeline(db, organization_id=org.id, employee_id=employee_id, limit=limit)


@router.get("/{employee_id}/reports", response_model=list[EmployeeSummary])
async def direct_reports(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:read")),
    db: AsyncSession = Depends(get_db),
):
    await _get_employee_or_404(db, org, employee_id)
    employees = await employee_service.direct_reports(db, organization_id=org.id, employee_id=employee_id)
    return [EmployeeSummary.model_validate(_summary_payload(e)) for e in employees]


@router.get("/{employee_id}/colleagues", response_model=list[EmployeeSummary])
async def colleagues(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:read")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _get_employee_or_404(db, org, employee_id)
    employees = await employee_service.colleagues(db, organization_id=org.id, employee=employee)
    return [EmployeeSummary.model_validate(_summary_payload(e)) for e in employees]


# ------------------------------------------------------------------ favorites

@router.put("/{employee_id}/favorite", response_model=Message)
async def add_favorite(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("favorites:manage")),
    db: AsyncSession = Depends(get_db),
):
    viewer = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if viewer is None:
        raise HTTPException(404, "No employee record for this user")
    await _get_employee_or_404(db, org, employee_id)
    await employee_service.add_favorite(db, organization_id=org.id, employee_id=viewer.id, target_employee_id=employee_id)
    await db.commit()
    return Message(message="Added to favorites")


@router.delete("/{employee_id}/favorite", response_model=Message)
async def remove_favorite(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("favorites:manage")),
    db: AsyncSession = Depends(get_db),
):
    viewer = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if viewer is None:
        raise HTTPException(404, "No employee record for this user")
    await employee_service.remove_favorite(db, organization_id=org.id, employee_id=viewer.id, target_employee_id=employee_id)
    await db.commit()
    return Message(message="Removed from favorites")


# ------------------------------------------------------------------ skills

@router.post("/{employee_id}/skills", response_model=EmployeeSkillOut, status_code=201)
async def add_skill(
    employee_id: str,
    payload: EmployeeSkillAdd,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _get_employee_or_404(db, org, employee_id)
    try:
        row = await employee_service.add_skill(
            db,
            organization_id=org.id,
            employee=employee,
            skill_id=payload.skill_id,
            name=payload.name,
            level=payload.level,
            years_experience=payload.years_experience,
            verified=payload.verified,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    from app.models.skill import Skill as SkillModel

    skill = await db.get(SkillModel, row.skill_id)
    await db.commit()
    return EmployeeSkillOut(
        id=row.id,
        skill_id=row.skill_id,
        name=skill.name,
        category=skill.category,
        level=row.level,
        years_experience=row.years_experience,
        verified=row.verified,
    )


@router.delete("/{employee_id}/skills/{skill_id}", response_model=Message)
async def remove_skill(
    employee_id: str,
    skill_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _get_employee_or_404(db, org, employee_id)
    await employee_service.remove_skill(db, organization_id=org.id, employee=employee, skill_id=skill_id)
    await db.commit()
    return Message(message="Skill removed")


# ------------------------------------------------------------------ certifications

@router.post("/{employee_id}/certifications", response_model=CertificationOut, status_code=201)
async def add_certification(
    employee_id: str,
    payload: CertificationCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _get_employee_or_404(db, org, employee_id)
    cert = await employee_service.add_certification(
        db, organization_id=org.id, employee=employee, data=payload.model_dump()
    )
    await db.commit()
    return CertificationOut.model_validate(cert)


@router.delete("/{employee_id}/certifications/{cert_id}", response_model=Message)
async def remove_certification(
    employee_id: str,
    cert_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _get_employee_or_404(db, org, employee_id)
    await employee_service.remove_certification(db, organization_id=org.id, employee=employee, cert_id=cert_id)
    await db.commit()
    return Message(message="Certification removed")


# ------------------------------------------------------------------ achievements

@router.post("/{employee_id}/achievements", response_model=AchievementOut, status_code=201)
async def add_achievement(
    employee_id: str,
    payload: AchievementCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _get_employee_or_404(db, org, employee_id)
    achievement = await employee_service.add_achievement(
        db, organization_id=org.id, employee=employee, data=payload.model_dump()
    )
    await db.commit()
    return AchievementOut.model_validate(achievement)


@router.delete("/{employee_id}/achievements/{achievement_id}", response_model=Message)
async def remove_achievement(
    employee_id: str,
    achievement_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("employees:manage")),
    db: AsyncSession = Depends(get_db),
):
    employee = await _get_employee_or_404(db, org, employee_id)
    await employee_service.remove_achievement(
        db, organization_id=org.id, employee=employee, achievement_id=achievement_id
    )
    await db.commit()
    return Message(message="Achievement removed")
