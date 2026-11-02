"""Backup Manifest — Canonical backup metadata storage.

Provides durable, queryable storage for backup metadata and verification results.
This is NOT a business model — it is operational infrastructure for backup/restore.
"""

import json
import uuid
import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import (
    Column, String, Text, DateTime, Integer, Enum as SQLEnum,
    ForeignKey, Index, Text, JSON, Boolean
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func

from app.db.base import Base
from app.validation.capability_contract import ValidationStatus


class BackupKind(str, enum.Enum):
    """Types of backups."""
    FULL = "full"
    INCREMENTAL = "incremental"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    ON_DEMAND = "on_demand"
    PRE_DEPLOYMENT = "pre_deployment"
    POST_DEPLOYMENT = "post_deployment"
    PRE_MIGRATION = "pre_migration"
    POST_MIGRATION = "post_migration"


class BackupStatus(str, enum.Enum):
    """Backup status states."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    VERIFIED = "verified"
    FAILED_VERIFICATION = "failed_verification"
    EXPIRED = "expired"
    CORRUPTED = "corrupted"


class RecoveryManifestState(str, enum.Enum):
    """Recovery manifest lifecycle states."""
    CREATED = "created"
    PREFLIGHTED = "preflighted"
    BACKUP_SELECTED = "backup_selected"
    BACKUP_VERIFIED = "backup_verified"
    RESTORE_INITIALIZED = "restore_initialized"
    DATABASE_RESTORED = "database_restored"
    WAL_REPLAYED = "wal_replayed"
    SCHEMA_VALIDATED = "schema_validated"
    CANONICAL_VALIDATED = "canonical_validated"
    TENANT_VALIDATED = "tenant_validated"
    TEMPORAL_VALIDATED = "temporal_validated"
    PROVENANCE_VALIDATED = "provenance_validated"
    GOVERNANCE_VALIDATED = "governance_validated"
    LONGITUDINAL_VALIDATED = "longitudinal_validated"
    DEPENDENCIES_VALIDATED = "dependencies_validated"
    READY_FOR_APPROVAL = "ready_for_approval"
    ACTIVATED = "activated"
    FAILED = "failed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    INTERRUPTED = "interrupted"


class RecoveryVerificationStatus(str, enum.Enum):
    """Individual verification check status."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"


class BackupManifest(Base):
    """Canonical backup manifest — durable record of backup operations."""
    
    __tablename__ = "backup_manifests"
    
    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"bkp-{uuid.uuid4().hex[:12]}"
    )
    
    # Organization ownership (for tenant isolation)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    # Backup identity
    backup_kind: Mapped[str] = mapped_column(
        SQLEnum(BackupKind, values_callable=lambda x: [e.value for e in BackupKind], native_enum=False),
        default=BackupKind.FULL, nullable=False
    )
    status: Mapped[str] = mapped_column(
        SQLEnum(BackupStatus, values_callable=lambda x: [e.value for e in BackupStatus], native_enum=False),
        default=BackupStatus.PENDING, nullable=False, index=True
    )
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Source database info
    database_url_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    pg_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    schema_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    vcos_version: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    
    # Backup format and storage
    backup_format: Mapped[str] = mapped_column(String(32), default="pgbackrest", nullable=False)
    backup_size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    checksum_sha256: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # Table scope
    tables_included: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    tables_excluded: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    
    # Retention
    retention_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    
    # Storage location
    vault_bucket: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    vault_path: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    
    # Error tracking
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_trace: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Verification
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    verification_status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    verification_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Canonical metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    
    # Relationships
    verification_results = relationship("BackupVerificationResult", back_populates="backup", cascade="all, delete-orphan")
    restore_operations = relationship("RestoreOperation", back_populates="backup", cascade="all, delete-orphan")


