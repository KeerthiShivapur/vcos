"""Skills catalog and expertise scoring (Phase 2)."""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Skill(Base, TimestampMixin):
    __tablename__ = "skills"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_skill_name_org"),
        Index("ix_skills_org_category", "organization_id", "category"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(120))
    description: Mapped[Optional[str]] = mapped_column(Text)

    employees: Mapped[list["EmployeeSkill"]] = relationship(  # noqa: F821
        back_populates="skill", cascade="all, delete-orphan"
    )
    expertise_scores: Mapped[list["ExpertiseScore"]] = relationship(  # noqa: F821
        back_populates="skill", cascade="all, delete-orphan"
    )


class ExpertiseScore(Base, TimestampMixin):
    """Per-skill expertise score computed by the expertise engine."""

    __tablename__ = "expertise_scores"
    __table_args__ = (
        UniqueConstraint("organization_id", "employee_id", "skill_id", name="uq_expertise_score"),
        Index("ix_expertise_org_score", "organization_id", "score"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)
    level: Mapped[int] = mapped_column(default=1)
    years_experience: Mapped[float] = mapped_column(Float, default=0.0)
    factors: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON)
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    employee: Mapped["Employee"] = relationship(back_populates="expertise_scores")  # noqa: F821
    skill: Mapped["Skill"] = relationship(back_populates="expertise_scores")  # noqa: F821
