"""Expertise API — skills catalog, scoring, experts, successors, gaps (Phase 2)."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.people.expertise_service import expertise_service
from app.schemas.people import (
    ExpertiseScoreOut,
    ExpertOut,
    MentorOut,
    SkillCreate,
    SkillGap,
    SkillOut,
    SuccessorOut,
)

router = APIRouter(prefix="/expertise", tags=["Expertise"])


# ------------------------------------------------------------------ skills catalog

@router.get("/skills", response_model=list[SkillOut])
async def list_skills(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("expertise:read")),
    db: AsyncSession = Depends(get_db),
    category: str = Query(None),
    search: str = Query(None),
):
    skills = await expertise_service.list_skills(
        db, organization_id=org.id, category=category, search=search
    )
    return [
        SkillOut.model_validate(
            {
                "id": s.id, "name": s.name, "category": s.category,
                "description": s.description,
                "employees_count": getattr(s, "employees_count", 0),
            }
        )
        for s in skills
    ]


@router.post("/skills", response_model=SkillOut, status_code=201)
async def create_skill(
    payload: SkillCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("expertise:read")),
    db: AsyncSession = Depends(get_db),
):
    skill = await expertise_service.create_skill(db, organization_id=org.id, data=payload.model_dump())
    await db.commit()
    return SkillOut.model_validate(
        {
            "id": skill.id, "name": skill.name, "category": skill.category,
            "description": skill.description, "employees_count": 0,
        }
    )


@router.get("/skills/categories", response_model=list[str])
async def skill_categories(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("expertise:read")),
    db: AsyncSession = Depends(get_db),
):
    return await expertise_service.categories(db, organization_id=org.id)


# ------------------------------------------------------------------ experts & scores

@router.get("/experts", response_model=list[ExpertOut])
async def experts(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("expertise:read")),
    db: AsyncSession = Depends(get_db),
    skill_id: str = Query(None),
    skill_name: str = Query(None),
    category: str = Query(None),
    limit: int = Query(10, ge=1, le=50),
):
    return await expertise_service.experts(
        db, organization_id=org.id, skill_id=skill_id, skill_name=skill_name,
        category=category, limit=limit,
    )


@router.get("/employees/{employee_id}", response_model=list[ExpertiseScoreOut])
async def employee_expertise(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("expertise:read")),
    db: AsyncSession = Depends(get_db),
):
    scores = await expertise_service.employee_scores(db, organization_id=org.id, employee_id=employee_id)
    return [
        ExpertiseScoreOut.model_validate(
            {
                "id": s.id,
                "employee_id": s.employee_id,
                "skill_id": s.skill_id,
                "skill_name": s.skill.name,
                "category": s.skill.category,
                "score": s.score,
                "level": s.level,
                "years_experience": s.years_experience,
                "factors": s.factors,
                "updated_at": s.updated_at,
            }
        )
        for s in scores
    ]


@router.post("/employees/{employee_id}/recompute", response_model=list[ExpertiseScoreOut])
async def recompute_expertise(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("expertise:read")),
    db: AsyncSession = Depends(get_db),
):
    scores = await expertise_service.recompute_for_employee(
        db, organization_id=org.id, employee_id=employee_id
    )
    await db.commit()
    return [
        ExpertiseScoreOut.model_validate(
            {
                "id": s.id,
                "employee_id": s.employee_id,
                "skill_id": s.skill_id,
                "skill_name": s.skill.name,
                "category": s.skill.category,
                "score": s.score,
                "level": s.level,
                "years_experience": s.years_experience,
                "factors": s.factors,
                "updated_at": s.updated_at,
            }
        )
        for s in scores
    ]


# ------------------------------------------------------------------ successors & mentors

@router.get("/successors/{employee_id}", response_model=list[SuccessorOut])
async def successors(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("expertise:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(5, ge=1, le=20),
):
    try:
        return await expertise_service.successors(
            db, organization_id=org.id, employee_id=employee_id, limit=limit
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/mentors/{employee_id}", response_model=list[MentorOut])
async def mentors(
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("expertise:read")),
    db: AsyncSession = Depends(get_db),
    skill_id: str = Query(None),
    skill_name: str = Query(None),
    limit: int = Query(5, ge=1, le=20),
):
    return await expertise_service.mentors_for(
        db, organization_id=org.id, employee_id=employee_id,
        skill_id=skill_id, skill_name=skill_name, limit=limit,
    )


# ------------------------------------------------------------------ gaps

@router.get("/gaps", response_model=list[SkillGap])
async def skill_gaps(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("expertise:read")),
    db: AsyncSession = Depends(get_db),
):
    return await expertise_service.skill_gaps(db, organization_id=org.id)
