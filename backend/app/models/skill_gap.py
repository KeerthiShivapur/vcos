"""Skill gap analysis and organizational skill snapshots (Phase 10.3-10.4).

The Skill Engine maintains each employee's skill graph (levels derived from
EmployeeSkill + ExpertiseScore plus learning-derived boosts). The gap
analyzer continuously compares the current role's required skills (from the
career path framework) with current levels and persists SkillGap rows with
priority. SkillSnapshot rows power the Organization Skill Map: per-skill
aggregates (count, average level, open gaps, demand) that answer questions
like "do we have enough AI engineers?" and let analytics predict shortages.
"""

from datetime import date
from typing import Optional

from sqlalchemy import Date, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class SkillGap(Base, TimestampMixin):
    __tablename__ = "skill_gaps"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "employee_id", "skill_id", name="uq_skill_gap_employee_skill"
        ),
        Index("ix_skill_gaps_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE")
    )
    skill_name: Mapped[str] = mapped_column(String(120), nullable=False)
    required_level: Mapped[int] = mapped_column(Integer, default=3)  # 1..5
    current_level: Mapped[float] = mapped_column(Float, default=0.0)
    gap: Mapped[float] = mapped_column(Float, default=0.0)
    priority: Mapped[str] = mapped_column(String(20), default="medium")
    # low | medium | high
    source: Mapped[str] = mapped_column(String(40), default="role_framework")
    # role_framework | career_path | assessment | ai | manager
    status: Mapped[str] = mapped_column(String(20), default="open")
    # open | addressed | closed
    notes: Mapped[Optional[str]] = mapped_column(Text)

    @property
    def coverage(self) -> float:
        """Fraction of the required level currently covered (0..1)."""
        if self.required_level <= 0:
            return 1.0
        return max(0.0, min(1.0, self.current_level / self.required_level))


class SkillSnapshot(Base, TimestampMixin):
    """Organization Skill Map row: one aggregate per skill per organization."""

    __tablename__ = "skill_snapshots"
    __table_args__ = (
        UniqueConstraint("organization_id", "skill_id", "snapshot_date", name="uq_skill_snapshot"),
        Index("ix_skill_snapshots_org", "organization_id", "snapshot_date"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_name: Mapped[str] = mapped_column(String(120), nullable=False)
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    employee_count: Mapped[int] = mapped_column(Integer, default=0)
    average_level: Mapped[float] = mapped_column(Float, default=0.0)
    max_level: Mapped[float] = mapped_column(Float, default=0.0)
    open_gaps: Mapped[int] = mapped_column(Integer, default=0)
    high_gaps: Mapped[int] = mapped_column(Integer, default=0)
    demand_level: Mapped[int] = mapped_column(Integer, default=0)  # 1..5 derived from gaps
    projected_shortage: Mapped[bool] = mapped_column(default=False)