class BackupVerificationResult(Base):
    """Result of backup verification checks."""
    
    __tablename__ = "backup_verification_results"
    
    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"bvr-{uuid.uuid4().hex[:12]}"
    )
    
    backup_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("backup_manifests.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    # Overall result
    verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    
    # Individual checks (stored as ValidationStatus enum values)
    checksum_valid: Mapped[str] = mapped_column(String(32), default=ValidationStatus.INCONCLUSIVE.value, nullable=False)
    schema_valid: Mapped[str] = mapped_column(String(32), default=ValidationStatus.INCONCLUSIVE.value, nullable=False)
    data_integrity: Mapped[str] = mapped_column(String(32), default=ValidationStatus.INCONCLUSIVE.value, nullable=False)
    tenant_isolation: Mapped[str] = mapped_column(String(32), default=ValidationStatus.INCONCLUSIVE.value, nullable=False)
    temporal_integrity: Mapped[str] = mapped_column(String(32), default=ValidationStatus.INCONCLUSIVE.value, nullable=False)
    provenance_valid: Mapped[str] = mapped_column(String(32), default=ValidationStatus.INCONCLUSIVE.value, nullable=False)
    epistemic_valid: Mapped[str] = mapped_column(String(32), default=ValidationStatus.INCONCLUSIVE.value, nullable=False)
    governance_valid: Mapped[str] = mapped_column(String(32), default=ValidationStatus.INCONCLUSIVE.value, nullable=False)
    recovery_state_valid: Mapped[str] = mapped_column(String(32), default=ValidationStatus.INCONCLUSIVE.value, nullable=False)
    
    # Detailed results
    checks: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    errors: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    warnings: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    validation_details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fingerprint: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    
    # Relationship
    backup = relationship("BackupManifest", back_populates="verification_results")


class RestoreOperation(Base):
    """Record of a restore operation with full validation pipeline."""
    
    __tablename__ = "restore_operations"
    
    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"rst-{uuid.uuid4().hex[:12]}"
    )
    
    backup_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("backup_manifests.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    # Restore identity
    restore_id: Mapped[str] = mapped_column(
        String(32), default=lambda: f"rst-{uuid.uuid4().hex[:12]}", nullable=False, unique=True
    )
    
    # Restore parameters
    target_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    target_version: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    initiated_by: Mapped[str] = mapped_column(String(64), nullable=False)
    
    # Restore lifecycle state
    phase: Mapped[str] = mapped_column(String(64), default="BACKUP_SELECTED", nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False
    )
    
    # Phase results
    phases: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Error tracking
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    error_phase: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # Final validation results
    canonical_fingerprint: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    validation_passed: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    fingerprint: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    
    # Regular column (not used for optimistic locking)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    # Relationships
    backup = relationship("BackupManifest", back_populates="restore_operations")


class BackupCorruptionTest(Base):
    """Record of adversarial backup corruption tests."""
    
    __tablename__ = "backup_corruption_tests"
    
    id: Mapped[str] = mapped_column(
        String(32), primary_key=True, default=lambda: f"bct-{uuid.uuid4().hex[:12]}"
    )
    
    backup_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("backup_manifests.id", ondelete="CASCADE"), 
        nullable=False, index=True
    )
    
    # Test metadata
    test_name: Mapped[str] = mapped_column(String(64), nullable=False)
    test_category: Mapped[str] = mapped_column(String(32), nullable=False)  # corruption, attack, failure
    
    # Test parameters
    corruption_type: Mapped[str] = mapped_column(String(64), nullable=False)
    corruption_params: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    
    # Test result
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Details
    details: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    
    # Timing
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # Metadata
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    fingerprint: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)


# Indexes for query performance
Index("ix_backup_manifests_org_status", BackupManifest.organization_id, BackupManifest.status)
Index("ix_backup_manifests_org_started", BackupManifest.organization_id, BackupManifest.started_at)
Index("ix_backup_verification_backup_id", BackupVerificationResult.backup_id)
# Note: ix_restore_operations_backup_id is created automatically by index=True on RestoreOperation.backup_id column
Index("ix_restore_operations_org_status", RestoreOperation.organization_id, RestoreOperation.status)
# Note: ix_backup_corruption_tests_backup_id is created automatically by index=True on BackupCorruptionTest.backup_id column


# =====================================================================
# RECOVERY MANIFEST — Machine-readable recovery state
# =====================================================================

class RecoveryManifestState(str, enum.Enum):
    """Recovery manifest lifecycle states."""
    CREATED = "created"
    PREFLIGHTED = "preflighted"
    BACKUP_SELECTED = "backup_selected"
    BACKUP_VERIFIED = "backup_verified"
    RESTORE_INITIALIZED = "restore_initialized"
    DATABASE_RESTORED = "database_restored"
    WAL_REPLAYED = "wal_replayed"
    SCHEMA_VALIDATED = "schema_validated"
    CANONICAL_VALIDATED = "canonical_validated"
    TENANT_VALIDATED = "tenant_validated"
    TEMPORAL_VALIDATED = "temporal_validated"
    PROVENANCE_VALIDATED = "provenance_validated"
    GOVERNANCE_VALIDATED = "governance_validated"
    LONGITUDINAL_VALIDATED = "longitudinal_validated"
    DEPENDENCIES_VALIDATED = "dependencies_validated"
    READY_FOR_APPROVAL = "ready_for_approval"
    ACTIVATED = "activated"
    FAILED = "failed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    INTERRUPTED = "interrupted"


class RecoveryVerificationStatus(str, enum.Enum):
    """Individual verification check status."""
    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    SKIPPED = "skipped"


