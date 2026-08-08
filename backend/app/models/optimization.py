"""Phase 19 — Optimization history (applied optimizations).

Records applied optimizations and their expected benefit. Distinct from the
Phase 18 optimization history table owned by ``OptimizationAction``.
"""

from typing import Any, Optional

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


class OptimizationHistory(Base, TimestampMixin):
    """Record of applied optimizations and their expected benefit."""

    __tablename__ = "optimization_records"
    __table_args__ = (
        Index("ix_optimization_records_org", "organization_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    recommendation_id: Mapped[Optional[str]] = mapped_column(String(32))
    expected_benefit: Mapped[Optional[str]] = mapped_column(String(255))
    savings: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="applied")
    applied_by: Mapped[Optional[str]] = mapped_column(String(32))
    applied_at: Mapped[Optional[Any]] = mapped_column(DateTime(timezone=True))
