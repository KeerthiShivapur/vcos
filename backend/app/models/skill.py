"""Skill models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class SkillCategory(str):
    TECHNICAL = "technical"
    SOFT = "soft"
    LEADERSHIP = "leadership"
    DOMAIN = "domain"
    TOOL = "tool"
    LANGUAGE = "language"
    FRAMEWORK = "framework"
    PLATFORM = "platform"
    METHODOLOGY = "methodology"
    CERTIFICATION = "certification"


class SkillLevel(str):
    BEGINNER = "beginner"
    INTERMEDIATE = "intermediate"
    ADVANCED = "advanced"
    EXPERT = "expert"


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), default=SkillCategory.TECHNICAL, nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    aliases: Mapped[List[str]] = mapped_column(JSON, default=list)
    related_skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    skillcategory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    organization: Mapped["Organization"] = relationship()
    aliases_list: Mapped[List["SkillAliasRecord"]] = relationship(back_populates="skill", cascade="all, delete-orphan")
    employee_skills: Mapped[List["EmployeeSkill"]] = relationship(back_populates="skill")

    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_skills_org_slug"),
        UniqueConstraint("organization_id", "name", name="uq_skills_org_name"),
        Index("ix_skills_org_category", "organization_id", "category"),
    )


class SkillAliasRecord(Base, TimestampMixin):
    __tablename__ = "skill_aliases"
    __table_args__ = {"extend_existing": True}

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)  # manual, extracted, imported

    # Relationships
    skill: Mapped["Skill"] = relationship(back_populates="aliases_list")

    __table_args__ = (
        UniqueConstraint("skill_id", "alias", name="uq_skill_aliases_skill_alias"),
        {"extend_existing": True},
    )


class ExpertiseScore(Base, TimestampMixin):
    __tablename__ = "expertise_scores"

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
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    score: Mapped[float] = mapped_column(default=0.0, nullable=False)  # calculated score
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), default="calculated", nullable=False)  # calculated, manual, imported
    skillcategory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    employee: Mapped["Employee"] = relationship()
    skill: Mapped["Skill"] = relationship()

    __table_args__ = (
        UniqueConstraint("employee_id", "skill_id", name="uq_expertise_scores_emp_skill"),
        Index("ix_expertise_scores_emp_skill", "employee_id", "skill_id"),
        Index("ix_expertise_scores_org_level", "organization_id", "level"),
    )