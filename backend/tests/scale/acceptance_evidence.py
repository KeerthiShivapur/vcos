"""Scale Acceptance Evidence.

Structured, reproducible evidence artifact for authoritative scale validation runs.
This is a TEST INFRASTRUCTURE projection - NOT a business/domain model.
"""

import json
import hashlib
import uuid
from dataclasses import dataclass, field, asdict
from typing import Dict, Any, List, Optional
from datetime import datetime
from enum import Enum
from pathlib import Path


class AcceptanceResult(Enum):
    """Authoritative acceptance result states."""
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"
    INCONCLUSIVE = "INCONCLUSIVE"


class EvidenceSchemaVersion(Enum):
    """Evidence schema versions for backward compatibility."""
    V1 = "1.0"


@dataclass
class EnvironmentEvidence:
    """PostgreSQL environment evidence."""
    postgresql_version: str
    environment_type: str
    endpoint_identifier: str
    extensions: List[Dict[str, str]]
    configuration_fingerprint: str
    cpu_count: Optional[int] = None
    memory_bytes: Optional[str] = None
    storage_type: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GenerationEvidence:
    """Data generation evidence."""
    entities_generated: Dict[str, int]
    total_rows: int
    generation_duration_seconds: float
    throughput_rows_per_second: float
    checkpoint_completion: Dict[str, bool]
    retry_count: int
    interrupted: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class StructuralIntegrityEvidence:
    """Structural integrity validation evidence."""
    fk_validation_passed: bool
    required_fields_passed: bool
    enum_validity_passed: bool
    duplicate_fingerprints: int
    organization_ownership_passed: bool
    failed_entities: List[str] = field(default_factory=list)
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return (
            self.fk_validation_passed and
            self.required_fields_passed and
            self.enum_validity_passed and
            self.duplicate_fingerprints == 0 and
            self.organization_ownership_passed
        )


@dataclass
class TenantIsolationEvidence:
    """Tenant isolation validation evidence."""
    read_isolation_passed: bool
    write_isolation_passed: bool
    entities_tested: int
    cross_tenant_attempts: int
    blocked_attempts: int
    successful_unauthorized_attempts: int
    details: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return (
            self.read_isolation_passed and
            self.write_isolation_passed and
            self.successful_unauthorized_attempts == 0
        )


@dataclass
class TemporalEvidence:
    """Temporal integrity validation evidence."""
    recorded_at_coherent: bool
    observed_at_coherent: bool
    effective_from_coherent: bool
    effective_to_coherent: bool
    supersession_valid: bool
    ordering_coherent: bool
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.recorded_at_coherent,
            self.observed_at_coherent,
            self.effective_from_coherent,
            self.effective_to_coherent,
            self.supersession_valid,
            self.ordering_coherent,
        ])


@dataclass
class ProvenanceEvidence:
    """Provenance validation evidence."""
    external_sources_tracked: bool
    source_identities_preserved: bool
    source_timestamps_preserved: bool
    provenance_relationships_intact: bool
    external_boundaries_respected: bool
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.external_sources_tracked,
            self.source_identities_preserved,
            self.source_timestamps_preserved,
            self.provenance_relationships_intact,
            self.external_boundaries_respected,
        ])


@dataclass
class EpistemicEvidence:
    """Epistemic integrity validation evidence."""
    confirmed_preserved: bool
    supported_preserved: bool
    historical_preserved: bool
    corrected_preserved: bool
    conflicting_preserved: bool
    predicted_preserved: bool
    expected_preserved: bool
    unknown_preserved: bool
    not_collapsed_to_confidence: bool
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.confirmed_preserved,
            self.supported_preserved,
            self.historical_preserved,
            self.corrected_preserved,
            self.conflicting_preserved,
            self.predicted_preserved,
            self.expected_preserved,
            self.unknown_preserved,
            self.not_collapsed_to_confidence,
        ])


@dataclass
class GovernanceEvidence:
    """Governance validation evidence."""
    canonical_authorization_used: bool
    no_scale_specific_auth: bool
    access_control_validated: bool
    permission_resolution_validated: bool
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.canonical_authorization_used,
            self.no_scale_specific_auth,
            self.access_control_validated,
            self.permission_resolution_validated,
        ])


@dataclass
class CompanyBrainEvidence:
    """Company Brain projection validation evidence."""
    canonical_reality_intact: bool
    context_retrieval_works: bool
    projection_over_reality: bool
    query_intelligence_works: bool
    tenant_scope_respected: bool
    governance_respected: bool
    not_separate_intelligence_system: bool
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.canonical_reality_intact,
            self.context_retrieval_works,
            self.projection_over_reality,
            self.query_intelligence_works,
            self.tenant_scope_respected,
            self.governance_respected,
            self.not_separate_intelligence_system,
        ])


