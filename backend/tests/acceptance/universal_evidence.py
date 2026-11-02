"""Universal Acceptance Evidence.

Extends ScaleAcceptanceEvidence with universal acceptance specific domains.
This is TEST INFRASTRUCTURE - NOT a business/domain model.
"""

import json
import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from pathlib import Path

# Import base evidence classes
from tests.scale.acceptance_evidence import (
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
    ConcurrencyEvidence,
    ScaleAcceptanceEvidence,
    create_acceptance_evidence,
)


@dataclass
class UniversalityEvidence:
    """Universality validation evidence."""
    dimensions_tested: List[str] = field(default_factory=list)
    profiles_tested: List[str] = field(default_factory=list)
    scenario_types_tested: List[str] = field(default_factory=list)
    equivalence_classes_covered: Dict[str, List[str]] = field(default_factory=dict)
    cross_profile_invariants_held: bool = True
    anti_fork_verified: bool = False
    forks_detected: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return self.cross_profile_invariants_held and self.anti_fork_verified


@dataclass
class ScaleMatrixEvidence:
    """Scale matrix validation evidence."""
    scales_tested: List[str] = field(default_factory=list)
    scale_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    canonical_at_all_scales: bool = True
    performance_by_scale: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return self.canonical_at_all_scales


@dataclass
class OrgStructureEvidence:
    """Organizational structure validation evidence."""
    structures_tested: List[str] = field(default_factory=list)
    structure_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    identity_universal: bool = True
    governance_universal: bool = True
    work_universal: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return self.identity_universal and self.governance_universal and self.work_universal


@dataclass
class IndustryEvidence:
    """Industry validation evidence."""
    industries_tested: List[str] = field(default_factory=list)
    industry_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    primitives_compose: bool = True
    no_industry_specific_models: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return self.primitives_compose and self.no_industry_specific_models


@dataclass
class GeographyEvidence:
    """Geography/localization validation evidence."""
    geographies_tested: List[str] = field(default_factory=list)
    geography_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    timezone_handling: bool = True
    currency_handling: bool = True
    fiscal_calendar_handling: bool = True
    no_region_specific_reality: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.timezone_handling,
            self.currency_handling,
            self.fiscal_calendar_handling,
            self.no_region_specific_reality,
        ])


@dataclass
class MultiCompanyEvidence:
    """Multi-company validation evidence."""
    configurations_tested: List[str] = field(default_factory=list)
    multi_company_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tenant_isolation_absolute: bool = True
    cross_company_queries_scoped: bool = True
    ma_lineage_preserved: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.tenant_isolation_absolute,
            self.cross_company_queries_scoped,
            self.ma_lineage_preserved,
        ])


@dataclass
class IdentityEvidence:
    """Universal identity validation evidence."""
    scenarios_tested: List[str] = field(default_factory=list)
    identity_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    identity_stable_across_contexts: bool = True
    no_duplicate_person_graphs: bool = True
    provenance_tracks_all_events: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.identity_stable_across_contexts,
            self.no_duplicate_person_graphs,
            self.provenance_tracks_all_events,
        ])


@dataclass
class WorkEvidence:
    """Universal work model validation evidence."""
    work_types_tested: List[str] = field(default_factory=list)
    work_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    work_action_outcome_universal: bool = True
    no_independent_work_engines: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return self.work_action_outcome_universal and self.no_independent_work_engines


@dataclass
class GovernanceEvidence:
    """Universal governance validation evidence."""
    configurations_tested: List[str] = field(default_factory=list)
    governance_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    single_governance_engine: bool = True
    authorization_always_canonical: bool = True
    delegation_temporal_revocable: bool = True
    no_parallel_engines: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.single_governance_engine,
            self.authorization_always_canonical,
            self.delegation_temporal_revocable,
            self.no_parallel_engines,
        ])


@dataclass
class IntegrationEvidence:
    """Integration universality validation evidence."""
    connectors_tested: List[str] = field(default_factory=list)
    integration_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    universal_connector_contract_enforced: bool = True
    observations_distinct_from_canonical: bool = True
    reconciliation_governed: bool = True
    no_connector_specific_paths: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.universal_connector_contract_enforced,
            self.observations_distinct_from_canonical,
            self.reconciliation_governed,
            self.no_connector_specific_paths,
        ])


