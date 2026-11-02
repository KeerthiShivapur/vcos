"""Organization Health model."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class OrganizationHealth(Base, TimestampMixin):
    __tablename__ = "organization_health"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    health_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    health_status: Mapped[str] = mapped_column(String(24), default="good", nullable=False)  # excellent, good, fair, poor, critical
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)
    trends: Mapped[dict] = mapped_column(JSON, default=dict)
    alerts: Mapped[List[str]] = mapped_column(JSON, default=list)
    recommendations: Mapped[List[str]] = mapped_column(JSON, default=list)
    period_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    period_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_org_health_org_period", "organization_id", "period_end"),
    )