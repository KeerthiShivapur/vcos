"""Org Capability Intelligence models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class CapabilityHistory(Base, TimestampMixin):
    __tablename__ = "capability_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    capability_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)  # created, updated, deprecated, merged, split
    previous_state: Mapped[Optional[dict]] = mapped_column(JSON)
    new_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    changed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    change_reason: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_capability_history_org_capability", "organization_id", "capability_id"),
        Index("ix_capability_history_org_time", "organization_id", "created_at"),
    )


class CapabilityProjectLink(Base, TimestampMixin):
    __tablename__ = "capability_project_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    capability_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    project_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    link_type: Mapped[str] = mapped_column(String(40), default="requires", nullable=False)  # requires, provides, enhances
    strength: Mapped[float] = mapped_column(default=1.0, nullable=False)
    capabilityhistory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("capability_id", "project_id", "link_type", name="uq_capability_project_link_unique"),
        Index("ix_capability_project_links_org", "organization_id"),
    )


class CapabilitySignal(Base, TimestampMixin):
    __tablename__ = "capability_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    capability_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(40), nullable=False)  # demand, supply, gap, trend, saturation
    strength: Mapped[float] = mapped_column(default=0.0, nullable=False)
    direction: Mapped[str] = mapped_column(String(20), default="stable", nullable=False)  # rising, falling, stable
    source: Mapped[str] = mapped_column(String(60), default="system", nullable=False)
    evidence: Mapped[List[str]] = mapped_column(JSON, default=list)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_capability_signals_org_capability", "organization_id", "capability_id"),
        Index("ix_capability_signals_org_type", "organization_id", "signal_type"),
    )


class OrgCapability(Base, TimestampMixin):
    __tablename__ = "org_capabilities"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[str] = mapped_column(String(40), default="core", nullable=False)  # core, supporting, emerging, deprecated
    maturity_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)  # 1-5
    proficiency: Mapped[float] = mapped_column(default=0.0, nullable=False)  # 0-1
    strategic_importance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1-5
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    team_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)  # active, emerging, declining, deprecated
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    related_capabilities: Mapped[List[str]] = mapped_column(JSON, default=list)
    dependencies: Mapped[List[str]] = mapped_column(JSON, default=list)
    capabilityhistory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_org_capabilities_org_name"),
        Index("ix_org_capabilities_org_category", "organization_id", "category"),
        Index("ix_org_capabilities_org_maturity", "organization_id", "maturity_level"),
    )


CAPABILITY_STATES = (
    "active",
    "emerging",
    "declining",
    "deprecated",
    "planned",
    "archived",
)

CAPACITY_STATES = (
    "available",
    "constrained",
    "overloaded",
    "unavailable",
    "planned",
)