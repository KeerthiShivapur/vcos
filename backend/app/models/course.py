"""Course platform models (Phase 10.2 — Course Management).

Courses support internal and external content, recorded videos, live
sessions, documents, books and interactive content. Each course is
structured into optional modules containing lessons and quizzes; employees
enroll and progress through lessons until the course is completed and a
certificate may be issued. Course skill tags feed the Skill Engine so that
completing a course updates the employee's skill graph.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    JSON,
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


class Course(Base, TimestampMixin):
    __tablename__ = "courses"
    __table_args__ = (
        UniqueConstraint("organization_id", "title", name="uq_course_title_org"),
        Index("ix_courses_org_status", "organization_id", "status"),
        Index("ix_courses_org_category", "organization_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(120))
    difficulty: Mapped[str] = mapped_column(String(20), default="beginner")
    # beginner | intermediate | advanced
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)
    format: Mapped[str] = mapped_column(String(30), default="internal")
    # internal | external | video | live | document | book | interactive
    author_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    department: Mapped[Optional[str]] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(10), default="en")
    status: Mapped[str] = mapped_column(String(20), default="published")
    # draft | published | archived
    external_url: Mapped[Optional[str]] = mapped_column(String(500))
    cover_url: Mapped[Optional[str]] = mapped_column(String(500))
    certificate_title: Mapped[Optional[str]] = mapped_column(String(255))
    skills: Mapped[Optional[list[str]]] = mapped_column(JSON)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON)

    modules: Mapped[list["CourseModule"]] = relationship(
        back_populates="course", cascade="all, delete-orphan",
        order_by="CourseModule.position",
    )
    enrollments: Mapped[list["CourseEnrollment"]] = relationship(
        back_populates="course", cascade="all, delete-orphan"
    )


class CourseModule(Base, TimestampMixin):
    __tablename__ = "course_modules"
    __table_args__ = (
        UniqueConstraint("organization_id", "course_id", "position", name="uq_module_position"),
        Index("ix_modules_course", "organization_id", "course_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, default=0)

    course: Mapped["Course"] = relationship(back_populates="modules")
    lessons: Mapped[list["Lesson"]] = relationship(
        back_populates="module", cascade="all, delete-orphan",
        order_by="Lesson.position",
    )
    quizzes: Mapped[list["CourseQuiz"]] = relationship(
        back_populates="module", cascade="all, delete-orphan",
        order_by="CourseQuiz.position",
    )


class Lesson(Base, TimestampMixin):
    __tablename__ = "lessons"
    __table_args__ = (
        Index("ix_lessons_course_module", "organization_id", "course_id", "module_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    module_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("course_modules.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    content: Mapped[Optional[str]] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(String(30), default="text")
    # text | video | document | external | interactive
    external_url: Mapped[Optional[str]] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=0)

    module: Mapped[Optional["CourseModule"]] = relationship(back_populates="lessons")
    progress: Mapped[list["LessonProgress"]] = relationship(
        back_populates="lesson", cascade="all, delete-orphan"
    )


class CourseQuiz(Base, TimestampMixin):
    __tablename__ = "course_quizzes"
    __table_args__ = (
        Index("ix_course_quizzes_module", "organization_id", "course_id", "module_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    module_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("course_modules.id", ondelete="CASCADE")
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    questions: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON)
    # [{prompt, options: [..], answer_index, points}]
    position: Mapped[int] = mapped_column(Integer, default=0)
    passing_score: Mapped[float] = mapped_column(Float, default=70.0)

    module: Mapped[Optional["CourseModule"]] = relationship(back_populates="quizzes")


class CourseEnrollment(Base, TimestampMixin):
    __tablename__ = "course_enrollments"
    __table_args__ = (
        UniqueConstraint("organization_id", "course_id", "employee_id", name="uq_course_enrollment"),
        Index("ix_enrollments_employee", "organization_id", "employee_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[str] = mapped_column(String(20), default="enrolled")
    # enrolled | in_progress | completed
    progress: Mapped[float] = mapped_column(Float, default=0.0)
    enrolled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_activity_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    course: Mapped["Course"] = relationship(back_populates="enrollments")
    lesson_progress: Mapped[list["LessonProgress"]] = relationship(
        back_populates="enrollment", cascade="all, delete-orphan"
    )


class LessonProgress(Base):
    __tablename__ = "lesson_progress"
    __table_args__ = (
        UniqueConstraint("organization_id", "enrollment_id", "lesson_id", name="uq_lesson_progress"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    enrollment_id: Mapped[str] = mapped_column(
        ForeignKey("course_enrollments.id", ondelete="CASCADE"), index=True, nullable=False
    )
    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="CASCADE"), index=True, nullable=False
    )
    completed: Mapped[bool] = mapped_column(default=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    enrollment: Mapped["CourseEnrollment"] = relationship(back_populates="lesson_progress")
    lesson: Mapped["Lesson"] = relationship(back_populates="progress")
