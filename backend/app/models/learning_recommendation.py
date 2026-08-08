"""Personalized learning recommendations (Phase 10.5, 10.9 — Learning
Recommendations).

The AI recommends courses, mentors, communities, projects, books,
knowledge, training, certifications and conferences — driven by skill gaps,
career targets, current projects, role requirements and organizational
needs. Recommendations are deduplicated per (employee, kind, entity) and
can be accepted, dismissed or completed; acting on a recommendation
updates the relevant pipeline (enroll, request mentorship, join community).
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Float, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class LearningRecommendation(Base, TimestampMixin):
    __tablename__ = "learning_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "employee_id", "kind", "entity_id",
            name="uq_learning_recommendation",
        ),
        Index("ix_learning_recommendations_emp", "organization_id", "employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    # course | mentor | community | project | book | knowledge | training
    # certification | conference
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    reason: Mapped[Optional[str]] = mapped_column(String(500))
    score: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(40), default="ai")
    # ai | skill_gap | career | role | project | manager | onboarding
    entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | accepted | dismissed | completed
