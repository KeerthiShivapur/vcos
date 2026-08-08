"""Learning profiles and learning history (Phase 10.1 — Learning Foundation).

Every employee has exactly one living learning profile. It aggregates the
employee's learning score, career stage, preferred learning style, weekly
learning hours budget, course completions, certifications, active mentor and
last learning date. Learning history entries record every learning action
(course completion, assessment, certification, mentorship session, path
completion) so the dashboard and analytics can reconstruct the journey.
"""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class LearningProfile(Base, TimestampMixin):
    __tablename__ = "learning_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", name="uq_learning_profile_employee"),
        Index("ix_learning_profiles_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    learning_score: Mapped[float] = mapped_column(Float, default=0.0)
    career_stage: Mapped[str] = mapped_column(String(40), default="developing")
    # developing | established | senior | expert | leader | executive
    preferred_learning: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # mixed | video | reading | hands_on | social | structured
    weekly_learning_hours: Mapped[int] = mapped_column(Integer, default=4)
    completed_courses: Mapped[int] = mapped_column(Integer, default=0)
    certifications: Mapped[int] = mapped_column(Integer, default=0)
    mentor_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    last_learning_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    career_goals: Mapped[Optional[list[str]]] = mapped_column(JSON)
    learning_goals: Mapped[Optional[list[str]]] = mapped_column(JSON)

    employee: Mapped["Employee"] = relationship(  # noqa: F821
        back_populates="learning_profile", foreign_keys=[employee_id]
    )

    @property
    def level(self) -> str:
        """Simple learning-level label derived from the learning score."""
        if self.learning_score >= 80:
            return "expert"
        if self.learning_score >= 50:
            return "advanced"
        if self.learning_score >= 20:
            return "developing"
        return "foundational"


class LearningHistoryEntry(Base, TimestampMixin):
    __tablename__ = "learning_history"
    __table_args__ = (
        Index("ix_learning_history_emp_date", "organization_id", "employee_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # course_completion | assessment | certification | mentorship_session
    # path_completion | book | training | onboarding | skill_update
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    score: Mapped[Optional[float]] = mapped_column(Float)
    time_minutes: Mapped[int] = mapped_column(Integer, default=0)
    certificate_id: Mapped[Optional[str]] = mapped_column(String(32))
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    employee: Mapped["Employee"] = relationship()  # noqa: F821
