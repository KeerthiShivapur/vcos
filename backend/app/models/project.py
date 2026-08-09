"""Projects, roadmaps, epics, milestones, sprints (Phase 3 — Work Execution)."""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    Date,
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


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_project_code_org"),
        Index("ix_projects_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="draft")  # draft|active|paused|completed|archived
    priority: Mapped[str] = mapped_column(String(20), default="medium")  # low|medium|high|critical
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    health: Mapped[str] = mapped_column(String(20), default="healthy")  # healthy|at_risk|critical
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    department_id: Mapped[Optional[str]] = mapped_column(ForeignKey("departments.id", ondelete="SET NULL"))
    team_id: Mapped[Optional[str]] = mapped_column(ForeignKey("teams.id", ondelete="SET NULL"))
    roadmap_id: Mapped[Optional[str]] = mapped_column(ForeignKey("roadmaps.id", ondelete="SET NULL"))
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    budget: Mapped[Optional[float]] = mapped_column()  # numeric, sqlalchemy Float
    tags: Mapped[Optional[list]] = mapped_column(JSON)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Roadmap(Base, TimestampMixin):
    __tablename__ = "roadmaps"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_roadmap_name_org"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    timeframe: Mapped[str] = mapped_column(String(30), default="quarter")  # quarter|half|year
    status: Mapped[str] = mapped_column(String(30), default="draft")  # draft|active|completed|archived
    progress: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Epic(Base, TimestampMixin):
    __tablename__ = "epics"
    __table_args__ = (Index("ix_epics_org_project", "organization_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    roadmap_id: Mapped[Optional[str]] = mapped_column(ForeignKey("roadmaps.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="planned")  # planned|in_progress|completed
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    progress: Mapped[int] = mapped_column(Integer, default=0)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Milestone(Base, TimestampMixin):
    __tablename__ = "milestones"
    __table_args__ = (Index("ix_milestones_org_project", "organization_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    roadmap_id: Mapped[Optional[str]] = mapped_column(ForeignKey("roadmaps.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="pending")  # pending|in_progress|completed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class Sprint(Base, TimestampMixin):
    __tablename__ = "sprints"
    __table_args__ = (Index("ix_sprints_org_project", "organization_id", "project_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(Text)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="planned")  # planned|active|completed
    progress: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "employee_id", name="uq_project_member"),
        Index("ix_project_members_org", "organization_id", "employee_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[Optional[str]] = mapped_column(String(120))
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ProjectTimeline(Base):
    __tablename__ = "project_timelines"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    occurred_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
