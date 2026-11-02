"""Team models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Enum as SQLEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class TeamType(str):
    FUNCTIONAL = "functional"
    CROSS_FUNCTIONAL = "cross_functional"
    PROJECT = "project"
    AGILE = "agile"
    COMMUNITY = "community"
    COMMITTEE = "committee"


class TeamStatus(str):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"
    FORMING = "forming"


class Team(Base, TimestampMixin):
    __tablename__ = "teams"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    team_type: Mapped[str] = mapped_column(String(30), default=TeamType.FUNCTIONAL, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=TeamStatus.ACTIVE, nullable=False, index=True)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    lead_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    is_private: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_auto_assign: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_members: Mapped[Optional[int]] = mapped_column(Integer)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    teamtype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="teams")
    lead: Mapped[Optional["Employee"]] = relationship(
        back_populates="led_teams",
        foreign_keys="Team.lead_id"
    )
    parent: Mapped[Optional["Team"]] = relationship(
        back_populates="children", remote_side="Team.id"
    )
    children: Mapped[List["Team"]] = relationship(back_populates="parent")
    department: Mapped[Optional["Department"]] = relationship(back_populates="teams")
    project: Mapped[Optional["Project"]] = relationship(
        back_populates="teams",
        foreign_keys="Team.project_id"
    )
    members: Mapped[List["TeamMember"]] = relationship(back_populates="team", cascade="all, delete-orphan")
    employees: Mapped[List["Employee"]] = relationship(back_populates="team", foreign_keys="Employee.team_id")
    goals: Mapped[List["TeamGoal"]] = relationship(back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_teams_org_name"),
        Index("ix_teams_org_parent", "organization_id", "parent_id"),
        Index("ix_teams_org_status", "organization_id", "status"),
        Index("ix_teams_org_lead", "organization_id", "lead_id"),
        {"extend_existing": True},
    )


class TeamMember(Base, TimestampMixin):
    __tablename__ = "team_members"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(40), default="member", nullable=False)  # lead, co-lead, member, observer
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    left_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    role_description: Mapped[Optional[str]] = mapped_column(Text)
    permissions: Mapped[dict] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    team: Mapped["Team"] = relationship(back_populates="members")
    employee: Mapped["Employee"] = relationship(back_populates="team_memberships")

    __table_args__ = (
        UniqueConstraint("team_id", "employee_id", name="uq_team_members_team_emp"),
        Index("ix_team_members_emp_active", "employee_id", "is_active"),
        Index("ix_team_members_team_active", "team_id", "is_active"),
    )


class TeamGoal(Base, TimestampMixin):
    __tablename__ = "team_goals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    team_id: Mapped[str] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="planned", nullable=False)  # planned, active, on_track, at_risk, completed, cancelled
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    target_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    teamtype_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    team: Mapped["Team"] = relationship(back_populates="goals")
    owner: Mapped[Optional["Employee"]] = relationship()

    __table_args__ = (
        Index("ix_team_goals_team_status", "team_id", "status"),
        Index("ix_team_goals_org_status", "organization_id", "status"),
    )