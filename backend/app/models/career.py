"""Career paths and career progress (Phase 10.6 — Career Path Engine).

Every employee sees a career roadmap: Junior Engineer → Engineer → Senior →
Lead → Architect → Principal → Director → CTO. Each CareerPathStep defines
the required skills (with minimum levels), years of experience and evidence
criteria. CareerProgress tracks the employee's current step, target step and
a readiness score computed from skill coverage, experience, completed
courses, certifications and mentorship. When readiness crosses a threshold
the system flags a promotion signal for the manager.
"""

from typing import Any, Optional

from sqlalchemy import JSON, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class CareerPath(Base, TimestampMixin):
    __tablename__ = "career_paths"
    __table_args__ = (
        UniqueConstraint("organization_id", "title", name="uq_career_path_title_org"),
        Index("ix_career_paths_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Engineering | Engineering Management | Sales | Marketing | People | Finance
    description: Mapped[Optional[str]] = mapped_column(Text)
    department: Mapped[Optional[str]] = mapped_column(String(100))
    levels: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="published")

    steps: Mapped[list["CareerPathStep"]] = relationship(
        back_populates="path", cascade="all, delete-orphan", order_by="CareerPathStep.position"
    )


class CareerPathStep(Base, TimestampMixin):
    __tablename__ = "career_path_steps"
    __table_args__ = (
        UniqueConstraint("organization_id", "career_path_id", "position", name="uq_career_step_pos"),
        Index("ix_career_steps_path", "organization_id", "career_path_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    career_path_id: Mapped[str] = mapped_column(
        ForeignKey("career_paths.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    # Junior Engineer, Engineer, Senior, Lead, Architect, Principal, Director, CTO
    position: Mapped[int] = mapped_column(Integer, default=0)
    level: Mapped[int] = mapped_column(Integer, default=1)
    required_skills: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    # [{skill, level}]
    required_years: Mapped[int] = mapped_column(Integer, default=2)
    responsibilities: Mapped[Optional[str]] = mapped_column(Text)
    criteria: Mapped[Optional[list[str]]] = mapped_column(JSON)

    path: Mapped["CareerPath"] = relationship(back_populates="steps")


class CareerProgress(Base, TimestampMixin):
    __tablename__ = "career_progress"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", name="uq_career_progress_employee"),
        Index("ix_career_progress_org", "organization_id", "readiness_score"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    career_path_id: Mapped[Optional[str]] = mapped_column(String(32))
    current_step_id: Mapped[Optional[str]] = mapped_column(String(32))
    target_step_id: Mapped[Optional[str]] = mapped_column(String(32))
    readiness_score: Mapped[float] = mapped_column(Float, default=0.0)
    evidence: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    # [{category, label, value, met}]


class PromotionSignal(Base, TimestampMixin):
    __tablename__ = "promotion_signals"
    __table_args__ = (
        Index("ix_promotion_signals_emp", "organization_id", "employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    career_step_id: Mapped[Optional[str]] = mapped_column(String(32))
    target_title: Mapped[str] = mapped_column(String(150), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(20), default="open")
    # open | reviewed | dismissed
    evidence: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
