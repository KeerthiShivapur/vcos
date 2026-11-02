"""Universal Scenario Builder.

Builds canonical test scenarios for the Universal Acceptance Matrix.
This is TEST INFRASTRUCTURE - NOT a business model.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
from enum import Enum
import uuid

from .dimensions import (
    DimensionId, EquivalenceClass, Dimension, ALL_DIMENSIONS,
    get_dimension, get_representative_profiles,
    CANONICAL_INVARIANTS,
)


class ScenarioType(str, Enum):
    """Types of acceptance scenarios."""
    PROVISIONING = "provisioning"
    IDENTITY = "identity"
    GOVERNANCE = "governance"
    WORK = "work"
    FINANCE = "finance"
    INTEGRATION = "integration"
    COMPANY_BRAIN = "company_brain"
    MEMORY = "memory"
    PREDICTION = "prediction"
    COUNTERFACTUAL = "counterfactual"
    AUTONOMY = "autonomy"
    CONTINUITY = "continuity"
    MIGRATION = "migration"
    MA = "ma"
    FAILURE = "failure"
    LONGITUDINAL = "longitudinal"
    DEPLOYMENT_DR = "deployment_dr"
    SECURITY = "security"
    API = "api"


class ScenarioPhase(str, Enum):
    """Phases of a scenario execution."""
    SETUP = "setup"
    PROVISION = "provision"
    CONFIGURE = "configure"
    EXECUTE = "execute"
    VALIDATE = "validate"
    VERIFY_INVARIANTS = "verify_invariants"
    TEARDOWN = "teardown"


@dataclass(frozen=True)
class ScenarioStep:
    """A single step in a scenario."""
    phase: ScenarioPhase
    name: str
    description: str
    action: str  # Reference to action function
    params: Dict[str, Any] = field(default_factory=dict)
    expected: Dict[str, Any] = field(default_factory=dict)
    invariants: List[str] = field(default_factory=list)
    depends_on: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class UniversalScenario:
    """A complete universal acceptance scenario."""
    id: str
    name: str
    description: str
    scenario_type: ScenarioType
    profile: Dict[str, Any]  # Dimension selections
    steps: List[ScenarioStep]
    required_invariants: List[str]
    tags: List[str] = field(default_factory=list)
    estimated_duration_seconds: float = 60.0


class CompanyProfileBuilder:
    """Builds company profiles from dimension equivalence classes."""
    
    def __init__(self):
        self._dimensions = {d.id: d for d in ALL_DIMENSIONS}
    
    def build_from_profile(self, profile: Dict[str, Any]) -> Dict[str, EquivalenceClass]:
        """Build a complete company profile from dimension selections."""
        result = {}
        for dim_id, class_id in profile.get("dimensions", {}).items():
            dim = self._dimensions.get(DimensionId(dim_id))
            if dim:
                eq_class = next((c for c in dim.equivalence_classes if c.id == class_id), None)
                if eq_class:
                    result[dim_id] = eq_class
        return result
    
    def build_representative(self, profile_name: str) -> Dict[str, EquivalenceClass]:
        """Build a representative profile by name."""
        profiles = get_representative_profiles()
        profile = next((p for p in profiles if p["name"] == profile_name), None)
        if not profile:
            raise ValueError(f"Unknown profile: {profile_name}")
        return self.build_from_profile(profile)
    
    def get_scale_from_profile(self, profile: Dict[str, EquivalenceClass]) -> int:
        """Extract employee count from profile."""
        scale_class = profile.get(DimensionId.A_SCALE)
        if scale_class:
            return scale_class.properties.get("employee_count", 5)
        return 5
    
    def get_tenant_count_from_profile(self, profile: Dict[str, EquivalenceClass]) -> int:
        """Extract tenant count from profile."""
        multi_class = profile.get(DimensionId.F_MULTI_COMPANY)
        if multi_class:
            props = multi_class.properties
            return len(props.get("subsidiaries", [])) + len(props.get("joint_ventures", [])) + 1
        return 1


class UniversalScenarioBuilder:
    """Builds universal acceptance scenarios for each scenario type."""
    
    def __init__(self, profile_builder: CompanyProfileBuilder):
        self.profile_builder = profile_builder
        self._scenario_templates: Dict[ScenarioType, Callable] = {
            ScenarioType.PROVISIONING: self._build_provisioning_scenario,
            ScenarioType.IDENTITY: self._build_identity_scenario,
            ScenarioType.GOVERNANCE: self._build_governance_scenario,
            ScenarioType.WORK: self._build_work_scenario,
            ScenarioType.FINANCE: self._build_finance_scenario,
            ScenarioType.INTEGRATION: self._build_integration_scenario,
            ScenarioType.COMPANY_BRAIN: self._build_company_brain_scenario,
            ScenarioType.MEMORY: self._build_memory_scenario,
            ScenarioType.PREDICTION: self._build_prediction_scenario,
            ScenarioType.COUNTERFACTUAL: self._build_counterfactual_scenario,
            ScenarioType.AUTONOMY: self._build_autonomy_scenario,
            ScenarioType.CONTINUITY: self._build_continuity_scenario,
            ScenarioType.MIGRATION: self._build_migration_scenario,
            ScenarioType.MA: self._build_ma_scenario,
            ScenarioType.FAILURE: self._build_failure_scenario,
            ScenarioType.LONGITUDINAL: self._build_longitudinal_scenario,
            ScenarioType.DEPLOYMENT_DR: self._build_deployment_dr_scenario,
            ScenarioType.SECURITY: self._build_security_scenario,
            ScenarioType.API: self._build_api_scenario,
        }
    
    def build_scenario(
        self,
        scenario_type: ScenarioType,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        """Build a scenario for the given type and profile."""
        builder = self._scenario_templates.get(scenario_type)
        if not builder:
            raise ValueError(f"No builder for scenario type: {scenario_type}")
        return builder(profile, custom_steps)
    
    def build_all_scenarios(self, profile: Dict[str, EquivalenceClass]) -> List[UniversalScenario]:
        """Build all scenario types for a profile."""
        scenarios = []
        for scenario_type in ScenarioType:
            try:
                scenario = self.build_scenario(scenario_type, profile)
                scenarios.append(scenario)
            except Exception as e:
                # Log but continue - some scenarios may not apply to all profiles
                pass
        return scenarios
    
    def _base_steps(self, profile: Dict[str, EquivalenceClass]) -> List[ScenarioStep]:
        """Base steps common to all scenarios."""
        return [
            ScenarioStep(
                phase=ScenarioPhase.SETUP,
                name="initialize_canonical_context",
                description="Initialize canonical company context",
                action="setup_canonical_context",
                params={"profile": profile},
                expected={"context_initialized": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.PROVISION,
                name="provision_company",
                description="Provision company through canonical provisioning",
                action="provision_company",
                params={"profile": profile},
                expected={"company_provisioned": True, "tenant_created": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP", "PROPERTY_2_CANONICAL_MUTATION"],
            ),
        ]
    
    def _validation_steps(self, invariants: List[str]) -> List[ScenarioStep]:
        """Standard validation steps."""
        return [
            ScenarioStep(
                phase=ScenarioPhase.VALIDATE,
                name="verify_canonical_integrity",
                description="Verify canonical integrity constraints",
                action="verify_canonical_integrity",
                params={},
                expected={"integrity_valid": True},
                invariants=invariants,
            ),
            ScenarioStep(
                phase=ScenarioPhase.VERIFY_INVARIANTS,
                name="verify_all_invariants",
                description="Verify all canonical invariants hold",
                action="verify_invariants",
                params={"invariants": invariants},
                expected={"all_invariants_hold": True},
                invariants=invariants,
            ),
        ]
    
    def _build_provisioning_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="configure_organization",
                description="Configure organization structure per profile",
                action="configure_organization_structure",
                params={"profile": profile},
                expected={"structure_configured": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="configure_governance",
                description="Configure governance policies per profile",
                action="configure_governance",
                params={"profile": profile},
                expected={"governance_configured": True},
                invariants=["PROPERTY_2_CANONICAL_MUTATION", "PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="configure_integrations",
                description="Configure external integrations per profile",
                action="configure_integrations",
                params={"profile": profile},
                expected={"integrations_configured": True},
                invariants=["PROPERTY_3_OBSERVATION_DISTINGUISHABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="initial_sync",
                description="Execute initial sync for all connectors",
                action="execute_initial_sync",
                params={"profile": profile},
                expected={"sync_completed": True, "observations_recorded": True},
                invariants=["PROPERTY_3_OBSERVATION_DISTINGUISHABLE", "PROPERTY_5_PROVENANCE_VALID"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"prov_{uuid.uuid4().hex[:8]}",
            name="Company Provisioning",
            description="Full company provisioning through canonical pathway",
            scenario_type=ScenarioType.PROVISIONING,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["provisioning", "canonical"],
            estimated_duration_seconds=120.0,
        )
    
    def _build_identity_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="create_people",
                description="Create people with identity per profile",
                action="create_people",
                params={"profile": profile},
                expected={"people_created": True, "identities_stable": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP", "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_identity_transitions",
                description="Test identity transitions (role changes, transfers, etc.)",
                action="test_identity_transitions",
                params={"profile": profile},
                expected={"transitions_tracked": True, "identity_continuous": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", "PROPERTY_5_PROVENANCE_VALID"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_cross_entity_identity",
                description="Test identity across subsidiaries/entities",
                action="test_cross_entity_identity",
                params={"profile": profile},
                expected={"cross_entity_resolved": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP", "PROPERTY_5_PROVENANCE_VALID"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"ident_{uuid.uuid4().hex[:8]}",
            name="Universal Identity",
            description="Identity stability across roles, entities, transitions",
            scenario_type=ScenarioType.IDENTITY,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["identity", "canonical"],
            estimated_duration_seconds=90.0,
        )
    
    def _build_governance_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="define_roles_permissions",
                description="Define roles and permissions per governance profile",
                action="define_roles_permissions",
                params={"profile": profile},
                expected={"roles_defined": True, "permissions_scoped": True},
                invariants=["PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_authorization",
                description="Test authorization decisions across scopes",
                action="test_authorization_decisions",
                params={"profile": profile},
                expected={"authorization_correct": True},
                invariants=["PROPERTY_2_CANONICAL_MUTATION", "PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_delegation_revocation",
                description="Test delegation and revocation",
                action="test_delegation_revocation",
                params={"profile": profile},
                expected={"delegation_works": True, "revocation_works": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", "PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_privileged_operations",
                description="Test privileged operations require governance",
                action="test_privileged_operations",
                params={"profile": profile},
                expected={"privileged_governed": True},
                invariants=["PROPERTY_2_CANONICAL_MUTATION", "PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"gov_{uuid.uuid4().hex[:8]}",
            name="Universal Governance",
            description="Governance across startup/enterprise/federated/regulated",
            scenario_type=ScenarioType.GOVERNANCE,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["governance", "canonical"],
            estimated_duration_seconds=120.0,
        )
    
    def _build_work_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="define_work_types",
                description="Define work types per industry/profile",
                action="define_work_types",
                params={"profile": profile},
                expected={"work_types_defined": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="execute_work_lifecycle",
                description="Execute full work lifecycle: create → action → outcome",
                action="execute_work_lifecycle",
                params={"profile": profile},
                expected={"work_created": True, "actions_executed": True, "outcomes_recorded": True},
                invariants=[
                    "PROPERTY_2_CANONICAL_MUTATION",
                    "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE",
                    "PROPERTY_7_OUTCOME_DISTINGUISHABLE",
                ],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_work_composition",
                description="Test work type composition (project + ticket + objective)",
                action="test_work_composition",
                params={"profile": profile},
                expected={"composition_works": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP", "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"work_{uuid.uuid4().hex[:8]}",
            name="Universal Work",
            description="Work/action/outcome across 10 work type patterns",
            scenario_type=ScenarioType.WORK,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["work", "canonical"],
            estimated_duration_seconds=120.0,
        )
    
    def _build_finance_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="configure_finance",
                description="Configure finance per profile (currencies, entities, dimensions)",
                action="configure_finance",
                params={"profile": profile},
                expected={"finance_configured": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP", "PROPERTY_5_PROVENANCE_VALID"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_multi_currency",
                description="Test multi-currency transactions",
                action="test_multi_currency_transactions",
                params={"profile": profile},
                expected={"fx_handled": True, "provenance_tracked": True},
                invariants=["PROPERTY_3_OBSERVATION_DISTINGUISHABLE", "PROPERTY_5_PROVENANCE_VALID"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_consolidation",
                description="Test multi-entity consolidation",
                action="test_consolidation",
                params={"profile": profile},
                expected={"consolidation_correct": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP", "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"fin_{uuid.uuid4().hex[:8]}",
            name="Universal Finance",
            description="Finance across simple/multi-currency/multi-entity/regulated",
            scenario_type=ScenarioType.FINANCE,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["finance", "canonical"],
            estimated_duration_seconds=90.0,
        )
    
    def _build_integration_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="configure_connectors",
                description="Configure Universal Connector Contract connectors",
                action="configure_connectors",
                params={"profile": profile},
                expected={"connectors_configured": True},
                invariants=["PROPERTY_3_OBSERVATION_DISTINGUISHABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_inbound_observation",
                description="Test inbound observations with evidence/validation",
                action="test_inbound_observations",
                params={"profile": profile},
                expected={"observations_validated": True, "evidence_recorded": True},
                invariants=[
                    "PROPERTY_3_OBSERVATION_DISTINGUISHABLE",
                    "PROPERTY_5_PROVENANCE_VALID",
                ],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_reconciliation",
                description="Test reconciliation as governed mutation",
                action="test_reconciliation",
                params={"profile": profile},
                expected={"reconciled": True, "mutation_governed": True},
                invariants=[
                    "PROPERTY_2_CANONICAL_MUTATION",
                    "PROPERTY_3_OBSERVATION_DISTINGUISHABLE",
                ],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_outbound_operations",
                description="Test outbound operations with idempotency",
                action="test_outbound_operations",
                params={"profile": profile},
                expected={"outbound_idempotent": True},
                invariants=["PROPERTY_2_CANONICAL_MUTATION", "PROPERTY_5_PROVENANCE_VALID"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"int_{uuid.uuid4().hex[:8]}",
            name="Integration Universality",
            description="Universal Connector Contract across all connectors",
            scenario_type=ScenarioType.INTEGRATION,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["integration", "canonical"],
            estimated_duration_seconds=180.0,
        )
    
    def _build_company_brain_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="configure_company_brain",
                description="Configure Company Brain projection",
                action="configure_company_brain",
                params={"profile": profile},
                expected={"brain_configured": True},
                invariants=["PROPERTY_9_MEMORY_DERIVES_CANONICAL", "PROPERTY_10_TWIN_IS_PROJECTION"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_context_retrieval",
                description="Test context retrieval from canonical reality",
                action="test_context_retrieval",
                params={"profile": profile},
                expected={"context_retrieved": True, "grounded_in_canonical": True},
                invariants=[
                    "PROPERTY_9_MEMORY_DERIVES_CANONICAL",
                    "PROPERTY_10_TWIN_IS_PROJECTION",
                ],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_temporal_queries",
                description="Test temporal queries (as-of, time-travel)",
                action="test_temporal_queries",
                params={"profile": profile},
                expected={"temporal_queries_work": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_governance_respected",
                description="Test governance respected in queries",
                action="test_governance_in_queries",
                params={"profile": profile},
                expected={"governance_enforced": True},
                invariants=["PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"brain_{uuid.uuid4().hex[:8]}",
            name="Company Brain Projection",
            description="Company Brain as projection over canonical reality",
            scenario_type=ScenarioType.COMPANY_BRAIN,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["company_brain", "projection", "canonical"],
            estimated_duration_seconds=120.0,
        )
    
    def _build_memory_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="verify_memory_derivation",
                description="Verify memory derives from canonical reality",
                action="verify_memory_derivation",
                params={"profile": profile},
                expected={"memory_from_canonical": True},
                invariants=["PROPERTY_9_MEMORY_DERIVES_CANONICAL"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_epistemic_status",
                description="Test epistemic status preservation in memory",
                action="test_epistemic_status",
                params={"profile": profile},
                expected={"epistemic_preserved": True},
                invariants=["PROPERTY_9_MEMORY_DERIVES_CANONICAL", "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_longitudinal_memory",
                description="Test longitudinal memory across time",
                action="test_longitudinal_memory",
                params={"profile": profile},
                expected={"longitudinal_intact": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", "PROPERTY_9_MEMORY_DERIVES_CANONICAL"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"mem_{uuid.uuid4().hex[:8]}",
            name="Living Company Memory",
            description="Memory derives from canonical reality across time",
            scenario_type=ScenarioType.MEMORY,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["memory", "longitudinal", "canonical"],
            estimated_duration_seconds=120.0,
        )
    
    def _build_prediction_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="create_prediction",
                description="Create prediction with explicit assumptions",
                action="create_prediction",
                params={"profile": profile},
                expected={"prediction_created": True, "assumptions_explicit": True},
                invariants=["PROPERTY_8_PREDICTION_DISTINGUISHABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="verify_prediction_non_canonical",
                description="Verify prediction never becomes canonical truth",
                action="verify_prediction_non_canonical",
                params={"profile": profile},
                expected={"remains_non_canonical": True},
                invariants=["PROPERTY_8_PREDICTION_DISTINGUISHABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_governance_on_prediction",
                description="Test governance gates on predictions",
                action="test_governance_on_prediction",
                params={"profile": profile},
                expected={"governance_applied": True},
                invariants=["PROPERTY_6_AUTHORIZATION_GOVERNED", "PROPERTY_8_PREDICTION_DISTINGUISHABLE"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"pred_{uuid.uuid4().hex[:8]}",
            name="Prediction / Forecasting",
            description="Predictions with explicit assumptions, non-canonical",
            scenario_type=ScenarioType.PREDICTION,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["prediction", "non_canonical", "canonical"],
            estimated_duration_seconds=90.0,
        )
    
    def _build_counterfactual_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="create_counterfactual",
                description="Create counterfactual scenario",
                action="create_counterfactual",
                params={"profile": profile},
                expected={"scenario_created": True, "assumptions_explicit": True},
                invariants=["PROPERTY_8_PREDICTION_DISTINGUISHABLE", "PROPERTY_10_TWIN_IS_PROJECTION"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="simulate_scenario",
                description="Run simulation over canonical reality",
                action="simulate_scenario",
                params={"profile": profile},
                expected={"simulation_completed": True, "canonical_unchanged": True},
                invariants=["PROPERTY_10_TWIN_IS_PROJECTION", "PROPERTY_8_PREDICTION_DISTINGUISHABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_governed_commitment",
                description="Test governed commitment of scenario outcomes",
                action="test_governed_commitment",
                params={"profile": profile},
                expected={"commitment_governed": True},
                invariants=["PROPERTY_2_CANONICAL_MUTATION", "PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"cf_{uuid.uuid4().hex[:8]}",
            name="Counterfactual Simulation",
            description="What-if scenarios with explicit uncertainty",
            scenario_type=ScenarioType.COUNTERFACTUAL,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["counterfactual", "simulation", "non_canonical"],
            estimated_duration_seconds=120.0,
        )
    
    def _build_autonomy_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.CONFIGURE,
                name="configure_autonomy_policy",
                description="Configure autonomy policy per profile",
                action="configure_autonomy_policy",
                params={"profile": profile},
                expected={"policy_configured": True},
                invariants=["PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_eligibility_evidence",
                description="Test eligibility → evidence → governance flow",
                action="test_autonomy_flow",
                params={"profile": profile},
                expected={"flow_complete": True, "human_gate_respected": True},
                invariants=[
                    "PROPERTY_2_CANONICAL_MUTATION",
                    "PROPERTY_6_AUTHORIZATION_GOVERNED",
                    "PROPERTY_7_OUTCOME_DISTINGUISHABLE",
                ],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_autonomous_execution",
                description="Test autonomous execution with verification",
                action="test_autonomous_execution",
                params={"profile": profile},
                expected={"executed": True, "verified": True, "learned": True},
                invariants=["PROPERTY_2_CANONICAL_MUTATION", "PROPERTY_7_OUTCOME_DISTINGUISHABLE"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"auto_{uuid.uuid4().hex[:8]}",
            name="Governed Autonomous Operations",
            description="Autonomy eligibility→evidence→governance→commitment→execution",
            scenario_type=ScenarioType.AUTONOMY,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["autonomy", "governed", "canonical"],
            estimated_duration_seconds=120.0,
        )
    
    def _build_continuity_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="simulate_continuity_event",
                description="Simulate continuity event (departure, reorg, acquisition)",
                action="simulate_continuity_event",
                params={"profile": profile},
                expected={"event_simulated": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", "PROPERTY_9_MEMORY_DERIVES_CANONICAL"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="verify_history_intact",
                description="Verify historical truth remains intact",
                action="verify_history_intact",
                params={"profile": profile},
                expected={"history_intact": True, "lineage_preserved": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", "PROPERTY_5_PROVENANCE_VALID"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="verify_identity_continuous",
                description="Verify identity continuity through event",
                action="verify_identity_continuous",
                params={"profile": profile},
                expected={"identity_continuous": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP", "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"cont_{uuid.uuid4().hex[:8]}",
            name="Company Continuity",
            description="Continuity through departure/reorg/acquisition/merger",
            scenario_type=ScenarioType.CONTINUITY,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["continuity", "m_a", "canonical"],
            estimated_duration_seconds=120.0,
        )
    
    def _build_migration_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="execute_migration",
                description="Execute migration per profile",
                action="execute_migration",
                params={"profile": profile},
                expected={"migration_completed": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", "PROPERTY_5_PROVENANCE_VALID"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.VALIDATE,
                name="verify_preservation",
                description="Verify identity/provenance/history preserved",
                action="verify_migration_preservation",
                params={"profile": profile},
                expected={"all_preserved": True},
                invariants=[
                    "PROPERTY_1_TENANT_OWNERSHIP",
                    "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE",
                    "PROPERTY_5_PROVENANCE_VALID",
                    "PROPERTY_9_MEMORY_DERIVES_CANONICAL",
                ],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"mig_{uuid.uuid4().hex[:8]}",
            name="Migration Universality",
            description="Migration preserving identity/provenance/history",
            scenario_type=ScenarioType.MIGRATION,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["migration", "preservation", "canonical"],
            estimated_duration_seconds=180.0,
        )
    
    def _build_ma_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="execute_ma",
                description="Execute M&A scenario per profile",
                action="execute_ma",
                params={"profile": profile},
                expected={"ma_completed": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", "PROPERTY_5_PROVENANCE_VALID"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.VALIDATE,
                name="verify_ma_lineage",
                description="Verify M&A lineage in canonical reality",
                action="verify_ma_lineage",
                params={"profile": profile},
                expected={"lineage_complete": True, "both_legacies_preserved": True},
                invariants=[
                    "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE",
                    "PROPERTY_5_PROVENANCE_VALID",
                    "PROPERTY_9_MEMORY_DERIVES_CANONICAL",
                ],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"ma_{uuid.uuid4().hex[:8]}",
            name="M&A Lineage",
            description="M&A preserving both legacies in canonical reality",
            scenario_type=ScenarioType.MA,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["m_a", "lineage", "canonical"],
            estimated_duration_seconds=180.0,
        )
    
    def _build_failure_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="inject_failure",
                description="Inject failure (DB, worker, network, external)",
                action="inject_failure",
                params={"profile": profile, "failure_type": "mixed"},
                expected={"failure_injected": True},
                invariants=["PROPERTY_11_FAILURE_NO_INVENT"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="verify_tenant_isolation",
                description="Verify Tenant A failure != Tenant B failure",
                action="verify_tenant_isolation_under_failure",
                params={"profile": profile},
                expected={"isolated": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP", "PROPERTY_11_FAILURE_NO_INVENT"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_governed_recovery",
                description="Test governed recovery with UNKNOWN preservation",
                action="test_governed_recovery",
                params={"profile": profile},
                expected={"recovery_governed": True, "unknown_preserved": True},
                invariants=[
                    "PROPERTY_2_CANONICAL_MUTATION",
                    "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE",
                    "PROPERTY_11_FAILURE_NO_INVENT",
                ],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"fail_{uuid.uuid4().hex[:8]}",
            name="Failure + Universality",
            description="35-H failure scenarios across company types",
            scenario_type=ScenarioType.FAILURE,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["failure", "35h", "isolation", "canonical"],
            estimated_duration_seconds=180.0,
        )
    
    def _build_longitudinal_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="run_longitudinal",
                description="Run longitudinal simulation (1-10 years)",
                action="run_longitudinal_simulation",
                params={"profile": profile, "years": 3},
                expected={"simulation_completed": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", "PROPERTY_9_MEMORY_DERIVES_CANONICAL"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.VALIDATE,
                name="verify_temporal_integrity",
                description="Verify temporal integrity over time",
                action="verify_temporal_integrity",
                params={"profile": profile},
                expected={"temporal_intact": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.VALIDATE,
                name="verify_knowledge_timeline",
                description="Verify knowledge timeline integrity",
                action="verify_knowledge_timeline",
                params={"profile": profile},
                expected={"knowledge_timeline_valid": True},
                invariants=["PROPERTY_9_MEMORY_DERIVES_CANONICAL"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"long_{uuid.uuid4().hex[:8]}",
            name="Longitudinal Universality",
            description="35-I temporal reality across company classes",
            scenario_type=ScenarioType.LONGITUDINAL,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["longitudinal", "35i", "temporal", "canonical"],
            estimated_duration_seconds=240.0,
        )
    
    def _build_deployment_dr_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_backup",
                description="Test backup with canonical integrity",
                action="test_backup",
                params={"profile": profile},
                expected={"backup_valid": True, "canonical_integrity": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE", "PROPERTY_5_PROVENANCE_VALID"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_restore",
                description="Test restore with tenant isolation",
                action="test_restore",
                params={"profile": profile},
                expected={"restore_valid": True, "tenant_isolation": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP", "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="verify_rpo_rto",
                description="Verify RPO/RTO targets met",
                action="verify_rpo_rto",
                params={"profile": profile},
                expected={"rpo_met": True, "rto_met": True},
                invariants=["PROPERTY_4_TEMPORAL_RECONSTRUCTABLE"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"dr_{uuid.uuid4().hex[:8]}",
            name="Deployment/DR Acceptance",
            description="Backup/restore/DR with canonical integrity",
            scenario_type=ScenarioType.DEPLOYMENT_DR,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["deployment", "dr", "backup", "restore", "canonical"],
            estimated_duration_seconds=180.0,
        )
    
    def _build_security_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_tenant_isolation",
                description="Test cross-tenant access rejection",
                action="test_cross_tenant_rejection",
                params={"profile": profile},
                expected={"rejected": True},
                invariants=["PROPERTY_1_TENANT_OWNERSHIP"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_scope_isolation",
                description="Test cross-scope access rejection",
                action="test_cross_scope_rejection",
                params={"profile": profile},
                expected={"rejected": True},
                invariants=["PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_provenance_spoofing",
                description="Test fake provenance rejection",
                action="test_provenance_spoofing",
                params={"profile": profile},
                expected={"rejected": True},
                invariants=["PROPERTY_5_PROVENANCE_VALID"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_unauthorized_autonomy",
                description="Test unauthorized autonomy rejection",
                action="test_unauthorized_autonomy",
                params={"profile": profile},
                expected={"rejected": True},
                invariants=["PROPERTY_2_CANONICAL_MUTATION", "PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"sec_{uuid.uuid4().hex[:8]}",
            name="Security / Tenant Matrix",
            description="Security posture across company classes",
            scenario_type=ScenarioType.SECURITY,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["security", "tenant_isolation", "canonical"],
            estimated_duration_seconds=120.0,
        )
    
    def _build_api_scenario(
        self,
        profile: Dict[str, EquivalenceClass],
        custom_steps: Optional[List[ScenarioStep]] = None,
    ) -> UniversalScenario:
        steps = self._base_steps(profile) + [
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_api_canonical_semantics",
                description="Test API semantics remain canonical across protocols",
                action="test_api_canonical_semantics",
                params={"profile": profile},
                expected={"semantics_canonical": True},
                invariants=["PROPERTY_12_NO_FORK"],
            ),
            ScenarioStep(
                phase=ScenarioPhase.EXECUTE,
                name="test_api_governance",
                description="Test governance enforced at API boundary",
                action="test_api_governance",
                params={"profile": profile},
                expected={"governance_enforced": True},
                invariants=["PROPERTY_2_CANONICAL_MUTATION", "PROPERTY_6_AUTHORIZATION_GOVERNED"],
            ),
        ] + self._validation_steps(CANONICAL_INVARIANTS)
        
        if custom_steps:
            steps.extend(custom_steps)
        
        return UniversalScenario(
            id=f"api_{uuid.uuid4().hex[:8]}",
            name="API / Interoperability",
            description="Universal API semantics across protocols",
            scenario_type=ScenarioType.API,
            profile={k: v.id for k, v in profile.items()},
            steps=steps,
            required_invariants=CANONICAL_INVARIANTS,
            tags=["api", "interoperability", "canonical"],
            estimated_duration_seconds=90.0,
        )


def create_scenario_builder() -> UniversalScenarioBuilder:
    """Factory function to create a scenario builder."""
    return UniversalScenarioBuilder(CompanyProfileBuilder())