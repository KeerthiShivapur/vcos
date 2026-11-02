"""Tests for Acceptance Firewall."""

import pytest
from tests.scale.acceptance_firewall import (
    AcceptanceFirewall,
    FirewallVerdict,
    FirewallRule,
    evaluate_acceptance,
)
from tests.scale.acceptance_evidence import (
    ScaleAcceptanceEvidence,
    AcceptanceResult,
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
    ConcurrencyEvidence,
    create_acceptance_evidence,
)


class TestFirewallRules:
    
    def test_firewall_rules_exist(self):
        firewall = AcceptanceFirewall()
        assert len(firewall._rules) > 0
    
    def test_all_mandatory_domains_covered(self):
        firewall = AcceptanceFirewall()
        
        mandatory_domains = set()
        for rule in firewall._rules:
            if rule.mandatory:
                mandatory_domains.add(rule.domain)
        
        expected = {
            "environment", "generation", "structural_integrity", "tenant_isolation",
            "temporal", "provenance", "epistemic", "governance", "company_brain",
            "resource", "recovery",
        }
        
        assert expected.issubset(mandatory_domains), f"Missing mandatory domains: {expected - mandatory_domains}"
    
    def test_optional_domains_not_mandatory(self):
        firewall = AcceptanceFirewall()
        
        optional_domains = set()
        for rule in firewall._rules:
            if not rule.mandatory:
                optional_domains.add(rule.domain)
        
        # performance and promotion are optional
        assert "performance" in optional_domains or "promotion" in optional_domains


