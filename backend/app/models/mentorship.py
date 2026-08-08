"""Internal mentorship (Phase 10.7 — Internal Mentorship).

Employees become mentors by creating a MentorProfile (topics, availability,
capacity). AI recommends the best mentor based on skills, projects,
availability, department and knowledge. A Mentorship links mentor + mentee
with goals and topics; sessions and feedback track progress. The
mentorship worker sends session reminders and keeps stale requests moving.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class MentorProfile(Base, TimestampMixin):
    __tablename__ = "mentor_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", name="uq_mentor_profile_employee"),
        Index("ix_mentor_profiles_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    bio: Mapped[Optional[str]] = mapped_column(Text)
    topics: Mapped[Optional[list[str]]] = mapped_column(JSON)
    availability: Mapped[str] = mapped_column(String(40), default="weekly")
    # weekly | biweekly | monthly | on_demand
    max_mentees: Mapped[int] = mapped_column(Integer, default=3)
    active: Mapped[bool] = mapped_column(default=True)


class Mentorship(Base, TimestampMixin):
    __tablename__ = "mentorships"
    __table_args__ = (
        Index("ix_mentorships_mentor", "organization_id", "mentor_id", "status"),
        Index("ix_mentorships_mentee", "organization_id", "mentee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    mentor_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    mentee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    topic: Mapped[str] = mapped_column(String(255), nullable=False)
    goals: Mapped[Optional[list[str]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | active | completed | declined
    requested_by: Mapped[str] = mapped_column(String(30), default="mentee")
    # mentee | mentor | manager | ai
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float] = mapped_column(Float, default=0.0)


class MentorshipSession(Base, TimestampMixin):
    __tablename__ = "mentorship_sessions"
    __table_args__ = (
        Index("ix_mentorship_sessions", "organization_id", "mentorship_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    mentorship_id: Mapped[str] = mapped_column(
        ForeignKey("mentorships.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), default="call")
    # call | chat | meeting | review
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)


class MentorshipFeedback(Base, TimestampMixin):
    __tablename__ = "mentorship_feedback"
    __table_args__ = (
        Index("ix_mentorship_feedback", "organization_id", "mentorship_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    mentorship_id: Mapped[str] = mapped_column(
        ForeignKey("mentorships.id", ondelete="CASCADE"), index=True, nullable=False
    )
    session_id: Mapped[Optional[str]] = mapped_column(String(32))
    author_id: Mapped[str] = mapped_column(String(32), nullable=False)
    rating: Mapped[int] = mapped_column(Integer, default=5)
    comment: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
