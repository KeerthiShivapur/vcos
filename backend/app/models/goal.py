"""Goal and Key Result models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class GoalStatus(str):
    DRAFT = "draft"
    ACTIVE = "active"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class GoalVisibility(str):
    PUBLIC = "public"
    INTERNAL = "internal"
    PRIVATE = "private"


class GoalType(str):
    STRATEGIC = "strategic"
    TACTICAL = "tactical"
    OPERATIONAL = "operational"
    PERSONAL = "personal"
    TEAM = "team"
    DEPARTMENT = "department"
    COMPANY = "company"


class Goal(Base, TimestampMixin):
    __tablename__ = "goals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=GoalStatus.DRAFT, nullable=False, index=True)
    visibility: Mapped[str] = mapped_column(String(20), default=GoalVisibility.INTERNAL, nullable=False)
    goal_type: Mapped[str] = mapped_column(String(20), default=GoalType.STRATEGIC, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    owner_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("goals.id", ondelete="SET NULL"), index=True
    )
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    team_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("teams.id", ondelete="SET NULL"), index=True
    )
    project_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    target_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    target_value: Mapped[Optional[float]] = mapped_column(default=None)
    current_value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    custom_fields: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    goalstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    organization: Mapped["Organization"] = relationship()
    owner: Mapped["Employee"] = relationship(back_populates="owned_goals")
    parent: Mapped[Optional["Goal"]] = relationship(
        back_populates="children", remote_side="Goal.id"
    )
    children: Mapped[List["Goal"]] = relationship(back_populates="parent")
    department: Mapped[Optional["Department"]] = relationship()
    team: Mapped[Optional["Team"]] = relationship()
    key_results: Mapped[List["KeyResult"]] = relationship(back_populates="goal", cascade="all, delete-orphan")
    updates: Mapped[List["GoalUpdate"]] = relationship(back_populates="goal", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_goals_org_status", "organization_id", "status"),
        Index("ix_goals_org_owner", "organization_id", "owner_id"),
        Index("ix_goals_org_type", "organization_id", "goal_type"),
        Index("ix_goals_org_dates", "organization_id", "start_date", "target_date"),
        Index("ix_goals_parent", "parent_id"),
    )


class KeyResult(Base, TimestampMixin):
    __tablename__ = "key_results"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="not_started", nullable=False)  # not_started, on_track, at_risk, achieved
    metric_type: Mapped[str] = mapped_column(String(30), default="metric", nullable=False)  # metric, milestone, binary
    target_value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    current_value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    start_value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    owner_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    target_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    achieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.5, nullable=False)
    weight: Mapped[float] = mapped_column(default=1.0, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    goalstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    goal: Mapped["Goal"] = relationship(back_populates="key_results")
    owner: Mapped[Optional["Employee"]] = relationship()

    __table_args__ = (
        Index("ix_key_results_goal", "goal_id"),
        Index("ix_key_results_owner", "owner_id"),
    )


class GoalUpdate(Base, TimestampMixin):
    __tablename__ = "goal_updates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    goal_id: Mapped[str] = mapped_column(
        ForeignKey("goals.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)  # on_track, at_risk, off_track, achieved
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.5, nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    challenges: Mapped[Optional[str]] = mapped_column(Text)
    next_steps: Mapped[Optional[str]] = mapped_column(Text)
    goalstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    goal: Mapped["Goal"] = relationship(back_populates="updates")
    author: Mapped["Employee"] = relationship()

    __table_args__ = (
        Index("ix_goal_updates_goal", "goal_id"),
        Index("ix_goal_updates_author", "author_id"),
    )