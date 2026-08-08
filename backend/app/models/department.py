"""Departments — the formal structure of the organization (Phase 2)."""

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class Department(Base, TimestampMixin):
    __tablename__ = "departments"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_department_code_org"),
        UniqueConstraint("organization_id", "name", name="uq_department_name_org"),
        Index("ix_departments_org_parent", "organization_id", "parent_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL")
    )
    head_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    location_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    parent: Mapped[Optional["Department"]] = relationship(
        remote_side="Department.id", back_populates="children"
    )
    children: Mapped[list["Department"]] = relationship(back_populates="parent")
    head: Mapped[Optional["Employee"]] = relationship(  # noqa: F821
        foreign_keys=[head_id], back_populates="headed_departments"
    )
    employees: Mapped[list["Employee"]] = relationship(  # noqa: F821
        back_populates="department", foreign_keys="Employee.department_id"
    )
    teams: Mapped[list["Team"]] = relationship(  # noqa: F821
        back_populates="department", foreign_keys="Team.department_id"
    )


class BusinessUnit(Base, TimestampMixin):
    __tablename__ = "business_units"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_bu_code_org"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    head_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("business_units.id", ondelete="SET NULL")
    )
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    parent: Mapped[Optional["BusinessUnit"]] = relationship(
        remote_side="BusinessUnit.id", back_populates="children"
    )
    children: Mapped[list["BusinessUnit"]] = relationship(back_populates="parent")


class Location(Base, TimestampMixin):
    __tablename__ = "locations"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_location_code_org"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    code: Mapped[str] = mapped_column(String(60), nullable=False)
    city: Mapped[Optional[str]] = mapped_column(String(150))
    country: Mapped[Optional[str]] = mapped_column(String(150))
    address: Mapped[Optional[str]] = mapped_column(String(500))
    is_office: Mapped[bool] = mapped_column(default=True)
    timezone: Mapped[Optional[str]] = mapped_column(String(80))
    created_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    employees: Mapped[list["Employee"]] = relationship(  # noqa: F821
        back_populates="location", foreign_keys="Employee.location_id"
    )
