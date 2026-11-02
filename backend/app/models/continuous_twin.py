"""Continuous Twin models for digital twin synchronization."""

from datetime import datetime, date
from typing import Optional, List, Any
from sqlalchemy import DateTime, ForeignKey, String, Text, JSON, Boolean, Index, UniqueConstraint, Integer, Date
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, gen_uuid


class CompanyStateSnapshot(Base, TimestampMixin):
    __tablename__ = "company_state_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    snapshot_type: Mapped[str] = mapped_column(String(40), default="full", nullable=False)  # full, incremental, milestone
    state_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    state_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    previous_snapshot_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("company_state_snapshots.id", ondelete="SET NULL"), index=True
    )
    entities_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    changes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_baseline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_state_snapshots_org_time", "organization_id", "created_at"),
    )


class CompanyStateDimension(Base, TimestampMixin):
    __tablename__ = "company_state_dimensions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dimension_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    dimension_type: Mapped[str] = mapped_column(String(40), nullable=False)  # metric, status, configuration, relationship
    current_value: Mapped[Any] = mapped_column(JSON, nullable=False)
    previous_value: Mapped[Optional[Any]] = mapped_column(JSON)
    unit: Mapped[Optional[str]] = mapped_column(String(50))
    trend: Mapped[str] = mapped_column(String(20), default="stable", nullable=False)  # increasing, decreasing, stable, volatile
    change_rate: Mapped[float] = mapped_column(default=0.0, nullable=False)
    last_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "dimension_name", name="uq_company_state_dim_org_name"),
        Index("ix_company_state_dim_org_type", "organization_id", "dimension_type"),
    )


class TwinStateSnapshot(Base, TimestampMixin):
    __tablename__ = "twin_state_snapshots"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    twin_type: Mapped[str] = mapped_column(String(40), default="digital_twin", nullable=False)
    snapshot_id: Mapped[str] = mapped_column(
        ForeignKey("company_state_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    state_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    is_consistent: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    consistency_score: Mapped[float] = mapped_column(default=1.0, nullable=False)
    discrepancies: Mapped[List[dict]] = mapped_column(JSON, default=list)
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_twin_state_snapshots_org", "organization_id"),
        Index("ix_twin_state_snapshots_snapshot", "snapshot_id"),
    )


class TwinSynchronizationLog(Base, TimestampMixin):
    __tablename__ = "twin_synchronization_logs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sync_type: Mapped[str] = mapped_column(String(40), default="full", nullable=False)  # full, incremental, partial, on_demand
    trigger: Mapped[str] = mapped_column(String(40), default="scheduled", nullable=False)  # scheduled, event_driven, manual, api
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, running, completed, failed, partial
    entities_synced: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    entities_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    triggered_by: Mapped[Optional[str]] = mapped_column(String(32))  # user_id or system
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_twin_sync_logs_org_status", "organization_id", "status"),
        Index("ix_twin_sync_logs_org_time", "organization_id", "started_at"),
    )


class PredictionCalibration(Base, TimestampMixin):
    __tablename__ = "prediction_calibrations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    prediction_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    calibration_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    calibration_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    predictions_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    actual_outcomes_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    accuracy: Mapped[float] = mapped_column(default=0.0, nullable=False)
    precision: Mapped[float] = mapped_column(default=0.0, nullable=False)
    recall: Mapped[float] = mapped_column(default=0.0, nullable=False)
    f1_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    calibration_error: Mapped[float] = mapped_column(default=0.0, nullable=False)
    brier_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    reliability_diagram: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_prediction_calibrations_org_model", "organization_id", "model_id"),
        Index("ix_prediction_calibrations_org_type", "organization_id", "prediction_type"),
    )


class OptimizationContext(Base, TimestampMixin):
    __tablename__ = "optimization_contexts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    context_name: Mapped[str] = mapped_column(String(200), nullable=False)
    context_type: Mapped[str] = mapped_column(String(40), default="general", nullable=False)  # resource_allocation, scheduling, budget, hiring
    objective: Mapped[str] = mapped_column(String(100), nullable=False)
    objective_type: Mapped[str] = mapped_column(String(40), default="maximize", nullable=False)  # maximize, minimize, target
    target_value: Mapped[Optional[float]] = mapped_column(default=None)
    constraints: Mapped[List[dict]] = mapped_column(JSON, default=list)
    variables: Mapped[List[dict]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)  # draft, active, running, completed, archived
    current_value: Mapped[Optional[float]] = mapped_column(default=None)
    best_value: Mapped[Optional[float]] = mapped_column(default=None)
    iterations: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_optimization_contexts_org_status", "organization_id", "status"),
        Index("ix_optimization_contexts_org_type", "organization_id", "context_type"),
    )


