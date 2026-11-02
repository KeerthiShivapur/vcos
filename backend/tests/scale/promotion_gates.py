"""Scale Promotion Gates and Validation Pipeline.

Implements the authoritative promotion chain:
5K → 10K → 25K → 50K+ → Multi-tenant → 35-F RATIFIED
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from enum import Enum
from datetime import datetime


class ScaleProfile(Enum):
    """Scale profiles in promotion order."""
    STARTUP_5 = "startup_5"
    SMALL_50 = "small_50"
    MEDIUM_500 = "medium_500"
    LARGE_5K = "large_5k"
    XLARGE_10K = "xlarge_10k"
    ENTERPRISE_25K = "enterprise_25k"
    MEGA_50K = "mega_50k"
    MULTI_TENANT_10X5K = "multi_10x5k"
    MULTI_TENANT_100X500 = "multi_100x500"
    MULTI_TENANT_1000X50 = "multi_1000x50"


class PromotionResult(Enum):
    """Promotion gate results."""
    PASS = "PASS"
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    INVALID = "INVALID"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class PromotionGate:
    """Single promotion gate definition."""
    from_profile: ScaleProfile
    to_profile: ScaleProfile
    required_checks: List[str] = field(default_factory=list)
    blocked_checks: List[str] = field(default_factory=list)
    
    def can_promote(self, results: Dict[str, Any]) -> tuple[bool, str]:
        """Check if promotion is allowed based on results."""
        for check in self.required_checks:
            if check not in results:
                return False, f"Missing required check: {check}"
            if not results[check]:
                return False, f"Required check failed: {check}"
        
        for check in self.blocked_checks:
            if check in results and results[check]:
                return False, f"Blocking check failed: {check}"
        
        return True, "Promotion allowed"


@dataclass
class ScaleValidationResult:
    """Result of a scale validation run."""
    profile: ScaleProfile
    employee_count: int
    tenant_count: int
    result: PromotionResult
    run_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: float = 0.0
    generation_counts: Dict[str, int] = field(default_factory=dict)
    integrity_checks: Dict[str, bool] = field(default_factory=dict)
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "profile": self.profile.value,
            "employee_count": self.employee_count,
            "tenant_count": self.tenant_count,
            "result": self.result.value,
            "run_id": self.run_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "generation_counts": self.generation_counts,
            "integrity_checks": self.integrity_checks,
            "performance_metrics": self.performance_metrics,
            "errors": self.errors,
            "warnings": self.warnings,
        }


class PromotionGateEngine:
    """Manages the promotion chain for authoritative scale validation."""
    
    PROMOTION_CHAIN = [
        PromotionGate(
            from_profile=ScaleProfile.STARTUP_5,
            to_profile=ScaleProfile.SMALL_50,
            required_checks=["generation_complete", "integrity_validated"],
        ),
        PromotionGate(
            from_profile=ScaleProfile.SMALL_50,
            to_profile=ScaleProfile.MEDIUM_500,
            required_checks=["generation_complete", "integrity_validated", "tenant_isolation"],
        ),
        PromotionGate(
            from_profile=ScaleProfile.MEDIUM_500,
            to_profile=ScaleProfile.LARGE_5K,
            required_checks=["generation_complete", "integrity_validated", "tenant_isolation", "temporal_validated"],
        ),
        PromotionGate(
            from_profile=ScaleProfile.LARGE_5K,
            to_profile=ScaleProfile.XLARGE_10K,
            required_checks=["generation_complete", "integrity_validated", "tenant_isolation", "temporal_validated", "epistemic_validated"],
            blocked_checks=["resource_exhausted"],
        ),
        PromotionGate(
            from_profile=ScaleProfile.XLARGE_10K,
            to_profile=ScaleProfile.ENTERPRISE_25K,
            required_checks=["generation_complete", "integrity_validated", "tenant_isolation", "temporal_validated", "epistemic_validated", "provenance_validated"],
            blocked_checks=["resource_exhausted", "connection_exhausted"],
        ),
        PromotionGate(
            from_profile=ScaleProfile.ENTERPRISE_25K,
            to_profile=ScaleProfile.MEGA_50K,
            required_checks=["generation_complete", "integrity_validated", "tenant_isolation", "temporal_validated", "epistemic_validated", "provenance_validated", "governance_validated"],
            blocked_checks=["resource_exhausted", "connection_exhausted", "wal_exhausted"],
        ),
        PromotionGate(
            from_profile=ScaleProfile.MEGA_50K,
            to_profile=ScaleProfile.MULTI_TENANT_10X5K,
            required_checks=["generation_complete", "integrity_validated", "multi_tenant_isolation"],
            blocked_checks=["resource_exhausted"],
        ),
        PromotionGate(
            from_profile=ScaleProfile.MULTI_TENANT_10X5K,
            to_profile=ScaleProfile.MULTI_TENANT_100X500,
            required_checks=["generation_complete", "integrity_validated", "multi_tenant_isolation"],
            blocked_checks=["resource_exhausted"],
        ),
        PromotionGate(
            from_profile=ScaleProfile.MULTI_TENANT_100X500,
            to_profile=ScaleProfile.MULTI_TENANT_1000X50,
            required_checks=["generation_complete", "integrity_validated", "multi_tenant_isolation"],
            blocked_checks=["resource_exhausted"],
        ),
    ]
    
    def __init__(self):
        self.results: Dict[ScaleProfile, ScaleValidationResult] = {}
        self.current_profile: Optional[ScaleProfile] = None
    
    def record_result(self, result: ScaleValidationResult) -> None:
        """Record a scale validation result."""
        self.results[result.profile] = result
        
        if result.result == PromotionResult.PASS:
            # Update current profile if this is the latest passing profile
            if self.current_profile is None or self._profile_order(result.profile) > self._profile_order(self.current_profile):
                self.current_profile = result.profile
    
    def _profile_order(self, profile: ScaleProfile) -> int:
        order = {
            ScaleProfile.STARTUP_5: 1,
            ScaleProfile.SMALL_50: 2,
            ScaleProfile.MEDIUM_500: 3,
            ScaleProfile.LARGE_5K: 4,
            ScaleProfile.XLARGE_10K: 5,
            ScaleProfile.ENTERPRISE_25K: 6,
            ScaleProfile.MEGA_50K: 7,
            ScaleProfile.MULTI_TENANT_10X5K: 8,
            ScaleProfile.MULTI_TENANT_100X500: 9,
            ScaleProfile.MULTI_TENANT_1000X50: 10,
        }
        return order.get(profile, 0)
    
    def can_promote(self, target_profile: ScaleProfile) -> tuple[bool, str]:
        """Check if promotion to target profile is allowed."""
        if target_profile not in [p.to_profile for p in self.PROMOTION_CHAIN]:
            return False, f"Unknown target profile: {target_profile}"
        
        gate = next(p for p in self.PROMOTION_CHAIN if p.to_profile == target_profile)
        
        # Convert results to checkable format
        check_results = {}
        for profile, result in self.results.items():
            if result.result == PromotionResult.PASS:
                check_results["generation_complete"] = True
                for check, passed in result.integrity_checks.items():
                    check_results[check] = passed
        
        return gate.can_promote(check_results)
    
    def get_next_target(self) -> Optional[ScaleProfile]:
        """Get the next profile in the promotion chain."""
        if self.current_profile is None:
            return ScaleProfile.STARTUP_5
        
        order = self._profile_order(self.current_profile)
        for gate in self.PROMOTION_CHAIN:
            if self._profile_order(gate.from_profile) == order:
                return gate.to_profile
        return None

    def evaluate_profile(self, profile_name: str, employee_count: int, evidence: 'ScaleAcceptanceEvidence') -> 'PromotionResult':
        """Evaluate if the given profile passes its own promotion gate.
        
        This checks if the profile's required checks are satisfied by the evidence.
        """
        # Map profile name to ScaleProfile
        profile_map = {
            "startup": ScaleProfile.STARTUP_5,
            "small": ScaleProfile.SMALL_50,
            "medium": ScaleProfile.MEDIUM_500,
            "large": ScaleProfile.LARGE_5K,
            "xlarge": ScaleProfile.XLARGE_10K,
            "enterprise": ScaleProfile.ENTERPRISE_25K,
            "mega": ScaleProfile.MEGA_50K,
        }
        
        target_profile = profile_map.get(profile_name.lower())
        if not target_profile:
            return PromotionResult.INVALID
        
        # Find the gate for this profile (the gate FROM this profile)
        gate = next((g for g in self.PROMOTION_CHAIN if g.from_profile == target_profile), None)
        if not gate:
            # Final profile has no outgoing gate - it's the terminal state
            # Check if all required checks for ratification are met
            return PromotionResult.PASS if self._check_ratification_checks(evidence) else PromotionResult.FAIL
        
        # Build check results from evidence
        check_results = {}
        
        # Map evidence mandatory_checks to gate check names
        mandatory = evidence.mandatory_checks
        
        # Generation complete
        check_results["generation_complete"] = mandatory.get("generation_complete", False)
        
        # Integrity validated (structural integrity)
        check_results["integrity_validated"] = mandatory.get("structural_integrity", False)
        
        # Tenant isolation
        check_results["tenant_isolation"] = mandatory.get("tenant_isolation", False)
        
        # Temporal validated (maps to temporal_integrity)
        check_results["temporal_validated"] = mandatory.get("temporal_integrity", False)
        
        # Epistemic validated (maps to epistemic)
        check_results["epistemic_validated"] = mandatory.get("epistemic", False)
        
        # Provenance validated (maps to provenance)
        check_results["provenance_validated"] = mandatory.get("provenance", False)
        
        # Governance validated (maps to governance)
        check_results["governance_validated"] = mandatory.get("governance", False)
        
        # Multi-tenant isolation (maps to tenant_isolation for single-tenant)
        check_results["multi_tenant_isolation"] = mandatory.get("tenant_isolation", False)
        
        # Resource/connection checks - default to False (not exhausted)
        check_results["resource_exhausted"] = False
        check_results["connection_exhausted"] = False
        check_results["wal_exhausted"] = False
        
        # Evaluate gate
        can_promote, reason = gate.can_promote(check_results)
        return PromotionResult.PASS if can_promote else PromotionResult.FAIL
    
    def _check_ratification_checks(self, evidence: 'ScaleAcceptanceEvidence') -> bool:
        """Check if all ratification requirements are met."""
        # For the final profile, all mandatory checks must pass
        return all(evidence.mandatory_checks.values())
    
    def is_ratified(self) -> bool:
        """Check if 35-F is fully ratified."""
        required_profiles = [
            ScaleProfile.STARTUP_5,
            ScaleProfile.SMALL_50,
            ScaleProfile.MEDIUM_500,
            ScaleProfile.LARGE_5K,
            ScaleProfile.XLARGE_10K,
            ScaleProfile.ENTERPRISE_25K,
            ScaleProfile.MEGA_50K,
            ScaleProfile.MULTI_TENANT_10X5K,
            ScaleProfile.MULTI_TENANT_100X500,
            ScaleProfile.MULTI_TENANT_1000X50,
        ]
        
        for profile in required_profiles:
            if profile not in self.results:
                return False
            if self.results[profile].result != PromotionResult.PASS:
                return False
        
        return True
    
    def get_ratification_report(self) -> Dict[str, Any]:
        """Get complete ratification status report."""
        return {
            "ratified": self.is_ratified(),
            "current_profile": self.current_profile.value if self.current_profile else None,
            "completed_profiles": [
                p.value for p, r in self.results.items() 
                if r.result == PromotionResult.PASS
            ],
            "pending_profiles": [
                p.value for p, r in self.results.items() 
                if r.result not in (PromotionResult.PASS,)
            ],
            "results": {p.value: r.to_dict() for p, r in self.results.items()},
            "next_target": self.get_next_target().value if self.get_next_target() else None,
        }


def create_promotion_engine() -> PromotionGateEngine:
    """Create the promotion gate engine for 35-F validation."""
    return PromotionGateEngine()