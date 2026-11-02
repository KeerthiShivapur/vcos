"""Learning Cycle model."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class LearningCycleStatus(str):
    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class LearningCycleType(str):
    INDIVIDUAL = "individual"
    TEAM = "team"
    ORGANIZATIONAL = "organizational"
    PROJECT = "project"
    RETROSPECTIVE = "retrospective"


class LearningCycle(Base, TimestampMixin):
    __tablename__ = "learning_cycles"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    cycle_type: Mapped[str] = mapped_column(String(30), default=LearningCycleType.INDIVIDUAL, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default=LearningCycleStatus.PLANNING, nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    start_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    learning_objectives: Mapped[List[str]] = mapped_column(JSON, default=list)
    key_insights: Mapped[List[str]] = mapped_column(JSON, default=list)
    actions_taken: Mapped[List[str]] = mapped_column(JSON, default=list)
    outcomes: Mapped[List[str]] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    status_detail: Mapped[Optional[str]] = mapped_column(Text)
    learningcyclestatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_learning_cycles_org_status", "organization_id", "status"),
        Index("ix_learning_cycles_org_owner", "organization_id", "owner_id"),
    )