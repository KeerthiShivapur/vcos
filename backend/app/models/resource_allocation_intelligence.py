"""Slice 4G.4 - Universal Resource & Capacity Allocation Intelligence models.

The canonical resource allocation ledger. Every table is exact-once on
source_event_id so replays of capacity.* events converge to the same row:

* AllocationDemand     - one live demand per (org, project, capability,
                         window): the work asks the organization for units of
                         a capability inside a time window at a proficiency.
* CapacityAllocation   - a human-governed allocation decision (a claim on
                         supply) with its later outcome (achieved/partial/
                         missed) that feeds 4E.7 organizational learning.
* CapacitySnapshot     - one persisted recompute of a (capability, window)
                         neighborhood keyed by event - replays converge and
                         the latest row per window is the live state.
* CapacityHistory      - append-only temporal trail of demand/allocation/
                         supply changes with reasons (organizational memory).

Demand windows are the temporal backbone: a project demanding "8 security
engineers" for September 1-30 is measured against the supply in THAT window,
never against today's snapshot. Nothing here models money; financial resource
planning belongs to the future Finance layer (4I) - VCOS understands resources
wherever they materially affect execution.
"""

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# Demand proficiency bands (matched against 4F.2/4F.3 expertise scores).
PROFICIENCY_HIGH = "high"      # score >= 50: strong trusted evidence
PROFICIENCY_EXPERT = "expert"  # score >= 70: deep trusted evidence
EXPERTISE_STRONG = 50.0
EXPERTISE_DEEP = 70.0

# Allocation outcome taxonomy for learning.
ALLOCATION_STATUSES: tuple[str, ...] = ("active", "completed")
ALLOCATION_OUTCOMES: tuple[str, ...] = ("achieved", "partial", "missed")

# Supply states the engine reports (mirrors the 4F.6 capability ledger).
SUPPLY_STATES: tuple[str, ...] = ("available", "stretched", "constrained", "unknown")


class AllocationDemand(Base, TimestampMixin):
    """One project's explicit resource demand: capability x units x window.

    The live row is maintained by the governed write path (projects:manage);
    the event handler records CapacityHistory + CapacitySnapshot for the
    affected (capability, window) neighborhood - exact-once on the event id.
    """

    __tablename__ = "allocation_demands"
    __table_args__ = (
        Index("ix_ad_org_cap", "organization_id", "capability"),
        Index("ix_ad_org_project", "organization_id", "project_id"),
        UniqueConstraint(
            "organization_id", "project_id", "capability", "window_start", "window_end",
            name="uq_ad_live",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    capability: Mapped[str] = mapped_column(String(120), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # the execution window the demand applies to
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    proficiency: Mapped[str] = mapped_column(String(24), nullable=False, default="high")
    note: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class CapacityAllocation(Base, TimestampMixin):
    """A human-governed allocation: X units of a capability committed to a
    project inside a window. The outcome is recorded later by a human and
    pours into 4E.7 learning (this is where VCOS gets smarter from history).
    """

    __tablename__ = "capacity_allocations"
    __table_args__ = (
        Index("ix_ca_org_cap", "organization_id", "capability"),
        Index("ix_ca_org_project", "organization_id", "project_id"),
        UniqueConstraint(
            "organization_id", "project_id", "capability", "window_start", "window_end",
            name="uq_ca_live",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(String(32), nullable=False)
    project_label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    capability: Mapped[str] = mapped_column(String(120), nullable=False)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    outcome: Mapped[Optional[str]] = mapped_column(String(16), default=None)
    note: Mapped[Optional[str]] = mapped_column(Text)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class CapacitySnapshot(Base, TimestampMixin):
    """One persisted recompute of a (capability, window) neighborhood.

    The incremental guarantee: a capacity event refreshes ONLY the affected
    capability/window and writes one snapshot row keyed by
    (org, capability, window, event) - replays converge. The latest row per
    window is the live state served by the brain.
    """

    __tablename__ = "capacity_snapshots"
    __table_args__ = (
        Index("ix_cs_org_cap_time", "organization_id", "capability", "occurred_at"),
        UniqueConstraint(
            "organization_id", "capability", "window_start", "window_end", "source_event_id",
            name="uq_cs_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    capability: Mapped[str] = mapped_column(String(120), nullable=False)
    window_start: Mapped[date] = mapped_column(Date, nullable=False)
    window_end: Mapped[date] = mapped_column(Date, nullable=False)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    event_name: Mapped[str] = mapped_column(String(60), nullable=False)
    # supply in the window (4F.6 ledger, read-only here)
    supply_potential: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supply_committed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supply_available: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    supply_state: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    # demand in the window (explicit project demands, aggregated)
    demand_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    allocated_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    gap: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    utilization: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    is_bottleneck: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    affected_projects: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    affected_goals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # the full evidence-backed assessment served by the brain
    payload_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class CapacityHistory(Base, TimestampMixin):
    """Append-only temporal trail of resource changes (organizational memory).

    One row per (entity, field, event): a demand's creation/removal, an
    allocation's creation/completion, a supply state change. Replays are
    exact-once.
    """

    __tablename__ = "capacity_history"
    __table_args__ = (
        Index("ix_ch_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_ch_org_time", "organization_id", "changed_at"),
        UniqueConstraint(
            "organization_id", "entity_type", "entity_id", "field", "source_event_id",
            name="uq_ch_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # capability | demand | allocation
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    field: Mapped[str] = mapped_column(String(40), nullable=False)
    old_value: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    new_value: Mapped[Optional[str]] = mapped_column(String(500), default=None)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
