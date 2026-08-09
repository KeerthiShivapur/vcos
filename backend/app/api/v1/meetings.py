"""Meetings API — first-class meeting workspaces (Phase 3)."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.collaboration.collab_base import parse_json
from app.collaboration.live import live_hub
from app.collaboration.note_service import note_service
from app.collaboration.participant_service import participant_service
from app.collaboration.session_service import session_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.schemas.collaboration import (
    InviteBody,
    JoinBody,
    NoteCreate,
    NoteOut,
    NoteUpdate,
    ParticipantOut,
    SessionCreate,
    SessionOut,
)
from app.schemas.work import (
    ActionItemOut,
    AgendaItemOut,
    AttendeeOut,
    MeetingCreate,
    MeetingOut,
    MeetingUpdate,
)
from app.work.meeting_service import meeting_service

router = APIRouter(prefix="/meetings", tags=["Meetings"])


class RsvpBody(BaseModel):
    status: str = Field(pattern="^(accepted|declined|tentative)$")


class ActionItemCreate(BaseModel):
    title: str
    assignee_id: Optional[str] = None
    due_date: Optional[datetime] = None


def _meeting_payload(m) -> dict:
    return {
        "id": m.id,
        "title": m.title,
        "description": m.description,
        "meeting_type": m.meeting_type,
        "status": m.status,
        "organizer_id": m.organizer_id,
        "organizer_name": getattr(m, "organizer_name", None),
        "project_id": m.project_id,
        "goal_id": m.goal_id,
        "department_id": m.department_id,
        "team_id": m.team_id,
        "calendar_event_id": m.calendar_event_id,
        "room_id": m.room_id,
        "meeting_code": m.meeting_code,
        "timezone": m.timezone,
        "duration_minutes": m.duration_minutes,
        "start_at": m.start_at,
        "end_at": m.end_at,
        "location": m.location,
        "meeting_link": m.meeting_link,
        "transcript_summary": m.transcript_summary,
        "ai_summary": m.ai_summary,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def _session_payload(s) -> dict:
    participants = [ParticipantOut.model_validate(p) for p in getattr(s, "participants", None) or []]
    return {
        "id": s.id,
        "meeting_id": s.meeting_id,
        "room_id": s.room_id,
        "status": s.status,
        "meeting_code": s.meeting_code,
        "timezone": s.timezone,
        "max_participants": s.max_participants,
        "started_at": s.started_at,
        "ended_at": s.ended_at,
        "duration_seconds": s.duration_seconds,
        "is_recording": s.is_recording,
        "is_captions_enabled": s.is_captions_enabled,
        "is_translation_enabled": s.is_translation_enabled,
        "is_transcribing": s.is_transcribing,
        "settings": parse_json(s.settings),
        "participants": participants,
        "created_at": s.created_at,
        "updated_at": s.updated_at,
    }


@router.get("", response_model=list[MeetingOut])
async def list_meetings(
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    employee_id: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meetings = await meeting_service.list_all(
        db, organization_id=org.id, project_id=project_id, status=status, employee_id=employee_id,
    )
    return [MeetingOut.model_validate(_meeting_payload(m)) for m in meetings]


@router.post("", response_model=MeetingOut, status_code=201)
async def create_meeting(
    payload: MeetingCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    data = payload.model_dump(exclude_unset=True)
    if "agenda" in data:
        data["agenda"] = [item.model_dump() if hasattr(item, "model_dump") else item for item in data["agenda"]]
    try:
        meeting = await meeting_service.create(
            db, organization_id=org.id, data=data, actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting.id)
    return MeetingOut.model_validate(_meeting_payload(meeting))


@router.get("/upcoming", response_model=list[dict])
async def upcoming_meetings(
    scope: str = "organization",
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    """Upcoming/live meetings with session context (scope: personal|department|organization)."""
    from app.people.employee_service import employee_service

    if scope not in ("personal", "department", "organization"):
        raise HTTPException(400, "scope must be personal, department or organization")
    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    meetings = await session_service.upcoming(
        db,
        organization_id=org.id,
        employee_id=actor.id if actor else None,
        scope=scope,
        from_date=from_date,
        to_date=to_date,
    )
    out = []
    for meeting in meetings:
        item = _meeting_payload(meeting)
        item["session"] = _session_payload(meeting.session) if getattr(meeting, "session", None) else None
        out.append(item)
    return out


@router.get("/code/{code}", response_model=dict)
async def meeting_by_code(
    code: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    """Resolve a join code to its meeting + live session."""
    session = await session_service.by_code(db, organization_id=org.id, code=code)
    if session is None:
        raise HTTPException(404, "No meeting found for this join code")
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=session.meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    item = _meeting_payload(meeting)
    item["session"] = _session_payload(session)
    return item


@router.get("/{meeting_id}", response_model=MeetingOut)
async def get_meeting(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return MeetingOut.model_validate(_meeting_payload(meeting))


@router.patch("/{meeting_id}", response_model=MeetingOut)
async def update_meeting(
    meeting_id: str,
    payload: MeetingUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        meeting = await meeting_service.update(
            db, organization_id=org.id, meeting=meeting, data=payload.model_dump(exclude_unset=True),
            actor=actor, ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return MeetingOut.model_validate(_meeting_payload(meeting))


@router.post("/{meeting_id}/complete", response_model=MeetingOut)
async def complete_meeting(
    meeting_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    meeting = await meeting_service.complete(
        db, organization_id=org.id, meeting=meeting, actor=actor, ip_address=get_client_ip(request),
    )
    await db.commit()
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    return MeetingOut.model_validate(_meeting_payload(meeting))


@router.delete("/{meeting_id}", response_model=Message)
async def delete_meeting(
    meeting_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    await meeting_service.delete(
        db, organization_id=org.id, meeting=meeting, actor=actor, ip_address=get_client_ip(request)
    )
    await db.commit()
    return Message(message="Meeting deleted")


# --------------------------------------------------------------------------- Attendees

@router.get("/{meeting_id}/attendees", response_model=list[AttendeeOut])
async def list_attendees(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return await meeting_service.attendees(db, organization_id=org.id, meeting_id=meeting_id)


@router.post("/{meeting_id}/attendees", response_model=AttendeeOut, status_code=201)
async def add_attendee(
    meeting_id: str,
    payload: dict,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    try:
        attendee = await meeting_service.add_attendee(
            db, organization_id=org.id, meeting_id=meeting_id,
            employee_id=payload["employee_id"], role=payload.get("role", "participant"),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    from app.models.employee import Employee

    emp = await db.get(Employee, attendee.employee_id)
    return AttendeeOut(
        id=attendee.id, employee_id=attendee.employee_id,
        name=emp.full_name if emp else "Unknown",
        designation=emp.designation if emp else None,
        avatar_url=emp.avatar_url if emp else None,
        role=attendee.role, status=attendee.status, rsvp_at=attendee.rsvp_at,
    )


@router.post("/{meeting_id}/rsvp", response_model=AttendeeOut)
async def rsvp(
    meeting_id: str,
    payload: RsvpBody,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    attendee = await meeting_service.set_rsvp(
        db, organization_id=org.id, meeting_id=meeting_id,
        employee_id=actor.id, status=payload.status,
    )
    if payload.status == "accepted":
        await session_service.accept_rsvp(db, organization_id=org.id, meeting=meeting, employee=actor)
    await db.commit()
    return AttendeeOut(
        id=attendee.id, employee_id=attendee.employee_id, name=actor.full_name,
        designation=actor.designation, avatar_url=actor.avatar_url,
        role=attendee.role, status=attendee.status, rsvp_at=attendee.rsvp_at,
    )


@router.delete("/{meeting_id}/attendees/{employee_id}", response_model=Message)
async def remove_attendee(
    meeting_id: str,
    employee_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    await meeting_service.remove_attendee(db, organization_id=org.id, meeting_id=meeting_id, employee_id=employee_id)
    await db.commit()
    return Message(message="Attendee removed")


# --------------------------------------------------------------------------- Agenda

@router.get("/{meeting_id}/agenda", response_model=list[AgendaItemOut])
async def list_agenda(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return await meeting_service.agenda(db, organization_id=org.id, meeting_id=meeting_id)


@router.post("/{meeting_id}/agenda", response_model=AgendaItemOut, status_code=201)
async def add_agenda_item(
    meeting_id: str,
    payload: dict,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    try:
        item = await meeting_service.add_agenda_item(
            db, organization_id=org.id, meeting_id=meeting_id, data=payload,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return item


# --------------------------------------------------------------------------- Action items

@router.get("/{meeting_id}/action-items", response_model=list[ActionItemOut])
async def list_action_items(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return await meeting_service.action_items(db, organization_id=org.id, meeting_id=meeting_id)


@router.post("/{meeting_id}/action-items", response_model=ActionItemOut, status_code=201)
async def add_action_item(
    meeting_id: str,
    payload: ActionItemCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    try:
        item = await meeting_service.add_action_item(
            db, organization_id=org.id, meeting_id=meeting_id,
            data=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return item


@router.post("/{meeting_id}/action-items/{item_id}/complete", response_model=ActionItemOut)
async def complete_action_item(
    meeting_id: str,
    item_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    items = await meeting_service.action_items(db, organization_id=org.id, meeting_id=meeting_id)
    item = next((i for i in items if i.id == item_id), None)
    if item is None:
        raise HTTPException(404, "Action item not found")
    item = await meeting_service.complete_action_item(db, organization_id=org.id, item=item)
    await db.commit()
    return item


# --------------------------------------------------------------------------- Phase 6: sessions

@router.get("/{meeting_id}/session", response_model=SessionOut)
async def get_meeting_session(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    if session is None:
        raise HTTPException(404, "No session created for this meeting yet")
    session.participants = await participant_service.list(
        db, organization_id=org.id, session_id=session.id
    )
    return SessionOut.model_validate(_session_payload(session))


@router.post("/{meeting_id}/session", response_model=SessionOut, status_code=201)
async def create_meeting_session(
    meeting_id: str,
    payload: SessionCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    session = await session_service.ensure(
        db,
        organization_id=org.id,
        meeting=meeting,
        data=payload.model_dump(exclude_unset=True),
        actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    session.participants = await participant_service.list(db, organization_id=org.id, session_id=session.id)
    return SessionOut.model_validate(_session_payload(session))


@router.post("/{meeting_id}/join", response_model=dict)
async def join_meeting(
    meeting_id: str,
    payload: Optional[JoinBody] = None,
    request: Request = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    if meeting.status == "cancelled":
        raise HTTPException(409, "Meeting was cancelled")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    session = await session_service.ensure(
        db, organization_id=org.id, meeting=meeting, actor=actor, ip_address=get_client_ip(request)
    )
    participant = await session_service.join(
        db,
        organization_id=org.id,
        meeting=meeting,
        session=session,
        employee=actor,
        device=payload.device if payload else None,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    session.participants = await participant_service.list(db, organization_id=org.id, session_id=session.id)
    enriched = next((p for p in session.participants if p["id"] == participant.id), None)
    await live_hub.broadcast(
        session.id,
        "peer.joined",
        {
            "employee_id": participant.employee_id,
            "name": actor.full_name,
            "role": participant.role,
            "device": participant.device,
        },
        exclude_employee=participant.employee_id,
    )
    return {
        "meeting": _meeting_payload(meeting),
        "session": _session_payload(session),
        "participant": ParticipantOut.model_validate(enriched or participant),
    }


@router.post("/{meeting_id}/leave", response_model=dict)
async def leave_meeting(
    meeting_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    if session is None:
        return {"left": False}
    participant = await session_service.leave(
        db,
        organization_id=org.id,
        session=session,
        employee=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    if participant is not None:
        await live_hub.broadcast(
            session.id,
            "peer.left",
            {"employee_id": participant.employee_id, "name": actor.full_name},
            exclude_employee=participant.employee_id,
        )
    return {"left": participant is not None, "participant_id": participant.id if participant else None}


@router.post("/{meeting_id}/invite", response_model=dict)
async def invite_to_meeting(
    meeting_id: str,
    payload: InviteBody,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    try:
        added = await session_service.invite(
            db,
            organization_id=org.id,
            meeting=meeting,
            employee_ids=payload.employee_ids,
            actor=actor,
            ip_address=get_client_ip(request),
            message=payload.message,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return {"invited": added, "count": len(added)}


@router.post("/{meeting_id}/start", response_model=SessionOut)
async def start_meeting_session(
    meeting_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    session = await session_service.ensure(
        db, organization_id=org.id, meeting=meeting, actor=actor, ip_address=get_client_ip(request)
    )
    session = await session_service.start(
        db,
        organization_id=org.id,
        meeting=meeting,
        session=session,
        actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    session.participants = await participant_service.list(db, organization_id=org.id, session_id=session.id)
    return SessionOut.model_validate(_session_payload(session))


@router.post("/{meeting_id}/end", response_model=SessionOut)
async def end_meeting_session(
    meeting_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    if session is None:
        raise HTTPException(404, "No session for this meeting")
    session = await session_service.end(
        db,
        organization_id=org.id,
        meeting=meeting,
        session=session,
        actor=actor,
        ip_address=get_client_ip(request),
    )
    from app.collaboration.ai_meeting_service import ai_meeting_service

    await ai_meeting_service.finalize(
        db,
        organization_id=org.id,
        meeting=meeting,
        session=session,
        actor=actor,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    session.participants = await participant_service.list(db, organization_id=org.id, session_id=session.id)
    return SessionOut.model_validate(_session_payload(session))


@router.post("/{meeting_id}/presence", response_model=ParticipantOut)
async def participant_presence(
    meeting_id: str,
    payload: dict,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    """Live media-state heartbeat from the client (mic/camera/screen/hand)."""
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    if session is None:
        raise HTTPException(404, "No session for this meeting")
    participant = await participant_service.heartbeat(
        db,
        organization_id=org.id,
        session_id=session.id,
        employee_id=actor.id,
        device=payload.get("device"),
        mic_enabled=payload.get("mic_enabled"),
        camera_enabled=payload.get("camera_enabled"),
        screen_sharing=payload.get("screen_sharing"),
        raised_hand=payload.get("raised_hand"),
    )
    if participant is None:
        raise HTTPException(404, "You are not in this session yet — join first")
    await db.commit()
    rows = await participant_service.list(db, organization_id=org.id, session_id=session.id)
    enriched = next((r for r in rows if r["id"] == participant.id), None)
    event = (
        "screen_share.started" if payload.get("screen_sharing") else "screen_share.stopped"
    ) if payload.get("screen_sharing") is not None else "presence.changed"
    await live_hub.broadcast(
        session.id,
        event,
        {
            "employee_id": actor.id,
            "name": actor.full_name,
            "mic_enabled": participant.mic_enabled,
            "camera_enabled": participant.camera_enabled,
            "screen_sharing": participant.screen_sharing,
            "raised_hand": participant.raised_hand,
            "is_present": participant.is_present,
        },
        exclude_employee=actor.id,
    )
    return ParticipantOut.model_validate(enriched or participant)


@router.get("/{meeting_id}/participants", response_model=list[ParticipantOut])
async def list_session_participants(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    if session is None:
        return []
    rows = await participant_service.list(db, organization_id=org.id, session_id=session.id)
    return [ParticipantOut.model_validate(r) for r in rows]


# --------------------------------------------------------------------------- Phase 6: notes

@router.get("/{meeting_id}/notes", response_model=list[NoteOut])
async def list_notes(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    notes = await note_service.list(db, organization_id=org.id, meeting_id=meeting.id)
    return [
        NoteOut(
            id=n.id,
            meeting_id=n.meeting_id,
            session_id=n.session_id,
            author_id=n.author_id,
            author_name=getattr(n, "author_name", None),
            content=n.content,
            version=n.version,
            created_at=n.created_at,
            updated_at=n.updated_at,
        )
        for n in notes
    ]


@router.post("/{meeting_id}/notes", response_model=NoteOut, status_code=201)
async def create_note(
    meeting_id: str,
    payload: NoteCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    note = await note_service.create(
        db,
        organization_id=org.id,
        meeting_id=meeting.id,
        author=actor,
        content=payload.content,
        session_id=payload.session_id,
    )
    await db.commit()
    return NoteOut(
        id=note.id,
        meeting_id=note.meeting_id,
        session_id=note.session_id,
        author_id=note.author_id,
        author_name=actor.full_name,
        content=note.content,
        version=note.version,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.patch("/{meeting_id}/notes/{note_id}", response_model=NoteOut)
async def update_note(
    meeting_id: str,
    note_id: str,
    payload: NoteUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    note = await note_service.get(db, organization_id=org.id, meeting_id=meeting_id, note_id=note_id)
    if note is None:
        raise HTTPException(404, "Note not found")
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    note = await note_service.update(db, note=note, content=payload.content, author=actor)
    await db.commit()
    return NoteOut(
        id=note.id,
        meeting_id=note.meeting_id,
        session_id=note.session_id,
        author_id=note.author_id,
        author_name=None,
        content=note.content,
        version=note.version,
        created_at=note.created_at,
        updated_at=note.updated_at,
    )


@router.delete("/{meeting_id}/notes/{note_id}", response_model=Message)
async def delete_note(
    meeting_id: str,
    note_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    note = await note_service.get(db, organization_id=org.id, meeting_id=meeting_id, note_id=note_id)
    if note is None:
        raise HTTPException(404, "Note not found")
    await note_service.delete(db, note=note)
    await db.commit()
    return Message(message="Note deleted")
