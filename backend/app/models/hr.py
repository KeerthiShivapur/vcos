"""HR & Workforce Operations models (Phase 11).

Covers the full employee lifecycle inside VCOS: attendance, shifts,
holidays, leave, recruitment (jobs/candidates/interviews/offers),
performance (cycles/goals/reviews), assets, offboarding, compliance,
payroll integration references, workforce planning, succession,
wellbeing and alumni — all tenant-scoped and auditable.
"""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


# ------------------------------------------------------------------ attendance

class Shift(Base, TimestampMixin):
    __tablename__ = "shifts"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_shift_name_org"),
        Index("ix_shifts_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_time: Mapped[str] = mapped_column(String(8), default="09:00")
    end_time: Mapped[str] = mapped_column(String(8), default="17:00")
    work_hours: Mapped[float] = mapped_column(Float, default=8.0)
    break_minutes: Mapped[int] = mapped_column(Integer, default=60)
    # days of week the shift applies to: [0..6] (Monday..Sunday)
    days: Mapped[Optional[list[int]]] = mapped_column(JSON, default=list)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    is_flexible: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Holiday(Base, TimestampMixin):
    __tablename__ = "holidays"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", "date", name="uq_holiday_name_date"),
        Index("ix_holidays_org_date", "organization_id", "date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    # public | company | regional
    kind: Mapped[str] = mapped_column(String(20), default="public")
    optional: Mapped[bool] = mapped_column(Boolean, default=False)


class AttendanceRecord(Base, TimestampMixin):
    __tablename__ = "attendance_records"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", "date", name="uq_attendance_emp_date"),
        Index("ix_attendance_org_date", "organization_id", "date"),
        Index("ix_attendance_emp", "organization_id", "employee_id", "date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    shift_id: Mapped[Optional[str]] = mapped_column(ForeignKey("shifts.id", ondelete="SET NULL"))
    # office | remote | hybrid | field | shift | flexible
    work_mode: Mapped[str] = mapped_column(String(20), default="office")
    check_in: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    check_out: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    breaks: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    # [{start, end, minutes}]
    # present | absent | half_day | work_from_home | on_leave | holiday
    status: Mapped[str] = mapped_column(String(20), default="present")
    work_minutes: Mapped[int] = mapped_column(Integer, default=0)
    overtime_minutes: Mapped[int] = mapped_column(Integer, default=0)
    late_minutes: Mapped[int] = mapped_column(Integer, default=0)
    early_departure_minutes: Mapped[int] = mapped_column(Integer, default=0)
    location: Mapped[Optional[str]] = mapped_column(String(255))
    # manual | app | qr | biometric | gps | wifi
    source: Mapped[str] = mapped_column(String(20), default="manual")
    note: Mapped[Optional[str]] = mapped_column(Text)
    verified_by: Mapped[Optional[str]] = mapped_column(String(32))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)


class AttendanceCorrection(Base, TimestampMixin):
    __tablename__ = "attendance_corrections"
    __table_args__ = (
        Index("ix_att_corrections_emp", "organization_id", "employee_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    attendance_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("attendance_records.id", ondelete="SET NULL")
    )
    requested_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String(20), default="pending")
    adjusted_check_in: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    adjusted_check_out: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(32))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------------ leave

class LeaveType(Base, TimestampMixin):
    __tablename__ = "leave_types"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_leave_type_code_org"),
        Index("ix_leave_types_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    color: Mapped[str] = mapped_column(String(20), default="#6366f1")
    days_per_year: Mapped[float] = mapped_column(Float, default=15.0)
    carry_over: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, default=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class LeaveBalance(Base, TimestampMixin):
    __tablename__ = "leave_balances"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "employee_id", "leave_type_id", "year", name="uq_leave_balance_emp_year"
        ),
        Index("ix_leave_balances_emp", "organization_id", "employee_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    leave_type_id: Mapped[str] = mapped_column(
        ForeignKey("leave_types.id", ondelete="CASCADE"), nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    allocated: Mapped[float] = mapped_column(Float, default=0.0)
    used: Mapped[float] = mapped_column(Float, default=0.0)
    carried_over: Mapped[float] = mapped_column(Float, default=0.0)

    @property
    def remaining(self) -> float:
        return max(0.0, self.allocated + self.carried_over - self.used)


class LeaveRequest(Base, TimestampMixin):
    __tablename__ = "leave_requests"
    __table_args__ = (
        Index("ix_leave_requests_emp", "organization_id", "employee_id", "status"),
        Index("ix_leave_requests_dates", "organization_id", "start_date", "end_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    leave_type_id: Mapped[str] = mapped_column(
        ForeignKey("leave_types.id", ondelete="CASCADE"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[float] = mapped_column(Float, default=1.0)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    # pending | approved | rejected | cancelled
    status: Mapped[str] = mapped_column(String(20), default="pending")
    approved_by: Mapped[Optional[str]] = mapped_column(String(32))
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    backup_employee_id: Mapped[Optional[str]] = mapped_column(String(32))
    half_day: Mapped[bool] = mapped_column(Boolean, default=False)
    reviewer_note: Mapped[Optional[str]] = mapped_column(Text)


# ------------------------------------------------------------------ recruitment

class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (
        Index("ix_jobs_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(150), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100))
    location: Mapped[Optional[str]] = mapped_column(String(150))
    employment_type: Mapped[str] = mapped_column(String(30), default="full_time")
    description: Mapped[Optional[str]] = mapped_column(Text)
    requirements: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    skills: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    salary_range: Mapped[Optional[str]] = mapped_column(String(100))
    openings: Mapped[int] = mapped_column(Integer, default=1)
    # draft | open | paused | closed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[Optional[str]] = mapped_column(String(32))


class Candidate(Base, TimestampMixin):
    __tablename__ = "candidates"
    __table_args__ = (
        Index("ix_candidates_job", "organization_id", "job_id", "stage"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(320))
    phone: Mapped[Optional[str]] = mapped_column(String(60))
    resume_url: Mapped[Optional[str]] = mapped_column(String(500))
    source: Mapped[str] = mapped_column(String(50), default="website")
    # applied | screening | interview | offer | hired | rejected | withdrawn
    stage: Mapped[str] = mapped_column(String(20), default="applied")
    skills: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    experience_years: Mapped[float] = mapped_column(Float, default=0.0)
    current_company: Mapped[Optional[str]] = mapped_column(String(150))
    current_title: Mapped[Optional[str]] = mapped_column(String(150))
    match_score: Mapped[float] = mapped_column(Float, default=0.0)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Interview(Base, TimestampMixin):
    __tablename__ = "interviews"
    __table_args__ = (
        Index("ix_interviews_candidate", "organization_id", "candidate_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scheduled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=45)
    panel: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    # video | onsite | phone
    mode: Mapped[str] = mapped_column(String(20), default="video")
    # scheduled | completed | cancelled
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    feedback: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[Optional[str]] = mapped_column(Text)


class Offer(Base, TimestampMixin):
    __tablename__ = "offers"
    __table_args__ = (
        Index("ix_offers_candidate", "organization_id", "candidate_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    job_id: Mapped[str] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    candidate_id: Mapped[str] = mapped_column(
        ForeignKey("candidates.id", ondelete="CASCADE"), index=True, nullable=False
    )
    salary: Mapped[Optional[str]] = mapped_column(String(100))
    equity: Mapped[Optional[str]] = mapped_column(String(100))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    expires_at: Mapped[Optional[date]] = mapped_column(Date)
    # draft | sent | accepted | declined | withdrawn
    status: Mapped[str] = mapped_column(String(20), default="draft")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    signed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------------ performance

class PerformanceCycle(Base, TimestampMixin):
    __tablename__ = "performance_cycles"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_perf_cycle_name_org"),
        Index("ix_perf_cycles_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # {start, end} ISO dates
    period: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    # draft | open | reviewing | closed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    created_by: Mapped[Optional[str]] = mapped_column(String(32))
    description: Mapped[Optional[str]] = mapped_column(Text)


class PerformanceGoal(Base, TimestampMixin):
    __tablename__ = "performance_goals"
    __table_args__ = (
        Index("ix_perf_goals_emp", "organization_id", "employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    cycle_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("performance_cycles.id", ondelete="SET NULL")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    # project | learning | behavior | leadership
    kind: Mapped[str] = mapped_column(String(30), default="project")
    status: Mapped[str] = mapped_column(String(20), default="active")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    due_date: Mapped[Optional[date]] = mapped_column(Date)


class PerformanceReview(Base, TimestampMixin):
    __tablename__ = "performance_reviews"
    __table_args__ = (
        Index("ix_perf_reviews_emp", "organization_id", "employee_id", "status"),
        Index("ix_perf_reviews_cycle", "organization_id", "cycle_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    cycle_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("performance_cycles.id", ondelete="SET NULL")
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reviewer_id: Mapped[Optional[str]] = mapped_column(String(32))
    # self | manager | peer | 360
    kind: Mapped[str] = mapped_column(String(20), default="self")
    # draft | submitted | completed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    rating: Mapped[float] = mapped_column(Float, default=0.0)
    goals: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    strengths: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    improvements: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    learning_plan: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------------ assets

class EmployeeAsset(Base, TimestampMixin):
    __tablename__ = "employee_assets"
    __table_args__ = (
        Index("ix_assets_emp", "organization_id", "employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # laptop | phone | monitor | software | license | access_card | vehicle | other
    category: Mapped[str] = mapped_column(String(30), default="other")
    serial_number: Mapped[Optional[str]] = mapped_column(String(150))
    purchase_date: Mapped[Optional[date]] = mapped_column(Date)
    warranty_until: Mapped[Optional[date]] = mapped_column(Date)
    assigned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    returned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # available | assigned | returned | lost | maintenance
    status: Mapped[str] = mapped_column(String(20), default="available")
    condition: Mapped[Optional[str]] = mapped_column(String(50))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    assigned_by: Mapped[Optional[str]] = mapped_column(String(32))


# ------------------------------------------------------------------ offboarding

class Offboarding(Base, TimestampMixin):
    __tablename__ = "offboardings"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", name="uq_offboarding_employee"),
        Index("ix_offboardings_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    reason: Mapped[Optional[str]] = mapped_column(Text)
    resignation_date: Mapped[Optional[date]] = mapped_column(Date)
    exit_date: Mapped[Optional[date]] = mapped_column(Date)
    # requested | approved | in_progress | completed
    status: Mapped[str] = mapped_column(String(20), default="requested")
    initiated_by: Mapped[Optional[str]] = mapped_column(String(32))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    knowledge_transfer: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, default=list)
    # [{title, owner, status}]
    exit_interview: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    # {feedback, reason, completed, notes}
    transitions_to_alumni: Mapped[bool] = mapped_column(Boolean, default=True)
    employee: Mapped[Optional["Employee"]] = relationship(  # noqa: F821
        foreign_keys=[employee_id]
    )


class OffboardingTask(Base, TimestampMixin):
    __tablename__ = "offboarding_tasks"
    __table_args__ = (
        Index("ix_offboarding_tasks_plan", "organization_id", "offboarding_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    offboarding_id: Mapped[str] = mapped_column(
        ForeignKey("offboardings.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # knowledge | asset | access | finance | document | exit
    category: Mapped[str] = mapped_column(String(20), default="knowledge")
    status: Mapped[str] = mapped_column(String(20), default="pending")
    completed_by: Mapped[Optional[str]] = mapped_column(String(32))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    notes: Mapped[Optional[str]] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)


# ------------------------------------------------------------------ compliance

class ComplianceRecord(Base, TimestampMixin):
    __tablename__ = "compliance_records"
    __table_args__ = (
        Index("ix_compliance_emp", "organization_id", "employee_id", "status"),
        Index("ix_compliance_expiry", "organization_id", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True
    )
    # contract | visa | identity | certification | policy_acknowledgement
    document_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # valid | expiring | expired | missing
    status: Mapped[str] = mapped_column(String(20), default="valid")
    reference: Mapped[Optional[str]] = mapped_column(String(255))
    issued_at: Mapped[Optional[date]] = mapped_column(Date)
    expires_at: Mapped[Optional[date]] = mapped_column(Date)
    last_reviewed_at: Mapped[Optional[date]] = mapped_column(Date)
    reviewed_by: Mapped[Optional[str]] = mapped_column(String(32))
    notes: Mapped[Optional[str]] = mapped_column(Text)


class TrainingRequirement(Base, TimestampMixin):
    __tablename__ = "training_requirements"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_training_req_name_org"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # security | policy | safety | compliance
    category: Mapped[str] = mapped_column(String(30), default="compliance")
    required_for: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    frequency_days: Mapped[int] = mapped_column(Integer, default=365)
    description: Mapped[Optional[str]] = mapped_column(Text)


class TrainingCompletion(Base, TimestampMixin):
    __tablename__ = "training_completions"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "employee_id", "requirement_id", name="uq_training_completion"
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    requirement_id: Mapped[str] = mapped_column(
        ForeignKey("training_requirements.id", ondelete="CASCADE"), nullable=False
    )
    completed_at: Mapped[Optional[date]] = mapped_column(Date)
    expires_at: Mapped[Optional[date]] = mapped_column(Date)
    provider: Mapped[Optional[str]] = mapped_column(String(150))
    certificate_ref: Mapped[Optional[str]] = mapped_column(String(255))


# ------------------------------------------------------------------ payroll integration

class PayrollProvider(Base, TimestampMixin):
    __tablename__ = "payroll_providers"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_payroll_provider_name"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    # sap | oracle | workday | adp | gusto | local | custom
    provider: Mapped[str] = mapped_column(String(30), default="custom")
    config: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class PayrollRun(Base, TimestampMixin):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        Index("ix_payroll_runs_org", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    provider_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("payroll_providers.id", ondelete="SET NULL")
    )
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)
    # synced | failed | pending
    status: Mapped[str] = mapped_column(String(20), default="pending")
    employee_count: Mapped[int] = mapped_column(Integer, default=0)
    gross_amount: Mapped[float] = mapped_column(Float, default=0.0)
    reference_id: Mapped[Optional[str]] = mapped_column(String(255))
    payload: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


# ------------------------------------------------------------------ workforce & succession

class WorkforcePlan(Base, TimestampMixin):
    __tablename__ = "workforce_plans"
    __table_args__ = (
        Index("ix_workforce_plans_org", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    horizon: Mapped[str] = mapped_column(String(30), default="quarter")
    department: Mapped[Optional[str]] = mapped_column(String(100))
    headcount_target: Mapped[int] = mapped_column(Integer, default=0)
    skill_needs: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    budget: Mapped[float] = mapped_column(Float, default=0.0)
    # draft | approved | active | completed
    status: Mapped[str] = mapped_column(String(20), default="draft")
    notes: Mapped[Optional[str]] = mapped_column(Text)
    created_by: Mapped[Optional[str]] = mapped_column(String(32))


class SuccessionCandidate(Base, TimestampMixin):
    __tablename__ = "succession_candidates"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "position_title", "candidate_employee_id", name="uq_succession_candidate"
        ),
        Index("ix_succession_pos", "organization_id", "position_title"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    position_title: Mapped[str] = mapped_column(String(150), nullable=False)
    employee_id: Mapped[Optional[str]] = mapped_column(String(32))
    candidate_employee_id: Mapped[str] = mapped_column(String(32), nullable=False)
    readiness: Mapped[int] = mapped_column(Integer, default=0)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    # identified | developing | ready
    status: Mapped[str] = mapped_column(String(20), default="identified")
    last_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class WorkforceSnapshot(Base, TimestampMixin):
    __tablename__ = "workforce_snapshots"
    __table_args__ = (
        UniqueConstraint("organization_id", "date", name="uq_workforce_snapshot_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    headcount: Mapped[int] = mapped_column(Integer, default=0)
    hires_month: Mapped[int] = mapped_column(Integer, default=0)
    exits_month: Mapped[int] = mapped_column(Integer, default=0)
    attrition_rate: Mapped[float] = mapped_column(Float, default=0.0)
    departments: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # {dept: {count, open_roles}}


# ------------------------------------------------------------------ wellbeing & alumni

class WellbeingCheck(Base, TimestampMixin):
    __tablename__ = "wellbeing_checks"
    __table_args__ = (
        Index("ix_wellbeing_emp", "organization_id", "employee_id", "risk_level"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    check_date: Mapped[date] = mapped_column(Date, nullable=False)
    # {meeting_hours, task_load, learning_load, leave_balance_days, recognitions, engagement}
    metrics: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    # low | medium | high
    risk_level: Mapped[str] = mapped_column(String(20), default="low")
    signals: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)


class AlumniProfile(Base, TimestampMixin):
    __tablename__ = "alumni_profiles"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", name="uq_alumni_employee"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    left_at: Mapped[Optional[date]] = mapped_column(Date)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    # alumni | boomerang | contact
    status: Mapped[str] = mapped_column(String(20), default="alumni")
    linkedin: Mapped[Optional[str]] = mapped_column(String(500))
    keep_in_touch: Mapped[bool] = mapped_column(Boolean, default=True)
    knowledge_contributions: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    last_activity: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
