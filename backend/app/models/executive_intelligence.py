"""Phase 20 — Executive Intelligence snapshots.

The executive intelligence layer captures the company brain's understanding
of the organization at a point in time: current state, health, opportunities,
risks, knowledge growth, innovation, customer trends, engagement, learning
progress and executive priorities — as one connected intelligence snapshot.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class ExecutiveIntelligence(Base, TimestampMixin):
    """One company-brain intelligence snapshot (Phase 20.2 / 20.15)."""

    __tablename__ = "executive_intelligence"
    __table_args__ = (
        Index("ix_exec_intel_org_period", "organization_id", "period"),
        Index("ix_exec_intel_org_generated", "organization_id", "generated_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # daily | weekly | monthly | quarterly | on_demand
    period: Mapped[str] = mapped_column(String(20), default="on_demand")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[Optional[str]] = mapped_column(Text)
    # {"health": {...}, "opportunities": [...], "risks": [...], "changes": [...],
    #  "knowledge": {...}, "learning": {...}, "customers": {...}, "priorities": [...]}
    sections: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    health_score: Mapped[float] = mapped_column(Float, default=0.0)
    intelligence_score: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(120), default="kernel.intelligence")
    generated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
