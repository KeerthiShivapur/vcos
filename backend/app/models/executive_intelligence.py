"""Executive Intelligence model."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class ExecutiveIntelligence(Base, TimestampMixin):
    __tablename__ = "executive_intelligence"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    intelligence_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    detailed_analysis: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    impact_level: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    urgency: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)
    time_horizon: Mapped[str] = mapped_column(String(24), default="medium_term", nullable=False)
    affected_domains: Mapped[List[str]] = mapped_column(JSON, default=list)
    affected_entities: Mapped[List[dict]] = mapped_column(JSON, default=list)
    key_drivers: Mapped[List[str]] = mapped_column(JSON, default=list)
    assumptions: Mapped[List[str]] = mapped_column(JSON, default=list)
    data_sources: Mapped[List[str]] = mapped_column(JSON, default=list)
    methodology: Mapped[Optional[str]] = mapped_column(Text)
    limitations: Mapped[Optional[str]] = mapped_column(Text)
    actionable_recommendations: Mapped[List[dict]] = mapped_column(JSON, default=list)
    monitoring_indicators: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    reviewed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_executive_intelligence_org_type", "organization_id", "intelligence_type"),
        Index("ix_executive_intelligence_org_impact", "organization_id", "impact_level"),
        Index("ix_executive_intelligence_org_urgency", "organization_id", "urgency"),
        Index("ix_executive_intelligence_org_status", "organization_id", "status"),
    )