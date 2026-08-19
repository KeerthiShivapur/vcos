"""Slice 4G.6 — Commercial & Business Performance Intelligence models.

The canonical business-performance ledger of the organization: which business
metrics matter, the observations that ground them, the targets the company
commits to, the forecasts that bound expectations, the drivers that move
things, and the multidimensional performance snapshots that tie it all to
strategy (4G.3), capacity/demand (4G.4), customer intelligence (4G.5),
projects, decisions and people.

Every connection is stated in deterministic language — linked to / strongly
associated with / evidence indicates / likely contributor — never invented
certainty, and every number is a deterministic function of the SAME canonical
ledger the platform already maintains. Every write is an exact-once,
change-driven reaction to a durable business event, so replays converge.

The engine is advisory-only and universal: one canonical model for every
company size (5 to 50,000+ people), with org-wide / business-unit / project
scopes — never a separate model per company size.
"""

from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid

# --- canonical vocabularies ------------------------------------------------

# Metric domains. A small canonical set so aggregation across orgs and
# business units stays meaningful at any company size.
METRIC_KINDS: tuple[str, ...] = (
    "revenue", "growth", "retention", "churn", "expansion",
    "efficiency", "quality", "satisfaction", "utilization",
    "delivery", "adoption", "engagement", "cost", "health",
    "security", "other",
)
# Which direction is good for the business — the basis of every trend call.
METRIC_DIRECTIONS = ("up_is_good", "down_is_good")
METRIC_STATUSES = ("active", "retired")
METRIC_VISIBILITIES = ("public", "internal", "restricted")
# Natural reporting cadence of a metric.
METRIC_GRANULARITIES = ("daily", "weekly", "monthly", "quarterly", "yearly")
# Quantitative nature of an observation: actuals vs expectations.
OBSERVATION_LABELS = ("actual", "forecast", "plan", "target", "estimated", "other")
# Provider-neutral observation origins.
OBSERVATION_SOURCES = (
    "manual", "survey", "export", "crm", "system",
    "measurement", "financial", "customer", "operator", "other",
)
# Driver taxonomy: what moves a business metric.
DRIVER_TYPES = (
    "customer", "market", "operational", "economic",
    "competitive", "opportunity", "risk",
)
# How much evidence grounds the driver.
DRIVER_STRENGTHS = ("strong", "moderate", "evidence_limited")
DRIVER_DIRECTIONS = ("toward", "away")
# The shape of a driver's measurable impact.
IMPACT_SHAPES = ("attribute", "aggregation", "portfolio")
# Target lifecycle. delivered/missed close a target; the others are live.
TARGET_STATUSES = ("pending", "on_track", "at_risk", "slipped", "delivered", "missed")
# Belief of attainment — the target's own honesty control.
TARGET_BELIEFS = ("certain", "likely", "plausible", "uncertain")
FORECAST_TYPES = ("conservative", "base", "optimistic")
# Where a snapshot looks (org-wide, one business unit, one project).
SNAPSHOT_SCOPES = ("org_wide", "business_unit", "project")
# How the snapshot's numbers were produced — projection bases must be labeled.
COMPUTE_MODES = ("observed", "derived", "projected", "scenario")
# Multidimensional health state vocabulary (same as customer health 4G.5).
HEALTH_STATES = ("healthy", "concerned", "at_risk")
# The deterministic link language. Machine keys; the engine maps them to the
# canonical phrases ("linked to", "strongly associated with",
# "evidence indicates", "likely contributor") when served.
LINK_KINDS = (
    "linked_to",
    "strongly_associated_with",
    "evidence_indicates",
    "likely_contributor",
)
# Canonical business-health dimensions evaluated per snapshot.
HEALTH_DIMENSIONS: tuple[str, ...] = (
    "growth", "customers", "execution", "strategy", "capacity",
    "operations", "innovation", "financial",
)


