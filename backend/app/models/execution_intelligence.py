"""Slice 4G.1 — Canonical Project Execution Intelligence.

One canonical execution record per project: a deterministic, evidence-backed
health model (health score + factors + one human explain + primary cause),
a real critical path (CPM: forward/backward passes with slack over the
existing TaskDependency graph), blocker analysis with root-cause chains and
systemic grouping, capacity constraints read from the 4F.6 capability record,
pending decisions read from the 4A decision registry, the goal chain
(company goal -> objective -> project), and the mandatory outcome record
(planned vs actual + assessment). A snapshot history makes "what changed"
answerable over time.

Everything is change-driven from the SAME durable events the platform
already emits (project.*, task.*, milestone.*, dependency.*, decision.*,
goal.*) and every event-driven write is exact-once on source_event_id.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
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


class ProjectExecutionState(Base, TimestampMixin):
    __tablename__ = "project_execution_states"
    __table_args__ = (
        Index("ix_exec_state_org_health", "organization_id", "health_status"),
        Index("ix_exec_state_org_project", "organization_id", "project_id"),
        UniqueConstraint("organization_id", "project_id", name="uq_exec_state_project"),
        UniqueConstraint(
            "organization_id", "project_id", "source_event_id",
            name="uq_exec_state_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_event_id: Mapped[Optional[str]] = mapped_column(String(32))
    health_score: Mapped[int] = mapped_column(Integer, default=80)
    health_status: Mapped[str] = mapped_column(String(20), default="healthy")
    factors: Mapped[Optional[dict]] = mapped_column(JSON)
    explain: Mapped[Optional[str]] = mapped_column(Text)
    primary_cause: Mapped[Optional[str]] = mapped_column(String(240))
    counts: Mapped[Optional[dict]] = mapped_column(JSON)
    critical_path: Mapped[Optional[dict]] = mapped_column(JSON)
    blockers: Mapped[Optional[list]] = mapped_column(JSON)
    systemic_blockers: Mapped[Optional[list]] = mapped_column(JSON)
    capacity_constraints: Mapped[Optional[list]] = mapped_column(JSON)
    pending_decisions: Mapped[Optional[list]] = mapped_column(JSON)
    goal_chain: Mapped[Optional[list]] = mapped_column(JSON)
    outcome: Mapped[Optional[dict]] = mapped_column(JSON)


class ProjectExecutionSnapshot(Base, TimestampMixin):
    __tablename__ = "project_execution_snapshots"
    __table_args__ = (
        Index(
            "ix_exec_snap_org_project_time",
            "organization_id", "project_id", "occurred_at",
        ),
        UniqueConstraint(
            "organization_id", "project_id", "source_event_id",
            name="uq_exec_snap_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    event_name: Mapped[str] = mapped_column(String(60), nullable=False)
    health_score: Mapped[int] = mapped_column(Integer, default=80)
    health_status: Mapped[str] = mapped_column(String(20), default="healthy")
    primary_cause: Mapped[Optional[str]] = mapped_column(String(240))
    explain: Mapped[Optional[str]] = mapped_column(Text)
    factors: Mapped[Optional[dict]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )