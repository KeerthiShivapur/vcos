"""Disaster Recovery Service — legacy DR lifecycle SIMULATION harness + failure injection.

Purpose (honest scope): this module is an in-memory simulation harness used by
tests and demos to exercise the *shape* of the DR lifecycle
(DISASTER_DETECTED -> RECOVERY_DECLARED -> ... -> POST_RECOVERY_VERIFICATION).
It does NOT perform real backups, restores, or recovery validation, and its
`execute_recovery`/`validate_recovery` results are explicitly marked
`simulated: true`.

The REAL recovery path is the Track A stack: recovery gates
(`app/services/recovery_gates.py`), isolated restore
(`app/services/isolated_restore.py`), and post-restore semantic validation
(`app/services/post_restore_validator.py` / `restore_service`).

Fail-closed contract: outside test/development contexts (APP_ENV in
{test, development} or VCOS_TEST_MODE=1), `execute_recovery` and
`validate_recovery` raise RuntimeError instead of claiming a recovery was
executed or validated.
"""

import hashlib
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum


SIMULATION_DISABLED_ERROR = (
    "Legacy disaster-recovery simulation is disabled outside test/development "
    "(set APP_ENV=test/development or VCOS_TEST_MODE=1); no recovery was "
    "executed - refusing to fabricate a result. Use the real recovery path "
    "(recovery_gates + isolated_restore) instead."
)


def simulation_permitted() -> bool:
    """True when the legacy simulation harness may run (test/development only)."""
    env = os.environ.get("APP_ENV", "").strip().lower()
    return env in ("test", "development") or os.environ.get("VCOS_TEST_MODE") == "1"

from sqlalchemy import select, func, text, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.core.config import get_settings
from app.core.timeutils import utcnow
from app.core.config import get_settings

from app.models.canonical_reliability import (
    CanonicalOperation,
    OperationAttempt,
    Recovery,
    Reconciliation,
    ExternalUnknownState,
    WorkerLease,
    OperationCheckpoint,
    CanonicalOperation,
    OperationAttempt,
    Recovery,
    Reconciliation,
    ExternalUnknownState,
    WorkerLease,
    OperationCheckpoint,
)
from app.models.longitudinal import (
    CompanyTimelineEvent,
    CompanyKnowledgeSnapshot,
    DecisionTimelineEvent,
    LearningTimelineEvent,
    OrganizationalTimelineEvent,
    MergerAcquisitionLineage,
    LongitudinalProvenance,
    EpistemicCalibrationEvent,
    CompanyMemorySnapshot,
    TemporalQueryLog,
    FutureSimulatorCalibration,
    LongitudinalIntegrityFinding,
    LongitudinalAdversarialTest,
    TenantHistoricalIsolation,
)
from app.intelligence.canonical_mutation import (
    canonical_mutation_boundary,
    canonical_create,
    canonical_update,
    canonical_transition,
    canonical_delete,
    validate_temporal_integrity,
    validate_provenance,
    validate_epistemic_integrity,
    validate_governance,
)
from app.intelligence.company_brain import CompanyBrain
import logging
from app.intelligence.canonical_digital_twin_service import CanonicalDigitalTwinService as DigitalTwin
from app.services.canonical_reliability_service import canonical_reliability_service

logger = logging.getLogger("vcos.disaster_recovery")


class DisasterType(str, Enum):
    """Types of disasters."""
    REGION_OUTAGE = "region_outage"
    DB_FAILOVER = "db_failover"
    REPLICA_PROMOTION = "replica_promotion"
    RECOVERY_TEST = "recovery_test"
    STORAGE_FALLBACK = "storage_fallback"
    DB_CORRUPTION = "db_corruption"
    CONNECTION_LOSS = "connection_loss"
    EXTERNAL_API_FAILURE = "external_api_failure"
    DEPLOYMENT_FAILURE = "deployment_failure"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_API_TIMEOUT = "external_api_timeout"
    EXTERNAL_API_500 = "external_http_500"
    EXTERNAL_RATE_LIMIT = "external_rate_limit"
    EXTERNAL_PARTIAL_RESPONSE = "external_partial_response"
    EXTERNAL_DUPLICATE_DELIVERY = "external_duplicate_delivery"
    EXTERNAL_OUT_OF_ORDER = "external_out_of_order"
    EXTERNAL_UNKNOWN_OUTCOME = "external_unknown_outcome"
    WORKER_CRASH = "worker_crash"


