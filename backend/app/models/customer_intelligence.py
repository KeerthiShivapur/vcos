"""Customer Intelligence models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class CustomerCommitment(Base, TimestampMixin):
    __tablename__ = "customer_commitments"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    commitment_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    value_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    value_amount: Mapped[Optional[float]] = mapped_column(default=None)
    start_date: Mapped[Optional[date]] = mapped_column(Date)
    end_date: Mapped[Optional[date]] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    probability: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    customercommitment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_customer_commitments_org_customer", "organization_id", "customer_id"),
        Index("ix_customer_commitments_org_status", "organization_id", "status"),
    )


class CustomerHealthHistory(Base, TimestampMixin):
    __tablename__ = "customer_health_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    health_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    health_status: Mapped[str] = mapped_column(String(24), default="good", nullable=False)
    factors: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_factors: Mapped[List[str]] = mapped_column(JSON, default=list)
    positive_signals: Mapped[List[str]] = mapped_column(JSON, default=list)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        Index("ix_customer_health_history_org_customer", "organization_id", "customer_id"),
        Index("ix_customer_health_history_org_time", "organization_id", "recorded_at"),
    )


class CustomerHealthRow(Base, TimestampMixin):
    __tablename__ = "customer_health_rows"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    metric_name: Mapped[str] = mapped_column(String(100), nullable=False)
    metric_value: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    target_value: Mapped[Optional[float]] = mapped_column(default=None)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    status: Mapped[str] = mapped_column(String(24), default="on_track", nullable=False)
    trend: Mapped[str] = mapped_column(String(20), default="stable", nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    __table_args__ = (
        UniqueConstraint("customer_id", "metric_name", "recorded_at", name="uq_customer_health_rows_unique"),
        Index("ix_customer_health_rows_org_customer", "organization_id", "customer_id"),
    )


class CustomerOutcome(Base, TimestampMixin):
    __tablename__ = "customer_outcomes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    outcome_type: Mapped[str] = mapped_column(String(40), nullable=False)
    outcome_value: Mapped[Optional[float]] = mapped_column(default=None)
    outcome_currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    outcome_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    probability: Mapped[float] = mapped_column(default=0.0, nullable=False)
    contributing_factors: Mapped[List[str]] = mapped_column(JSON, default=list)
    customercommitment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_customer_outcomes_org_customer", "organization_id", "customer_id"),
        Index("ix_customer_outcomes_org_type", "organization_id", "outcome_type"),
    )


class CustomerSignal(Base, TimestampMixin):
    __tablename__ = "customer_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    signal_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[Optional[float]] = mapped_column(default=None)
    threshold: Mapped[Optional[float]] = mapped_column(default=None)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    customercommitment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_customer_signals_org_customer", "organization_id", "customer_id"),
        Index("ix_customer_signals_org_type", "organization_id", "signal_type"),
        Index("ix_customer_signals_org_active", "organization_id", "is_active"),
    )


class CustomerTheme(Base, TimestampMixin):
    __tablename__ = "customer_themes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    theme: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    customer_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    sentiment: Mapped[str] = mapped_column(String(20), default="neutral", nullable=False)
    frequency: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    trend: Mapped[str] = mapped_column(String(20), default="stable", nullable=False)
    first_detected: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    related_signals: Mapped[List[str]] = mapped_column(JSON, default=list)
    customercommitment_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_customer_themes_org_status", "organization_id", "status"),
        Index("ix_customer_themes_org_sentiment", "organization_id", "sentiment"),
    )