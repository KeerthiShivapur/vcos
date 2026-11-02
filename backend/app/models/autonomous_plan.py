"""Autonomous Plan models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class AutonomousPlanStatus(str):
    DRAFT = "draft"
    PROPOSED = "proposed"
    APPROVED = "approved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ON_HOLD = "on_hold"


class AutonomousPlanType(str):
    STRATEGIC = "strategic"
    OPERATIONAL = "operational"
    PROJECT = "project"
    RESOURCE = "resource"
    HIRING = "hiring"
    BUDGET = "budget"
    PROCESS = "process"
    TECHNOLOGY = "technology"


class AutonomousPlan(Base, TimestampMixin):
    __tablename__ = "autonomous_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    plan_type: Mapped[str] = mapped_column(String(40), default=AutonomousPlanType.STRATEGIC, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=AutonomousPlanStatus.DRAFT, nullable=False, index=True)
    creator_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    budget_amount: Mapped[Optional[float]] = mapped_column(default=None)
    goals: Mapped[List[str]] = mapped_column(JSON, default=list)
    milestones: Mapped[List[dict]] = mapped_column(JSON, default=list)
    tasks: Mapped[List[dict]] = mapped_column(JSON, default=list)
    resources: Mapped[List[dict]] = mapped_column(JSON, default=list)
    risks: Mapped[List[dict]] = mapped_column(JSON, default=list)
    assumptions: Mapped[List[str]] = mapped_column(JSON, default=list)
    constraints: Mapped[List[str]] = mapped_column(JSON, default=list)
    success_criteria: Mapped[List[str]] = mapped_column(JSON, default=list)
    autonomousplanstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_autonomous_plans_org_status", "organization_id", "status"),
        Index("ix_autonomous_plans_org_creator", "organization_id", "creator_id"),
        Index("ix_autonomous_plans_org_dates", "organization_id", "start_date", "end_date"),
    )