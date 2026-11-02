"""Task and Task Dependency models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Enum as SQLEnum, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class TaskStatus(str):
    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    DONE = "done"
    CANCELLED = "cancelled"
    BLOCKED = "blocked"


class TaskPriority(str):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    URGENT = "urgent"


class TaskType(str):
    TASK = "task"
    BUG = "bug"
    FEATURE = "feature"
    EPIC = "epic"
    STORY = "story"
    SPIKE = "spike"
    CHORE = "chore"
    SUBTASK = "subtask"


class Task(Base, TimestampMixin):
    __tablename__ = "tasks"

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
    sprint_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("sprints.id", ondelete="SET NULL"), index=True
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )
    assignee_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    reporter_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default=TaskStatus.BACKLOG, nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default=TaskPriority.MEDIUM, nullable=False, index=True)
    task_type: Mapped[str] = mapped_column(String(20), default=TaskType.TASK, nullable=False, index=True)
    story_points: Mapped[Optional[float]] = mapped_column(default=None)
    estimated_hours: Mapped[Optional[float]] = mapped_column(default=None)
    logged_hours: Mapped[float] = mapped_column(default=0.0, nullable=False)
    remaining_hours: Mapped[Optional[float]] = mapped_column(default=None)
    progress: Mapped[float] = mapped_column(default=0.0, nullable=False)
    status_detail: Mapped[Optional[str]] = mapped_column(String(500))
    start_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), index=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    labels: Mapped[List[str]] = mapped_column(JSON, default=list)
    custom_fields: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    watchers: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    blocked_reason: Mapped[Optional[str]] = mapped_column(Text)
    recurrence_rule: Mapped[Optional[str]] = mapped_column(String(500))
    recurrence_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    original_task_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("tasks.id", ondelete="SET NULL"), index=True
    )

    # Relationships
    project: Mapped["Project"] = relationship(back_populates="tasks")
    epic: Mapped[Optional["Epic"]] = relationship(back_populates="tasks")
    sprint: Mapped[Optional["Sprint"]] = relationship(back_populates="tasks")
    parent: Mapped[Optional["Task"]] = relationship(
        back_populates="subtasks",
        foreign_keys="Task.parent_id",
        remote_side="Task.id"
    )
    subtasks: Mapped[List["Task"]] = relationship(
        back_populates="parent",
        foreign_keys="Task.parent_id"
    )
    assignee: Mapped[Optional["Employee"]] = relationship(back_populates="assigned_tasks", foreign_keys="Task.assignee_id")
    reporter: Mapped[Optional["Employee"]] = relationship(back_populates="reported_tasks", foreign_keys="Task.reporter_id")
    dependencies: Mapped[List["TaskDependency"]] = relationship(
        back_populates="task", foreign_keys="TaskDependency.task_id", cascade="all, delete-orphan"
    )
    dependents: Mapped[List["TaskDependency"]] = relationship(
        back_populates="depends_on_task", foreign_keys="TaskDependency.depends_on_task_id"
    )
    comments: Mapped[List["TaskComment"]] = relationship(back_populates="task", cascade="all, delete-orphan")
    attachments: Mapped[List["TaskAttachment"]] = relationship(back_populates="task", cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("project_id", "slug", name="uq_tasks_proj_slug"),
        Index("ix_tasks_proj_status", "project_id", "status"),
        Index("ix_tasks_proj_assignee", "project_id", "assignee_id"),
        Index("ix_tasks_proj_status_priority", "project_id", "status", "priority"),
        Index("ix_tasks_assignee_status", "assignee_id", "status"),
        Index("ix_tasks_parent", "parent_id"),
    )


class TaskDependency(Base, TimestampMixin):
    __tablename__ = "task_dependencies"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    depends_on_task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dependency_type: Mapped[str] = mapped_column(String(20), default="blocks", nullable=False)  # blocks, is_blocked_by, relates_to, duplicates, clones
    lag_days: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    taskstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    task: Mapped["Task"] = relationship(back_populates="dependencies", foreign_keys="TaskDependency.task_id")
    depends_on_task: Mapped["Task"] = relationship(back_populates="dependents", foreign_keys="TaskDependency.depends_on_task_id")

    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_task_deps_task_depends"),
        Index("ix_task_deps_task", "task_id"),
        Index("ix_task_deps_depends_on", "depends_on_task_id"),
    )


class TaskComment(Base, TimestampMixin):
    __tablename__ = "task_comments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    author_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("task_comments.id", ondelete="SET NULL"), index=True
    )
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reactions: Mapped[dict] = mapped_column(JSON, default=dict)
    mentions: Mapped[List[str]] = mapped_column(JSON, default=list)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    task: Mapped["Task"] = relationship(back_populates="comments")
    author: Mapped["Employee"] = relationship()
    parent: Mapped[Optional["TaskComment"]] = relationship(
        back_populates="replies", remote_side="TaskComment.id"
    )
    replies: Mapped[List["TaskComment"]] = relationship(back_populates="parent")

    __table_args__ = (
        Index("ix_task_comments_task_created", "task_id", "created_at"),
        Index("ix_task_comments_author", "author_id"),
    )


class TaskAttachment(Base, TimestampMixin):
    __tablename__ = "task_attachments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"), index=True, nullable=False
    )
    uploaded_by: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(300), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(300), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(50), default="local", nullable=False)
    checksum: Mapped[Optional[str]] = mapped_column(String(64))
    is_inline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    taskstatus_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    task: Mapped["Task"] = relationship(back_populates="attachments")
    uploader: Mapped["Employee"] = relationship()

    __table_args__ = (
        Index("ix_task_attachments_task", "task_id"),
        Index("ix_task_attachments_uploader", "uploaded_by"),
    )