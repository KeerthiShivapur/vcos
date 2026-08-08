"""Goals and key results (Phase 3 — Work Execution Engine)."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"
    __table_args__ = (Index("ix_goals_org_owner", "organization_id", "owner_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    parent_goal_id: Mapped[Optional[str]] = mapped_column(ForeignKey("goals.id", ondelete="SET NULL"))
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    scope: Mapped[str] = mapped_column(String(30), default="team")  # company|department|team|project|personal
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    department_id: Mapped[Optional[str]] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="planned")  # planned|in_progress|completed|at_risk
    progress: Mapped[float] = mapped_column(Float, default=0)  # 0-100
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class KeyResult(Base, TimestampMixin):
    __tablename__ = "goal_key_results"
    __table_args__ = (Index("ix_key_results_org_goal", "organization_id", "goal_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    metric: Mapped[Optional[str]] = mapped_column(String(120))
    unit: Mapped[Optional[str]] = mapped_column(String(40))
    target: Mapped[Optional[float]] = mapped_column(Float)
    current: Mapped[Optional[float]] = mapped_column(Float)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="on_track")  # on_track|at_risk|behind|completed
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
