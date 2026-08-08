"""Internal academies (Phase 10.8 — Internal Academy).

Organizations create learning academies (Engineering Academy, Leadership
Academy, Sales Academy, Security Academy, AI Academy, Finance Academy).
Each academy groups courses, knowledge, experts, communities and projects
behind a common theme; employees join academies aligned with their growth
interests.
"""

from typing import Optional

from sqlalchemy import JSON, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Academy(Base, TimestampMixin):
    __tablename__ = "academies"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_academy_name_org"),
        Index("ix_academies_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(120))
    # engineering | leadership | sales | security | ai | finance | hr | compliance | design | research
    cover_url: Mapped[Optional[str]] = mapped_column(String(500))
    curriculum: Mapped[Optional[list[str]]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="published")
    # draft | published | archived

    members: Mapped[list["AcademyMember"]] = relationship(
        back_populates="academy", cascade="all, delete-orphan"
    )
    courses: Mapped[list["AcademyCourse"]] = relationship(
        back_populates="academy", cascade="all, delete-orphan", order_by="AcademyCourse.position"
    )


class AcademyMember(Base, TimestampMixin):
    __tablename__ = "academy_members"
    __table_args__ = (
        UniqueConstraint("organization_id", "academy_id", "employee_id", name="uq_academy_member"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    academy_id: Mapped[str] = mapped_column(
        ForeignKey("academies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role: Mapped[str] = mapped_column(String(20), default="member")
    # member | admin

    academy: Mapped["Academy"] = relationship(back_populates="members")


class AcademyCourse(Base, TimestampMixin):
    __tablename__ = "academy_courses"
    __table_args__ = (
        UniqueConstraint("organization_id", "academy_id", "course_id", name="uq_academy_course"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    academy_id: Mapped[str] = mapped_column(
        ForeignKey("academies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    course_id: Mapped[str] = mapped_column(
        ForeignKey("courses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, default=0)

    academy: Mapped["Academy"] = relationship(back_populates="courses")
