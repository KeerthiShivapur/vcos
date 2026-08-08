"""Collaboration foundation (Phase 6) — meeting rooms, sessions, participants, notes.

New tables only; the existing Phase 3 `meetings` table gains a few columns via
an idempotent ALTER at startup (see app/db/database.py).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class MeetingRoom(Base, TimestampMixin):
    """A place to meet — physical or virtual (recurring or ad hoc)."""

    __tablename__ = "meeting_rooms"
    __table_args__ = (Index("ix_meeting_rooms_org_status", "organization_id", "status"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    room_type: Mapped[str] = mapped_column(String(40), default="meeting")  # meeting|virtual_office|project|department|team|event|standup
    description: Mapped[Optional[str]] = mapped_column(Text)
    capacity: Mapped[int] = mapped_column(Integer, default=8)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="available")  # available|scheduled|occupied|maintenance
    department_id: Mapped[Optional[str]] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    is_public: Mapped[bool] = mapped_column(Boolean, default=True)
    allow_recording: Mapped[bool] = mapped_column(Boolean, default=True)
    settings: Mapped[Optional[str]] = mapped_column(Text)  # JSON: layout, background, default captions
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingSession(Base, TimestampMixin):
    """One runnable instance of a meeting — owns the join code and live state."""

    __tablename__ = "meeting_sessions"
    __table_args__ = (
        Index("ix_meeting_sessions_org_status", "organization_id", "status"),
        Index("ix_meeting_sessions_meeting", "meeting_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    room_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_rooms.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="scheduled")  # scheduled|live|ended|recorded
    meeting_code: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    max_participants: Mapped[int] = mapped_column(Integer, default=50)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    is_recording: Mapped[bool] = mapped_column(Boolean, default=False)
    is_captions_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_translation_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    is_transcribing: Mapped[bool] = mapped_column(Boolean, default=False)
    settings: Mapped[Optional[str]] = mapped_column(Text)  # JSON: media gateway, layout, simulcast
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingParticipant(Base):
    """Per-session attendance + live media state for one employee."""

    __tablename__ = "meeting_participants"
    __table_args__ = (Index("ix_meeting_participants_session_emp", "session_id", "employee_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    session_id: Mapped[str] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="CASCADE"), nullable=False)
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False, index=True)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default="participant")  # host|co_host|participant|observer
    status: Mapped[str] = mapped_column(String(30), default="invited")  # invited|joined|left|declined|no_show
    device: Mapped[Optional[str]] = mapped_column(String(60))
    mic_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    camera_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    screen_sharing: Mapped[bool] = mapped_column(Boolean, default=False)
    is_present: Mapped[bool] = mapped_column(Boolean, default=False)
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    speaking_seconds: Mapped[int] = mapped_column(Integer, default=0)
    messages_count: Mapped[int] = mapped_column(Integer, default=0)
    raised_hand: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingNote(Base):
    """Collaborative markdown notes per meeting (becomes knowledge + AI memory)."""

    __tablename__ = "meeting_notes"
    __table_args__ = (Index("ix_meeting_notes_meeting", "meeting_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="SET NULL"))
    author_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text, default="")
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingChatMessage(Base):
    """Live in-session chat message (Phase 6.5)."""

    __tablename__ = "meeting_chat_messages"
    __table_args__ = (Index("ix_meeting_chat_meeting", "meeting_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="SET NULL"))
    employee_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    kind: Mapped[str] = mapped_column(String(20), default="message")  # message|system
    reply_to: Mapped[Optional[str]] = mapped_column(String(32))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingWhiteboard(Base):
    """One shared whiteboard per meeting — JSON stroke/shape state + version (Phase 6.4)."""

    __tablename__ = "meeting_whiteboards"
    __table_args__ = (Index("ix_meeting_whiteboards_meeting", "meeting_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="SET NULL"))
    content: Mapped[Optional[str]] = mapped_column(Text)  # JSON: {shapes: [...], background: ...}
    version: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingRecording(Base):
    """A captured meeting (video/audio) with storage metadata (Phase 6.7)."""

    __tablename__ = "meeting_recordings"
    __table_args__ = (Index("ix_meeting_recordings_meeting", "meeting_id", "status"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="SET NULL"))
    room_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_rooms.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200), default="")
    kind: Mapped[str] = mapped_column(String(20), default="manual")  # auto|manual
    status: Mapped[str] = mapped_column(String(30), default="requested")  # requested|recording|processing|completed|failed
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    file_url: Mapped[Optional[str]] = mapped_column(String(500))
    storage_key: Mapped[Optional[str]] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    format: Mapped[str] = mapped_column(String(20), default="webm")
    mime_type: Mapped[str] = mapped_column(String(80), default="video/webm")
    resolution: Mapped[Optional[str]] = mapped_column(String(40))
    captions_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    language: Mapped[str] = mapped_column(String(16), default="en")
    visibility: Mapped[str] = mapped_column(String(20), default="org")  # private|org|participants
    retention_days: Mapped[int] = mapped_column(Integer, default=365)
    is_encrypted: Mapped[bool] = mapped_column(Boolean, default=True)
    created_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingTranscript(Base):
    """Full meeting transcript + speaker segments (Phase 6.8/6.10)."""

    __tablename__ = "meeting_transcripts"
    __table_args__ = (Index("ix_meeting_transcripts_meeting", "meeting_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="requested")  # requested|transcribing|completed|failed
    language: Mapped[str] = mapped_column(String(16), default="en")
    content: Mapped[Optional[str]] = mapped_column(Text)
    segments: Mapped[Optional[str]] = mapped_column(Text)  # JSON: [{speaker, start_ms, text}]
    speakers: Mapped[Optional[str]] = mapped_column(Text)  # JSON: [{employee_id, name, speaking_ms}]
    word_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingCaption(Base):
    """One caption segment — live captions + translation (Phase 6.8/6.9)."""

    __tablename__ = "meeting_captions"
    __table_args__ = (Index("ix_meeting_captions_meeting", "meeting_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="SET NULL"))
    employee_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    language: Mapped[str] = mapped_column(String(16), default="en")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text: Mapped[Optional[str]] = mapped_column(Text)
    translation_language: Mapped[Optional[str]] = mapped_column(String(16))
    start_ms: Mapped[int] = mapped_column(Integer, default=0)
    end_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingDecision(Base):
    """A decision recorded from a meeting — feeds knowledge + graph (Phase 6.10)."""

    __tablename__ = "meeting_decisions"
    __table_args__ = (Index("ix_meeting_decisions_meeting", "meeting_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="SET NULL"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    made_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual|transcript|ai
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft|confirmed
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class MeetingAnalytics(Base):
    """Per-session analytics snapshot (attendance intelligence, engagement) — Phase 6.11/6.14."""

    __tablename__ = "meeting_analytics"
    __table_args__ = (Index("ix_meeting_analytics_meeting", "meeting_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False)
    session_id: Mapped[Optional[str]] = mapped_column(ForeignKey("meeting_sessions.id", ondelete="SET NULL"))
    duration_seconds: Mapped[int] = mapped_column(Integer, default=0)
    participants_invited: Mapped[int] = mapped_column(Integer, default=0)
    participants_joined: Mapped[int] = mapped_column(Integer, default=0)
    participants_present: Mapped[int] = mapped_column(Integer, default=0)
    late_joiners: Mapped[int] = mapped_column(Integer, default=0)
    early_exits: Mapped[int] = mapped_column(Integer, default=0)
    with_mic: Mapped[int] = mapped_column(Integer, default=0)
    with_camera: Mapped[int] = mapped_column(Integer, default=0)
    screen_shares: Mapped[int] = mapped_column(Integer, default=0)
    messages_count: Mapped[int] = mapped_column(Integer, default=0)
    engagement_score: Mapped[int] = mapped_column(Integer, default=0)
    snapshot: Mapped[Optional[str]] = mapped_column(Text)  # JSON: per-participant metrics + topics
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
