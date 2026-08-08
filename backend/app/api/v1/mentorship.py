"""Mentorship API (Phase 10.6 — Mentorship Program).

Mentor profiles, AI-ranked mentor recommendations, mentorship lifecycle
(request/respond/session/feedback/completion) with progress tracking.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.learning.mentorship_service import mentorship_service
from app.models.employee import Employee
from app.models.mentorship import MentorProfile
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/learning/mentorship", tags=["Learning"])


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
async def my_profile(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    profile = (
        await db.execute(
            select(MentorProfile).where(
                MentorProfile.organization_id == org.id, MentorProfile.employee_id == employee_id
            )
        )
    ).scalar_one_or_none()
    if profile is None:
        return {"exists": False}
    return {
        "exists": True,
        "id": profile.id,
        "employee_id": profile.employee_id,
        "bio": profile.bio,
        "topics": profile.topics or [],
        "availability": profile.availability,
        "max_mentees": profile.max_mentees,
        "is_active": profile.active,
    }


@router.post("/profile")
async def create_profile(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    profile = await mentorship_service.create_profile(
        db, organization_id=org.id, employee_id=employee_id, data=payload
    )
    if profile is None:
        raise HTTPException(status_code=404, detail="Employee profile not found")
    await db.commit()
    return {"id": profile.id, "employee_id": profile.employee_id, "is_active": profile.active}


@router.get("/mentors")
async def list_mentors(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    category: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    return await mentorship_service.list_mentors(
        db, organization_id=org.id, topic=category or search, limit=limit
    )


@router.get("/mentors/recommend")
async def recommend_mentors(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    skill: Optional[str] = Query(None),
    limit: int = Query(5, ge=1, le=20),
):
    employee_id = await _employee_id(db, org, user)
    return await mentorship_service.recommend_mentors(
        db, organization_id=org.id, employee_id=employee_id, skills=skill, limit=limit
    )


@router.post("/mentors/{mentor_id}/request", status_code=201)
async def request_mentorship(
    mentor_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    employee_id = await _employee_id(db, org, user)
    mentorship = await mentorship_service.request(
        db, organization_id=org.id, mentor_id=mentor_id, mentee_id=employee_id,
        topic=payload.get("topic", "Career growth"),
        goals=payload.get("goals"),
        requested_by=payload.get("requested_by", "mentee"),
    )
    if mentorship is None:
        raise HTTPException(status_code=400, detail="Cannot request this mentor")
    await db.commit()
    return {"id": mentorship.id, "status": mentorship.status, "topic": mentorship.topic}


@router.get("/requests")
async def list_requests(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("learning:read")),
    db: AsyncSession = Depends(get_db),
    role: str = Query("mentee"),
    status: Optional[str] = Query(None),
):
    employee_id = await _employee_id(db, org, user)
    return await mentorship_service.list_for(
        db, organization_id=org.id, employee_id=employee_id, role=role, status=status
    )


@router.post("/{mentorship_id}/respond")
async def respond(
    mentorship_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor_id = await _employee_id(db, org, user)
    mentorship = await mentorship_service.respond(
        db, organization_id=org.id, mentorship_id=mentorship_id,
        actor_id=actor_id, accept=bool(payload.get("accept", True)),
    )
    if mentorship is None:
        raise HTTPException(status_code=404, detail="Mentorship request not found")
    await db.commit()
    return {"id": mentorship.id, "status": mentorship.status}


@router.post("/{mentorship_id}/sessions", status_code=201)
async def add_session(
    mentorship_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor_id = await _employee_id(db, org, user)
    session = await mentorship_service.add_session(
        db, organization_id=org.id, mentorship_id=mentorship_id, actor_id=actor_id,
        title=payload.get("title", "Mentorship session"),
        notes=payload.get("notes"),
        kind=payload.get("kind", "call"),
        occurred_at=payload.get("occurred_at"),
        duration_minutes=int(payload.get("duration_minutes", 30)),
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Active mentorship not found")
    await db.commit()
    return {"id": session.id, "title": session.title, "kind": session.kind}


@router.post("/{mentorship_id}/feedback", status_code=201)
async def add_feedback(
    mentorship_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    author_id = await _employee_id(db, org, user)
    feedback = await mentorship_service.add_feedback(
        db, organization_id=org.id, mentorship_id=mentorship_id, author_id=author_id,
        rating=int(payload.get("rating", 5)),
        comment=payload.get("comment"),
        session_id=payload.get("session_id"),
    )
    if feedback is None:
        raise HTTPException(status_code=404, detail="Mentorship not found")
    await db.commit()
    return {"id": feedback.id, "rating": feedback.rating}


@router.post("/{mentorship_id}/complete")
async def complete_mentorship(
    mentorship_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    actor_id = await _employee_id(db, org, user)
    mentorship = await mentorship_service.complete(
        db, organization_id=org.id, mentorship_id=mentorship_id, actor_id=actor_id
    )
    if mentorship is None:
        raise HTTPException(status_code=404, detail="Mentorship not found")
    await db.commit()
    return {"id": mentorship.id, "status": mentorship.status, "progress": mentorship.progress}
