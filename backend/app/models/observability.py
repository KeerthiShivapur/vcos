"""Gate 34 — Universal Observability & Operational Intelligence Fabric Models.

This module implements the canonical observation model that provides
a single source of truth for operational telemetry across the VCOS platform.

Key principles:
- Observability is a governed projection over the canonical VCOS reality
- No parallel observability reality - reuses existing primitives
- Correlation across request → authorization → governance → decision → action → worker → integration → outcome
- Epistemic boundaries preserved: telemetry ≠ business truth
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict
from enum import Enum

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
    Enum as SQLEnum,
    CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import ENUM as PGEnum

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid
from app.models.organization import utcnow


# =============================================================================
# VOCABULARIES
# =============================================================================

# Observation types - what kind of observation this is
OBSERVATION_TYPES = (
    "request",              # API request lifecycle
    "worker_execution",     # Worker job execution
    "operation_lifecycle",  # CanonicalOperation lifecycle
    "integration_sync",     # Integration sync status
    "external_operation",   # External system operation
    "security_event",       # Security event
    "recovery_action",      # Recovery operation
    "reconciliation",       # Reconciliation event
    "health_check",         # Health check result
    "freshness_check",      # Data freshness check
    "slo_evaluation",       # SLO evaluation
    "attention_signal",     # Operational attention signal
    "degradation",          # Degradation/incident
    "correlation",          # Cross-system correlation
)

# Observation severity
OBSERVATION_SEVERITY = (
    "debug",
    "info",
    "notice",
    "warning",
    "critical",
)

# Observation epistemic status
OBSERVATION_EPISTEMIC = (
    "observed",         # Directly observed
    "measured",         # Measured value
    "evidence_backed",  # Supported by evidence
    "inferred",         # Inferred from evidence
    "predicted",        # Predicted value
    "unknown",          # Unknown state
)

# Correlation types
CORRELATION_TYPES = (
    "request_flow",           # End-to-end request trace
    "operation_chain",        # Operation → attempt → recovery
    "integration_flow",       # Integration sync → external op
    "security_cascade",       # Security event chain
    "recovery_chain",         # Failure → recovery → verification
    "degradation_cascade",    # Degradation → attention → recovery
    "business_impact",        # Technical → business impact
)

# Degradation states
DEGRADATION_STATES = (
    "detected",
    "investigating",
    "contained",
    "recovering",
    "resolved",
    "verified",
    "learned",
)

# Degradation severity
DEGRADATION_SEVERITY = (
    "minor",
    "major",
    "critical",
)

# Health dimensions
HEALTH_DIMENSIONS = (
    "availability",
    "latency",
    "error_rate",
    "queue_delay",
    "sync_freshness",
    "worker_health",
    "recovery_backlog",
    "reconciliation_backlog",
)

# Observation severity
OBSERVATION_SEVERITY = (
    "debug",
    "info",
    "notice",
    "warning",
    "critical",
)

# Observation epistemic status
OBSERVATION_EPISTEMIC = (
    "observed",         # Directly observed
    "measured",         # Measured value
    "evidence_backed",  # Supported by evidence
    "inferred",         # Inferred from evidence
    "predicted",        # Predicted value
    "unknown",          # Unknown state
)

# Correlation types
CORRELATION_TYPES = (
    "request_flow",           # End-to-end request trace
    "operation_chain",        # Operation → attempt → recovery
    "integration_flow",       # Integration sync → external op
    "security_cascade",       # Security event chain
    "recovery_chain",         # Failure → recovery → verification
    "degradation_cascade",    # Degradation → attention → recovery
    "business_impact",        # Technical → business impact
)

# Degradation states
DEGRADATION_STATES = (
    "detected",
    "investigating",
    "contained",
    "recovering",
    "resolved",
    "verified",
    "learned",
)

# Degradation severity
DEGRADATION_SEVERITY = (
    "minor",
    "major",
    "critical",
)

# Health dimensions
HEALTH_DIMENSIONS = (
    "availability",
    "latency",
    "error_rate",
    "queue_delay",
    "sync_freshness",
    "worker_health",
    "recovery_backlog",
    "reconciliation_backlog",
)


# =============================================================================
# SHARED ENUM INSTANCES — Avoid duplicate CREATE TYPE attempts
# schema="public" ensures enums are created in the public schema
# =============================================================================

DEGRADATION_STATE_ENUM = PGEnum(
    *DEGRADATION_STATES,
    name="degradation_state",
    schema="public",
    create_type=True,
)

DEGRADATION_SEVERITY_ENUM = PGEnum(
    *DEGRADATION_SEVERITY,
    name="degradation_severity",
    schema="public",
    create_type=True,
)


# =============================================================================
# CANONICAL OBSERVATION — Single observation record
# =============================================================================

class CanonicalObservation(Base, TimestampMixin):
    """
    Canonical Observation — the canonical record of an operational observation.
    
    Every operational observation goes through this model. Reuses existing
    primitives: tenant isolation, provenance, exact-once, correlation.
    """
    
    __tablename__ = "canonical_observations"
    __table_args__ = (
        Index("ix_canobs_org_type", "organization_id", "observation_type"),
        Index("ix_canobs_org_severity", "organization_id", "severity"),
        Index("ix_canobs_org_epistemic", "organization_id", "epistemic_status"),
        Index("ix_canobs_org_recorded", "organization_id", "recorded_at"),
        Index("ix_canobs_correlation", "correlation_id"),
        Index("ix_canobs_trace", "trace_id"),
        Index("ix_canobs_span", "span_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_canobs_fp_exact_once",
        ),
        CheckConstraint(
            "observation_type IN ('request', 'worker_execution', 'operation_lifecycle', "
            "'integration_sync', 'external_operation', 'security_event', "
            "'recovery_action', 'reconciliation', 'health_check', 'freshness_check', "
            "'slo_evaluation', 'attention_signal', 'degradation', 'correlation')",
            name="ck_canobs_type_valid",
        ),
        CheckConstraint(
            "severity IN ('debug', 'info', 'notice', 'warning', 'critical')",
            name="ck_canobs_severity_valid",
        ),
        CheckConstraint(
            "epistemic_status IN ('observed', 'measured', 'evidence_backed', "
            "'inferred', 'predicted', 'unknown')",
            name="ck_canobs_epistemic_valid",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Observation identity
    observation_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Source identification
    source: Mapped[str] = mapped_column(String(100), nullable=False)  # api|worker|integration|security|reliability|etc
    source_component: Mapped[Optional[str]] = mapped_column(String(100))  # specific component
    
    # Actor (who/what generated this)
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(20), default="system")  # human|system|agent|worker
    
    # Severity and epistemic status
    severity: Mapped[str] = mapped_column(String(10), default="info", nullable=False, index=True)
    epistemic_status: Mapped[str] = mapped_column(String(20), default="observed", nullable=False, index=True)
    
    # Correlation
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    span_id: Mapped[Optional[str]] = mapped_column(String(64))
    parent_span_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Operation correlation
    operation_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    operation_type: Mapped[Optional[str]] = mapped_column(String(60))
    attempt_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Integration correlation
    integration_id: Mapped[Optional[str]] = mapped_column(String(32))
    connector_id: Mapped[Optional[str]] = mapped_column(String(32))
    external_operation_id: Mapped[Optional[str]] = mapped_column(String(255))
    
    # Security correlation
    security_event_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Degradation correlation
    degradation_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Content
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    details_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Metrics
    metrics_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Provenance
    provenance_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    source_event_id: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Timing
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# CORRELATION CONTEXT — Cross-system correlation context
# =============================================================================

class CorrelationContext(Base, TimestampMixin):
    """
    Correlation Context — maintains cross-system correlation state.
    
    Allows reconstructing the full chain: request → authorization → governance → decision → action → worker → integration → outcome
    """
    
    __tablename__ = "correlation_contexts"
    __table_args__ = (
        Index("ix_corrctx_org_type", "organization_id", "correlation_type"),
        Index("ix_corrctx_org_correlation", "organization_id", "correlation_id"),
        Index("ix_corrctx_trace", "trace_id"),
        UniqueConstraint(
            "organization_id", "correlation_id",
            name="uq_corrctx_correlation_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Correlation identity
    correlation_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    correlation_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    
    # Chain state
    chain_json: Mapped[dict] = mapped_column(JSON, default=dict)  # Ordered list of steps
    current_step: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[Optional[int]] = mapped_column(Integer)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|completed|broken|stale
    outcome: Mapped[Optional[str]] = mapped_column(String(30))  # success|partial|failed|unknown
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Metadata
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# DEGRADATION — Operational degradation/incident
# =============================================================================

class Degradation(Base, TimestampMixin):
    """
    Degradation — operational degradation/incident lifecycle.
    
    Reuses existing primitives: provenance, temporal truth, governance.
    """
    
    __tablename__ = "degradations"
    __table_args__ = (
        Index("ix_degrad_org_state", "organization_id", "state"),
        Index("ix_degrad_org_severity", "organization_id", "severity"),
        Index("ix_degrad_org_type", "organization_id", "degradation_type"),
        Index("ix_degrad_org_detected", "organization_id", "detected_at"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_degrad_fp_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Degradation identity
    degradation_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Classification
    severity: Mapped[str] = mapped_column(
        DEGRADATION_SEVERITY_ENUM,
        default="minor", nullable=False, index=True
    )
    
    # State machine
    state: Mapped[str] = mapped_column(
        DEGRADATION_STATE_ENUM,
        default="detected", nullable=False, index=True
    )
    
    # Content
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    details_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Affected entities
    affected_entities_json: Mapped[List[dict]] = mapped_column(JSON, default=list)
    affected_dimensions_json: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    # Correlation
    correlation_id: Mapped[Optional[str]] = mapped_column(String(64), index=True)
    root_cause_observation_id: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(20), default="system")
    
    # Evidence
    evidence_json: Mapped[List[dict]] = mapped_column(JSON, default=list)
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Timing
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    acknowledged_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    contained_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    recovered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    learned_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Resolution
    resolution_note: Mapped[Optional[str]] = mapped_column(Text)
    resolution_method: Mapped[Optional[str]] = mapped_column(String(40))
    lessons_learned_json: Mapped[Optional[dict]] = mapped_column(JSON)
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# HEALTH DIMENSION — Operational health dimension measurement
# =============================================================================

class HealthDimension(Base, TimestampMixin):
    """
    Health Dimension — measurable operational health dimension.
    
    Reuses existing primitives: exact-once, provenance, temporal truth.
    """
    
    __tablename__ = "health_dimensions"
    __table_args__ = (
        Index("ix_hdim_org_dim", "organization_id", "dimension"),
        Index("ix_hdim_org_status", "organization_id", "status"),
        Index("ix_hdim_org_recorded", "organization_id", "recorded_at"),
        UniqueConstraint(
            "organization_id", "dimension", "scope_type", "scope_id",
            name="uq_hdim_org_dim_scope_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Dimension identity
    dimension: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="company", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="healthy", nullable=False, index=True)  # healthy|degraded|critical|unknown
    
    # Measurements
    current_value: Mapped[float] = mapped_column(Float, default=0.0)
    target_value: Mapped[Optional[float]] = mapped_column(Float)
    threshold_warn: Mapped[Optional[float]] = mapped_column(Float)
    threshold_critical: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Trend
    trend: Mapped[str] = mapped_column(String(20), default="stable")  # improving|stable|degrading|volatile
    trend_score: Mapped[float] = mapped_column(Float, default=0.0)
    
    # SLO
    slo_target: Mapped[Optional[float]] = mapped_column(Float)
    slo_compliance: Mapped[Optional[float]] = mapped_column(Float)  # percentage
    
    # Evidence
    evidence_json: Mapped[List[dict]] = mapped_column(JSON, default=list)
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Timing
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    window_start: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# SLO TARGET — Operational target/threshold
# =============================================================================

class SLOTarget(Base, TimestampMixin):
    """
    SLO Target — operational target/threshold for a health dimension.
    """
    
    __tablename__ = "slo_targets"
    __table_args__ = (
        Index("ix_slo_org_dim", "organization_id", "dimension"),
        Index("ix_slo_org_status", "organization_id", "status"),
        UniqueConstraint(
            "organization_id", "dimension", "scope_type", "scope_id",
            name="uq_slo_org_dim_scope_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # SLO identity
    dimension: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(20), default="company", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Target
    target_value: Mapped[float] = mapped_column(Float, nullable=False)
    operator: Mapped[str] = mapped_column(String(10), default="<=")  # <=|>=|==|<
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Window
    window_type: Mapped[str] = mapped_column(String(20), default="rolling")  # rolling|calendar
    window_size: Mapped[str] = mapped_column(String(30), default="7d")  # 1h|1d|7d|30d
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|paused|deprecated
    current_compliance: Mapped[Optional[float]] = mapped_column(Float)
    last_evaluated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Metadata
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# FRESHNESS CHECK — Data freshness tracking
# =============================================================================

class FreshnessCheck(Base, TimestampMixin):
    """
    Freshness Check — tracks freshness of canonical data feeds.
    """
    
    __tablename__ = "freshness_checks"
    __table_args__ = (
        Index("ix_fresh_org_feed", "organization_id", "feed_type"),
        Index("ix_fresh_org_status", "organization_id", "status"),
        Index("ix_fresh_org_checked", "organization_id", "last_checked_at"),
        UniqueConstraint(
            "organization_id", "feed_type", "scope_type", "scope_id",
            name="uq_fresh_org_feed_scope_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    # Feed identity
    feed_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)  # integration|worker|event|sync|projection|etc
    scope_type: Mapped[str] = mapped_column(String(20), default="company")
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    feed_id: Mapped[Optional[str]] = mapped_column(String(64))  # specific feed identifier
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="fresh", index=True)  # fresh|delayed|stale|unknown
    
    # Timing
    expected_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)  # expected update interval
    last_event_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    delay_seconds: Mapped[Optional[int]] = mapped_column(Integer)
    max_acceptable_delay_seconds: Mapped[int] = mapped_column(Integer, default=3600)
    
    # Evidence
    last_event_fingerprint: Mapped[Optional[str]] = mapped_column(String(160))
    details_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# OPERATIONAL TARGET — Operational target for worker/operation
# =============================================================================

class OperationalTarget(Base, TimestampMixin):
    """
    Operational Target — target for worker/operation completion.
    """
    
    __tablename__ = "operational_targets"
    __table_args__ = (
        Index("ix_optarget_org_type", "organization_id", "target_type"),
        Index("ix_optarget_org_status", "organization_id", "status"),
        UniqueConstraint(
            "organization_id", "target_type", "scope_type", "scope_id",
            name="uq_optarget_org_type_scope_exact_once",
        ),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    
    target_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # worker_completion|operation_completion|recovery_time|sync_freshness
    scope_type: Mapped[str] = mapped_column(String(20), default="company")
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    
    # Target
    target_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    target_value: Mapped[Optional[float]] = mapped_column(Float)
    unit: Mapped[Optional[str]] = mapped_column(String(20))
    
    # Status
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)  # active|paused|met|missed
    current_value: Mapped[Optional[float]] = mapped_column(Float)
    
    # Window
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    window_end: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Metadata
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    
    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# SHARED ENUM INSTANCES — Avoid duplicate CREATE TYPE attempts
# schema="public" ensures enums are created in the public schema
# =============================================================================

DEGRADATION_STATE_ENUM = PGEnum(
    *DEGRADATION_STATES,
    name="degradation_state",
    schema="public",
    create_type=True,
)

DEGRADATION_SEVERITY_ENUM = PGEnum(
    *DEGRADATION_SEVERITY,
    name="degradation_severity",
    schema="public",
    create_type=True,
)


# =============================================================================
# UTILITIES
# =============================================================================

def compute_observation_fingerprint(payload: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:160]


def compute_correlation_fingerprint(
    organization_id: str,
    correlation_id: str,
    trace_id: Optional[str] = None,
) -> str:
    """Compute fingerprint for correlation context."""
    data = {
        "organization_id": organization_id,
        "correlation_id": correlation_id,
        "trace_id": trace_id or "",
    }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:160]


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Vocabularies
    "OBSERVATION_TYPES",
    "OBSERVATION_SEVERITY",
    "OBSERVATION_EPISTEMIC",
    "CORRELATION_TYPES",
    "DEGRADATION_STATES",
    "DEGRADATION_SEVERITY",
    "HEALTH_DIMENSIONS",
    # Models
    "CanonicalObservation",
    "CorrelationContext",
    "Degradation",
    "HealthDimension",
    "SLOTarget",
    "FreshnessCheck",
    "OperationalTarget",
    # Shared enums
    "DEGRADATION_STATE_ENUM",
    "DEGRADATION_SEVERITY_ENUM",
    # Utilities
    "compute_observation_fingerprint",
    "compute_correlation_fingerprint",
]