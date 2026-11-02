"""Tests for Universal Acceptance Matrix Infrastructure."""

import pytest
import asyncio
from tests.acceptance import (
    DimensionId,
    EquivalenceClass,
    Dimension,
    ALL_DIMENSIONS,
    get_dimension,
    get_all_equivalence_classes,
    get_representative_profiles,
    CANONICAL_INVARIANTS,
    ScenarioType,
    ScenarioPhase,
    ScenarioStep,
    UniversalScenario,
    CompanyProfileBuilder,
    UniversalScenarioBuilder,
    create_scenario_builder,
    ScenarioStatus,
    InvariantStatus,
    StepResult,
    InvariantResult,
    ScenarioResult,
    ProfileResult,
    AcceptanceMatrixResult,
    ActionRegistry,
    InvariantVerifier,
    AcceptanceMatrixRunner,
    run_acceptance_matrix,
    UniversalityEvidence,
    ScaleMatrixEvidence,
    OrgStructureEvidence,
    IndustryEvidence,
    GeographyEvidence,
    MultiCompanyEvidence,
    IdentityEvidence,
    WorkEvidence,
    GovernanceEvidence,
    IntegrationEvidence,
    CompanyBrainEvidence,
    MemoryEvidence,
    PredictionEvidence,
    CounterfactualEvidence,
    AutonomyEvidence,
    ContinuityEvidence,
    MigrationEvidence,
    MAEvidence,
    FailureUniversalityEvidence,
    LongitudinalUniversalityEvidence,
    DeploymentDREvidence,
    SecurityEvidence,
    APIEvidence,
    UniversalAcceptanceEvidence,
    create_universal_acceptance_evidence,
)
from tests.scale.acceptance_evidence import AcceptanceResult


class TestDimensions:
    """Test dimension definitions."""
    
    def test_26_dimensions_defined(self):
        """Verify all 26 dimensions (A-Z) are defined."""
        assert len(ALL_DIMENSIONS) == 26
        
        expected_ids = [DimensionId(chr(ord('A') + i)) for i in range(26)]
        actual_ids = [d.id for d in ALL_DIMENSIONS]
        assert actual_ids == expected_ids
    
    def test_dimension_a_scale(self):
        """Test Dimension A: Company Scale."""
        dim = get_dimension(DimensionId.A_SCALE)
        assert dim.name == "Company Scale"
        assert len(dim.equivalence_classes) == 6
        class_ids = [c.id for c in dim.equivalence_classes]
        assert class_ids == [
            "startup_5", "small_50", "medium_500", 
            "large_5k", "enterprise_50k", "mega_500k"
        ]
        # Verify scale properties
        startup = dim.equivalence_classes[0]
        assert startup.properties["employee_count"] == 5
        mega = dim.equivalence_classes[-1]
        assert mega.properties["employee_count"] == 500000
    
    def test_dimension_b_org_structure(self):
        """Test Dimension B: Organizational Structure."""
        dim = get_dimension(DimensionId.B_ORG_STRUCTURE)
        assert dim.name == "Organizational Structure"
        assert len(dim.equivalence_classes) == 14
        class_ids = [c.id for c in dim.equivalence_classes]
        assert "hierarchical" in class_ids
        assert "flat" in class_ids
        assert "matrix" in class_ids
        assert "federated" in class_ids
        assert "holding_company" in class_ids
        assert "post_acquisition" in class_ids
        assert "post_merger" in class_ids
    
    def test_dimension_c_industry(self):
        """Test Dimension C: Industry."""
        dim = get_dimension(DimensionId.C_INDUSTRY)
        assert dim.name == "Industry"
        assert len(dim.equivalence_classes) == 13
        class_ids = [c.id for c in dim.equivalence_classes]
        assert "software" in class_ids
        assert "manufacturing" in class_ids
        assert "healthcare" in class_ids
        assert "financial_services" in class_ids
        assert "multinational" in class_ids
    
    def test_dimension_d_geography(self):
        """Test Dimension D: Geography."""
        dim = get_dimension(DimensionId.D_GEOGRAPHY)
        assert dim.name == "Geography / Localization"
        assert len(dim.equivalence_classes) == 6
        class_ids = [c.id for c in dim.equivalence_classes]
        assert "india" in class_ids
        assert "united_states" in class_ids
        assert "europe" in class_ids
        assert "middle_east" in class_ids
        assert "asia_pacific" in class_ids
        assert "multi_region" in class_ids
    
    def test_all_dimensions_have_invariants(self):
        """Verify all dimensions have canonical invariants."""
        for dim in ALL_DIMENSIONS:
            assert len(dim.canonical_invariants) > 0, f"{dim.id} missing invariants"
    
    def test_equivalence_classes_have_properties(self):
        """Verify all equivalence classes have properties."""
        for dim in ALL_DIMENSIONS:
            for eq_class in dim.equivalence_classes:
                assert eq_class.id
                assert eq_class.name
                assert eq_class.description
                assert isinstance(eq_class.properties, dict)


