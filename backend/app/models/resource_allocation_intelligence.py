"""Resource Allocation Intelligence models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class AllocationDemand(Base, TimestampMixin):
    __tablename__ = "allocation_demands"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    role: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    required_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    hours_per_week: Mapped[float] = mapped_column(default=40.0, nullable=False)
    skills_required: Mapped[List[str]] = mapped_column(JSON, default=list)
    seniority_level: Mapped[Optional[str]] = mapped_column(String(40))
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="open", nullable=False)  # open, filled, partial, cancelled
    filled_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    allocationdemand_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_allocation_demands_org_status", "organization_id", "status"),
        Index("ix_allocation_demands_org_dates", "organization_id", "start_date", "end_date"),
    )


class CapacityAllocation(Base, TimestampMixin):
    __tablename__ = "capacity_allocations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    demand_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("allocation_demands.id", ondelete="SET NULL"), index=True
    )
    hours_per_week: Mapped[float] = mapped_column(default=0.0, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    allocation_type: Mapped[str] = mapped_column(String(20), default="project", nullable=False)
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    allocationdemand_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_capacity_allocs_org_dates", "organization_id", "start_date", "end_date"),
        Index("ix_capacity_allocs_emp_dates", "employee_id", "start_date", "end_date"),
        Index("ix_capacity_allocs_proj_dates", "project_id", "start_date", "end_date"),
    )


class CapacityHistory(Base, TimestampMixin):
    __tablename__ = "capacity_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    total_capacity_hours: Mapped[float] = mapped_column(default=40.0, nullable=False)
    allocated_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    available_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    utilization_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    __table_args__ = (
        Index("ix_capacity_history_org_emp", "organization_id", "employee_id"),
        Index("ix_capacity_history_org_time", "organization_id", "recorded_at"),
    )


class CapacitySnapshot(Base, TimestampMixin):
    __tablename__ = "capacity_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_capacity_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    total_allocated_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    total_available_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    utilization_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    department_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    role_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    project_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    allocationdemand_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "snapshot_date", name="uq_capacity_snapshots_org_date"),
        Index("ix_capacity_snapshots_org_date", "organization_id", "snapshot_date"),
    )