"""Employee models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Enum as SQLEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class EmploymentType(str):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACTOR = "contractor"
    INTERN = "intern"
    TEMPORARY = "temporary"


class EmploymentStatus(str):
    ACTIVE = "active"
    ON_LEAVE = "on_leave"
    TERMINATED = "terminated"
    ONBOARDING = "onboarding"
    OFFBOARDING = "offboarding"


class Employee(Base, TimestampMixin):
    __tablename__ = "employees"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), unique=True, index=True
    )
    employee_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    first_name: Mapped[str] = mapped_column(String(100), nullable=False)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False)
    display_name: Mapped[Optional[str]] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    personal_email: Mapped[Optional[str]] = mapped_column(String(320))
    phone: Mapped[Optional[str]] = mapped_column(String(30))
    mobile: Mapped[Optional[str]] = mapped_column(String(30))
    avatar_url: Mapped[Optional[str]] = mapped_column(String(500))
    date_of_birth: Mapped[Optional[date]] = mapped_column(Date)
    hire_date: Mapped[Optional[date]] = mapped_column(Date)
    termination_date: Mapped[Optional[date]] = mapped_column(Date)
    employment_type: Mapped[str] = mapped_column(
        String(20), default=EmploymentType.FULL_TIME, nullable=False
    )
    employment_status: Mapped[str] = mapped_column(
        String(20), default=EmploymentStatus.ACTIVE, nullable=False, index=True
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    team_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    manager_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    location_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), index=True
    )
    job_title: Mapped[Optional[str]] = mapped_column(String(200))
    job_level: Mapped[Optional[str]] = mapped_column(String(50))
    job_family: Mapped[Optional[str]] = mapped_column(String(100))
    cost_center: Mapped[Optional[str]] = mapped_column(String(50))
    salary_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    salary_amount: Mapped[Optional[float]] = mapped_column(default=0.0)
    pay_frequency: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    reports_to: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    emergency_contact_name: Mapped[Optional[str]] = mapped_column(String(200))
    emergency_contact_phone: Mapped[Optional[str]] = mapped_column(String(30))
    emergency_contact_relationship: Mapped[Optional[str]] = mapped_column(String(50))
    address_line1: Mapped[Optional[str]] = mapped_column(String(200))
    address_line2: Mapped[Optional[str]] = mapped_column(String(200))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    nationality: Mapped[Optional[str]] = mapped_column(String(100))
    work_permit_expiry: Mapped[Optional[date]] = mapped_column(Date)
    visa_type: Mapped[Optional[str]] = mapped_column(String(50))
    bank_account_details: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    tax_information: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    benefits_enrollment: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    custom_fields: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    terminated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    terminated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    termination_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="employees")
    user: Mapped[Optional["User"]] = relationship(back_populates="employee", foreign_keys="Employee.user_id")
    department: Mapped[Optional["Department"]] = relationship(back_populates="employees", foreign_keys="Employee.department_id")
    team: Mapped[Optional["Team"]] = relationship(back_populates="employees", foreign_keys="Employee.team_id")
    manager: Mapped[Optional["Employee"]] = relationship(
        back_populates="direct_reports",
        foreign_keys="Employee.manager_id",
        remote_side="Employee.id"
    )
    direct_reports: Mapped[List["Employee"]] = relationship(
        back_populates="manager",
        foreign_keys="Employee.reports_to",
        remote_side="Employee.reports_to"
    )
    location: Mapped[Optional["Location"]] = relationship(back_populates="employees")
    skills: Mapped[List["EmployeeSkill"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    certifications: Mapped[List["EmployeeCertification"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    achievements: Mapped[List["EmployeeAchievement"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    timeline: Mapped[List["EmployeeTimeline"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    availability: Mapped[List["EmployeeAvailability"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    presence: Mapped[List["EmployeePresence"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    favorites: Mapped[List["EmployeeFavorite"]] = relationship(back_populates="employee", cascade="all, delete-orphan")
    owned_projects: Mapped[List["Project"]] = relationship(back_populates="owner", foreign_keys="Project.owner_id")
    managed_projects: Mapped[List["Project"]] = relationship(back_populates="manager", foreign_keys="Project.manager_id")
    project_memberships: Mapped[List["ProjectMember"]] = relationship(back_populates="employee", foreign_keys="ProjectMember.employee_id")
    assigned_tasks: Mapped[List["Task"]] = relationship(back_populates="assignee", foreign_keys="Task.assignee_id")
    reported_tasks: Mapped[List["Task"]] = relationship(back_populates="reporter", foreign_keys="Task.reporter_id")
    owned_goals: Mapped[List["Goal"]] = relationship(back_populates="owner", foreign_keys="Goal.owner_id")
    created_events: Mapped[List["CalendarEvent"]] = relationship(back_populates="creator", foreign_keys="CalendarEvent.creator_id")
    led_teams: Mapped[List["Team"]] = relationship(back_populates="lead", foreign_keys="Team.lead_id")
    managed_departments: Mapped[List["Department"]] = relationship(back_populates="manager", foreign_keys="Department.manager_id")
    team_memberships: Mapped[List["TeamMember"]] = relationship(back_populates="employee", foreign_keys="TeamMember.employee_id")
    learning_profile: Mapped[Optional["LearningProfile"]] = relationship(back_populates="employee", foreign_keys="LearningProfile.employee_id", uselist=False)
    owned_calendars: Mapped[List["Calendar"]] = relationship(back_populates="owner", foreign_keys="Calendar.owner_id")
    owned_risks: Mapped[List["Risk"]] = relationship(back_populates="owner", foreign_keys="Risk.owner_id")

    __table_args__ = (
        Index("ix_employees_org_status", "organization_id", "employment_status"),
        Index("ix_employees_org_dept", "organization_id", "department_id"),
        Index("ix_employees_org_team", "organization_id", "team_id"),
        Index("ix_employees_org_manager", "organization_id", "manager_id"),
        UniqueConstraint("organization_id", "employee_id", name="uq_employees_org_employee_id"),
        UniqueConstraint("organization_id", "email", name="uq_employees_org_email"),
    )


class EmployeeSkill(Base, TimestampMixin):
    __tablename__ = "employee_skills"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    proficiency_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    years_experience: Mapped[float] = mapped_column(default=0.0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20), default="self", nullable=False)  # self, manager, peer, system
    last_assessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    employmenttype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    employee: Mapped["Employee"] = relationship(back_populates="skills")
    skill: Mapped["Skill"] = relationship(back_populates="employee_skills")

    __table_args__ = (
        UniqueConstraint("employee_id", "skill_id", name="uq_employee_skills_emp_skill"),
        Index("ix_employee_skills_emp_prof", "employee_id", "proficiency_level"),
    )


class EmployeeCertification(Base, TimestampMixin):
    __tablename__ = "employee_certifications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    issuer: Mapped[str] = mapped_column(String(200), nullable=False)
    credential_id: Mapped[Optional[str]] = mapped_column(String(100))
    credential_url: Mapped[Optional[str]] = mapped_column(String(500))
    issued_date: Mapped[date] = mapped_column(Date, nullable=False)
    expires_at: Mapped[Optional[date]] = mapped_column(Date, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    credential_data: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    employee: Mapped["Employee"] = relationship(back_populates="certifications")

    __table_args__ = (
        Index("ix_emp_certs_emp_expires", "employee_id", "expires_at"),
    )


class EmployeeAchievement(Base, TimestampMixin):
    __tablename__ = "employee_achievements"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    achievement_type: Mapped[str] = mapped_column(String(40), nullable=False)  # award, milestone, recognition, completion
    category: Mapped[Optional[str]] = mapped_column(String(50))
    awarded_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    awarded_at: Mapped[date] = mapped_column(Date, nullable=False)
    badge_url: Mapped[Optional[str]] = mapped_column(String(500))
    points: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    employmenttype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    employee: Mapped["Employee"] = relationship(back_populates="achievements")

    __table_args__ = (
        Index("ix_emp_achievements_emp_awarded", "employee_id", "awarded_at"),
    )


class EmployeeTimeline(Base, TimestampMixin):
    """Employee lifecycle events and milestones."""

    __tablename__ = "employee_timeline"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # hire, promotion, transfer, leave, return, termination, etc.
    event_title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    effective_date: Mapped[Optional[date]] = mapped_column(Date)
    related_entity_type: Mapped[Optional[str]] = mapped_column(String(50))  # department, team, role, project
    related_entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    initiated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    approved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    is_milestone: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    employmenttype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    employee: Mapped["Employee"] = relationship(back_populates="timeline")

    __table_args__ = (
        Index("ix_emp_timeline_emp_date", "employee_id", "event_date"),
        Index("ix_emp_timeline_org_date", "organization_id", "event_date"),
    )


class EmployeeAvailability(Base, TimestampMixin):
    __tablename__ = "employee_availability"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)  # 0=Monday, 6=Sunday
    start_time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    end_time: Mapped[str] = mapped_column(String(5), nullable=False)  # HH:MM
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    availability_type: Mapped[str] = mapped_column(String(20), default="working", nullable=False)  # working, unavailable, preferred
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[Optional[date]] = mapped_column(Date)
    employmenttype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    employee: Mapped["Employee"] = relationship(back_populates="availability")

    __table_args__ = (
        Index("ix_emp_availability_emp_day", "employee_id", "day_of_week"),
    )


class EmployeePresence(Base, TimestampMixin):
    """Real-time presence tracking for employees."""

    __tablename__ = "employee_presence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="offline", nullable=False)  # online, away, busy, offline
    status_message: Mapped[Optional[str]] = mapped_column(String(300))
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    device_info: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45))
    location: Mapped[Optional[str]] = mapped_column(String(200))
    is_auto_away: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idle_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    employee: Mapped["Employee"] = relationship(back_populates="presence")

    __table_args__ = (
        Index("ix_emp_presence_emp_status", "employee_id", "status"),
        Index("ix_emp_presence_org_status", "organization_id", "status"),
    )


class EmployeeFavorite(Base, TimestampMixin):
    __tablename__ = "employee_favorites"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    favorite_type: Mapped[str] = mapped_column(String(40), nullable=False)  # employee, document, project, team, etc.
    favorite_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String(300))
    employmenttype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    employee: Mapped["Employee"] = relationship(back_populates="favorites")

    __table_args__ = (
        UniqueConstraint("employee_id", "favorite_type", "favorite_id", name="uq_emp_favorites_emp_type_id"),
        Index("ix_emp_favorites_emp_type", "employee_id", "favorite_type"),
    )