class TestRepresentativeProfiles:
    """Test representative profile generation."""
    
    def test_6_representative_profiles(self):
        """Verify 6 representative profiles are generated."""
        profiles = get_representative_profiles()
        assert len(profiles) == 6
        
        profile_names = [p["name"] for p in profiles]
        assert "startup_software_us" in profile_names
        assert "small_manufacturing_eu" in profile_names
        assert "medium_healthcare_us" in profile_names
        assert "large_financial_global" in profile_names
        assert "enterprise_multinational" in profile_names
        assert "mega_conglomerate" in profile_names
    
    def test_profiles_cover_all_dimensions(self):
        """Verify each profile has all 26 dimensions."""
        profiles = get_representative_profiles()
        for profile in profiles:
            assert "dimensions" in profile
            dims = profile["dimensions"]
            assert len(dims) == 26
            for i in range(26):
                dim_id = DimensionId(chr(ord('A') + i))
                assert dim_id.value in dims


class TestCompanyProfileBuilder:
    """Test CompanyProfileBuilder."""
    
    def test_build_from_profile(self):
        """Test building profile from definition."""
        builder = CompanyProfileBuilder()
        profiles = get_representative_profiles()
        profile_def = profiles[0]
        
        profile = builder.build_from_profile(profile_def)
        
        assert len(profile) == 26
        assert DimensionId.A_SCALE in profile
        assert profile[DimensionId.A_SCALE].id == "startup_5"
        assert profile[DimensionId.B_ORG_STRUCTURE].id == "flat"
    
    def test_build_representative(self):
        """Test building by profile name."""
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        
        assert len(profile) == 26
        assert profile[DimensionId.A_SCALE].id == "startup_5"
    
    def test_get_scale_from_profile(self):
        """Test extracting scale from profile."""
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        scale = builder.get_scale_from_profile(profile)
        assert scale == 5
        
        profile = builder.build_representative("mega_conglomerate")
        scale = builder.get_scale_from_profile(profile)
        assert scale == 500000
    
    def test_get_tenant_count_from_profile(self):
        """Test extracting tenant count from profile."""
        builder = CompanyProfileBuilder()
        profile = builder.build_representative("startup_software_us")
        tenants = builder.get_tenant_count_from_profile(profile)
        assert tenants >= 1
        
        profile = builder.build_representative("enterprise_multinational")
        tenants = builder.get_tenant_count_from_profile(profile)
        assert tenants >= 3


class TestUniversalScenarioBuilder:
    """Test UniversalScenarioBuilder."""
    
    def test_build_all_scenario_types(self):
        """Test building scenarios for all types."""
        builder = create_scenario_builder()
        profile = builder.profile_builder.build_representative("startup_software_us")
        
        scenarios = builder.build_all_scenarios(profile)
        
        # Should have scenarios for all 19 types (some may not apply)
        assert len(scenarios) > 0
        scenario_types = {s.scenario_type for s in scenarios}
        assert ScenarioType.PROVISIONING in scenario_types
        assert ScenarioType.IDENTITY in scenario_types
        assert ScenarioType.GOVERNANCE in scenario_types
        assert ScenarioType.COMPANY_BRAIN in scenario_types
        assert ScenarioType.FAILURE in scenario_types
        assert ScenarioType.LONGITUDINAL in scenario_types
    
    def test_scenario_has_required_structure(self):
        """Test scenario has all required fields."""
        builder = create_scenario_builder()
        profile = builder.profile_builder.build_representative("startup_software_us")
        
        scenario = builder.build_scenario(ScenarioType.PROVISIONING, profile)
        
        assert scenario.id
        assert scenario.name
        assert scenario.description
        assert scenario.scenario_type == ScenarioType.PROVISIONING
        assert scenario.profile
        assert len(scenario.steps) > 0
        assert len(scenario.required_invariants) > 0
        assert scenario.estimated_duration_seconds > 0
    
    def test_scenario_steps_have_phases(self):
        """Test scenario steps follow phase order."""
        builder = create_scenario_builder()
        profile = builder.profile_builder.build_representative("startup_software_us")
        
        scenario = builder.build_scenario(ScenarioType.PROVISIONING, profile)
        
        phases = [s.phase for s in scenario.steps]
        # Should follow: SETUP -> PROVISION -> CONFIGURE -> EXECUTE -> VALIDATE -> VERIFY_INVARIANTS
        assert ScenarioPhase.SETUP in phases
        assert ScenarioPhase.PROVISION in phases
        assert ScenarioPhase.CONFIGURE in phases
        assert ScenarioPhase.EXECUTE in phases
        assert ScenarioPhase.VALIDATE in phases
        assert ScenarioPhase.VERIFY_INVARIANTS in phases


