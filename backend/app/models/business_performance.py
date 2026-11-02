"""Business Performance models."""

from datetime import datetime, date
from typing import Optional, List
from sqlalchemy import Date, DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Float, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class BusinessDriver(Base, TimestampMixin):
    __tablename__ = "business_drivers"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    driver_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    category: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    target_direction: Mapped[str] = mapped_column(String(20), default="increase", nullable=False)
    weight: Mapped[float] = mapped_column(default=1.0, nullable=False)
    formula: Mapped[Optional[str]] = mapped_column(Text)
    data_source: Mapped[Optional[str]] = mapped_column(String(200))
    update_frequency: Mapped[str] = mapped_column(String(24), default="monthly", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    businessdriver_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_business_drivers_org_name"),
        Index("ix_business_drivers_org_category", "organization_id", "category"),
    )


class BusinessForecast(Base, TimestampMixin):
    __tablename__ = "business_forecasts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    forecast_type: Mapped[str] = mapped_column(String(40), default="revenue", nullable=False)
    metric_name: Mapped[str] = mapped_column(String(200), nullable=False)
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    predicted_value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    lower_bound: Mapped[Optional[float]] = mapped_column(default=None)
    upper_bound: Mapped[Optional[float]] = mapped_column(default=None)
    confidence_level: Mapped[float] = mapped_column(default=0.95, nullable=False)
    model_name: Mapped[str] = mapped_column(String(100), default="auto", nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), default="1.0", nullable=False)
    features_used: Mapped[List[str]] = mapped_column(JSON, default=list)
    actual_value: Mapped[Optional[float]] = mapped_column(default=None)
    actual_recorded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    accuracy: Mapped[Optional[float]] = mapped_column(default=None)
    businessdriver_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_business_forecasts_org_type", "organization_id", "forecast_type"),
        Index("ix_business_forecasts_org_period", "organization_id", "period_start", "period_end"),
    )


class BusinessMetric(Base, TimestampMixin):
    __tablename__ = "business_metrics"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    metric_type: Mapped[str] = mapped_column(String(40), default="kpi", nullable=False)
    category: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    target_direction: Mapped[str] = mapped_column(String(20), default="increase", nullable=False)
    current_value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    target_value: Mapped[Optional[float]] = mapped_column(default=None)
    previous_value: Mapped[Optional[float]] = mapped_column(default=None)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    frequency: Mapped[str] = mapped_column(String(24), default="monthly", nullable=False)
    data_source: Mapped[Optional[str]] = mapped_column(String(200))
    formula: Mapped[Optional[str]] = mapped_column(Text)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"), index=True)
    department_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    businessdriver_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="uq_business_metrics_org_name"),
        Index("ix_business_metrics_org_category", "organization_id", "category"),
    )


class BusinessMetricObservation(Base, TimestampMixin):
    __tablename__ = "business_metric_observations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        ForeignKey("business_metrics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    period_start: Mapped[Optional[date]] = mapped_column(Date)
    period_end: Mapped[Optional[date]] = mapped_column(Date)
    source: Mapped[str] = mapped_column(String(60), default="manual", nullable=False)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict)
    businessdriver_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_business_metric_obs_metric_time", "metric_id", "recorded_at"),
        Index("ix_business_metric_obs_org_time", "organization_id", "recorded_at"),
    )


