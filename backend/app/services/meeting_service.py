"""
Meeting Service — Native VCOS Meetings, Conferences, and Presentations.

Provides a first-class meeting experience with:
- Instant and scheduled meetings
- Multi-scale support (small team to 50,000+ participants)
- Presentation workflow with screen sharing
- Meeting intelligence (agendas, notes, summaries)
- Decision capture and action item tracking
- Calendar integration
- Recording and transcription (with consent)
"""

import asyncio
import logging
import secrets
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.meeting import (
    Meeting,
    MeetingParticipant,
    MeetingRecording,
    MeetingTranscript,
    MeetingType,
    MeetingStatus,
    ParticipantRole,
    RecordingStatus,
)
from app.models.project import Project
from app.models.user import User
# from app.services.calendar_service import calendar_service
from app.services.notification_service import notification_service
from app.intelligence.canonical_mutation import canonical_mutation_boundary, MutationType

logger = logging.getLogger("vcos.meetings")


class MediaProvider(str, Enum):
    """Supported media infrastructure providers."""
    LIVEKIT = "livekit"
    WEBRTC_MESH = "webrtc_mesh"
    SFU = "sfu"
    BROADCAST = "broadcast"


class MeetingScale(str, Enum):
    """Meeting scale modes."""
    SMALL = "small"          # 2-10 participants, peer-to-peer
    TEAM = "team"            # 10-50 participants, SFU
    DEPARTMENT = "department"  # 50-200 participants, SFU
    TOWN_HALL = "town_hall"  # 200-1000 participants, selective forwarding
    WEBINAR = "webinar"      # 1000-10000, broadcast with controlled interaction
    CONFERENCE = "conference"  # 10000+, broadcast distribution


@dataclass
class MeetingConfig:
    """Configuration for a meeting."""
    title: str
    organizer_id: str
    description: Optional[str] = None
    meeting_type: MeetingType = MeetingType.STANDARD
    scale: MeetingScale = MeetingScale.TEAM
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    timezone: str = "UTC"
    project_id: Optional[str] = None
    participant_ids: List[str] = field(default_factory=list)
    external_guest_emails: List[str] = field(default_factory=list)
    agenda: List[str] = field(default_factory=list)
    materials: List[Dict[str, Any]] = field(default_factory=list)
    settings: Dict[str, Any] = field(default_factory=dict)
    # Media settings
    media_provider: MediaProvider = MediaProvider.LIVEKIT
    recording_enabled: bool = False
    transcription_enabled: bool = False
    wait_room_enabled: bool = True
    chat_enabled: bool = True
    reactions_enabled: bool = True
    screen_share_enabled: bool = True
    # Access control
    require_approval: bool = False
    allow_external_guests: bool = True
    password_protected: bool = False
    password: Optional[str] = None
@dataclass
class PresentationConfig:
    """Configuration for a presentation."""
    title: str
    presenter_id: str
    meeting_id: Optional[str] = None
    slides: List[Dict[str, Any]] = field(default_factory=list)
    co_presenter_ids: List[str] = field(default_factory=list)
    audience_qna_enabled: bool = True
    polls_enabled: bool = True
    recording_enabled: bool = True
    materials: List[Dict[str, Any]] = field(default_factory=list)


