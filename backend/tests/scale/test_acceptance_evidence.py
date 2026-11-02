"""Tests for Scale Acceptance Evidence."""

import pytest
import json
from tests.scale.acceptance_evidence import (
    ScaleAcceptanceEvidence,
    AcceptanceResult,
    EvidenceSchemaVersion,
    EnvironmentEvidence,
    GenerationEvidence,
    StructuralIntegrityEvidence,
    TenantIsolationEvidence,
    TemporalEvidence,
    ProvenanceEvidence,
    EpistemicEvidence,
    GovernanceEvidence,
    CompanyBrainEvidence,
    PerformanceEvidence,
    ResourceEvidence,
    RecoveryEvidence,
    PromotionEvidence,
    create_acceptance_evidence,
)


class TestScaleAcceptanceEvidence:
    
    def test_evidence_creation(self):
        evidence = create_acceptance_evidence(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
        )
        
        assert evidence.run_id == "test_123"
        assert evidence.scale_profile == "large_10k"
        assert evidence.employee_count == 10000
        assert evidence.evidence_schema_version == "1.0"
        assert evidence.started_at != ""
    
    def test_evidence_serialization(self):
        evidence = create_acceptance_evidence(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
        )
        
        evidence.environment = EnvironmentEvidence(
            postgresql_version="PostgreSQL 16.0",
            environment_type="external",
            endpoint_identifier="host:5432",
            extensions=[{"name": "pg_trgm", "version": "1.6"}],
            configuration_fingerprint="fp_123",
        )
        
        evidence.generation = GenerationEvidence(
            entities_generated={"employees": 10000},
            total_rows=10000,
            generation_duration_seconds=120.5,
            throughput_rows_per_second=83.0,
            checkpoint_completion={"employees": True},
            retry_count=0,
        )
        
        json_str = evidence.to_json()
        assert "test_123" in json_str
        assert "large_10k" in json_str
        assert "PostgreSQL 16.0" in json_str
    
    def test_evidence_deserialization(self):
        evidence = create_acceptance_evidence(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
        )
        
        evidence.environment = EnvironmentEvidence(
            postgresql_version="PostgreSQL 16.0",
            environment_type="external",
            endpoint_identifier="host:5432",
            extensions=[{"name": "pg_trgm", "version": "1.6"}],
            configuration_fingerprint="fp_123",
        )
        
        json_str = evidence.to_json()
        restored = ScaleAcceptanceEvidence.from_json(json_str)
        
        assert restored.run_id == evidence.run_id
        assert restored.scale_profile == evidence.scale_profile
        assert restored.employee_count == evidence.employee_count
        assert restored.environment.postgresql_version == "PostgreSQL 16.0"
    
    def test_deterministic_fingerprint(self):
        evidence1 = create_acceptance_evidence(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
        )
        
        evidence2 = create_acceptance_evidence(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
        )
        
        assert evidence1.get_fingerprint() == evidence2.get_fingerprint()
    
    def test_acceptance_determination(self):
        evidence = create_acceptance_evidence(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
        )
        
        # No mandatory checks -> INCONCLUSIVE
        assert evidence.determine_acceptance() == AcceptanceResult.INCONCLUSIVE
        
        # All mandatory checks passed -> PASS
        evidence.set_mandatory_check("generation_complete", True)
        evidence.set_mandatory_check("integrity_validated", True)
        evidence.set_mandatory_check("tenant_isolation", True)
        assert evidence.determine_acceptance() == AcceptanceResult.PASS
        
        # One mandatory check failed -> FAIL
        evidence.set_mandatory_check("tenant_isolation", False)
        assert evidence.determine_acceptance() == AcceptanceResult.FAIL


