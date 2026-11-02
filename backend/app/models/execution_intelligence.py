"""Project Execution Intelligence models."""

from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class ProjectExecutionState(Base, TimestampMixin):
    __tablename__ = "project_execution_states"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    current_phase: Mapped[str] = mapped_column(String(60), default="planning", nullable=False)
    health_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    velocity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    predicted_completion: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    blockers_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_risks_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    milestone_completion_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    budget_utilization: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    resource_utilization: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    team_satisfaction: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    last_assessed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    projectexecutionstate_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("project_id", name="uq_proj_exec_state_project"),
        Index("ix_proj_exec_states_org_phase", "organization_id", "current_phase"),
    )


class ProjectExecutionSnapshot(Base, TimestampMixin):
    __tablename__ = "project_execution_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    snapshot_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    health_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    velocity: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    completed_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_tasks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_risks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    open_blockers: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    budget_spent: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    budget_total: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    team_size: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_task_completion_time: Mapped[float] = mapped_column(default=0.0, nullable=False)
    projectexecutionstate_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("project_id", "snapshot_date", name="uq_proj_exec_snap_proj_date"),
        Index("ix_proj_exec_snapshots_org_date", "organization_id", "snapshot_date"),
    )