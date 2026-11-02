"""Optimization History model."""

from datetime import datetime
from typing import Optional
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class OptimizationHistory(Base, TimestampMixin):
    __tablename__ = "optimization_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    context_id: Mapped[str] = mapped_column(
        ForeignKey("optimization_contexts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    alternative_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("optimization_alternatives.id", ondelete="SET NULL"), index=True
    )
    action: Mapped[str] = mapped_column(String(60), nullable=False)  # created, evaluated, selected, rejected, implemented
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    predicted_outcome: Mapped[float] = mapped_column(default=0.0, nullable=False)
    actual_outcome: Mapped[Optional[float]] = mapped_column(default=None)
    score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    notes: Mapped[Optional[str]] = mapped_column(Text)
    performed_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    optimizationhistory_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_optimization_history_org_context", "organization_id", "context_id"),
        Index("ix_optimization_history_org_action", "organization_id", "action"),
        {"extend_existing": True},
    )