@dataclass
class RecoveryManifest:
    """Machine-readable recovery manifest for DR operations."""
    
    # Schema version
    manifest_schema_version: str = "1.0"
    
    # Backup identification
    backup_id: str = ""
    backup_method: str = ""           # e.g., "pgbackrest", "pg_basebackup"
    backup_format: str = ""           # e.g., "tar", "directory", "custom"
    backup_start_time: Optional[datetime] = None
    backup_completion_time: Optional[datetime] = None
    postgresql_version: str = ""
    database_system_identifier: str = ""
    source_database_name: str = ""
    source_environment_identity: str = ""
    vcos_revision: str = ""
    schema_revision: str = ""
    required_extensions: List[str] = field(default_factory=list)
    
    # Backup artifact
    backup_artifact_location: str = ""
    backup_artifact_size_bytes: int = 0
    backup_integrity_checksum: str = ""
    
    # WAL range
    required_wal_start_lsn: str = ""
    required_wal_end_lsn: str = ""
    earliest_verified_recovery_target: Optional[datetime] = None
    latest_verified_recovery_target: Optional[datetime] = None
    
    # Verification state
    verification_state: RecoveryManifestState = RecoveryManifestState.CREATED
    verification_checks: Dict[str, RecoveryVerificationStatus] = field(default_factory=dict)
    verification_details: Dict[str, Any] = field(default_factory=dict)
    
    # Limitations
    limitations: List[str] = field(default_factory=list)
    missing_wal_segments: List[str] = field(default_factory=list)
    historical_gaps: List[Dict[str, Any]] = field(default_factory=list)
    
    # Metadata
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary for JSON storage."""
        return {
            "manifest_schema_version": self.manifest_schema_version,
            "backup_id": self.backup_id,
            "backup_method": self.backup_method,
            "backup_format": self.backup_format,
            "backup_start_time": self.backup_start_time.isoformat() if self.backup_start_time else None,
            "backup_completion_time": self.backup_completion_time.isoformat() if self.backup_completion_time else None,
            "postgresql_version": self.postgresql_version,
            "database_system_identifier": self.database_system_identifier,
            "source_database_name": self.source_database_name,
            "source_environment_identity": self.source_environment_identity,
            "vcos_revision": self.vcos_revision,
            "schema_revision": self.schema_revision,
            "required_extensions": self.required_extensions,
            "backup_artifact_location": self.backup_artifact_location,
            "backup_artifact_size_bytes": self.backup_artifact_size_bytes,
            "backup_integrity_checksum": self.backup_integrity_checksum,
            "required_wal_start_lsn": self.required_wal_start_lsn,
            "required_wal_end_lsn": self.required_wal_end_lsn,
            "earliest_verified_recovery_target": self.earliest_verified_recovery_target.isoformat() if self.earliest_verified_recovery_target else None,
            "latest_verified_recovery_target": self.latest_verified_recovery_target.isoformat() if self.latest_verified_recovery_target else None,
            "verification_state": self.verification_state.value,
            "verification_checks": {k: v.value for k, v in self.verification_checks.items()},
            "verification_details": self.verification_details,
            "limitations": self.limitations,
            "missing_wal_segments": self.missing_wal_segments,
            "historical_gaps": self.historical_gaps,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RecoveryManifest":
        """Deserialize from dictionary."""
        manifest = cls()
        manifest.manifest_schema_version = data.get("manifest_schema_version", "1.0")
        manifest.backup_id = data.get("backup_id", "")
        manifest.backup_method = data.get("backup_method", "")
        manifest.backup_format = data.get("backup_format", "")
        manifest.backup_start_time = datetime.fromisoformat(data["backup_start_time"]) if data.get("backup_start_time") else None
        manifest.backup_completion_time = datetime.fromisoformat(data["backup_completion_time"]) if data.get("backup_completion_time") else None
        manifest.postgresql_version = data.get("postgresql_version", "")
        manifest.database_system_identifier = data.get("database_system_identifier", "")
        manifest.source_database_name = data.get("source_database_name", "")
        manifest.source_environment_identity = data.get("source_environment_identity", "")
        manifest.vcos_revision = data.get("vcos_revision", "")
        manifest.schema_revision = data.get("schema_revision", "")
        manifest.required_extensions = data.get("required_extensions", [])
        manifest.backup_artifact_location = data.get("backup_artifact_location", "")
        manifest.backup_artifact_size_bytes = data.get("backup_artifact_size_bytes", 0)
        manifest.backup_integrity_checksum = data.get("backup_integrity_checksum", "")
        manifest.required_wal_start_lsn = data.get("required_wal_start_lsn", "")
        manifest.required_wal_end_lsn = data.get("required_wal_end_lsn", "")
        manifest.earliest_verified_recovery_target = datetime.fromisoformat(data["earliest_verified_recovery_target"]) if data.get("earliest_verified_recovery_target") else None
        manifest.latest_verified_recovery_target = datetime.fromisoformat(data["latest_verified_recovery_target"]) if data.get("latest_verified_recovery_target") else None
        manifest.verification_state = RecoveryManifestState(data.get("verification_state", "created"))
        manifest.verification_checks = {k: RecoveryVerificationStatus(v) for k, v in data.get("verification_checks", {}).items()}
        manifest.verification_details = data.get("verification_details", {})
        manifest.limitations = data.get("limitations", [])
        manifest.missing_wal_segments = data.get("missing_wal_segments", [])
        manifest.historical_gaps = data.get("historical_gaps", [])
        manifest.created_at = datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(timezone.utc)
        manifest.updated_at = datetime.fromisoformat(data["updated_at"]) if data.get("updated_at") else datetime.now(timezone.utc)
        return manifest
    
    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "RecoveryManifest":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))