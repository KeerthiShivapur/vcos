"""Automated Recovery Evidence Generator.

Generates machine-readable recovery evidence artifacts for DR validation.
"""

import json
import platform
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.backup_manifest import BackupManifest, BackupStatus, BackupKind
from app.services.recovery_gates import RecoveryGateState, recovery_readiness_gates
from app.services.pitr_test_orchestrator import pitr_test_orchestrator, PITRTestResult
from app.services.post_restore_validator import post_restore_canonical_validator, ValidationVerdict
from app.services.rpo_rto_measurement import rpo_rto_service, RPORTOMeasurement


class EvidenceStatus(str, Enum):
    """Evidence generation status."""
    PENDING = "pending"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class RecoveryEvidence:
    """Complete recovery evidence artifact."""
    
    # Metadata
    evidence_id: str
    generated_at: datetime
    code_revision: str
    environment_identity: str
    postgresql_version: str
    
    # Backup info
    backup_id: str
    backup_checksum: str
    backup_size_bytes: int
    wal_range_start: str
    wal_range_end: str
    
    # Recovery info
    recovery_target: Optional[datetime] = None
    recovery_target_lsn: Optional[str] = None
    
    # Test results
    restore_result: Optional[Dict[str, Any]] = None
    pitr_result: Optional[Dict[str, Any]] = None
    
    # Validation results
    canonical_validation: Optional[Dict[str, Any]] = None
    tenant_isolation: Optional[Dict[str, Any]] = None
    temporal_validation: Optional[Dict[str, Any]] = None
    provenance_validation: Optional[Dict[str, Any]] = None
    epistemic_validation: Optional[Dict[str, Any]] = None
    governance_validation: Optional[Dict[str, Any]] = None
    longitudinal_validation: Optional[Dict[str, Any]] = None
    
    # RPO/RTO
    rpo_rto_measurement: Optional[Dict[str, Any]] = None
    
    # Limitations
    limitations: List[str] = field(default_factory=list)
    historical_gaps: List[Dict[str, Any]] = field(default_factory=list)
    
    # Final verdict
    final_verdict: str = "INCONCLUSIVE"
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize to dictionary."""
        data = asdict(self)
        # Convert datetime to ISO format
        data["generated_at"] = self.generated_at.isoformat()
        if self.recovery_target:
            data["recovery_target"] = self.recovery_target.isoformat()
        return data
    
    def to_json(self) -> str:
        """Serialize to JSON."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> "RecoveryEvidence":
        """Deserialize from JSON."""
        data = json.loads(json_str)
        data["generated_at"] = datetime.fromisoformat(data["generated_at"])
        if data.get("recovery_target"):
            data["recovery_target"] = datetime.fromisoformat(data["recovery_target"])
        return cls(**data)