@dataclass
class CompanyBrainEvidence:
    """Company Brain projection validation evidence."""
    configurations_tested: List[str] = field(default_factory=list)
    brain_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    always_projection_over_canonical: bool = True
    never_separate_intelligence: bool = True
    governance_respected: bool = True
    temporal_queries_work: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.always_projection_over_canonical,
            self.never_separate_intelligence,
            self.governance_respected,
            self.temporal_queries_work,
        ])


@dataclass
class MemoryEvidence:
    """Living Company Memory validation evidence."""
    configurations_tested: List[str] = field(default_factory=list)
    memory_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    derives_from_canonical: bool = True
    no_separate_memory_store: bool = True
    epistemic_status_preserved: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.derives_from_canonical,
            self.no_separate_memory_store,
            self.epistemic_status_preserved,
        ])


@dataclass
class PredictionEvidence:
    """Prediction/Forecasting validation evidence."""
    scenarios_tested: List[str] = field(default_factory=list)
    prediction_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    explicit_assumptions: bool = True
    never_becomes_canonical: bool = True
    governed_by_same_authorization: bool = True
    traceable_to_canonical_inputs: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.explicit_assumptions,
            self.never_becomes_canonical,
            self.governed_by_same_authorization,
            self.traceable_to_canonical_inputs,
        ])


@dataclass
class CounterfactualEvidence:
    """Counterfactual/Simulation validation evidence."""
    scenarios_tested: List[str] = field(default_factory=list)
    counterfactual_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    explicitly_non_canonical: bool = True
    assumptions_uncertainty_first_class: bool = True
    governed_commitment: bool = True
    canonical_unchanged: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.explicitly_non_canonical,
            self.assumptions_uncertainty_first_class,
            self.governed_commitment,
            self.canonical_unchanged,
        ])


@dataclass
class AutonomyEvidence:
    """Governed Autonomous Operations validation evidence."""
    levels_tested: List[str] = field(default_factory=list)
    autonomy_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    eligibility_evidence_governance_authorization: bool = True
    human_control_preserved: bool = True
    no_separate_auth_system: bool = True
    all_actions_provenance_tracked: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.eligibility_evidence_governance_authorization,
            self.human_control_preserved,
            self.no_separate_auth_system,
            self.all_actions_provenance_tracked,
        ])


@dataclass
class ContinuityEvidence:
    """Company Continuity validation evidence."""
    scenarios_tested: List[str] = field(default_factory=list)
    continuity_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    history_intact: bool = True
    canonical_preserves_all_facts: bool = True
    identity_governance_decision_lineage_continuous: bool = True
    no_historical_truth_rewriting: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.history_intact,
            self.canonical_preserves_all_facts,
            self.identity_governance_decision_lineage_continuous,
            self.no_historical_truth_rewriting,
        ])


@dataclass
class MigrationEvidence:
    """Migration universality validation evidence."""
    scenarios_tested: List[str] = field(default_factory=list)
    migration_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    identity_provenance_history_preserved: bool = True
    governance_decision_history_learning_preserved: bool = True
    no_truth_rewriting: bool = True
    canonical_mutation_governs: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.identity_provenance_history_preserved,
            self.governance_decision_history_learning_preserved,
            self.no_truth_rewriting,
            self.canonical_mutation_governs,
        ])


@dataclass
class MAEvidence:
    """M&A Lineage validation evidence."""
    scenarios_tested: List[str] = field(default_factory=list)
    ma_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    lineage_canonical_temporal: bool = True
    both_legacies_preserved: bool = True
    identity_governance_finance_traceable: bool = True
    no_separate_ma_model: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.lineage_canonical_temporal,
            self.both_legacies_preserved,
            self.identity_governance_finance_traceable,
            self.no_separate_ma_model,
        ])


@dataclass
class FailureUniversalityEvidence:
    """Failure + Universality validation evidence."""
    scenarios_tested: List[str] = field(default_factory=list)
    failure_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tenant_a_failure_not_b: bool = True
    regional_outage_isolated: bool = True
    recovery_governed: bool = True
    unknown_preserved: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.tenant_a_failure_not_b,
            self.regional_outage_isolated,
            self.recovery_governed,
            self.unknown_preserved,
        ])


