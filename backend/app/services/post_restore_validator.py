"""Post-Restore Canonical Validation Orchestrator.

Composes existing canonical validators for comprehensive post-restore validation.
This does NOT create new validators - it orchestrates existing ones.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.validation.capability_contract import (
    ValidationResult,
    CapabilityAwareValidator,
)
from app.services.canonical_reality_integrity_service import (
    canonical_reality_integrity_service,
    severity_matches,
)
from app.models.canonical_reliability import (
    CanonicalOperation,
)

logger = logging.getLogger("vcos.canonical_validation")


class CanonicalValidationPhase(str, Enum):
    """Canonical validation phases."""
    STRUCTURAL = "structural"
    TENANT = "tenant"
    TEMPORAL = "temporal"
    PROVENANCE = "provenance"
    EPISTEMIC = "epistemic"
    GOVERNANCE = "governance"
    OPERATING_CHAIN = "operating_chain"
    CONTRADICTION = "contradiction"
    LONGITUDINAL = "longitudinal"
    COMPANY_BRAIN = "company_brain"
    DIGITAL_TWIN = "digital_twin"
    COMPLETE = "complete"


class ValidationVerdict(str, Enum):
    """Overall validation verdict."""
    VERIFIED = "verified"
    FAILED = "failed"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    WARNING = "warning"


@dataclass
class CanonicalValidationResult:
    """Result of a canonical validation phase."""
    phase: CanonicalValidationPhase
    verdict: ValidationVerdict
    started_at: datetime
    completed_at: Optional[datetime] = None
    message: str = ""
    findings: List[Dict[str, Any]] = field(default_factory=list)
    critical_count: int = 0
    high_count: int = 0
    medium_count: int = 0
    low_count: int = 0
    details: Dict[str, Any] = field(default_factory=dict)
    validation_result: Optional[ValidationResult] = None


@dataclass
class PostRestoreValidationReport:
    """Complete post-restore validation report."""
    report_id: str
    organization_id: str
    restore_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    overall_verdict: ValidationVerdict = ValidationVerdict.INCONCLUSIVE
    phases: List[CanonicalValidationResult] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    limitations: List[str] = field(default_factory=list)
    unknown_operations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "report_id": self.report_id,
            "organization_id": self.organization_id,
            "restore_id": self.restore_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "overall_verdict": self.overall_verdict.value,
            "phases": [
                {
                    "phase": p.phase.value,
                    "verdict": p.verdict.value,
                    "started_at": p.started_at.isoformat(),
                    "completed_at": p.completed_at.isoformat() if p.completed_at else None,
                    "message": p.message,
                    "critical_count": p.critical_count,
                    "high_count": p.high_count,
                    "medium_count": p.medium_count,
                    "low_count": p.low_count,
                    "details": p.details,
                }
                for p in self.phases
            ],
            "summary": self.summary,
            "limitations": self.limitations,
            "unknown_operations": self.unknown_operations,
        }


class PostRestoreCanonicalValidator(CapabilityAwareValidator):
    """Orchestrates post-restore canonical validation using existing validators."""
    
    def __init__(self):
        super().__init__()
        self._phase_validators: Dict[CanonicalValidationPhase, Callable] = {
            CanonicalValidationPhase.STRUCTURAL: self._validate_structural,
            CanonicalValidationPhase.TENANT: self._validate_tenant,
            CanonicalValidationPhase.TEMPORAL: self._validate_temporal,
            CanonicalValidationPhase.PROVENANCE: self._validate_provenance,
            CanonicalValidationPhase.EPISTEMIC: self._validate_epistemic,
            CanonicalValidationPhase.GOVERNANCE: self._validate_governance,
            CanonicalValidationPhase.OPERATING_CHAIN: self._validate_operating_chain,
            CanonicalValidationPhase.CONTRADICTION: self._validate_contradiction,
            CanonicalValidationPhase.LONGITUDINAL: self._validate_longitudinal,
            CanonicalValidationPhase.COMPANY_BRAIN: self._validate_company_brain,
            CanonicalValidationPhase.DIGITAL_TWIN: self._validate_digital_twin,
        }
    
    async def validate_restored_database(
        self,
        db: AsyncSession,
        organization_id: str,
        restore_id: str,
        recovery_target: Optional[datetime] = None,
        checks: Optional[List[str]] = None,
        limit: int = 100,
    ) -> PostRestoreValidationReport:
        """Run comprehensive canonical validation on restored database."""
        self.db = db
        self.detector.db = db
        
        report = PostRestoreValidationReport(
            report_id=f"crv-{uuid.uuid4().hex[:12]}",
            organization_id=organization_id,
            restore_id=restore_id,
            started_at=utcnow(),
        )
        
        # Determine which phases to run
        if checks:
            phases_to_run = [
                CanonicalValidationPhase(c) 
                for c in checks 
                if c in [p.value for p in CanonicalValidationPhase]
            ]
        else:
            # Run all phases except DIGITAL_TWIN (requires running twin)
            phases_to_run = [
                CanonicalValidationPhase.STRUCTURAL,
                CanonicalValidationPhase.TENANT,
                CanonicalValidationPhase.TEMPORAL,
                CanonicalValidationPhase.PROVENANCE,
                CanonicalValidationPhase.EPISTEMIC,
                CanonicalValidationPhase.GOVERNANCE,
                CanonicalValidationPhase.OPERATING_CHAIN,
                CanonicalValidationPhase.CONTRADICTION,
                CanonicalValidationPhase.LONGITUDINAL,
                CanonicalValidationPhase.COMPANY_BRAIN,
            ]
        
        try:
            overall_verdict = ValidationVerdict.VERIFIED
            
            for phase in phases_to_run:
                phase_result = await self._run_phase(db, phase, organization_id, limit, recovery_target)
                report.phases.append(phase_result)
                
                # Track overall verdict - most severe wins
                if phase_result.verdict == ValidationVerdict.FAILED:
                    overall_verdict = ValidationVerdict.FAILED
                elif phase_result.verdict == ValidationVerdict.BLOCKED and overall_verdict != ValidationVerdict.FAILED:
                    overall_verdict = ValidationVerdict.BLOCKED
                elif phase_result.verdict == ValidationVerdict.WARNING and overall_verdict == ValidationVerdict.VERIFIED:
                    overall_verdict = ValidationVerdict.WARNING
                elif phase_result.verdict == ValidationVerdict.INCONCLUSIVE and overall_verdict == ValidationVerdict.VERIFIED:
                    overall_verdict = ValidationVerdict.INCONCLUSIVE
            
            # Identify unknown operations at recovery target
            report.unknown_operations = await self._identify_unknown_operations(db, organization_id, recovery_target)
            
            # Generate summary
            report.summary = self._generate_summary(report)
            
            report.overall_verdict = overall_verdict
            report.completed_at = utcnow()
            
        except Exception as e:
            logger.error(f"Post-restore validation failed: {e}")
            report.overall_verdict = ValidationVerdict.FAILED
            report.completed_at = utcnow()
            report.summary["error"] = str(e)
        
        return report
    
    async def _run_phase(
        self,
        db: AsyncSession,
        phase: CanonicalValidationPhase,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> CanonicalValidationResult:
        """Run a single validation phase."""
        phase_start = utcnow()
        
        validator = self._phase_validators.get(phase)
        if not validator:
            return CanonicalValidationResult(
                phase=phase,
                verdict=ValidationVerdict.INCONCLUSIVE,
                started_at=phase_start,
                completed_at=utcnow(),
                message=f"No validator for phase {phase.value}",
            )
        
        try:
            result = await validator(db, organization_id, limit, recovery_target)
            return CanonicalValidationResult(
                phase=phase,
                verdict=result.get("verdict", ValidationVerdict.INCONCLUSIVE),
                started_at=phase_start,
                completed_at=utcnow(),
                message=result.get("message", ""),
                findings=result.get("findings", []),
                critical_count=result.get("critical_count", 0),
                high_count=result.get("high_count", 0),
                medium_count=result.get("medium_count", 0),
                low_count=result.get("low_count", 0),
                details=result.get("details", {}),
                validation_result=result.get("validation_result"),
            )
        except Exception as e:
            logger.error(f"Validation phase {phase.value} failed: {e}")
            return CanonicalValidationResult(
                phase=phase,
                verdict=ValidationVerdict.FAILED,
                started_at=phase_start,
                completed_at=utcnow(),
                message=f"Phase execution failed: {str(e)}",
            )
    
    # =====================================================================
    # PHASE VALIDATORS - Compose existing validators
    # =====================================================================
    
    async def _validate_structural(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate structural integrity using canonical_reality_integrity_service."""
        findings = await canonical_reality_integrity_service.check_structural_integrity(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        high = [f for f in findings if severity_matches(f, "HIGH")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Structural integrity failed: {len(critical)} critical findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        elif high:
            return {
                "verdict": ValidationVerdict.WARNING,
                "message": f"Structural integrity has {len(high)} high-severity findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Structural integrity validated",
                "findings": [],
                "critical_count": 0,
                "high_count": 0,
            }
    
    async def _validate_tenant(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate tenant isolation using canonical_reality_integrity_service."""
        findings = await canonical_reality_integrity_service.check_tenant_integrity(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Tenant isolation failed: {len(critical)} critical cross-tenant references",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Tenant isolation validated",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": 0,
            }
    
    async def _validate_temporal(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate temporal integrity using existing validators."""
        # Use the canonical_reality_integrity_service
        findings = await canonical_reality_integrity_service.check_temporal_integrity(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        high = [f for f in findings if severity_matches(f, "HIGH")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Temporal integrity failed: {len(critical)} critical findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        elif high:
            return {
                "verdict": ValidationVerdict.WARNING,
                "message": f"Temporal integrity has {len(high)} high-severity findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Temporal integrity validated",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": 0,
                "high_count": 0,
            }
    
    async def _validate_provenance(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate provenance using existing validators."""
        findings = await canonical_reality_integrity_service.check_provenance_integrity(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        high = [f for f in findings if severity_matches(f, "HIGH")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Provenance validation failed: {len(critical)} critical findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        elif high:
            return {
                "verdict": ValidationVerdict.WARNING,
                "message": f"Provenance has {len(high)} high-severity findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Provenance validated",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": 0,
                "high_count": 0,
            }
    
    async def _validate_epistemic(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate epistemic integrity using existing validators."""
        findings = await canonical_reality_integrity_service.check_epistemic_integrity(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        high = [f for f in findings if severity_matches(f, "HIGH")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Epistemic validation failed: {len(critical)} critical findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        elif high:
            return {
                "verdict": ValidationVerdict.WARNING,
                "message": f"Epistemic has {len(high)} high-severity findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Epistemic integrity validated",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": 0,
                "high_count": 0,
            }
    
    async def _validate_governance(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate governance using existing validators."""
        findings = await canonical_reality_integrity_service.check_gate30_integrity(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        high = [f for f in findings if severity_matches(f, "HIGH")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Governance validation failed: {len(critical)} critical findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        elif high:
            return {
                "verdict": ValidationVerdict.WARNING,
                "message": f"Governance has {len(high)} high-severity findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Governance validated",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": 0,
                "high_count": 0,
            }
    
    async def _validate_operating_chain(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate operating chain (Decision -> Authorization -> Commitment -> Action -> Outcome)."""
        findings = await canonical_reality_integrity_service.check_operating_chain_integrity(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        high = [f for f in findings if severity_matches(f, "HIGH")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Operating chain validation failed: {len(critical)} critical breaks",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        elif high:
            return {
                "verdict": ValidationVerdict.WARNING,
                "message": f"Operating chain has {len(high)} high-severity issues",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Operating chain validated",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": 0,
                "high_count": 0,
            }
    
    async def _validate_contradiction(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate contradiction preservation using the canonical integrity scan."""
        findings = await canonical_reality_integrity_service.check_contradiction_integrity(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        high = [f for f in findings if severity_matches(f, "HIGH")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Contradiction preservation failed: {len(critical)} critical findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        elif high:
            return {
                "verdict": ValidationVerdict.WARNING,
                "message": f"Contradiction preservation has {len(high)} high-severity findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Contradiction preservation validated",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": 0,
                "high_count": 0,
            }
    
    async def _validate_longitudinal(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate longitudinal integrity."""
        findings = await canonical_reality_integrity_service.check_longitudinal_integrity(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        high = [f for f in findings if severity_matches(f, "HIGH")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Longitudinal validation failed: {len(critical)} critical findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        elif high:
            return {
                "verdict": ValidationVerdict.WARNING,
                "message": f"Longitudinal has {len(high)} high-severity findings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Longitudinal integrity validated",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": 0,
                "high_count": 0,
            }
    
    async def _validate_company_brain(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate Company Brain dependencies can be rebuilt."""
        findings = await canonical_reality_integrity_service.check_company_brain_dependencies(
            db=db,
            organization_id=organization_id,
            limit=limit,
        )
        
        critical = [f for f in findings if severity_matches(f, "CRITICAL")]
        high = [f for f in findings if severity_matches(f, "HIGH")]
        
        if critical:
            return {
                "verdict": ValidationVerdict.FAILED,
                "message": f"Company Brain validation failed: {len(critical)} critical missing dependencies",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        elif high:
            return {
                "verdict": ValidationVerdict.WARNING,
                "message": f"Company Brain has {len(high)} high-severity warnings",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": len(critical),
                "high_count": len(high),
            }
        else:
            return {
                "verdict": ValidationVerdict.VERIFIED,
                "message": "Company Brain dependencies validated",
                "findings": [self._finding_to_dict(f) for f in findings],
                "critical_count": 0,
                "high_count": 0,
            }
    
    async def _validate_digital_twin(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int,
        recovery_target: Optional[datetime],
    ) -> Dict[str, Any]:
        """Validate Digital Twin projections."""
        # This would check if the continuous twin can be reconstructed
        # For now, check if the required tables have data
        try:
            from app.models.continuous_twin import (
                CompanyAttention, ModelTwinDrift, TwinStateSnapshot,
                PredictionCalibration, OptimizationContext,
            )
            
            tables = [CompanyAttention, ModelTwinDrift, TwinStateSnapshot, PredictionCalibration, OptimizationContext]
            empty = []
            
            for table in tables:
                result = await db.execute(select(table))
                rows = result.scalars().all()
                if not rows:
                    empty.append(table.__name__)
            
            if empty:
                return {
                    "verdict": ValidationVerdict.WARNING,
                    "message": f"Digital Twin tables empty: {empty}",
                    "details": {"empty_tables": empty},
                }
            else:
                return {
                    "verdict": ValidationVerdict.VERIFIED,
                    "message": "Digital Twin tables have data",
                    "details": {"tables_checked": len(tables)},
                }
        except Exception as e:
            return {
                "verdict": ValidationVerdict.INCONCLUSIVE,
                "message": f"Digital Twin validation error: {str(e)}",
                "details": {"error": str(e)},
            }
    
    async def _identify_unknown_operations(
        self,
        db: AsyncSession,
        organization_id: str,
        recovery_target: Optional[datetime],
    ) -> List[str]:
        """Identify operations that are UNKNOWN at the recovery target."""
        unknown_ops = []
        
        try:
            # Check canonical operations with UNKNOWN state
            query = select(CanonicalOperation).where(
                CanonicalOperation.organization_id == organization_id,
                CanonicalOperation.state == "unknown",
            )
            
            if recovery_target:
                query = query.where(CanonicalOperation.created_at <= recovery_target)
            
            result = await db.execute(query.limit(100))
            for op in result.scalars().all():
                unknown_ops.append(
                    f"Operation {op.id} ({op.operation_type}) is UNKNOWN - "
                    f"created at {op.created_at}, no attempts recorded"
                )
            
            # Check external unknown states
            from app.models.canonical_reliability import ExternalUnknownState
            query = select(ExternalUnknownState).where(
                ExternalUnknownState.organization_id == organization_id,
                ExternalUnknownState.state == "unknown",
            )
            
            if recovery_target:
                query = query.where(ExternalUnknownState.requested_at <= recovery_target)
            
            result = await db.execute(query.limit(100))
            for state in result.scalars().all():
                unknown_ops.append(
                    f"External operation {state.external_operation_id} on {state.external_system} "
                    f"is UNKNOWN - requested at {state.requested_at}, no resolution evidence"
                )
                
        except Exception as e:
            logger.warning(f"Could not identify unknown operations: {e}")
        
        return unknown_ops
    
    def _finding_to_dict(self, finding) -> Dict[str, Any]:
        """Convert IntegrityFinding to dictionary."""
        return {
            "id": finding.id,
            "type": finding.finding_type.value if hasattr(finding.finding_type, 'value') else str(finding.finding_type),
            "severity": finding.severity.value if hasattr(finding.severity, 'value') else str(finding.severity),
            "entity_type": finding.entity_type,
            "entity_id": finding.entity_id,
            "title": finding.title,
            "description": finding.description,
            "observed_evidence": finding.observed_evidence,
            "provenance": finding.provenance,
        }
    
    def _generate_summary(self, report: PostRestoreValidationReport) -> Dict[str, Any]:
        """Generate validation summary."""
        total_critical = sum(p.critical_count for p in report.phases)
        total_high = sum(p.high_count for p in report.phases)
        total_medium = sum(p.medium_count for p in report.phases)
        total_low = sum(p.low_count for p in report.phases)
        
        passed_phases = [p for p in report.phases if p.verdict == ValidationVerdict.VERIFIED]
        warning_phases = [p for p in report.phases if p.verdict == ValidationVerdict.WARNING]
        failed_phases = [p for p in report.phases if p.verdict == ValidationVerdict.FAILED]
        blocked_phases = [p for p in report.phases if p.verdict == ValidationVerdict.BLOCKED]
        
        return {
            "total_phases": len(report.phases),
            "passed_phases": len(passed_phases),
            "warning_phases": len(warning_phases),
            "failed_phases": len(failed_phases),
            "blocked_phases": len(blocked_phases),
            "total_critical_findings": total_critical,
            "total_high_findings": total_high,
            "total_medium_findings": total_medium,
            "total_low_findings": total_low,
            "unknown_operations_count": len(report.unknown_operations),
            "recovery_target": report.phases[0].started_at.isoformat() if report.phases else None,
        }


# Global instance
post_restore_canonical_validator = PostRestoreCanonicalValidator()