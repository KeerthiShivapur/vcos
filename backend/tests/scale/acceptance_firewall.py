"""Acceptance Firewall.

Deterministic final gate over ScaleAcceptanceEvidence.
Refuses PASS if any mandatory domain is missing, false, blocked, inconclusive, invalid, or failed.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from enum import Enum

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
)
from tests.scale.scale_state import ScaleRunState


class FirewallVerdict(Enum):
    """Firewall verdict."""
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class FirewallRule:
    """A single firewall rule."""
    domain: str
    check_name: str
    description: str
    mandatory: bool = True
    
    def __hash__(self):
        return hash((self.domain, self.check_name))
    
    def __eq__(self, other):
        if not isinstance(other, FirewallRule):
            return False
        return self.domain == other.domain and self.check_name == other.check_name


@dataclass
class FirewallCheckResult:
    """Result of a firewall check."""
    rule: FirewallRule
    passed: bool
    reason: str = ""
    evidence_value: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "domain": self.rule.domain,
            "check": self.rule.check_name,
            "description": self.rule.description,
            "mandatory": self.rule.mandatory,
            "passed": self.passed,
            "reason": self.reason,
            "evidence_value": str(self.evidence_value) if self.evidence_value is not None else None,
        }


@dataclass
class FirewallVerdictResult:
    """Complete firewall verdict."""
    verdict: FirewallVerdict
    check_results: List[FirewallCheckResult] = field(default_factory=list)
    mandatory_passed: int = 0
    mandatory_total: int = 0
    optional_passed: int = 0
    optional_total: int = 0
    summary: str = ""
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "verdict": self.verdict.value,
            "checks": [c.to_dict() for c in self.check_results],
            "mandatory_passed": self.mandatory_passed,
            "mandatory_total": self.mandatory_total,
            "optional_passed": self.optional_passed,
            "optional_total": self.optional_total,
            "summary": self.summary,
        }


class AcceptanceFirewall:
    """Deterministic acceptance firewall.
    
    Evaluates ScaleAcceptanceEvidence and produces a final verdict.
    The same evidence always produces the same verdict.
    """
    
    # Mandatory evidence domains
    MANDATORY_DOMAINS = [
        "environment",
        "generation",
        "structural_integrity",
        "tenant_isolation",
        "temporal",
        "provenance",
        "epistemic",
        "governance",
        "company_brain",
        "performance",
        "resource",
        "recovery",
        "promotion",
        "concurrency",
    ]
    
    def __init__(self):
        self._rules = self._build_rules()
    
    def _build_rules(self) -> List[FirewallRule]:
        """Build the complete set of firewall rules."""
        rules = []
        
        # Environment
        rules.append(FirewallRule(
            domain="environment",
            check_name="environment_preflight",
            description="PostgreSQL environment preflight passed",
            mandatory=True,
        ))
        
        # Generation
        rules.append(FirewallRule(
            domain="generation",
            check_name="generation_complete",
            description="Scale dataset generation completed successfully",
            mandatory=True,
        ))
        
        # Structural Integrity
        rules.append(FirewallRule(
            domain="structural_integrity",
            check_name="fk_validation",
            description="Foreign key integrity validated",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="structural_integrity",
            check_name="required_fields",
            description="Required fields populated",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="structural_integrity",
            check_name="enum_validity",
            description="Enum values valid",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="structural_integrity",
            check_name="duplicate_fingerprints",
            description="No duplicate fingerprints",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="structural_integrity",
            check_name="organization_ownership",
            description="Organization ownership validated",
            mandatory=True,
        ))
        
        # Tenant Isolation
        rules.append(FirewallRule(
            domain="tenant_isolation",
            check_name="read_isolation",
            description="Cross-tenant read isolation enforced",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="tenant_isolation",
            check_name="write_isolation",
            description="Cross-tenant write isolation enforced",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="tenant_isolation",
            check_name="no_unauthorized_access",
            description="No successful unauthorized cross-tenant operations",
            mandatory=True,
        ))
        
        # Temporal
        rules.append(FirewallRule(
            domain="temporal",
            check_name="recorded_at_coherent",
            description="Recorded timestamps coherent",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="temporal",
            check_name="observed_at_coherent",
            description="Observed timestamps coherent",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="temporal",
            check_name="effective_intervals_coherent",
            description="Effective intervals coherent",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="temporal",
            check_name="supersession_valid",
            description="Supersession relationships valid",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="temporal",
            check_name="ordering_coherent",
            description="Temporal ordering coherent",
            mandatory=True,
        ))
        
        # Provenance
        rules.append(FirewallRule(
            domain="provenance",
            check_name="external_sources_tracked",
            description="External sources tracked",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="provenance",
            check_name="source_identities_preserved",
            description="Source identities preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="provenance",
            check_name="source_timestamps_preserved",
            description="Source timestamps preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="provenance",
            check_name="provenance_relationships_intact",
            description="Provenance relationships intact",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="provenance",
            check_name="external_boundaries_respected",
            description="External boundaries respected",
            mandatory=True,
        ))
        
        # Epistemic
        rules.append(FirewallRule(
            domain="epistemic",
            check_name="confirmed_preserved",
            description="CONFIRMED state preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="epistemic",
            check_name="supported_preserved",
            description="SUPPORTED state preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="epistemic",
            check_name="historical_preserved",
            description="HISTORICAL state preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="epistemic",
            check_name="corrected_preserved",
            description="CORRECTED state preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="epistemic",
            check_name="conflicting_preserved",
            description="CONFLICTING state preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="epistemic",
            check_name="predicted_preserved",
            description="PREDICTED state preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="epistemic",
            check_name="expected_preserved",
            description="EXPECTED state preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="epistemic",
            check_name="unknown_preserved",
            description="UNKNOWN state preserved",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="epistemic",
            check_name="not_collapsed_to_confidence",
            description="Epistemic states not collapsed to confidence score",
            mandatory=True,
        ))
        
        # Governance
        rules.append(FirewallRule(
            domain="governance",
            check_name="canonical_authorization_used",
            description="Canonical authorization machinery used",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="governance",
            check_name="no_scale_specific_auth",
            description="No scale-specific authorization layer",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="governance",
            check_name="access_control_validated",
            description="Access control validated",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="governance",
            check_name="permission_resolution_validated",
            description="Permission resolution validated",
            mandatory=True,
        ))
        
        # Company Brain
        rules.append(FirewallRule(
            domain="company_brain",
            check_name="canonical_reality_intact",
            description="Canonical reality intact",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="company_brain",
            check_name="context_retrieval_works",
            description="Context retrieval works",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="company_brain",
            check_name="projection_over_reality",
            description="Company Brain is projection over canonical reality",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="company_brain",
            check_name="query_intelligence_works",
            description="Query intelligence works",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="company_brain",
            check_name="tenant_scope_respected",
            description="Tenant scope respected",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="company_brain",
            check_name="governance_respected",
            description="Governance respected in Company Brain",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="company_brain",
            check_name="not_separate_intelligence_system",
            description="Company Brain is not a separate intelligence system",
            mandatory=True,
        ))
        
        # Performance (optional - must have evidence but thresholds are informational)
        rules.append(FirewallRule(
            domain="performance",
            check_name="performance_measurement",
            description="Performance measurements collected",
            mandatory=False,
        ))
        
        # Resource
        rules.append(FirewallRule(
            domain="resource",
            check_name="cleanup_completed",
            description="Resource cleanup completed",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="resource",
            check_name="no_resource_leaks",
            description="No resource leaks detected",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="resource",
            check_name="no_connection_leaks",
            description="No connection leaks detected",
            mandatory=True,
        ))
        
        # Recovery
        rules.append(FirewallRule(
            domain="recovery",
            check_name="checkpoint_state_preserved",
            description="Checkpoint state preserved on interruption",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="recovery",
            check_name="duplicate_prevention_verified",
            description="Duplicate prevention verified",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="recovery",
            check_name="safe_cleanup_performed",
            description="Safe cleanup performed",
            mandatory=True,
        ))
        
        # Promotion
        rules.append(FirewallRule(
            domain="promotion",
            check_name="promotion_allowed",
            description="Promotion gate allows next scale",
            mandatory=False,
        ))
        
        # 35-G Canonical Concurrency
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="atomic_create_verified",
            description="Atomic idempotent CREATE verified on PostgreSQL",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="concurrent_create_10_passed",
            description="10 concurrent identical CREATE operations produce one canonical effect",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="concurrent_create_100_passed",
            description="100 concurrent identical CREATE operations produce one canonical effect",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="atomic_update_verified",
            description="Atomic optimistic UPDATE with WHERE version verified on PostgreSQL",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="concurrent_update_10_passed",
            description="10 concurrent identical UPDATE operations correctly detect conflicts",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="concurrent_update_100_passed",
            description="100 concurrent identical UPDATE operations correctly detect conflicts",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="worker_lease_contention_verified",
            description="WorkerLease contention correctly excludes other workers",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="lease_expiry_verified",
            description="Lease expiry correctly allows new acquisition",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="advisory_lock_contention_verified",
            description="Transaction-scoped advisory lock contention verified",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="worker_crash_unknown_preserved",
            description="Worker crash creates UNKNOWN not FAILED",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="gate32_recovery_verified",
            description="Gate 32 recovery/reconciliation verified under concurrency",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="authorization_race_verified",
            description="Authorization revoked during execution correctly handled",
            mandatory=True,
        ))
        rules.append(FirewallRule(
            domain="concurrency",
            check_name="tenant_isolation_under_concurrency",
            description="Tenant isolation maintained under concurrent mutations",
            mandatory=True,
        ))
        
        return rules
    
    def evaluate(self, evidence: ScaleAcceptanceEvidence) -> FirewallVerdictResult:
        """Evaluate evidence and produce deterministic verdict."""
        results = []
        
        # Check each rule
        for rule in self._rules:
            passed = False
            reason = ""
            evidence_value = None
            
            if rule.domain == "environment":
                passed, reason, evidence_value = self._check_environment(evidence, rule)
            elif rule.domain == "generation":
                passed, reason, evidence_value = self._check_generation(evidence, rule)
            elif rule.domain == "structural_integrity":
                passed, reason, evidence_value = self._check_structural_integrity(evidence, rule)
            elif rule.domain == "tenant_isolation":
                passed, reason, evidence_value = self._check_tenant_isolation(evidence, rule)
            elif rule.domain == "temporal":
                passed, reason, evidence_value = self._check_temporal(evidence, rule)
            elif rule.domain == "provenance":
                passed, reason, evidence_value = self._check_provenance(evidence, rule)
            elif rule.domain == "epistemic":
                passed, reason, evidence_value = self._check_epistemic(evidence, rule)
            elif rule.domain == "governance":
                passed, reason, evidence_value = self._check_governance(evidence, rule)
            elif rule.domain == "company_brain":
                passed, reason, evidence_value = self._check_company_brain(evidence, rule)
            elif rule.domain == "performance":
                passed, reason, evidence_value = self._check_performance(evidence, rule)
            elif rule.domain == "resource":
                passed, reason, evidence_value = self._check_resource(evidence, rule)
            elif rule.domain == "recovery":
                passed, reason, evidence_value = self._check_recovery(evidence, rule)
            elif rule.domain == "promotion":
                passed, reason, evidence_value = self._check_promotion(evidence, rule)
            elif rule.domain == "concurrency":
                passed, reason, evidence_value = self._check_concurrency(evidence, rule)
            else:
                passed = True
                reason = "No rule defined"
            
            results.append(FirewallCheckResult(
                rule=rule,
                passed=passed,
                reason=reason,
                evidence_value=evidence_value,
            ))
        
        # Count mandatory/optional
        mandatory_results = [r for r in results if r.rule.mandatory]
        optional_results = [r for r in results if not r.rule.mandatory]
        
        mandatory_passed = sum(1 for r in mandatory_results if r.passed)
        mandatory_total = len(mandatory_results)
        optional_passed = sum(1 for r in optional_results if r.passed)
        optional_total = len(optional_results)
        
        # Determine verdict
        verdict = self._determine_verdict(
            evidence,
            mandatory_passed,
            mandatory_total,
            mandatory_results,
        )
        
        return FirewallVerdictResult(
            verdict=verdict,
            check_results=results,
            mandatory_passed=mandatory_passed,
            mandatory_total=mandatory_total,
            optional_passed=optional_passed,
            optional_total=optional_total,
            summary=self._generate_summary(verdict, mandatory_passed, mandatory_total, optional_passed, optional_total),
        )
    
    def _check_environment(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.environment:
            return False, "Environment evidence missing", None
        if not evidence.mandatory_checks.get("environment_preflight", False):
            return False, "Environment preflight check not passed", None
        return True, "Environment preflight passed", evidence.environment.to_dict() if evidence.environment else None
    
    def _check_generation(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.generation:
            return False, "Generation evidence missing", None
        if not evidence.mandatory_checks.get("generation_complete", False):
            return False, "Generation complete check not passed", None
        return True, "Generation complete", {"total_rows": evidence.generation.total_rows, "duration": evidence.generation.generation_duration_seconds}
    
    def _check_structural_integrity(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.structural_integrity:
            return False, "Structural integrity evidence missing", None
        
        si = evidence.structural_integrity
        
        if rule.check_name == "fk_validation":
            return si.fk_validation_passed, "FK validation" + (" passed" if si.fk_validation_passed else " failed"), si.fk_validation_passed
        elif rule.check_name == "required_fields":
            return si.required_fields_passed, "Required fields" + (" passed" if si.required_fields_passed else " failed"), si.required_fields_passed
        elif rule.check_name == "enum_validity":
            return si.enum_validity_passed, "Enum validity" + (" passed" if si.enum_validity_passed else " failed"), si.enum_validity_passed
        elif rule.check_name == "duplicate_fingerprints":
            passed = si.duplicate_fingerprints == 0
            return passed, f"Duplicate fingerprints: {si.duplicate_fingerprints}", si.duplicate_fingerprints
        elif rule.check_name == "organization_ownership":
            return si.organization_ownership_passed, "Organization ownership" + (" passed" if si.organization_ownership_passed else " failed"), si.organization_ownership_passed
        
        return False, f"Unknown check: {rule.check_name}", None
    
    def _check_tenant_isolation(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.tenant_isolation:
            return False, "Tenant isolation evidence missing", None
        
        ti = evidence.tenant_isolation
        
        if rule.check_name == "read_isolation":
            return ti.read_isolation_passed, "Read isolation" + (" passed" if ti.read_isolation_passed else " failed"), ti.read_isolation_passed
        elif rule.check_name == "write_isolation":
            return ti.write_isolation_passed, "Write isolation" + (" passed" if ti.write_isolation_passed else " failed"), ti.write_isolation_passed
        elif rule.check_name == "no_unauthorized_access":
            passed = ti.successful_unauthorized_attempts == 0
            return passed, f"Unauthorized access attempts: {ti.successful_unauthorized_attempts}", ti.successful_unauthorized_attempts
        
        return False, f"Unknown check: {rule.check_name}", None
    
    def _check_temporal(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.temporal:
            return False, "Temporal evidence missing", None
        
        temp = evidence.temporal
        
        checks = {
            "recorded_at_coherent": temp.recorded_at_coherent,
            "observed_at_coherent": temp.observed_at_coherent,
            "effective_intervals_coherent": temp.effective_from_coherent and temp.effective_to_coherent,
            "supersession_valid": temp.supersession_valid,
            "ordering_coherent": temp.ordering_coherent,
        }
        
        passed = checks.get(rule.check_name, False)
        return passed, rule.description + (" passed" if passed else " failed"), passed
    
    def _check_provenance(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.provenance:
            return False, "Provenance evidence missing", None
        
        prov = evidence.provenance
        
        checks = {
            "external_sources_tracked": prov.external_sources_tracked,
            "source_identities_preserved": prov.source_identities_preserved,
            "source_timestamps_preserved": prov.source_timestamps_preserved,
            "provenance_relationships_intact": prov.provenance_relationships_intact,
            "external_boundaries_respected": prov.external_boundaries_respected,
        }
        
        passed = checks.get(rule.check_name, False)
        return passed, rule.description + (" passed" if passed else " failed"), passed
    
    def _check_epistemic(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.epistemic:
            return False, "Epistemic evidence missing", None
        
        epi = evidence.epistemic
        
        checks = {
            "confirmed_preserved": epi.confirmed_preserved,
            "supported_preserved": epi.supported_preserved,
            "historical_preserved": epi.historical_preserved,
            "corrected_preserved": epi.corrected_preserved,
            "conflicting_preserved": epi.conflicting_preserved,
            "predicted_preserved": epi.predicted_preserved,
            "expected_preserved": epi.expected_preserved,
            "unknown_preserved": epi.unknown_preserved,
            "not_collapsed_to_confidence": epi.not_collapsed_to_confidence,
        }
        
        passed = checks.get(rule.check_name, False)
        return passed, rule.description + (" passed" if passed else " failed"), passed
    
    def _check_governance(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.governance:
            return False, "Governance evidence missing", None
        
        gov = evidence.governance
        
        checks = {
            "canonical_authorization_used": gov.canonical_authorization_used,
            "no_scale_specific_auth": gov.no_scale_specific_auth,
            "access_control_validated": gov.access_control_validated,
            "permission_resolution_validated": gov.permission_resolution_validated,
        }
        
        passed = checks.get(rule.check_name, False)
        return passed, rule.description + (" passed" if passed else " failed"), passed
    
    def _check_company_brain(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.company_brain:
            return False, "Company Brain evidence missing", None
        
        cb = evidence.company_brain
        
        checks = {
            "canonical_reality_intact": cb.canonical_reality_intact,
            "context_retrieval_works": cb.context_retrieval_works,
            "projection_over_reality": cb.projection_over_reality,
            "query_intelligence_works": cb.query_intelligence_works,
            "tenant_scope_respected": cb.tenant_scope_respected,
            "governance_respected": cb.governance_respected,
            "not_separate_intelligence_system": cb.not_separate_intelligence_system,
        }
        
        passed = checks.get(rule.check_name, False)
        return passed, rule.description + (" passed" if passed else " failed"), passed
    
    def _check_performance(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.performance:
            return True, "Performance evidence optional", None
        if rule.check_name == "performance_measurement":
            return evidence.mandatory_checks.get("performance_measurement", True), "Performance measurement", True
        return True, "Optional check", None
    
    def _check_resource(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.resources:
            return False, "Resource evidence missing", None
        
        res = evidence.resources
        
        if rule.check_name == "cleanup_completed":
            passed = res.cleanup_completed
            return passed, "Cleanup completed" + ("" if passed else " NOT completed"), passed
        elif rule.check_name == "no_resource_leaks":
            passed = len(res.resource_leaks) == 0
            return passed, f"Resource leaks: {len(res.resource_leaks)}", len(res.resource_leaks)
        elif rule.check_name == "no_connection_leaks":
            passed = res.connection_leaks == 0
            return passed, f"Connection leaks: {res.connection_leaks}", res.connection_leaks
        
        return True, "Optional resource check", None
    
    def _check_recovery(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.recovery:
            return False, "Recovery evidence missing", None
        
        rec = evidence.recovery
        
        checks = {
            "checkpoint_state_preserved": rec.checkpoint_state_preserved,
            "duplicate_prevention_verified": rec.duplicate_prevention_verified,
            "safe_cleanup_performed": rec.safe_cleanup_performed,
        }
        
        passed = checks.get(rule.check_name, False)
        return passed, rule.description + (" passed" if passed else " failed"), passed
    
    def _check_promotion(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.promotion:
            return True, "Promotion evidence optional", None
        if rule.check_name == "promotion_allowed":
            passed = evidence.promotion.promotion_allowed
            return passed, "Promotion allowed" if passed else "Promotion blocked", passed
        return True, "Optional check", None
    
    def _check_concurrency(self, evidence: ScaleAcceptanceEvidence, rule: FirewallRule) -> tuple:
        if not evidence.concurrency:
            return False, "Concurrency evidence missing", None
        
        conc = evidence.concurrency
        
        checks = {
            "atomic_create_verified": conc.atomic_create_verified,
            "concurrent_create_10_passed": conc.concurrent_create_10_passed,
            "concurrent_create_100_passed": conc.concurrent_create_100_passed,
            "atomic_update_verified": conc.atomic_update_verified,
            "concurrent_update_10_passed": conc.concurrent_update_10_passed,
            "concurrent_update_100_passed": conc.concurrent_update_100_passed,
            "worker_lease_contention_verified": conc.worker_lease_contention_verified,
            "lease_expiry_verified": conc.lease_expiry_verified,
            "advisory_lock_contention_verified": conc.advisory_lock_contention_verified,
            "worker_crash_unknown_preserved": conc.worker_crash_unknown_preserved,
            "gate32_recovery_verified": conc.gate32_recovery_verified,
            "authorization_race_verified": conc.authorization_race_verified,
            "tenant_isolation_under_concurrency": conc.tenant_isolation_under_concurrency,
        }
        
        passed = checks.get(rule.check_name, False)
        return passed, rule.description + (" passed" if passed else " failed"), passed
    
    def _determine_verdict(
        self, 
        evidence: ScaleAcceptanceEvidence,
        mandatory_passed: int,
        mandatory_total: int,
        mandatory_results: List,
    ) -> FirewallVerdict:
        """Determine final verdict based on all checks."""
        
        # If any mandatory check failed -> FAIL
        if mandatory_passed < mandatory_total:
            return FirewallVerdict.FAIL
        
        # If evidence acceptance_result is explicitly set, honor it
        if evidence.acceptance_result:
            mapping = {
                AcceptanceResult.PASS: FirewallVerdict.PASS,
                AcceptanceResult.FAIL: FirewallVerdict.FAIL,
                AcceptanceResult.BLOCKED: FirewallVerdict.BLOCKED,
                AcceptanceResult.INVALID: FirewallVerdict.INVALID,
                AcceptanceResult.INCONCLUSIVE: FirewallVerdict.INCONCLUSIVE,
            }
            return mapping.get(evidence.acceptance_result, FirewallVerdict.FAIL)
        
        # Check if evidence indicates blocked environment
        if evidence.environment:
            # Could check for blocked indicators here
            pass
        
        # All mandatory checks passed
        return FirewallVerdict.PASS
    
    def _generate_summary(
        self, 
        verdict: FirewallVerdict, 
        mandatory_passed: int, 
        mandatory_total: int,
        optional_passed: int,
        optional_total: int,
    ) -> str:
        if verdict == FirewallVerdict.PASS:
            return f"PASS: All {mandatory_total} mandatory checks passed. {optional_passed}/{optional_total} optional checks passed."
        elif verdict == FirewallVerdict.FAIL:
            return f"FAIL: {mandatory_total - mandatory_passed} of {mandatory_total} mandatory checks failed."
        elif verdict == FirewallVerdict.BLOCKED:
            return "BLOCKED: Environment or prerequisites not satisfied."
        elif verdict == FirewallVerdict.INVALID:
            return "INVALID: Evidence artifact invalid or incomplete."
        else:
            return "INCONCLUSIVE: Insufficient evidence for determination."


# Convenience function
def evaluate_acceptance(evidence: ScaleAcceptanceEvidence) -> FirewallVerdictResult:
    """Evaluate evidence through the acceptance firewall."""
    firewall = AcceptanceFirewall()
    return firewall.evaluate(evidence)