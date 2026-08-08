"""Meeting rooms API — rooms, availability, room sessions (Phase 6)."""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.collaboration.collab_base import parse_json
from app.collaboration.room_service import room_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.collaboration import RoomCreate, RoomOut, RoomUpdate, SessionOut
from app.schemas.common import Message

router = APIRouter(prefix="/meeting-rooms", tags=["Meeting Rooms"])


def _room_payload(room) -> dict[str, Any]:
    return {
        "id": room.id,
        "name": room.name,
        "room_type": room.room_type,
        "description": room.description,
        "capacity": room.capacity,
        "location": room.location,
        "status": room.status,
        "department_id": room.department_id,
        "team_id": room.team_id,
        "project_id": room.project_id,
        "created_by": room.created_by,
        "is_public": room.is_public,
        "allow_recording": room.allow_recording,
        "settings": parse_json(room.settings),
        "created_at": room.created_at,
        "updated_at": room.updated_at,
    }


def _session_payload(session) -> dict[str, Any]:
    from app.schemas.collaboration import ParticipantOut

    participants = [
        ParticipantOut.model_validate(p) for p in getattr(session, "participants", []) or []
    ]
    return {
        "id": session.id,
        "meeting_id": session.meeting_id,
        "room_id": session.room_id,
        "status": session.status,
        "meeting_code": session.meeting_code,
        "timezone": session.timezone,
        "max_participants": session.max_participants,
        "started_at": session.started_at,
        "ended_at": session.ended_at,
        "duration_seconds": session.duration_seconds,
        "is_recording": session.is_recording,
        "is_captions_enabled": session.is_captions_enabled,
        "is_translation_enabled": session.is_translation_enabled,
        "is_transcribing": session.is_transcribing,
        "settings": parse_json(session.settings),
        "participants": participants,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
    }


@router.get("", response_model=list[RoomOut])
async def list_rooms(
    room_type: Optional[str] = None,
    status: Optional[str] = None,
    department_id: Optional[str] = None,
    team_id: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    rooms = await room_service.list_all(
        db,
        organization_id=org.id,
        room_type=room_type,
        status=status,
        department_id=department_id,
        team_id=team_id,
    )
    return [RoomOut.model_validate(_room_payload(r)) for r in rooms]


@router.post("", response_model=RoomOut, status_code=201)
async def create_room(
    payload: RoomCreate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    try:
        room = await room_service.create(
            db,
            organization_id=org.id,
            data=payload.model_dump(exclude_unset=True),
            actor=actor,
            ip_address=get_client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return RoomOut.model_validate(_room_payload(room))


@router.get("/{room_id}", response_model=RoomOut)
async def get_room(
    room_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    room = await room_service.get(db, organization_id=org.id, room_id=room_id)
    if room is None:
        raise HTTPException(404, "Meeting room not found")
    return RoomOut.model_validate(_room_payload(room))


@router.patch("/{room_id}", response_model=RoomOut)
async def update_room(
    room_id: str,
    payload: RoomUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    room = await room_service.get(db, organization_id=org.id, room_id=room_id)
    if room is None:
        raise HTTPException(404, "Meeting room not found")
    try:
        room = await room_service.update(
            db, organization_id=org.id, room=room, data=payload.model_dump(exclude_unset=True)
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    return RoomOut.model_validate(_room_payload(room))


@router.delete("/{room_id}", response_model=Message)
async def delete_room(
    room_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    room = await room_service.get(db, organization_id=org.id, room_id=room_id)
    if room is None:
        raise HTTPException(404, "Meeting room not found")
    await room_service.delete(db, room=room)
    await db.commit()
    return Message(message="Meeting room deleted")


class AvailabilityParams(BaseModel):
    start: Optional[datetime] = None
    end: Optional[datetime] = None


@router.get("/{room_id}/availability")
async def room_availability(
    room_id: str,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    room = await room_service.get(db, organization_id=org.id, room_id=room_id)
    if room is None:
        raise HTTPException(404, "Meeting room not found")
    return await room_service.availability(
        db, organization_id=org.id, room_id=room_id, start=start, end=end
    )


@router.get("/{room_id}/sessions", response_model=list[SessionOut])
async def room_sessions(
    room_id: str,
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    room = await room_service.get(db, organization_id=org.id, room_id=room_id)
    if room is None:
        raise HTTPException(404, "Meeting room not found")
    sessions = await room_service.sessions(
        db, organization_id=org.id, room_id=room_id, status=status
    )
    return [SessionOut.model_validate(_session_payload(s)) for s in sessions]
