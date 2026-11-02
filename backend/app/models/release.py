"""Release State Models — Release Candidate Hardening Slice 2C.

Implements release lifecycle states with failure injection and recovery tracking.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from enum import Enum

from sqlalchemy import (
    String, DateTime, ForeignKey, Index, Text, Enum as SQLEnum,
    Boolean, Integer, JSON
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base
from app.models.organization import gen_uuid


class ReleasePhase(str, Enum):
    """Release lifecycle phases."""
    
    # Planning phases
    PLANNED = "planned"
    PRECHECKING = "prechecking"
    PRECHECKED = "prechecked"
    
    # Pre-release validation
    FINGERPRINT_CAPTURED = "fingerprint_captured"
    ARTIFACT_VALIDATED = "artifact_validated"
    
    # Migration phases
    MIGRATION_STARTED = "migration_started"
    MIGRATION_IN_PROGRESS = "migration_in_progress"
    MIGRATION_COMPLETED = "migration_completed"
    
    # Deployment phases
    APPLICATION_DEPLOYING = "application_deploying"
    APPLICATION_DEPLOYED = "application_deployed"
    WORKERS_DEPLOYING = "workers_deploying"
    WORKERS_DEPLOYED = "workers_deployed"
    
    # Validation phases
    VALIDATING = "validating"
    HEALTH_CHECKS_RUNNING = "health_checks_running"
    READINESS_CHECKS_RUNNING = "readiness_checks_running"
    
    # Activation phases
    ACTIVATING = "activating"
    ACTIVE = "active"
    
    # Post-activation
    POST_ACTIVATION_VERIFICATION = "post_activation_verification"
    COMPLETED = "completed"
    
    # Failure states
    PRECHECK_FAILED = "precheck_failed"
    ARTIFACT_INVALID = "artifact_invalid"
    MIGRATION_FAILED = "migration_failed"
    APPLICATION_DEPLOYMENT_FAILED = "application_deployment_failed"
    WORKER_DEPLOYMENT_FAILED = "worker_deployment_failed"
    HEALTH_CHECK_FAILED = "health_check_failed"
    READINESS_CHECK_FAILED = "readiness_check_failed"
    CANONICAL_INTEGRITY_FAILED = "canonical_integrity_failed"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    ACTIVATION_FAILED = "activation_failed"
    
    # Recovery states
    RECOVERY_REQUIRED = "recovery_required"
    RECOVERING = "recovering"
    RECOVERED = "recovered"
    ROLLED_BACK = "rolled_back"
    ABORTED = "aborted"
    RECOVERY_VALIDATION_FAILED = "recovery_validation_failed"
    
    # Governance
    REQUIRES_GOVERNANCE = "requires_governance"
    GOVERNANCE_PENDING = "governance_pending"
    GOVERNANCE_APPROVED = "governance_approved"
    GOVERNANCE_REJECTED = "governance_rejected"


class ReleaseFailureType(str, Enum):
    """Types of release failures for injection."""
    PREFLIGHT = "preflight"
    ARTIFACT_VALIDATION = "artifact_validation"
    MIGRATION_START = "migration_start"
    MIGRATION_MIDDLE = "migration_middle"
    MIGRATION_COMPLETION = "migration_completion"
    APPLICATION_DEPLOYMENT = "application_deployment"
    WORKER_DEPLOYMENT = "worker_deployment"
    HEALTH_CHECK = "health_check"
    READINESS_CHECK = "readiness_check"
    CANONICAL_INTEGRITY = "canonical_integrity"
    FINGERPRINT_VERIFICATION = "fingerprint_verification"
    ACTIVATION = "activation"
    POST_ACTIVATION = "post_activation"


class RecoveryStrategy(str, Enum):
    """Recovery strategy types."""
    RETRY = "retry"
    CONTINUE = "continue"
    ROLLBACK_APPLICATION = "rollback_application"
    ROLLBACK_MIGRATION = "rollback_migration"
    RESTORE_DATABASE = "restore_database"
    RECONCILE = "reconcile"
    GOVERNANCE_INTERVENTION = "governance_intervention"
    ABORT = "abort"


class ReleaseRecord(Base):
    """Canonical release record with full lifecycle tracking."""
    
    __tablename__ = "release_records"
    __table_args__ = (
        Index("ix_rr_org_status", "organization_id", "status"),
        Index("ix_rr_version", "version"),
        Index("ix_rr_phase", "phase"),
        Index("ix_rr_started", "started_at"),
        Index("ix_rr_fingerprint", "pre_release_fingerprint"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"rel-{uuid.uuid4().hex[:12]}")
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    version: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    phase: Mapped[str] = mapped_column(String(64), default=ReleasePhase.PLANNED.value, nullable=False)
    
    # Release contract
    contract_id: Mapped[Optional[str]] = mapped_column(String(64))
    contract_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    
    # Fingerprint evidence
    pre_release_fingerprint: Mapped[Optional[str]] = mapped_column(String(160))
    pre_release_component_fingerprints: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    post_release_fingerprint: Mapped[Optional[str]] = mapped_column(String(160))
    post_release_component_fingerprints: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    expected_fingerprint_changes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    unexpected_fingerprint_changes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    fingerprint_algorithm: Mapped[str] = mapped_column(String(32), default="sha256_64")
    
    # Phase tracking
    phase: Mapped[str] = mapped_column(String(64), default=ReleasePhase.PLANNED.value, nullable=False)
    phase_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    phase_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    phase_history: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON)
    
    # Preflight
    preflight_verdict: Mapped[Optional[str]] = mapped_column(String(32))
    preflight_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Migration tracking
    migration_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    migration_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    migration_revisions: Mapped[Optional[List[str]]] = mapped_column(JSON)
    migration_status: Mapped[Optional[str]] = mapped_column(String(32))
    
    # Deployment tracking
    application_deployed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    workers_deployed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Validation
    health_checks_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    readiness_checks_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    canonical_integrity_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    fingerprint_match: Mapped[Optional[bool]] = mapped_column(Boolean)
    
    # Fingerprint comparison
    fingerprint_comparison_result: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    expected_fingerprint_changes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    unexpected_fingerprint_changes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Failure tracking
    failure_type: Mapped[Optional[str]] = mapped_column(String(64))
    failure_injected: Mapped[bool] = mapped_column(Boolean, default=False)
    failure_point: Mapped[Optional[str]] = mapped_column(String(64))
    failure_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    failure_injected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Recovery tracking
    recovery_strategy: Mapped[Optional[str]] = mapped_column(String(64))
    recovery_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    recovery_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    recovery_status: Mapped[Optional[str]] = mapped_column(String(32))
    recovery_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    recovery_validation_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    
    # Governance
    governance_required: Mapped[bool] = mapped_column(Boolean, default=False)
    governance_status: Mapped[Optional[str]] = mapped_column(String(32))
    governance_approved_by: Mapped[Optional[str]] = mapped_column(String(32))
    governance_approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    governance_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Post-recovery validation
    post_recovery_fingerprint: Mapped[Optional[str]] = mapped_column(String(160))
    post_recovery_validation: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    post_recovery_validation_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Error tracking
    error: Mapped[Optional[str]] = mapped_column(Text)
    error_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Metadata
    initiated_by: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class ReleaseFailureInjection(Base):
    """Deterministic failure injection for release testing."""
    
    __tablename__ = "release_failure_injections"
    __table_args__ = (
        Index("ix_rfi_release_type", "release_id", "failure_type"),
        Index("ix_rfi_active", "is_active"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"rfi-{uuid.uuid4().hex[:12]}")
    release_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("release_records.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    failure_type: Mapped[str] = mapped_column(String(64), nullable=False)
    failure_point: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Injection configuration
    trigger_condition: Mapped[str] = mapped_column(String(64), default="always")
    trigger_parameters: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    error_message: Mapped[str] = mapped_column(String(512))
    error_code: Mapped[Optional[str]] = mapped_column(String(64))
    exception_type: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Execution control
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    max_triggers: Mapped[int] = mapped_column(Integer, default=1)
    trigger_count: Mapped[int] = mapped_column(Integer, default=0)
    
    # Execution tracking
    triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Metadata
    created_by: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
    
    # Test-only marker
    test_mode_only: Mapped[bool] = mapped_column(Boolean, default=True)


class ReleaseRecoveryRecord(Base):
    """Recovery operation record for a failed release."""
    
    __tablename__ = "release_recovery_records"
    __table_args__ = (
        Index("ix_rrr_release", "release_id"),
        Index("ix_rrr_status", "status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"rrr-{uuid.uuid4().hex[:12]}")
    release_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("release_records.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    # Recovery classification
    recovery_strategy: Mapped[str] = mapped_column(String(64))
    recovery_reason: Mapped[str] = mapped_column(Text)
    
    # Recovery execution
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Recovery steps
    steps: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON)
    steps_completed: Mapped[int] = mapped_column(Integer, default=0)
    steps_total: Mapped[int] = mapped_column(Integer, default=0)
    current_step: Mapped[Optional[str]] = mapped_column(String(64))
    
    # Validation
    validation_passed: Mapped[Optional[bool]] = mapped_column(Boolean)
    validation_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Fingerprint comparison
    pre_recovery_fingerprint: Mapped[Optional[str]] = mapped_column(String(160))
    post_recovery_fingerprint: Mapped[Optional[str]] = mapped_column(String(160))
    fingerprint_match: Mapped[Optional[bool]] = mapped_column(Boolean)
    fingerprint_changes: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Governance
    governance_required: Mapped[bool] = mapped_column(Boolean, default=False)
    governance_status: Mapped[Optional[str]] = mapped_column(String(32))
    authorized_by: Mapped[Optional[str]] = mapped_column(String(32))
    authorized_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    
    # Error
    error: Mapped[Optional[str]] = mapped_column(Text)
    error_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Metadata
    initiated_by: Mapped[str] = mapped_column(String(64))
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class ReleaseFingerprintEvidence(Base):
    """Canonical fingerprint evidence for a release."""
    
    __tablename__ = "release_fingerprint_evidence"
    __table_args__ = (
        Index("ix_rfe_release", "release_id"),
        Index("ix_rfe_org_type", "organization_id", "fingerprint_type"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: f"rfe-{uuid.uuid4().hex[:12]}")
    release_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("release_records.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    fingerprint_type: Mapped[str] = mapped_column(String(32), nullable=False)  # pre_release, post_release, post_recovery, expected_changes
    aggregate_fingerprint: Mapped[str] = mapped_column(String(160), nullable=False)
    component_fingerprints: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)
    
    algorithm: Mapped[str] = mapped_column(String(32), default="sha256_64")
    algorithm_version: Mapped[str] = mapped_column(String(32), default="1.0")
    
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    computed_by: Mapped[str] = mapped_column(String(64))
    
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON)


# Re-export
__all__ = [
    "ReleasePhase",
    "ReleaseFailureType",
    "RecoveryStrategy",
    "ReleaseRecord",
    "ReleaseFailureInjection",
    "ReleaseRecoveryRecord",
    "ReleaseFingerprintEvidence",
]