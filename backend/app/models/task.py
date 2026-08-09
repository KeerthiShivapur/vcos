"""Tasks and dependencies (Phase 3 — Work Execution Engine)."""

from datetime import date, datetime
from typing import Optional

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
from sqlalchemy.orm import Mapped, mapped_column

from app.core.timeutils import utcnow
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

TASK_STATUSES = ("backlog", "todo", "in_progress", "review", "blocked", "completed", "archived")


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (
        Index("ix_tasks_org_project", "organization_id", "project_id"),
        Index("ix_tasks_org_assignee", "organization_id", "assignee_id"),
        Index("ix_tasks_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[Optional[str]] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"))
    epic_id: Mapped[Optional[str]] = mapped_column(ForeignKey("epics.id", ondelete="SET NULL"))
    milestone_id: Mapped[Optional[str]] = mapped_column(ForeignKey("milestones.id", ondelete="SET NULL"))
    sprint_id: Mapped[Optional[str]] = mapped_column(ForeignKey("sprints.id", ondelete="SET NULL"))
    parent_task_id: Mapped[Optional[str]] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="backlog", index=True)
    priority: Mapped[str] = mapped_column(String(20), default="medium")  # low|medium|high|critical
    assignee_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    reporter_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    estimate_hours: Mapped[Optional[float]] = mapped_column(Float)
    spent_hours: Mapped[float] = mapped_column(Float, default=0)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    due_date: Mapped[Optional[date]] = mapped_column(Date)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    progress: Mapped[int] = mapped_column(Integer, default=0)  # 0-100
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class TaskDependency(Base):
    __tablename__ = "task_dependencies"
    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_dependency"),
        Index("ix_task_deps_org", "organization_id", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    depends_on_task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(
        String(30), default="finish_to_start"
    )  # finish_to_start|start_to_start|finish_to_finish|blocking|related
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class TaskComment(Base):
    """Discussion on a task — the collaborative surface of execution."""

    __tablename__ = "task_comments"
    __table_args__ = (
        Index("ix_task_comments_org_task", "organization_id", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    author_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    mentions: Mapped[Optional[list[str]]] = mapped_column(JSON)  # employee ids @-mentioned
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class TaskAttachment(Base):
    """File metadata attached to a task (storage is external/URL-based)."""

    __tablename__ = "task_attachments"
    __table_args__ = (
        Index("ix_task_attachments_org_task", "organization_id", "task_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[Optional[str]] = mapped_column(String(100))  # mime type
    uploaded_by: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