class OptimizationAlternative(Base, TimestampMixin):
    __tablename__ = "optimization_alternatives"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    context_id: Mapped[str] = mapped_column(
        ForeignKey("optimization_contexts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    predicted_outcome: Mapped[float] = mapped_column(default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    rank: Mapped[Optional[int]] = mapped_column(Integer)
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    evaluated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_optimization_alts_context", "context_id"),
        Index("ix_optimization_alts_org_rank", "organization_id", "rank"),
    )


class LearningSignal(Base, TimestampMixin):
    __tablename__ = "learning_signals"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    signal_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)  # pattern, anomaly, trend, correlation, prediction
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)  # metric, event, prediction, user_feedback, system
    source_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    signal_strength: Mapped[float] = mapped_column(default=0.0, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    related_entities: Mapped[List[dict]] = mapped_column(JSON, default=list)
    action_taken: Mapped[Optional[str]] = mapped_column(Text)
    action_outcome: Mapped[Optional[str]] = mapped_column(Text)
    is_actionable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_learning_signals_org_type", "organization_id", "signal_type"),
        Index("ix_learning_signals_org_strength", "organization_id", "signal_strength"),
        Index("ix_learning_signals_org_time", "organization_id", "created_at"),
    )


class ContinuousLearningSession(Base, TimestampMixin):
    __tablename__ = "continuous_learning_sessions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    session_type: Mapped[str] = mapped_column(String(40), default="batch", nullable=False)  # batch, incremental, online, reinforcement
    model_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    training_data_period_start: Mapped[date] = mapped_column(Date, nullable=False)
    training_data_period_end: Mapped[date] = mapped_column(Date, nullable=False)
    samples_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    features_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    epochs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    final_loss: Mapped[Optional[float]] = mapped_column(default=None)
    validation_metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    model_versions_before: Mapped[dict] = mapped_column(JSON, default=dict)
    model_versions_after: Mapped[dict] = mapped_column(JSON, default=dict)
    drift_detected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    drift_details: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    triggered_by: Mapped[str] = mapped_column(String(40), default="scheduled", nullable=False)  # scheduled, drift_detected, manual, threshold
    status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, running, completed, failed
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    __table_args__ = (
        Index("ix_learning_sessions_org_status", "organization_id", "status"),
        Index("ix_learning_sessions_org_time", "organization_id", "started_at"),
    )


class InstitutionalMemoryEntry(Base, TimestampMixin):
    __tablename__ = "institutional_memory_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entry_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # lesson, decision, pattern, anti-pattern, best_practice
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[List[str]] = mapped_column(JSON, default=list)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), nullable=False)  # project, incident, retrospective, decision, experiment
    source_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    applicable_contexts: Mapped[List[dict]] = mapped_column(JSON, default=list)
    related_entries: Mapped[List[str]] = mapped_column(JSON, default=list)
    superseded_by: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    validated_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    validated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index("ix_inst_memory_org_type", "organization_id", "entry_type"),
        Index("ix_inst_memory_org_confidence", "organization_id", "confidence"),
    )


class CompanyAttention(Base, TimestampMixin):
    __tablename__ = "company_attention"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    attention_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # risk, opportunity, anomaly, deadline, milestone
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), default="medium", nullable=False)  # low, medium, high, critical
    entity_type: Mapped[Optional[str]] = mapped_column(String(60), index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    source: Mapped[str] = mapped_column(String(60), default="system", nullable=False)  # system, user, ai, external
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_company_attention_org_active", "organization_id", "is_active"),
        Index("ix_company_attention_org_priority", "organization_id", "priority"),
        Index("ix_company_attention_org_entity", "organization_id", "entity_type", "entity_id"),
        Index("ix_company_attention_expires", "expires_at"),
    )