@dataclass
class LongitudinalUniversalityEvidence:
    """Longitudinal + Universality validation evidence."""
    scenarios_tested: List[str] = field(default_factory=list)
    longitudinal_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    historical_truth_valid: bool = True
    knowledge_timeline_valid: bool = True
    decision_timeline_valid: bool = True
    learning_valid: bool = True
    ma_lineage_valid: bool = True
    organizational_continuity_valid: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.historical_truth_valid,
            self.knowledge_timeline_valid,
            self.decision_timeline_valid,
            self.learning_valid,
            self.ma_lineage_valid,
            self.organizational_continuity_valid,
        ])


@dataclass
class DeploymentDREvidence:
    """Deployment/DR Acceptance validation evidence."""
    scales_tested: List[str] = field(default_factory=list)
    dr_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    backup_valid: bool = True
    restore_valid: bool = True
    tenant_isolation_maintained: bool = True
    rpo_rto_met: bool = True
    canonical_integrity_verified: bool = True
    temporal_integrity_preserved: bool = True
    provenance_chain_unbroken: bool = True
    company_brain_recoverable: bool = True
    longitudinal_state_recoverable: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.backup_valid,
            self.restore_valid,
            self.tenant_isolation_maintained,
            self.rpo_rto_met,
            self.canonical_integrity_verified,
            self.temporal_integrity_preserved,
            self.provenance_chain_unbroken,
            self.company_brain_recoverable,
            self.longitudinal_state_recoverable,
        ])


@dataclass
class SecurityEvidence:
    """Security/Tenant Matrix validation evidence."""
    configurations_tested: List[str] = field(default_factory=list)
    security_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    tenant_isolation_canonical_invariant: bool = True
    scope_isolation_at_mutation: bool = True
    provenance_tracks_access: bool = True
    no_security_level_models: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.tenant_isolation_canonical_invariant,
            self.scope_isolation_at_mutation,
            self.provenance_tracks_access,
            self.no_security_level_models,
        ])


@dataclass
class APIEvidence:
    """API/Interoperability validation evidence."""
    protocols_tested: List[str] = field(default_factory=list)
    api_results: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    semantics_canonical_across_protocols: bool = True
    no_protocol_specific_reality: bool = True
    governance_at_boundary: bool = True
    provenance_tracks_source: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.semantics_canonical_across_protocols,
            self.no_protocol_specific_reality,
            self.governance_at_boundary,
            self.provenance_tracks_source,
        ])