class TestEvidenceDomains:
    
    def test_environment_evidence(self):
        env = EnvironmentEvidence(
            postgresql_version="PostgreSQL 16.0",
            environment_type="external",
            endpoint_identifier="host:5432",
            extensions=[{"name": "pg_trgm", "version": "1.6"}],
            configuration_fingerprint="fp_123",
        )
        
        data = env.to_dict()
        assert data["postgresql_version"] == "PostgreSQL 16.0"
        assert data["environment_type"] == "external"
    
    def test_generation_evidence(self):
        gen = GenerationEvidence(
            entities_generated={"employees": 10000, "departments": 15},
            total_rows=10015,
            generation_duration_seconds=120.5,
            throughput_rows_per_second=83.0,
            checkpoint_completion={"employees": True},
            retry_count=0,
        )
        
        assert gen.total_rows == 10015
        assert gen.throughput_rows_per_second == 83.0
    
    def test_structural_integrity_evidence(self):
        si = StructuralIntegrityEvidence(
            fk_validation_passed=True,
            required_fields_passed=True,
            enum_validity_passed=True,
            duplicate_fingerprints=0,
            organization_ownership_passed=True,
        )
        
        assert si.all_passed() is True
        
        si2 = StructuralIntegrityEvidence(
            fk_validation_passed=True,
            required_fields_passed=True,
            enum_validity_passed=True,
            duplicate_fingerprints=1,  # Has duplicates
            organization_ownership_passed=True,
        )
        
        assert si2.all_passed() is False
    
    def test_tenant_isolation_evidence(self):
        ti = TenantIsolationEvidence(
            read_isolation_passed=True,
            write_isolation_passed=True,
            entities_tested=35,
            cross_tenant_attempts=0,
            blocked_attempts=0,
            successful_unauthorized_attempts=0,
        )
        
        assert ti.all_passed() is True
        
        ti2 = TenantIsolationEvidence(
            read_isolation_passed=True,
            write_isolation_passed=True,
            entities_tested=35,
            cross_tenant_attempts=5,
            blocked_attempts=5,
            successful_unauthorized_attempts=1,  # Unauthorized access!
        )
        
        assert ti2.all_passed() is False
    
    def test_temporal_evidence(self):
        temp = TemporalEvidence(
            recorded_at_coherent=True,
            observed_at_coherent=True,
            effective_from_coherent=True,
            effective_to_coherent=True,
            supersession_valid=True,
            ordering_coherent=True,
        )
        
        assert temp.all_passed() is True
    
    def test_provenance_evidence(self):
        prov = ProvenanceEvidence(
            external_sources_tracked=True,
            source_identities_preserved=True,
            source_timestamps_preserved=True,
            provenance_relationships_intact=True,
            external_boundaries_respected=True,
        )
        
        assert prov.all_passed() is True
    
    def test_epistemic_evidence(self):
        epist = EpistemicEvidence(
            confirmed_preserved=True,
            supported_preserved=True,
            historical_preserved=True,
            corrected_preserved=True,
            conflicting_preserved=True,
            predicted_preserved=True,
            expected_preserved=True,
            unknown_preserved=True,
            not_collapsed_to_confidence=True,
        )
        
        assert epist.all_passed() is True
    
    def test_governance_evidence(self):
        gov = GovernanceEvidence(
            canonical_authorization_used=True,
            no_scale_specific_auth=True,
            access_control_validated=True,
            permission_resolution_validated=True,
        )
        
        assert gov.all_passed() is True
    
    def test_company_brain_evidence(self):
        cb = CompanyBrainEvidence(
            canonical_reality_intact=True,
            context_retrieval_works=True,
            projection_over_reality=True,
            query_intelligence_works=True,
            tenant_scope_respected=True,
            governance_respected=True,
            not_separate_intelligence_system=True,
        )
        
        assert cb.all_passed() is True
    
    def test_performance_evidence(self):
        perf = PerformanceEvidence(
            generation_duration_seconds=120.5,
            database_size_mb=500.0,
            index_size_mb=100.0,
            throughput_rows_per_second=83.0,
            query_latency_p50_ms=10.0,
            query_latency_p95_ms=50.0,
            query_latency_p99_ms=100.0,
            fts_latency_ms=25.0,
            cursor_pagination_latency_ms=5.0,
            company_brain_context_latency_ms=15.0,
            integrity_validation_duration_seconds=30.0,
            cleanup_duration_seconds=5.0,
        )
        
        assert perf.throughput_rows_per_second == 83.0
    
    def test_resource_evidence(self):
        res = ResourceEvidence(
            connections_used=10,
            peak_connections=15,
            memory_mb=256.0,
            wal_mb=50.0,
            cleanup_completed=True,
            resource_leaks=[],
            connection_leaks=0,
        )
        
        assert res.all_passed() is True
        
        res2 = ResourceEvidence(
            connections_used=10,
            peak_connections=15,
            cleanup_completed=False,  # Not cleaned up!
        )
        
        assert res2.all_passed() is False
    
    def test_recovery_evidence(self):
        rec = RecoveryEvidence(
            retry_count=0,
            checkpoint_state_preserved=True,
            duplicate_prevention_verified=True,
            safe_cleanup_performed=True,
        )
        
        assert rec.retry_count == 0
        assert rec.checkpoint_state_preserved is True
    
    def test_promotion_evidence(self):
        promo = PromotionEvidence(
            required_checks_passed=["generation_complete", "integrity_validated"],
            blocked_checks_failed=[],
            promotion_allowed=True,
            next_target="25k",
        )
        
        assert promo.promotion_allowed is True
        assert promo.next_target == "25k"


class TestSecretRedaction:
    
    def test_no_secrets_in_output(self):
        evidence = create_acceptance_evidence(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
        )
        
        evidence.environment = EnvironmentEvidence(
            postgresql_version="PostgreSQL 16.0",
            environment_type="external",
            endpoint_identifier="host:5432",
            extensions=[{"name": "pg_trgm", "version": "1.6"}],
            configuration_fingerprint="fp_123",
        )
        
        json_str = evidence.to_json()
        
        # Verify no secrets
        assert "password" not in json_str.lower()
        assert "token" not in json_str.lower()
        assert "secret" not in json_str.lower()
        assert "api_key" not in json_str.lower()
    
    def test_fingerprint_excludes_timestamps_and_result(self):
        evidence1 = create_acceptance_evidence(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
        )
        
        evidence2 = create_acceptance_evidence(
            run_id="test_123",
            scale_profile="large_10k",
            employee_count=10000,
            tenant_count=1,
            seed=42,
            dataset_identity={"hash": "abc123"},
            environment_fingerprint={"fp": "xyz789"},
            schema_revision="schema_v1",
            vcos_revision="abc123",
            generator_revision="gen_v1",
        )
        
        evidence1.acceptance_result = AcceptanceResult.PASS
        evidence1.completed_at = "2024-01-01T00:00:00"
        
        evidence2.acceptance_result = AcceptanceResult.FAIL
        evidence2.completed_at = "2024-01-02T00:00:00"
        
        # Fingerprint should be same despite different results/timestamps
        assert evidence1.get_fingerprint() == evidence2.get_fingerprint()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])