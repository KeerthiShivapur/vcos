"""Meeting Models — Native VCOS Meetings, Conferences, and Presentations."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import JSON, String, Text, ForeignKey, Enum as SQLEnum, Index, DateTime, Boolean, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base, TimestampMixin, gen_uuid


class MeetingType(str, Enum):
    """Types of meetings."""
    STANDARD = "standard"           # Regular team meeting
    STANDUP = "standup"             # Daily standup
    PLANNING = "planning"           # Sprint/project planning
    REVIEW = "review"               # Retrospective/review
    ONE_ON_ONE = "one_on_one"       # 1:1 meeting
    TOWN_HALL = "town_hall"         # Company-wide
    WEBINAR = "webinar"             # External-facing presentation
    CONFERENCE = "conference"       # Large conference
    BOARD = "board"                 # Board meeting
    INTERVIEW = "interview"         # Candidate interview
    SALES = "sales"                 # Sales call
    SUPPORT = "support"             # Support session
    TRAINING = "training"           # Training session
    WORKSHOP = "workshop"           # Collaborative workshop


class MeetingStatus(str, Enum):
    """Meeting status."""
    DRAFT = "draft"                 # Created but not scheduled
    SCHEDULED = "scheduled"         # Scheduled for future
    WAITING = "waiting"             # Waiting for host to start
    ACTIVE = "active"               # In progress
    PAUSED = "paused"               # Temporarily paused
    ENDED = "ended"                 # Completed
    CANCELLED = "cancelled"         # Cancelled


class MeetingScale(str, Enum):
    """Meeting scale modes."""
    SMALL = "small"                 # 2-10 participants
    TEAM = "team"                   # 10-50
    DEPARTMENT = "department"       # 50-200
    TOWN_HALL = "town_hall"         # 200-1000
    WEBINAR = "webinar"             # 1000-10000
    CONFERENCE = "conference"       # 10000+


class ParticipantRole(str, Enum):
    """Participant roles in meeting."""
    HOST = "host"                   # Meeting organizer/owner
    CO_HOST = "co_host"             # Co-host with host permissions
    PRESENTER = "presenter"         # Currently presenting
    PARTICIPANT = "participant"     # Regular participant
    GUEST = "guest"                 # External guest
    OBSERVER = "observer"           # Watch-only


class ParticipantStatus(str, Enum):
    """Participant status in meeting."""
    INVITED = "invited"             # Invited but not responded
    PENDING = "pending"             # Waiting for approval
    JOINING = "joining"             # Currently joining
    JOINED = "joined"               # In meeting
    LEFT = "left"                   # Left meeting
    RECONNECTING = "reconnecting"   # Reconnecting


class RecordingStatus(str, Enum):
    """Recording status."""
    PENDING = "pending"             # Waiting to start
    RECORDING = "recording"         # Actively recording
    PROCESSING = "processing"       # Post-processing
    COMPLETED = "completed"         # Ready
    FAILED = "failed"               # Failed
    EXPIRED = "expired"             # Expired/deleted


class Meeting(Base, TimestampMixin):
    """Meeting model."""

    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Basic info
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    meeting_type: Mapped[MeetingType] = mapped_column(
        SQLEnum(MeetingType), default=MeetingType.STANDARD, nullable=False
    )
    scale: Mapped[MeetingScale] = mapped_column(
        SQLEnum(MeetingScale), default=MeetingScale.TEAM, nullable=False
    )

    # Timing
    scheduled_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    scheduled_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actual_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    actual_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    timezone: Mapped[str] = mapped_column(String(50), default="UTC")

    # Project context
    project_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )

    # Organization
    organizer_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)

    # Status
    status: Mapped[MeetingStatus] = mapped_column(
        SQLEnum(MeetingStatus), default=MeetingStatus.SCHEDULED, nullable=False
    )

    # Media
    media_provider: Mapped[str] = mapped_column(String(32), default="livekit")
    media_room_name: Mapped[Optional[str]] = mapped_column(String(255))
    media_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Settings
    agenda: Mapped[List[str]] = mapped_column(JSON, default=list)
    materials: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    settings: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)

    # Features
    recording_enabled: Mapped[bool] = mapped_column(default=False)
    transcription_enabled: Mapped[bool] = mapped_column(default=False)
    wait_room_enabled: Mapped[bool] = mapped_column(default=True)
    chat_enabled: Mapped[bool] = mapped_column(default=True)
    reactions_enabled: Mapped[bool] = mapped_column(default=True)
    screen_share_enabled: Mapped[bool] = mapped_column(default=True)

    # Access control
    require_approval: Mapped[bool] = mapped_column(default=False)
    allow_external_guests: Mapped[bool] = mapped_column(default=True)
    password_protected: Mapped[bool] = mapped_column(default=False)
    password_hash: Mapped[Optional[str]] = mapped_column(String(64))

    # Recording
    recording_id: Mapped[Optional[str]] = mapped_column(String(32))
    recording_url: Mapped[Optional[str]] = mapped_column(String(500))
    recording_status: Mapped[Optional[str]] = mapped_column(String(32))

    # Transcription
    transcription_url: Mapped[Optional[str]] = mapped_column(String(500))
    transcription_status: Mapped[Optional[str]] = mapped_column(String(32))

    # Presentation state
    current_presentation_id: Mapped[Optional[str]] = mapped_column(String(32))
    presentation_state: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # Decisions and action items
    decisions: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    action_items: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)

    # Summary
    summary: Mapped[Optional[str]] = mapped_column(Text)
    summary_generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Metadata
    created_by: Mapped[str] = mapped_column(String(32))
    started_by: Mapped[Optional[str]] = mapped_column(String(32))
    ended_by: Mapped[Optional[str]] = mapped_column(String(32))

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="meetings")
    project: Mapped[Optional["Project"]] = relationship()
    organizer: Mapped["User"] = relationship(foreign_keys=[organizer_id])
    participants: Mapped[List["MeetingParticipant"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    recordings: Mapped[List["MeetingRecording"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    transcripts: Mapped[List["MeetingTranscript"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    agenda_items: Mapped[List["MeetingAgendaItem"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    action_items: Mapped[List["MeetingActionItem"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    analytics: Mapped[Optional["MeetingAnalytics"]] = relationship(
        back_populates="meeting", uselist=False, cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("ix_meetings_org_status", "organization_id", "status"),
        Index("ix_meetings_org_scheduled", "organization_id", "scheduled_start"),
        Index("ix_meetings_organizer", "organizer_id"),
        Index("ix_meetings_project", "project_id"),
    )


class MeetingParticipant(Base, TimestampMixin):
    """Meeting participant model."""

    __tablename__ = "meeting_participants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True)

    # Identity
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Role
    role: Mapped[ParticipantRole] = mapped_column(
        SQLEnum(ParticipantRole), default=ParticipantRole.PARTICIPANT, nullable=False
    )

    # Status
    status: Mapped[ParticipantStatus] = mapped_column(
        SQLEnum(ParticipantStatus), default=ParticipantStatus.INVITED, nullable=False
    )

    # Timing
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(default=0)

    # Permissions
    can_present: Mapped[bool] = mapped_column(default=False)
    can_record: Mapped[bool] = mapped_column(default=False)
    can_mute_others: Mapped[bool] = mapped_column(default=False)
    can_remove_others: Mapped[bool] = mapped_column(default=False)

    # Settings
    audio_enabled: Mapped[bool] = mapped_column(default=True)
    video_enabled: Mapped[bool] = mapped_column(default=True)
    screen_sharing: Mapped[bool] = mapped_column(default=False)
    hand_raised: Mapped[bool] = mapped_column(default=False)

    # Network
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    connection_quality: Mapped[Optional[str]] = mapped_column(String(20))  # excellent, good, fair, poor

    # Metadata
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # Relationships
    meeting: Mapped["Meeting"] = relationship(back_populates="participants")
    user: Mapped[Optional["User"]] = relationship()

    # Indexes
    __table_args__ = (
        Index("ix_meeting_participants_meeting_user", "meeting_id", "user_id"),
        Index("ix_meeting_participants_meeting_email", "meeting_id", "email"),
    )


class MeetingAttendee(Base, TimestampMixin):
    """Meeting attendee model — alias for MeetingParticipant for backward compatibility."""

    __tablename__ = "meeting_participants"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[Optional[str]] = mapped_column(String(255), index=True)

    # Identity
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Role
    role: Mapped[ParticipantRole] = mapped_column(
        SQLEnum(ParticipantRole), default=ParticipantRole.PARTICIPANT, nullable=False
    )

    # Status
    status: Mapped[ParticipantStatus] = mapped_column(
        SQLEnum(ParticipantStatus), default=ParticipantStatus.INVITED, nullable=False
    )

    # Timing
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(default=0)

    # Permissions
    can_present: Mapped[bool] = mapped_column(default=False)
    can_record: Mapped[bool] = mapped_column(default=False)
    can_mute_others: Mapped[bool] = mapped_column(default=False)
    can_remove_others: Mapped[bool] = mapped_column(default=False)

    # Settings
    audio_enabled: Mapped[bool] = mapped_column(default=True)
    video_enabled: Mapped[bool] = mapped_column(default=True)
    screen_sharing: Mapped[bool] = mapped_column(default=False)
    hand_raised: Mapped[bool] = mapped_column(default=False)

    # Network
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    user_agent: Mapped[Optional[str]] = mapped_column(Text)
    connection_quality: Mapped[Optional[str]] = mapped_column(String(20))  # excellent, good, fair, poor

    # Metadata
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # Relationships (use same table, different FK names)
    meeting: Mapped["Meeting"] = relationship()
    employee: Mapped[Optional["Employee"]] = relationship()

    # Indexes
    __table_args__ = (
        Index("ix_meeting_attendees_meeting_employee", "meeting_id", "employee_id"),
        Index("ix_meeting_attendees_meeting_email", "meeting_id", "email"),
        {'extend_existing': True},
    )


class MeetingAgendaItem(Base, TimestampMixin):
    """Meeting agenda item model."""

    __tablename__ = "meeting_agenda_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    order: Mapped[int] = mapped_column(default=0)
    duration_minutes: Mapped[Optional[int]] = mapped_column()
    presenter_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey("users.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, in_progress, completed, skipped
    notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # Relationships
    meeting: Mapped["Meeting"] = relationship(back_populates="agenda_items")
    presenter: Mapped[Optional["User"]] = relationship()

    # Indexes
    __table_args__ = (
        Index("ix_agenda_items_meeting_order", "meeting_id", "order"),
    )


class MeetingActionItem(Base, TimestampMixin):
    """Meeting action item model."""

    __tablename__ = "meeting_action_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    assignee_id: Mapped[Optional[str]] = mapped_column(String(32), ForeignKey("users.id", ondelete="SET NULL"))
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    priority: Mapped[str] = mapped_column(String(20), default="medium")  # low, medium, high, critical
    status: Mapped[str] = mapped_column(String(32), default="open")  # open, in_progress, completed, cancelled
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # Relationships
    meeting: Mapped["Meeting"] = relationship(back_populates="action_items")
    assignee: Mapped[Optional["User"]] = relationship()

    # Indexes
    __table_args__ = (
        Index("ix_action_items_meeting_status", "meeting_id", "status"),
        Index("ix_action_items_assignee", "assignee_id"),
    )


class MeetingRecording(Base, TimestampMixin):
    """Meeting recording model."""

    __tablename__ = "meeting_recordings"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recording_id: Mapped[str] = mapped_column(String(64), index=True, nullable=False)  # Provider recording ID

    # Status
    status: Mapped[RecordingStatus] = mapped_column(
        SQLEnum(RecordingStatus), default=RecordingStatus.PENDING, nullable=False
    )

    # Media
    provider: Mapped[str] = mapped_column(String(32), default="livekit")
    provider_recording_id: Mapped[Optional[str]] = mapped_column(String(64))
    file_url: Mapped[Optional[str]] = mapped_column(String(500))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500))
    format: Mapped[str] = mapped_column(String(20), default="mp4")
    size_bytes: Mapped[int] = mapped_column(default=0)
    duration_seconds: Mapped[int] = mapped_column(default=0)

    # Transcription
    transcription_url: Mapped[Optional[str]] = mapped_column(String(500))
    transcription_status: Mapped[Optional[str]] = mapped_column(String(32))

    # Chapters/segments
    chapters: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)
    highlights: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    processing_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Access
    access_level: Mapped[str] = mapped_column(String(20), default="participants")  # public, organization, participants, private
    download_enabled: Mapped[bool] = mapped_column(default=True)
    expire_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Metadata
    started_by: Mapped[Optional[str]] = mapped_column(String(32))
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)

    # Relationships
    meeting: Mapped["Meeting"] = relationship(back_populates="recordings")
    transcript: Mapped[Optional["MeetingTranscript"]] = relationship(back_populates="recording")

    # Indexes
    __table_args__ = (
        Index("ix_recordings_meeting_status", "meeting_id", "status"),
    )


class MeetingTranscript(Base, TimestampMixin):
    """Meeting transcript model."""

    __tablename__ = "meeting_transcripts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recording_id: Mapped[Optional[str]] = mapped_column(
        String(32), ForeignKey("meeting_recordings.id", ondelete="SET NULL"), index=True
    )

    # Content
    full_text: Mapped[str] = mapped_column(Text)
    segments: Mapped[List[Dict[str, Any]]] = mapped_column(JSON, default=list)  # [{speaker, text, start, end, confidence}]

    # Processing
    provider: Mapped[str] = mapped_column(String(32), default="assemblyai")
    language: Mapped[str] = mapped_column(String(10), default="en")
    confidence: Mapped[float] = mapped_column(default=0.0)

    # Status
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending, processing, completed, failed
    error: Mapped[Optional[str]] = mapped_column(Text)

    # Timing
    processing_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    meeting: Mapped["Meeting"] = relationship(back_populates="transcripts")
    recording: Mapped[Optional["MeetingRecording"]] = relationship(back_populates="transcript")

    # Indexes
    __table_args__ = (
        Index("ix_transcripts_meeting_status", "meeting_id", "status"),
    )