"""Gate 32 — Universal Reliability, Failure Recovery & Continuity Fabric Models.

This module implements the canonical reliability fabric that ensures the company
operating system remains truthful, governed, and resilient under real-world
failure conditions.

Key principles:
- No parallel reality: reliability is a property of the canonical operating system
- Every failure/recovery/reconciliation event preserves evidence
- UNKNOWN state is distinct from FAILED
- Recovery must never create a second reality
- Governance cannot be bypassed during recovery
"""

import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict
from enum import Enum

from sqlalchemy import (
    Index,
    UniqueConstraint,
    CheckConstraint,
    ForeignKey,
    String,
    Text,
    Integer,
    DateTime,
    Boolean,
    JSON,
    select,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid


# =============================================================================
# VOCABULARIES
# =============================================================================

# Operation lifecycle states
OPERATION_STATES = (
    "queued",           # Operation queued for execution
    "attempting",       # Currently being attempted
    "executing",        # External system interaction in progress
    "completed",        # Successfully completed
    "failed",           # Definitively failed (non-retryable)
    "retrying",         # Will be retried
    "cancelled",        # Cancelled before completion
    "unknown",          # Result unknown (external timeout, etc.)
    "recovering",       # Recovery in progress
    "reconciled",       # Reconciled with external system
    "expired",          # Expired without resolution
)

# Attempt states
ATTEMPT_STATES = (
    "pending",          # Not yet started
    "executing",        # Currently executing
    "completed",        # Completed successfully
    "failed",           # Failed
    "timeout",          # Timed out
    "cancelled",        # Cancelled
    "unknown",          # Result unknown
    "retrying",         # Being retried
)

# Recovery states
RECOVERY_STATES = (
    "pending",          # Recovery queued
    "detecting",        # Detecting failure
    "classifying",      # Classifying failure type
    "planning",         # Planning recovery
    "executing",        # Executing recovery
    "verifying",        # Verifying recovery result
    "completed",        # Recovery completed
    "failed",           # Recovery failed
    "escalated",        # Escalated to human
    "cancelled",        # Cancelled
)

# Reconciliation states
RECONCILIATION_STATES = (
    "pending",          # Pending reconciliation
    "detecting",        # Detecting discrepancy
    "querying",         # Querying external system
    "comparing",        # Comparing states
    "resolving",        # Resolving discrepancy
    "completed",        # Completed
    "failed",           # Failed
    "escalated",        # Escalated to human
)

# Recovery types
RECOVERY_TYPES = (
    "retry",                    # Simple retry
    "replay",                   # Replay from checkpoint
    "compensate",               # Compensating transaction
    "reconcile",                # Reconcile with external system
    "escalate",                 # Escalate to human
    "restart",                  # Restart from checkpoint
    "compensate_and_retry",     # Compensate then retry
    "external_reconcile",       # Reconcile with external system
    "manual_intervention",      # Requires human intervention
)

# Failure classifications
FAILURE_CLASSES = (
    "transient",                # Transient failure, safe to retry
    "permanent",                # Permanent failure, not retryable
    "unknown",                  # Unknown (timeout, network, etc.)
    "external_unknown",         # External system state unknown
    "external_conflict",        # External system reports conflict
    "governance_blocked",       # Blocked by governance
    "authorization_expired",    # Authorization expired
    "resource_exhausted",       # Resource exhausted
    "validation_failed",        # Validation failed
    "external_conflict",        # External system reports conflict
    # 35-H extended failure classes
    "validated_failure",        # Validated failure (non-retryable, known failure)
    "infrastructure_failure",   # Infrastructure failure (DB, Redis, network)
    "transient_failure",        # Transient failure (retryable)
    "timeout_failure",          # Timeout (may be UNKNOWN if external)
    "connection_failure",       # Connection failure
    "worker_crash",             # Worker process crash
    "database_failure",         # Database failure
    "external_failure",         # External system failure
    "unknown_external_outcome", # External system outcome unknown
    "recovery_required",        # Recovery required
    "reconciliation_required",  # Reconciliation required
    "partial_failure",          # Partial failure (partial success)
    "cascading_failure",        # Cascading failure
    "resource_exhausted",       # Resource exhausted (CPU, memory, disk)
    "capacity_exceeded",        # Capacity exceeded (quotas, limits)
    "configuration_error",      # Configuration error
    "data_corruption",          # Data corruption detected
    "version_conflict",         # Optimistic concurrency conflict
    "idempotency_conflict",     # Idempotency key conflict
)

# Retry policy types
RETRY_POLICIES = (
    "exponential_backoff",
    "fixed_interval",
    "linear_backoff",
    "immediate",
    "custom",
)

# Failure Taxonomy — deterministic classification of all failure types
FAILURE_TAXONOMY = {
    "validated_failure": {
        "retryable": False,
        "category": "validated",
        "description": "Validated failure (non-retryable, known failure)",
        "requires_reconciliation": False,
    },
    "infrastructure_failure": {
        "retryable": True,
        "category": "infrastructure",
        "description": "Infrastructure failure (DB, Redis, network)",
        "requires_reconciliation": False,
    },
    "transient_failure": {
        "retryable": True,
        "category": "transient",
        "description": "Transient failure (retryable)",
        "requires_reconciliation": False,
    },
    "timeout_failure": {
        "retryable": True,
        "category": "timeout",
        "description": "Timeout (may be UNKNOWN if external)",
        "requires_reconciliation": True,
    },
    "connection_failure": {
        "retryable": True,
        "category": "connection",
        "description": "Connection failure",
        "requires_reconciliation": False,
    },
    "worker_crash": {
        "retryable": True,
        "category": "worker",
        "description": "Worker process crash",
        "requires_reconciliation": False,
    },
    "database_failure": {
        "retryable": True,
        "category": "database",
        "description": "Database failure",
        "requires_reconciliation": False,
    },
    "external_failure": {
        "retryable": True,
        "category": "external",
        "description": "External system failure",
        "requires_reconciliation": True,
    },
    "unknown_external_outcome": {
        "retryable": False,
        "category": "external_unknown",
        "description": "External system outcome unknown",
        "requires_reconciliation": True,
    },
    "recovery_required": {
        "retryable": False,
        "category": "recovery",
        "description": "Recovery required",
        "requires_reconciliation": False,
    },
    "reconciliation_required": {
        "retryable": False,
        "category": "reconciliation",
        "description": "Reconciliation required",
        "requires_reconciliation": True,
    },
    "partial_failure": {
        "retryable": False,
        "category": "partial",
        "description": "Partial failure (partial success)",
        "requires_reconciliation": True,
    },
    "cascading_failure": {
        "retryable": False,
        "category": "cascading",
        "description": "Cascading failure",
        "requires_reconciliation": True,
    },
    "resource_exhausted": {
        "retryable": True,
        "category": "resource",
        "description": "Resource exhausted (CPU, memory, disk)",
        "requires_reconciliation": False,
    },
    "capacity_exceeded": {
        "retryable": True,
        "category": "capacity",
        "description": "Capacity exceeded (quotas, limits)",
        "requires_reconciliation": False,
    },
    "configuration_error": {
        "retryable": False,
        "category": "configuration",
        "description": "Configuration error",
        "requires_reconciliation": False,
    },
    "data_corruption": {
        "retryable": False,
        "category": "corruption",
        "description": "Data corruption detected",
        "requires_reconciliation": True,
    },
    "version_conflict": {
        "retryable": True,
        "category": "concurrency",
        "description": "Optimistic concurrency conflict",
        "requires_reconciliation": False,
    },
    "idempotency_conflict": {
        "retryable": False,
        "category": "idempotency",
        "description": "Idempotency key conflict",
        "requires_reconciliation": False,
    },
    "validated_failure": {
        "retryable": False,
        "category": "validated",
        "description": "Validated failure (non-retryable, known failure)",
        "requires_reconciliation": False,
    },
    "infrastructure_failure": {
        "retryable": True,
        "category": "infrastructure",
        "description": "Infrastructure failure (DB, Redis, network)",
        "requires_reconciliation": False,
    },
    "transient_failure": {
        "retryable": True,
        "category": "transient",
        "description": "Transient failure (retryable)",
        "requires_reconciliation": False,
    },
    "timeout_failure": {
        "retryable": True,
        "category": "timeout",
        "description": "Timeout (may be UNKNOWN if external)",
        "requires_reconciliation": True,
    },
    "connection_failure": {
        "retryable": True,
        "category": "connection",
        "description": "Connection failure",
        "requires_reconciliation": False,
    },
    "worker_crash": {
        "retryable": True,
        "category": "worker",
        "description": "Worker process crash",
        "requires_reconciliation": False,
    },
    "database_failure": {
        "retryable": True,
        "category": "database",
        "description": "Database failure",
        "requires_reconciliation": False,
    },
    "external_failure": {
        "retryable": True,
        "category": "external",
        "description": "External system failure",
        "requires_reconciliation": True,
    },
    "unknown_external_outcome": {
        "retryable": False,
        "category": "external_unknown",
        "description": "External system outcome unknown",
        "requires_reconciliation": True,
    },
    "recovery_required": {
        "retryable": False,
        "category": "recovery",
        "description": "Recovery required",
        "requires_reconciliation": False,
    },
    "reconciliation_required": {
        "retryable": False,
        "category": "reconciliation",
        "description": "Reconciliation required",
        "requires_reconciliation": True,
    },
    "partial_failure": {
        "retryable": False,
        "category": "partial",
        "description": "Partial failure (partial success)",
        "requires_reconciliation": True,
    },
    "cascading_failure": {
        "retryable": False,
        "category": "cascading",
        "description": "Cascading failure",
        "requires_reconciliation": True,
    },
    "resource_exhausted": {
        "retryable": True,
        "category": "resource",
        "description": "Resource exhausted (CPU, memory, disk)",
        "requires_reconciliation": False,
    },
    "capacity_exceeded": {
        "retryable": True,
        "category": "capacity",
        "description": "Capacity exceeded (quotas, limits)",
        "requires_reconciliation": False,
    },
    "configuration_error": {
        "retryable": False,
        "category": "configuration",
        "description": "Configuration error",
        "requires_reconciliation": False,
    },
    "data_corruption": {
        "retryable": False,
        "category": "corruption",
        "description": "Data corruption detected",
        "requires_reconciliation": True,
    },
    "version_conflict": {
        "retryable": True,
        "category": "concurrency",
        "description": "Optimistic concurrency conflict",
        "requires_reconciliation": False,
    },
    "idempotency_conflict": {
        "retryable": False,
        "category": "idempotency",
        "description": "Idempotency key conflict",
        "requires_reconciliation": False,
    },
    "transient": {
        "retryable": True,
        "category": "transient",
        "description": "Transient failure (alias for transient_failure)",
        "requires_reconciliation": False,
    },
    "permanent": {
        "retryable": False,
        "category": "validated",
        "description": "Permanent failure, not retryable",
        "requires_reconciliation": False,
    },
    "unknown": {
        "retryable": False,
        "category": "unknown",
        "description": "Unknown failure (timeout, network, etc.)",
        "requires_reconciliation": False,
    },
    "external_unknown": {
        "retryable": False,
        "category": "external_unknown",
        "description": "External system state unknown",
        "requires_reconciliation": True,
    },
    "external_conflict": {
        "retryable": False,
        "category": "external",
        "description": "External system reports conflict",
        "requires_reconciliation": True,
    },
    "governance_blocked": {
        "retryable": False,
        "category": "governance",
        "description": "Blocked by governance",
        "requires_reconciliation": False,
    },
    "authorization_expired": {
        "retryable": False,
        "category": "authorization",
        "description": "Authorization expired",
        "requires_reconciliation": True,
    },
    "validation_failed": {
        "retryable": False,
        "category": "validation",
        "description": "Validation failed",
        "requires_reconciliation": False,
    },
}

# Failure classification hierarchy for deterministic lookup
FAILURE_TAXONOMY_HIERARCHY = {
    "validated": ["validated_failure", "permanent"],
    "infrastructure": ["infrastructure_failure", "database_failure", "connection_failure"],
    "transient": ["transient_failure", "connection_failure", "transient"],
    "timeout": ["timeout_failure"],
    "worker": ["worker_crash"],
    "database": ["database_failure"],
    "external": ["external_failure", "external_conflict"],
    "external_unknown": ["unknown_external_outcome"],
    "recovery": ["recovery_required"],
    "reconciliation": ["reconciliation_required"],
    "partial": ["partial_failure"],
    "cascading": ["cascading_failure"],
    "resource": ["resource_exhausted", "capacity_exceeded"],
    "configuration": ["configuration_error"],
    "corruption": ["data_corruption"],
    "concurrency": ["version_conflict"],
    "idempotency": ["idempotency_conflict"],
    "validated": ["validated_failure"],
    "infrastructure": ["infrastructure_failure"],
    "transient": ["transient_failure"],
    "timeout": ["timeout_failure"],
    "connection": ["connection_failure"],
    "worker": ["worker_crash"],
    "database": ["database_failure"],
    "external": ["external_failure", "unknown_external_outcome"],
    "external_unknown": ["unknown_external_outcome"],
    "recovery": ["recovery_required"],
    "reconciliation": ["reconciliation_required"],
    "validated": ["validated_failure", "permanent"],
    "infrastructure": ["infrastructure_failure"],
    "transient": ["transient_failure", "transient"],
    "timeout": ["timeout_failure"],
    "connection": ["connection_failure"],
    "worker": ["worker_crash"],
    "database": ["database_failure"],
    "external": ["external_failure", "unknown_external_outcome"],
    "external_unknown": ["unknown_external_outcome"],
    "recovery": ["recovery_required"],
    "reconciliation": ["reconciliation_required"],
    "validated": ["validated_failure", "permanent"],
    "unknown": ["unknown"],
    "governance": ["governance_blocked"],
    "authorization": ["authorization_expired"],
    "validation": ["validation_failed"],
    "external": ["external_failure", "external_conflict", "unknown_external_outcome"],
    "external_unknown": ["unknown_external_outcome", "external_unknown"],
    "partial": ["partial_failure"],
    "cascading": ["cascading_failure"],
    "resource": ["resource_exhausted", "capacity_exceeded"],
    "configuration": ["configuration_error"],
    "corruption": ["data_corruption"],
    "concurrency": ["version_conflict"],
    "idempotency": ["idempotency_conflict"],
}

# Failure Taxonomy model for database persistence
class FailureTaxonomy(Base, TimestampMixin):
    """Failure Taxonomy — deterministic classification of failure types."""
    
    __tablename__ = "failure_taxonomy"
    __table_args__ = (
        UniqueConstraint("failure_class", name="uq_failure_taxonomy_class"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    failure_class: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_reconciliation: Mapped[bool] = mapped_column(Boolean, default=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    def __repr__(self):
        return f"<FailureTaxonomy {self.failure_class}>"

# Retry policy types
RETRY_POLICIES = (
    "exponential_backoff",
    "fixed_interval",
    "linear_backoff",
    "immediate",
    "custom",
)

# Recovery outcome classifications
RECOVERY_OUTCOMES = (
    "recovered",            # Fully recovered
    "partially_recovered",  # Partially recovered
    "compensated",          # Compensated via compensating transaction
    "escalated",            # Escalated to human
    "abandoned",            # Abandoned (non-recoverable)
    "reconciled",           # Reconciled with external system
)

# Attempt outcome states
ATTEMPT_OUTCOMES = (
    "success",
    "failure",
    "timeout",
    "cancelled",
    "unknown",
    "cancelled_by_user",
    "cancelled_by_system",
)


# =============================================================================
# CANONICAL OPERATION — Single operation with attempt history
# =============================================================================

class CanonicalOperation(Base, TimestampMixin):
    """
    Canonical Operation — the canonical record of an operation attempt lifecycle.
    
    Tracks the complete lifecycle from queued through execution to final outcome,
    including all attempts, retries, recoveries, and reconciliations.
    
    One canonical operation per business operation. Exact-once via fingerprint.
    """

    __tablename__ = "canonical_operations"
    __table_args__ = (
        Index("ix_co_org_state", "organization_id", "state"),
        Index("ix_co_org_type", "organization_id", "operation_type"),
        Index("ix_co_org_fingerprint", "organization_id", "fingerprint"),
        Index("ix_co_org_created", "organization_id", "created_at"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_co_fp_exact_once",
        ),
        CheckConstraint(
            "state IN ('queued', 'attempting', 'executing', 'completed', 'failed', "
            "'retrying', 'cancelled', 'unknown', 'recovering', 'reconciled', 'expired')",
            name="ck_co_state_valid",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Operation identity
    operation_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)

    # Scope and governance
    scope_type: Mapped[str] = mapped_column(String(20), default="company", nullable=False)
    scope_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    target_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    governance_scope_id: Mapped[Optional[str]] = mapped_column(String(32))

    # Links to canonical graph
    commitment_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    authorization_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    decision_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)
    action_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    # State machine
    state: Mapped[str] = mapped_column(String(20), default="queued", nullable=False, index=True)

    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(20), default="human")  # human | agent | system

    # External interaction
    is_external: Mapped[bool] = mapped_column(Boolean, default=False)
    external_system: Mapped[Optional[str]] = mapped_column(String(60))
    external_operation_id: Mapped[Optional[str]] = mapped_column(String(255))

    # Retry policy
    retry_policy: Mapped[str] = mapped_column(String(30), default="exponential_backoff")
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    current_attempt: Mapped[int] = mapped_column(Integer, default=0)
    max_retry_interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    concurrency_token: Mapped[int] = mapped_column(Integer, default=1)

    # Timing
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    next_retry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

# Result
    outcome: Mapped[Optional[str]] = mapped_column(String(20))  # ATTEMPT_OUTCOMES
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    payload: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)

    # Failure classification
    failure_class: Mapped[Optional[str]] = mapped_column(String(30))
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)

    # Recovery
    recovery_state: Mapped[Optional[str]] = mapped_column(String(20))
    recovery_type: Mapped[Optional[str]] = mapped_column(String(30))
    recovery_id: Mapped[Optional[str]] = mapped_column(String(32))
    recovery_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    recovery_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Reconciliation
    reconciliation_state: Mapped[Optional[str]] = mapped_column(String(20))
    reconciliation_id: Mapped[Optional[str]] = mapped_column(String(32))
    external_state: Mapped[Optional[dict]] = mapped_column(JSON)

    # Exact-once fingerprint
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    @property
    def is_terminal(self) -> bool:
        return self.state in ("completed", "failed", "cancelled", "expired", "reconciled")

    @property
    def can_retry(self) -> bool:
        return (
            self.state in ("failed", "retrying", "unknown")
            and self.current_attempt < self.max_attempts
        )


# =============================================================================
# OPERATION ATTEMPT — Individual attempt within an operation
# =============================================================================

class OperationAttempt(Base, TimestampMixin):
    """
    Operation Attempt — individual attempt within a canonical operation.
    
    Exact-once per (operation, attempt_number). Immutable once completed.
    """

    __tablename__ = "operation_attempts"
    __table_args__ = (
        Index("ix_oa_op_attempt", "operation_id", "attempt_number"),
        Index("ix_oa_state", "state"),
        Index("ix_oa_started", "started_at"),
        UniqueConstraint(
            "operation_id", "attempt_number",
            name="uq_oa_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Attempt identity
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # State
    state: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    # Timing
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Worker
    worker_id: Mapped[Optional[str]] = mapped_column(String(64))
    worker_instance: Mapped[Optional[str]] = mapped_column(String(64))

    # Result
    state: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    outcome: Mapped[Optional[str]] = mapped_column(String(20))  # ATTEMPT_OUTCOMES
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)

    # External
    external_request_id: Mapped[Optional[str]] = mapped_column(String(255))
    external_response_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Timing
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Retry
    retry_reason: Mapped[Optional[str]] = mapped_column(Text)
    is_retry: Mapped[bool] = mapped_column(Boolean, default=False)
    retried_from_attempt_id: Mapped[Optional[str]] = mapped_column(String(32))

    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    @property
    def is_terminal(self) -> bool:
        return self.state in ("completed", "failed", "cancelled", "timeout", "unknown")


# =============================================================================
# RECOVERY — Canonical recovery record
# =============================================================================

class Recovery(Base, TimestampMixin):
    """
    Recovery — canonical recovery record for failed/unknown operations.
    
    Tracks the complete recovery lifecycle from detection through verification.
    One recovery per canonical operation that requires recovery.
    """

    __tablename__ = "recoveries"
    __table_args__ = (
        Index("ix_rec_org_state", "organization_id", "state"),
        Index("ix_rec_org_type", "organization_id", "recovery_type"),
        Index("ix_rec_org_operation", "organization_id", "operation_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_rec_fp_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Recovery identity
    recovery_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # RECOVERY_TYPES
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    # Classification
    failure_class: Mapped[str] = mapped_column(String(30), nullable=False, index=True)  # FAILURE_CLASSES
    failure_reason: Mapped[Optional[str]] = mapped_column(Text)

    # State machine
    state: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)  # RECOVERY_STATES

    # Recovery plan
    recovery_plan_json: Mapped[Optional[dict]] = mapped_column(JSON)
    recovery_steps_json: Mapped[Optional[list]] = mapped_column(JSON)

    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))
    actor_type: Mapped[str] = mapped_column(String(20), default="system")  # human | system | autonomous

    # Governance
    governance_scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    requires_governance: Mapped[bool] = mapped_column(Boolean, default=False)
    authorized_by: Mapped[Optional[str]] = mapped_column(String(64))
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # State machine
    state: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)  # RECOVERY_STATES

    # Timing
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Progress
    current_step: Mapped[Optional[int]] = mapped_column(Integer)
    total_steps: Mapped[Optional[int]] = mapped_column(Integer)
    current_step_name: Mapped[Optional[str]] = mapped_column(String(120))

    # Result
    outcome: Mapped[Optional[str]] = mapped_column(String(30))  # RECOVERY_OUTCOMES
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)

    # Verification
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verified_by: Mapped[Optional[str]] = mapped_column(String(64))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verification_result_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Compensation
    compensation_id: Mapped[Optional[str]] = mapped_column(String(32))
    compensation_type: Mapped[Optional[str]] = mapped_column(String(30))
    compensation_executed: Mapped[bool] = mapped_column(Boolean, default=False)

    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# RECONCILIATION — External system reconciliation
