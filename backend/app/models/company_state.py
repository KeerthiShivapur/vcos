"""Phase 19 — Company state (live awareness snapshot) and organization metrics."""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class CompanyState(Base, TimestampMixin):
    """A point-in-time live state of the company (what VCOS always knows)."""

    __tablename__ = "company_state"
    __table_args__ = (
        Index("ix_company_state_org_time", "organization_id", "snapshot_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    state: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(40), default="awareness")
    snapshot_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))


class OrganizationMetric(Base, TimestampMixin):
    """Materialized organizational metrics for analytics and trend tracking."""

    __tablename__ = "org_metrics"
    __table_args__ = (
        Index("ix_org_metrics_org_name_period", "organization_id", "name", "period"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    period: Mapped[str] = mapped_column(String(20), default="daily")
    source: Mapped[Optional[str]] = mapped_column(String(60))
    recorded_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