@dataclass
class UniversalAcceptanceEvidence(ScaleAcceptanceEvidence):
    """Complete universal acceptance evidence artifact.
    
    Extends ScaleAcceptanceEvidence with universal acceptance domains.
    This is a TEST INFRASTRUCTURE projection over the canonical VCOS system.
    It is NOT a business/domain model and must not become another source of truth.
    """
    
    # Universal acceptance specific fields
    universality: Optional[UniversalityEvidence] = None
    scale_matrix: Optional[ScaleMatrixEvidence] = None
    org_structure: Optional[OrgStructureEvidence] = None
    industry: Optional[IndustryEvidence] = None
    geography: Optional[GeographyEvidence] = None
    multi_company: Optional[MultiCompanyEvidence] = None
    identity: Optional[IdentityEvidence] = None
    work: Optional[WorkEvidence] = None
    governance_universal: Optional[GovernanceEvidence] = None
    integration: Optional[IntegrationEvidence] = None
    company_brain_universal: Optional[CompanyBrainEvidence] = None
    memory_universal: Optional[MemoryEvidence] = None
    prediction: Optional[PredictionEvidence] = None
    counterfactual: Optional[CounterfactualEvidence] = None
    autonomy: Optional[AutonomyEvidence] = None
    continuity: Optional[ContinuityEvidence] = None
    migration: Optional[MigrationEvidence] = None
    ma: Optional[MAEvidence] = None
    failure_universality: Optional[FailureUniversalityEvidence] = None
    longitudinal_universality: Optional[LongitudinalUniversalityEvidence] = None
    deployment_dr: Optional[DeploymentDREvidence] = None
    security: Optional[SecurityEvidence] = None
    api: Optional[APIEvidence] = None
    
    # Matrix execution metadata
    matrix_run_id: str = ""
    profiles_executed: List[str] = field(default_factory=list)
    scenarios_executed: List[str] = field(default_factory=list)
    total_scenarios: int = 0
    passed_scenarios: int = 0
    failed_scenarios: int = 0
    blocked_scenarios: int = 0
    
    def __post_init__(self):
        super().__post_init__()
        if not self.matrix_run_id:
            self.matrix_run_id = str(uuid.uuid4())[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary, excluding secrets."""
        data = super().to_dict()
        
        # Add universal acceptance fields
        universal_fields = [
            'universality', 'scale_matrix', 'org_structure', 'industry',
            'geography', 'multi_company', 'identity', 'work',
            'governance_universal', 'integration', 'company_brain_universal',
            'memory_universal', 'prediction', 'counterfactual', 'autonomy',
            'continuity', 'migration', 'ma', 'failure_universality',
            'longitudinal_universality', 'deployment_dr', 'security', 'api',
            'matrix_run_id', 'profiles_executed', 'scenarios_executed',
            'total_scenarios', 'passed_scenarios', 'failed_scenarios',
            'blocked_scenarios',
        ]
        
        for field_name in universal_fields:
            value = getattr(self, field_name, None)
            if value is not None:
                if hasattr(value, 'to_dict'):
                    data[field_name] = value.to_dict()
                elif isinstance(value, Enum):
                    data[field_name] = value.value
                elif isinstance(value, dict):
                    data[field_name] = {k: v.to_dict() if hasattr(v, 'to_dict') else v 
                                        for k, v in value.items()}
                else:
                    data[field_name] = value
        
        return data
    
    def determine_acceptance(self) -> AcceptanceResult:
        """Determine acceptance result from all evidence domains."""
        # Check mandatory scale checks first
        scale_result = super().determine_acceptance()
        if scale_result != AcceptanceResult.PASS:
            return scale_result
        
        # Check all universal acceptance domains
        domains = [
            self.universality,
            self.scale_matrix,
            self.org_structure,
            self.industry,
            self.geography,
            self.multi_company,
            self.identity,
            self.work,
            self.governance_universal,
            self.integration,
            self.company_brain_universal,
            self.memory_universal,
            self.prediction,
            self.counterfactual,
            self.autonomy,
            self.continuity,
            self.migration,
            self.ma,
            self.failure_universality,
            self.longitudinal_universality,
            self.deployment_dr,
            self.security,
            self.api,
        ]
        
        for domain in domains:
            if domain is not None and not domain.all_passed():
                return AcceptanceResult.FAIL
        
        return AcceptanceResult.PASS
    
    def get_universality_summary(self) -> Dict[str, Any]:
        """Get summary of universality validation."""
        domains = {
            'universality': self.universality,
            'scale_matrix': self.scale_matrix,
            'org_structure': self.org_structure,
            'industry': self.industry,
            'geography': self.geography,
            'multi_company': self.multi_company,
            'identity': self.identity,
            'work': self.work,
            'governance': self.governance_universal,
            'integration': self.integration,
            'company_brain': self.company_brain_universal,
            'memory': self.memory_universal,
            'prediction': self.prediction,
            'counterfactual': self.counterfactual,
            'autonomy': self.autonomy,
            'continuity': self.continuity,
            'migration': self.migration,
            'ma': self.ma,
            'failure_universality': self.failure_universality,
            'longitudinal_universality': self.longitudinal_universality,
            'deployment_dr': self.deployment_dr,
            'security': self.security,
            'api': self.api,
        }
        
        summary = {}
        for name, domain in domains.items():
            if domain is not None:
                summary[name] = {
                    'tested': True,
                    'passed': domain.all_passed(),
                }
            else:
                summary[name] = {
                    'tested': False,
                    'passed': False,
                }
        
        return summary
    
    @classmethod
    def from_json(cls, json_str: str) -> 'UniversalAcceptanceEvidence':
        """Deserialize from JSON."""
        data = json.loads(json_str)
        
        # Convert enums back
        if 'acceptance_result' in data and data['acceptance_result']:
            data['acceptance_result'] = AcceptanceResult(data['acceptance_result'])
        
        # Reconstruct base evidence domain objects
        base_evidence_fields = [
            'environment', 'generation', 'structural_integrity', 
            'tenant_isolation', 'temporal', 'provenance', 'epistemic',
            'governance', 'company_brain', 'performance', 'resources',
            'recovery', 'promotion', 'concurrency'
        ]
        
        base_evidence_classes = {
            'environment': EnvironmentEvidence,
            'generation': GenerationEvidence,
            'structural_integrity': StructuralIntegrityEvidence,
            'tenant_isolation': TenantIsolationEvidence,
            'temporal': TemporalEvidence,
            'provenance': ProvenanceEvidence,
            'epistemic': EpistemicEvidence,
            'governance': GovernanceEvidence,
            'company_brain': CompanyBrainEvidence,
            'performance': PerformanceEvidence,
            'resources': ResourceEvidence,
            'recovery': RecoveryEvidence,
            'promotion': PromotionEvidence,
            'concurrency': ConcurrencyEvidence,
        }
        
        for field in base_evidence_fields:
            if field in data and data[field] is not None:
                if isinstance(data[field], dict):
                    data[field] = base_evidence_classes[field](**data[field])
        
        # Reconstruct universal acceptance evidence domain objects
        universal_evidence_fields = [
            'universality', 'scale_matrix', 'org_structure', 'industry',
            'geography', 'multi_company', 'identity', 'work',
            'governance_universal', 'integration', 'company_brain_universal',
            'memory_universal', 'prediction', 'counterfactual', 'autonomy',
            'continuity', 'migration', 'ma', 'failure_universality',
            'longitudinal_universality', 'deployment_dr', 'security', 'api',
        ]
        
        universal_evidence_classes = {
            'universality': UniversalityEvidence,
            'scale_matrix': ScaleMatrixEvidence,
            'org_structure': OrgStructureEvidence,
            'industry': IndustryEvidence,
            'geography': GeographyEvidence,
            'multi_company': MultiCompanyEvidence,
            'identity': IdentityEvidence,
            'work': WorkEvidence,
            'governance_universal': GovernanceEvidence,
            'integration': IntegrationEvidence,
            'company_brain_universal': CompanyBrainEvidence,
            'memory_universal': MemoryEvidence,
            'prediction': PredictionEvidence,
            'counterfactual': CounterfactualEvidence,
            'autonomy': AutonomyEvidence,
            'continuity': ContinuityEvidence,
            'migration': MigrationEvidence,
            'ma': MAEvidence,
            'failure_universality': FailureUniversalityEvidence,
            'longitudinal_universality': LongitudinalUniversalityEvidence,
            'deployment_dr': DeploymentDREvidence,
            'security': SecurityEvidence,
            'api': APIEvidence,
        }
        
        for field in universal_evidence_fields:
            if field in data and data[field] is not None:
                if isinstance(data[field], dict):
                    data[field] = universal_evidence_classes[field](**data[field])
        
        return cls(**data)


def create_universal_acceptance_evidence(
    run_id: str,
    scale_profile: str,
    employee_count: int,
    tenant_count: int,
    seed: int,
    dataset_identity: Dict[str, Any],
    environment_fingerprint: Dict[str, Any],
    schema_revision: str,
    vcos_revision: str,
    generator_revision: str,
    matrix_run_id: str,
) -> UniversalAcceptanceEvidence:
    """Factory function to create initialized UniversalAcceptanceEvidence."""
    base = create_acceptance_evidence(
        run_id=run_id,
        scale_profile=scale_profile,
        employee_count=employee_count,
        tenant_count=tenant_count,
        seed=seed,
        dataset_identity=dataset_identity,
        environment_fingerprint=environment_fingerprint,
        schema_revision=schema_revision,
        vcos_revision=vcos_revision,
        generator_revision=generator_revision,
    )
    
    return UniversalAcceptanceEvidence(
        run_id=base.run_id,
        evidence_schema_version=base.evidence_schema_version,
        scale_profile=base.scale_profile,
        employee_count=base.employee_count,
        tenant_count=base.tenant_count,
        seed=base.seed,
        dataset_identity=base.dataset_identity,
        environment_fingerprint=base.environment_fingerprint,
        schema_revision=base.schema_revision,
        vcos_revision=base.vcos_revision,
        generator_revision=base.generator_revision,
        started_at=base.started_at,
        matrix_run_id=matrix_run_id,
    )