"""Live collaboration REST endpoints (Phase 6.4/6.5) — chat + whiteboard.

Real-time fan-out for these resources happens over the WebSocket
(`/ws/meetings/{meeting_id}`); these endpoints persist state and seed history.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.collaboration.collab_base import emit_and_audit
from app.collaboration.chat_service import chat_service
from app.collaboration.session_service import session_service
from app.collaboration.whiteboard_service import whiteboard_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.schemas.collaboration import ChatMessageOut, ChatSendBody, WhiteboardOut, WhiteboardUpdate
from app.schemas.common import Message
from app.work.meeting_service import meeting_service

router = APIRouter(prefix="/meetings", tags=["Live Collaboration"])


async def _meeting_or_404(db: AsyncSession, org: Organization, meeting_id: str):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return meeting


async def _session_id_or_none(db: AsyncSession, org: Organization, meeting_id: str) -> Optional[str]:
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting_id)
    return session.id if session else None


# --------------------------------------------------------------------------- chat

@router.get("/{meeting_id}/chat", response_model=list[ChatMessageOut])
async def list_chat(
    meeting_id: str,
    limit: int = 50,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    await _meeting_or_404(db, org, meeting_id)
    return await chat_service.list(db, organization_id=org.id, meeting_id=meeting_id, limit=limit)


@router.post("/{meeting_id}/chat", response_model=ChatMessageOut, status_code=201)
async def send_chat(
    meeting_id: str,
    payload: ChatSendBody,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _meeting_or_404(db, org, meeting_id)
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    session_id = await _session_id_or_none(db, org, meeting.id)
    try:
        message = await chat_service.send(
            db,
            organization_id=org.id,
            meeting_id=meeting.id,
            session_id=session_id,
            employee=actor,
            content=payload.content,
            reply_to=payload.reply_to,
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    await db.commit()
    await emit_and_audit(
        db,
        organization_id=org.id,
        name="meeting.chat_sent",
        actor=actor,
        actor_user_id=user.id,
        ip_address=get_client_ip(request),
        payload={"meeting_id": meeting.id, "session_id": session_id},
        resource_type="meeting",
        resource_id=meeting.id,
    )
    await db.commit()
    return message


@router.delete("/{meeting_id}/chat/{message_id}", response_model=Message)
async def delete_chat(
    meeting_id: str,
    message_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _meeting_or_404(db, org, meeting_id)
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    if actor is None:
        raise HTTPException(403, "No employee profile linked")
    message = await chat_service.get(db, organization_id=org.id, meeting_id=meeting.id, message_id=message_id)
    if message is None:
        raise HTTPException(404, "Message not found")
    is_host = meeting.organizer_id == actor.id
    try:
        await chat_service.delete(db, message=message, actor=actor, is_host=is_host)
    except ValueError as exc:
        raise HTTPException(403, str(exc)) from exc
    await db.commit()
    return Message(message="Message deleted")


# --------------------------------------------------------------------------- whiteboard

@router.get("/{meeting_id}/whiteboard", response_model=WhiteboardOut)
async def get_whiteboard(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _meeting_or_404(db, org, meeting_id)
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    session_id = await _session_id_or_none(db, org, meeting.id)
    board = await whiteboard_service.get_or_create(
        db,
        organization_id=org.id,
        meeting_id=meeting.id,
        session_id=session_id,
        created_by=actor.id if actor else None,
    )
    await db.commit()
    return whiteboard_service.payload(board)


@router.put("/{meeting_id}/whiteboard", response_model=WhiteboardOut)
async def update_whiteboard(
    meeting_id: str,
    payload: WhiteboardUpdate,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _meeting_or_404(db, org, meeting_id)
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    session_id = await _session_id_or_none(db, org, meeting.id)
    board = await whiteboard_service.get_or_create(
        db,
        organization_id=org.id,
        meeting_id=meeting.id,
        session_id=session_id,
        created_by=actor.id if actor else None,
    )
    try:
        board = await whiteboard_service.update(
            db, board=board, content=payload.content, expected_version=payload.version
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(409, str(exc)) from exc
    await db.commit()
    await emit_and_audit(
        db,
        organization_id=org.id,
        name="meeting.whiteboard_updated",
        actor=actor,
        actor_user_id=user.id,
        ip_address=get_client_ip(request),
        payload={"meeting_id": meeting.id, "session_id": session_id, "version": board.version},
        resource_type="meeting",
        resource_id=meeting.id,
    )
    await db.commit()
    return whiteboard_service.payload(board)
