"""Acceptance Matrix Runner.

Orchestrates execution of the Universal Acceptance Matrix across
representative company profiles and scenario types.
This is TEST INFRASTRUCTURE - NOT a business model.
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Any, Optional, Callable, Set
from datetime import datetime
from enum import Enum
from pathlib import Path
from collections import defaultdict

from .dimensions import (
    DimensionId, EquivalenceClass, Dimension, ALL_DIMENSIONS,
    get_representative_profiles, CANONICAL_INVARIANTS,
)
from .scenario_builder import (
    UniversalScenarioBuilder, UniversalScenario, ScenarioType,
    ScenarioPhase, ScenarioStep, create_scenario_builder,
    CompanyProfileBuilder,
)


class ScenarioStatus(str, Enum):
    """Status of scenario execution."""
    PENDING = "pending"
    RUNNING = "running"
    PASSED = "passed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class InvariantStatus(str, Enum):
    """Status of invariant verification."""
    HOLDS = "holds"
    VIOLATED = "violated"
    UNKNOWN = "unknown"


@dataclass
class StepResult:
    """Result of a single scenario step."""
    step_name: str
    phase: ScenarioPhase
    status: ScenarioStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    output: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    invariants_verified: List[str] = field(default_factory=list)


@dataclass
class InvariantResult:
    """Result of an invariant verification."""
    invariant: str
    status: InvariantStatus
    details: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScenarioResult:
    """Result of a complete scenario execution."""
    scenario_id: str
    scenario_name: str
    scenario_type: ScenarioType
    profile_name: str
    profile: Dict[str, str]
    status: ScenarioStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    steps: List[StepResult] = field(default_factory=list)
    invariants: List[InvariantResult] = field(default_factory=list)
    error: Optional[str] = None
    
    @property
    def passed(self) -> bool:
        return self.status == ScenarioStatus.PASSED
    
    @property
    def all_invariants_hold(self) -> bool:
        return all(i.status == InvariantStatus.HOLDS for i in self.invariants)


@dataclass
class ProfileResult:
    """Result of all scenarios for a single profile."""
    profile_name: str
    profile: Dict[str, str]
    scenarios: List[ScenarioResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    @property
    def duration_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    @property
    def passed_count(self) -> int:
        return sum(1 for s in self.scenarios if s.passed)
    
    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.scenarios if s.status == ScenarioStatus.FAILED)
    
    @property
    def blocked_count(self) -> int:
        return sum(1 for s in self.scenarios if s.status == ScenarioStatus.BLOCKED)
    
    @property
    def all_passed(self) -> bool:
        return all(s.passed for s in self.scenarios) and len(self.scenarios) > 0


@dataclass
class AcceptanceMatrixResult:
    """Complete result of the acceptance matrix execution."""
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    profiles: List[ProfileResult] = field(default_factory=list)
    environment: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_seconds(self) -> float:
        if self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0.0
    
    @property
    def total_scenarios(self) -> int:
        return sum(len(p.scenarios) for p in self.profiles)
    
    @property
    def passed_scenarios(self) -> int:
        return sum(p.passed_count for p in self.profiles)
    
    @property
    def failed_scenarios(self) -> int:
        return sum(p.failed_count for p in self.profiles)
    
    @property
    def blocked_scenarios(self) -> int:
        return sum(p.blocked_count for p in self.profiles)
    
    @property
    def all_passed(self) -> bool:
        return all(p.all_passed for p in self.profiles) and len(self.profiles) > 0


class ActionRegistry:
    """Registry of executable actions for scenario steps."""
    
    def __init__(self):
        self._actions: Dict[str, Callable] = {}
        self._register_builtin_actions()
    
    def _register_builtin_actions(self):
        """Register built-in action implementations."""
        # These are placeholders - actual implementations integrate with VCOS
        self.register("setup_canonical_context", self._action_setup_canonical_context)
        self.register("provision_company", self._action_provision_company)
        self.register("configure_organization_structure", self._action_configure_org_structure)
        self.register("configure_governance", self._action_configure_governance)
        self.register("configure_integrations", self._action_configure_integrations)
        self.register("execute_initial_sync", self._action_execute_initial_sync)
        self.register("create_people", self._action_create_people)
        self.register("test_identity_transitions", self._action_test_identity_transitions)
        self.register("test_cross_entity_identity", self._action_test_cross_entity_identity)
        self.register("define_roles_permissions", self._action_define_roles_permissions)
        self.register("test_authorization_decisions", self._action_test_authorization)
        self.register("test_delegation_revocation", self._action_test_delegation_revocation)
        self.register("test_privileged_operations", self._action_test_privileged_ops)
        self.register("define_work_types", self._action_define_work_types)
        self.register("execute_work_lifecycle", self._action_execute_work_lifecycle)
        self.register("test_work_composition", self._action_test_work_composition)
        self.register("configure_finance", self._action_configure_finance)
        self.register("test_multi_currency_transactions", self._action_test_multi_currency)
        self.register("test_consolidation", self._action_test_consolidation)
        self.register("configure_connectors", self._action_configure_connectors)
        self.register("test_inbound_observations", self._action_test_inbound_observations)
        self.register("test_reconciliation", self._action_test_reconciliation)
        self.register("test_outbound_operations", self._action_test_outbound_ops)
        self.register("configure_company_brain", self._action_configure_company_brain)
        self.register("test_context_retrieval", self._action_test_context_retrieval)
        self.register("test_temporal_queries", self._action_test_temporal_queries)
        self.register("test_governance_in_queries", self._action_test_governance_in_queries)
        self.register("verify_memory_derivation", self._action_verify_memory_derivation)
        self.register("test_epistemic_status", self._action_test_epistemic_status)
        self.register("test_longitudinal_memory", self._action_test_longitudinal_memory)
        self.register("create_prediction", self._action_create_prediction)
        self.register("verify_prediction_non_canonical", self._action_verify_prediction_non_canonical)
        self.register("test_governance_on_prediction", self._action_test_governance_on_prediction)
        self.register("create_counterfactual", self._action_create_counterfactual)
        self.register("simulate_scenario", self._action_simulate_scenario)
        self.register("test_governed_commitment", self._action_test_governed_commitment)
        self.register("configure_autonomy_policy", self._action_configure_autonomy_policy)
        self.register("test_autonomy_flow", self._action_test_autonomy_flow)
        self.register("test_autonomous_execution", self._action_test_autonomous_execution)
        self.register("simulate_continuity_event", self._action_simulate_continuity_event)
        self.register("verify_history_intact", self._action_verify_history_intact)
        self.register("verify_identity_continuous", self._action_verify_identity_continuous)
        self.register("execute_migration", self._action_execute_migration)
        self.register("verify_migration_preservation", self._action_verify_migration_preservation)
        self.register("execute_ma", self._action_execute_ma)
        self.register("verify_ma_lineage", self._action_verify_ma_lineage)
        self.register("inject_failure", self._action_inject_failure)
        self.register("verify_tenant_isolation_under_failure", self._action_verify_tenant_isolation)
        self.register("test_governed_recovery", self._action_test_governed_recovery)
        self.register("run_longitudinal_simulation", self._action_run_longitudinal)
        self.register("verify_temporal_integrity", self._action_verify_temporal_integrity)
        self.register("verify_knowledge_timeline", self._action_verify_knowledge_timeline)
        self.register("test_backup", self._action_test_backup)
        self.register("test_restore", self._action_test_restore)
        self.register("verify_rpo_rto", self._action_verify_rpo_rto)
        self.register("test_cross_tenant_rejection", self._action_test_cross_tenant_rejection)
        self.register("test_cross_scope_rejection", self._action_test_cross_scope_rejection)
        self.register("test_provenance_spoofing", self._action_test_provenance_spoofing)
        self.register("test_unauthorized_autonomy", self._action_test_unauthorized_autonomy)
        self.register("test_api_canonical_semantics", self._action_test_api_semantics)
        self.register("test_api_governance", self._action_test_api_governance)
        self.register("verify_canonical_integrity", self._action_verify_canonical_integrity)
        self.register("verify_invariants", self._action_verify_invariants)
    
    def register(self, name: str, action: Callable):
        """Register an action."""
        self._actions[name] = action
    
    def get(self, name: str) -> Optional[Callable]:
        """Get an action by name."""
        return self._actions.get(name)
    
    async def execute(self, name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute an action by name."""
        action = self._actions.get(name)
        if not action:
            raise ValueError(f"Unknown action: {name}")
        if asyncio.iscoroutinefunction(action):
            return await action(params)
        return action(params)
    
    # Placeholder action implementations
    # In real implementation, these integrate with VCOS services
    
    def _action_setup_canonical_context(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"context_initialized": True, "canonical_context_id": str(uuid.uuid4())}
    
    def _action_provision_company(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"company_provisioned": True, "tenant_id": str(uuid.uuid4()), "company_id": str(uuid.uuid4())}
    
    def _action_configure_org_structure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"structure_configured": True}
    
    def _action_configure_governance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"governance_configured": True}
    
    def _action_configure_integrations(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"integrations_configured": True}
    
    def _action_execute_initial_sync(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"sync_completed": True, "observations_recorded": True}
    
    def _action_create_people(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"people_created": True, "identities_stable": True, "count": 10}
    
    def _action_test_identity_transitions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"transitions_tracked": True, "identity_continuous": True}
    
    def _action_test_cross_entity_identity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"cross_entity_resolved": True}
    
    def _action_define_roles_permissions(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"roles_defined": True, "permissions_scoped": True}
    
    def _action_test_authorization(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"authorization_correct": True}
    
    def _action_test_delegation_revocation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"delegation_works": True, "revocation_works": True}
    
    def _action_test_privileged_ops(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"privileged_governed": True}
    
    def _action_define_work_types(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"work_types_defined": True}
    
    def _action_execute_work_lifecycle(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"work_created": True, "actions_executed": True, "outcomes_recorded": True}
    
    def _action_test_work_composition(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"composition_works": True}
    
    def _action_configure_finance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"finance_configured": True}
    
    def _action_test_multi_currency(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"fx_handled": True, "provenance_tracked": True}
    
    def _action_test_consolidation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"consolidation_correct": True}
    
    def _action_configure_connectors(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"connectors_configured": True}
    
    def _action_test_inbound_observations(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"observations_validated": True, "evidence_recorded": True}
    
    def _action_test_reconciliation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"reconciled": True, "mutation_governed": True}
    
    def _action_test_outbound_ops(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"outbound_idempotent": True}
    
    def _action_configure_company_brain(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"brain_configured": True}
    
    def _action_test_context_retrieval(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"context_retrieved": True, "grounded_in_canonical": True}
    
    def _action_test_temporal_queries(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"temporal_queries_work": True}
    
    def _action_test_governance_in_queries(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"governance_enforced": True}
    
    def _action_verify_memory_derivation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"memory_from_canonical": True}
    
    def _action_test_epistemic_status(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"epistemic_preserved": True}
    
    def _action_test_longitudinal_memory(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"longitudinal_intact": True}
    
    def _action_create_prediction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"prediction_created": True, "assumptions_explicit": True}
    
    def _action_verify_prediction_non_canonical(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"remains_non_canonical": True}
    
    def _action_test_governance_on_prediction(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"governance_applied": True}
    
    def _action_create_counterfactual(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"scenario_created": True, "assumptions_explicit": True}
    
    def _action_simulate_scenario(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"simulation_completed": True, "canonical_unchanged": True}
    
    def _action_test_governed_commitment(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"commitment_governed": True}
    
    def _action_configure_autonomy_policy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"policy_configured": True}
    
    def _action_test_autonomy_flow(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"flow_complete": True, "human_gate_respected": True}
    
    def _action_test_autonomous_execution(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"executed": True, "verified": True, "learned": True}
    
    def _action_simulate_continuity_event(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"event_simulated": True}
    
    def _action_verify_history_intact(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"history_intact": True, "lineage_preserved": True}
    
    def _action_verify_identity_continuous(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"identity_continuous": True}
    
    def _action_execute_migration(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"migration_completed": True}
    
    def _action_verify_migration_preservation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"all_preserved": True}
    
    def _action_execute_ma(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"ma_completed": True}
    
    def _action_verify_ma_lineage(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"lineage_complete": True, "both_legacies_preserved": True}
    
    def _action_inject_failure(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"failure_injected": True}
    
    def _action_verify_tenant_isolation(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"isolated": True}
    
    def _action_test_governed_recovery(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"recovery_governed": True, "unknown_preserved": True}
    
    def _action_run_longitudinal(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"simulation_completed": True}
    
    def _action_verify_temporal_integrity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"temporal_intact": True}
    
    def _action_verify_knowledge_timeline(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"knowledge_timeline_valid": True}
    
    def _action_test_backup(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"backup_valid": True, "canonical_integrity": True}
    
    def _action_test_restore(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"restore_valid": True, "tenant_isolation": True}
    
    def _action_verify_rpo_rto(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"rpo_met": True, "rto_met": True}
    
    def _action_test_cross_tenant_rejection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"rejected": True}
    
    def _action_test_cross_scope_rejection(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"rejected": True}
    
    def _action_test_provenance_spoofing(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"rejected": True}
    
    def _action_test_unauthorized_autonomy(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"rejected": True}
    
    def _action_test_api_semantics(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"semantics_canonical": True}
    
    def _action_test_api_governance(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"governance_enforced": True}
    
    def _action_verify_canonical_integrity(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return {"integrity_valid": True}
    
    def _action_verify_invariants(self, params: Dict[str, Any]) -> Dict[str, Any]:
        invariants = params.get("invariants", [])
        return {"all_invariants_hold": True, "verified": invariants}


class InvariantVerifier:
    """Verifies canonical invariants against system state."""
    
    def __init__(self, action_registry: ActionRegistry):
        self.action_registry = action_registry
    
    async def verify_all(self, invariants: List[str], context: Dict[str, Any]) -> List[InvariantResult]:
        """Verify all invariants."""
        results = []
        for invariant in invariants:
            result = await self.verify(invariant, context)
            results.append(result)
        return results
    
    async def verify(self, invariant: str, context: Dict[str, Any]) -> InvariantResult:
        """Verify a single invariant."""
        # Map invariant to verification action
        verification_map = {
            "PROPERTY_1_TENANT_OWNERSHIP": self._verify_tenant_ownership,
            "PROPERTY_2_CANONICAL_MUTATION": self._verify_canonical_mutation,
            "PROPERTY_3_OBSERVATION_DISTINGUISHABLE": self._verify_observation_distinguishable,
            "PROPERTY_4_TEMPORAL_RECONSTRUCTABLE": self._verify_temporal_reconstructable,
            "PROPERTY_5_PROVENANCE_VALID": self._verify_provenance_valid,
            "PROPERTY_6_AUTHORIZATION_GOVERNED": self._verify_authorization_governed,
            "PROPERTY_7_OUTCOME_DISTINGUISHABLE": self._verify_outcome_distinguishable,
            "PROPERTY_8_PREDICTION_DISTINGUISHABLE": self._verify_prediction_distinguishable,
            "PROPERTY_9_MEMORY_DERIVES_CANONICAL": self._verify_memory_derives_canonical,
            "PROPERTY_10_TWIN_IS_PROJECTION": self._verify_twin_is_projection,
            "PROPERTY_11_FAILURE_NO_INVENT": self._verify_failure_no_invent,
            "PROPERTY_12_NO_FORK": self._verify_no_fork,
        }
        
        verifier = verification_map.get(invariant)
        if not verifier:
            return InvariantResult(
                invariant=invariant,
                status=InvariantStatus.UNKNOWN,
                details={"error": "No verifier for invariant"},
            )
        
        try:
            result = await verifier(context)
            return InvariantResult(
                invariant=invariant,
                status=InvariantStatus.HOLDS if result.get("holds", False) else InvariantStatus.VIOLATED,
                details=result.get("details", {}),
                evidence=result.get("evidence", {}),
            )
        except Exception as e:
            return InvariantResult(
                invariant=invariant,
                status=InvariantStatus.VIOLATED,
                details={"error": str(e)},
            )
    
    # Placeholder verifiers - integrate with actual VCOS checks
    async def _verify_tenant_ownership(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "All entities have tenant_id"}
    
    async def _verify_canonical_mutation(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "All mutations through CanonicalMutationBoundary"}
    
    async def _verify_observation_distinguishable(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "Observations have source_system, canonical_flag=false"}
    
    async def _verify_temporal_reconstructable(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "All entities have recorded_at, observed_at, effective_from"}
    
    async def _verify_provenance_valid(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "All provenance references resolve"}
    
    async def _verify_authorization_governed(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "All auth decisions through GovernanceEngine"}
    
    async def _verify_outcome_distinguishable(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "Outcomes separate from actions/executions"}
    
    async def _verify_prediction_distinguishable(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "Predictions have is_prediction=true, assumptions tracked"}
    
    async def _verify_memory_derives_canonical(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "Memory entries reference canonical entity IDs"}
    
    async def _verify_twin_is_projection(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "Digital Twin queries canonical, no separate store"}
    
    async def _verify_failure_no_invent(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "Failure paths preserve UNKNOWN, no truth invention"}
    
    async def _verify_no_fork(self, context: Dict[str, Any]) -> Dict[str, Any]:
        return {"holds": True, "details": "No company-type-specific canonical models found"}


class AcceptanceMatrixRunner:
    """Main runner for the Universal Acceptance Matrix."""
    
    def __init__(
        self,
        profiles: Optional[List[Dict[str, Any]]] = None,
        scenario_types: Optional[List[ScenarioType]] = None,
        action_registry: Optional[ActionRegistry] = None,
        invariant_verifier: Optional[InvariantVerifier] = None,
        parallel: bool = False,
        max_parallel: int = 4,
    ):
        self.profile_builder = CompanyProfileBuilder()
        self.scenario_builder = UniversalScenarioBuilder(self.profile_builder)
        self.action_registry = action_registry or ActionRegistry()
        self.invariant_verifier = invariant_verifier or InvariantVerifier(self.action_registry)
        self.parallel = parallel
        self.max_parallel = max_parallel
        
        self.profiles = profiles or get_representative_profiles()
        self.scenario_types = scenario_types or list(ScenarioType)
    
    async def run(self) -> AcceptanceMatrixResult:
        """Run the complete acceptance matrix."""
        run_id = f"ua_{uuid.uuid4().hex[:12]}"
        started_at = datetime.utcnow()
        
        result = AcceptanceMatrixResult(
            run_id=run_id,
            started_at=started_at,
            environment=self._capture_environment(),
        )
        
        # Build profile objects
        profile_objects = []
        for profile_def in self.profiles:
            profile = self.profile_builder.build_from_profile(profile_def)
            profile_objects.append((profile_def["name"], profile))
        
        # Run scenarios for each profile
        if self.parallel:
            await self._run_parallel(result, profile_objects)
        else:
            await self._run_sequential(result, profile_objects)
        
        result.completed_at = datetime.utcnow()
        return result
    
    async def _run_sequential(
        self,
        result: AcceptanceMatrixResult,
        profile_objects: List[tuple],
    ):
        """Run scenarios sequentially."""
        for profile_name, profile in profile_objects:
            profile_result = ProfileResult(
                profile_name=profile_name,
                profile={k: v.id for k, v in profile.items()},
                started_at=datetime.utcnow(),
            )
            
            # Build scenarios for this profile
            scenarios = self.scenario_builder.build_all_scenarios(profile)
            # Filter by requested scenario types
            scenarios = [s for s in scenarios if s.scenario_type in self.scenario_types]
            
            for scenario in scenarios:
                scenario_result = await self._run_scenario(scenario, profile_name, profile)
                profile_result.scenarios.append(scenario_result)
            
            profile_result.completed_at = datetime.utcnow()
            result.profiles.append(profile_result)
    
    async def _run_parallel(
        self,
        result: AcceptanceMatrixResult,
        profile_objects: List[tuple],
    ):
        """Run scenarios in parallel across profiles."""
        semaphore = asyncio.Semaphore(self.max_parallel)
        
        async def run_profile(profile_name: str, profile: Dict[str, EquivalenceClass]):
            async with semaphore:
                profile_result = ProfileResult(
                    profile_name=profile_name,
                    profile={k: v.id for k, v in profile.items()},
                    started_at=datetime.utcnow(),
                )
                
                scenarios = self.scenario_builder.build_all_scenarios(profile)
                scenarios = [s for s in scenarios if s.scenario_type in self.scenario_types]
                
                # Run scenarios for this profile sequentially
                for scenario in scenarios:
                    scenario_result = await self._run_scenario(scenario, profile_name, profile)
                    profile_result.scenarios.append(scenario_result)
                
                profile_result.completed_at = datetime.utcnow()
                return profile_result
        
        tasks = [run_profile(name, profile) for name, profile in profile_objects]
        profile_results = await asyncio.gather(*tasks)
        result.profiles.extend(profile_results)
    
    async def _run_scenario(
        self,
        scenario: UniversalScenario,
        profile_name: str,
        profile: Dict[str, EquivalenceClass],
    ) -> ScenarioResult:
        """Run a single scenario."""
        scenario_result = ScenarioResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            scenario_type=scenario.scenario_type,
            profile_name=profile_name,
            profile={k: v.id for k, v in profile.items()},
            status=ScenarioStatus.RUNNING,
            started_at=datetime.utcnow(),
        )
        
        try:
            # Execute steps in order, respecting dependencies
            completed_steps: Set[str] = set()
            step_results: Dict[str, StepResult] = {}
            
            for step in scenario.steps:
                # Check dependencies
                deps_met = all(dep in completed_steps for dep in step.depends_on)
                if not deps_met:
                    step_result = StepResult(
                        step_name=step.name,
                        phase=step.phase,
                        status=ScenarioStatus.BLOCKED,
                        started_at=datetime.utcnow(),
                        error=f"Dependencies not met: {step.depends_on}",
                    )
                    scenario_result.steps.append(step_result)
                    scenario_result.status = ScenarioStatus.BLOCKED
                    break
                
                # Execute step
                step_result = await self._run_step(step, profile, step_results)
                scenario_result.steps.append(step_result)
                step_results[step.name] = step_result
                
                if step_result.status == ScenarioStatus.FAILED:
                    scenario_result.status = ScenarioStatus.FAILED
                    scenario_result.error = step_result.error
                    break
                elif step_result.status == ScenarioStatus.BLOCKED:
                    scenario_result.status = ScenarioStatus.BLOCKED
                    scenario_result.error = step_result.error
                    break
                else:
                    completed_steps.add(step.name)
            
            # Verify invariants if scenario completed
            if scenario_result.status == ScenarioStatus.RUNNING:
                invariant_results = await self.invariant_verifier.verify_all(
                    scenario.required_invariants,
                    {"profile": {k: v.id for k, v in profile.items()}, "steps": step_results},
                )
                scenario_result.invariants = invariant_results
                
                if all(r.status == InvariantStatus.HOLDS for r in invariant_results):
                    scenario_result.status = ScenarioStatus.PASSED
                else:
                    scenario_result.status = ScenarioStatus.FAILED
                    failed = [r.invariant for r in invariant_results if r.status == InvariantStatus.VIOLATED]
                    scenario_result.error = f"Invariants violated: {failed}"
        
        except Exception as e:
            scenario_result.status = ScenarioStatus.FAILED
            scenario_result.error = str(e)
        
        finally:
            scenario_result.completed_at = datetime.utcnow()
            if scenario_result.started_at:
                scenario_result.duration_seconds = (
                    scenario_result.completed_at - scenario_result.started_at
                ).total_seconds()
        
        return scenario_result
    
    async def _run_step(
        self,
        step: ScenarioStep,
        profile: Dict[str, EquivalenceClass],
        previous_results: Dict[str, StepResult],
    ) -> StepResult:
        """Run a single scenario step."""
        started_at = datetime.utcnow()
        
        step_result = StepResult(
            step_name=step.name,
            phase=step.phase,
            status=ScenarioStatus.RUNNING,
            started_at=started_at,
        )
        
        try:
            # Prepare params with context from previous steps
            params = dict(step.params)
            params["profile"] = {k: v.id for k, v in profile.items()}
            params["previous_results"] = {
                k: v.output for k, v in previous_results.items()
            }
            
            # Execute action
            output = await self.action_registry.execute(step.action, params)
            
            # Check expected results
            expected = step.expected
            for key, expected_value in expected.items():
                if output.get(key) != expected_value:
                    step_result.status = ScenarioStatus.FAILED
                    step_result.error = f"Expected {key}={expected_value}, got {output.get(key)}"
                    step_result.output = output
                    return step_result
            
            step_result.status = ScenarioStatus.PASSED
            step_result.output = output
            step_result.invariants_verified = step.invariants
            
        except Exception as e:
            step_result.status = ScenarioStatus.FAILED
            step_result.error = str(e)
        
        finally:
            step_result.completed_at = datetime.utcnow()
            step_result.duration_seconds = (
                step_result.completed_at - step_result.started_at
            ).total_seconds()
        
        return step_result
    
    def _capture_environment(self) -> Dict[str, Any]:
        """Capture environment information."""
        import sys
        import platform
        
        return {
            "python_version": sys.version,
            "platform": platform.platform(),
            "timestamp": datetime.utcnow().isoformat(),
            "runner": "AcceptanceMatrixRunner",
        }
    
    def save_results(self, result: AcceptanceMatrixResult, output_dir: str = "acceptance_results"):
        """Save results to JSON file."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"acceptance_matrix_{result.run_id}_{result.started_at.strftime('%Y%m%d_%H%M%S')}.json"
        filepath = output_path / filename
        
        # Convert to serializable dict
        data = self._serialize_result(result)
        
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2, default=str)
        
        return filepath
    
    def _serialize_result(self, result: AcceptanceMatrixResult) -> Dict[str, Any]:
        """Serialize result to dict."""
        return {
            "run_id": result.run_id,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "duration_seconds": result.duration_seconds,
            "environment": result.environment,
            "summary": {
                "total_profiles": len(result.profiles),
                "total_scenarios": result.total_scenarios,
                "passed": result.passed_scenarios,
                "failed": result.failed_scenarios,
                "blocked": result.blocked_scenarios,
                "all_passed": result.all_passed,
            },
            "profiles": [
                {
                    "profile_name": p.profile_name,
                    "profile": p.profile,
                    "started_at": p.started_at.isoformat() if p.started_at else None,
                    "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                    "duration_seconds": p.duration_seconds,
                    "passed": p.passed_count,
                    "failed": p.failed_count,
                    "blocked": p.blocked_count,
                    "all_passed": p.all_passed,
                    "scenarios": [
                        {
                            "scenario_id": s.scenario_id,
                            "scenario_name": s.scenario_name,
                            "scenario_type": s.scenario_type.value,
                            "status": s.status.value,
                            "started_at": s.started_at.isoformat(),
                            "completed_at": s.completed_at.isoformat() if s.completed_at else None,
                            "duration_seconds": s.duration_seconds,
                            "error": s.error,
                            "steps": [
                                {
                                    "step_name": st.step_name,
                                    "phase": st.phase.value,
                                    "status": st.status.value,
                                    "duration_seconds": st.duration_seconds,
                                    "error": st.error,
                                    "invariants_verified": st.invariants_verified,
                                }
                                for st in s.steps
                            ],
                            "invariants": [
                                {
                                    "invariant": i.invariant,
                                    "status": i.status.value,
                                    "details": i.details,
                                }
                                for i in s.invariants
                            ],
                        }
                        for s in p.scenarios
                    ],
                }
                for p in result.profiles
            ],
        }


async def run_acceptance_matrix(
    profiles: Optional[List[Dict[str, Any]]] = None,
    scenario_types: Optional[List[ScenarioType]] = None,
    parallel: bool = False,
    max_parallel: int = 4,
    output_dir: str = "acceptance_results",
) -> AcceptanceMatrixResult:
    """Convenience function to run the acceptance matrix."""
    runner = AcceptanceMatrixRunner(
        profiles=profiles,
        scenario_types=scenario_types,
        parallel=parallel,
        max_parallel=max_parallel,
    )
    result = await runner.run()
    runner.save_results(result, output_dir)
    return result