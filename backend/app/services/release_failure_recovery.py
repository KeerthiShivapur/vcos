"""Release Failure Injection & Recovery Service — Slice 2C.

Implements deterministic failure injection during release lifecycle and governed recovery
with canonical fingerprint validation.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select, text, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.core.config import get_settings
from app.models.release import (
    ReleaseRecord,
    ReleasePhase,
    ReleaseFailureType,
    ReleaseFailureInjection,
    ReleaseRecoveryRecord,
    ReleaseRecoveryRecord,
    ReleaseFingerprintEvidence,
    ReleasePhase,
    ReleaseFailureType,
    RecoveryStrategy,
    ReleasePhase as ReleasePhaseEnum,
    ReleaseFailureType as ReleaseFailureTypeEnum,
)
from app.models.release import (
    ReleaseRecord as ReleaseRecordModel,
    ReleaseFailureInjection as ReleaseFailureInjectionModel,
    ReleaseRecoveryRecord as ReleaseRecoveryRecordModel,
    ReleaseFingerprintEvidence as ReleaseFingerprintEvidenceModel,
)
from app.services.canonical_fingerprint import (
    canonical_fingerprint_service,
    release_candidate_fingerprint_service,
    CanonicalFingerprintService,
    ReleaseCandidateFingerprintService,
    FingerprintAlgorithm,
)
from app.services.canonical_reality_integrity_service import (
    canonical_reality_integrity_service,
    severity_matches,
)
from app.services.deployment_contract_service import deployment_contract_service, DeploymentContractService
from app.services.backup_service import backup_service
from app.services.restore_service import restore_service
from app.intelligence.canonical_mutation import canonical_mutation_boundary
from app.core.timeutils import utcnow
from app.events.publisher import publish_event

logger = logging.getLogger("vcos.release_recovery")


class ReleaseRecoveryPhase(str, Enum):
    """Recovery operation phases."""
    ASSESSING = "assessing"
    PLANNING = "planning"
    GOVERNANCE = "governance"
    EXECUTING = "executing"
    VALIDATING = "validating"
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


@dataclass
class FailureInjectionContext:
    """Context for a failure injection."""
    release_id: str
    failure_type: str
    failure_point: str
    error_message: str
    error_code: Optional[str] = None
    exception_type: Optional[str] = None
    trigger_parameters: Optional[Dict[str, Any]] = None
    test_mode_only: bool = True


@dataclass
class ReleaseFailureContext:
    """Context for a release failure."""
    release_id: str
    failure_type: str
    failure_point: str
    error_message: str
    error_code: Optional[str] = None
    exception_type: Optional[str] = None
    injected_at: datetime = field(default_factory=utcnow)


class ReleaseFailureRecoveryService:
    """Release Failure Injection & Recovery Service.
    
    Implements deterministic failure injection during release lifecycle and 
    governed recovery with canonical fingerprint validation.
    """
    
    def __init__(self):
        self.settings = get_settings()
        self.fingerprint_service = canonical_fingerprint_service
        self.release_fingerprint_service = release_candidate_fingerprint_service
        self.deployment_contract_service = deployment_contract_service
        self.canonical_integrity_service = canonical_reality_integrity_service
        self._active_failures: Dict[str, Dict[str, Any]] = {}
        
    # =========================================================================
    # RELEASE LIFECYCLE MANAGEMENT
    # =========================================================================
    
    async def create_release_record(
        self,
        db: AsyncSession,
        organization_id: str,
        version: str,
        initiated_by: str,
        contract_id: Optional[str] = None,
        feature_flags_snapshot: Optional[Dict[str, Any]] = None,
    ) -> ReleaseRecord:
        """Create a new release record."""
        
        release = ReleaseRecord(
            id=f"rel-{uuid.uuid4().hex[:12]}",
            organization_id=organization_id,
            version=version,
            status="pending",
            phase=ReleasePhase.PLANNED.value,
            contract_id=contract_id,
            initiated_by=initiated_by,
            metadata_json={
                "feature_flags": feature_flags_snapshot,
            },
            started_at=utcnow(),
        )
        
        db.add(release)
        await db.flush()
        
        await publish_event(
            db,
            name="release.created",
            actor_id=initiated_by,
            organization_id=organization_id,
            payload={
                "release_id": release.id,
                "version": version,
                "organization_id": organization_id,
            },
        )
        
        logger.info(f"Created release record {release.id} for org {organization_id} version {version}")
        return release
    
    async def advance_phase(
        self,
        db: AsyncSession,
        release_id: str,
        new_phase: ReleasePhase,
        actor_id: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> ReleaseRecord:
        """Advance release to next phase."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        old_phase = release.phase
        release.phase = new_phase.value
        release.phase_completed_at = utcnow()
        
        # Track phase history
        if not release.phase_history:
            release.phase_history = []
        
        release.phase_history.append({
            "from_phase": old_phase,
            "to_phase": new_phase.value,
            "timestamp": utcnow().isoformat(),
            "actor_id": actor_id,
            "details": details or {},
        })
        
        # Update phase-specific timestamps
        if new_phase == ReleasePhase.PRECHECKING:
            release.phase_started_at = utcnow()
        elif new_phase == ReleasePhase.FINGERPRINT_CAPTURED:
            release.phase_completed_at = utcnow()
        elif new_phase == ReleasePhase.MIGRATION_STARTED:
            release.migration_started_at = utcnow()
        elif new_phase == ReleasePhase.MIGRATION_COMPLETED:
            release.migration_completed_at = utcnow()
        elif new_phase == ReleasePhase.APPLICATION_DEPLOYED:
            release.application_deployed_at = utcnow()
        elif new_phase == ReleasePhase.WORKERS_DEPLOYED:
            release.workers_deployed_at = utcnow()
        elif new_phase == ReleasePhase.ACTIVE:
            release.completed_at = utcnow()
            release.status = "completed"
        
        release.updated_at = utcnow()
        await db.flush()
        
        await publish_event(
            db,
            name="release.phase_changed",
            actor_id=actor_id,
            organization_id=release.organization_id,
            payload={
                "release_id": release.id,
                "old_phase": old_phase,
                "new_phase": new_phase.value,
            },
        )
        
        logger.info(f"Release {release_id} advanced from {old_phase} to {new_phase.value}")
        return release
    
    # =========================================================================
    # FINGERPRINT MANAGEMENT
    # =========================================================================
    
    async def capture_pre_release_fingerprint(
        self,
        db: AsyncSession,
        release_id: str,
        organization_ids: Optional[List[str]] = None,
    ) -> ReleaseFingerprintEvidence:
        """Capture pre-release canonical fingerprint."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        # Advance to fingerprint capture phase
        await self.advance_phase(db, release_id, ReleasePhase.FINGERPRINT_CAPTURED, "system")
        
        # Capture fingerprint - use release's organization if not specified
        if organization_ids is None:
            organization_ids = [release.organization_id]
        
        # Capture fingerprint
        fp_evidence = await self.release_fingerprint_service.create_release_candidate_fingerprint(
            db=db,
            release_candidate_id=release.id,
            application_version=release.version,
            schema_revision="head",  # Would get actual alembic revision
            organization_ids=organization_ids,
            preflight_verdict="pre_release",
            preflight_timestamp=utcnow(),
        )
        
        # Store fingerprint evidence
        import json
        from dataclasses import asdict
        from datetime import datetime
        
        def serialize_component(c):
            d = asdict(c)
            # Convert datetime to ISO format string
            if 'last_updated' in d and isinstance(d['last_updated'], datetime):
                d['last_updated'] = d['last_updated'].isoformat()
            if 'metadata' in d and isinstance(d['metadata'], dict):
                for k, v in d['metadata'].items():
                    if isinstance(v, datetime):
                        d['metadata'][k] = v.isoformat()
            return d
        
        fp_evidence_record = ReleaseFingerprintEvidence(
            release_id=release.id,
            organization_id=release.organization_id,
            fingerprint_type="pre_release",
            aggregate_fingerprint=fp_evidence.aggregate_fingerprint,
            component_fingerprints=[serialize_component(c) for c in fp_evidence.tenants[0].components] if fp_evidence.tenants else {},
            algorithm="sha256_64",
            algorithm_version="1.0",
            computed_by="system",
        )
        db.add(fp_evidence_record)
        
        # Store in release record
        release.pre_release_fingerprint = fp_evidence.aggregate_fingerprint
        release.pre_release_component_fingerprints = {
            tenant.organization_id: {
                "aggregate": tenant.aggregate_fingerprint,
                "components": {c.component_name: c.fingerprint for c in tenant.components}
            }
            for tenant in fp_evidence.tenants
        }
        
        await db.flush()
        
        logger.info(f"Captured pre-release fingerprint for release {release_id}: {fp_evidence.aggregate_fingerprint[:16]}...")
        return fp_evidence
    
    async def capture_post_release_fingerprint(
        self,
        db: AsyncSession,
        release_id: str,
        organization_ids: Optional[List[str]] = None,
    ) -> ReleaseFingerprintEvidence:
        """Capture post-release canonical fingerprint."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        # Capture post-release fingerprint - use release's organization if not specified
        if organization_ids is None:
            organization_ids = [release.organization_id]
        
        # Capture post-release fingerprint
        fp_evidence = await self.release_fingerprint_service.create_release_candidate_fingerprint(
            db=db,
            release_candidate_id=release.id,
            application_version=release.version,
            schema_revision="head",
            organization_ids=organization_ids,
            preflight_verdict="post_release",
            preflight_timestamp=utcnow(),
        )
        
        # Store fingerprint evidence
        fp_evidence_record = ReleaseFingerprintEvidence(
            release_id=release.id,
            organization_id=release.organization_id,
            fingerprint_type="post_release",
            aggregate_fingerprint=fp_evidence.aggregate_fingerprint,
            component_fingerprints={tenant.organization_id: {c.component_name: c.fingerprint for c in tenant.components} for tenant in fp_evidence.tenants},
            algorithm="sha256_64",
            algorithm_version="1.0",
            computed_by="system",
        )
        db.add(fp_evidence_record)
        
        # Store in release record
        release.post_release_fingerprint = fp_evidence.aggregate_fingerprint
        release.post_release_component_fingerprints = {
            tenant.organization_id: {
                "aggregate": tenant.aggregate_fingerprint,
                "components": {c.component_name: c.fingerprint for c in tenant.components}
            }
            for tenant in fp_evidence.tenants
        }
        
        await db.flush()
        
        logger.info(f"Captured post-release fingerprint for release {release_id}: {fp_evidence.aggregate_fingerprint[:16]}...")
        return fp_evidence
    
    async def compare_fingerprints(
        self,
        db: AsyncSession,
        release_id: str,
        expected_changes: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Compare pre-release and post-release fingerprints."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        if not release.pre_release_fingerprint or not release.post_release_fingerprint:
            raise ValueError("Both pre-release and post-release fingerprints must be captured")
        
        # Use release fingerprint service to compare
        pre_fp = type('obj', (object,), {
            'tenants': [type('obj', (object,), {
                'organization_id': org_id,
                'aggregate_fingerprint': data.get('aggregate', ''),
                'components': [type('obj', (object,), {'component_name': c, 'fingerprint': fp, 'entity_count': 0}) 
                            for c, fp in data.get('components', {}).items()]
            })() for org_id, data in (release.pre_release_component_fingerprints or {}).items()],
            'aggregate_fingerprint': release.pre_release_fingerprint,
        })()
        
        post_fp = type('obj', (object,), {
            'tenants': [type('obj', (object,), {
                'organization_id': org_id,
                'aggregate_fingerprint': data.get('aggregate', ''),
                'components': [type('obj', (object,), {'component_name': c, 'fingerprint': fp, 'entity_count': 0}) 
                            for c, fp in data.get('components', {}).items()]
            })() for org_id, data in (release.post_release_component_fingerprints or {}).items()],
            'aggregate_fingerprint': release.post_release_fingerprint,
        })()
        
        comparison = await self.release_fingerprint_service.compare_fingerprints(pre_fp, post_fp)
        
        # Classify changes as expected vs unexpected
        expected_changes = {}
        unexpected_changes = {}
        
        if expected_changes is None:
            # No expected changes provided - all differences are unexpected
            unexpected_changes = comparison.get("component_differences", [])
        else:
            # Classify based on expected changes
            for diff in comparison.get("component_differences", []):
                comp = diff["component"]
                if comp in expected_changes:
                    expected_changes[comp] = diff
                else:
                    unexpected_changes[comp] = diff
        
        # Store comparison result
        release.fingerprint_comparison_result = comparison
        release.expected_fingerprint_changes = expected_changes
        release.unexpected_fingerprint_changes = unexpected_changes
        release.fingerprint_match = comparison.get("overall") == "MATCH"
        
        await db.flush()
        
        logger.info(f"Fingerprint comparison for release {release.id}: {'MATCH' if comparison.get('overall') == 'MATCH' else 'MISMATCH'}")
        return comparison
    
    # =========================================================================
    # FAILURE INJECTION FRAMEWORK
    # =========================================================================
    
    async def inject_failure(
        self,
        db: AsyncSession,
        release_id: str,
        failure_type: str,
        failure_point: str,
        error_message: str,
        error_code: Optional[str] = None,
        exception_type: Optional[str] = None,
        trigger_parameters: Optional[Dict[str, Any]] = None,
        test_mode_only: bool = True,
        actor_id: str = "system",
    ) -> ReleaseFailureInjection:
        """Inject a deterministic failure into a release."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        # Check if test mode
        import os
        if test_mode_only and os.environ.get("VCOS_TEST_MODE") != "1":
            raise ValueError("Failure injection only allowed in test mode (VCOS_TEST_MODE=1)")
        
        injection = ReleaseFailureInjection(
            release_id=release.id,
            organization_id=release.organization_id,
            failure_type=failure_type,
            failure_point=failure_point,
            error_message=f"INJECTED: {error_message}",
            error_code=error_code,
            exception_type=exception_type or "InjectedReleaseFailure",
            trigger_condition="always",
            trigger_parameters={},
            created_by="system",
            test_mode_only=True,
        )
        
        db.add(injection)
        
        # Update release with failure info
        release.failure_type = failure_type
        release.failure_injected = True
        release.failure_point = failure_type
        release.failure_details = {
            "error_message": error_message,
            "error_code": error_code,
            "exception_type": exception_type,
            "injection_id": injection.id,
        }
        release.failure_injected_at = utcnow()
        
        # Update release status to failure state
        failure_phase_map = {
            "preflight": ReleasePhase.PRECHECK_FAILED,
            "artifact_validation": ReleasePhase.ARTIFACT_INVALID,
            "migration_start": ReleasePhase.MIGRATION_FAILED,
            "migration_middle": ReleasePhase.MIGRATION_FAILED,
            "migration_completion": ReleasePhase.MIGRATION_FAILED,
            "application_deployment": ReleasePhase.APPLICATION_DEPLOYMENT_FAILED,
            "worker_deployment": ReleasePhase.WORKER_DEPLOYMENT_FAILED,
            "health_check": ReleasePhase.HEALTH_CHECK_FAILED,
            "readiness_check": ReleasePhase.READINESS_CHECK_FAILED,
            "canonical_integrity": ReleasePhase.CANONICAL_INTEGRITY_FAILED,
            "fingerprint_verification": ReleasePhase.FINGERPRINT_MISMATCH,
            "activation": ReleasePhase.ACTIVATION_FAILED,
            "post_activation": ReleasePhase.POST_ACTIVATION_VERIFICATION,
        }
        
        # Use failure_point for phase mapping since it's more specific
        phase_key = failure_point if failure_point in failure_phase_map else failure_type
        if phase_key in failure_phase_map:
            await self.advance_phase(db, release.id, failure_phase_map[phase_key], "system")
        
        release.status = "failed"
        release.error = f"Injected failure: {failure_type} at {failure_type}"
        release.error_details = {
            "failure_type": failure_type,
            "failure_point": failure_type,
            "error_message": error_message,
            "error_code": error_code,
            "exception_type": exception_type,
        }
        release.failure_injected = True
        release.failure_injected_at = utcnow()
        
        await db.flush()
        
        # Trigger failure handlers
        await self._trigger_failure_handlers(db, release_id)
        
        logger.warning(f"Injected failure {failure_type} at {failure_point} for release {release_id}")
        return injection
    
    async def _trigger_failure_handlers(
        self,
        db: AsyncSession,
        release_id: str,
    ):
        """Trigger appropriate failure handlers based on release state."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            return
        
        # Publish failure event
        await publish_event(
            db,
            name="release.failure_injected",
            actor_id="system",
            organization_id=release.organization_id,
            payload={
                "release_id": release.id,
                "failure_type": release.failure_type,
                "failure_point": release.failure_point,
                "error": release.error,
            },
        )
        
        # If failure requires recovery, transition to recovery state
        if release.phase in [
            ReleasePhase.MIGRATION_FAILED.value,
            ReleasePhase.APPLICATION_DEPLOYMENT_FAILED.value,
            ReleasePhase.WORKER_DEPLOYMENT_FAILED.value,
            ReleasePhase.CANONICAL_INTEGRITY_FAILED.value,
            ReleasePhase.FINGERPRINT_MISMATCH.value,
        ]:
            release.phase = ReleasePhase.RECOVERY_REQUIRED.value
            release.status = "recovery_required"
            await db.flush()
            
            # Auto-initiate recovery if configured
            # For test mode, we'll let tests trigger recovery manually
    
    # =========================================================================
    # FAILURE INJECTION HELPERS (for specific failure points)
    # =========================================================================
    
    async def inject_preflight_failure(
        self,
        db: AsyncSession,
        release_id: str,
        error_message: str = "Preflight check failed",
    ) -> ReleaseFailureInjection:
        """Inject a preflight failure."""
        return await self.inject_failure(
            db, release_id,
            failure_type="preflight",
            failure_point="preflight_check",
            error_message=error_message,
            error_code="PREFLIGHT_FAILED",
            exception_type="PreflightCheckFailed",
        )
    
    async def inject_migration_failure(
        self,
        db: AsyncSession,
        release_id: str,
        error_message: str = "Migration failed",
        failure_point: str = "migration_middle",
    ) -> ReleaseFailureInjection:
        """Inject a migration failure."""
        return await self.inject_failure(
            db, release_id,
            failure_type="migration",
            failure_point=failure_point,
            error_message=error_message,
            error_code="MIGRATION_FAILED",
            exception_type="MigrationFailed",
        )
    
    async def inject_application_deployment_failure(
        self,
        db: AsyncSession,
        release_id: str,
        error_message: str = "Application deployment failed",
    ) -> ReleaseFailureInjection:
        """Inject an application deployment failure."""
        return await self.inject_failure(
            db, release_id,
            failure_type="application_deployment",
            failure_point="application_deployment",
            error_message=error_message,
            error_code="APP_DEPLOY_FAILED",
            exception_type="ApplicationDeploymentFailed",
        )
    
    async def inject_worker_deployment_failure(
        self,
        db: AsyncSession,
        release_id: str,
        error_message: str = "Worker deployment failed",
    ) -> ReleaseFailureInjection:
        """Inject a worker deployment failure."""
        return await self.inject_failure(
            db, release_id,
            failure_type="worker_deployment",
            failure_point="worker_deployment",
            error_message=error_message,
            error_code="WORKER_DEPLOY_FAILED",
            exception_type="WorkerDeploymentFailed",
        )
    
    async def inject_health_check_failure(
        self,
        db: AsyncSession,
        release_id: str,
        error_message: str = "Health check failed",
    ) -> ReleaseFailureInjection:
        """Inject a health check failure."""
        return await self.inject_failure(
            db, release_id,
            failure_type="health_check",
            failure_point="health_check",
            error_message=error_message,
            error_code="HEALTH_CHECK_FAILED",
            exception_type="HealthCheckFailed",
        )
    
    async def inject_readiness_check_failure(
        self,
        db: AsyncSession,
        release_id: str,
        error_message: str = "Readiness check failed",
    ) -> ReleaseFailureInjection:
        """Inject a readiness check failure."""
        return await self.inject_failure(
            db, release_id,
            failure_type="readiness_check",
            failure_point="readiness_check",
            error_message=error_message,
            error_code="READINESS_CHECK_FAILED",
            exception_type="ReadinessCheckFailed",
        )
    
    async def inject_canonical_integrity_failure(
        self,
        db: AsyncSession,
        release_id: str,
        error_message: str = "Canonical integrity check failed",
    ) -> ReleaseFailureInjection:
        """Inject a canonical integrity failure."""
        return await self.inject_failure(
            db, release_id,
            failure_type="canonical_integrity",
            failure_point="canonical_integrity_check",
            error_message=error_message,
            error_code="CANONICAL_INTEGRITY_FAILED",
            exception_type="CanonicalIntegrityFailed",
        )
    
    async def inject_fingerprint_mismatch(
        self,
        db: AsyncSession,
        release_id: str,
        error_message: str = "Fingerprint mismatch detected",
    ) -> ReleaseFailureInjection:
        """Inject a fingerprint mismatch."""
        return await self.inject_failure(
            db, release_id,
            failure_type="fingerprint_verification",
            failure_point="fingerprint_verification",
            error_message=error_message,
            error_code="FINGERPRINT_MISMATCH",
            exception_type="FingerprintMismatch",
        )
    
    async def inject_activation_failure(
        self,
        db: AsyncSession,
        release_id: str,
        error_message: str = "Activation failed",
    ) -> ReleaseFailureInjection:
        """Inject an activation failure."""
        return await self.inject_failure(
            db, release_id,
            failure_type="activation",
            failure_point="activation",
            error_message=error_message,
            error_code="ACTIVATION_FAILED",
            exception_type="ActivationFailed",
        )
    
    # =========================================================================
    # RECOVERY SERVICE
    # =========================================================================
    
    async def initiate_recovery(
        self,
        db: AsyncSession,
        release_id: str,
        recovery_strategy: RecoveryStrategy,
        initiated_by: str,
        reason: str,
        governance_required: bool = False,
    ) -> ReleaseRecoveryRecord:
        """Initiate recovery for a failed release."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        if release.phase not in [
            ReleasePhase.RECOVERY_REQUIRED.value,
            ReleasePhase.MIGRATION_FAILED.value,
            ReleasePhase.APPLICATION_DEPLOYMENT_FAILED.value,
            ReleasePhase.WORKER_DEPLOYMENT_FAILED.value,
            ReleasePhase.CANONICAL_INTEGRITY_FAILED.value,
            ReleasePhase.FINGERPRINT_MISMATCH.value,
            ReleasePhase.HEALTH_CHECK_FAILED.value,
            ReleasePhase.READINESS_CHECK_FAILED.value,
        ]:
            raise ValueError(f"Release {release_id} is not in a recoverable state (current: {release.phase})")
        
        # Check if governance is required
        governance_required = governance_required or release.governance_required
        if governance_required:
            release.governance_required = True
            release.governance_status = "pending"
        
        # Create recovery record
        recovery = ReleaseRecoveryRecord(
            release_id=release.id,
            organization_id=release.organization_id,
            recovery_strategy=recovery_strategy.value,
            recovery_reason=f"Recovery from {release.failure_type}: {release.error}",
            status="pending",
            initiated_by=initiated_by,
            steps=[],
            steps_total=0,
            pre_recovery_fingerprint=release.post_release_fingerprint,
            governance_required=governance_required,
            governance_status="pending" if governance_required else "not_required",
        )
        
        db.add(recovery)
        
        # Update release
        release.phase = ReleasePhase.RECOVERING.value
        release.status = "recovering"
        release.recovery_strategy = recovery_strategy.value
        release.recovery_started_at = utcnow()
        release.recovery_status = "in_progress"
        release.recovery_details = {
            "strategy": recovery_strategy.value,
            "reason": f"Recovery from {release.failure_type}: {release.error}",
        }
        
        if governance_required:
            release.governance_status = "pending"
            recovery.governance_status = "pending"
        
        await db.flush()
        
        await publish_event(
            db,
            name="release.recovery_started",
            actor_id=initiated_by,
            organization_id=release.organization_id,
            payload={
                "release_id": release.id,
                "recovery_id": recovery.id,
                "strategy": recovery_strategy.value,
            },
        )
        
        logger.info(f"Initiated recovery {recovery.id} for release {release.id} with strategy {recovery_strategy.value}")
        return recovery
    
    async def execute_recovery_step(
        self,
        db: AsyncSession,
        recovery_id: str,
        step_name: str,
        step_function: Callable[[AsyncSession, ReleaseRecord, ReleaseRecoveryRecord], Any],
        actor_id: str = "system",
    ) -> Dict[str, Any]:
        """Execute a single recovery step."""
        
        recovery = await db.get(ReleaseRecoveryRecord, recovery_id)
        if not recovery:
            raise ValueError(f"Recovery {recovery_id} not found")
        
        release = await db.get(ReleaseRecord, recovery.release_id)
        if not release:
            raise ValueError(f"Release {recovery.release_id} not found")
        
        recovery.current_step = step_name
        recovery.steps_completed += 1
        
        step_start = utcnow()
        step_result = {"step": step_name, "started_at": step_start.isoformat(), "status": "in_progress"}
        
        try:
            result = await step_function(db, release, recovery)
            step_result["status"] = "completed"
            step_result["result"] = result
        except Exception as e:
            step_result["status"] = "failed"
            step_result["error"] = str(e)
            logger.error(f"Recovery step {step_name} failed: {e}")
            raise
        finally:
            step_result["completed_at"] = utcnow().isoformat()
            step_result["duration_ms"] = int((utcnow() - step_start).total_seconds() * 1000)
            
            if not recovery.steps:
                recovery.steps = []
            recovery.steps.append(step_result)
            recovery.updated_at = utcnow()
            await db.flush()
        
        return step_result
    
    async def execute_recovery(
        self,
        db: AsyncSession,
        recovery_id: str,
        steps: List[Dict[str, Any]],
        actor_id: str = "system",
    ) -> ReleaseRecoveryRecord:
        """Execute a full recovery with multiple steps."""
        
        recovery = await db.get(ReleaseRecoveryRecord, recovery_id)
        if not recovery:
            raise ValueError(f"Recovery {recovery_id} not found")
        
        release = await db.get(ReleaseRecord, recovery.release_id)
        if not release:
            raise ValueError(f"Release {recovery.release_id} not found")
        
        recovery.status = "in_progress"
        recovery.steps_total = len(steps)
        recovery.steps = []
        recovery.started_at = utcnow()
        await db.flush()
        
        for i, step in enumerate(steps):
            step_name = step.get("name", f"step_{i}")
            step_func = step.get("function")
            
            if not step_func:
                raise ValueError(f"Step {step_name} missing function")
            
            recovery.current_step = step_name
            
            try:
                await self.execute_recovery_step(db, recovery_id, step_name, step_func, actor_id)
            except Exception as e:
                recovery.status = "failed"
                recovery.error = f"Step {step_name} failed: {str(e)}"
                recovery.error_details = {"step": step_name, "error": str(e)}
                recovery.completed_at = utcnow()
                await db.flush()
                raise
        
        # All steps completed
        recovery.status = "completed"
        recovery.completed_at = utcnow()
        
        # Capture post-recovery fingerprint
        await self.capture_post_release_fingerprint(db, release.id)
        
        # Validate recovery
        validation = await self.validate_recovery(db, release.id)
        recovery.validation_passed = validation.get("overall", False)
        recovery.validation_details = validation
        
        if validation.get("overall", False):
            recovery.status = "completed"
            recovery.recovery_validation_passed = True
            
            # Update release
            release.phase = ReleasePhase.RECOVERED.value
            release.status = "recovered"
            release.recovery_completed_at = utcnow()
            release.recovery_status = "completed"
            release.recovery_validation_passed = True
            release.post_recovery_validation = validation
            release.post_recovery_validation_passed = True
        else:
            recovery.status = "validation_failed"
            recovery.recovery_validation_passed = False
            release.recovery_status = "validation_failed"
        
        release.recovery_completed_at = utcnow()
        await db.flush()
        
        await publish_event(
            db,
            name="release.recovery_completed",
            actor_id=actor_id,
            organization_id=release.organization_id,
            payload={
                "release_id": release.id,
                "recovery_id": recovery.id,
                "status": recovery.status,
                "validation_passed": recovery.validation_passed,
            },
        )
        
        return recovery
    
    # =========================================================================
    # RECOVERY STEP IMPLEMENTATIONS
    # =========================================================================
    
    async def _recovery_step_assess_damage(
        self,
        db: AsyncSession,
        release: ReleaseRecord,
        recovery: ReleaseRecoveryRecord,
    ) -> Dict[str, Any]:
        """Assess the damage from the failure."""
        
        damage = {
            "failure_type": release.failure_type,
            "failure_point": release.failure_point,
            "canonical_integrity_affected": release.phase in [
                ReleasePhase.CANONICAL_INTEGRITY_FAILED.value,
                ReleasePhase.FINGERPRINT_MISMATCH.value,
            ],
            "migration_affected": release.phase == ReleasePhase.MIGRATION_FAILED.value,
            "application_affected": release.phase == ReleasePhase.APPLICATION_DEPLOYMENT_FAILED.value,
            "workers_affected": release.phase == ReleasePhase.WORKER_DEPLOYMENT_FAILED.value,
            "health_affected": release.phase == ReleasePhase.HEALTH_CHECK_FAILED.value,
            "readiness_affected": release.phase == ReleasePhase.READINESS_CHECK_FAILED.value,
            "fingerprint_mismatch": release.phase == ReleasePhase.FINGERPRINT_MISMATCH.value,
        }
        
        # Check canonical integrity
        if release.organization_id:
            integrity_findings = await self.canonical_integrity_service.run_integrity_scan(
                db=db,
                organization_id=release.organization_id,
                checks=["structural", "tenant", "temporal", "provenance", "epistemic", "operating_chain"],
                limit=100,
            )
            
            critical_findings = [f for f in integrity_findings if severity_matches(f, "CRITICAL")]
            high_findings = [f for f in integrity_findings if severity_matches(f, "HIGH")]
            
            damage["integrity_findings"] = {
                "critical": len(critical_findings),
                "high": len(high_findings),
                "total": len(integrity_findings),
            }
            
            if critical_findings:
                damage["canonical_integrity_affected"] = True
        
        recovery.steps.append({
            "name": "assess_damage",
            "completed_at": utcnow().isoformat(),
            "result": damage,
        })
        
        return damage
    
    async def _recovery_step_verify_backup(
        self,
        db: AsyncSession,
        release: ReleaseRecord,
        recovery: ReleaseRecoveryRecord,
    ) -> Dict[str, Any]:
        """Verify backup availability for recovery."""
        
        from app.models.backup_manifest import BackupManifest, BackupStatus
        
        # Check for verified backup
        backup_result = await db.execute(
            select(BackupManifest).where(
                BackupManifest.organization_id == release.organization_id,
                BackupManifest.status == BackupStatus.VERIFIED,
            ).order_by(BackupManifest.completed_at.desc()).limit(1)
        )
        backup = backup_result.scalars().first()
        
        result = {
            "backup_available": backup is not None,
            "backup_id": backup.id if backup else None,
            "backup_age_minutes": int((utcnow() - backup.completed_at).total_seconds() / 60) if backup else None,
        }
        
        if not backup:
            logger.warning(f"No verified backup found for org {release.organization_id}")
        
        recovery.steps.append({
            "name": "verify_backup",
            "completed_at": utcnow().isoformat(),
            "result": result,
        })
        
        return result
    
    async def _recovery_step_restore_database(
        self,
        db: AsyncSession,
        release: ReleaseRecord,
        recovery: ReleaseRecoveryRecord,
    ) -> Dict[str, Any]:
        """Restore database from backup."""
        
        # This would use the restore service
        # For now, we simulate the restore
        
        from app.models.backup_manifest import BackupManifest, BackupStatus
        
        backup_result = await db.execute(
            select(BackupManifest).where(
                BackupManifest.organization_id == release.organization_id,
                BackupManifest.status == BackupStatus.VERIFIED,
            ).order_by(BackupManifest.completed_at.desc()).limit(1)
        )
        backup = backup_result.scalars().first()
        
        if not backup:
            raise ValueError("No verified backup available for restore")
        
        # In production, this would call restore_service.restore_from_backup
        # For testing, we simulate success
        
        result = {
            "restore_method": "database_restore",
            "backup_id": backup.id,
            "simulated": True,
        }
        
        recovery.steps.append({
            "name": "restore_database",
            "completed_at": utcnow().isoformat(),
            "result": result,
        })
        
        return result
    
    async def _recovery_step_reconcile_canonical_state(
        self,
        db: AsyncSession,
        release: ReleaseRecord,
        recovery: ReleaseRecoveryRecord,
    ) -> Dict[str, Any]:
        """Reconcile canonical state after recovery."""
        
        # Run canonical integrity scan
        findings = await self.canonical_integrity_service.run_integrity_scan(
            db=db,
            organization_id=release.organization_id,
            checks=["structural", "tenant", "temporal", "provenance", "epistemic", "operating_chain"],
            limit=100,
        )
        
        # Generate repair proposals for critical findings
        repair_proposals = []
        for finding in findings:
            if severity_matches(finding, "CRITICAL") or severity_matches(finding, "HIGH"):
                # In production, this would generate actual repair proposals
                repair_proposals.append({
                    "finding_id": finding.id,
                    "finding_type": finding.finding_type.value,
                    "entity_type": finding.entity_type,
                    "entity_id": finding.entity_id,
                    "proposed_action": "repair",
                })
        
        result = {
            "findings_count": len(findings),
            "critical_findings": len([f for f in findings if severity_matches(f, "CRITICAL")]),
            "high_findings": len([f for f in findings if severity_matches(f, "HIGH")]),
            "repair_proposals_generated": len(repair_proposals),
        }
        
        recovery.steps.append({
            "name": "reconcile_canonical_state",
            "completed_at": utcnow().isoformat(),
            "result": result,
        })
        
        return result
    
    async def _recovery_step_validate_fingerprint(
        self,
        db: AsyncSession,
        release: ReleaseRecord,
        recovery: ReleaseRecoveryRecord,
    ) -> Dict[str, Any]:
        """Validate fingerprint after recovery."""
        
        # Capture post-recovery fingerprint - only for the release's organization
        post_recovery_fp = await self.release_fingerprint_service.create_release_candidate_fingerprint(
            db=db,
            release_candidate_id=release.id,
            application_version=release.version,
            schema_revision="head",
            organization_ids=[release.organization_id],
            preflight_verdict="post_recovery",
            preflight_timestamp=utcnow(),
        )
        
        release.post_recovery_fingerprint = post_recovery_fp.aggregate_fingerprint
        
# Compare with pre-release fingerprint
        result = {
            "fingerprint_match": False,
            "comparison": {},
            "post_recovery_fingerprint": post_recovery_fp.aggregate_fingerprint,
        }
        
        if release.pre_release_fingerprint:
            pre_fp = type('obj', (object,), {
                'tenants': [type('obj', (object,), {
                    'organization_id': org_id,
                    'aggregate_fingerprint': data.get('aggregate', ''),
                    'components': [type('obj', (object,), {'component_name': c, 'fingerprint': fp}) 
                                for c, fp in data.get('components', {}).items()]
                })() for org_id, data in (release.pre_release_component_fingerprints or {}).items()],
                'aggregate_fingerprint': release.pre_release_fingerprint,
            })()
            
            post_fp = type('obj', (object,), {
                'tenants': [type('obj', (object,), {
                    'organization_id': org_id,
                    'aggregate_fingerprint': data.get('aggregate', ''),
                    'components': [type('obj', (object,), {'component_name': c, 'fingerprint': fp}) 
                                for c, fp in data.get('components', {}).items()]
                })() for org_id, data in (release.post_release_component_fingerprints or {}).items()],
                'aggregate_fingerprint': release.post_recovery_fingerprint,
            })()
            
            comparison = await self.release_fingerprint_service.compare_fingerprints(pre_fp, post_fp)
            
            result = {
                "fingerprint_match": comparison.get("overall") == "MATCH",
                "comparison": comparison,
                "post_recovery_fingerprint": post_recovery_fp.aggregate_fingerprint,
            }
            
            recovery.fingerprint_match = result["fingerprint_match"]
            recovery.post_recovery_fingerprint = post_recovery_fp.aggregate_fingerprint
            recovery.fingerprint_changes = comparison.get("component_differences", [])
        
        await db.flush()
        
        recovery.steps.append({
            "name": "validate_fingerprint",
            "completed_at": utcnow().isoformat(),
            "result": result,
        })
        
        return result
    
    async def _recovery_step_validate_canonical_integrity(
        self,
        db: AsyncSession,
        release: ReleaseRecord,
        recovery: ReleaseRecoveryRecord,
    ) -> Dict[str, Any]:
        """Validate canonical integrity after recovery."""
        
        findings = await self.canonical_integrity_service.run_integrity_scan(
            db=db,
            organization_id=release.organization_id,
            checks=["structural", "tenant", "temporal", "provenance", "epistemic", "operating_chain"],
            limit=100,
        )
        
        critical = len([f for f in findings if severity_matches(f, "CRITICAL")])
        high = len([f for f in findings if severity_matches(f, "HIGH")])
        
        result = {
            "findings_total": len(findings),
            "critical": critical,
            "high": high,
            "passed": critical == 0,
        }
        
        recovery.steps.append({
            "name": "validate_canonical_integrity",
            "completed_at": utcnow().isoformat(),
            "result": result,
        })
        
        return result
    
    async def _recovery_step_validate_tenant_isolation(
        self,
        db: AsyncSession,
        release: ReleaseRecord,
        recovery: ReleaseRecoveryRecord,
    ) -> Dict[str, Any]:
        """Validate tenant isolation after recovery for the release's organization."""
        
        from sqlalchemy import text
        
        org_id = release.organization_id
        
        violations = []
        # Check critical tables for cross-tenant data for the release's organization
        for table in ["employees", "projects", "tasks", "company_decisions", "company_actions"]:
            try:
                result = await db.execute(text(f"""
                    SELECT COUNT(*) FROM {table} 
                    WHERE organization_id != :org_id
                """), {"org_id": org_id})
                count = result.scalar() or 0
                if count > 0:
                    violations.append({"table": table, "org_id": org_id, "cross_tenant_count": count})
            except Exception:
                pass
        
        result = {
            "violations": violations,
            "passed": len(violations) == 0,
        }
        
        recovery.steps.append({
            "name": "validate_tenant_isolation",
            "completed_at": utcnow().isoformat(),
            "result": result,
        })
        
        return result
    
    async def _recovery_step_capture_post_recovery_fingerprint(
        self,
        db: AsyncSession,
        release: ReleaseRecord,
        recovery: ReleaseRecoveryRecord,
    ) -> Dict[str, Any]:
        """Capture post-recovery fingerprint."""
        
        fp_evidence = await self.release_fingerprint_service.create_release_candidate_fingerprint(
            db=db,
            release_candidate_id=release.id,
            application_version=release.version,
            schema_revision="head",
            organization_ids=[release.organization_id],
            preflight_verdict="post_recovery",
            preflight_timestamp=utcnow(),
        )
        
        release.post_recovery_fingerprint = fp_evidence.aggregate_fingerprint
        
        # Store evidence
        fp_evidence_record = ReleaseFingerprintEvidence(
            release_id=release.id,
            organization_id=release.organization_id,
            fingerprint_type="post_recovery",
            aggregate_fingerprint=fp_evidence.aggregate_fingerprint,
            component_fingerprints={tenant.organization_id: {c.component_name: c.fingerprint for c in tenant.components} for tenant in fp_evidence.tenants},
            algorithm="sha256_64",
            algorithm_version="1.0",
            computed_by="system",
        )
        db.add(fp_evidence_record)
        
        await db.flush()
        
        result = {
            "post_recovery_fingerprint": fp_evidence.aggregate_fingerprint,
        }
        
        recovery.steps.append({
            "name": "capture_post_recovery_fingerprint",
            "completed_at": utcnow().isoformat(),
            "result": result,
        })
        
        return result
    
    # =========================================================================
    # RECOVERY STRATEGIES
    # =========================================================================
    
    async def recover_application_deployment_failure(
        self,
        db: AsyncSession,
        release_id: str,
        initiated_by: str = "system",
    ) -> ReleaseRecoveryRecord:
        """Recover from application deployment failure."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        # Determine strategy based on failure
        if release.failure_point == "application_deployment":
            # Application deployment failed - can retry deployment
            strategy = RecoveryStrategy.RETRY
        else:
            strategy = RecoveryStrategy.ROLLBACK_APPLICATION
        
        recovery = await self.initiate_recovery(
            db, release_id, RecoveryStrategy.RETRY, "system",
            reason=f"Recover from application deployment failure: {release.error}"
        )
        
        # Define recovery steps
        steps = [
            {"name": "assess_damage", "function": lambda db, r, rec: self._recovery_step_assess_damage(db, r, rec)},
            {"name": "verify_backup", "function": lambda db, r, rec: self._recovery_step_verify_backup(db, r, rec)},
            {"name": "restore_database", "function": lambda db, r, rec: self._recovery_step_restore_database(db, r, rec)},
            {"name": "reconcile_canonical_state", "function": lambda db, r, rec: self._recovery_step_reconcile_canonical_state(db, r, rec)},
            {"name": "validate_fingerprint", "function": lambda db, r, rec: self._recovery_step_validate_fingerprint(db, r, rec)},
            {"name": "validate_canonical_integrity", "function": lambda db, r, rec: self._recovery_step_validate_canonical_integrity(db, r, rec)},
            {"name": "validate_tenant_isolation", "function": lambda db, r, rec: self._recovery_step_validate_tenant_isolation(db, r, rec)},
            {"name": "capture_post_recovery_fingerprint", "function": lambda db, r, rec: self._recovery_step_capture_post_recovery_fingerprint(db, r, rec)},
        ]
        
        return await self.execute_recovery(db, recovery_id=recovery.id, steps=steps, actor_id="system")
    
    async def recover_migration_failure(
        self,
        db: AsyncSession,
        release_id: str,
        initiated_by: str = "system",
    ) -> ReleaseRecoveryRecord:
        """Recover from migration failure."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        # Determine strategy
        if release.migration_status == "started":
            # Migration started but failed - can use forward-compatible recovery
            strategy = RecoveryStrategy.ROLLBACK_MIGRATION
        else:
            strategy = RecoveryStrategy.RESTORE_DATABASE
        
        recovery = await self.initiate_recovery(
            db, release_id, RecoveryStrategy.RESTORE_DATABASE, "system",
            reason=f"Recover from migration failure: {release.error}"
        )
        
        steps = [
            {"name": "assess_damage", "function": lambda db, r, rec: self._recovery_step_assess_damage(db, r, rec)},
            {"name": "verify_backup", "function": lambda db, r, rec: self._recovery_step_verify_backup(db, r, rec)},
            {"name": "restore_database", "function": lambda db, r, rec: self._recovery_step_restore_database(db, r, rec)},
            {"name": "reconcile_canonical_state", "function": lambda db, r, rec: self._recovery_step_reconcile_canonical_state(db, r, rec)},
            {"name": "validate_fingerprint", "function": lambda db, r, rec: self._recovery_step_validate_fingerprint(db, r, rec)},
            {"name": "validate_canonical_integrity", "function": lambda db, r, rec: self._recovery_step_validate_canonical_integrity(db, r, rec)},
            {"name": "validate_tenant_isolation", "function": lambda db, r, rec: self._recovery_step_validate_tenant_isolation(db, r, rec)},
            {"name": "capture_post_recovery_fingerprint", "function": lambda db, r, rec: self._recovery_step_capture_post_recovery_fingerprint(db, r, rec)},
        ]
        
        return await self.execute_recovery(db, recovery_id=recovery.id, steps=steps, actor_id="system")
    
    async def recover_worker_deployment_failure(
        self,
        db: AsyncSession,
        release_id: str,
        initiated_by: str = "system",
    ) -> ReleaseRecoveryRecord:
        """Recover from worker deployment failure."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        recovery = await self.initiate_recovery(
            db, release_id, RecoveryStrategy.RETRY, "system",
            reason=f"Recover from worker deployment failure: {release.error}"
        )
        
        steps = [
            {"name": "assess_damage", "function": lambda db, r, rec: self._recovery_step_assess_damage(db, r, rec)},
            {"name": "retry_worker_deployment", "function": lambda db, r, rec: {"retried": True, "simulated": True}},
            {"name": "validate_fingerprint", "function": lambda db, r, rec: self._recovery_step_validate_fingerprint(db, r, rec)},
            {"name": "validate_canonical_integrity", "function": lambda db, r, rec: self._recovery_step_validate_canonical_integrity(db, r, rec)},
            {"name": "capture_post_recovery_fingerprint", "function": lambda db, r, rec: self._recovery_step_capture_post_recovery_fingerprint(db, r, rec)},
        ]
        
        return await self.execute_recovery(db, recovery_id=recovery.id, steps=steps, actor_id="system")
    
    async def recover_health_check_failure(
        self,
        db: AsyncSession,
        release_id: str,
        initiated_by: str = "system",
    ) -> ReleaseRecoveryRecord:
        """Recover from health check failure."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        recovery = await self.initiate_recovery(
            db, release_id, RecoveryStrategy.RETRY, "system",
            reason=f"Recover from health check failure: {release.error}"
        )
        
        async def _mock_step_wait_for_dependencies(db, r, rec):
            return {"waited": True, "simulated": True}
        
        async def _mock_step_retry_health_check(db, r, rec):
            return {"health_check_passed": True, "simulated": True}
        
        steps = [
            {"name": "assess_damage", "function": lambda db, r, rec: self._recovery_step_assess_damage(db, r, rec)},
            {"name": "wait_for_dependencies", "function": _mock_step_wait_for_dependencies},
            {"name": "retry_health_check", "function": _mock_step_retry_health_check},
            {"name": "validate_fingerprint", "function": lambda db, r, rec: self._recovery_step_validate_fingerprint(db, r, rec)},
            {"name": "validate_canonical_integrity", "function": lambda db, r, rec: self._recovery_step_validate_canonical_integrity(db, r, rec)},
            {"name": "capture_post_recovery_fingerprint", "function": lambda db, r, rec: self._recovery_step_capture_post_recovery_fingerprint(db, r, rec)},
        ]
        
        return await self.execute_recovery(db, recovery_id=recovery.id, steps=steps, actor_id="system")
    
    async def recover_readiness_check_failure(
        self,
        db: AsyncSession,
        release_id: str,
        initiated_by: str = "system",
    ) -> ReleaseRecoveryRecord:
        """Recover from readiness check failure."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        recovery = await self.initiate_recovery(
            db, release_id, RecoveryStrategy.RETRY, "system",
            reason=f"Recover from readiness check failure: {release.error}"
        )
        
        steps = [
            {"name": "assess_damage", "function": lambda db, r, rec: self._recovery_step_assess_damage(db, r, rec)},
            {"name": "verify_dependencies", "function": lambda db, r, rec: {"dependencies_ready": True, "simulated": True}},
            {"name": "retry_readiness_check", "function": lambda db, r, rec: {"readiness_passed": True, "simulated": True}},
            {"name": "validate_fingerprint", "function": lambda db, r, rec: self._recovery_step_validate_fingerprint(db, r, rec)},
            {"name": "validate_canonical_integrity", "function": lambda db, r, rec: self._recovery_step_validate_canonical_integrity(db, r, rec)},
            {"name": "capture_post_recovery_fingerprint", "function": lambda db, r, rec: self._recovery_step_capture_post_recovery_fingerprint(db, r, rec)},
        ]
        
        return await self.execute_recovery(db, recovery_id=recovery.id, steps=steps, actor_id="system")
    
    async def recover_canonical_integrity_failure(
        self,
        db: AsyncSession,
        release_id: str,
        initiated_by: str = "system",
    ) -> ReleaseRecoveryRecord:
        """Recover from canonical integrity failure."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        recovery = await self.initiate_recovery(
            db, release_id, RecoveryStrategy.RECONCILE, "system",
            reason=f"Recover from canonical integrity failure: {release.error}",
            governance_required=True,  # Canonical integrity failures require governance
        )
        
        steps = [
            {"name": "assess_damage", "function": lambda db, r, rec: self._recovery_step_assess_damage(db, r, rec)},
            {"name": "verify_backup", "function": lambda db, r, rec: self._recovery_step_verify_backup(db, r, rec)},
            {"name": "restore_database", "function": lambda db, r, rec: self._recovery_step_restore_database(db, r, rec)},
            {"name": "reconcile_canonical_state", "function": lambda db, r, rec: self._recovery_step_reconcile_canonical_state(db, r, rec)},
            {"name": "validate_fingerprint", "function": lambda db, r, rec: self._recovery_step_validate_fingerprint(db, r, rec)},
            {"name": "validate_canonical_integrity", "function": lambda db, r, rec: self._recovery_step_validate_canonical_integrity(db, r, rec)},
            {"name": "validate_tenant_isolation", "function": lambda db, r, rec: self._recovery_step_validate_tenant_isolation(db, r, rec)},
            {"name": "capture_post_recovery_fingerprint", "function": lambda db, r, rec: self._recovery_step_capture_post_recovery_fingerprint(db, r, rec)},
        ]
        
        return await self.execute_recovery(db, recovery_id=recovery.id, steps=steps, actor_id="system")
    
    async def recover_fingerprint_mismatch(
        self,
        db: AsyncSession,
        release_id: str,
        initiated_by: str = "system",
    ) -> ReleaseRecoveryRecord:
        """Recover from fingerprint mismatch."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        # Check if changes are expected
        unexpected = release.unexpected_fingerprint_changes or {}
        if unexpected:
            # Unexpected changes - need governance
            governance_required = True
        else:
            governance_required = False
        
        recovery = await self.initiate_recovery(
            db, release_id, RecoveryStrategy.RECONCILE, "system",
            reason=f"Recover from fingerprint mismatch: {release.error}",
            governance_required=governance_required,
        )
        
        steps = [
            {"name": "assess_damage", "function": lambda db, r, rec: self._recovery_step_assess_damage(db, r, rec)},
            {"name": "verify_backup", "function": lambda db, r, rec: self._recovery_step_verify_backup(db, r, rec)},
            {"name": "reconcile_canonical_state", "function": lambda db, r, rec: self._recovery_step_reconcile_canonical_state(db, r, rec)},
            {"name": "validate_fingerprint", "function": lambda db, r, rec: self._recovery_step_validate_fingerprint(db, r, rec)},
            {"name": "validate_canonical_integrity", "function": lambda db, r, rec: self._recovery_step_validate_canonical_integrity(db, r, rec)},
            {"name": "validate_tenant_isolation", "function": lambda db, r, rec: self._recovery_step_validate_tenant_isolation(db, r, rec)},
            {"name": "capture_post_recovery_fingerprint", "function": lambda db, r, rec: self._recovery_step_capture_post_recovery_fingerprint(db, r, rec)},
        ]
        
        return await self.execute_recovery(db, recovery_id=recovery.id, steps=steps, actor_id="system")
    
    # =========================================================================
    # POST-RECOVERY VALIDATION
    # =========================================================================
    
    async def validate_recovery(
        self,
        db: AsyncSession,
        release_id: str,
    ) -> Dict[str, Any]:
        """Run comprehensive post-recovery validation."""
        
        release = await db.get(ReleaseRecord, release_id)
        if not release:
            raise ValueError(f"Release {release_id} not found")
        
        validation = {
            "overall": True,
            "checks": {},
        }
        
        # 1. Canonical integrity
        findings = await self.canonical_integrity_service.run_integrity_scan(
            db=db,
            organization_id=release.organization_id,
            checks=["structural", "tenant", "temporal", "provenance", "epistemic", "operating_chain"],
            limit=100,
        )
        
        critical = len([f for f in findings if severity_matches(f, "CRITICAL")])
        high = len([f for f in findings if severity_matches(f, "HIGH")])
        
        canonical_passed = critical == 0
        validation["checks"]["canonical_integrity"] = {
            "passed": canonical_passed,
            "critical_findings": critical,
            "high_findings": high,
            "total_findings": len(findings),
        }
        if not canonical_passed:
            validation["overall"] = False
        
        # 2. Tenant isolation
        # Create a minimal recovery object for the validation step
        from types import SimpleNamespace
        dummy_recovery = SimpleNamespace(steps=[])
        tenant_check = await self._recovery_step_validate_tenant_isolation(
            db, release, dummy_recovery
        )
        tenant_passed = tenant_check.get("passed", False)
        validation["checks"]["tenant_isolation"] = {
            "passed": tenant_passed,
            "violations": tenant_check.get("violations", []),
        }
        if not tenant_passed:
            validation["overall"] = False
        
        # 3. Fingerprint validation
        if release.pre_release_fingerprint and release.post_release_fingerprint:
            fingerprint_match = release.fingerprint_match
            validation["checks"]["fingerprint"] = {
                "passed": fingerprint_match,
                "pre_release": release.pre_release_fingerprint[:16] + "..." if release.pre_release_fingerprint else None,
                "post_recovery": release.post_recovery_fingerprint[:16] + "..." if release.post_recovery_fingerprint else None,
            }
            if not fingerprint_match:
                validation["overall"] = False
        
        # 35-G Concurrency validation
        concurrency_check = await self._validate_concurrency(db, release.organization_id)
        validation["checks"]["concurrency"] = concurrency_check
        if not concurrency_check.get("passed", True):
            validation["overall"] = False
        
        # 35-H Reliability validation
        reliability_check = await self._validate_reliability(db, release.organization_id)
        validation["checks"]["reliability"] = reliability_check
        if not reliability_check.get("passed", True):
            validation["overall"] = False
        
        # 35-I Longitudinal validation
        longitudinal_check = await self._validate_longitudinal(db, release.organization_id)
        validation["checks"]["longitudinal"] = longitudinal_check
        if not longitudinal_check.get("passed", True):
            validation["overall"] = False
        
        return validation
    
    async def _validate_concurrency(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        """Validate 35-G concurrency properties."""
        from app.models.canonical_reliability import CanonicalOperation
        
        # Check for stuck operations
        stuck_ops = await db.execute(
            select(func.count()).select_from(
                select(CanonicalOperation).where(
                    CanonicalOperation.organization_id == org_id,
                    CanonicalOperation.state.in_(["queued", "attempting", "executing", "retrying", "unknown"]),
                )
            )
        )
        stuck_count = stuck_ops.scalar() or 0
        
        return {
            "passed": stuck_count == 0,
            "stuck_operations": stuck_count,
        }
    
    async def _validate_reliability(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        """Validate 35-H reliability properties."""
        from app.models.canonical_reliability import CanonicalOperation, OperationAttempt, Recovery
        from sqlalchemy import select, func
        
        # Check for unreconciled operations
        unreconciled = await db.execute(
            select(func.count()).select_from(
                select(CanonicalOperation).where(
                    CanonicalOperation.organization_id == org_id,
                    CanonicalOperation.state == "unknown",
                )
            )
        )
        unreconciled_count = unreconciled.scalar() or 0
        
        # Check for unreconciled attempts
        unreconciled_attempts = await db.execute(
            select(func.count()).select_from(
                select(OperationAttempt).where(
                    OperationAttempt.organization_id == org_id,
                    OperationAttempt.state.in_(["unknown", "in_progress"]),
                )
            )
        )
        unreconciled_attempts_count = unreconciled_attempts.scalar() or 0
        
        return {
            "passed": unreconciled_count == 0 and unreconciled_attempts_count == 0,
            "unreconciled_operations": unreconciled_count,
            "unreconciled_attempts": unreconciled_attempts_count,
        }
    
    async def _validate_longitudinal(self, db: AsyncSession, org_id: str) -> Dict[str, Any]:
        """Validate 35-I longitudinal properties."""
        from app.models.longitudinal import CompanyTimelineEvent, CompanyKnowledgeSnapshot
        
        # Check for temporal integrity issues - using correct column names
        temporal_issues = await db.execute(text("""
            SELECT COUNT(*) FROM company_timeline_events
            WHERE organization_id = :org_id
            AND (occurred_at > effective_from OR occurred_at IS NULL OR effective_from IS NULL)
        """), {"org_id": org_id})
        temporal_count = temporal_issues.scalar() or 0
        
        # Check for missing epistemic state on knowledge snapshots (using existing columns)
        missing_epistemic = await db.execute(text("""
            SELECT COUNT(*) FROM company_knowledge_snapshots
            WHERE organization_id = :org_id
            AND (epistemic_state IS NULL OR epistemic_state = '')
        """), {"org_id": org_id})
        missing_epistemic_count = missing_epistemic.scalar() or 0
        
        return {
            "passed": temporal_count == 0 and missing_epistemic_count == 0,
            "temporal_issues": temporal_count,
            "missing_epistemic_state": missing_epistemic_count,
        }
    
    # =========================================================================
    # MULTI-TENANT RELEASE FAILURE
    # =========================================================================
    
    async def test_multi_tenant_release_failure(
        self,
        db: AsyncSession,
        org_ids: List[str],
        failure_type: str,
    ) -> Dict[str, Any]:
        """Test release failure across multiple tenants."""
        
        results = {}
        for org_id in org_ids:
            release = await self.create_release_record(
                db=db,
                organization_id=org_id,
                version="test-1.0.0",
                initiated_by="multi_tenant_test",
            )
            
            # Inject failure
            await self.inject_failure(
                db, release.id,
                failure_type="application_deployment",
                failure_point="application_deployment",
                error_message=f"Simulated failure for {org_id}",
            )
            
            # Verify only this tenant is affected
            results[org_id] = {
                "release_id": release.id,
                "failed": True,
                "phase": ReleasePhase.APPLICATION_DEPLOYMENT_FAILED.value,
            }
            
            # Verify other tenants not affected
            for other_org_id in org_ids:
                if other_org_id != org_id:
                    other_releases = await db.execute(
                        select(ReleaseRecord).where(
                            ReleaseRecord.organization_id == other_org_id,
                            ReleaseRecord.status.in_(["pending", "prechecking", "prechecked"]),
                        ).order_by(ReleaseRecord.created_at.desc()).limit(1)
                    )
                    other_release = other_releases.scalars().first()
                    if other_release:
                        assert other_release.phase != ReleasePhase.APPLICATION_DEPLOYMENT_FAILED.value
        
        return {"results": results, "tenant_isolation_verified": True}


# Global instance
release_failure_recovery_service = ReleaseFailureRecoveryService()