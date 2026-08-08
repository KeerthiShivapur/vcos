"""Employees — the living digital identity of an organization (Phase 2)."""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
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


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_number", name="uq_employee_number_org"),
        UniqueConstraint("organization_id", "user_id", name="uq_employee_user_org"),
        UniqueConstraint("organization_id", "email", name="uq_employee_email_org"),
        Index("ix_employees_org_status", "organization_id", "status"),
        Index("ix_employees_dept", "organization_id", "department_id"),
        Index("ix_employees_team", "organization_id", "team_id"),
        Index("ix_employees_manager", "organization_id", "manager_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    employee_number: Mapped[str] = mapped_column(String(40), nullable=False)

    # Identity
    first_name: Mapped[str] = mapped_column(String(150), nullable=False)
    last_name: Mapped[Optional[str]] = mapped_column(String(150))
    display_name: Mapped[Optional[str]] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    phone: Mapped[Optional[str]] = mapped_column(String(60))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Position
    designation: Mapped[Optional[str]] = mapped_column(String(150))
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    manager_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    location_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    business_unit_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("business_units.id", ondelete="SET NULL")
    )

    employment_type: Mapped[str] = mapped_column(String(30), default="full_time")
    joining_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    timezone: Mapped[str] = mapped_column(String(80), default="UTC")
    language: Mapped[Optional[str]] = mapped_column(String(10), default="en")
    bio: Mapped[Optional[str]] = mapped_column(Text)
    emergency_contact: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)

    # Derived intelligence (updated by the expertise engine)
    expertise_score: Mapped[float] = mapped_column(Float, default=0.0)
    profile_completion: Mapped[int] = mapped_column(Integer, default=0)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped[Optional["User"]] = relationship(  # noqa: F821
        back_populates="employee", foreign_keys=[user_id]
    )
    department: Mapped[Optional["Department"]] = relationship(  # noqa: F821
        back_populates="employees", foreign_keys=[department_id]
    )
    team: Mapped[Optional["Team"]] = relationship(  # noqa: F821
        back_populates="members", foreign_keys=[team_id]
    )
    manager: Mapped[Optional["Employee"]] = relationship(
        remote_side="Employee.id", back_populates="direct_reports", foreign_keys=[manager_id]
    )
    direct_reports: Mapped[list["Employee"]] = relationship(
        back_populates="manager", foreign_keys=[manager_id]
    )
    location: Mapped[Optional["Location"]] = relationship(  # noqa: F821
        back_populates="employees", foreign_keys=[location_id]
    )
    skills: Mapped[list["EmployeeSkill"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan"
    )
    certifications: Mapped[list["EmployeeCertification"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan"
    )
    achievements: Mapped[list["EmployeeAchievement"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan"
    )
    timeline: Mapped[list["EmployeeTimeline"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan"
    )
    availability: Mapped[Optional["EmployeeAvailability"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan", uselist=False
    )
    presence: Mapped[Optional["EmployeePresence"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan", uselist=False
    )
    expertise_scores: Mapped[list["ExpertiseScore"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan"
    )
    learning_profile: Mapped[Optional["LearningProfile"]] = relationship(  # noqa: F821
        back_populates="employee", cascade="all, delete-orphan", uselist=False,
        foreign_keys="LearningProfile.employee_id",
    )
    headed_departments: Mapped[list["Department"]] = relationship(  # noqa: F821
        back_populates="head", foreign_keys="Department.head_id"
    )
    led_teams: Mapped[list["Team"]] = relationship(  # noqa: F821
        back_populates="lead", foreign_keys="Team.lead_id"
    )

    @property
    def full_name(self) -> str:
        return self.display_name or (
            f"{self.first_name} {self.last_name}".strip() if self.last_name else self.first_name
        )


class EmployeeSkill(Base, TimestampMixin):
    __tablename__ = "employee_skills"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", "skill_id", name="uq_emp_skill"),
        Index("ix_employee_skills_org_skill", "organization_id", "skill_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    level: Mapped[int] = mapped_column(Integer, default=2)  # 1..5
    years_experience: Mapped[float] = mapped_column(Float, default=0.0)
    verified: Mapped[bool] = mapped_column(default=False)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    employee: Mapped["Employee"] = relationship(back_populates="skills")  # noqa: F821
    skill: Mapped["Skill"] = relationship(back_populates="employees")  # noqa: F821


class EmployeeCertification(Base, TimestampMixin):
    __tablename__ = "employee_certifications"
    __table_args__ = (
        Index("ix_emp_certs", "organization_id", "employee_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[Optional[str]] = mapped_column(String(255))
    credential_id: Mapped[Optional[str]] = mapped_column(String(255))
    issue_date: Mapped[Optional[date]] = mapped_column(Date)
    expiry_date: Mapped[Optional[date]] = mapped_column(Date)
    verified: Mapped[bool] = mapped_column(default=False)

    employee: Mapped["Employee"] = relationship(back_populates="certifications")  # noqa: F821


class EmployeeAchievement(Base, TimestampMixin):
    __tablename__ = "employee_achievements"
    __table_args__ = (
        Index("ix_emp_achievements", "organization_id", "employee_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(30), default="recognition")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    achieved_on: Mapped[Optional[date]] = mapped_column(Date)

    employee: Mapped["Employee"] = relationship(back_populates="achievements")  # noqa: F821


class EmployeeTimeline(Base):
    __tablename__ = "employee_timelines"
    __table_args__ = (
        Index("ix_emp_timeline", "organization_id", "employee_id", "occurred_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    employee: Mapped["Employee"] = relationship(back_populates="timeline")  # noqa: F821


class EmployeeAvailability(Base, TimestampMixin):
    __tablename__ = "employee_availability"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", name="uq_emp_availability"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), default="available")
    note: Mapped[Optional[str]] = mapped_column(String(300))
    available_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    available_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    employee: Mapped["Employee"] = relationship(back_populates="availability")  # noqa: F821


class EmployeePresence(Base, TimestampMixin):
    __tablename__ = "employee_presence"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", name="uq_emp_presence"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    is_online: Mapped[bool] = mapped_column(default=False)
    status: Mapped[str] = mapped_column(String(20), default="offline")
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    working_hours: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    timezone: Mapped[Optional[str]] = mapped_column(String(80))
    device: Mapped[Optional[str]] = mapped_column(String(255))

    employee: Mapped["Employee"] = relationship(back_populates="presence")  # noqa: F821


class EmployeeFavorite(Base, TimestampMixin):
    __tablename__ = "employee_favorites"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", "target_employee_id", name="uq_favorite"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
