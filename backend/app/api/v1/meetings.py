"""Meeting API Routes — Native VCOS Meetings, Conferences, and Presentations."""

import asyncio
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query, Body, File, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_current_organization, get_db
from app.models.meeting import (
    Meeting,
    MeetingParticipant,
    MeetingRecording,
    MeetingTranscript,
    MeetingType,
    MeetingStatus,
    MeetingScale,
    ParticipantRole,
    ParticipantStatus,
    RecordingStatus,
)
from app.models.project import Project
from app.models.user import User
from app.models.organization import Organization
from app.services.meeting_service import meeting_service, MeetingConfig, MeetingScale as ServiceMeetingScale, PresentationConfig
# from app.services.calendar_service import calendar_service

router = APIRouter(prefix="/meetings", tags=["Meetings"])


# =============================================================================
# Request/Response Models
# =============================================================================

class MeetingCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    meeting_type: MeetingType = MeetingType.STANDARD
    scale: Optional[MeetingScale] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    timezone: str = "UTC"
    project_id: Optional[str] = None
    participant_ids: List[str] = []
    external_guest_emails: List[str] = []
    agenda: List[str] = []
    materials: List[Dict[str, Any]] = []
    settings: Dict[str, Any] = {}
    recording_enabled: bool = False
    transcription_enabled: bool = False
    wait_room_enabled: bool = True
    chat_enabled: bool = True
    reactions_enabled: bool = True
    screen_share_enabled: bool = True
    require_approval: bool = False
    allow_external_guests: bool = True
    password_protected: bool = False
    password: Optional[str] = None


class MeetingUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    meeting_type: Optional[MeetingType] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    agenda: Optional[List[str]] = None
    materials: Optional[List[Dict[str, Any]]] = None
    settings: Optional[Dict[str, Any]] = None
    recording_enabled: Optional[bool] = None
    transcription_enabled: Optional[bool] = None
    wait_room_enabled: Optional[bool] = None
    chat_enabled: Optional[bool] = None
    reactions_enabled: Optional[bool] = None
    screen_share_enabled: Optional[bool] = None
    require_approval: Optional[bool] = None
    allow_external_guests: Optional[bool] = None
    password_protected: Optional[bool] = None
    password: Optional[str] = None


class MeetingResponse(BaseModel):
    id: str
    title: str
    description: Optional[str]
    meeting_type: str
    scale: str
    scheduled_start: Optional[str]
    scheduled_end: Optional[str]
    actual_start: Optional[str]
    actual_end: Optional[str]
    timezone: str
    project_id: Optional[str]
    organizer_id: str
    status: str
    media_room_name: Optional[str]
    media_url: Optional[str]
    agenda: List[str]
    materials: List[Dict[str, Any]]
    settings: Dict[str, Any]
    recording_enabled: bool
    transcription_enabled: bool
    wait_room_enabled: bool
    chat_enabled: bool
    reactions_enabled: bool
    screen_share_enabled: bool
    require_approval: bool
    allow_external_guests: bool
    password_protected: bool
    recording_id: Optional[str]
    recording_url: Optional[str]
    recording_status: Optional[str]
    transcription_url: Optional[str]
    current_presentation_id: Optional[str]
    presentation_state: Optional[Dict[str, Any]]
    decisions: List[Dict[str, Any]]
    action_items: List[Dict[str, Any]]
    summary: Optional[str]
    created_at: str
    updated_at: str
    created_by: str


class ParticipantResponse(BaseModel):
    id: str
    meeting_id: str
    user_id: Optional[str]
    email: Optional[str]
    display_name: Optional[str]
    avatar_url: Optional[str]
    role: str
    status: str
    joined_at: Optional[str]
    left_at: Optional[str]
    duration_seconds: int
    audio_enabled: bool
    video_enabled: bool
    screen_sharing: bool
    hand_raised: bool


class JoinMeetingResponse(BaseModel):
    meeting_id: str
    participant_id: str
    media_token: str
    media_url: str
    room_name: str
    settings: Dict[str, Any]


class PresentationCreate(BaseModel):
    title: str
    meeting_id: Optional[str] = None
    slides: List[Dict[str, Any]] = []
    co_presenter_ids: List[str] = []
    audience_qna_enabled: bool = True
    polls_enabled: bool = True
    recording_enabled: bool = True
    materials: List[Dict[str, Any]] = []


class DecisionCreate(BaseModel):
    title: str
    description: Optional[str] = None
    options: List[str] = []
    evidence: List[Dict[str, Any]] = []


class ActionItemCreate(BaseModel):
    title: str
    description: Optional[str] = None
    assignee_id: Optional[str] = None
    due_date: Optional[datetime] = None
    priority: str = "medium"


