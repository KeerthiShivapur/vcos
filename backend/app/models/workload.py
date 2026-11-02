"""Workload and capacity models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import DateTime, Date, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class WorkloadSnapshot(Base, TimestampMixin):
    __tablename__ = "workload_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    billable_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    non_billable_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    meeting_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    focus_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    overtime_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    capacity_hours: Mapped[float] = mapped_column(default=40.0, nullable=False)
    utilization_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    project_hours: Mapped[dict] = mapped_column(JSON, default=dict)
    task_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    meeting_hours_breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    snapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("employee_id", "snapshot_date", name="uq_workload_snapshots_emp_date"),
        Index("ix_workload_snapshots_org_date", "organization_id", "snapshot_date"),
    )


class CapacityPlan(Base, TimestampMixin):
    __tablename__ = "capacity_plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    team_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    total_capacity_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    allocated_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    available_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    utilization_target: Mapped[float] = mapped_column(default=0.85, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)  # draft, active, archived
    created_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)

    __table_args__ = (
        Index("ix_capacity_plans_org_dates", "organization_id", "period_start", "period_end"),
        Index("ix_capacity_plans_org_status", "organization_id", "status"),
    )


class Allocation(Base, TimestampMixin):
    __tablename__ = "allocations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    capacity_plan_id: Mapped[str] = mapped_column(
        ForeignKey("capacity_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    task_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    hours_per_week: Mapped[float] = mapped_column(default=0.0, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[Optional[date]] = mapped_column(Date, index=True)
    allocation_type: Mapped[str] = mapped_column(String(20), default="project", nullable=False)  # project, meeting, ops, learning, other
    is_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    confirmed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    snapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_allocations_org_dates", "organization_id", "start_date", "end_date"),
        Index("ix_allocations_emp_dates", "employee_id", "start_date", "end_date"),
        Index("ix_allocations_proj_dates", "project_id", "start_date", "end_date"),
    )


class TimeOffEntry(Base, TimestampMixin):
    __tablename__ = "time_off_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    time_off_type: Mapped[str] = mapped_column(String(40), nullable=False)  # vacation, sick, personal, parental, bereavement, etc.
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, approved, rejected, cancelled
    start_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    end_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    start_time: Mapped[Optional[str]] = mapped_column(String(5))  # HH:MM
    end_time: Mapped[Optional[str]] = mapped_column(String(5))  # HH:MM
    is_all_day: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    days_count: Mapped[float] = mapped_column(default=0.0, nullable=False)
    hours_count: Mapped[float] = mapped_column(default=0.0, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_reason: Mapped[Optional[str]] = mapped_column(Text)
    is_half_day: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    half_day_period: Mapped[Optional[str]] = mapped_column(String(20))  # morning, afternoon
    recurring_rule: Mapped[Optional[str]] = mapped_column(String(500))
    recurrence_end: Mapped[Optional[date]] = mapped_column(Date)
    parent_entry_id: Mapped[Optional[str]] = mapped_column(ForeignKey("time_off_entries.id", ondelete="SET NULL"))

    __table_args__ = (
        Index("ix_time_off_emp_dates", "employee_id", "start_date", "end_date"),
        Index("ix_time_off_org_status", "organization_id", "status"),
    )


class OvertimeEntry(Base, TimestampMixin):
    __tablename__ = "overtime_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    rate_multiplier: Mapped[float] = mapped_column(default=1.5, nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_compensated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    compensation_type: Mapped[str] = mapped_column(String(20), default="pay", nullable=False)  # pay, time_off
    compensated_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    task_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )

    __table_args__ = (
        Index("ix_overtime_emp_date", "employee_id", "date"),
        Index("ix_overtime_org_status", "organization_id", "date"),
    )