class TestAcceptanceFirewall:
    
    def _create_passing_evidence(self) -> ScaleAcceptanceEvidence:
        """Create evidence that should pass all checks."""
        evidence = create_acceptance_evidence(
            run_id="test_pass",
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
        
        # All mandatory checks passed
        evidence.mandatory_checks = {
            "environment_preflight": True,
            "generation_complete": True,
            "structural_integrity": True,
            "tenant_isolation": True,
            "temporal_integrity": True,
            "provenance": True,
            "epistemic_integrity": True,
            "governance": True,
            "company_brain": True,
            "performance_measurement": True,
            "cleanup": True,
            "checkpoint_state_preserved": True,
            "duplicate_prevention_verified": True,
            "safe_cleanup_performed": True,
        }
        
        evidence.environment = EnvironmentEvidence(
            postgresql_version="PostgreSQL 16.0",
            environment_type="external",
            endpoint_identifier="host:5432/db",
            extensions=[{"name": "pg_trgm", "version": "1.6"}],
            configuration_fingerprint="fp_123",
        )
        
        evidence.generation = GenerationEvidence(
            entities_generated={"employees": 10000},
            total_rows=10000,
            generation_duration_seconds=120.0,
            throughput_rows_per_second=83.0,
            checkpoint_completion={},
            retry_count=0,
        )
        
        evidence.structural_integrity = StructuralIntegrityEvidence(
            fk_validation_passed=True,
            required_fields_passed=True,
            enum_validity_passed=True,
            duplicate_fingerprints=0,
            organization_ownership_passed=True,
        )
        
        evidence.tenant_isolation = TenantIsolationEvidence(
            read_isolation_passed=True,
            write_isolation_passed=True,
            entities_tested=35,
            cross_tenant_attempts=0,
            blocked_attempts=0,
            successful_unauthorized_attempts=0,
        )
        
        evidence.temporal = TemporalEvidence(
            recorded_at_coherent=True,
            observed_at_coherent=True,
            effective_from_coherent=True,
            effective_to_coherent=True,
            supersession_valid=True,
            ordering_coherent=True,
        )
        
        evidence.provenance = ProvenanceEvidence(
            external_sources_tracked=True,
            source_identities_preserved=True,
            source_timestamps_preserved=True,
            provenance_relationships_intact=True,
            external_boundaries_respected=True,
        )
        
        evidence.epistemic = EpistemicEvidence(
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
        
        evidence.governance = GovernanceEvidence(
            canonical_authorization_used=True,
            no_scale_specific_auth=True,
            access_control_validated=True,
            permission_resolution_validated=True,
        )
        
        evidence.company_brain = CompanyBrainEvidence(
            canonical_reality_intact=True,
            context_retrieval_works=True,
            projection_over_reality=True,
            query_intelligence_works=True,
            tenant_scope_respected=True,
            governance_respected=True,
            not_separate_intelligence_system=True,
        )
        
        evidence.resources = ResourceEvidence(
            connections_used=10,
            peak_connections=15,
            cleanup_completed=True,
            resource_leaks=[],
            connection_leaks=0,
        )
        
        evidence.recovery = RecoveryEvidence(
            checkpoint_state_preserved=True,
            duplicate_prevention_verified=True,
            safe_cleanup_performed=True,
        )
        
        evidence.promotion = PromotionEvidence(
            required_checks_passed=["generation_complete", "integrity_validated"],
            blocked_checks_failed=[],
            promotion_allowed=True,
            next_target="25k",
        )
        
        evidence.concurrency = ConcurrencyEvidence(
            atomic_create_verified=True,
            concurrent_create_10_passed=True,
            concurrent_create_100_passed=True,
            atomic_update_verified=True,
            concurrent_update_10_passed=True,
            concurrent_update_100_passed=True,
            worker_lease_contention_verified=True,
            lease_expiry_verified=True,
            advisory_lock_contention_verified=True,
            worker_crash_unknown_preserved=True,
            gate32_recovery_verified=True,
            authorization_race_verified=True,
            tenant_isolation_under_concurrency=True,
        )
        
        return evidence
    
    def test_passing_evidence_passes_firewall(self):
        evidence = self._create_passing_evidence()
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.PASS
        assert result.mandatory_passed == result.mandatory_total
    
    def test_missing_environment_evidence_fails(self):
        evidence = self._create_passing_evidence()
        evidence.environment = None  # Missing mandatory domain
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
        assert result.mandatory_passed < result.mandatory_total
    
    def test_missing_generation_evidence_fails(self):
        evidence = self._create_passing_evidence()
        evidence.generation = None
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_failed_structural_integrity_fails(self):
        evidence = self._create_passing_evidence()
        evidence.structural_integrity.fk_validation_passed = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_unauthorized_tenant_access_fails(self):
        evidence = self._create_passing_evidence()
        evidence.tenant_isolation.successful_unauthorized_attempts = 1
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_missing_tenant_isolation_fails(self):
        evidence = self._create_passing_evidence()
        evidence.tenant_isolation = None
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_epistemic_collapse_to_confidence_fails(self):
        evidence = self._create_passing_evidence()
        evidence.epistemic.not_collapsed_to_confidence = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_cleanup_not_completed_fails(self):
        evidence = self._create_passing_evidence()
        evidence.resources.cleanup_completed = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_resource_leaks_fails(self):
        evidence = self._create_passing_evidence()
        evidence.resources.resource_leaks = ["leaked_session_1", "leaked_cursor_1"]
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_connection_leaks_fails(self):
        evidence = self._create_passing_evidence()
        evidence.resources.connection_leaks = 2
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_duplicate_fingerprints_fails(self):
        evidence = self._create_passing_evidence()
        evidence.structural_integrity.duplicate_fingerprints = 5
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_environment_preflight_failed_fails(self):
        evidence = self._create_passing_evidence()
        evidence.mandatory_checks["environment_preflight"] = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_generation_incomplete_fails(self):
        evidence = self._create_passing_evidence()
        evidence.mandatory_checks["generation_complete"] = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_temporal_integrity_failed_fails(self):
        evidence = self._create_passing_evidence()
        evidence.temporal.recorded_at_coherent = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_provenance_failed_fails(self):
        evidence = self._create_passing_evidence()
        evidence.provenance.external_sources_tracked = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_governance_failed_fails(self):
        evidence = self._create_passing_evidence()
        evidence.governance.canonical_authorization_used = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_company_brain_not_projection_fails(self):
        evidence = self._create_passing_evidence()
        evidence.company_brain.projection_over_reality = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_cleanup_not_performed_fails(self):
        evidence = self._create_passing_evidence()
        evidence.recovery.safe_cleanup_performed = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_checkpoint_state_not_preserved_fails(self):
        evidence = self._create_passing_evidence()
        evidence.recovery.checkpoint_state_preserved = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_duplicate_prevention_not_verified_fails(self):
        evidence = self._create_passing_evidence()
        evidence.recovery.duplicate_prevention_verified = False
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL
    
    def test_deterministic_results(self):
        """Same evidence should always produce same result."""
        evidence = self._create_passing_evidence()
        
        firewall1 = AcceptanceFirewall()
        result1 = firewall1.evaluate(evidence)
        
        firewall2 = AcceptanceFirewall()
        result2 = firewall2.evaluate(evidence)
        
        assert result1.verdict == result2.verdict
        assert result1.mandatory_passed == result2.mandatory_passed
        assert len(result1.check_results) == len(result2.check_results)
        
        for c1, c2 in zip(result1.check_results, result2.check_results):
            assert c1.passed == c2.passed
            assert c1.rule.domain == c2.rule.domain
            assert c1.rule.check_name == c2.rule.check_name
    
    def test_firewall_result_serialization(self):
        evidence = self._create_passing_evidence()
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        data = result.to_dict()
        
        assert data["verdict"] == "PASS"
        assert "checks" in data
        assert data["mandatory_passed"] == data["mandatory_total"]
        assert "summary" in data
    
    def test_convenience_function(self):
        evidence = self._create_passing_evidence()
        result = evaluate_acceptance(evidence)
        
        assert result.verdict == FirewallVerdict.PASS
        assert isinstance(result, type(evaluate_acceptance(evidence)))
    
    def test_evidence_with_acceptance_result_blocked(self):
        evidence = self._create_passing_evidence()
        evidence.acceptance_result = AcceptanceResult.BLOCKED
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        # BLOCKED from evidence should map to BLOCKED verdict
        assert result.verdict == FirewallVerdict.BLOCKED
    
    def test_evidence_with_acceptance_result_invalid(self):
        evidence = self._create_passing_evidence()
        evidence.acceptance_result = AcceptanceResult.INVALID
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.INVALID
    
    def test_evidence_with_acceptance_result_inconclusive(self):
        evidence = self._create_passing_evidence()
        evidence.acceptance_result = AcceptanceResult.INCONCLUSIVE
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.INCONCLUSIVE
    
    def test_evidence_with_acceptance_result_fail(self):
        evidence = self._create_passing_evidence()
        evidence.acceptance_result = AcceptanceResult.FAIL
        
        firewall = AcceptanceFirewall()
        result = firewall.evaluate(evidence)
        
        assert result.verdict == FirewallVerdict.FAIL


class TestFirewallVerdictMapping:
    
    def test_firewall_verdict_values(self):
        assert FirewallVerdict.PASS.value == "PASS"
        assert FirewallVerdict.FAIL.value == "FAIL"
        assert FirewallVerdict.BLOCKED.value == "BLOCKED"
        assert FirewallVerdict.INVALID.value == "INVALID"
        assert FirewallVerdict.INCONCLUSIVE.value == "INCONCLUSIVE"
    
    def test_firewall_rule_equality(self):
        rule1 = FirewallRule(domain="test", check_name="check1", description="desc", mandatory=True)
        rule2 = FirewallRule(domain="test", check_name="check1", description="desc", mandatory=True)
        rule3 = FirewallRule(domain="test", check_name="check2", description="desc", mandatory=True)
        
        assert rule1 == rule2
        assert rule1 != rule3
        assert hash(rule1) == hash(rule2)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])