# =============================================================================

class Reconciliation(Base, TimestampMixin):
    """
    Reconciliation — canonical reconciliation with external systems.
    
    Tracks reconciliation of canonical state with external systems.
    """

    __tablename__ = "reconciliations"
    __table_args__ = (
        Index("ix_recn_org_state", "organization_id", "state"),
        Index("ix_recn_org_type", "organization_id", "reconciliation_type"),
        Index("ix_recn_org_entity", "organization_id", "entity_type", "entity_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_recn_fp_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Reconciliation identity
    reconciliation_type: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    # Entity being reconciled
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    external_system: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    external_entity_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # State machine
    state: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    # Discrepancy
    discrepancy_type: Mapped[Optional[str]] = mapped_column(String(60))
    discrepancy_details_json: Mapped[Optional[dict]] = mapped_column(JSON)
    canonical_state_json: Mapped[Optional[dict]] = mapped_column(JSON)
    external_state_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Resolution
    resolution_method: Mapped[Optional[str]] = mapped_column(String(30))  # authority|manual|merged|policy
    resolved_value_json: Mapped[Optional[dict]] = mapped_column(JSON)
    resolved_by: Mapped[Optional[str]] = mapped_column(String(64))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Governance
    requires_governance: Mapped[bool] = mapped_column(Boolean, default=False)
    governance_scope_id: Mapped[Optional[str]] = mapped_column(String(32))
    authorized_by: Mapped[Optional[str]] = mapped_column(String(64))
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # State machine
    state: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)

    # Timing
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Result
    outcome: Mapped[Optional[str]] = mapped_column(String(30))
    result_json: Mapped[Optional[dict]] = mapped_column(JSON)
    error: Mapped[Optional[str]] = mapped_column(Text)

    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# EXTERNAL UNKNOWN STATE — Tracks operations with unknown external results
# =============================================================================

class ExternalUnknownState(Base, TimestampMixin):
    """
    External Unknown State — tracks operations where external result is unknown.
    
    Critical for distinguishing UNKNOWN from FAILED. External systems may have
    succeeded or failed, but VCOS cannot determine the result.
    """

    __tablename__ = "external_unknown_states"
    __table_args__ = (
        Index("ix_eus_org_state", "organization_id", "state"),
        Index("ix_eus_org_operation", "organization_id", "operation_id"),
        Index("ix_eus_external", "external_system", "external_operation_id"),
        UniqueConstraint(
            "organization_id", "fingerprint",
            name="uq_eus_fp_exact_once",
        ),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("external_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # External identity
    external_system: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    external_operation_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    external_operation_type: Mapped[str] = mapped_column(String(60))

    # Original request
    request_payload_json: Mapped[Optional[dict]] = mapped_column(JSON)
    request_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    # State
    state: Mapped[str] = mapped_column(String(20), default="unknown", nullable=False, index=True)

    # Timing
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    last_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    timeout_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Reconciliation
    reconciliation_id: Mapped[Optional[str]] = mapped_column(String(32))
    reconciliation_state: Mapped[Optional[str]] = mapped_column(String(20))
    external_state_json: Mapped[Optional[dict]] = mapped_column(JSON)
    reconciliation_method: Mapped[Optional[str]] = mapped_column(String(30))
    reconciliation_result_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Evidence
    evidence_fingerprints: Mapped[list] = mapped_column(JSON, default=list)
    evidence_details_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # Actor
    actor_id: Mapped[Optional[str]] = mapped_column(String(64))

    # Exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# RECOVERY PROPOSAL — Governed repair proposals
# =============================================================================

class RecoveryProposal(Base, TimestampMixin):
    """
    Recovery Proposal — governed repair proposal for integrity findings.
    
    A repair proposal must go through governance before execution.
    """

    __tablename__ = "recovery_proposals"
    __table_args__ = (
        Index("ix_rp_org_state", "organization_id", "state"),
        Index("ix_rp_finding", "finding_id"),
        Index("ix_rp_org_entity", "organization_id", "entity_type", "entity_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    finding_id: Mapped[Optional[str]] = mapped_column(String(32), index=True)

    # Affected entity
    entity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(32), nullable=False)
    current_state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    proposed_change_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Evidence and provenance
    evidence_json: Mapped[dict] = mapped_column(JSON, default=dict)
    provenance_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    temporal_basis_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Governance
    governance_scope_ids: Mapped[list] = mapped_column(JSON, default=list)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    proposed_mutation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    reversibility_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # State machine
    state: Mapped[str] = mapped_column(String(20), default="proposed", nullable=False, index=True)

    # Governance workflow
    proposed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    authorized_by: Mapped[Optional[str]] = mapped_column(String(64))
    executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    executed_by: Mapped[Optional[str]] = mapped_column(String(64))
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    verified_by: Mapped[Optional[str]] = mapped_column(String(64))

    # Reversibility
    reversibility_json: Mapped[dict] = mapped_column(JSON, default=dict)

    # Version for optimistic concurrency
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# STALE OPERATION DETECTION
# =============================================================================

class StaleOperationDetector(Base, TimestampMixin):
    """
    Stale Operation Detector — detects and tracks stale/abandoned operations.
    
    Uses temporal evidence to detect operations that appear stuck.
    """

    __tablename__ = "stale_operation_detections"
    __table_args__ = (
        Index("ix_sod_org_state", "organization_id", "operation_state"),
        Index("ix_sod_org_operation", "organization_id", "operation_id"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Detection
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    detection_method: Mapped[str] = mapped_column(String(40))  # timeout | heartbeat | checkpoint | manual
    stale_since: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stale_duration_seconds: Mapped[int] = mapped_column(Integer)
    detection_reason: Mapped[str] = mapped_column(Text)

    # Operation state at detection
    operation_state: Mapped[str] = mapped_column(String(20))
    operation_attempt: Mapped[int] = mapped_column(Integer)
    last_progress_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Recovery
    recovery_id: Mapped[Optional[str]] = mapped_column(String(32))
    recovery_state: Mapped[Optional[str]] = mapped_column(String(20))

    # Resolution
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution_method: Mapped[Optional[str]] = mapped_column(String(30))

    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# WORKER HEARTBEAT & LEASE
# =============================================================================

class WorkerLease(Base, TimestampMixin):
    """
    Worker Lease — lease-based worker coordination for crash detection.
    
    Workers acquire leases for operations. Lease expiration indicates crash.
    """

    __tablename__ = "worker_leases"
    __table_args__ = (
        Index("ix_wl_worker", "worker_id"),
        Index("ix_wl_operation", "operation_id"),
        Index("ix_wl_expires", "expires_at"),
        UniqueConstraint("worker_id", "operation_id", name="uq_wl_worker_operation"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    worker_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    worker_instance: Mapped[Optional[str]] = mapped_column(String(64))
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Lease
    acquired_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    renewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    renewal_count: Mapped[int] = mapped_column(Integer, default=0)

    # Worker identity
    worker_type: Mapped[str] = mapped_column(String(40))  # worker | autonomous | worker_type
    worker_metadata_json: Mapped[Optional[dict]] = mapped_column(JSON)

    # State
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    expired: Mapped[bool] = mapped_column(Boolean, default=False)


# =============================================================================
# OPERATION CHECKPOINT
# =============================================================================

class OperationCheckpoint(Base, TimestampMixin):
    """
    Operation Checkpoint — checkpoint for operation recovery.
    
    Captures operation state at a point in time for crash recovery.
    """

    __tablename__ = "operation_checkpoints"
    __table_args__ = (
        Index("ix_oc_op", "operation_id"),
        Index("ix_oc_created", "created_at"),
        UniqueConstraint("operation_id", "checkpoint_number", name="uq_oc_op_checkpoint"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    operation_id: Mapped[str] = mapped_column(
        ForeignKey("canonical_operations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Checkpoint identity
    checkpoint_number: Mapped[int] = mapped_column(Integer, nullable=False)
    checkpoint_type: Mapped[str] = mapped_column(String(30))  # start | step | external_call | pre_commit | post_commit

    # State snapshot
    operation_state_json: Mapped[dict] = mapped_column(JSON, default=dict)
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    step_number: Mapped[Optional[int]] = mapped_column(Integer)
    step_name: Mapped[Optional[str]] = mapped_column(String(120))

    # Fingerprint for exact-once
    fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)

    # Version
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Vocabularies
    "OPERATION_STATES",
    "ATTEMPT_STATES",
    "RECOVERY_STATES",
    "RECONCILIATION_STATES",
    "RECOVERY_TYPES",
    "FAILURE_CLASSES",
    "RETRY_POLICIES",
    "RECOVERY_OUTCOMES",
    "ATTEMPT_OUTCOMES",
    "FAILURE_TAXONOMY",
    "FAILURE_TAXONOMY_HIERARCHY",
    "RETRY_POLICIES",
    "RECOVERY_OUTCOMES",
    "ATTEMPT_OUTCOMES",
    # Models
    "CanonicalOperation",
    "OperationAttempt",
    "Recovery",
    "Reconciliation",
    "ExternalUnknownState",
    "RecoveryProposal",
    "StaleOperationDetector",
    "WorkerLease",
    "OperationCheckpoint",
    "FailureTaxonomy",
    # Utilities
    "compute_payload_fingerprint",
    "compute_operation_fingerprint",
]


def compute_payload_fingerprint(payload: dict[str, Any]) -> str:
    """Compute deterministic SHA-256 fingerprint for exact-once semantics."""
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:160]


def compute_operation_fingerprint(
    organization_id: str,
    operation_type: str,
    scope_type: str,
    scope_id: Optional[str],
    key_fields: dict
) -> str:
    """Compute fingerprint for a canonical operation."""
    data = {
        "organization_id": organization_id,
        "operation_type": operation_type,
        "scope_type": scope_type,
        "scope_id": scope_id or "",
        "key_fields": key_fields,
    }
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:160]


# Import at the end to avoid circular imports
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import DateTime, Boolean
from app.models.organization import TimestampMixin, gen_uuid