"""Onboarding academy (Phase 10.10 — Onboarding Academy).

When a new employee joins, the AI creates a personalized onboarding plan:
company introduction, policies, security training, team members to meet,
projects to explore, a mentor, knowledge to read and training to complete —
all as a checklist with progress tracked by managers and HR.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class OnboardingPlan(Base, TimestampMixin):
    __tablename__ = "onboarding_plans"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", name="uq_onboarding_plan_employee"),
        Index("ix_onboarding_plans_org", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    # draft | active | completed
    progress: Mapped[float] = mapped_column(default=0.0)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    target_date: Mapped[Optional[date]] = mapped_column(Date)
    mentor_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    tasks: Mapped[list["OnboardingTask"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan", order_by="OnboardingTask.position"
    )


class OnboardingTask(Base, TimestampMixin):
    __tablename__ = "onboarding_tasks"
    __table_args__ = (
        Index("ix_onboarding_tasks_plan", "organization_id", "plan_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    plan_id: Mapped[str] = mapped_column(
        ForeignKey("onboarding_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="onboarding")
    # introduction | policies | knowledge | people | projects | training | mentor | system
    kind: Mapped[str] = mapped_column(String(30), default="checklist")
    # document | policy | video | meeting | people | project | training | quiz | mentor | checklist
    reference_id: Mapped[Optional[str]] = mapped_column(String(32))
    position: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    plan: Mapped["OnboardingPlan"] = relationship(back_populates="tasks")
