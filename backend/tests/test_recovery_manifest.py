"""Tests for Recovery Manifest model and serialization."""

import pytest
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from app.models.backup_manifest import (
    RecoveryManifest,
    RecoveryManifestState,
    RecoveryVerificationStatus,
)


class TestRecoveryManifest:
    """Test RecoveryManifest model."""
    
    def test_manifest_creation_defaults(self):
        """Test creating a manifest with defaults."""
        manifest = RecoveryManifest()
        
        assert manifest.manifest_schema_version == "1.0"
        assert manifest.backup_id == ""
        assert manifest.verification_state == RecoveryManifestState.CREATED
        assert manifest.verification_checks == {}
        assert manifest.limitations == []
        assert manifest.missing_wal_segments == []
        assert manifest.historical_gaps == []
        assert manifest.created_at is not None
        assert manifest.updated_at is not None
    
    def test_manifest_with_data(self):
        """Test creating a manifest with data."""
        now = datetime.now(timezone.utc)
        manifest = RecoveryManifest(
            backup_id="bkp-abc123",
            backup_method="pgbackrest",
            backup_format="tar",
            backup_start_time=now - timedelta(hours=1),
            backup_completion_time=now,
            postgresql_version="18.2",
            database_system_identifier="123456789",
            source_environment_identity="prod-host-1",
            vcos_revision="1.0.0",
            schema_revision="2026.10",
            required_extensions=["pg_trgm", "btree_gin"],
            backup_artifact_location="s3://vcos-backups/bkp-abc123",
            backup_artifact_size_bytes=1024 * 1024 * 100,
            backup_integrity_checksum="a" * 64,
            required_wal_start_lsn="0/1000000",
            required_wal_end_lsn="0/2000000",
            earliest_verified_recovery_target=now - timedelta(hours=1),
            latest_verified_recovery_target=now,
            verification_state=RecoveryManifestState.BACKUP_VERIFIED,
            verification_checks={
                "checksum": RecoveryVerificationStatus.VERIFIED,
                "schema": RecoveryVerificationStatus.VERIFIED,
            },
            verification_details={"checksum": "verified"},
            limitations=["Historical gap at segment 14"],
            missing_wal_segments=["000000010000008900000014"],
            historical_gaps=[{"segment": "14", "reason": "corrupt archive"}],
        )
        
        assert manifest.backup_id == "bkp-abc123"
        assert manifest.backup_method == "pgbackrest"
        assert manifest.verification_state == RecoveryManifestState.BACKUP_VERIFIED
        assert manifest.verification_checks["checksum"] == RecoveryVerificationStatus.VERIFIED
        assert "Historical gap at segment 14" in manifest.limitations
        assert "000000010000008900000014" in manifest.missing_wal_segments
        assert len(manifest.historical_gaps) == 1
    
    def test_manifest_to_dict(self):
        """Test serialization to dictionary."""
        now = datetime.now(timezone.utc)
        manifest = RecoveryManifest(
            backup_id="bkp-test",
            backup_method="pgbackrest",
            backup_start_time=now - timedelta(hours=1),
            backup_completion_time=now,
            postgresql_version="18.2",
            verification_state=RecoveryManifestState.CANONICAL_VALIDATED,
            verification_checks={
                "checksum": RecoveryVerificationStatus.VERIFIED,
                "schema": RecoveryVerificationStatus.VERIFIED,
            },
        )
        
        data = manifest.to_dict()
        
        assert data["manifest_schema_version"] == "1.0"
        assert data["backup_id"] == "bkp-test"
        assert data["backup_method"] == "pgbackrest"
        assert data["postgresql_version"] == "18.2"
        assert data["verification_state"] == "canonical_validated"
        assert data["verification_checks"]["checksum"] == "verified"
        assert data["verification_checks"]["schema"] == "verified"
        assert data["created_at"] is not None
        assert data["updated_at"] is not None
    
    def test_manifest_from_dict(self):
        """Test deserialization from dictionary."""
        now = datetime.now(timezone.utc)
        data = {
            "manifest_schema_version": "1.0",
            "backup_id": "bkp-test",
            "backup_method": "pgbackrest",
            "backup_format": "tar",
            "backup_start_time": (now - timedelta(hours=1)).isoformat(),
            "backup_completion_time": now.isoformat(),
            "postgresql_version": "18.2",
            "database_system_identifier": "123456789",
            "source_environment_identity": "prod-host-1",
            "vcos_revision": "1.0.0",
            "schema_revision": "2026.10",
            "required_extensions": ["pg_trgm"],
            "backup_artifact_location": "s3://bucket/backup",
            "backup_artifact_size_bytes": 1024 * 1024 * 50,
            "backup_integrity_checksum": "b" * 64,
            "required_wal_start_lsn": "0/1000000",
            "required_wal_end_lsn": "0/2000000",
            "earliest_verified_recovery_target": (now - timedelta(hours=1)).isoformat(),
            "latest_verified_recovery_target": now.isoformat(),
            "verification_state": "canonical_validated",
            "verification_checks": {
                "checksum": "verified",
                "schema": "verified",
            },
            "verification_details": {},
            "limitations": [],
            "missing_wal_segments": [],
            "historical_gaps": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }
        
        manifest = RecoveryManifest.from_dict(data)
        
        assert manifest.backup_id == "bkp-test"
        assert manifest.backup_method == "pgbackrest"
        assert manifest.postgresql_version == "18.2"
        assert manifest.verification_state == RecoveryManifestState.CANONICAL_VALIDATED
        assert manifest.verification_checks["checksum"] == RecoveryVerificationStatus.VERIFIED
        assert manifest.backup_start_time is not None
        assert manifest.backup_completion_time is not None
        assert manifest.earliest_verified_recovery_target is not None
        assert manifest.latest_verified_recovery_target is not None
    
    def test_manifest_round_trip(self):
        """Test serialization round-trip."""
        now = datetime.now(timezone.utc)
        original = RecoveryManifest(
            backup_id="bkp-roundtrip",
            backup_method="pg_basebackup",
            backup_format="directory",
            backup_start_time=now - timedelta(hours=2),
            backup_completion_time=now,
            postgresql_version="18.2",
            database_system_identifier="987654321",
            vcos_revision="2.0.0",
            backup_artifact_location="/backups/bkp-roundtrip",
            backup_artifact_size_bytes=1024 * 1024 * 200,
            backup_integrity_checksum="c" * 64,
            required_wal_start_lsn="0/500000",
            required_wal_end_lsn="0/600000",
            earliest_verified_recovery_target=now - timedelta(hours=2),
            latest_verified_recovery_target=now,
            verification_state=RecoveryManifestState.ACTIVATED,
            verification_checks={
                "checksum": RecoveryVerificationStatus.VERIFIED,
                "schema": RecoveryVerificationStatus.VERIFIED,
                "tenant_isolation": RecoveryVerificationStatus.VERIFIED,
            },
            limitations=["Missing historical segment 14"],
        )
        
        # Serialize to dict
        data = original.to_dict()
        
        # Deserialize
        restored = RecoveryManifest.from_dict(data)
        
        # Verify all fields match
        assert restored.backup_id == original.backup_id
        assert restored.backup_method == original.backup_method
        assert restored.backup_format == original.backup_format
        assert restored.postgresql_version == original.postgresql_version
        assert restored.database_system_identifier == original.database_system_identifier
        assert restored.vcos_revision == original.vcos_revision
        assert restored.backup_artifact_location == original.backup_artifact_location
        assert restored.backup_artifact_size_bytes == original.backup_artifact_size_bytes
        assert restored.backup_integrity_checksum == original.backup_integrity_checksum
        assert restored.required_wal_start_lsn == original.required_wal_start_lsn
        assert restored.required_wal_end_lsn == original.required_wal_end_lsn
        assert restored.verification_state == original.verification_state
        assert restored.verification_checks == original.verification_checks
        assert restored.limitations == original.limitations
    
    def test_manifest_to_json(self):
        """Test JSON serialization."""
        manifest = RecoveryManifest(
            backup_id="bkp-json",
            backup_method="pg_dump",
            postgresql_version="18.2",
        )
        
        json_str = manifest.to_json()
        assert isinstance(json_str, str)
        
        # Verify it's valid JSON
        data = json.loads(json_str)
        assert data["backup_id"] == "bkp-json"
        assert data["backup_method"] == "pg_dump"
        assert data["postgresql_version"] == "18.2"
    
    def test_manifest_from_json(self):
        """Test JSON deserialization."""
        now = datetime.now(timezone.utc)
        json_str = json.dumps({
            "manifest_schema_version": "1.0",
            "backup_id": "bkp-from-json",
            "backup_method": "pg_dump",
            "backup_format": "custom",
            "backup_start_time": (now - timedelta(hours=1)).isoformat(),
            "backup_completion_time": now.isoformat(),
            "postgresql_version": "18.2",
            "database_system_identifier": "111222333",
            "source_environment_identity": "test-host",
            "vcos_revision": "1.0.0",
            "schema_revision": "2026.10",
            "required_extensions": ["pg_trgm", "btree_gin", "uuid-ossp"],
            "backup_artifact_location": "/backups/bkp-from-json.sql.gz",
            "backup_artifact_size_bytes": 1024 * 1024 * 10,
            "backup_integrity_checksum": "d" * 64,
            "required_wal_start_lsn": "0/100000",
            "required_wal_end_lsn": "0/200000",
            "earliest_verified_recovery_target": (now - timedelta(hours=1)).isoformat(),
            "latest_verified_recovery_target": now.isoformat(),
            "verification_state": "restore_initialized",
            "verification_checks": {
                "checksum": "verified",
            },
            "verification_details": {},
            "limitations": ["Logical backup only - no PITR"],
            "missing_wal_segments": [],
            "historical_gaps": [],
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        })
        
        manifest = RecoveryManifest.from_json(json_str)
        
        assert manifest.backup_id == "bkp-from-json"
        assert manifest.backup_method == "pg_dump"
        assert manifest.backup_format == "custom"
        assert manifest.required_extensions == ["pg_trgm", "btree_gin", "uuid-ossp"]
        assert manifest.verification_state == RecoveryManifestState.RESTORE_INITIALIZED
        assert "Logical backup only - no PITR" in manifest.limitations
    
    def test_enum_values(self):
        """Test enum values."""
        assert RecoveryManifestState.CREATED.value == "created"
        assert RecoveryManifestState.BACKUP_VERIFIED.value == "backup_verified"
        assert RecoveryManifestState.CANONICAL_VALIDATED.value == "canonical_validated"
        assert RecoveryManifestState.ACTIVATED.value == "activated"
        assert RecoveryManifestState.FAILED.value == "failed"
        
        assert RecoveryVerificationStatus.NOT_STARTED.value == "not_started"
        assert RecoveryVerificationStatus.IN_PROGRESS.value == "in_progress"
        assert RecoveryVerificationStatus.VERIFIED.value == "verified"
        assert RecoveryVerificationStatus.FAILED.value == "failed"
        assert RecoveryVerificationStatus.BLOCKED.value == "blocked"
        assert RecoveryVerificationStatus.INCONCLUSIVE.value == "inconclusive"
        assert RecoveryVerificationStatus.SKIPPED.value == "skipped"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])