class ModelTwinDrift(Base, TimestampMixin):
    __tablename__ = "model_twin_drifts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    model_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    drift_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # concept, data, prediction, performance
    severity: Mapped[str] = mapped_column(String(20), default="low", nullable=False)  # low, medium, high, critical
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    drift_score: Mapped[float] = mapped_column(default=0.0, nullable=False)
    threshold: Mapped[float] = mapped_column(default=0.0, nullable=False)
    affected_metrics: Mapped[List[str]] = mapped_column(JSON, default=list)
    affected_entities: Mapped[List[str]] = mapped_column(JSON, default=list)
    root_cause: Mapped[Optional[str]] = mapped_column(Text)
    recommended_action: Mapped[Optional[str]] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), default="detected", nullable=False)  # detected, investigating, mitigating, resolved, ignored
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_by: Mapped[Optional[str]] = mapped_column(ForeignKey("employees.id", ondelete="SET NULL"))
    mitigation_details: Mapped[Optional[str]] = mapped_column(Text)
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_model_twin_drifts_org_status", "organization_id", "status"),
        Index("ix_model_twin_drifts_org_model", "organization_id", "model_id"),
        Index("ix_model_twin_drifts_org_severity", "organization_id", "severity"),
    )


class TwinScope(Base, TimestampMixin):
    __tablename__ = "twin_scopes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    scope_type: Mapped[str] = mapped_column(String(40), default="full", nullable=False)  # full, department, team, project, metric
    scope_definition: Mapped[dict] = mapped_column(JSON, nullable=False)
    sync_frequency: Mapped[str] = mapped_column(String(20), default="real_time", nullable=False)  # real_time, hourly, daily, weekly, on_demand
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_sync_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_status: Mapped[str] = mapped_column(String(24), default="pending", nullable=False)  # pending, synced, error
    entities_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[Optional[str]] = mapped_column(Text)
    companystatesnapshot_metadata: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)

    __table_args__ = (
        Index("ix_twin_scopes_org_active", "organization_id", "is_active"),
    )


class TwinContext(Base):
    __tablename__ = "twin_contexts"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    context_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    context_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    scope_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("twin_scopes.id", ondelete="SET NULL"), index=True
    )
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_immutable: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "context_key", "valid_from", name="uq_twin_contexts_org_key_time"),
        Index("ix_twin_contexts_org_time", "organization_id", "valid_from", "valid_until"),
    )


class ContinuousStateProjection(Base, TimestampMixin):
    __tablename__ = "continuous_state_projections"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    projection_type: Mapped[str] = mapped_column(String(40), nullable=False)  # forecast, simulation, what-if, trend
    time_horizon: Mapped[str] = mapped_column(String(20), nullable=False)  # 1_day, 1_week, 1_month, 1_quarter, 1_year
    projected_state: Mapped[dict] = mapped_column(JSON, nullable=False)
    confidence: Mapped[float] = mapped_column(default=0.0, nullable=False)
    assumptions: Mapped[List[dict]] = mapped_column(JSON, default=list)
    scenarios: Mapped[List[dict]] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    valid_from: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        Index("ix_state_projections_org_type", "organization_id", "projection_type"),
        Index("ix_state_projections_org_horizon", "organization_id", "time_horizon"),
        Index("ix_state_projections_valid", "valid_from", "valid_until"),
    )


# Constants for Continuous Twin
COMPANY_STATE_DIMENSIONS = [
    "financial_health",
    "operational_efficiency",
    "employee_engagement",
    "customer_satisfaction",
    "innovation_rate",
    "market_position",
    "regulatory_compliance",
    "technical_debt",
    "knowledge_health",
    "cultural_alignment",
]

TWIN_SYNC_STATES = ["pending", "running", "completed", "failed", "partial"]
CALIBRATION_STATES = ["pending", "running", "completed", "failed"]
OPTIMIZATION_STATES = ["draft", "active", "running", "completed", "archived"]
DRIFT_SEVERITY = ["low", "medium", "high", "critical"]
LEARNING_SIGNAL_TYPES = ["pattern", "anomaly", "trend", "correlation", "prediction"]
ATTENTION_PRIORITY = ["low", "medium", "high", "critical"]
TWIN_SCOPE_TYPES = ["full", "department", "team", "project", "metric"]
DRIFT_TYPES = ["concept", "data", "prediction", "performance"]