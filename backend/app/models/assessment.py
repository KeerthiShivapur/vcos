"""Assessments (Phase 10.8 — Assessments).

Assessments support quizzes (MCQ), coding, essays, scenario-based cases,
presentations, interviews and assignments. Each attempt can be evaluated by
AI (heuristic scoring of quiz answers), peers or managers. Finished
assessments update the employee's Skill Graph and Learning History, and emit
assessment.finished events.
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
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Assessment(Base, TimestampMixin):
    __tablename__ = "assessments"
    __table_args__ = (
        Index("ix_assessments_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(30), default="quiz")
    # quiz | coding | essay | case_study | presentation | interview | assignment
    course_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL")
    )
    certification_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("certifications.id", ondelete="SET NULL")
    )
    difficulty: Mapped[str] = mapped_column(String(20), default="intermediate")
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    passing_score: Mapped[float] = mapped_column(Float, default=70.0)
    max_score: Mapped[float] = mapped_column(Float, default=100.0)
    evaluation: Mapped[str] = mapped_column(String(30), default="ai")
    # ai | peer | manager | none
    skills: Mapped[Optional[list[str]]] = mapped_column(JSON)
    questions: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    # [{prompt, options, answer_index, points}]
    rubric: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="published")
    # draft | published | retired


class AssessmentAttempt(Base, TimestampMixin):
    __tablename__ = "assessment_attempts"
    __table_args__ = (
        Index("ix_assessment_attempts_emp", "organization_id", "employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    assessment_id: Mapped[str] = mapped_column(
        ForeignKey("assessments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="assigned")
    # assigned | in_progress | submitted | evaluated
    score: Mapped[Optional[float]] = mapped_column(Float)
    passed: Mapped[Optional[bool]] = mapped_column()
    answers: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    # [{question_index, answer, points_earned}]
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    evaluator_id: Mapped[Optional[str]] = mapped_column(String(32))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class AssessmentReview(Base, TimestampMixin):
    __tablename__ = "assessment_reviews"
    __table_args__ = (
        Index("ix_assessment_reviews_attempt", "organization_id", "attempt_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    attempt_id: Mapped[str] = mapped_column(
        ForeignKey("assessment_attempts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(32))
    review_kind: Mapped[str] = mapped_column(String(20), default="peer")
    # peer | manager | ai
    score: Mapped[Optional[float]] = mapped_column(Float)
    feedback: Mapped[Optional[str]] = mapped_column(Text)