class BusinessMetric(Base, TimestampMixin):
    """One canonical business metric — the unit of business measurement.

    Universally defined: kind, direction, unit and visibility are canonical
    so the same metric key aggregates across any company size. The metric is
    the anchor for observations, targets, forecasts, drivers and links.
    """

    __tablename__ = "business_metrics"
    __table_args__ = (
        # one live metric per key; updates mutate the live row, and replays
        # of created/updated events converge through the engine's existence
        # check (exact-once is enforced there and on observation rows)
        UniqueConstraint("organization_id", "key", name="uq_bm_metric_key"),
        Index("ix_bm_org", "organization_id"),
        Index("ix_bm_org_kind", "organization_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # canonical metric key, e.g. "recurring_revenue" / "customer_churn"
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(Text)
    # revenue | growth | retention | churn | expansion | efficiency | quality |
    # satisfaction | utilization | delivery | adoption | engagement | cost | health | security | other
    kind: Mapped[str] = mapped_column(String(40), nullable=False, default="other")
    # up_is_good | down_is_good
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="up_is_good")
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    # public | internal | restricted
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="internal")
    # daily | weekly | monthly | quarterly | yearly
    period_granularity: Mapped[str] = mapped_column(String(16), nullable=False, default="monthly")
    # org_wide | business_unit | project
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="org_wide")
    # business-unit or project id when the metric is scoped
    scope_entity_id: Mapped[Optional[str]] = mapped_column(String(32))
    last_value: Mapped[Optional[float]] = mapped_column(Float)
    last_observed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class BusinessMetricObservation(Base, TimestampMixin):
    """One observed value of a business metric.

    The grounding unit of performance intelligence: an actual/plan/forecast
    number with its source and provenance (e.g. the customer outcome event
    that produced it). Exact-once on (org, metric, observed_at, source event)
    so replays never double-count history.
    """

    __tablename__ = "business_metric_observations"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "metric_id", "observed_at", "source_event_id",
            name="uq_bmo_exact_once",
        ),
        Index("ix_bmo_org_metric_time", "organization_id", "metric_id", "observed_at"),
        Index("ix_bmo_org_time", "organization_id", "observed_at"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        ForeignKey("business_metrics.id", ondelete="CASCADE"), nullable=False
    )
    value: Mapped[float] = mapped_column(Float, nullable=False)
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    # actual | forecast | plan | target | estimated | other
    label: Mapped[str] = mapped_column(String(16), nullable=False, default="actual")
    # manual | survey | export | crm | system | measurement | financial |
    # customer | operator | other
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="manual")
    # where the number came from, e.g. "customer.outcome.recorded:abc123"
    provenance: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    note: Mapped[Optional[str]] = mapped_column(Text)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class BusinessDriver(Base, TimestampMixin):
    """One driver of business performance — why a metric moves.

    A driver carries its evidence honestly: strength (strong / moderate /
    evidence_limited), direction, the metric keys it is observed against, and
    a bounded monetized estimate when evidence allows. Never presented as
    causation — always as a deterministic, evidence-backed association.
    """

    __tablename__ = "business_drivers"
    __table_args__ = (
        # one live driver per key; updates mutate the live row and replays
        # converge through the engine's existence check
        UniqueConstraint("organization_id", "key", name="uq_bd_driver_key"),
        Index("ix_bd_org", "organization_id"),
        Index("ix_bd_org_type", "organization_id", "driver_type"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(Text)
    # customer | market | operational | economic | competitive | opportunity | risk
    driver_type: Mapped[str] = mapped_column(String(24), nullable=False, default="market")
    # strong | moderate | evidence_limited
    strength: Mapped[str] = mapped_column(String(20), nullable=False, default="moderate")
    # toward (improves) | away (hurts)
    direction: Mapped[str] = mapped_column(String(12), nullable=False, default="toward")
    # attribute | aggregation | portfolio
    impact_shape: Mapped[str] = mapped_column(String(16), nullable=False, default="attribute")
    # canonical metric keys this driver is observed against
    metric_keys_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # bounded monetized estimate per period when evidence allows (never a guess)
    monetized_impact: Mapped[Optional[float]] = mapped_column(Float)
    # e.g. "strongly_associated_with recurring_revenue"
    relation_summary: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # linked entities: [{"entity_type": "customer", "entity_id": "..."}]
    linked_entities_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class BusinessTarget(Base, TimestampMixin):
    """One committed business target on a metric.

    The target connects strategy to measurement: the metric, the numeric
    commitment, its timeline and periods, the belief of attainment (honest),
    the owner, and the supporting initiatives / dependencies / open decisions
    that strategy (4G.3) and coordination (4G.2) surfaced. Status transitions
    are governed writes (pending -> on_track / at_risk / slipped -> delivered
    / missed) that publish business.target.updated.
    """

    __tablename__ = "business_targets"
    __table_args__ = (
        # one live target per (metric, period); replays converge through the
        # engine's existence check
        UniqueConstraint(
            "organization_id", "metric_id", "period_label",
            name="uq_bt_live",
        ),
        Index("ix_bt_org_metric", "organization_id", "metric_id"),
        Index("ix_bt_org_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        ForeignKey("business_metrics.id", ondelete="CASCADE"), nullable=False
    )
    metric_label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False, default="")
    start_at: Mapped[Optional[date]] = mapped_column(Date)
    end_at: Mapped[date] = mapped_column(Date, nullable=False)
    period_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    # pending | on_track | at_risk | slipped | delivered | missed
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    # certain | likely | plausible | uncertain
    belief: Mapped[str] = mapped_column(String(16), nullable=False, default="plausible")
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    owner_label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # supporting initiatives (labels) from 4G.3 strategy
    initiative_labels_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # supporting dependency labels from 4G.2 coordination
    dependency_labels_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # open decisions that gate attainment
    open_decisions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # linked strategy node label when declared
    strategy_label: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # linked project labels when declared
    project_labels_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # period-by-period expected values: [{"period": "...", "expected": 100}]
    periods_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # review trail: [{"at": "...", "note": "..."}]
    reviews_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class BusinessForecast(Base, TimestampMixin):
    """One bounded forecast of a business metric.

    Conservative / base / optimistic arcs over a horizon, each with its basis
    (the evidence it was derived from), required conditions and risk factors.
    A forecast is projected knowledge — always labeled as such, never
    presented as observed fact.
    """

    __tablename__ = "business_forecasts"
    __table_args__ = (
        # one live forecast per (metric, horizon, type); replays converge
        # through the engine's existence check
        UniqueConstraint(
            "organization_id", "metric_id", "horizon_label", "forecast_type",
            name="uq_bf_live",
        ),
        Index("ix_bf_org_metric", "organization_id", "metric_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    metric_id: Mapped[str] = mapped_column(
        ForeignKey("business_metrics.id", ondelete="CASCADE"), nullable=False
    )
    metric_label: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    # conservative | base | optimistic
    forecast_type: Mapped[str] = mapped_column(String(16), nullable=False, default="base")
    horizon_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    # the evidence the forecast is derived from
    basis: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    # [{"period": "...", "low": ..., "mid": ..., "high": ...}]
    path_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    low_value: Mapped[Optional[float]] = mapped_column(Float)
    midpoint_value: Mapped[Optional[float]] = mapped_column(Float)
    high_value: Mapped[Optional[float]] = mapped_column(Float)
    # 0..1 confidence with its basis
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    confidence_basis: Mapped[str] = mapped_column(String(300), nullable=False, default="")
    required_conditions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    risk_factors_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    last_observed_value: Mapped[Optional[float]] = mapped_column(Float)
    # implied per-period growth rate that produced the arc
    growth_rate: Mapped[Optional[float]] = mapped_column(Float)
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class BusinessPerformanceSnapshot(Base, TimestampMixin):
    """The CURRENT evidence-backed performance assessment of a scope.

    Multidimensional health (one explainable state per dimension — the why is
    always carried), metric trajectories with direction-aware trends, driver
    associations, monetized gains/losses and a summary narrative. The compute
    mode labels how the numbers were produced (observed / derived / projected
    / scenario). The temporal trail lives in BusinessPerformanceHistory.
    """

    __tablename__ = "business_performance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scope", "scope_entity_id", "period_label",
            "compute_mode", "source_event_id",
            name="uq_bps_exact_once",
        ),
        Index(
            "ix_bps_org_scope_time",
            "organization_id", "scope", "scope_entity_id", "period_label",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # org_wide | business_unit | project
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="org_wide")
    # business-unit or project id when scoped
    scope_entity_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    # observed | derived | projected | scenario
    compute_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="observed")
    period_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # healthy | concerned | at_risk
    health_state: Mapped[str] = mapped_column(String(12), nullable=False, default="concerned")
    # [{"key","label","score","state","reasons","positives","top_metrics","evidence_count","updated_at"}]
    health_dimensions_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # [{"metric_key","label","trend","delta","unit","direction"}]
    metric_trajectories_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # driver associations: [{"driver_key","title","strength","direction","kind"}]
    driver_links_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # monetized gains/losses: [{"label","delta","unit","monetized","direction","confidence"}]
    gains_losses_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    # cross-slice links: business/strategy/projects/customer/people/capacity
    links_json: Mapped[Optional[list[Any]]] = mapped_column(JSON, default=list)
    summary_narrative: Mapped[str] = mapped_column(Text, nullable=False, default="")
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    event_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)


