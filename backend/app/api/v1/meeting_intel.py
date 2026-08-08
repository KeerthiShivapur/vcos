"""Meeting intelligence APIs (Phase 6.10–6.16) — AI finalize, decisions,
attendance intelligence, org analytics, and calendar intelligence suggestions.

IMPORTANT: this router is included BEFORE the meetings router so the static
paths /meetings/suggest and /meeting-analytics win over /meetings/{meeting_id}.
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.collaboration.ai_meeting_service import ai_meeting_service
from app.collaboration.analytics_service import meeting_analytics_service
from app.collaboration.attendance_service import attendance_service
from app.collaboration.collab_base import emit_and_audit
from app.collaboration.scheduler_service import meeting_scheduler_service
from app.collaboration.session_service import session_service
from app.db.database import get_db
from app.models.collaboration import MeetingDecision
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.work.meeting_service import meeting_service

router = APIRouter(tags=["Meeting Intelligence"])


class DecisionCreate(BaseModel):
    content: str = Field(min_length=2, max_length=2000)
    status: str = Field(default="draft", pattern="^(draft|confirmed)$")


class FinalizeBody(BaseModel):
    pass


class SuggestBody(BaseModel):
    employee_ids: list[str] = []
    duration_minutes: int = Field(default=60, ge=5, le=480)
    days: int = Field(default=7, ge=1, le=30)
    start_at: Optional[datetime] = None
    end_at: Optional[datetime] = None
    capacity: int = Field(default=8, ge=1)


async def _meeting_or_404(db: AsyncSession, org: Organization, meeting_id: str):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return meeting


# --------------------------------------------------------------------------- org analytics (6.14)

@router.get("/meeting-analytics", response_model=dict)
async def org_meeting_analytics(
    days: int = 30,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    return await meeting_analytics_service.overview(db, organization_id=org.id, days=min(days, 365))


# --------------------------------------------------------------------------- calendar intelligence (6.15)

@router.get("/meetings/suggest", response_model=dict)
async def meeting_suggestions(
    employee_ids: str = "",
    duration_minutes: int = 60,
    days: int = 7,
    capacity: int = 8,
    start_at: Optional[datetime] = None,
    end_at: Optional[datetime] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    """One-stop scheduling intelligence: conflicts, free slots, room picks, timezone view."""
    ids = [e for e in employee_ids.split(",") if e] if employee_ids else []
    conflicts = {}
    if start_at and end_at:
        conflicts = await meeting_scheduler_service.conflicts(
            db, organization_id=org.id, start_at=start_at, end_at=end_at, employee_ids=ids or None
        )
    slots = await meeting_scheduler_service.suggest_slots(
        db,
        organization_id=org.id,
        employee_ids=ids,
        duration_minutes=duration_minutes,
        start_date=start_at,
        days=days,
    )
    rooms = []
    if start_at and end_at:
        rooms = await meeting_scheduler_service.suggest_rooms(
            db, organization_id=org.id, start_at=start_at, end_at=end_at, capacity=capacity
        )
    timezones = await meeting_scheduler_service.optimize_timezone(
        db, organization_id=org.id, employee_ids=ids
    )
    return {
        "conflicts": conflicts,
        "free_slots": slots,
        "rooms": rooms,
        "timezones": timezones,
    }


# --------------------------------------------------------------------------- attendance intelligence (6.11)

@router.get("/meetings/{meeting_id}/attendance", response_model=dict)
async def meeting_attendance(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _meeting_or_404(db, org, meeting_id)
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    if session is None:
        raise HTTPException(404, "No session for this meeting")
    metrics = await attendance_service.metrics(
        db, organization_id=org.id, meeting=meeting, session=session
    )
    snapshot = await attendance_service.for_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    return {"live": metrics, "snapshot": attendance_service.payload(snapshot) if snapshot else None}


# --------------------------------------------------------------------------- decisions (6.10)

@router.get("/meetings/{meeting_id}/decisions", response_model=list[dict])
async def list_decisions(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    await _meeting_or_404(db, org, meeting_id)
    rows = (
        await db.execute(
            select(MeetingDecision)
            .where(
                MeetingDecision.organization_id == org.id,
                MeetingDecision.meeting_id == meeting_id,
            )
            .order_by(MeetingDecision.created_at.desc())
        )
    ).scalars().all()
    return [_decision_payload(row) for row in rows]


@router.post("/meetings/{meeting_id}/decisions", response_model=dict, status_code=201)
async def create_decision(
    meeting_id: str,
    payload: DecisionCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _meeting_or_404(db, org, meeting_id)
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    decision = MeetingDecision(
        organization_id=org.id,
        meeting_id=meeting.id,
        session_id=session.id if session else None,
        content=payload.content,
        made_by=actor.id if actor else None,
        source="manual",
        status=payload.status,
    )
    db.add(decision)
    await db.flush()
    await db.commit()
    await emit_and_audit(
        db,
        organization_id=org.id,
        name="decision.recorded",
        actor=actor,
        actor_user_id=user.id,
        ip_address=get_client_ip(request),
        payload={"meeting_id": meeting.id, "decision_id": decision.id},
        resource_type="meeting_decision",
        resource_id=decision.id,
    )
    await db.commit()
    return _decision_payload(decision)


@router.patch("/meetings/{meeting_id}/decisions/{decision_id}", response_model=dict)
async def update_decision(
    meeting_id: str,
    decision_id: str,
    payload: DecisionCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    decision = (
        await db.execute(
            select(MeetingDecision).where(
                MeetingDecision.organization_id == org.id,
                MeetingDecision.meeting_id == meeting_id,
                MeetingDecision.id == decision_id,
            )
        )
    ).scalar_one_or_none()
    if decision is None:
        raise HTTPException(404, "Decision not found")
    decision.content = payload.content
    decision.status = payload.status
    await db.commit()
    return _decision_payload(decision)


@router.delete("/meetings/{meeting_id}/decisions/{decision_id}", response_model=Message)
async def delete_decision(
    meeting_id: str,
    decision_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    decision = (
        await db.execute(
            select(MeetingDecision).where(
                MeetingDecision.organization_id == org.id,
                MeetingDecision.meeting_id == meeting_id,
                MeetingDecision.id == decision_id,
            )
        )
    ).scalar_one_or_none()
    if decision is None:
        raise HTTPException(404, "Decision not found")
    await db.delete(decision)
    await db.commit()
    return Message(message="Decision deleted")


# --------------------------------------------------------------------------- AI finalize (6.10/6.13)

@router.post("/meetings/{meeting_id}/ai/finalize", response_model=dict)
async def finalize_meeting_intelligence(
    meeting_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Run end-of-meeting AI: summary, action items -> tasks, decisions, analytics."""
    meeting = await _meeting_or_404(db, org, meeting_id)
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    result = await ai_meeting_service.finalize(
        db,
        organization_id=org.id,
        meeting=meeting,
        session=session,
        actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return result


def _decision_payload(decision: MeetingDecision) -> dict:
    return {
        "id": decision.id,
        "meeting_id": decision.meeting_id,
        "session_id": decision.session_id,
        "content": decision.content,
        "made_by": decision.made_by,
        "source": decision.source,
        "status": decision.status,
        "created_at": decision.created_at,
    }