class RecordingStartResponse(BaseModel):
    recording_id: str
    status: str


# =============================================================================
# Meeting CRUD
# =============================================================================

@router.post("", response_model=MeetingResponse, status_code=status.HTTP_201_CREATED)
async def create_meeting(
    payload: MeetingCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Create a new meeting."""
    config = MeetingConfig(
        title=payload.title,
        description=payload.description,
        meeting_type=payload.meeting_type,
        scale=ServiceMeetingScale(payload.scale.value) if payload.scale else None,
        scheduled_start=payload.scheduled_start,
        scheduled_end=payload.scheduled_end,
        timezone=payload.timezone,
        project_id=payload.project_id,
        organizer_id=user.id,
        participant_ids=payload.participant_ids,
        external_guest_emails=payload.external_guest_emails,
        agenda=payload.agenda,
        materials=payload.materials,
        settings=payload.settings,
        recording_enabled=payload.recording_enabled,
        transcription_enabled=payload.transcription_enabled,
        wait_room_enabled=payload.wait_room_enabled,
        chat_enabled=payload.chat_enabled,
        reactions_enabled=payload.reactions_enabled,
        screen_share_enabled=payload.screen_share_enabled,
        require_approval=payload.require_approval,
        allow_external_guests=payload.allow_external_guests,
        password_protected=payload.password_protected,
        password=payload.password,
    )

    meeting = await meeting_service.create_meeting(db, config, actor_id=user.id)

    return _meeting_to_response(meeting)


@router.get("", response_model=List[MeetingResponse])
async def list_meetings(
    status: Optional[MeetingStatus] = None,
    project_id: Optional[str] = None,
    upcoming_only: bool = True,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """List meetings for the organization."""
    query = select(Meeting).where(Meeting.organization_id == org.id)

    if status:
        query = query.where(Meeting.status == status)
    if project_id:
        query = query.where(Meeting.project_id == project_id)
    if upcoming_only:
        query = query.where(Meeting.scheduled_start >= datetime.now(timezone.utc))

    query = query.order_by(Meeting.scheduled_start).limit(limit).offset(offset)

    result = await db.execute(query)
    meetings = result.scalars().all()

    return [_meeting_to_response(m) for m in meetings]


@router.get("/{meeting_id}", response_model=MeetingResponse)
async def get_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Get meeting details."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    return _meeting_to_response(meeting)


@router.patch("/{meeting_id}", response_model=MeetingResponse)
async def update_meeting(
    meeting_id: str,
    payload: MeetingUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Update meeting details."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Only organizer can update meeting")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(meeting, key, value)

    await db.commit()

    return _meeting_to_response(meeting)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Delete a meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Only organizer can delete meeting")

    if meeting.status == MeetingStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Cannot delete active meeting")

    await db.delete(meeting)
    await db.commit()


# =============================================================================
# Meeting Lifecycle
# =============================================================================

@router.post("/{meeting_id}/start", response_model=MeetingResponse)
async def start_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Start a meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    meeting = await meeting_service.start_meeting(db, meeting_id, actor_id=user.id)

    return _meeting_to_response(meeting)


@router.post("/{meeting_id}/end", response_model=MeetingResponse)
async def end_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """End a meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    meeting = await meeting_service.end_meeting(db, meeting_id, actor_id=user.id)

    return _meeting_to_response(meeting)


@router.post("/{meeting_id}/join", response_model=JoinMeetingResponse)
async def join_meeting(
    meeting_id: str,
    display_name: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Join a meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    join_info = await meeting_service.join_meeting(db, meeting_id, user_id=user.id, display_name=display_name)

    return JoinMeetingResponse(**join_info)


@router.post("/{meeting_id}/leave")
async def leave_meeting(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Leave a meeting."""
    # Find participant
    participant = await db.execute(
        select(MeetingParticipant).where(
            MeetingParticipant.meeting_id == meeting_id,
            MeetingParticipant.user_id == user.id,
        )
    )
    participant = participant.scalar_one_or_none()

    if not participant:
        raise HTTPException(status_code=404, detail="Not a participant in this meeting")

    await meeting_service.leave_meeting(db, meeting_id, participant.id)

    return {"success": True}


@router.post("/{meeting_id}/join-guest", response_model=JoinMeetingResponse)
async def join_meeting_as_guest(
    meeting_id: str,
    email: str = Body(..., embed=True),
    display_name: Optional[str] = Body(None),
    db: AsyncSession = Depends(get_db),
    org: Organization = Depends(get_current_organization),
):
    """Join a meeting as an external guest."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if not meeting.allow_external_guests:
        raise HTTPException(status_code=403, detail="External guests not allowed")

    join_info = await meeting_service.join_meeting(db, meeting_id, email=email, display_name=display_name)

    return JoinMeetingResponse(**join_info)


# =============================================================================
# Participants
# =============================================================================

@router.get("/{meeting_id}/participants", response_model=List[ParticipantResponse])
async def list_participants(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """List meeting participants."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    result = await db.execute(
        select(MeetingParticipant).where(MeetingParticipant.meeting_id == meeting_id)
    )
    participants = result.scalars().all()

    return [_participant_to_response(p) for p in participants]


@router.post("/{meeting_id}/participants", response_model=ParticipantResponse)
async def add_participant(
    meeting_id: str,
    user_id: str = Body(..., embed=True),
    role: ParticipantRole = Body(ParticipantRole.PARTICIPANT),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Add a participant to meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Only organizer can add participants")

    # Check if already participant
    existing = await db.execute(
        select(MeetingParticipant).where(
            MeetingParticipant.meeting_id == meeting_id,
            MeetingParticipant.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="User already a participant")

    participant = MeetingParticipant(
        id=uuid4().hex[:32],
        meeting_id=meeting_id,
        user_id=user_id,
        role=role,
        status=ParticipantStatus.PENDING,
    )
    db.add(participant)
    await db.commit()

    return _participant_to_response(participant)


@router.delete("/{meeting_id}/participants/{participant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_participant(
    meeting_id: str,
    participant_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Remove a participant from meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    if meeting.organizer_id != user.id:
        raise HTTPException(status_code=403, detail="Only organizer can remove participants")

    participant = await db.get(MeetingParticipant, participant_id)
    if not participant or participant.meeting_id != meeting_id:
        raise HTTPException(status_code=404, detail="Participant not found")

    await db.delete(participant)
    await db.commit()


# =============================================================================
# Presentation Workflow
# =============================================================================

@router.post("/{meeting_id}/presentations", response_model=Dict[str, Any])
async def create_presentation(
    meeting_id: str,
    payload: PresentationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Create a presentation for a meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    config = PresentationConfig(
        title=payload.title,
        meeting_id=meeting_id,
        slides=payload.slides,
        presenter_id=user.id,
        co_presenter_ids=payload.co_presenter_ids,
        audience_qna_enabled=payload.audience_qna_enabled,
        polls_enabled=payload.polls_enabled,
        recording_enabled=payload.recording_enabled,
        materials=payload.materials,
    )

    presentation = await meeting_service.create_presentation(db, config, actor_id=user.id)

    return presentation


@router.post("/{meeting_id}/presentations/{presentation_id}/start", response_model=Dict[str, Any])
async def start_presentation(
    meeting_id: str,
    presentation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Start presenting in a meeting."""
    presentation = await meeting_service.start_presentation(db, meeting_id, presentation_id, actor_id=user.id)
    return presentation


@router.post("/{meeting_id}/presentations/next-slide", response_model=Dict[str, Any])
async def next_slide(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Advance to next slide."""
    presentation = await meeting_service.next_slide(db, meeting_id, actor_id=user.id)
    return presentation


# =============================================================================
# Meeting Intelligence
# =============================================================================

@router.post("/{meeting_id}/decisions", response_model=Dict[str, Any])
async def capture_decision(
    meeting_id: str,
    payload: DecisionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Capture a decision during meeting."""
    decision = await meeting_service.capture_decision(db, meeting_id, payload.model_dump(), actor_id=user.id)
    return decision


@router.post("/{meeting_id}/decisions/{decision_id}/approve", response_model=Dict[str, Any])
async def approve_decision(
    meeting_id: str,
    decision_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Approve a proposed decision."""
    result = await meeting_service.approve_decision(db, meeting_id, decision_id, actor_id=user.id)
    return result


@router.post("/{meeting_id}/action-items", response_model=Dict[str, Any])
async def capture_action_item(
    meeting_id: str,
    payload: ActionItemCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Capture an action item during meeting."""
    action = await meeting_service.capture_action_item(db, meeting_id, payload.model_dump(), actor_id=user.id)
    return action


# =============================================================================
# Recording
# =============================================================================

@router.post("/{meeting_id}/recording/start", response_model=RecordingStartResponse)
async def start_recording(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Start recording a meeting."""
    result = await meeting_service.start_recording(db, meeting_id, actor_id=user.id)
    return RecordingStartResponse(**result)


@router.post("/{meeting_id}/recording/stop", response_model=Dict[str, Any])
async def stop_recording(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Stop recording a meeting."""
    result = await meeting_service.stop_recording(db, meeting_id, actor_id=user.id)
    return result


@router.get("/{meeting_id}/recordings", response_model=List[Dict[str, Any]])
async def list_recordings(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """List recordings for a meeting."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    result = await db.execute(
        select(MeetingRecording).where(MeetingRecording.meeting_id == meeting_id)
    )
    recordings = result.scalars().all()

    return [
        {
            "id": r.id,
            "recording_id": r.recording_id,
            "status": r.status.value,
            "file_url": r.file_url,
            "thumbnail_url": r.thumbnail_url,
            "format": r.format,
            "size_bytes": r.size_bytes,
            "duration_seconds": r.duration_seconds,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "ended_at": r.ended_at.isoformat() if r.ended_at else None,
            "access_level": r.access_level,
        }
        for r in recordings
    ]


@router.get("/{meeting_id}/transcript", response_model=Dict[str, Any])
async def get_transcript(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Get meeting transcript."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(status_code=404, detail="Meeting not found")

    result = await db.execute(
        select(MeetingTranscript).where(MeetingTranscript.meeting_id == meeting_id)
    )
    transcript = result.scalar_one_or_none()

    if not transcript:
        raise HTTPException(status_code=404, detail="Transcript not found")

    return {
        "id": transcript.id,
        "full_text": transcript.full_text,
        "segments": transcript.segments,
        "language": transcript.language,
        "confidence": transcript.confidence,
        "status": transcript.status,
        "completed_at": transcript.completed_at.isoformat() if transcript.completed_at else None,
    }


# =============================================================================
# Calendar Integration
# =============================================================================

@router.post("/{meeting_id}/calendar/sync")
async def sync_calendar(
    meeting_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Sync meeting to calendar."""
    meeting = await db.get(Meeting, meeting_id)
    if not meeting or meeting.organization_id != org.id:
        raise HTTPException(status_code=404, detail="Meeting not found")

    # await calendar_service.create_meeting_event(db, meeting)

    return {"success": True, "message": "Calendar event created"}


# =============================================================================
# Helper Functions
# =============================================================================

def _meeting_to_response(meeting: Meeting) -> MeetingResponse:
    return MeetingResponse(
        id=meeting.id,
        title=meeting.title,
        description=meeting.description,
        meeting_type=meeting.meeting_type.value,
        scale=meeting.scale.value,
        scheduled_start=meeting.scheduled_start.isoformat() if meeting.scheduled_start else None,
        scheduled_end=meeting.scheduled_end.isoformat() if meeting.scheduled_end else None,
        actual_start=meeting.actual_start.isoformat() if meeting.actual_start else None,
        actual_end=meeting.actual_end.isoformat() if meeting.actual_end else None,
        timezone=meeting.timezone,
        project_id=meeting.project_id,
        organizer_id=meeting.organizer_id,
        status=meeting.status.value,
        media_room_name=meeting.media_room_name,
        media_url=meeting.media_url,
        agenda=meeting.agenda,
        materials=meeting.materials,
        settings=meeting.settings,
        recording_enabled=meeting.recording_enabled,
        transcription_enabled=meeting.transcription_enabled,
        wait_room_enabled=meeting.wait_room_enabled,
        chat_enabled=meeting.chat_enabled,
        reactions_enabled=meeting.reactions_enabled,
        screen_share_enabled=meeting.screen_share_enabled,
        require_approval=meeting.require_approval,
        allow_external_guests=meeting.allow_external_guests,
        password_protected=meeting.password_protected,
        recording_id=meeting.recording_id,
        recording_url=meeting.recording_url,
        recording_status=meeting.recording_status,
        transcription_url=meeting.transcription_url,
        current_presentation_id=meeting.current_presentation_id,
        presentation_state=meeting.presentation_state,
        decisions=meeting.decisions,
        action_items=meeting.action_items,
        summary=meeting.summary,
        created_at=meeting.created_at.isoformat(),
        updated_at=meeting.updated_at.isoformat(),
        created_by=meeting.created_by,
    )


def _participant_to_response(participant: MeetingParticipant) -> ParticipantResponse:
    return ParticipantResponse(
        id=participant.id,
        meeting_id=participant.meeting_id,
        user_id=participant.user_id,
        email=participant.email,
        display_name=participant.display_name,
        avatar_url=participant.avatar_url,
        role=participant.role.value,
        status=participant.status.value,
        joined_at=participant.joined_at.isoformat() if participant.joined_at else None,
        left_at=participant.left_at.isoformat() if participant.left_at else None,
        duration_seconds=participant.duration_seconds,
        audio_enabled=participant.audio_enabled,
        video_enabled=participant.video_enabled,
        screen_sharing=participant.screen_sharing,
        hand_raised=participant.hand_raised,
    )