class BusinessPerformanceHistory(Base, TimestampMixin):
    """Append-only temporal trail of performance assessments.

    One row per snapshot-computing event (exact-once on the source event),
    so "how did the organisation's performance change" stays answerable over
    any period — the org-wide performance audit trail.
    """

    __tablename__ = "business_performance_history"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "scope", "scope_entity_id", "period_label",
            "compute_mode", "source_event_id",
            name="uq_bph_exact_once",
        ),
        Index(
            "ix_bph_org_scope_time",
            "organization_id", "scope", "scope_entity_id", "occurred_at",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    scope: Mapped[str] = mapped_column(String(16), nullable=False, default="org_wide")
    scope_entity_id: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    compute_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="observed")
    period_label: Mapped[str] = mapped_column(String(80), nullable=False, default="")
    health_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health_state: Mapped[str] = mapped_column(String(12), nullable=False, default="concerned")
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    event_name: Mapped[str] = mapped_column(String(60), nullable=False, default="")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class BusinessPerformanceLink(Base, TimestampMixin):
    """One evidence-weighted connection from business performance to reality.

    Links a performance entity (metric / driver / target / snapshot) to a
    strategy node, project, customer, person, capacity surface or decision —
    with a deterministic linkage kind (linked to / strongly associated with /
    evidence indicates / likely contributor), weight, and the reasoning that
    produced the connection.
    """

    __tablename__ = "business_performance_links"
    __table_args__ = (
        UniqueConstraint(
            "organization_id", "entity_type", "entity_id",
            "target_type", "target_id", "kind", "source_event_id",
            name="uq_bpl_exact_once",
        ),
        Index("ix_bpl_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_bpl_org_target", "organization_id", "target_type", "target_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    # business_metric | business_driver | business_target | business_performance_snapshot
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # strategy_goal | company_objective | company_initiative | project |
    # customer | person | capacity | decision | business_metric | ...
    target_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # linked_to | strongly_associated_with | evidence_indicates | likely_contributor
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    # 0..1 evidence weight
    weight: Mapped[float] = mapped_column(Float, default=0.5)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    reasoning: Mapped[str] = mapped_column(String(400), nullable=False, default="")
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="engine")
    source_event_id: Mapped[str] = mapped_column(String(32), nullable=False)