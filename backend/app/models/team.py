"""Teams — cross-functional working groups inside departments (Phase 2)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    JSON,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Team(Base, TimestampMixin):
    __tablename__ = "teams"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_team_code_org"),
        UniqueConstraint("organization_id", "name", name="uq_team_name_org"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    lead_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    department: Mapped[Optional["Department"]] = relationship(  # noqa: F821
        back_populates="teams", foreign_keys=[department_id]
    )
    lead: Mapped[Optional["Employee"]] = relationship(  # noqa: F821
        foreign_keys=[lead_id], back_populates="led_teams"
    )
    members: Mapped[list["Employee"]] = relationship(  # noqa: F821
        back_populates="team", foreign_keys="Employee.team_id"
    )
    cross_memberships: Mapped[list["TeamMember"]] = relationship(  # noqa: F821
        back_populates="team", cascade="all, delete-orphan"
    )


class TeamMember(Base):
    """Many-to-many memberships for cross-functional / matrix teams."""

    __tablename__ = "team_members"
    __table_args__ = (
        UniqueConstraint("team_id", "employee_id", name="uq_team_member"),
        Index("ix_team_members_org", "organization_id", "employee_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    employee_id: Mapped[str] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[Optional[str]] = mapped_column(String(120))
    joined_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    team: Mapped["Team"] = relationship(back_populates="cross_memberships")  # noqa: F821
    employee: Mapped["Employee"] = relationship()  # noqa: F821


class TeamGoal(Base):
    __tablename__ = "team_goals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    team_id: Mapped[str] = mapped_column(ForeignKey("teams.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="planned")
    meta: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