class BusinessPerformanceHistory(Base, TimestampMixin):
    __tablename__ = "business_performance_history"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    period_start: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    period_type: Mapped[str] = mapped_column(String(24), default="monthly", nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    top_drivers: Mapped[List[dict]] = mapped_column(JSON, default=list)
    anomalies: Mapped[List[dict]] = mapped_column(JSON, default=list)
    insights: Mapped[List[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        UniqueConstraint("organization_id", "period_start", "period_end", name="uq_biz_perf_hist_org_period"),
        Index("ix_biz_perf_hist_org_period", "organization_id", "period_start"),
    )


class BusinessPerformanceLink(Base, TimestampMixin):
    __tablename__ = "business_performance_links"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    driver_id: Mapped[str] = mapped_column(
        ForeignKey("business_drivers.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        ForeignKey("business_metrics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(40), default="influences", nullable=False)
    strength: Mapped[float] = mapped_column(default=1.0, nullable=False)
    lag_periods: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    evidence: Mapped[List[str]] = mapped_column(JSON, default=list)

    __table_args__ = (
        UniqueConstraint("driver_id", "metric_id", name="uq_biz_perf_links_driver_metric"),
        Index("ix_biz_perf_links_org_driver", "organization_id", "driver_id"),
    )


class BusinessPerformanceSnapshot(Base, TimestampMixin):
    __tablename__ = "business_performance_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    snapshot_type: Mapped[str] = mapped_column(String(24), default="monthly", nullable=False)
    overall_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    drivers: Mapped[dict] = mapped_column(JSON, default=dict)
    trends: Mapped[dict] = mapped_column(JSON, default=dict)
    alerts: Mapped[List[str]] = mapped_column(JSON, default=list)
    businessdriver_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "snapshot_date", name="uq_biz_perf_snapshots_org_date"),
        Index("ix_biz_perf_snapshots_org_date", "organization_id", "snapshot_date"),
    )


class BusinessTarget(Base, TimestampMixin):
    __tablename__ = "business_targets"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        ForeignKey("business_metrics.id", ondelete="CASCADE"), index=True, nullable=False
    )
    target_name: Mapped[str] = mapped_column(String(300), nullable=False)
    target_value: Mapped[float] = mapped_column(default=0.0, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    target_type: Mapped[str] = mapped_column(String(24), default="absolute", nullable=False)
    baseline_value: Mapped[Optional[float]] = mapped_column(default=None)
    owner_id: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(24), default="active", nullable=False)
    achieved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    businessdriver_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_business_targets_org_metric", "organization_id", "metric_id"),
        Index("ix_business_targets_org_status", "organization_id", "status"),
    )


# Constants
DRIVER_TYPES = (
    "revenue",
    "cost",
    "efficiency",
    "quality",
    "customer_satisfaction",
    "employee_engagement",
    "innovation",
    "compliance",
    "risk",
    "growth",
)

DRIVER_DIRECTIONS = ("increase", "decrease", "maintain")

DRIVER_STRENGTHS = ("weak", "moderate", "strong", "critical")

COMPUTE_MODES = ("average", "weighted", "median", "latest", "trend")

FORECAST_TYPES = ("linear", "exponential", "seasonal", "prophet", "arima")

HEALTH_STATES = ("healthy", "concerned", "at_risk", "critical")

LINK_KINDS = (
    "driver_to_metric",
    "metric_to_forecast",
    "forecast_to_target",
    "driver_to_target",
    "causal",
    "correlation",
)

METRIC_CATEGORIES = (
    "financial",
    "operational",
    "customer",
    "employee",
    "product",
    "market",
    "strategic",
)

METRIC_DIRECTIONS = ("higher_better", "lower_better", "target_range")

METRIC_STATUSES = ("on_track", "at_risk", "off_track", "exceeding")

OBSERVATION_LABELS = ("actual", "projected", "target", "baseline")

OBSERVATION_SOURCES = ("system", "manual", "integration", "calculation")

EPISTEMIC_STATUSES = ("observed", "inferred", "predicted", "proposed", "contested")

LINEAGE_RELATIONS = ("derived_from", "depends_on", "influences", "validates", "contradicts")

VARIANCE_DIRECTIONS = ("positive", "negative", "neutral")

CAUSE_CANDIDATE_STATUS = ("identified", "investigating", "confirmed", "ruled_out")

HEALTH_DIMENSIONS = (
    "financial",
    "operational",
    "customer",
    "employee",
    "strategic",
    "compliance",
)

DECISION_CONTEXT_SECTIONS = (
    "rationale",
    "evidence",
    "alternatives",
    "impact_assessment",
    "risk_assessment",
    "constraints",
)

DECISION_STATES = ("proposed", "under_review", "approved", "implemented", "cancelled")

IMPACT_SHAPES = ("linear", "exponential", "step", "s_curve", "custom")

METRIC_GRANULARITIES = ("daily", "weekly", "monthly", "quarterly", "yearly")

METRIC_KINDS = (
    "revenue",
    "cost",
    "profit",
    "margin",
    "growth",
    "efficiency",
    "quality",
    "satisfaction",
    "engagement",
    "retention",
    "acquisition",
    "conversion",
    "churn",
    "ltv",
    "cac",
    "nps",
    "csat",
    "employee_count",
    "headcount",
    "turnover",
    "productivity",
    "utilization",
    "capacity",
    "velocity",
    "throughput",
    "cycle_time",
    "lead_time",
    "defect_rate",
    "availability",
    "latency",
    "throughput",
    "error_rate",
)

METRIC_VISIBILITIES = ("public", "internal", "private", "restricted")

SNAPSHOT_SCOPES = ("organization", "department", "team", "project", "individual")

TARGET_BELIEFS = ("must_hit", "should_hit", "stretch", "aspirational")

TARGET_STATUSES = ("active", "achieved", "missed", "abandoned", "at_risk", "on_track")