"""Collaboration models for meetings, notes, whiteboards, and recordings."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class MeetingAnalytics(Base, TimestampMixin):
    __tablename__ = "meeting_analytics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    total_duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scheduled_duration_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_duration_minutes: Mapped[Optional[int]] = mapped_column(Integer)
    attendees_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    expected_attendees_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attendance_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    action_items_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    action_items_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    decisions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    notes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    speakers_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engagement_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    sentiment_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    topics_discussed: Mapped[List[str]] = mapped_column(JSON, default=list)
    key_takeaways: Mapped[List[str]] = mapped_column(JSON, default=list)
    improvement_suggestions: Mapped[List[str]] = mapped_column(JSON, default=list)

    meeting: Mapped["Meeting"] = relationship(back_populates="analytics", uselist=False)

    __table_args__ = (
        Index("ix_meeting_analytics_org", "organization_id"),
    )


class MeetingCaption(Base, TimestampMixin):
    __tablename__ = "meeting_captions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    speaker_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    language: Mapped[str] = mapped_column(String(10), default="en", nullable=False)
    is_edited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    edited_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    speaker_name: Mapped[Optional[str]] = mapped_column(String(200))

    __table_args__ = (
        Index("ix_meeting_captions_meeting_time", "meeting_id", "start_time"),
        {"extend_existing": True},
    )


class MeetingChatMessage(Base, TimestampMixin):
    __tablename__ = "meeting_chat_messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    message_type: Mapped[str] = mapped_column(String(20), default="text", nullable=False)  # text, file, link, system
    reply_to_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("meeting_chat_messages.id", ondelete="SET NULL"), index=True
    )
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reactions: Mapped[dict] = mapped_column(JSON, default=dict)
    attachments: Mapped[List[dict]] = mapped_column(JSON, default=list)

    __table_args__ = (
        Index("ix_meeting_chat_meeting_time", "meeting_id", "created_at"),
    )


class MeetingDecision(Base, TimestampMixin):
    __tablename__ = "meeting_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    decision_type: Mapped[str] = mapped_column(String(40), default="general", nullable=False)
    decided_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    decision_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    options_considered: Mapped[List[str]] = mapped_column(JSON, default=list)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    action_items: Mapped[List[str]] = mapped_column(JSON, default=list)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)

    meeting: Mapped["Meeting"] = relationship()
    decided_by_employee: Mapped[Optional["Employee"]] = relationship()

    __table_args__ = (
        Index("ix_meeting_decisions_meeting", "meeting_id"),
        {"extend_existing": True},
    )


class MeetingNote(Base, TimestampMixin):
    __tablename__ = "meeting_notes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)

    meeting: Mapped["Meeting"] = relationship()
    author: Mapped["Employee"] = relationship()

    __table_args__ = (
        Index("ix_meeting_notes_meeting", "meeting_id"),
        Index("ix_meeting_notes_author", "author_id"),
        {"extend_existing": True},
    )


class MeetingWhiteboard(Base, TimestampMixin):
    __tablename__ = "meeting_whiteboards"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    meeting_id: Mapped[str] = mapped_column(
        ForeignKey("meetings.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_meeting_whiteboards_meeting", "meeting_id"),
    )