class DisasterSeverity(str, Enum):
    """Disaster severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DisasterStatus(str, Enum):
    """Disaster status states."""
    DETECTED = "detected"
    RECOVERY_DECLARED = "recovery_declared"
    RECOVERY_PLAN_SELECTED = "recovery_plan_selected"
    BACKUP_SELECTED = "backup_selected"
    RESTORING = "restoring"
    VALIDATING = "validating"
    READY = "ready"
    ACTIVATED = "activated"
    POST_RECOVERY_VERIFICATION = "post_recovery_verification"
    COMPLETED = "completed"
    FAILED = "failed"


class DRScenario(str, Enum):
    """Disaster recovery scenarios."""
    
    REGION_OUTAGE = "region_outage"
    DB_FAILOVER = "db_failover"
    REPLICA_PROMOTION = "replica_promotion"
    RECOVERY_TEST = "recovery_test"
    STORAGE_FALLBACK = "storage_fallback"
    DB_CORRUPTION = "db_corruption"
    CONNECTION_LOSS = "connection_loss"
    WORKER_CRASH = "worker_crash"
    MIGRATION_FAILURE = "migration_failure"
    REDIS_FAILURE = "redis_failure"
    OBJECT_STORAGE_FAILURE = "object_storage_failure"
    NETWORK_PARTITION = "network_partition"
    EXTERNAL_RATE_LIMIT = "external_rate_limit"
    EXTERNAL_PARTIAL_RESPONSE = "external_partial_response"
    EXTERNAL_DUPLICATE_DELIVERY = "external_duplicate_delivery"
    EXTERNAL_OUT_OF_ORDER = "external_out_of_order"
    EXTERNAL_UNKNOWN_OUTCOME = "external_unknown_outcome"


@dataclass
class DisasterEvent:
    """Disaster event record."""
    disaster_id: str
    disaster_type: DisasterType
    severity: DisasterSeverity
    status: DisasterStatus
    organization_id: str
    detected_at: datetime
    declared_at: Optional[datetime] = None
    recovery_plan: Optional[str] = None
    backup_id: Optional[str] = None
    affected_systems: List[str] = field(default_factory=list)
    affected_tenants: List[str] = field(default_factory=list)
    rpo_target_minutes: int = 15
    rto_target_minutes: int = 30
    actual_rpo_minutes: Optional[int] = None
    actual_rto_minutes: Optional[int] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)


@dataclass
class DRMetrics:
    """DR metrics for a disaster event."""
    disaster_id: str
    rpo_target_minutes: int
    rpo_actual_minutes: Optional[int] = None
    rto_target_minutes: int = 30
    rto_actual_minutes: Optional[int] = None
    backup_used: Optional[str] = None
    backup_age_minutes: Optional[int] = None
    data_loss_bytes: int = 0
    data_loss_records: int = 0
    recovery_success: bool = False
    recovery_time_seconds: Optional[float] = None
    validation_passed: bool = False
    validation_details: Dict[str, Any] = field(default_factory=dict)


class DisasterRecoveryService:
    """Legacy DR lifecycle SIMULATION service (test/development only).

    Real recovery is performed and validated by the Track A recovery-gate
    stack. This service fabricates plausible lifecycle transitions for tests;
    it fails closed outside test/development contexts.
    """

    def __init__(self):
        self.settings = get_settings()
        self._active_disasters: Dict[str, DisasterEvent] = {}
        self._failure_injectors: Dict[str, Any] = {}

    async def detect_disaster(
        self,
        db: AsyncSession,
        disaster_type: DisasterType,
        severity: DisasterSeverity,
        organization_id: str,
        affected_systems: List[str],
        affected_tenants: List[str],
        error: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> DisasterEvent:
        """Detect and declare a disaster."""
        disaster_id = f"dr-{uuid.uuid4().hex[:12]}"
        
        disaster = DisasterEvent(
            disaster_id=disaster_id,
            disaster_type=disaster_type,
            severity=severity,
            status=DisasterStatus.DETECTED,
            organization_id=organization_id,
            affected_systems=affected_systems,
            affected_tenants=affected_tenants,
            detected_at=utcnow(),
            error=error,
            metadata=metadata or {},
        )
        
        self._active_disasters[disaster_id] = disaster
        
        # Emit disaster detected event
        await self._emit_disaster_event(disaster, "disaster.detected")
        
        # Auto-declare recovery for high/critical severity
        if severity in (DisasterSeverity.HIGH, DisasterSeverity.CRITICAL):
            await self.declare_recovery(db, disaster_id)
        
        return disaster

    async def declare_recovery(
        self,
        db: AsyncSession,
        disaster_id: str,
        recovery_plan: Optional[str] = None,
    ) -> DisasterEvent:
        """Declare recovery for a disaster."""
        disaster = self._active_disasters.get(disaster_id)
        if not disaster:
            raise ValueError(f"Disaster {disaster_id} not found")
        
        disaster.status = DisasterStatus.RECOVERY_DECLARED
        disaster.declared_at = utcnow()
        disaster.recovery_plan = recovery_plan or "standard"
        
        await self._emit_disaster_event(disaster, "disaster.recovery_declared")
        
        # Select recovery plan
        await self.select_recovery_plan(db, disaster_id)
        
        return disaster

    async def select_recovery_plan(
        self,
        db: AsyncSession,
        disaster_id: str,
    ) -> str:
        """Select appropriate recovery plan based on disaster type."""
        disaster = self._active_disasters.get(disaster_id)
        if not disaster:
            raise ValueError(f"Disaster {disaster_id} not found")
        
        # Select recovery plan based on disaster type
        plans = {
            DisasterType.REGION_OUTAGE: "region_failover",
            DisasterType.DB_FAILOVER: "db_failover",
            DisasterType.REPLICA_PROMOTION: "replica_promotion",
            DisasterType.DB_CORRUPTION: "db_restore",
            DisasterType.CONNECTION_LOSS: "connection_recovery",
            DisasterType.EXTERNAL_API_FAILURE: "external_reconciliation",
            DisasterType.MIGRATION_FAILURE: "migration_rollback",
            DisasterType.REDIS_FAILURE: "redis_failover",
            DisasterType.OBJECT_STORAGE_FAILURE: "storage_failover",
            DisasterType.NETWORK_PARTITION: "network_recovery",
            DisasterType.EXTERNAL_API_TIMEOUT: "external_timeout_recovery",
            DisasterType.EXTERNAL_API_500: "external_error_recovery",
            DisasterType.EXTERNAL_RATE_LIMIT: "rate_limit_recovery",
            DisasterType.EXTERNAL_PARTIAL_RESPONSE: "partial_response_recovery",
            DisasterType.EXTERNAL_DUPLICATE_DELIVERY: "duplicate_dedup",
            DisasterType.EXTERNAL_OUT_OF_ORDER: "ordering_recovery",
            DisasterType.EXTERNAL_UNKNOWN_OUTCOME: "unknown_reconciliation",
            DisasterType.WORKER_CRASH: "worker_recovery",
            DisasterType.DEPLOYMENT_FAILURE: "deployment_rollback",
        }
        
        plan = plans.get(disaster.disaster_type, "standard")
        disaster.recovery_plan = plan
        disaster.status = DisasterStatus.RECOVERY_PLAN_SELECTED
        disaster.updated_at = utcnow()
        
        return plan

    async def execute_recovery(
        self,
        db: AsyncSession,
        disaster_id: str,
    ) -> Dict[str, Any]:
        """Execute the (simulated) recovery plan for a disaster.

        Fail-closed: raises outside test/development; never claims a real
        recovery was executed. The result carries ``simulated: True``.
        """
        if not simulation_permitted():
            raise RuntimeError(SIMULATION_DISABLED_ERROR)

        disaster = self._active_disasters.get(disaster_id)
        if not disaster:
            raise ValueError(f"Disaster {disaster_id} not found")
        
        disaster.status = DisasterStatus.RESTORING
        disaster.updated_at = utcnow()
        
        start_time = utcnow()
        
        try:
            # Execute recovery based on plan
            if disaster.recovery_plan == "db_restore":
                result = await self._execute_db_restore(db, disaster)
            elif disaster.disaster_type == DisasterType.REGION_OUTAGE:
                result = await self._execute_region_failover(db, disaster)
            elif disaster.disaster_type == DisasterType.DB_FAILOVER:
                result = await self._execute_db_failover(db, disaster)
            elif disaster.disaster_type == DisasterType.REPLICA_PROMOTION:
                result = await self._execute_replica_promotion(db, disaster)
            elif disaster.disaster_type == DisasterType.EXTERNAL_API_FAILURE:
                result = await self._execute_external_reconciliation(db, disaster)
            elif disaster.disaster_type == DisasterType.WORKER_CRASH:
                result = await self._execute_worker_recovery(db, disaster)
            else:
                result = await self._execute_standard_recovery(db, disaster)
            
            disaster.actual_rto_minutes = int((utcnow() - disaster.detected_at).total_seconds() / 60)
            disaster.status = DisasterStatus.VALIDATING
            disaster.updated_at = utcnow()
            
            # Validate recovery
            validation = await self.validate_recovery(db, disaster)
            
            if validation["passed"]:
                disaster.status = DisasterStatus.COMPLETED
                disaster.actual_rto_minutes = int((utcnow() - disaster.detected_at).total_seconds() / 60)
            else:
                disaster.status = DisasterStatus.FAILED
                disaster.error = validation.get("error", "Validation failed")
            
            disaster.updated_at = utcnow()
            
            return {
                "disaster_id": disaster.disaster_id,
                "status": disaster.status.value,
                "actual_rto_minutes": disaster.actual_rto_minutes,
                "validation": validation,
                "simulated": True,
            }
            
        except Exception as e:
            disaster.status = DisasterStatus.FAILED
            disaster.error = str(e)
            disaster.updated_at = utcnow()
            raise
        finally:
            await self._emit_disaster_event(disaster, "disaster.recovery_completed")

    async def _execute_db_restore(
        self,
        db: AsyncSession,
        disaster: DisasterEvent,
    ) -> Dict[str, Any]:
        """Execute database restore from backup."""
        # This would use the restore service
        return {"success": True, "message": "Database restore completed"}

    async def _execute_region_failover(self, db: AsyncSession, disaster: DisasterEvent) -> Dict[str, Any]:
        """Execute region failover."""
        return {"success": True, "message": "Region failover completed"}

    async def _execute_db_failover(self, db: AsyncSession, disaster: DisasterEvent) -> Dict[str, Any]:
        """Execute database failover to replica."""
        # Promote replica
        return {"success": True, "message": "Database failover completed"}

    async def _execute_replica_promotion(self, db: AsyncSession, disaster: DisasterEvent) -> Dict[str, Any]:
        """Promote replica to primary."""
        return {"success": True, "message": "Replica promoted"}

    async def _execute_external_reconciliation(
        self, db: AsyncSession, disaster: DisasterEvent
    ) -> Dict[str, Any]:
        """Reconcile with external system after API failure."""
        return {"success": True, "message": "External reconciliation completed"}

    async def _execute_worker_recovery(
        self, db: AsyncSession, disaster: DisasterEvent
    ) -> Dict[str, Any]:
        """Recover from worker crash."""
        return {"success": True, "message": "Worker recovery completed"}

    async def _execute_standard_recovery(
        self, db: AsyncSession, disaster: DisasterEvent
    ) -> Dict[str, Any]:
        """Standard recovery for unknown disaster types."""
        return {"success": True, "message": "Standard recovery completed"}

    async def validate_recovery(
        self,
        db: AsyncSession,
        disaster: DisasterEvent,
    ) -> Dict[str, Any]:
        """SIMULATED recovery validation — not evidence of real recovery.

        This harness performs no real restore, so it cannot genuinely validate
        one. Outside test/development it fails closed. When permitted, the
        result is explicitly marked ``simulated: True``; real recovery
        validation lives in the Track A recovery-gate stack.
        """
        if not simulation_permitted():
            raise RuntimeError(SIMULATION_DISABLED_ERROR)

        return {
            "passed": True,
            "simulated": True,
            "message": (
                "SIMULATED validation (legacy harness) - not evidence of real "
                "recovery; real validation is performed by the recovery gates "
                "stack (recovery_gates + isolated_restore + post_restore_validator)"
            ),
            "details": {
                "canonical_integrity": True,
                "tenant_isolation": True,
                "temporal_integrity": True,
                "provenance": True,
                "epistemic_integrity": True,
            },
        }

    async def _emit_disaster_event(self, disaster: DisasterEvent, event_type: str):
        """Emit disaster event for observability."""
        logger.info(f"Disaster event: {event_type} for {disaster.disaster_id}")


class FailureInjector:
    """Deterministic failure injection for testing."""
    
    def __init__(self):
        self._active_failures: Dict[str, Dict[str, Any]] = {}
    
    def inject_database_failure(self, failure_type: str, **params) -> str:
        """Inject a database failure."""
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": failure_type,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_worker_crash(self, worker_id: str, **params) -> str:
        """Inject a worker crash."""
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "worker_crash",
            "worker_id": worker_id,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_timeout(self, external_system: str, **params) -> str:
        """Inject external system timeout."""
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_timeout",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_500(self, external_system: str, **params) -> str:
        """Inject external HTTP 500."""
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_500",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_rate_limit(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_rate_limit",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_partial_response(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_partial_response",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_out_of_order(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_out_of_order",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_unknown_outcome(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_unknown_outcome",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_duplicate_delivery(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_duplicate_delivery",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_out_of_order(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_out_of_order",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_unknown_outcome(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_unknown_outcome",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_duplicate_delivery(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_duplicate_delivery",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_out_of_order(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_out_of_order",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_unknown_outcome(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_unknown_outcome",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_duplicate_delivery(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_duplicate_delivery",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_out_of_order(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_out_of_order",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_unknown_outcome(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_unknown_outcome",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_duplicate_delivery(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_duplicate_delivery",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_out_of_order(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_out_of_order",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_unknown_outcome(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_unknown_outcome",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_duplicate_delivery(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_duplicate_delivery",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_out_of_order(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_out_of_order",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_unknown_outcome(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_unknown_outcome",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_duplicate_delivery(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_duplicate_delivery",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_out_of_order(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_out_of_order",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_external_unknown_outcome(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_unknown_outcome",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def inject_duplicate_delivery(self, external_system: str, **params) -> str:
        failure_id = f"fail-{uuid.uuid4().hex[:8]}"
        self._active_failures[failure_id] = {
            "type": "external_duplicate_delivery",
            "external_system": external_system,
            "params": params,
            "started_at": utcnow(),
            "active": True,
        }
        return failure_id
    
    def clear_failure(self, failure_id: str):
        """Clear an active failure injection."""
        if failure_id in self._active_failures:
            self._active_failures[failure_id]["active"] = False
            self._active_failures[failure_id]["ended_at"] = utcnow()
    
    def clear_all(self):
        """Clear all active failures."""
        for failure in self._active_failures.values():
            failure["active"] = False
            failure["ended_at"] = utcnow()
    
    def get_active_failures(self) -> List[Dict[str, Any]]:
        """Get all active failure injections."""
        return [
            {"id": fid, **finfo}
            for fid, finfo in self._active_failures.items()
            if finfo["active"]
        ]


# Global instances
disaster_recovery_service = DisasterRecoveryService()
failure_injector = FailureInjector()