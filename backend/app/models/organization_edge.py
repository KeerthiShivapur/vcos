"""Organization Edge model."""

from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class OrganizationEdge(Base, TimestampMixin):
    __tablename__ = "organization_edges"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    target_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    relationship: Mapped[str] = mapped_column(String(60), nullable=False)
    weight: Mapped[float] = mapped_column(default=1.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    organizationedge_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("organization_id", "source_type", "source_id", "target_type", "target_id", "relationship", name="uq_org_edges_unique"),
        Index("ix_org_edges_org_source", "organization_id", "source_type", "source_id"),
        Index("ix_org_edges_org_target", "organization_id", "target_type", "target_id"),
        Index("ix_org_edges_org_active", "organization_id", "is_active"),
    )