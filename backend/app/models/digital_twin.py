"""Phase 18 — Autonomous Enterprise Intelligence & Organizational Digital Twin models.

Every organization gets one living Digital Twin. These tables persist the twin
itself, its state history, predictions, health records, decision history,
strategic forecasts and optimization history. Each row carries the standard
multi-tenancy columns so every insight is scoped to its organization and
traceable to underlying evidence.

Phase 8's executive tables (CompanyHealth, OrganizationSnapshot, Simulation,
ExecutiveRecommendation, StrategicRisk) remain the lightweight executive
layer; the tables here are the Phase 18 *living* model with state series,
explainable predictions and scenario simulations.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    JSON,
    Boolean,
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


class DigitalTwin(Base, TimestampMixin):
    """One living digital twin per organization (Phase 18.1).

    ``twin_json`` holds the full twin payload — entity counts, dimension
    summaries, and the current/historical/predicted state — as computed by
    the twin service. The twin is updated continuously by the twin worker and
    on demand through the API.
    """

    __tablename__ = "digital_twins"
    __table_args__ = (
        Index("ix_digital_twins_org", "organization_id"),
        UniqueConstraint("organization_id", name="uq_digital_twins_org"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    twin_json: Mapped[Optional[str]] = mapped_column(Text)  # full twin payload
    entity_counts_json: Mapped[Optional[str]] = mapped_column(Text)  # entity -> count
    dimensions_json: Mapped[Optional[str]] = mapped_column(Text)  # dimension -> summary
    state_json: Mapped[Optional[str]] = mapped_column(Text)  # current state model
    state_history_json: Mapped[Optional[str]] = mapped_column(Text)  # recent states
    predicted_state_json: Mapped[Optional[str]] = mapped_column(Text)  # 30d projection
    health_score: Mapped[Optional[float]] = mapped_column(Float)
    health_status: Mapped[Optional[str]] = mapped_column(String(20))
    refresh_count: Mapped[int] = mapped_column(Integer, default=0)
    last_refreshed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class TwinStateHistory(Base, TimestampMixin):
    """A historical state snapshot of the digital twin (Phase 18.2)."""

    __tablename__ = "twin_state_history"
    __table_args__ = (Index("ix_twin_state_history_org_time", "organization_id", "captured_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    state_json: Mapped[Optional[str]] = mapped_column(Text)
    summary_json: Mapped[Optional[str]] = mapped_column(Text)  # headline metrics at capture
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TwinPrediction(Base, TimestampMixin):
    """A proactive, explainable organizational prediction (Phase 18.4).

    Kinds: attrition | project_failure | budget_overrun | customer_churn |
    knowledge_loss | security_risk | burnout | compliance_risk | hiring_need |
    innovation_trend.
    """

    __tablename__ = "twin_predictions"
    __table_args__ = (
        Index("ix_twin_predictions_org_kind", "organization_id", "kind"),
        Index("ix_twin_predictions_status", "organization_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    probability: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    impact: Mapped[float] = mapped_column(Float, default=0.0)  # 0-100
    score: Mapped[float] = mapped_column(Float, default=0.0)  # probability * impact
    level: Mapped[str] = mapped_column(String(10), default="low")  # low | medium | high | critical
    horizon_days: Mapped[int] = mapped_column(Integer, default=30)
    subject_type: Mapped[Optional[str]] = mapped_column(String(40))  # project | employee | team | customer | organization
    subject_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    subject_name: Mapped[Optional[str]] = mapped_column(String(300))
    signals_json: Mapped[Optional[str]] = mapped_column(Text)  # explainable evidence chain
    recommended_action: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | acknowledged | dismissed | resolved
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    model_version: Mapped[str] = mapped_column(String(30), default="twin-v1")


class OrganizationHealthRecord(Base, TimestampMixin):
    """A unified health record for the organization (Phase 18.5).

    The health engine computes nine dimensions plus a unified score. Each
    refresh appends a new record so health trends are visible over time.
    """

    __tablename__ = "organization_health_records"
    __table_args__ = (Index("ix_org_health_org_time", "organization_id", "period"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Float, default=0.0)  # unified 0-100
    status: Mapped[str] = mapped_column(String(20), default="stable")  # excellent | good | watch | at_risk
    breakdown_json: Mapped[Optional[str]] = mapped_column(Text)  # dimension -> {score, status, drivers}
    period: Mapped[str] = mapped_column(String(40), index=True)  # e.g. 2026-08-07
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class DecisionRecord(Base, TimestampMixin):
    """A stored decision with reason, alternatives, evidence and lessons (Phase 18.7)."""

    __tablename__ = "decision_history"
    __table_args__ = (Index("ix_decision_history_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    decided_by: Mapped[Optional[str]] = mapped_column(String(300))
    category: Mapped[str] = mapped_column(String(40), default="strategy")  # strategy | hiring | budget | product | operations | expansion | risk
    decision: Mapped[str] = mapped_column(String(500), nullable=False)
    reason: Mapped[Optional[str]] = mapped_column(Text)
    alternatives_json: Mapped[Optional[str]] = mapped_column(Text)  # list[str]
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)  # evidence chain
    outcome: Mapped[Optional[str]] = mapped_column(Text)  # what happened after
    outcome_score: Mapped[Optional[float]] = mapped_column(Float)  # -100..100 success rating
    lessons_json: Mapped[Optional[str]] = mapped_column(Text)  # list[str]
    status: Mapped[str] = mapped_column(String(20), default="made")  # made | implemented | reviewed
    analyzed: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class StrategicForecast(Base, TimestampMixin):
    """A forecast for one organizational dimension (Phase 18.9).

    Dimensions: growth | hiring | revenue | knowledge | learning | projects |
    community | infrastructure | capacity.
    """

    __tablename__ = "strategic_forecasts"
    __table_args__ = (
        Index("ix_strategic_forecasts_org_dim", "organization_id", "dimension"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    dimension: Mapped[str] = mapped_column(String(40), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, default=90)
    series_json: Mapped[Optional[str]] = mapped_column(Text)  # [{date, value}] projection
    summary: Mapped[Optional[str]] = mapped_column(Text)
    confidence: Mapped[float] = mapped_column(Float, default=0.7)
    drivers_json: Mapped[Optional[str]] = mapped_column(Text)  # evidence driving the trend
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class OptimizationAction(Base, TimestampMixin):
    """An optimization suggestion produced by the optimization engine (Phase 18.12).

    Kinds: restructuring | reassignment | expert_allocation | meeting_reduction |
    workflow_simplification | automation.
    """

    __tablename__ = "optimization_history"
    __table_args__ = (Index("ix_optimization_history_org", "organization_id"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    rationale: Mapped[Optional[str]] = mapped_column(Text)
    impact: Mapped[str] = mapped_column(String(20), default="medium")  # high | medium | low
    effort: Mapped[str] = mapped_column(String(20), default="medium")  # low | medium | high
    expected_gain: Mapped[Optional[float]] = mapped_column(Float)  # e.g. hours saved / month
    evidence_json: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="suggested")  # suggested | applied | dismissed
    applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
