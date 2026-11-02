"""Project models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Enum as SQLEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class ProjectStatus(str):
    PLANNING = "planning"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class ProjectPriority(str):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    URGENT = "urgent"


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default=ProjectStatus.PLANNING, nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default=ProjectPriority.MEDIUM, nullable=False, index=True)
    project_type: Mapped[str] = mapped_column(String(40), default="standard", nullable=False)  # standard, epic, program, initiative
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    manager_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    team_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    client_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    target_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    budget_amount: Mapped[Optional[float]] = mapped_column(default=0.0)
    spent_amount: Mapped[float] = mapped_column(default=0.0, nullable=False)
    revenue_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    revenue_amount: Mapped[Optional[float]] = mapped_column(default=0.0)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    tags_visibility: Mapped[str] = mapped_column(String(20), default="public", nullable=False)  # public, internal, private
    methodology: Mapped[str] = mapped_column(String(30), default="agile", nullable=False)  # agile, waterfall, hybrid
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    custom_fields: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    template_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="projects")
    parent: Mapped[Optional["Project"]] = relationship(
        back_populates="children",
        foreign_keys="Project.parent_id",
        remote_side="Project.id"
    )
    children: Mapped[List["Project"]] = relationship(back_populates="parent", foreign_keys="Project.parent_id")
    owner: Mapped[Optional["Employee"]] = relationship(back_populates="owned_projects", foreign_keys="Project.owner_id")
    manager: Mapped[Optional["Employee"]] = relationship(back_populates="managed_projects", foreign_keys="Project.manager_id")
    department: Mapped[Optional["Department"]] = relationship(back_populates="projects")
    team: Mapped[Optional["Team"]] = relationship(
        back_populates="project",
        foreign_keys="Project.team_id"
    )
    teams: Mapped[List["Team"]] = relationship(back_populates="project", foreign_keys="Team.project_id")
    client: Mapped[Optional["Customer"]] = relationship(back_populates="projects")
    template: Mapped[Optional["Project"]] = relationship(
        back_populates="templated_projects",
        foreign_keys="Project.template_id",
        remote_side="Project.id"
    )
    templated_projects: Mapped[List["Project"]] = relationship(back_populates="template", foreign_keys="Project.template_id")
    members: Mapped[List["ProjectMember"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    roadmap: Mapped[Optional["Roadmap"]] = relationship(back_populates="project", uselist=False, cascade="all, delete-orphan")
    epics: Mapped[List["Epic"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    milestones: Mapped[List["Milestone"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    sprints: Mapped[List["Sprint"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    timeline: Mapped[List["ProjectTimeline"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    tasks: Mapped[List["Task"]] = relationship(back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_projects_org_slug"),
        Index("ix_projects_org_status", "organization_id", "status"),
        Index("ix_projects_org_owner", "organization_id", "owner_id"),
        Index("ix_projects_org_manager", "organization_id", "manager_id"),
        Index("ix_projects_org_dates", "organization_id", "start_date", "target_date"),
    )


class ProjectMember(Base, TimestampMixin):
    __tablename__ = "project_members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(40), default="member", nullable=False)  # owner, manager, lead, member, viewer
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    allocation_percentage: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    can_manage_project: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_manage_members: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_view_financials: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="members")
    employee: Mapped["Employee"] = relationship(back_populates="project_memberships")

    __table_args__ = (
        UniqueConstraint("project_id", "employee_id", name="uq_project_members_proj_emp"),
        Index("ix_project_members_emp_active", "employee_id", "is_active"),
        Index("ix_project_members_proj_active", "project_id", "is_active"),
    )


class Epic(Base, TimestampMixin):
    __tablename__ = "epics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False)  # planned, active, on_track, at_risk, completed, cancelled
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    target_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    projectstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="epics")
    owner: Mapped[Optional["Employee"]] = relationship()
    milestones: Mapped[List["Milestone"]] = relationship(back_populates="epic")
    tasks: Mapped[List["Task"]] = relationship(back_populates="epic")

    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_epics_proj_slug"),
        Index("ix_epics_proj_status", "project_id", "status"),
    )


class Milestone(Base, TimestampMixin):
    __tablename__ = "milestones"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    epic_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("epics.id", ondelete="SET NULL"), index=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False)  # planned, at_risk, completed
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_gate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gate_criteria: Mapped[Optional[str]] = mapped_column(Text)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    projectstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="milestones")
    epic: Mapped[Optional["Epic"]] = relationship(back_populates="milestones")

    __table_args__ = (
        Index("ix_milestones_proj_due", "project_id", "due_date"),
        Index("ix_milestones_epic_status", "epic_id", "status"),
    )


class Sprint(Base, TimestampMixin):
    __tablename__ = "sprints"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(Text)
    sprint_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False)  # planned, active, completed, cancelled
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    capacity_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    committed_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    completed_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    velocity: Mapped[float] = mapped_column(default=0.0, nullable=False)
    retrospective: Mapped[Optional[str]] = mapped_column(Text)
    projectstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="sprints")
    tasks: Mapped[List["Task"]] = relationship(back_populates="sprint")

    __table_args__ = (
        UniqueConstraint("project_id", "sprint_number", name="uq_sprints_proj_number"),
        Index("ix_sprints_proj_dates", "project_id", "start_date", "end_date"),
    )


class ProjectTimeline(Base, TimestampMixin):
    """Project timeline events."""

    __tablename__ = "project_timeline"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # created, status_change, milestone, member_change, etc.
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    event_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    actor_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    old_value: Mapped[Optional[str]] = mapped_column(Text)
    new_value: Mapped[Optional[str]] = mapped_column(Text)
    projectstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="timeline")
    actor: Mapped[Optional["Employee"]] = relationship()

    __table_args__ = (
        Index("ix_project_timeline_proj_date", "project_id", "event_date"),
    )


class Roadmap(Base, TimestampMixin):
    """Project roadmap with initiatives and timeline."""

    __tablename__ = "roadmaps"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    time_horizon: Mapped[str] = mapped_column(String(20), default="quarter", nullable=False)  # quarter, half, year
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    visibility: Mapped[str] = mapped_column(String(20), default="internal", nullable=False)  # public, internal, private
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    projectstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="roadmap", uselist=False)
    items: Mapped[List["RoadmapItem"]] = relationship(back_populates="roadmap", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_roadmaps_org_dates", "organization_id", "start_date", "end_date"),
    )


class RoadmapItem(Base, TimestampMixin):
    __tablename__ = "roadmap_items"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    roadmap_id: Mapped[str] = mapped_column(
        ForeignKey("roadmaps.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    item_type: Mapped[str] = mapped_column(String(40), nullable=False)  # initiative, feature, improvement, bug_fix, debt
    status: Mapped[str] = mapped_column(String(24), default="proposed", nullable=False)  # proposed, planned, in_progress, done
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_quarter: Mapped[Optional[str]] = mapped_column(String(10))  # YYYY-Q
    end_quarter: Mapped[Optional[str]] = mapped_column(String(10))
    estimated_effort: Mapped[Optional[float]] = mapped_column(default=None)
    theme: Mapped[Optional[str]] = mapped_column(String(100))
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    dependencies: Mapped[List[str]] = mapped_column(JSON, default=list)  # other roadmap item IDs
    projectstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    roadmap: Mapped["Roadmap"] = relationship(back_populates="items")
    epic_id: Mapped[Optional[str]] = mapped_column(ForeignKey("epics.id", ondelete="SET NULL"), index=True)
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="SET NULL"), index=True)

    __table_args__ = (
        Index("ix_roadmap_items_roadmap_quarter", "roadmap_id", "start_quarter"),
    )