@dataclass
class PerformanceEvidence:
    """Performance measurement evidence."""
    generation_duration_seconds: float
    database_size_mb: float
    index_size_mb: float
    throughput_rows_per_second: float
    query_latency_p50_ms: Optional[float] = None
    query_latency_p95_ms: Optional[float] = None
    query_latency_p99_ms: Optional[float] = None
    fts_latency_ms: Optional[float] = None
    cursor_pagination_latency_ms: Optional[float] = None
    company_brain_context_latency_ms: Optional[float] = None
    integrity_validation_duration_seconds: float = 0.0
    cleanup_duration_seconds: float = 0.0
    unavailable_measurements: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ResourceEvidence:
    """Resource safety evidence."""
    connections_used: int
    peak_connections: int
    memory_mb: Optional[float] = None
    wal_mb: Optional[float] = None
    cleanup_completed: bool = False
    resource_leaks: List[str] = field(default_factory=list)
    connection_leaks: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return self.cleanup_completed and len(self.resource_leaks) == 0 and self.connection_leaks == 0


@dataclass
class RecoveryEvidence:
    """Recovery and retry evidence."""
    interruption_state: Optional[str] = None
    retry_count: int = 0
    checkpoint_state_preserved: bool = False
    duplicate_prevention_verified: bool = False
    safe_cleanup_performed: bool = False
    cleanup_required: bool = False
    # Semantic state: NOT_REQUIRED | PASS | FAIL | UNKNOWN
    recovery_state: str = "NOT_REQUIRED"
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        """Recovery passes if NOT_REQUIRED (no recovery needed) or PASS."""
        return self.recovery_state in ("NOT_REQUIRED", "PASS")


@dataclass
class PromotionEvidence:
    """Promotion gate evidence."""
    required_checks_passed: List[str] = field(default_factory=list)
    blocked_checks_failed: List[str] = field(default_factory=list)
    promotion_allowed: bool = False
    next_target: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        """Promotion passes if allowed (no blocking issues)."""
        return self.promotion_allowed


@dataclass
class ConcurrencyEvidence:
    """35-G Canonical Concurrency validation evidence."""
    atomic_create_verified: bool = False
    concurrent_create_10_passed: bool = False
    concurrent_create_100_passed: bool = False
    atomic_update_verified: bool = False
    concurrent_update_10_passed: bool = False
    concurrent_update_100_passed: bool = False
    worker_lease_contention_verified: bool = False
    lease_expiry_verified: bool = False
    advisory_lock_contention_verified: bool = False
    worker_crash_unknown_preserved: bool = False
    gate32_recovery_verified: bool = False
    authorization_race_verified: bool = False
    tenant_isolation_under_concurrency: bool = False
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    def all_passed(self) -> bool:
        return all([
            self.atomic_create_verified,
            self.concurrent_create_10_passed,
            self.concurrent_create_100_passed,
            self.atomic_update_verified,
            self.concurrent_update_10_passed,
            self.worker_lease_contention_verified,
            self.lease_expiry_verified,
            self.advisory_lock_contention_verified,
            self.worker_crash_unknown_preserved,
            self.gate32_recovery_verified,
            self.authorization_race_verified,
            self.tenant_isolation_under_concurrency,
        ])


