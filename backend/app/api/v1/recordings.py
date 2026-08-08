"""Recordings, transcript and captions APIs (Phase 6.7/6.8/6.9).

Recording lifecycle: start -> (media gateway captures) -> stop -> worker
finalizes -> completed. Transcript/captions can be fed by streaming STT or by
the AI pipeline (when no STT provider is configured).
"""

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, require_permission
from app.collaboration.captions_service import captions_service, transcript_service
from app.collaboration.collab_base import emit_and_audit
from app.collaboration.recording_service import recording_service
from app.collaboration.session_service import session_service
from app.db.database import get_db
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.user import User
from app.schemas.common import Message
from app.work.meeting_service import meeting_service

router = APIRouter(prefix="/meetings", tags=["Recordings & Captions"])


class RecordingStartBody(BaseModel):
    kind: str = Field(default="manual", pattern="^(auto|manual)$")
    title: Optional[str] = None
    captions_enabled: bool = False
    language: str = Field(default="en", max_length=16)


class CaptionCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    employee_id: Optional[str] = None
    language: str = Field(default="en", max_length=16)
    start_ms: int = Field(default=0, ge=0)
    end_ms: int = Field(default=0, ge=0)
    translated_text: Optional[str] = None
    translation_language: Optional[str] = None


class TranscriptSave(BaseModel):
    content: str = ""
    segments: Optional[list[dict[str, Any]]] = None
    speakers: Optional[list[dict[str, Any]]] = None
    language: Optional[str] = None
    status: str = Field(default="completed", pattern="^(requested|transcribing|completed|failed)$")


async def _meeting_or_404(db: AsyncSession, org: Organization, meeting_id: str):
    meeting = await meeting_service.get(db, organization_id=org.id, meeting_id=meeting_id)
    if meeting is None:
        raise HTTPException(404, "Meeting not found")
    return meeting


# --------------------------------------------------------------------------- recordings

@router.get("/{meeting_id}/recordings", response_model=list[dict])
async def list_recordings(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    await _meeting_or_404(db, org, meeting_id)
    rows = await recording_service.list(db, organization_id=org.id, meeting_id=meeting_id)
    return [recording_service.payload(r) for r in rows]


@router.post("/{meeting_id}/recordings/start", response_model=dict, status_code=201)
async def start_recording(
    meeting_id: str,
    payload: RecordingStartBody,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _meeting_or_404(db, org, meeting_id)
    from app.people.employee_service import employee_service

    actor = await employee_service.get_by_user(db, organization_id=org.id, user_id=user.id)
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    recording = await recording_service.start(
        db,
        organization_id=org.id,
        meeting_id=meeting.id,
        session=session,
        created_by=actor.id if actor else None,
        title=payload.title,
        kind=payload.kind,
        captions_enabled=payload.captions_enabled,
        language=payload.language,
    )
    await db.commit()
    await emit_and_audit(
        db,
        organization_id=org.id,
        name="meeting.recording_started",
        actor=actor,
        actor_user_id=user.id,
        ip_address=get_client_ip(request),
        payload={"meeting_id": meeting.id, "recording_id": recording.id},
        resource_type="meeting_recording",
        resource_id=recording.id,
    )
    await db.commit()
    return recording_service.payload(recording)


@router.post("/{meeting_id}/recordings/{recording_id}/stop", response_model=dict)
async def stop_recording(
    meeting_id: str,
    recording_id: str,
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _meeting_or_404(db, org, meeting_id)
    recording = await recording_service.stop(db, organization_id=org.id, recording_id=recording_id)
    if recording is None:
        raise HTTPException(404, "Recording not found")
    await db.commit()
    await emit_and_audit(
        db,
        organization_id=org.id,
        name="meeting.recording_stopped",
        actor=user,
        actor_user_id=user.id,
        ip_address=get_client_ip(request),
        payload={"meeting_id": meeting_id, "recording_id": recording.id},
        resource_type="meeting_recording",
        resource_id=recording.id,
    )
    await db.commit()
    return recording_service.payload(recording)


@router.delete("/{meeting_id}/recordings/{recording_id}", response_model=Message)
async def delete_recording(
    meeting_id: str,
    recording_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _meeting_or_404(db, org, meeting_id)
    recording = await recording_service.get(db, organization_id=org.id, recording_id=recording_id)
    if recording is None:
        raise HTTPException(404, "Recording not found")
    await recording_service.delete(db, recording=recording)
    await db.commit()
    return Message(message="Recording deleted")


# --------------------------------------------------------------------------- transcript

@router.get("/{meeting_id}/transcript", response_model=dict)
async def get_transcript(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    meeting = await _meeting_or_404(db, org, meeting_id)
    transcript = await transcript_service.get(db, organization_id=org.id, meeting_id=meeting.id)
    if transcript is None:
        return {"meeting_id": meeting.id, "status": "none"}
    return transcript_service.payload(transcript)


@router.put("/{meeting_id}/transcript", response_model=dict)
async def save_transcript(
    meeting_id: str,
    payload: TranscriptSave,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Save transcript content (from STT worker or AI pipeline)."""
    meeting = await _meeting_or_404(db, org, meeting_id)
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    transcript = await transcript_service.get_or_create(
        db, organization_id=org.id, meeting_id=meeting.id,
        session_id=session.id if session else None, language=payload.language or "en",
    )
    transcript = await transcript_service.save(
        db,
        transcript=transcript,
        content=payload.content,
        segments=payload.segments,
        speakers=payload.speakers,
        language=payload.language,
        status=payload.status,
    )
    await db.commit()
    return transcript_service.payload(transcript)


# --------------------------------------------------------------------------- captions

@router.get("/{meeting_id}/captions", response_model=list[dict])
async def list_captions(
    meeting_id: str,
    after_ms: Optional[int] = None,
    language: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
    db: AsyncSession = Depends(get_db),
):
    await _meeting_or_404(db, org, meeting_id)
    rows = await captions_service.list(
        db, organization_id=org.id, meeting_id=meeting_id, after_ms=after_ms, language=language
    )
    out = []
    for row in rows:
        sender = await db.get(Employee, row.employee_id) if row.employee_id else None
        out.append(captions_service.payload(row, sender))
    return out


@router.post("/{meeting_id}/captions", response_model=dict, status_code=201)
async def add_caption(
    meeting_id: str,
    payload: CaptionCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Push one caption segment (streaming STT or simulated AI)."""
    meeting = await _meeting_or_404(db, org, meeting_id)
    session = await session_service.by_meeting(db, organization_id=org.id, meeting_id=meeting.id)
    caption = await captions_service.add(
        db,
        organization_id=org.id,
        meeting_id=meeting.id,
        session_id=session.id if session else None,
        employee_id=payload.employee_id,
        text=payload.text,
        language=payload.language,
        start_ms=payload.start_ms,
        end_ms=payload.end_ms,
        translated_text=payload.translated_text,
        translation_language=payload.translation_language,
    )
    await db.commit()
    return captions_service.payload(caption)


@router.delete("/{meeting_id}/captions", response_model=Message)
async def clear_captions(
    meeting_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:manage")),
    db: AsyncSession = Depends(get_db),
):
    await _meeting_or_404(db, org, meeting_id)
    count = await captions_service.delete_all(db, organization_id=org.id, meeting_id=meeting_id)
    await db.commit()
    return Message(message=f"{count} captions cleared")
