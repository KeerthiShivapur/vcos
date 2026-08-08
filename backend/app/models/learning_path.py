"""Career-based learning paths (Phase 10.2 — Learning Paths).

Instead of random courses, employees receive structured career-based paths
(e.g. Backend Developer: Python → FastAPI → Docker → PostgreSQL → Redis →
Architecture → Leadership). Each path is a sequence of steps; a step can
reference a course, a skill to build, a knowledge document, a project to
join, a mentorship, an assessment or a book. Employees enroll in paths and
the system tracks progress to completion.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class LearningPath(Base, TimestampMixin):
    __tablename__ = "learning_paths"
    __table_args__ = (
        Index("ix_learning_paths_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    target_role: Mapped[Optional[str]] = mapped_column(String(150))
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner")
    estimated_days: Mapped[Optional[int]] = mapped_column(Integer)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="published")
    # draft | published | archived
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

    steps: Mapped[list["LearningPathStep"]] = relationship(
        back_populates="path", cascade="all, delete-orphan", order_by="LearningPathStep.position"
    )
    enrollments: Mapped[list["PathEnrollment"]] = relationship(
        back_populates="path", cascade="all, delete-orphan"
    )


class LearningPathStep(Base, TimestampMixin):
    __tablename__ = "learning_path_steps"
    __table_args__ = (
        Index("ix_path_steps_path", "organization_id", "path_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    path_id: Mapped[str] = mapped_column(
        ForeignKey("learning_paths.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)
    kind: Mapped[str] = mapped_column(String(30), default="course")
    # course | skill | knowledge | project | mentorship | assessment | book | training
    skill_name: Mapped[Optional[str]] = mapped_column(String(120))
    course_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL")
    )
    reference_id: Mapped[Optional[str]] = mapped_column(String(32))

    path: Mapped["LearningPath"] = relationship(back_populates="steps")


class PathEnrollment(Base, TimestampMixin):
    __tablename__ = "path_enrollments"
    __table_args__ = (
        Index("ix_path_enrollments_emp", "organization_id", "employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    path_id: Mapped[str] = mapped_column(
        ForeignKey("learning_paths.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="active")
    # active | completed | abandoned
    progress: Mapped[float] = mapped_column(default=0.0)
    completed_step_ids: Mapped[Optional[list[str]]] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    path: Mapped["LearningPath"] = relationship(back_populates="enrollments")