@dataclass
class ScaleAcceptanceEvidence:
    """Complete scale acceptance evidence artifact.
    
    This is a TEST INFRASTRUCTURE projection over the canonical VCOS system.
    It is NOT a business/domain model and must not become another source of truth.
    """
    
    # Run identification
    run_id: str
    evidence_schema_version: str = "1.0"
    
    # Scale configuration
    scale_profile: str = ""
    employee_count: int = 0
    tenant_count: int = 0
    seed: int = 42
    
    # Identity
    dataset_identity: Dict[str, Any] = field(default_factory=dict)
    environment_fingerprint: Dict[str, Any] = field(default_factory=dict)
    schema_revision: str = "unknown"
    vcos_revision: str = "unknown"
    generator_revision: str = "unknown"
    
    # Evidence domains
    environment: Optional[EnvironmentEvidence] = None
    generation: Optional[GenerationEvidence] = None
    structural_integrity: Optional[StructuralIntegrityEvidence] = None
    tenant_isolation: Optional[TenantIsolationEvidence] = None
    temporal: Optional[TemporalEvidence] = None
    provenance: Optional[ProvenanceEvidence] = None
    epistemic: Optional[EpistemicEvidence] = None
    governance: Optional[GovernanceEvidence] = None
    company_brain: Optional[CompanyBrainEvidence] = None
    performance: Optional[PerformanceEvidence] = None
    resources: Optional[ResourceEvidence] = None
    recovery: Optional[RecoveryEvidence] = None
    promotion: Optional[PromotionEvidence] = None
    concurrency: Optional[ConcurrencyEvidence] = None
    
    # Final determination
    acceptance_result: Optional[AcceptanceResult] = None
    acceptance_reason: str = ""
    mandatory_checks: Dict[str, bool] = field(default_factory=dict)
    
    # Timestamps
    started_at: str = ""
    completed_at: Optional[str] = None
    duration_seconds: float = 0.0
    
    def __post_init__(self):
        if not self.run_id:
            self.run_id = str(uuid.uuid4())[:12]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary, excluding secrets."""
        data = {}
        for key, value in asdict(self).items():
            if value is not None:
                if hasattr(value, 'to_dict'):
                    data[key] = value.to_dict()
                elif isinstance(value, Enum):
                    data[key] = value.value
                elif isinstance(value, dict):
                    data[key] = {k: v.to_dict() if hasattr(v, 'to_dict') else v 
                                for k, v in value.items()}
                else:
                    data[key] = value
        return data
    
    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)
    
    def determine_acceptance(self) -> AcceptanceResult:
        """Determine acceptance result from mandatory checks."""
        if not self.mandatory_checks:
            return AcceptanceResult.INCONCLUSIVE
        
        # If any mandatory check failed -> FAIL
        if any(not v for v in self.mandatory_checks.values()):
            return AcceptanceResult.FAIL
        
        # If BLOCKED checks exist -> BLOCKED
        # (This would be determined by environment evidence)
        
        # All mandatory checks passed -> PASS
        return AcceptanceResult.PASS
    
    def set_mandatory_check(self, check_name: str, passed: bool) -> None:
        """Set a mandatory check result."""
        self.mandatory_checks[check_name] = passed
    
    def get_fingerprint(self) -> str:
        """Generate deterministic fingerprint for this evidence."""
        # Create a stable representation excluding timestamps and result
        fingerprint_data = {
            "run_id": self.run_id,
            "scale_profile": self.scale_profile,
            "employee_count": self.employee_count,
            "tenant_count": self.tenant_count,
            "seed": self.seed,
            "dataset_identity": self.dataset_identity,
            "schema_revision": self.schema_revision,
            "vcos_revision": self.vcos_revision,
            "generator_revision": self.generator_revision,
            "evidence_schema_version": self.evidence_schema_version,
        }
        content = json.dumps(fingerprint_data, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    @classmethod
    def from_json(cls, json_str: str) -> 'ScaleAcceptanceEvidence':
        """Deserialize from JSON."""
        data = json.loads(json_str)
        
        # Convert enums back
        if 'acceptance_result' in data and data['acceptance_result']:
            data['acceptance_result'] = AcceptanceResult(data['acceptance_result'])
        
        # Reconstruct evidence domain objects
        evidence_fields = [
            'environment', 'generation', 'structural_integrity', 
            'tenant_isolation', 'temporal', 'provenance', 'epistemic',
            'governance', 'company_brain', 'performance', 'resources',
            'recovery', 'promotion', 'concurrency'
        ]
        
        evidence_classes = {
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
        
        for field in evidence_fields:
            if field in data and data[field] is not None:
                if isinstance(data[field], dict):
                    data[field] = evidence_classes[field](**data[field])
        
        return cls(**data)
    
    def save(self, output_dir: str = "scale_evidence") -> Path:
        """Save evidence artifact to file."""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        filename = f"scale_evidence_{self.scale_profile}_{self.run_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
        filepath = output_path / filename
        
        with open(filepath, 'w') as f:
            f.write(self.to_json())
        
        return filepath


def create_acceptance_evidence(
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
) -> ScaleAcceptanceEvidence:
    """Factory function to create initialized ScaleAcceptanceEvidence."""
    return ScaleAcceptanceEvidence(
        run_id=run_id,
        evidence_schema_version=EvidenceSchemaVersion.V1.value,
        scale_profile=scale_profile,
        employee_count=employee_count,
        tenant_count=tenant_count,
        seed=seed,
        dataset_identity=dataset_identity,
        environment_fingerprint=environment_fingerprint,
        schema_revision=schema_revision,
        vcos_revision=vcos_revision,
        generator_revision=generator_revision,
        started_at=datetime.utcnow().isoformat(),
    )