class MeetingService:
    """Core meeting service for VCOS."""

    def __init__(self):
        self._livekit_client = None
        self._media_provider = MediaProvider.LIVEKIT

    async def initialize_media_client(self, provider: MediaProvider = MediaProvider.LIVEKIT):
        """Initialize the media infrastructure client."""
        self._media_provider = provider
        if provider == MediaProvider.LIVEKIT:
            # Initialize LiveKit client
            from livekit import api
            self._livekit_client = api.LiveKitAPI(
                url="https://livekit.vcos.io",
                api_key="vcos-meetings",
                api_secret="secret",
            )
        logger.info(f"Initialized media client: {provider.value}")

    # =========================================================================
    # MEETING LIFECYCLE
    # =========================================================================

    async def create_meeting(
        self,
        db: AsyncSession,
        config: MeetingConfig,
        *,
        actor_id: str,
    ) -> Meeting:
        """Create a new meeting with media infrastructure."""
        # Validate organizer
        organizer = await db.get(User, config.organizer_id)
        if not organizer:
            raise ValueError("Organizer not found")

        # Determine scale based on participant count
        total_participants = len(config.participant_ids) + len(config.external_guest_emails)
        config.scale = self._determine_scale(total_participants)

        # Create meeting record
        meeting = Meeting(
            id=uuid.uuid4().hex[:32],
            title=config.title,
            description=config.description,
            meeting_type=config.meeting_type,
            scale=config.scale.value,
            scheduled_start=config.scheduled_start,
            scheduled_end=config.scheduled_end,
            timezone=config.timezone,
            project_id=config.project_id,
            organizer_id=config.organizer_id,
            agenda=config.agenda,
            materials=config.materials,
            settings=config.settings,
            media_provider=config.media_provider.value,
            recording_enabled=config.recording_enabled,
            transcription_enabled=config.transcription_enabled,
            wait_room_enabled=config.wait_room_enabled,
            chat_enabled=config.chat_enabled,
            reactions_enabled=config.reactions_enabled,
            screen_share_enabled=config.screen_share_enabled,
            require_approval=config.require_approval,
            allow_external_guests=config.allow_external_guests,
            password_protected=config.password_protected,
            password_hash=self._hash_password(config.password) if config.password else None,
            status=MeetingStatus.SCHEDULED if config.scheduled_start else MeetingStatus.WAITING,
            created_by=actor_id,
        )

        db.add(meeting)
        await db.flush()

        # Add participants
        for participant_id in config.participant_ids:
            participant = MeetingParticipant(
                id=uuid.uuid4().hex[:32],
                meeting_id=meeting.id,
                user_id=participant_id,
                role=ParticipantRole.PARTICIPANT,
                status="pending",
            )
            db.add(participant)

        # Add organizer as host
        organizer_participant = MeetingParticipant(
            id=uuid.uuid4().hex[:32],
            meeting_id=meeting.id,
            user_id=config.organizer_id,
            role=ParticipantRole.HOST,
            status="joined",
        )
        db.add(organizer_participant)

        # Add external guests
        for email in config.external_guest_emails:
            guest = MeetingParticipant(
                id=uuid.uuid4().hex[:32],
                meeting_id=meeting.id,
                email=email,
                role=ParticipantRole.GUEST,
                status="invited",
            )
            db.add(guest)

        # Create media room
        room_name = await self._create_media_room(meeting)
        meeting.media_room_name = room_name

        # Create calendar events
        if config.scheduled_start:
            # await calendar_service.create_meeting_event(db, meeting)
            pass

        await db.commit()

        # Emit event
        await publish_event(
            db,
            name="meeting.created",
            actor_id=actor_id,
            organization_id=organizer.organization_id,
            payload={
                "meeting_id": meeting.id,
                "title": meeting.title,
                "scale": meeting.scale,
                "scheduled_start": meeting.scheduled_start.isoformat() if meeting.scheduled_start else None,
            },
        )

        logger.info(f"Created meeting {meeting.id}: {meeting.title} (scale: {meeting.scale})")
        return meeting

    async def start_meeting(
        self,
        db: AsyncSession,
        meeting_id: str,
        *,
        actor_id: str,
    ) -> Meeting:
        """Start a meeting."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found")

        if meeting.status == MeetingStatus.ACTIVE:
            return meeting

        # Verify permissions
        if meeting.organizer_id != actor_id:
            # Check if actor is co-host
            participant = await db.execute(
                select(MeetingParticipant).where(
                    MeetingParticipant.meeting_id == meeting_id,
                    MeetingParticipant.user_id == actor_id,
                    MeetingParticipant.role.in_([ParticipantRole.HOST, ParticipantRole.CO_HOST]),
                )
            )
            if not participant.scalar_one_or_none():
                raise PermissionError("Only host or co-host can start meeting")

        # Start media session
        await self._start_media_session(meeting)

        meeting.status = MeetingStatus.ACTIVE
        meeting.actual_start = utcnow()
        meeting.started_by = actor_id
        await db.commit()

        # Emit event
        await publish_event(
            db,
            name="meeting.started",
            actor_id=actor_id,
            organization_id=meeting.organization_id,
            payload={"meeting_id": meeting.id, "started_at": meeting.actual_start.isoformat()},
        )

        # Notify participants
        await self._notify_participants(db, meeting, "meeting_started", {
            "meeting_id": meeting.id,
            "join_url": meeting.join_url,
        })

        logger.info(f"Started meeting {meeting.id}")
        return meeting

    async def end_meeting(
        self,
        db: AsyncSession,
        meeting_id: str,
        *,
        actor_id: str,
    ) -> Meeting:
        """End a meeting."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found")

        if meeting.organizer_id != actor_id:
            raise PermissionError("Only organizer can end meeting")

        # End media session
        await self._end_media_session(meeting)

        meeting.status = MeetingStatus.ENDED
        meeting.actual_end = utcnow()
        await db.commit()

        # Process recording if enabled
        if meeting.recording_enabled and meeting.recording_id:
            await self._process_recording(db, meeting)

        # Generate meeting summary
        await self._generate_meeting_summary(db, meeting)

        # Emit event
        await publish_event(
            db,
            name="meeting.ended",
            actor_id=actor_id,
            organization_id=meeting.organization_id,
            payload={"meeting_id": meeting.id, "ended_at": meeting.actual_end.isoformat()},
        )

        logger.info(f"Ended meeting {meeting.id}")
        return meeting

    async def join_meeting(
        self,
        db: AsyncSession,
        meeting_id: str,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        display_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Join a meeting, returning media connection details."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found")

        if meeting.status == MeetingStatus.ENDED:
            raise ValueError("Meeting has ended")

        if meeting.status == MeetingStatus.SCHEDULED and meeting.scheduled_start:
            if utcnow() < meeting.scheduled_start - timedelta(minutes=15):
                raise ValueError("Meeting has not started yet")

        # Check access
        participant = None
        if user_id:
            participant = await db.execute(
                select(MeetingParticipant).where(
                    MeetingParticipant.meeting_id == meeting_id,
                    MeetingParticipant.user_id == user_id,
                )
            )
            participant = participant.scalar_one_or_none()

        if not participant and email:
            participant = await db.execute(
                select(MeetingParticipant).where(
                    MeetingParticipant.meeting_id == meeting_id,
                    MeetingParticipant.email == email,
                )
            )
            participant = participant.scalar_one_or_none()

        if not participant and meeting.allow_external_guests and email:
            # Create guest participant
            participant = MeetingParticipant(
                id=uuid.uuid4().hex[:32],
                meeting_id=meeting_id,
                email=email,
                display_name=display_name,
                role=ParticipantRole.GUEST,
                status="joining",
            )
            db.add(participant)
            await db.flush()

        if not participant:
            raise PermissionError("Not authorized to join this meeting")

        # Update participant status
        participant.status = "joined"
        participant.joined_at = utcnow()
        if display_name:
            participant.display_name = display_name
        await db.commit()

        # Generate media token
        media_token = await self._generate_media_token(meeting, participant)

        return {
            "meeting_id": meeting.id,
            "participant_id": participant.id,
            "media_token": media_token,
            "media_url": meeting.media_url,
            "room_name": meeting.media_room_name,
            "settings": {
                "chat_enabled": meeting.chat_enabled,
                "reactions_enabled": meeting.reactions_enabled,
                "screen_share_enabled": meeting.screen_share_enabled,
                "recording_enabled": meeting.recording_enabled,
            },
        }

    async def leave_meeting(
        self,
        db: AsyncSession,
        meeting_id: str,
        participant_id: str,
    ) -> None:
        """Participant leaves meeting."""
        participant = await db.get(MeetingParticipant, participant_id)
        if participant and participant.meeting_id == meeting_id:
            participant.status = "left"
            participant.left_at = utcnow()
            await db.commit()

    # =========================================================================
    # PRESENTATION WORKFLOW
    # =========================================================================

    async def create_presentation(
        self,
        db: AsyncSession,
        config: PresentationConfig,
        *,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Create a presentation linked to a meeting."""
        meeting = None
        if config.meeting_id:
            meeting = await db.get(Meeting, config.meeting_id)
            if not meeting:
                raise ValueError("Meeting not found")

        presentation = {
            "id": uuid.uuid4().hex[:32],
            "title": config.title,
            "meeting_id": config.meeting_id,
            "slides": config.slides,
            "presenter_id": config.presenter_id,
            "co_presenter_ids": config.co_presenter_ids,
            "audience_qna_enabled": config.audience_qna_enabled,
            "polls_enabled": config.polls_enabled,
            "recording_enabled": config.recording_enabled,
            "materials": config.materials,
            "status": "draft",
            "created_by": actor_id,
            "created_at": utcnow().isoformat(),
        }

        # Store in meeting materials
        if meeting:
            materials = meeting.materials or []
            materials.append({
                "type": "presentation",
                "presentation_id": presentation["id"],
                "title": config.title,
            })
            meeting.materials = materials
            await db.commit()

        return presentation

    async def start_presentation(
        self,
        db: AsyncSession,
        meeting_id: str,
        presentation_id: str,
        *,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Start presenting in a meeting."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found")

        # Find presentation in materials
        presentation = None
        for material in meeting.materials or []:
            if material.get("presentation_id") == presentation_id:
                presentation = material
                break

        if not presentation:
            raise ValueError("Presentation not found")

        # Verify presenter
        if presentation["presenter_id"] != actor_id and actor_id not in presentation.get("co_presenter_ids", []):
            # Check if actor is host
            participant = await db.execute(
                select(MeetingParticipant).where(
                    MeetingParticipant.meeting_id == meeting_id,
                    MeetingParticipant.user_id == actor_id,
                    MeetingParticipant.role == ParticipantRole.HOST,
                )
            )
            if not participant.scalar_one_or_none():
                raise PermissionError("Not authorized to present")

        # Update meeting state
        meeting.current_presentation_id = presentation_id
        meeting.presentation_state = "active"
        await db.commit()

        # Broadcast to participants via media
        await self._broadcast_presentation_start(meeting, presentation)

        return {
            "presentation_id": presentation_id,
            "slides": presentation.get("slides", []),
            "current_slide": 0,
        }

    async def next_slide(
        self,
        db: AsyncSession,
        meeting_id: str,
        *,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Advance to next slide."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting or meeting.current_presentation_id != meeting_id:
            raise ValueError("No active presentation")

        # Verify presenter/host
        # ... permission check

        # Advance slide
        current = meeting.presentation_state.get("current_slide", 0)
        meeting.presentation_state["current_slide"] = current + 1
        await db.commit()

        # Broadcast slide change
        await self._broadcast_slide_change(meeting, current + 1)

        return {"current_slide": current + 1}

    # =========================================================================
    # MEETING INTELLIGENCE
    # =========================================================================

    async def capture_decision(
        self,
        db: AsyncSession,
        meeting_id: str,
        decision_data: Dict[str, Any],
        *,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Capture a decision during meeting."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found")

        decision = {
            "id": uuid.uuid4().hex[:32],
            "meeting_id": meeting_id,
            "title": decision_data.get("title"),
            "description": decision_data.get("description"),
            "proposed_by": actor_id,
            "status": "proposed",
            "options": decision_data.get("options", []),
            "evidence": decision_data.get("evidence", []),
            "created_at": utcnow().isoformat(),
        }

        meeting.decisions = meeting.decisions or []
        meeting.decisions.append(decision)
        await db.commit()

        # Emit for Company Brain
        await publish_event(
            db,
            name="meeting.decision_proposed",
            actor_id=actor_id,
            organization_id=meeting.organization_id,
            payload=decision,
        )

        return decision

    async def approve_decision(
        self,
        db: AsyncSession,
        meeting_id: str,
        decision_id: str,
        *,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Approve a proposed decision."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found")

        # Find and update decision
        for decision in meeting.decisions or []:
            if decision["id"] == decision_id:
                decision["status"] = "approved"
                decision["approved_by"] = actor_id
                decision["approved_at"] = utcnow().isoformat()
                break

        await db.commit()

        # Create canonical decision through mutation boundary
        async with canonical_mutation_boundary(db, actor_id) as mutation:
            # This would create the actual canonical decision record
            pass

        return {"success": True, "decision_id": decision_id}

    async def capture_action_item(
        self,
        db: AsyncSession,
        meeting_id: str,
        action_data: Dict[str, Any],
        *,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Capture an action item during meeting."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found")

        action = {
            "id": uuid.uuid4().hex[:32],
            "meeting_id": meeting_id,
            "title": action_data.get("title"),
            "description": action_data.get("description"),
            "assignee_id": action_data.get("assignee_id"),
            "due_date": action_data.get("due_date"),
            "priority": action_data.get("priority", "medium"),
            "status": "open",
            "created_by": actor_id,
            "created_at": utcnow().isoformat(),
        }

        meeting.action_items = meeting.action_items or []
        meeting.action_items.append(action)
        await db.commit()

        return action

    # =========================================================================
    # RECORDING & TRANSCRIPTION
    # =========================================================================

    async def start_recording(
        self,
        db: AsyncSession,
        meeting_id: str,
        *,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Start recording a meeting."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting:
            raise ValueError("Meeting not found")

        if not meeting.recording_enabled:
            raise ValueError("Recording not enabled for this meeting")

        # Check if already recording
        existing = await db.execute(
            select(MeetingRecording).where(
                MeetingRecording.meeting_id == meeting_id,
                MeetingRecording.status.in_([RecordingStatus.RECORDING, RecordingStatus.PROCESSING]),
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("Recording already in progress")

        # Start recording via media provider
        recording_id = await self._start_media_recording(meeting)

        recording = MeetingRecording(
            id=uuid.uuid4().hex[:32],
            meeting_id=meeting_id,
            recording_id=recording_id,
            status=RecordingStatus.RECORDING,
            started_by=actor_id,
            started_at=utcnow(),
        )
        db.add(recording)
        meeting.recording_id = recording.id
        await db.commit()

        return {"recording_id": recording.id, "status": "recording"}

    async def stop_recording(
        self,
        db: AsyncSession,
        meeting_id: str,
        *,
        actor_id: str,
    ) -> Dict[str, Any]:
        """Stop recording a meeting."""
        meeting = await db.get(Meeting, meeting_id)
        if not meeting or not meeting.recording_id:
            raise ValueError("No active recording")

        recording = await db.get(MeetingRecording, meeting.recording_id)
        if not recording:
            raise ValueError("Recording not found")

        # Stop via media provider
        await self._stop_media_recording(meeting, recording)

        recording.status = RecordingStatus.PROCESSING
        recording.ended_at = utcnow()
        await db.commit()

        return {"recording_id": recording.id, "status": "processing"}

    # =========================================================================
    # MEDIA INFRASTRUCTURE (Private methods)
    # =========================================================================

    def _determine_scale(self, participant_count: int) -> MeetingScale:
        """Determine meeting scale based on participant count."""
        if participant_count <= 10:
            return MeetingScale.SMALL
        elif participant_count <= 50:
            return MeetingScale.TEAM
        elif participant_count <= 200:
            return MeetingScale.DEPARTMENT
        elif participant_count <= 1000:
            return MeetingScale.TOWN_HALL
        elif participant_count <= 10000:
            return MeetingScale.WEBINAR
        else:
            return MeetingScale.CONFERENCE

    async def _create_media_room(self, meeting: Meeting) -> str:
        """Create media room in LiveKit."""
        if self._media_provider != MediaProvider.LIVEKIT or not self._livekit_client:
            return f"vcos-{meeting.id}"

        try:
            room_name = f"vcos-{meeting.id}"
            await self._livekit_client.room.create_room(
                api.CreateRoomRequest(
                    name=room_name,
                    empty_timeout=300,
                    max_participants=self._get_max_participants(meeting.scale),
                    metadata=meeting.id,
                )
            )
            return room_name
        except Exception as e:
            logger.error(f"Failed to create media room: {e}")
            return f"vcos-{meeting.id}"

    def _get_max_participants(self, scale: MeetingScale) -> int:
        limits = {
            MeetingScale.SMALL: 10,
            MeetingScale.TEAM: 50,
            MeetingScale.DEPARTMENT: 200,
            MeetingScale.TOWN_HALL: 1000,
            MeetingScale.WEBINAR: 10000,
            MeetingScale.CONFERENCE: 50000,
        }
        return limits.get(scale, 50)

    async def _start_media_session(self, meeting: Meeting) -> None:
        """Start media session."""
        # Update room state
        if self._livekit_client:
            try:
                await self._livekit_client.room.update_room_metadata(
                    api.UpdateRoomMetadataRequest(
                        room=meeting.media_room_name,
                        metadata={"status": "active", "started_at": utcnow().isoformat()},
                    )
                )
            except Exception as e:
                logger.error(f"Failed to update room metadata: {e}")

    async def _end_media_session(self, meeting: Meeting) -> None:
        """End media session."""
        if self._livekit_client:
            try:
                await self._livekit_client.room.update_room_metadata(
                    api.UpdateRoomMetadataRequest(
                        room=meeting.media_room_name,
                        metadata={"status": "ended", "ended_at": utcnow().isoformat()},
                    )
                )
                # Delete room after delay
                await asyncio.sleep(300)
                await self._livekit_client.room.delete_room(
                    api.DeleteRoomRequest(room=meeting.media_room_name)
                )
            except Exception as e:
                logger.error(f"Failed to end media session: {e}")

    async def _generate_media_token(self, meeting: Meeting, participant: MeetingParticipant) -> str:
        """Generate LiveKit access token for participant."""
        if not self._livekit_client:
            return "mock-token"

        from livekit import api
        token = api.AccessToken(
            api_key="vcos-meetings",
            api_secret="secret",
        ).with_identity(participant.id).with_name(
            participant.display_name or participant.user_id or participant.email or "Guest"
        ).with_grants(api.VideoGrants(
            room_join=True,
            room=meeting.media_room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
        )).to_jwt()

        return token

    async def _start_media_recording(self, meeting: Meeting) -> str:
        """Start recording via media provider."""
        if self._livekit_client:
            try:
                result = await self._livekit_client.egress.start_room_composite_egress(
                    api.RoomCompositeEgressRequest(
                        room_name=meeting.media_room_name,
                        layout="speaker",
                        file_outputs=[
                            api.EncodedFileOutput(
                                filepath=f"recordings/{meeting.id}/{datetime.now().isoformat()}.mp4",
                                s3=api.S3Upload(
                                    bucket="vcos-recordings",
                                    access_key="",
                                    secret="",
                                    region="us-east-1",
                                ),
                            ),
                        ],
                    )
                )
                return result.egress_id
            except Exception as e:
                logger.error(f"Failed to start recording: {e}")
        return f"recording-{uuid.uuid4().hex[:16]}"

    async def _stop_media_recording(self, meeting: Meeting, recording: MeetingRecording) -> None:
        """Stop recording via media provider."""
        if self._livekit_client and recording.recording_id:
            try:
                await self._livekit_client.egress.stop_egress(
                    api.StopEgressRequest(egress_id=recording.recording_id)
                )
            except Exception as e:
                logger.error(f"Failed to stop recording: {e}")

    async def _process_recording(self, db: AsyncSession, meeting: Meeting) -> None:
        """Process recording after meeting ends."""
        # Recording processing would happen here
        # - Transcription
        # - Thumbnail generation
        # - Chapter detection
        pass

    async def _generate_meeting_summary(self, db: AsyncSession, meeting: Meeting) -> None:
        """Generate AI summary of meeting."""
        # This would integrate with Company Brain
        pass

    async def _notify_participants(
        self,
        db: AsyncSession,
        meeting: Meeting,
        event_type: str,
        payload: Dict[str, Any],
    ) -> None:
        """Notify participants of meeting events."""
        participants = await db.execute(
            select(MeetingParticipant).where(MeetingParticipant.meeting_id == meeting.id)
        )
        for participant in participants.scalars():
            if participant.user_id:
                await notification_service.send(
                    db,
                    user_id=participant.user_id,
                    type="meeting",
                    title=f"Meeting {event_type}: {meeting.title}",
                    body=payload.get("message", ""),
                    data=payload,
                )

    async def _broadcast_presentation_start(self, meeting: Meeting, presentation: Dict[str, Any]) -> None:
        """Broadcast presentation start to participants."""
        # Send via media data channel
        pass

    async def _broadcast_slide_change(self, meeting: Meeting, slide_index: int) -> None:
        """Broadcast slide change to participants."""
        pass

    def _hash_password(self, password: str) -> str:
        """Hash meeting password."""
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()

    def verify_password(self, password: str, password_hash: str) -> bool:
        """Verify meeting password."""
        return self._hash_password(password) == password_hash


meeting_service = MeetingService()