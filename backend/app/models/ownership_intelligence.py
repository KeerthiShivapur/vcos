"""Ownership Intelligence models."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class OwnershipChange(Base, TimestampMixin):
    __tablename__ = "ownership_changes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    previous_owner_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    new_owner_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    change_type: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    changed_by: Mapped[str] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), index=True)
    effective_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    ownershipchange_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_ownership_changes_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_ownership_changes_org_effective", "organization_id", "effective_at"),
    )


class OwnershipRelationship(Base, TimestampMixin):
    __tablename__ = "ownership_relationships"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    owner_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    ownership_type: Mapped[str] = mapped_column(String(40), default="primary", nullable=False)
    percentage: Mapped[float] = mapped_column(default=100.0, nullable=False)
    start_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    end_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ownershipchange_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("entity_type", "entity_id", "owner_id", "ownership_type", name="uq_ownership_rels_unique"),
        Index("ix_ownership_rels_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_ownership_rels_org_owner", "organization_id", "owner_id"),
    )


class OwnershipSignal(Base, TimestampMixin):
    __tablename__ = "ownership_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    signal_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(32), index=True)
    owner_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    signal_strength: Mapped[float] = mapped_column(default=0.0, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    ownershipchange_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_ownership_signals_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_ownership_signals_org_actor", "organization_id", "actor_id"),
    )


# Responsibility types constant (mirrored from execution_strategy for compatibility)
RESPONSIBILITY_TYPES = (
    "accountability",
    "ownership",
    "approval",
    "consultation",
    "information",
)