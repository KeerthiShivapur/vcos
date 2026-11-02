"""Skills Intelligence models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class CanonicalSkill(Base, TimestampMixin):
    __tablename__ = "canonical_skills"
    __table_args__ = (
        UniqueConstraint("organization_id", "slug", name="uq_canonical_skills_org_slug"),
        Index("ix_canonical_skills_org_category", "organization_id", "category"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(40), default="technical", nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text)
    aliases: Mapped[List[str]] = mapped_column(JSON, default=list)
    related_skills: Mapped[List[str]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    skill_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)


class SkillAlias(Base):
    __tablename__ = "skill_aliases"
    __table_args__ = (
        UniqueConstraint("canonical_skill_id", "alias", name="uq_skill_aliases_canonical_alias"),
        {"extend_existing": True},
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    canonical_skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    alias: Mapped[str] = mapped_column(String(200), nullable=False)
    source: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)


class PersonSkill(Base, TimestampMixin):
    __tablename__ = "person_skills"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    canonical_skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    proficiency_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    years_experience: Mapped[float] = mapped_column(default=0.0, nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source: Mapped[str] = mapped_column(String(20), default="self", nullable=False)
    last_assessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    skill_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("employee_id", "canonical_skill_id", name="uq_person_skills_emp_skill"),
        Index("ix_person_skills_emp_proficiency", "employee_id", "proficiency_level"),
    )


class Expertise(Base, TimestampMixin):
    __tablename__ = "expertise"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    canonical_skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), default="calculated", nullable=False)
    skill_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("employee_id", "canonical_skill_id", name="uq_expertise_emp_skill"),
        Index("ix_expertise_org_level", "organization_id", "level"),
    )


class ExpertiseEvidence(Base, TimestampMixin):
    __tablename__ = "expertise_evidence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    expertise_id: Mapped[str] = mapped_column(
        ForeignKey("expertise.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evidence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    weight: Mapped[float] = mapped_column(default=1.0, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    skill_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_expertise_evidence_expertise", "expertise_id"),
    )


class CapabilityAggregate(Base, TimestampMixin):
    __tablename__ = "capability_aggregates"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    scope_type: Mapped[str] = mapped_column(String(40), default="organization", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    canonical_skill_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    employee_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    avg_proficiency: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    total_experience_years: Mapped[float] = mapped_column(default=0.0, nullable=False)
    experts_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    beginners_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    gap_analysis: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    last_calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_capability_agg_org_scope", "organization_id", "scope_type", "scope_id"),
        Index("ix_capability_agg_org_skill", "organization_id", "canonical_skill_id"),
    )


# Constants for capability aggregates
AGGREGATE_SCOPE_TYPES = (
    "organization",
    "department",
    "team",
    "project",
    "business_unit",
)