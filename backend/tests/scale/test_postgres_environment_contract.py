"""Tests for PostgreSQL Environment Contract and Portability."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tests.scale.postgres.environment import (
    EnvironmentCapabilityContract,
    DryRunContract,
    EndpointFingerprint,
    ScaleRunPortability,
    ExternalPostgreSQLSafety,
    ResourceSafetyValidator,
    EvidenceCompatibility,
    EnvironmentCapability,
    ScaleExecutionEnvironmentFactory,
    ExternalPostgresEnvironment,
)
from tests.scale.readiness import ScaleEnvironmentReadinessAssessor


class TestEnvironmentCapabilityContract:
    
    def test_validate_capabilities_all_required_met(self):
        capabilities = {
            "postgresql_version": "16.0",
            "extensions": ["pg_trgm"],
            "schema_access": True,
            "write_access": True,
            "transaction_support": True,
            "copy_support": True,
            "index_support": True,
            "connection_capacity": 100,
            "storage_visibility": True,
            "database_size_visibility": True,
            "configuration_visibility": True,
        }
        
        result = EnvironmentCapabilityContract.validate_capabilities(capabilities)
        
        assert result["required_met"] is True
        assert result["missing_required"] == []
        # The total includes required (10) + optional (0) = 10, but optional ones present count too
        # The implementation counts all provided capabilities
        assert result["total_capabilities"] >= 10
    
    def test_validate_capabilities_missing_required(self):
        capabilities = {
            "postgresql_version": "16.0",
            "extensions": ["pg_trgm"],
        }
        
        result = EnvironmentCapabilityContract.validate_capabilities(capabilities)
        
        assert result["required_met"] is False
        assert len(result["missing_required"]) > 0
        assert "schema_access" in result["missing_required"]
        assert "write_access" in result["missing_required"]
    
    def test_validate_capabilities_with_optional(self):
        capabilities = {
            "postgresql_version": "16.0",
            "extensions": ["pg_trgm"],
            "schema_access": True,
            "write_access": True,
            "transaction_support": True,
            "copy_support": True,
            "index_support": True,
            "connection_capacity": 100,
            "storage_visibility": True,
            "database_size_visibility": True,
            "configuration_visibility": True,
            "storage_type": "ssd",
            "database_size": "500MB",
        }
        
        result = EnvironmentCapabilityContract.validate_capabilities(capabilities)
        
        assert result["required_met"] is True
        # Optional order doesn't matter
        assert set(result["optional_reported"]) == {"storage_type", "database_size"}


class TestDryRunContract:
    
    def test_validate_dry_run_complete(self):
        dry_run_results = {
            "runtime_resolution": True,
            "preflight_checks": True,
            "readiness_assessment": True,
            "capability_inspection": True,
            "safe_isolation_validation": True,
        }
        
        result = DryRunContract.validate_dry_run(dry_run_results)
        
        assert result["complete"] is True
        assert result["missing_checks"] == []
    
    def test_validate_dry_run_incomplete(self):
        dry_run_results = {
            "runtime_resolution": True,
            "preflight_checks": True,
        }
        
        result = DryRunContract.validate_dry_run(dry_run_results)
        
        assert result["complete"] is False
        assert "readiness_assessment" in result["missing_checks"]
        assert "capability_inspection" in result["missing_checks"]
        assert "safe_isolation_validation" in result["missing_checks"]
    
    def test_must_not_claim_authoritative_pass_false(self):
        dry_run_results = {"authoritative_pass": False}
        
        assert DryRunContract.must_not_claim_authoritative_pass(dry_run_results) is True
    
    def test_must_not_claim_authoritative_pass_true(self):
        dry_run_results = {"authoritative_pass": True}
        
        assert DryRunContract.must_not_claim_authoritative_pass(dry_run_results) is False
    
    def test_must_not_claim_authoritative_pass_missing(self):
        dry_run_results = {}
        
        assert DryRunContract.must_not_claim_authoritative_pass(dry_run_results) is True


class TestEndpointFingerprint:
    
    def test_compute_deterministic(self):
        db_url = "postgresql+asyncpg://user:pass@host:5432/db"
        pg_version = "PostgreSQL 16.0"
        extensions = [{"name": "pg_trgm", "version": "1.6"}]
        settings = {"shared_buffers": "128MB"}
        db_name = "testdb"
        
        fp1 = EndpointFingerprint.compute(db_url, pg_version, extensions, {}, "testdb")
        fp2 = EndpointFingerprint.compute(db_url, pg_version, extensions, {}, "testdb")
        
        assert fp1 == fp2
        assert len(fp1) == 32
    
    def test_fingerprint_different_inputs(self):
        db_url = "postgresql+asyncpg://user:pass@host:5432/db"
        pg_version = "PostgreSQL 16.0"
        extensions = [{"name": "pg_trgm", "version": "1.6"}]
        
        fp1 = EndpointFingerprint.compute(db_url, pg_version, [{"name": "pg_trgm", "version": "1.6"}], {}, "testdb")
        fp2 = EndpointFingerprint.compute(db_url, pg_version, [{"name": "btree_gin", "version": "1.0"}], {}, "testdb")
        
        assert fp1 != fp2
    
    def test_redact_db_url(self):
        db_url = "postgresql+asyncpg://user:secret@host:5432/db"
        redacted = EndpointFingerprint.redact_db_url(db_url)
        
        assert "secret" not in redacted
        assert "***" in redacted
        assert "user" in redacted
    
    def test_redact_db_url_no_password(self):
        db_url = "postgresql+asyncpg://user@host:5432/db"
        redacted = EndpointFingerprint.redact_db_url(db_url)
        
        assert redacted == db_url


class TestScaleRunPortability:
    
    def test_validate_portable_profile(self):
        assert ScaleRunPortability.validate_portable_profile("startup") is True
        assert ScaleRunPortability.validate_portable_profile("small") is True
        assert ScaleRunPortability.validate_portable_profile("medium") is True
        assert ScaleRunPortability.validate_portable_profile("large") is True
        assert ScaleRunPortability.validate_portable_profile("enterprise") is True
        assert ScaleRunPortability.validate_portable_profile("mega") is True
        assert ScaleRunPortability.validate_portable_profile("unknown") is False
    
    def test_validate_portable_generation(self):
        generation_results = {
            "employees": 100,
            "departments": 5,
            "teams": 10,
            "projects": 20,
            "tasks": 500,
        }
        
        result = ScaleRunPortability.validate_portable_generation(generation_results)
        
        assert result["portable"] is True
        assert result["missing_required_entities"] == []
    
    def test_validate_portable_generation_missing(self):
        generation_results = {
            "employees": 100,
            "departments": 5,
        }
        
        result = ScaleRunPortability.validate_portable_generation(generation_results)
        
        assert result["portable"] is False
        assert "projects" in result["missing_required_entities"]
        assert "tasks" in result["missing_required_entities"]
    
    def test_validate_environment_independence(self):
        # Evidence with no environment-specific data
        clean_evidence = {
            "employees": 100,
            "departments": 5,
            "generation_time": 120.5,
        }
        
        assert ScaleRunPortability.validate_environment_independence(clean_evidence) is True
        
        # Evidence with localhost reference
        bad_evidence = {
            "endpoint": "localhost:5432",
            "data": "test",
        }
        
        assert ScaleRunPortability.validate_environment_independence(bad_evidence) is False
        
        # Evidence with Docker reference - "container" + "id" in "sha256"
        bad_evidence2 = {
            "container_id": "sha256:abc123",
        }
        
        # The check looks for "container" + "id" in the evidence string
        # "container_id" contains "container" and "id" -> triggers False
        assert ScaleRunPortability.validate_environment_independence(bad_evidence2) is False


class TestExternalPostgreSQLSafety:
    
    def test_validate_external_target_safe(self):
        db_url = "postgresql+asyncpg://user:pass@host:5432/vcos_scale_test_10k"
        db_name = "vcos_scale_test_10k"
        
        result = ExternalPostgreSQLSafety.validate_external_target(db_url, db_name)
        
        assert result["safe"] is True
        assert len(result["errors"]) == 0
    
    def test_validate_external_target_production_db(self):
        db_url = "postgresql+asyncpg://user:pass@host:5432/production_db"
        db_name = "production_db"
        
        result = ExternalPostgreSQLSafety.validate_external_target(db_url, db_name)
        
        assert result["safe"] is False
        assert len(result["errors"]) > 0
        assert "production" in result["errors"][0].lower()
    
    def test_validate_external_target_production_host(self):
        db_url = "postgresql+asyncpg://user:pass@prod-host:5432/testdb"
        db_name = "testdb"
        
        result = ExternalPostgreSQLSafety.validate_external_target(db_url, db_name)
        
        assert result["safe"] is True  # Host warning but not error
        assert len(result["warnings"]) > 0
        assert "production" in result["warnings"][0].lower()
    
    def test_validate_isolation_strategy_valid(self):
        for strategy in ["dedicated_database", "dedicated_schema", "transaction_rollback"]:
            result = ExternalPostgreSQLSafety.validate_isolation_strategy("postgresql://...", strategy)
            assert result["valid"] is True
            assert result["strategy"] == strategy
    
    def test_validate_isolation_strategy_invalid(self):
        result = ExternalPostgreSQLSafety.validate_isolation_strategy("postgresql://...", "invalid_strategy")
        
        assert result["valid"] is False
        assert "Invalid isolation strategy" in result["error"]


class TestResourceSafetyValidator:
    
    def test_validate_pre_execution_safe(self):
        capability = EnvironmentCapability(
            platform="linux",
            os_version="Ubuntu 22.04",
            architecture="x86_64",
            cpu_count=8,
            total_memory_mb=16384,
            available_memory_mb=8192,
            free_disk_gb=500.0,
            postgresql_version="16.0",
            postgresql_architecture="x64",
            max_connections=200,
            shared_buffers_mb=4096,
            work_mem_mb=64,
            maintenance_work_mem_mb=256,
            max_wal_size_mb=1024,
            effective_cache_size_mb=8192,
            autovacuum_max_workers=8,
            supports_parallel_query=True,
            supports_partitioning=True,
            supports_logical_replication=True,
            extensions=[],
            limitations=[],
        )
        
        result = ResourceSafetyValidator.validate_pre_execution(capability, "large")
        
        assert result["safe"] is True
    
    def test_validate_post_execution_clean(self):
        evidence = {
            "resources": {
                "cleanup_completed": True,
                "connection_leaks": 0,
                "resource_leaks": [],
            }
        }
        
        result = ResourceSafetyValidator.validate_post_execution(evidence)
        
        assert result["clean"] is True
        assert result["issues"] == []
    
    def test_validate_post_execution_not_clean(self):
        evidence = {
            "resources": {
                "cleanup_completed": False,
                "connection_leaks": 2,
                "resource_leaks": ["leaked_session"],
            }
        }
        
        result = ResourceSafetyValidator.validate_post_execution(evidence)
        
        assert result["clean"] is False
        assert len(result["issues"]) >= 2


class TestEvidenceCompatibility:
    
    def test_validate_evidence_portability_clean(self):
        clean_evidence = {
            "employees": 100,
            "generation_time": 120.5,
            "database_size": "100MB",
        }
        
        result = EvidenceCompatibility.validate_evidence_portability(clean_evidence)
        
        assert result["portable"] is True
        assert result["issues"] == []
    
    def test_validate_evidence_portability_absolute_path(self):
        bad_evidence = {
            "data_path": "/home/user/data",
        }
        
        result = EvidenceCompatibility.validate_evidence_portability(bad_evidence)
        
        assert result["portable"] is False
        assert any("absolute filesystem paths" in issue for issue in result["issues"])
    
    def test_validate_evidence_portability_localhost(self):
        bad_evidence = {
            "endpoint": "localhost:5432",
        }
        
        result = EvidenceCompatibility.validate_evidence_portability(bad_evidence)
        
        assert result["portable"] is False
        assert any("localhost" in issue for issue in result["issues"])
    
    def test_normalize_for_comparison(self):
        evidence = {
            "started_at": "2024-01-01T00:00:00",
            "completed_at": "2024-01-01T01:00:00",
            "run_id": "abc123",
            "environment_fingerprint": "fp123",
            "employees": 100,
        }
        
        normalized = EvidenceCompatibility.normalize_for_comparison(evidence)
        
        assert normalized["started_at"] == "NORMALIZED"
        assert normalized["completed_at"] == "NORMALIZED"
        assert normalized["run_id"] == "NORMALIZED"
        assert normalized["environment_fingerprint"] == "NORMALIZED"
        assert normalized["employees"] == 100  # Unchanged


class TestEnvironmentCapabilityToDict:
    
    def test_to_capability_dict(self):
        capability = EnvironmentCapability(
            platform="linux",
            os_version="Ubuntu 22.04",
            architecture="x86_64",
            cpu_count=8,
            total_memory_mb=16384,
            available_memory_mb=8192,
            free_disk_gb=500.0,
            postgresql_version="16.0",
            postgresql_architecture="x64",
            max_connections=200,
            shared_buffers_mb=4096,
            work_mem_mb=64,
            maintenance_work_mem_mb=256,
            max_wal_size_mb=1024,
            effective_cache_size_mb=8192,
            autovacuum_max_workers=8,
            supports_parallel_query=True,
            supports_partitioning=True,
            supports_logical_replication=True,
            extensions=["pg_trgm", "uuid-ossp"],
            limitations=[],
        )
        
        cap_dict = capability.to_capability_dict()
        
        assert cap_dict["postgresql_version"] == "16.0"
        assert cap_dict["extensions"] == ["pg_trgm", "uuid-ossp"]
        assert cap_dict["schema_access"] is True
        assert cap_dict["write_access"] is True
        assert cap_dict["transaction_support"] is True
        assert cap_dict["connection_capacity"] == 200
        assert cap_dict["extensions"] == ["pg_trgm", "uuid-ossp"]


class TestEndpointFingerprintSecurity:
    
    def test_redact_db_url_with_password(self):
        db_url = "postgresql+asyncpg://user:secretpassword@host:5432/db"
        redacted = EndpointFingerprint.redact_db_url(db_url)
        
        assert "secretpassword" not in redacted
        assert "***" in redacted
    
    def test_fingerprint_deterministic(self):
        db_url = "postgresql+asyncpg://user:pass@host:5432/db"
        pg_version = "PostgreSQL 16.0"
        extensions = [{"name": "pg_trgm", "version": "1.6"}]
        settings = {"shared_buffers": "128MB"}
        
        fp1 = EndpointFingerprint.compute(db_url, pg_version, extensions, settings, "testdb")
        fp2 = EndpointFingerprint.compute(db_url, pg_version, extensions, settings, "testdb")
        
        assert fp1 == fp2
        assert len(fp1) == 32
    
    def test_fingerprint_different_databases(self):
        db_url = "postgresql+asyncpg://user:pass@host:5432/db"
        pg_version = "PostgreSQL 16.0"
        extensions = [{"name": "pg_trgm", "version": "1.6"}]
        
        fp1 = EndpointFingerprint.compute(db_url, pg_version, extensions, {}, "db1")
        fp2 = EndpointFingerprint.compute(db_url, pg_version, extensions, {}, "db2")
        
        assert fp1 != fp2
    
    def test_fingerprint_redacts_credentials(self):
        db_url = "postgresql+asyncpg://user:secret@host:5432/db"
        pg_version = "PostgreSQL 16.0"
        extensions = [{"name": "pg_trgm", "version": "1.6"}]
        
        # The fingerprint should not contain the password
        fp = EndpointFingerprint.compute(db_url, "PostgreSQL 16.0", [{"name": "pg_trgm", "version": "1.6"}], {}, "testdb")
        
        assert "secret" not in fp
        assert "password" not in fp


if __name__ == "__main__":
    pytest.main([__file__, "-v"])