"""Department, Business Unit, and Location models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class Department(Base, TimestampMixin):
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), index=True
    )
    manager_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    cost_center: Mapped[Optional[str]] = mapped_column(String(50))
    budget_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    budget_amount: Mapped[Optional[float]] = mapped_column(default=0.0)
    headcount: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    department_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="departments")
    parent: Mapped[Optional["Department"]] = relationship(
        back_populates="children", remote_side="Department.id"
    )
    children: Mapped[List["Department"]] = relationship(back_populates="parent")
    manager: Mapped[Optional["Employee"]] = relationship(
        back_populates="managed_departments",
        foreign_keys="Department.manager_id"
    )
    employees: Mapped[List["Employee"]] = relationship(back_populates="department", foreign_keys="Employee.department_id")
    projects: Mapped[List["Project"]] = relationship(back_populates="department")
    teams: Mapped[List["Team"]] = relationship(back_populates="department")

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_departments_org_code"),
        Index("ix_departments_org_parent", "organization_id", "parent_id"),
        Index("ix_departments_org_active", "organization_id", "is_active"),
        {"extend_existing": True},
    )


class BusinessUnit(Base, TimestampMixin):
    __tablename__ = "business_units"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    unit_type: Mapped[str] = mapped_column(String(40), default="business_unit", nullable=False)  # business_unit, division, subsidiary
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("business_units.id", ondelete="SET NULL"), index=True
    )
    leader_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_profit_center: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    budget_amount: Mapped[Optional[float]] = mapped_column(default=0.0)
    revenue_target: Mapped[Optional[float]] = mapped_column(default=0.0)
    department_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="business_units")
    parent: Mapped[Optional["BusinessUnit"]] = relationship(
        back_populates="children", remote_side="BusinessUnit.id"
    )
    children: Mapped[List["BusinessUnit"]] = relationship(back_populates="parent")
    leader: Mapped[Optional["Employee"]] = relationship()

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_business_units_org_code"),
        Index("ix_business_units_org_parent", "organization_id", "parent_id"),
    )


class Location(Base, TimestampMixin):
    __tablename__ = "locations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    address_line1: Mapped[Optional[str]] = mapped_column(String(200))
    address_line2: Mapped[Optional[str]] = mapped_column(String(200))
    city: Mapped[Optional[str]] = mapped_column(String(100))
    state: Mapped[Optional[str]] = mapped_column(String(100))
    postal_code: Mapped[Optional[str]] = mapped_column(String(20))
    country: Mapped[Optional[str]] = mapped_column(String(100))
    timezone: Mapped[str] = mapped_column(String(50), default="UTC", nullable=False)
    latitude: Mapped[Optional[float]] = mapped_column(default=None)
    longitude: Mapped[Optional[float]] = mapped_column(default=None)
    location_type: Mapped[str] = mapped_column(String(30), default="office", nullable=False)  # office, warehouse, remote, hybrid
    capacity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_headquarters: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    department_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    # Relationships
    organization: Mapped["Organization"] = relationship(back_populates="locations")
    employees: Mapped[List["Employee"]] = relationship(back_populates="location")

    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_locations_org_code"),
        Index("ix_locations_org_country", "organization_id", "country"),
        Index("ix_locations_org_active", "organization_id", "is_active"),
    )