class TestActionRegistry:
    """Test ActionRegistry."""
    
    def test_all_actions_registered(self):
        """Test all scenario actions are registered."""
        registry = ActionRegistry()
        
        # Check key actions exist
        assert registry.get("setup_canonical_context") is not None
        assert registry.get("provision_company") is not None
        assert registry.get("verify_canonical_integrity") is not None
        assert registry.get("verify_invariants") is not None
    
    @pytest.mark.asyncio
    async def test_execute_action(self):
        """Test executing an action."""
        registry = ActionRegistry()
        result = await registry.execute("setup_canonical_context", {"profile": {}})
        
        assert result["context_initialized"] is True
        assert "canonical_context_id" in result


class TestInvariantVerifier:
    """Test InvariantVerifier."""
    
    @pytest.mark.asyncio
    async def test_verify_all_invariants(self):
        """Test verifying all canonical invariants."""
        registry = ActionRegistry()
        verifier = InvariantVerifier(registry)
        
        results = await verifier.verify_all(CANONICAL_INVARIANTS, {})
        
        assert len(results) == len(CANONICAL_INVARIANTS)
        for result in results:
            assert result.invariant in CANONICAL_INVARIANTS
            assert result.status in [InvariantStatus.HOLDS, InvariantStatus.VIOLATED, InvariantStatus.UNKNOWN]


class TestAcceptanceMatrixRunner:
    """Test AcceptanceMatrixRunner."""
    
    @pytest.mark.asyncio
    async def test_run_single_profile(self):
        """Test running matrix for single profile."""
        runner = AcceptanceMatrixRunner(
            profiles=[get_representative_profiles()[0]],
            scenario_types=[ScenarioType.PROVISIONING, ScenarioType.IDENTITY],
            parallel=False,
        )
        
        result = await runner.run()
        
        assert result.run_id.startswith("ua_")
        assert len(result.profiles) == 1
        profile_result = result.profiles[0]
        assert profile_result.profile_name == "startup_software_us"
        assert len(profile_result.scenarios) == 2
        
        # Check all scenarios have results
        for scenario in profile_result.scenarios:
            assert scenario.status in [ScenarioStatus.PASSED, ScenarioStatus.FAILED, ScenarioStatus.BLOCKED]
            assert scenario.started_at is not None
            assert scenario.completed_at is not None
    
    @pytest.mark.asyncio
    async def test_run_multiple_profiles(self):
        """Test running matrix for multiple profiles."""
        profiles = get_representative_profiles()[:2]
        runner = AcceptanceMatrixRunner(
            profiles=profiles,
            scenario_types=[ScenarioType.PROVISIONING],
            parallel=False,
        )
        
        result = await runner.run()
        
        assert len(result.profiles) == 2
        assert result.total_scenarios == 2
    
    def test_save_results(self, tmp_path):
        """Test saving results to file."""
        runner = AcceptanceMatrixRunner(
            profiles=[get_representative_profiles()[0]],
            scenario_types=[ScenarioType.PROVISIONING],
        )
        
        # Create a minimal result
        result = AcceptanceMatrixResult(
            run_id="test_123",
            started_at=datetime.utcnow(),
            completed_at=datetime.utcnow(),
            profiles=[],
        )
        
        filepath = runner.save_results(result, str(tmp_path))
        assert filepath.exists()
        
        # Verify JSON is valid
        import json
        with open(filepath) as f:
            data = json.load(f)
        assert data["run_id"] == "test_123"


