"""Learning API (Phase 10.1 — Learning Foundation).

Personal learning profile + learning history + the learning dashboard
aggregate (profile, in-progress courses, recommended learning, goals,
certificates, mentor, upcoming assessments, career progress, AI
recommendations).
"""

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.core.timeutils import utcnow
from app.db.database import get_db
from app.learning.ai_service import learning_ai_service
from app.learning.career_service import career_service
from app.learning.certification_service import certification_service
from app.learning.course_service import course_service
from app.learning.learning_path_service import learning_path_service
from app.learning.profile_service import profile_service
from app.learning.recommendation_service import recommendation_service
from app.models.employee import Employee
from app.models.learning_recommendation import LearningRecommendation
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning", tags=["Learning"])


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


@router.get("/profile")
async def get_profile(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    profile = await profile_service.get_profile(db, organization_id=org.id, employee_id=employee_id)
    return {
        "id": profile.id,
        "employee_id": profile.employee_id,
        "learning_score": profile.learning_score,
        "level": profile.level,
        "career_stage": profile.career_stage,
        "preferred_learning": profile.preferred_learning,
        "weekly_learning_hours": profile.weekly_learning_hours,
        "completed_courses": profile.completed_courses,
        "certifications": profile.certifications,
        "mentor_id": profile.mentor_id,
        "last_learning_date": profile.last_learning_date.isoformat() if profile.last_learning_date else None,
        "career_goals": profile.career_goals or [],
        "learning_goals": profile.learning_goals or [],
    }


@router.patch("/profile")
async def update_profile(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    profile = await profile_service.update_profile(
        db, organization_id=org.id, employee_id=employee_id, data=payload
    )
    await db.commit()
    return {
        "id": profile.id,
        "learning_score": profile.learning_score,
        "career_stage": profile.career_stage,
        "preferred_learning": profile.preferred_learning,
        "weekly_learning_hours": profile.weekly_learning_hours,
        "career_goals": profile.career_goals or [],
        "learning_goals": profile.learning_goals or [],
    }


@router.get("/history")
async def learning_history(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    employee_id = await _employee_id(db, org, user)
    entries = await profile_service.history(db, organization_id=org.id, employee_id=employee_id, limit=limit)
    return [
        {
            "id": entry.id,
            "kind": entry.kind,
            "title": entry.title,
            "entity_id": entry.entity_id,
            "score": entry.score,
            "time_minutes": entry.time_minutes,
            "certificate_id": entry.certificate_id,
            "feedback": entry.feedback,
            "meta": entry.meta,
            "occurred_at": entry.occurred_at.isoformat(),
        }
        for entry in entries
    ]


@router.get("/dashboard")
async def learning_dashboard(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    """The Learning Dashboard aggregate for the authenticated employee."""
    employee_id = await _employee_id(db, org, user)
    profile = await profile_service.get_profile(db, organization_id=org.id, employee_id=employee_id)

    enrollments = await course_service.my_enrollments(db, organization_id=org.id, employee_id=employee_id)
    my_courses = []
    for enrollment in enrollments[:8]:
        course = await course_service.get_course(db, organization_id=org.id, course_id=enrollment.course_id)
        if course is None:
            continue
        my_courses.append(
            {
                "id": course.id,
                "title": course.title,
                "category": course.category,
                "difficulty": course.difficulty,
                "duration_minutes": course.duration_minutes,
                "progress": enrollment.progress,
                "status": enrollment.status,
                "enrollment_id": enrollment.id,
            }
        )

    gaps = await skill_service_list_gaps(db, organization_id=org.id, employee_id=employee_id)
    gap_skills = [gap.skill_name for gap in gaps]
    recommended_courses = [
        {"id": course.id, "title": course.title, "category": course.category, "difficulty": course.difficulty}
        for course in await course_service.recommended_for(
            db, organization_id=org.id, employee_id=employee_id, skill_names=gap_skills, limit=6
        )
    ]

    feed = await recommendation_service.list(
        db, organization_id=org.id, employee_id=employee_id, statuses=("pending", "accepted"), limit=8
    )
    recommendations = [
        {
            "id": item.id,
            "kind": item.kind,
            "title": item.title,
            "description": item.description,
            "reason": item.reason,
            "score": item.score,
            "source": item.source,
            "entity_id": item.entity_id,
            "status": item.status,
        }
        for item in feed
    ]

    certificates = await certification_service.my_certifications(db, organization_id=org.id, employee_id=employee_id)
    career = await career_service.progress_for(db, organization_id=org.id, employee_id=employee_id)
    paths = await learning_path_service.my_enrollments(db, organization_id=org.id, employee_id=employee_id)
    mentor = None
    if profile.mentor_id:
        mentor_employee = await db.get(Employee, profile.mentor_id)
        mentor = {
            "employee_id": mentor_employee.id,
            "name": mentor_employee.full_name,
            "designation": mentor_employee.designation,
        } if mentor_employee else None

    upcoming = await _upcoming_assessments(db, org, user, employee_id)

    return {
        "profile": {
            "learning_score": profile.learning_score,
            "level": profile.level,
            "career_stage": profile.career_stage,
            "completed_courses": profile.completed_courses,
            "certifications": profile.certifications,
            "weekly_learning_hours": profile.weekly_learning_hours,
            "learning_goals": profile.learning_goals or [],
        },
        "my_courses": my_courses,
        "recommended_courses": recommended_courses,
        "recommendations": recommendations,
        "certificates": certificates,
        "mentor": mentor,
        "career": career,
        "learning_paths": [
            {
                "path_id": enrollment.path_id,
                "title": path.title if (path := await learning_path_service.get_path(db, organization_id=org.id, path_id=enrollment.path_id)) else None,
                "progress": enrollment.progress,
                "status": enrollment.status,
            }
            for enrollment in paths
        ],
        "upcoming_assessments": upcoming,
        "skill_gaps": [
            {"skill": gap.skill_name, "priority": gap.priority, "gap": gap.gap}
            for gap in gaps[:8]
        ],
        "trending": [
            {"id": course.id, "title": course.title}
            for course in await course_service.trending(db, organization_id=org.id, limit=5)
        ],
    }


def skill_service_list_gaps(db: AsyncSession, **kwargs):
    from app.learning.skill_service import skill_service
    return skill_service.list_gaps(db, **kwargs)


async def _upcoming_assessments(db: AsyncSession, org: Organization, user: User, employee_id: str) -> list[dict[str, Any]]:
    from app.learning.assessment_service import assessment_service
    attempts = await assessment_service.my_attempts(db, organization_id=org.id, employee_id=employee_id)
    return [
        {
            "id": attempt["id"],
            "title": attempt["assessment_title"],
            "kind": attempt["kind"],
            "status": attempt["status"],
        }
        for attempt in attempts
        if attempt["status"] in ("assigned", "in_progress", "submitted")
    ][:5]


# ------------------------------------------------------------------ AI companion

@router.post("/ai/ask")
async def ai_companion(
    payload: dict[str, str],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    """The AI Learning Companion: answers learning questions with context."""
    question = payload.get("question", "")
    if not question.strip():
        raise HTTPException(status_code=400, detail="question is required")
    employee_id = await _employee_id(db, org, user)
    answer = await learning_ai_service.answer(
        db, organization_id=org.id, employee_id=employee_id, question=question
    )
    await db.commit()
    return answer