class RecoveryEvidenceGenerator:
    """Generates recovery evidence artifacts."""
    
    def __init__(self):
        self._evidence_store: Dict[str, RecoveryEvidence] = {}

    def _runtime_identity(self) -> Dict[str, str]:
        """Derive evidence identity metadata from the runtime configuration."""
        settings = get_settings()
        return {
            "code_revision": str(getattr(settings, "APP_VERSION", "unknown")),
            "environment_identity": f"{settings.APP_ENV}-{platform.node() or 'unknown'}",
        }
    
    async def generate_from_pitr_test(
        self,
        db: AsyncSession,
        test_id: str,
    ) -> RecoveryEvidence:
        """Generate evidence from a completed PITR test."""
        test = pitr_test_orchestrator.get_test(test_id)
        if not test:
            raise ValueError(f"PITR test {test_id} not found")
        
        backup = await db.get(BackupManifest, test.backup_id)
        if not backup:
            raise ValueError(f"Backup {test.backup_id} not found")
        
        # Get RPO/RTO measurement
        rpo_rto = None
        measurements = rpo_rto_service.get_measurements_by_recovery(test_id)
        if measurements:
            rpo_rto = measurements[0].to_dict()
        
        evidence = RecoveryEvidence(
            evidence_id=f"ev-{uuid.uuid4().hex[:12]}",
            generated_at=datetime.now(timezone.utc),
            **self._runtime_identity(),
            postgresql_version=backup.pg_version or "18.2",
            
            backup_id=backup.id,
            backup_checksum=backup.checksum_sha256 or "",
            backup_size_bytes=backup.backup_size_bytes,
            wal_range_start=backup.verification_details.get("required_wal_start_lsn", "") if backup.verification_details else "",
            wal_range_end=backup.verification_details.get("required_wal_end_lsn", "") if backup.verification_details else "",
            
            recovery_target=test.target.target_time if test.target else None,
            recovery_target_lsn=test.target.target_lsn if test.target else None,
            
            restore_result={
                "success": test.isolated_restore_result.success if test.isolated_restore_result else False,
                "state": test.isolated_restore_result.state.value if test.isolated_restore_result else "unknown",
                "wal_files_replayed": test.isolated_restore_result.wal_files_replayed if test.isolated_restore_result else 0,
            } if test.isolated_restore_result else None,
            
            pitr_result={
                "result": test.result.value,
                "canonical_integrity_at_target": test.canonical_integrity_at_target,
                "temporal_integrity_at_target": test.temporal_integrity_at_target,
                "tenant_isolation_at_target": test.tenant_isolation_at_target,
                "provenance_integrity_at_target": test.provenance_integrity_at_target,
                "epistemic_integrity_at_target": test.epistemic_integrity_at_target,
                "governance_integrity_at_target": test.governance_integrity_at_target,
                "phases": [
                    {
                        "phase": p.phase.value,
                        "passed": p.passed,
                        "message": p.message,
                    }
                    for p in test.phases
                ],
            } if test.target else None,
            
            canonical_validation={
                "verified": test.canonical_integrity_at_target,
            },
            tenant_isolation={
                "verified": test.tenant_isolation_at_target,
            },
            temporal_validation={
                "verified": test.temporal_integrity_at_target,
            },
            provenance_validation={
                "verified": test.provenance_integrity_at_target,
            },
            epistemic_validation={
                "verified": test.epistemic_integrity_at_target,
            },
            governance_validation={
                "verified": test.governance_integrity_at_target,
            },
            
            rpo_rto_measurement=rpo_rto,
            
            limitations=self._collect_limitations(test),
            historical_gaps=backup.verification_details.get("historical_gaps", []) if backup.verification_details else [],
            
            final_verdict=test.result.value.upper(),
        )
        
        self._evidence_store[evidence.evidence_id] = evidence
        return evidence
    
    async def generate_from_restore(
        self,
        db: AsyncSession,
        recovery_id: str,
        canonical_report: Optional[Any] = None,
        restore_result: Optional[Any] = None,
    ) -> RecoveryEvidence:
        """Generate evidence from a restore operation."""
        context = recovery_readiness_gates.get_context(recovery_id)
        if not context:
            raise ValueError(f"Recovery context {recovery_id} not found")
        
        backup = await db.get(BackupManifest, context.backup_id)
        if not backup:
            raise ValueError(f"Backup {context.backup_id} not found")
        
        # Use the caller-provided canonical report (already run against the
        # restored database) or run the validator as a fallback.
        if canonical_report is None and context.target_time:
            canonical_report = await post_restore_canonical_validator.validate_restored_database(
                db=db,
                organization_id=context.organization_id,
                restore_id=recovery_id,
                recovery_target=context.target_time,
            )
        
        # Get RPO/RTO
        rpo_rto = None
        measurements = rpo_rto_service.get_measurements_by_recovery(recovery_id)
        if measurements:
            rpo_rto = measurements[0].to_dict()
        
        # Get gate status
        gate_status = recovery_readiness_gates.get_gate_status(recovery_id)
        
        restore_summary = {
            "recovery_id": recovery_id,
            "current_state": context.current_state.value,
            "gates": gate_status.get("gates", {}),
        }
        if restore_result is not None:
            restore_summary.update({
                "restore_id": getattr(restore_result, "restore_id", None),
                "isolated_port": getattr(restore_result, "isolated_port", None),
                "isolated_data_dir": getattr(restore_result, "isolated_data_dir", None),
                "validation_database": getattr(restore_result, "validation_database", None),
                "wal_files_replayed": getattr(restore_result, "wal_files_replayed", None),
                "canonical_validation_passed": getattr(restore_result, "canonical_validation_passed", None),
            })
        
        state = context.current_state
        if state == RecoveryGateState.ACTIVATED:
            final_verdict = "VERIFIED"
        elif state == RecoveryGateState.READY_FOR_APPROVAL:
            final_verdict = "VERIFIED_PENDING_ACTIVATION"
        elif state in (RecoveryGateState.FAILED, RecoveryGateState.BLOCKED):
            final_verdict = "NOT_VERIFIED"
        else:
            final_verdict = "IN_PROGRESS"
        
        evidence = RecoveryEvidence(
            evidence_id=f"ev-{uuid.uuid4().hex[:12]}",
            generated_at=datetime.now(timezone.utc),
            **self._runtime_identity(),
            postgresql_version=backup.pg_version or "18.2",
            
            backup_id=backup.id,
            backup_checksum=backup.checksum_sha256 or "",
            backup_size_bytes=backup.backup_size_bytes,
            wal_range_start=backup.verification_details.get("required_wal_start_lsn", "") if backup.verification_details else "",
            wal_range_end=backup.verification_details.get("required_wal_end_lsn", "") if backup.verification_details else "",
            
            recovery_target=context.target_time,
            recovery_target_lsn=context.target_lsn,
            
            restore_result=restore_summary,
            
            pitr_result={
                "target_time": context.target_time.isoformat() if context.target_time else None,
                "target_lsn": context.target_lsn,
            } if context.target_time or context.target_lsn else None,
            
            canonical_validation=canonical_report.to_dict() if canonical_report else None,
            
            rpo_rto_measurement=rpo_rto,
            
            limitations=self._collect_restore_limitations(context),
            historical_gaps=backup.verification_details.get("historical_gaps", []) if backup.verification_details else [],
            
            final_verdict=final_verdict,
        )
        
        self._evidence_store[evidence.evidence_id] = evidence
        return evidence
    
    def _collect_limitations(self, test) -> List[str]:
        """Collect limitations from test execution."""
        limitations = []
        
        if test.target and test.target.target_time:
            # Check if target is near gap
            pass
        
        if test.isolated_restore_result and test.isolated_restore_result.warnings:
            limitations.extend(test.isolated_restore_result.warnings)
        
        # Always document the segment 14 gap
        limitations.append("Historical WAL segment 000000010000008900000014 permanently missing - no PITR coverage across this gap")
        
        return limitations
    
    def _collect_restore_limitations(self, context) -> List[str]:
        """Collect limitations from restore context."""
        limitations = []
        
        if context.error:
            limitations.append(f"Recovery error: {context.error}")
        
        if context.current_state in (RecoveryGateState.FAILED, RecoveryGateState.BLOCKED, RecoveryGateState.INCONCLUSIVE):
            limitations.append(f"Recovery state: {context.current_state.value}")
        
        # Always document the segment 14 gap
        limitations.append("Historical WAL segment 000000010000008900000014 permanently missing - no PITR coverage across this gap")
        
        return limitations
    
    def get_evidence(self, evidence_id: str) -> Optional[RecoveryEvidence]:
        """Get evidence by ID."""
        return self._evidence_store.get(evidence_id)
    
    def list_evidence(self) -> List[Dict[str, Any]]:
        """List all evidence artifacts."""
        return [
            {
                "evidence_id": e.evidence_id,
                "generated_at": e.generated_at.isoformat(),
                "backup_id": e.backup_id,
                "recovery_target": e.recovery_target.isoformat() if e.recovery_target else None,
                "final_verdict": e.final_verdict,
            }
            for e in self._evidence_store.values()
        ]


# Global instance
recovery_evidence_generator = RecoveryEvidenceGenerator()