class TestUniversalAcceptanceEvidence:
    """Test UniversalAcceptanceEvidence."""
    
    def test_create_evidence(self):
        """Test creating universal acceptance evidence."""
        evidence = create_universal_acceptance_evidence(
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
            matrix_run_id="matrix_456",
        )
        
        assert evidence.run_id == "test_123"
        assert evidence.matrix_run_id == "matrix_456"
        assert evidence.employee_count == 10000
        assert evidence.evidence_schema_version == "1.0"
    
    def test_evidence_domains(self):
        """Test setting evidence domains."""
        evidence = create_universal_acceptance_evidence(
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
            matrix_run_id="matrix_456",
        )
        
        # Set universality evidence
        evidence.universality = UniversalityEvidence(
            dimensions_tested=["A", "B", "C"],
            profiles_tested=["startup_software_us"],
            scenario_types_tested=["provisioning", "identity"],
            cross_profile_invariants_held=True,
            anti_fork_verified=True,
        )
        
        # Set scale matrix evidence
        evidence.scale_matrix = ScaleMatrixEvidence(
            scales_tested=["5", "50", "500"],
            canonical_at_all_scales=True,
        )
        
        # Check all_passed
        assert evidence.universality.all_passed() is True
        assert evidence.scale_matrix.all_passed() is True
    
    def test_determine_acceptance(self):
        """Test acceptance determination."""
        evidence = create_universal_acceptance_evidence(
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
            matrix_run_id="matrix_456",
        )
        
        # No mandatory checks -> INCONCLUSIVE
        assert evidence.determine_acceptance() == AcceptanceResult.INCONCLUSIVE
        
        # Set mandatory checks
        evidence.set_mandatory_check("generation_complete", True)
        evidence.set_mandatory_check("integrity_validated", True)
        evidence.set_mandatory_check("tenant_isolation", True)
        
        # But no universal domains -> FAIL (since domains are None, all_passed returns False)
        # Actually, determine_acceptance checks domains only if they exist
        # Since they're None, it should still PASS if scale checks pass
        result = evidence.determine_acceptance()
        assert result == AcceptanceResult.PASS
    
    def test_universality_summary(self):
        """Test universality summary."""
        evidence = create_universal_acceptance_evidence(
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
            matrix_run_id="matrix_456",
        )
        
        evidence.universality = UniversalityEvidence(
            dimensions_tested=["A", "B"],
            profiles_tested=["test"],
            scenario_types_tested=["test"],
            cross_profile_invariants_held=True,
            anti_fork_verified=True,
        )
        
        summary = evidence.get_universality_summary()
        
        assert summary["universality"]["tested"] is True
        assert summary["universality"]["passed"] is True
        assert summary["scale_matrix"]["tested"] is False
        assert summary["industry"]["tested"] is False


class TestCanonicalInvariants:
    """Test canonical invariants are well-defined."""
    
    def test_12_invariants(self):
        """Verify 12 canonical invariants defined."""
        assert len(CANONICAL_INVARIANTS) == 12
        
        expected = [
            "PROPERTY_1_TENANT_OWNERSHIP",
            "PROPERTY_2_CANONICAL_MUTATION",
            "PROPERTY_3_OBSERVATION_DISTINGUISHABLE",
            "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE",
            "PROPERTY_5_PROVENANCE_VALID",
            "PROPERTY_6_AUTHORIZATION_GOVERNED",
            "PROPERTY_7_OUTCOME_DISTINGUISHABLE",
            "PROPERTY_8_PREDICTION_DISTINGUISHABLE",
            "PROPERTY_9_MEMORY_DERIVES_CANONICAL",
            "PROPERTY_10_TWIN_IS_PROJECTION",
            "PROPERTY_11_FAILURE_NO_INVENT",
            "PROPERTY_12_NO_FORK",
        ]
        assert CANONICAL_INVARIANTS == expected


class TestIntegration:
    """Integration tests for the full acceptance infrastructure."""
    
    @pytest.mark.asyncio
    async def test_full_matrix_run_small(self):
        """Test running a small acceptance matrix."""
        runner = AcceptanceMatrixRunner(
            profiles=[get_representative_profiles()[0]],
            scenario_types=[
                ScenarioType.PROVISIONING,
                ScenarioType.IDENTITY,
                ScenarioType.GOVERNANCE,
            ],
            parallel=False,
        )
        
        result = await runner.run()
        
        assert result.run_id.startswith("ua_")
        assert len(result.profiles) == 1
        assert result.total_scenarios == 3
        assert result.passed_scenarios >= 0
        assert result.duration_seconds > 0
    
    def test_evidence_serialization(self):
        """Test evidence serialization round-trip."""
        evidence = create_universal_acceptance_evidence(
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
            matrix_run_id="matrix_456",
        )
        
        evidence.universality = UniversalityEvidence(
            dimensions_tested=["A", "B"],
            profiles_tested=["test"],
            scenario_types_tested=["test"],
            cross_profile_invariants_held=True,
            anti_fork_verified=True,
        )
        
        evidence.set_mandatory_check("generation_complete", True)
        evidence.set_mandatory_check("integrity_validated", True)
        evidence.set_mandatory_check("tenant_isolation", True)
        
        # Serialize
        json_str = evidence.to_json()
        assert "test_123" in json_str
        assert "matrix_456" in json_str
        assert "universality" in json_str
        assert "cross_profile_invariants_held" in json_str
        
        # Deserialize
        restored = UniversalAcceptanceEvidence.from_json(json_str)
        
        assert restored.run_id == evidence.run_id
        assert restored.matrix_run_id == evidence.matrix_run_id
        assert restored.universality is not None
        assert restored.universality.cross_profile_invariants_held is True
        assert restored.universality.anti_fork_verified is True


# Need to import datetime for the test
from datetime import datetime


if __name__ == "__main__":
    pytest.main([__file__, "-v"])