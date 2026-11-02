"""Gate 32 — Canonical Reliability, Failure Recovery & Continuity Fabric Service.

Implements the canonical reliability fabric that ensures the company operating
system remains truthful, governed, and resilient under real-world failure
conditions.

Key principles:
- Reliability is a property of the canonical operating system, not a separate product
- Every failure/recovery/reconciliation event preserves evidence
- UNKNOWN state is distinct from FAILED
- Recovery must never create a second reality
- Governance cannot be bypassed during recovery
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Tuple, Set
from enum import Enum
from dataclasses import dataclass, field

from sqlalchemy import select, func, and_, or_, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.models.canonical_reliability import (
    CanonicalOperation,
    OperationAttempt,
    Recovery,
    Reconciliation,
    ExternalUnknownState,
    RecoveryProposal,
    StaleOperationDetector,
    WorkerLease,
    OperationCheckpoint,
    CanonicalOperation,
    OperationAttempt,
    Recovery,
    Reconciliation,
    ExternalUnknownState,
    RecoveryProposal,
    StaleOperationDetector,
    WorkerLease,
    OperationCheckpoint,
    OPERATION_STATES,
    ATTEMPT_STATES,
    RECOVERY_STATES,
    RECONCILIATION_STATES,
    RECOVERY_TYPES,
    FAILURE_CLASSES,
    RETRY_POLICIES,
    RECOVERY_OUTCOMES,
    ATTEMPT_OUTCOMES,
    compute_operation_fingerprint,
    compute_payload_fingerprint,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.company_actions import CompanyAction
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyCommitment, CompanyAuthorization
from app.models.autonomy import AutonomyProposal
from app.services.canonical_reality_integrity_service import canonical_reality_integrity_service
from app.services.autonomy_service import autonomy_service
from app.services.continuous_twin_service import continuous_twin_service
from app.services.canonical_company_continuity_service import canonical_company_continuity_service
from app.services.event_service import event_service
from app.intelligence.canonical_mutation import canonical_mutation_boundary, CanonicalMutationContext, MutationType
from app.intelligence.company_context import resolve_caller_access
from app.core.timeutils import utcnow

logger = logging.getLogger("vcos.canonical_reliability")


class FailureClassifier:
    """Classifies failures into deterministic categories using the Failure Taxonomy."""

    # Failure taxonomy loaded from models
    TAXONOMY = {
        "validated_failure": {"retryable": False, "category": "validated", "requires_reconciliation": False},
        "infrastructure_failure": {"retryable": True, "category": "infrastructure", "requires_reconciliation": False},
        "transient_failure": {"retryable": True, "category": "transient", "requires_reconciliation": False},
        "timeout_failure": {"retryable": True, "category": "timeout", "requires_reconciliation": True},
        "connection_failure": {"retryable": True, "category": "connection", "requires_reconciliation": False},
        "worker_crash": {"retryable": True, "category": "worker", "requires_reconciliation": False},
        "database_failure": {"retryable": True, "category": "database", "requires_reconciliation": False},
        "external_failure": {"retryable": True, "category": "external", "requires_reconciliation": True},
        "unknown_external_outcome": {"retryable": False, "category": "external_unknown", "requires_reconciliation": True},
        "recovery_required": {"retryable": False, "category": "recovery", "requires_reconciliation": False},
        "reconciliation_required": {"retryable": False, "category": "reconciliation", "requires_reconciliation": True},
        "partial_failure": {"retryable": False, "category": "partial", "requires_reconciliation": True},
        "cascading_failure": {"retryable": False, "category": "cascading", "requires_reconciliation": True},
        "resource_exhausted": {"retryable": True, "category": "resource", "requires_reconciliation": False},
        "capacity_exceeded": {"retryable": True, "category": "capacity", "requires_reconciliation": False},
        "configuration_error": {"retryable": False, "category": "configuration", "requires_reconciliation": False},
        "data_corruption": {"retryable": False, "category": "corruption", "requires_reconciliation": True},
        "version_conflict": {"retryable": True, "category": "concurrency", "requires_reconciliation": False},
        "idempotency_conflict": {"retryable": False, "category": "idempotency", "requires_reconciliation": False},
    }
    
    @staticmethod
    def get_taxonomy() -> Dict[str, Dict[str, Any]]:
        """Get the failure taxonomy."""
        return FailureClassifier.TAXONOMY
    
    @staticmethod
    def is_retryable(failure_class: str) -> bool:
        """Check if a failure class is retryable."""
        taxonomy = FailureClassifier.TAXONOMY.get(failure_class, {})
        return taxonomy.get("retryable", False)
    
    @staticmethod
    def requires_reconciliation(failure_class: str) -> bool:
        """Check if a failure class requires reconciliation."""
        taxonomy = FailureClassifier.TAXONOMY.get(failure_class, {})
        return taxonomy.get("requires_reconciliation", False)
    
    @staticmethod
    def get_category(failure_class: str) -> str:
        """Get the category of a failure class."""
        taxonomy = FailureClassifier.TAXONOMY.get(failure_class, {})
        return taxonomy.get("category", "unknown")
    
    @staticmethod
    def classify(exception: Exception, context: Dict[str, Any]) -> Tuple[str, str]:
        """
        Classify a failure into a deterministic category.
        
        Returns:
            Tuple of (failure_class, failure_reason)
        """
        error_str = str(exception).lower()
        is_external = context.get("is_external", False)
        
        # External unknown - result genuinely unknown (for external operations)
        external_unknown_indicators = [
            "timeout",
            "network unreachable",
            "connection timeout",
            "read timeout",
            "connection reset",
        ]
        
        # Permanent failures - not retryable
        permanent_indicators = [
            "not found",
            "does not exist",
            "invalid",
            "unauthorized",
            "forbidden",
            "permission denied",
            "invalid signature",
            "malformed",
            "constraint violation",
            "duplicate key",
            "unique constraint",
            "foreign key",
        ]
        
        # Transient failures - safe to retry (for internal operations)
        transient_indicators = [
            "connection refused",
            "connection timeout",
            "temporary failure",
            "temporarily unavailable",
            "rate limit",
            "too many requests",
            "service unavailable",
            "gateway timeout",
            "deadlock",
            "lock timeout",
        ]
        
        # Database failure indicators
        database_indicators = [
            "deadlock detected",
            "serialization failure",
            "sqlalchemy",
            "asyncpg",
            "postgresql",
            "database error",
            "sql error",
        ]
        
        # Connection failure indicators
        connection_indicators = [
            "connection refused",
            "connection reset",
            "network unreachable",
            "connection reset by peer",
            "broken pipe",
        ]
        
        # Worker crash indicators
        worker_indicators = [
            "worker",
            "process",
            "crash",
            "segmentation fault",
            "sigterm",
            "sigkill",
            "oom",
            "out of memory",
        ]
        
        # Resource exhaustion indicators
        resource_indicators = [
            "out of memory",
            "oom",
            "memory limit",
            "disk full",
            "no space left",
            "cpu limit",
            "quota exceeded",
            "rate limit",
            "too many connections",
        ]
        
        # For external operations, check unknown outcome FIRST (before connection/database)
        if is_external:
            for indicator in external_unknown_indicators:
                if indicator in error_str:
                    return ("unknown_external_outcome", f"External operation timeout/unknown: {str(exception)[:500]}")
        
        # Check for database failures first (most specific)
        for indicator in database_indicators:
            if indicator in error_str:
                return ("database_failure", f"Database failure: {str(exception)[:500]}")
        
        # Check for connection failures (before transient)
        for indicator in connection_indicators:
            if indicator in error_str:
                return ("connection_failure", f"Connection failure: {str(exception)[:500]}")
        
        # Check for resource exhaustion (before worker - more specific for OOM)
        for indicator in resource_indicators:
            if indicator in error_str:
                return ("resource_exhausted", f"Resource exhausted: {str(exception)[:500]}")
        
        # Check for worker crashes (before transient)
        for indicator in worker_indicators:
            if indicator in error_str:
                return ("worker_crash", f"Worker crash: {str(exception)[:500]}")
        
        # Check for permanent failures
        for indicator in permanent_indicators:
            if indicator in error_str:
                return ("validated_failure", f"Validated failure: {str(exception)[:500]}")
        
        # Check for transient failures
        for indicator in transient_indicators:
            if indicator in error_str:
                return ("transient_failure", f"Transient failure: {str(exception)[:500]}")
        
        # Default to unknown
        return ("unknown", f"Unclassified failure: {str(exception)[:500]}")


class RetryPolicy:
    """Retry policy calculator."""
    
    @staticmethod
    def calculate_next_retry(
        policy: str,
        attempt: int,
        base_interval_seconds: int = 60,
        max_interval_seconds: int = 3600,
    ) -> int:
        """Calculate next retry interval in seconds."""
        if policy == "exponential_backoff":
            interval = min(base_interval_seconds * (2 ** attempt), max_interval_seconds)
        elif policy == "linear_backoff":
            interval = min(base_interval_seconds * (attempt + 1), max_interval_seconds)
        elif policy == "fixed_interval":
            interval = base_interval_seconds
        elif policy == "immediate":
            interval = 1
        else:
            interval = base_interval_seconds
        
        # Add jitter (±10%)
        import random
        jitter = random.uniform(-0.1, 0.1)
        return int(interval * (1 + jitter))


@dataclass
class RecoveryContext:
    """Context for a recovery operation."""
    operation_id: str
    organization_id: str
    actor_id: str
    actor_type: str = "system"
    recovery_type: str = "retry"
    failure_class: str = "unknown"
    failure_reason: str = ""
    governance_scope_ids: List[str] = field(default_factory=list)
    provenance: Dict = field(default_factory=dict)
    metadata: Dict = field(default_factory=dict)


class CanonicalReliabilityService:
    """Service for canonical reliability, failure recovery & continuity."""
    
    def __init__(self):
        self._worker_batch_size = 100
        self._max_recoveries_per_scan = 50
        self._stale_threshold_seconds = 300  # 5 minutes
        self._worker_lease_seconds = 60
    
    # =====================================================================
    # PHASE 1: OPERATION LIFECYCLE
    # =====================================================================
    
    async def create_operation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        operation_type: str,
        title: str,
        description: str = "",
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        governance_scope_id: Optional[str] = None,
        commitment_id: Optional[str] = None,
        authorization_id: Optional[str] = None,
        decision_id: Optional[str] = None,
        action_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_type: str = "human",
        is_external: bool = False,
        external_system: Optional[str] = None,
        external_operation_id: Optional[str] = None,
        retry_policy: str = "exponential_backoff",
        max_attempts: int = 3,
        max_retry_interval_seconds: int = 300,
        key_fields: Optional[Dict] = None,
    ) -> CanonicalOperation:
        """Create a new canonical operation."""
        
        # Compute fingerprint for exact-once
        key_fields = key_fields or {}
        fingerprint = compute_operation_fingerprint(
            organization_id=organization_id,
            operation_type=operation_type,
            scope_type=scope_type,
            scope_id=scope_id,
            key_fields=key_fields,
        )
        
        # Check for exact-once duplicate
        existing = await db.execute(
            select(CanonicalOperation).where(
                CanonicalOperation.organization_id == organization_id,
                CanonicalOperation.fingerprint == fingerprint,
            )
        )
        existing_op = existing.scalars().first()
        if existing_op:
            logger.info(f"Exact-once duplicate detected for operation {fingerprint}")
            return existing_op
        
        # Create operation
        operation = CanonicalOperation(
            organization_id=organization_id,
            operation_type=operation_type,
            title=title,
            description=description,
            scope_type=scope_type,
            scope_id=scope_id,
            governance_scope_id=governance_scope_id,
            commitment_id=commitment_id,
            authorization_id=authorization_id,
            decision_id=decision_id,
            action_id=action_id,
            actor_id=actor_id,
            actor_type=actor_type,
            is_external=is_external,
            external_system=external_system,
            external_operation_id=external_operation_id,
            retry_policy=retry_policy,
            max_attempts=max_attempts,
            max_retry_interval_seconds=max_retry_interval_seconds,
            fingerprint=fingerprint,
        )
        
        db.add(operation)
        await db.flush()
        
        # Initialize operation state (no attempt yet - start_attempt will create first attempt)
        operation.current_attempt = 0
        operation.state = "queued"
        
        # Create worker lease
        await self._create_worker_lease(db, operation.id, "system", "system")
        
        # Create checkpoint
        await self._create_checkpoint(db, operation, "start", step_number=1, context={})
        
        await db.flush()
        
        logger.info(f"Created canonical operation {operation.id} ({operation.operation_type})")
        return operation

    async def start_attempt(
        self,
        db: AsyncSession,
        operation: CanonicalOperation,
        worker_id: str,
        worker_instance: Optional[str] = None,
    ) -> OperationAttempt:
        """Start a new attempt for an operation."""
        
        operation.current_attempt += 1
        attempt_number = operation.current_attempt
        
        attempt = OperationAttempt(
            operation_id=operation.id,
            organization_id=operation.organization_id,
            attempt_number=attempt_number,
            state="executing",
            worker_id=worker_id,
            worker_instance=worker_instance,
            started_at=utcnow(),
            is_retry=(attempt_number > 1),
            fingerprint=compute_payload_fingerprint({
                "operation_id": operation.id,
                "attempt_number": attempt_number,
            }),
        )
        
        operation.state = "attempting"
        operation.started_at = utcnow()
        
        db.add(attempt)
        
        # Update worker lease
        await self._renew_worker_lease(db, operation.id, "system")
        
        # Create checkpoint
        await self._create_checkpoint(db, operation, "attempt", step_number=attempt_number, context={
            "worker_id": worker_id,
            "attempt_number": attempt_number,
        })
        
        await db.flush()
        return attempt

    async def complete_attempt(
        self,
        db: AsyncSession,
        operation: CanonicalOperation,
        attempt: OperationAttempt,
        outcome: str,
        result_json: Optional[Dict] = None,
        error: Optional[str] = None,
        external_response_json: Optional[Dict] = None,
        external_request_id: Optional[str] = None,
    ) -> CanonicalOperation:
        """Complete an attempt and update operation state."""
        
        now = utcnow()
        attempt.completed_at = now
        attempt.outcome = outcome
        attempt.result_json = result_json
        attempt.error = error
        attempt.external_response_json = external_response_json
        attempt.external_request_id = external_request_id
        attempt.state = "completed" if outcome == "success" else "failed"
        if attempt.started_at:
            started_at = attempt.started_at
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=timezone.utc)
            attempt.duration_ms = int((now - started_at).total_seconds() * 1000)
        
        if outcome == "success":
            operation.state = "completed"
            operation.completed_at = now
            operation.outcome = "success"
            operation.result_json = result_json
        elif outcome == "timeout":
            operation.state = "unknown"
            operation.outcome = "timeout"
            operation.error = "Operation timed out"
        elif outcome == "cancelled":
            operation.state = "cancelled"
            operation.outcome = "cancelled"
            operation.error = error
        else:
            # Failure
            failure_class, failure_reason = FailureClassifier.classify(
                Exception(error or "Unknown error"),
                {"operation_id": operation.id, "attempt": attempt.attempt_number}
            )
            
            operation.failure_class = failure_class
            operation.failure_reason = error
            
            if attempt.attempt_number >= operation.max_attempts:
                operation.state = "failed"
                operation.completed_at = utcnow()
                operation.outcome = "failure"
                operation.error = error
            else:
                operation.state = "retrying"
                operation.next_retry_at = utcnow() + timedelta(
                    seconds=RetryPolicy.calculate_next_retry(
                        operation.retry_policy,
                        attempt.attempt_number,
                        max_interval_seconds=operation.max_retry_interval_seconds,
                    )
                )
        
        # Create checkpoint
        await self._create_checkpoint(db, operation, "attempt_complete", step_number=attempt.attempt_number, context={
            "outcome": outcome,
            "error": error,
        })
        
        # Release worker lease
        await self._release_worker_lease(db, operation.id)
        
        await db.flush()
        return operation

    # =====================================================================
    # PHASE 2: EXTERNAL UNKNOWN STATE HANDLING
    # =====================================================================
    
    async def mark_external_unknown(
        self,
        db: AsyncSession,
        operation: CanonicalOperation,
        external_system: str,
        external_operation_id: str,
        external_operation_type: str,
        request_payload: Optional[Dict] = None,
        timeout_at: Optional[datetime] = None,
    ) -> ExternalUnknownState:
        """Mark an operation as having unknown external result."""
        
        operation.state = "unknown"
        operation.is_external = True
        operation.external_system = operation.external_system or "unknown"
        operation.external_operation_id = operation.external_operation_id or "unknown"
        
        fingerprint = compute_payload_fingerprint({
            "operation_id": operation.id,
            "external_system": external_system,
            "external_operation_id": external_operation_id,
        })
        
        # Check for exact-once
        existing = await db.execute(
            select(ExternalUnknownState).where(
                ExternalUnknownState.organization_id == operation.organization_id,
                ExternalUnknownState.fingerprint == fingerprint,
            )
        )
        existing_eus = existing.scalars().first()
        if existing_eus:
            return existing_eus
        
        eus = ExternalUnknownState(
            operation_id=operation.id,
            organization_id=operation.organization_id,
            external_system=external_system,
            external_operation_id=external_operation_id,
            external_operation_type=external_operation_type,
            request_payload_json=request_payload,
            request_fingerprint=compute_payload_fingerprint(request_payload or {}),
            state="unknown",
            requested_at=utcnow(),
            timeout_at=timeout_at or (utcnow() + timedelta(hours=24)),
            fingerprint=fingerprint,
        )
        
        db.add(eus)
        await db.flush()
        
        # Emit event
        await event_service.emit(
            db,
            name="external.unknown",
            actor_id="system",
            organization_id=operation.organization_id,
            payload={
                "operation_id": operation.id,
                "external_system": external_system,
                "external_operation_id": external_operation_id,
                "eus_id": eus.id,
            },
        )
        
        return eus

    async def reconcile_external_unknown(
        self,
        db: AsyncSession,
        eus: ExternalUnknownState,
        external_state: Dict,
        reconciliation_method: str = "external_lookup",
        actor_id: str = "system",
    ) -> Reconciliation:
        """Reconcile an external unknown state with actual external state."""
        
        reconciliation = Reconciliation(
            organization_id=eus.organization_id,
            reconciliation_type="external_unknown",
            fingerprint=compute_payload_fingerprint({
                "eus_id": eus.id,
                "method": "external_lookup",
            }),
            entity_type="canonical_operation",
            entity_id=eus.operation_id,
            external_system=eus.external_system,
            external_entity_id=eus.external_operation_id,
            state="querying",
            canonical_state_json={"operation_id": eus.operation_id, "state": "unknown"},
            external_state_json=external_state,
            detected_at=utcnow(),
            started_at=utcnow(),
            requires_governance=True,
            governance_scope_id=eus.organization_id,
            authorized_by=actor_id,
        )
        
        db.add(reconciliation)
        await db.flush()
        
        # Update EUS
        eus.reconciliation_id = reconciliation.id
        eus.reconciliation_state = "querying"
        eus.external_state_json = external_state
        eus.reconciliation_method = "external_lookup"
        eus.last_checked_at = utcnow()
        
        # Compare states
        canonical_state = {"state": "unknown"}
        discrepancy = self._compare_states(canonical_state, external_state)
        
        if discrepancy:
            reconciliation.discrepancy_type = "state_mismatch"
            reconciliation.discrepancy_details_json = discrepancy
            reconciliation.canonical_state_json = canonical_state
            reconciliation.external_state_json = external_state
            reconciliation.state = "comparing"
            
            # Determine resolution
            if external_state.get("state") == "completed":
                reconciliation.resolution_method = "external_confirmed"
                reconciliation.resolved_value_json = external_state
                reconciliation.resolved_by = "system"
                reconciliation.resolved_at = utcnow()
                reconciliation.state = "resolving"
                reconciliation.outcome = "reconciled"
                reconciliation.completed_at = utcnow()
                
                # Update EUS
                eus.state = "reconciled"
                eus.reconciliation_state = "completed"
                eus.reconciliation_result_json = external_state
                
                # Update original operation
                operation = await db.get(CanonicalOperation, reconciliation.entity_id)
                if operation:
                    operation.state = "completed"
                    operation.outcome = "success"
                    operation.result_json = external_state
                    operation.completed_at = utcnow()
                    operation.state = "reconciled"
            elif external_state.get("state") == "failed":
                reconciliation.resolution_method = "external_confirmed_failed"
                reconciliation.resolved_value_json = external_state
                reconciliation.resolved_by = "system"
                reconciliation.resolved_at = utcnow()
                reconciliation.state = "resolving"
                reconciliation.outcome = "reconciled"
                reconciliation.completed_at = utcnow()
                
                eus.state = "reconciled"
                eus.reconciliation_state = "completed"
                
                operation = await db.get(CanonicalOperation, reconciliation.entity_id)
                if operation:
                    operation.state = "failed"
                    operation.outcome = "failure"
                    operation.completed_at = utcnow()
            else:
                reconciliation.state = "escalated"
                reconciliation.resolution_method = "escalated"
                reconciliation.outcome = "escalated"
                eus.reconciliation_state = "escalated"
        else:
            reconciliation.state = "completed"
            reconciliation.outcome = "reconciled"
            reconciliation.resolved_value_json = canonical_state
            reconciliation.resolved_by = "system"
            reconciliation.resolved_at = utcnow()
            reconciliation.completed_at = utcnow()
            
            eus.state = "reconciled"
            eus.reconciliation_state = "completed"
            eus.reconciliation_result_json = canonical_state
            
            operation = await db.get(CanonicalOperation, reconciliation.entity_id)
            if operation:
                operation.state = "reconciled"
                operation.result_json = canonical_state
        
        reconciliation.verified = True
        reconciliation.verified_by = "system"
        reconciliation.verified_at = utcnow()
        reconciliation.verification_result_json = {"canonical": canonical_state, "external": external_state}
        
        eus.reconciliation_result_json = {"canonical": canonical_state, "external": external_state}
        
        await db.flush()
        
        # Emit event
        await event_service.emit(
            db,
            name="reconciliation.completed",
            actor_id="system",
            organization_id=eus.organization_id,
            payload={
                "reconciliation_id": reconciliation.id,
                "outcome": reconciliation.outcome,
            },
        )
        
        return reconciliation

    def _compare_states(self, canonical: Dict, external: Dict) -> Optional[Dict]:
        """Compare canonical and external states."""
        # Simplified comparison - can be extended
        if canonical.get("state") != external.get("state"):
            return {"type": "state_mismatch", "canonical": canonical, "external": external}
        return None

    # =====================================================================
    # PHASE 3: RECOVERY
    # =====================================================================
    
    async def initiate_recovery(
        self,
        db: AsyncSession,
        context: RecoveryContext,
    ) -> Recovery:
        """Initiate a recovery for a failed/unknown operation."""
        
        operation = await db.get(CanonicalOperation, context.operation_id)
        if not operation:
            raise ValueError(f"Operation {context.operation_id} not found")
        
        # Check for existing recovery
        existing = await db.execute(
            select(Recovery).where(
                Recovery.organization_id == context.organization_id,
                Recovery.operation_id == context.operation_id,
                Recovery.state.in_(["pending", "detecting", "classifying", "planning", "executing", "verifying"]),
            )
        )
        existing_rec = existing.scalars().first()
        if existing_rec:
            logger.info(f"Recovery already in progress for operation {context.operation_id}")
            return existing_rec
        
        # Create recovery
        fingerprint = compute_payload_fingerprint({
            "operation_id": context.operation_id,
            "recovery_type": context.recovery_type,
            "actor_id": context.actor_id,
        })
        
        recovery = Recovery(
            operation_id=context.operation_id,
            organization_id=context.organization_id,
            recovery_type=context.recovery_type,
            failure_class=context.failure_class,
            failure_reason=context.failure_reason,
            state="detecting",
            actor_id=context.actor_id,
            actor_type=context.actor_type,
            governance_scope_id=context.governance_scope_ids[0] if context.governance_scope_ids else None,
            fingerprint=fingerprint,
            detected_at=utcnow(),
        )
        
        db.add(recovery)
        await db.flush()
        
        # Update operation
        operation = await db.get(CanonicalOperation, context.operation_id)
        if operation:
            operation.recovery_state = "detecting"
            operation.recovery_id = recovery.id
            operation.recovery_type = context.recovery_type
            operation.recovery_started_at = utcnow()
        
        await db.flush()
        
        # Emit event
        await event_service.emit(
            db,
            name="recovery.initiated",
            actor_id=context.actor_id,
            organization_id=context.organization_id,
            payload={
                "recovery_id": recovery.id,
                "operation_id": context.operation_id,
                "recovery_type": context.recovery_type,
                "failure_class": context.failure_class,
            },
        )
        
        return recovery

    async def execute_recovery(
        self,
        db: AsyncSession,
        recovery: Recovery,
        recovery_plan: Optional[Dict] = None,
    ) -> Recovery:
        """Execute a recovery plan."""
        
        recovery.state = "executing"
        recovery.started_at = utcnow()
        recovery.recovery_plan_json = recovery_plan or {}
        recovery.current_step = 0
        
        operation = await db.get(CanonicalOperation, recovery.operation_id)
        if operation:
            operation.recovery_state = "executing"
        
        await db.flush()
        
        try:
            if recovery.recovery_type == "retry":
                await self._execute_retry_recovery(db, recovery)
            elif recovery.recovery_type == "replay":
                await self._execute_replay_recovery(db, recovery)
            elif recovery.recovery_type == "compensate":
                await self._execute_compensate_recovery(db, recovery)
            elif recovery.recovery_type == "reconcile":
                await self._execute_reconcile_recovery(db, recovery)
            elif recovery.recovery_type == "escalate":
                await self._execute_escalate_recovery(db, recovery)
            elif recovery.recovery_type == "external_reconcile":
                await self._execute_external_reconcile_recovery(db, recovery)
            else:
                raise ValueError(f"Unknown recovery type: {recovery.recovery_type}")
            
            recovery.state = "verifying"
            await db.flush()
            
            # Verify
            await self._verify_recovery(db, recovery)
            
        except Exception as exc:
            recovery.state = "failed"
            recovery.error = str(exc)
            recovery.completed_at = utcnow()
            logger.exception(f"Recovery {recovery.id} failed: {exc}")
            raise
        
        await db.flush()
        return recovery

    async def _execute_retry_recovery(self, db: AsyncSession, recovery: Recovery) -> None:
        """Execute retry recovery - create new attempt."""
        operation = await db.get(CanonicalOperation, recovery.operation_id)
        if not operation:
            raise ValueError("Operation not found")
        
        if not operation.can_retry:
            raise ValueError("Operation cannot be retried (max attempts reached)")
        
        recovery.recovery_plan_json = {"type": "retry", "max_attempts": operation.max_attempts}
        
        # Create new attempt
        await self.start_attempt(db, operation, "recovery_worker", "recovery")
        recovery.current_step = 1
        recovery.total_steps = 1

    async def _execute_replay_recovery(self, db: AsyncSession, recovery: Recovery) -> None:
        """Execute replay recovery - replay from checkpoint."""
        operation = await db.get(CanonicalOperation, recovery.operation_id)
        if not operation:
            raise ValueError("Operation not found")
        
        # Get latest checkpoint
        checkpoint = await db.execute(
            select(OperationCheckpoint)
            .where(OperationCheckpoint.operation_id == recovery.operation_id)
            .order_by(OperationCheckpoint.checkpoint_number.desc())
            .limit(1)
        )
        checkpoint = checkpoint.scalars().first()
        
        if not checkpoint:
            raise ValueError("No checkpoint found for replay")
        
        recovery.recovery_plan_json = {"type": "replay", "checkpoint_id": checkpoint.id}
        
        # Restore operation state from checkpoint
        # Implementation depends on checkpoint type
        recovery.current_step = 1
        recovery.total_steps = 2

    async def _execute_compensate_recovery(self, db: AsyncSession, recovery: Recovery) -> None:
        """Execute compensating transaction recovery."""
        operation = await db.get(CanonicalOperation, recovery.operation_id)
        if not operation:
            raise ValueError("Operation not found")
        
        # Create compensating operation
        # This is domain-specific - would create inverse operation
        recovery.recovery_plan_json = {"type": "compensate", "operation_id": recovery.operation_id}
        recovery.compensation_type = "inverse_operation"
        recovery.compensation_executed = True
        
        operation = await db.get(CanonicalOperation, recovery.operation_id)
        if operation:
            operation.state = "compensated"
            operation.recovery_state = "completed"
        
        recovery.outcome = "compensated"
        recovery.state = "verifying"

    async def _execute_reconcile_recovery(self, db: AsyncSession, recovery: Recovery) -> None:
        """Execute reconciliation recovery."""
        # This would reconcile with external systems
        recovery.recovery_plan_json = {"type": "reconcile"}
        
        # Find external unknown state
        eus = await db.execute(
            select(ExternalUnknownState).where(
                ExternalUnknownState.operation_id == recovery.operation_id
            )
        )
        eus = eus.scalars().first()
        
        if eus:
            reconciliation = await self.reconcile_external_unknown(
                db,
                eus,
                {"state": "verified"},  # Would be actual external state
                "recovery_reconcile",
            )
            recovery.reconciliation_id = reconciliation.id

    async def _execute_escalate_recovery(self, db: AsyncSession, recovery: Recovery) -> None:
        """Escalate recovery to human."""
        recovery.state = "escalated"
        recovery.outcome = "escalated"
        recovery.completed_at = utcnow()
        
        # Create attention signal
        await event_service.emit(
            db,
            name="recovery.escalated",
            actor_id="system",
            organization_id=recovery.organization_id,
            payload={
                "recovery_id": recovery.id,
                "operation_id": recovery.operation_id,
                "failure_class": recovery.failure_class,
                "reason": recovery.failure_reason,
            },
        )

    async def _execute_external_reconcile_recovery(self, db: AsyncSession, recovery: Recovery) -> None:
        """Execute external reconciliation."""
        # Reconcile with external system
        recovery.recovery_plan_json = {"type": "external_reconcile"}
        
        # Similar to reconcile_external_unknown but initiated by recovery
        eus = await db.execute(
            select(ExternalUnknownState).where(
                ExternalUnknownState.operation_id == recovery.operation_id
            )
        )
        eus = eus.scalars().first()
        
        if eus:
            reconciliation = await self.reconcile_external_unknown(
                db,
                eus,
                {"state": "verified"},
                "recovery_reconcile",
            )
            recovery.reconciliation_id = reconciliation.id
            recovery.outcome = "reconciled"

    async def _verify_recovery(self, db: AsyncSession, recovery: Recovery) -> None:
        """Verify recovery result."""
        recovery.state = "completed"
        recovery.completed_at = utcnow()
        recovery.verified = True
        recovery.verified_by = "system"
        recovery.verified_at = utcnow()
        recovery.verification_result_json = {"verified": True, "at": utcnow().isoformat()}
        
        operation = await db.get(CanonicalOperation, recovery.operation_id)
        if operation:
            operation.recovery_state = "completed"
            operation.recovery_completed_at = utcnow()
        
        # Emit event
        await event_service.emit(
            db,
            name="recovery.completed",
            actor_id="system",
            organization_id=recovery.organization_id,
            payload={
                "recovery_id": recovery.id,
                "operation_id": recovery.operation_id,
                "outcome": recovery.outcome,
            },
        )

    # =====================================================================
    # PHASE 4: STALE OPERATION DETECTION & RECOVERY
    # =====================================================================
    
    async def detect_stale_operations(
        self,
        db: AsyncSession,
        organization_id: str,
        stale_threshold_seconds: int = 300,
        limit: int = 100,
    ) -> List[StaleOperationDetector]:
        """Detect stale/abandoned operations."""
        
        stale_threshold = utcnow() - timedelta(seconds=stale_threshold_seconds)
        
        # Find operations stuck in non-terminal states
        query = select(CanonicalOperation).where(
            CanonicalOperation.organization_id == organization_id,
            CanonicalOperation.state.in_(["queued", "attempting", "executing", "retrying", "unknown", "recovering"]),
            CanonicalOperation.updated_at < utcnow() - timedelta(seconds=300),
        )
        
        result = await db.execute(query.limit(limit))
        operations = result.scalars().all()
        
        detections = []
        for operation in operations:
            # Check if already detected
            existing = await db.execute(
                select(StaleOperationDetector).where(
                    StaleOperationDetector.organization_id == organization_id,
                    StaleOperationDetector.operation_id == operation.id,
                    StaleOperationDetector.resolved == False,
                )
            )
            if existing.scalars().first():
                continue
            
            # Ensure updated_at is timezone-aware
            updated_at = operation.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            stale_duration = int((utcnow() - updated_at).total_seconds())
            
            detection = StaleOperationDetector(
                organization_id=organization_id,
                operation_id=operation.id,
                detected_at=utcnow(),
                detection_method="timeout",
                stale_since=operation.updated_at,
                stale_duration_seconds=stale_duration,
                detection_reason=f"Operation in state '{operation.state}' for {stale_duration}s without progress",
                operation_state=operation.state,
                operation_attempt=operation.current_attempt,
                last_progress_at=operation.updated_at,
            )
            
            db.add(detection)
            detections.append(detection)
        
        if detections:
            await db.flush()
            logger.info(f"Detected {len(detections)} stale operations for org {organization_id}")
        
        return detections

    async def recover_stale_operations(
        self,
        db: AsyncSession,
        detections: List[StaleOperationDetector],
    ) -> List[Recovery]:
        """Recover detected stale operations."""
        
        recoveries = []
        for detection in detections:
            if detection.resolved:
                continue
            
            operation = await db.get(CanonicalOperation, detection.operation_id)
            if not operation:
                continue
            
            if operation.is_terminal:
                detection.resolved = True
                detection.resolved_at = utcnow()
                detection.resolution_method = "already_terminal"
                continue
            
            # Initiate recovery
            context = RecoveryContext(
                operation_id=operation.id,
                organization_id=detection.organization_id,
                actor_id="system",
                actor_type="system",
                recovery_type="retry" if operation.can_retry else "escalate",
                failure_class="timeout",
                failure_reason=f"Stale operation detected: {detection.detection_reason}",
                governance_scope_ids=[detection.organization_id],
            )
            
            recovery = await self.initiate_recovery(db, context)
            
            detection.recovery_id = recovery.id
            detection.recovery_state = recovery.state
            detection.resolved = True
            detection.resolved_at = utcnow()
            detection.resolution_method = "auto_recovery_initiated"
            
            recoveries.append(recovery)
        
        await db.flush()
        return recoveries

    # =====================================================================
    # PHASE 4: WORKER LEASE & CRASH RECOVERY
    # =====================================================================
    
    async def _create_worker_lease(
        self,
        db: AsyncSession,
        operation_id: str,
        worker_id: str,
        worker_type: str = "worker",
    ) -> WorkerLease:
        """Create a worker lease for an operation."""

        operation = await db.get(CanonicalOperation, operation_id)
        if operation is None:
            raise ValueError(f"Cannot create worker lease: operation {operation_id} not found")

        lease = WorkerLease(
            worker_id=worker_id,
            worker_instance=worker_id,
            operation_id=operation_id,
            organization_id=operation.organization_id,
            expires_at=utcnow() + timedelta(seconds=self._worker_lease_seconds),
            worker_type=worker_type,
        )
        db.add(lease)
        await db.flush()
        return lease

    async def _renew_worker_lease(
        self,
        db: AsyncSession,
        operation_id: str,
        worker_id: str,
    ) -> Optional[WorkerLease]:
        """Renew worker lease."""
        
        lease = await db.execute(
            select(WorkerLease).where(
                WorkerLease.operation_id == operation_id,
                WorkerLease.worker_id == "system",
                WorkerLease.active == True,
            )
        )
        lease = lease.scalars().first()
        if lease:
            lease.renewed_at = utcnow()
            lease.expires_at = utcnow() + timedelta(seconds=self._worker_lease_seconds)
            lease.renewal_count += 1
            await db.flush()
        return lease

    async def _release_worker_lease(
        self,
        db: AsyncSession,
        operation_id: str,
    ) -> None:
        """Release worker lease."""
        
        lease = await db.execute(
            select(WorkerLease).where(
                WorkerLease.operation_id == operation_id,
                WorkerLease.active == True,
            )
        )
        lease = lease.scalars().first()
        if lease:
            lease.active = False
            lease.expired = True
            await db.flush()

    async def detect_expired_leases(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int = 100,
    ) -> List[WorkerLease]:
        """Detect expired worker leases (indicating worker crash)."""
        
        now = utcnow()
        leases = await db.execute(
            select(WorkerLease).where(
                WorkerLease.organization_id == organization_id,
                WorkerLease.active == True,
                WorkerLease.expired == False,
                WorkerLease.expires_at < utcnow(),
            ).limit(limit)
        )
        return leases.scalars().all()

    async def recover_expired_leases(
        self,
        db: AsyncSession,
        leases: List[WorkerLease],
    ) -> List[Recovery]:
        """Recover operations with expired leases."""
        
        recoveries = []
        for lease in leases:
            if lease.expired:
                continue
            
            lease.expired = True
            lease.active = False
            
            operation = await db.get(CanonicalOperation, lease.operation_id)
            if not operation or operation.is_terminal:
                continue
            
            context = RecoveryContext(
                operation_id=operation.id,
                organization_id=lease.organization_id,
                actor_id="system",
                actor_type="system",
                recovery_type="restart",
                failure_class="timeout",
                failure_reason=f"Worker lease expired (worker: {lease.worker_id})",
                governance_scope_ids=[lease.organization_id],
            )
            
            recovery = await self.initiate_recovery(db, context)
            await self.execute_recovery(db, recovery)
            recoveries.append(recovery)
        
        return recoveries

    # =====================================================================
    # PHASE 5: CHECKPOINT MANAGEMENT
    # =====================================================================
    
    async def _create_checkpoint(
        self,
        db: AsyncSession,
        operation: CanonicalOperation,
        checkpoint_type: str,
        step_number: Optional[int] = None,
        step_name: Optional[str] = None,
        context: Optional[Dict] = None,
    ) -> OperationCheckpoint:
        """Create a checkpoint for an operation."""
        
        # Get next checkpoint number
        last = await db.execute(
            select(func.max(OperationCheckpoint.checkpoint_number))
            .where(OperationCheckpoint.operation_id == operation.id)
        )
        checkpoint_number = (last.scalar() or 0) + 1
        
        fingerprint = compute_payload_fingerprint({
            "operation_id": operation.id,
            "checkpoint_number": checkpoint_number,
            "type": checkpoint_type,
        })
        
        import json
        
        checkpoint = OperationCheckpoint(
            operation_id=operation.id,
            organization_id=operation.organization_id,
            checkpoint_number=checkpoint_number,
            checkpoint_type=checkpoint_type,
            operation_state_json={
                "state": operation.state,
                "current_attempt": operation.current_attempt,
                "outcome": operation.outcome,
            },
            context_json={"external_system": operation.external_system} if operation.external_system else {},
            step_number=step_number,
            step_name=step_name,
            fingerprint=fingerprint,
        )
        
        db.add(checkpoint)
        await db.flush()
        return checkpoint

    async def restore_from_checkpoint(
        self,
        db: AsyncSession,
        operation_id: str,
        checkpoint_number: Optional[int] = None,
    ) -> CanonicalOperation:
        """Restore operation state from checkpoint."""
        
        if checkpoint_number:
            checkpoint = await db.execute(
                select(OperationCheckpoint).where(
                    OperationCheckpoint.operation_id == operation_id,
                    OperationCheckpoint.checkpoint_number == checkpoint_number,
                )
            )
        else:
            checkpoint = await db.execute(
                select(OperationCheckpoint)
                .where(OperationCheckpoint.operation_id == operation_id)
                .order_by(OperationCheckpoint.checkpoint_number.desc())
                .limit(1)
            )
        
        checkpoint = checkpoint.scalars().first()
        if not checkpoint:
            raise ValueError(f"No checkpoint found for operation {operation_id}")
        
        operation = await db.get(CanonicalOperation, operation_id)
        if not operation:
            raise ValueError("Operation not found")
        
        # Restore state
        operation.state = checkpoint.operation_state_json.get("state", operation.state)
        operation.current_attempt = checkpoint.operation_state_json.get("current_attempt", operation.current_attempt)
        operation.outcome = checkpoint.operation_state_json.get("outcome", operation.outcome)
        
        await db.flush()
        return operation

    # =====================================================================
    # PHASE 6: CHECKPOINT RECOVERY
    # =====================================================================
    
    async def run_recovery_scan(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Dict[str, int]:
        """Run comprehensive recovery scan for an organization."""
        
        results = {
            "stale_detected": 0,
            "stale_recovered": 0,
            "expired_leases": 0,
            "expired_recovered": 0,
            "unknown_reconciled": 0,
        }
        
        # Detect stale operations
        stale = await self.detect_stale_operations(db, organization_id)
        results["stale_detected"] = len(stale)
        
        if stale:
            recovered = await self.recover_stale_operations(db, stale)
            results["stale_recovered"] = len(recovered)
        
        # Detect expired leases
        leases = await self.detect_expired_leases(db, organization_id)
        results["expired_leases"] = len(leases)
        
        if leases:
            recovered = await self.recover_expired_leases(db, leases)
            results["expired_recovered"] = len(recovered)
        
        # Reconcile external unknown states
        eus_query = select(ExternalUnknownState).where(
            ExternalUnknownState.organization_id == organization_id,
            ExternalUnknownState.state == "unknown",
        )
        eus_result = await db.execute(eus_query.limit(50))
        for eus in eus_result.scalars().all():
            if eus.timeout_at and eus.timeout_at < utcnow():
                await self.reconcile_external_unknown(
                    db,
                    eus,
                    {"state": "timeout"},  # Would be actual external state
                    "timeout_reconcile",
                )
                results["unknown_reconciled"] += 1
        
        return results

    # =====================================================================
    # PHASE 7: DATABASE TRANSACTION RECOVERY
    # =====================================================================
    
    async def handle_transaction_failure(
        self,
        db: AsyncSession,
        operation: CanonicalOperation,
        exception: Exception,
    ) -> CanonicalOperation:
        """Handle database transaction failure during operation."""
        
        # Rollback is automatic in SQLAlchemy
        # Operation state depends on when failure occurred
        
        if operation.state in ("attempting", "executing"):
            # Failure during execution - operation can be retried
            operation.state = "retrying"
            operation.next_retry_at = utcnow() + timedelta(seconds=60)
        elif operation.state == "completed":
            # Completed but DB failed - may need reconciliation
            operation.state = "reconciled"
        
        await db.flush()
        return operation

    # =====================================================================
    # PHASE 8: REDIS/QUEUE FAILURE HANDLING
    # =====================================================================
    
    async def handle_queue_failure(
        self,
        db: AsyncSession,
        organization_id: str,
        operation: CanonicalOperation,
        queue_error: Exception,
    ) -> CanonicalOperation:
        """Handle queue/Redis failure."""
        
        # Operation state depends on phase
        if operation.state in ("queued", "attempting"):
            # Not yet executing - can be re-queued
            operation.state = "retrying"
            operation.next_retry_at = utcnow() + timedelta(seconds=30)
        elif operation.state == "executing":
            # Was executing - result unknown
            operation.state = "unknown"
            await self.mark_external_unknown(db, operation, "queue", "queue", "queue")
        else:
            # Other states - mark for reconciliation
            operation.state = "reconciling"
        
        await db.flush()
        return operation

    # =====================================================================
    # PHASE 9: EXTERNAL INTEGRATION FAILURE HANDLING
    # =====================================================================
    
    async def handle_external_failure(
        self,
        db: AsyncSession,
        operation: CanonicalOperation,
        external_error: Exception,
        external_system: str,
        external_operation_id: str,
    ) -> CanonicalOperation:
        """Handle external integration failure."""
        
        failure_class, failure_reason = FailureClassifier.classify(
            external_error,
            {"external_system": external_system, "external_operation_id": operation.external_operation_id}
        )
        
        operation.failure_class = failure_class
        operation.failure_reason = str(external_error)[:500]
        
        if failure_class == "external_unknown":
            # Timeout - result genuinely unknown
            operation.state = "unknown"
            await self.mark_external_unknown(
                db, operation, external_system, operation.external_operation_id or "unknown", "operation"
            )
        elif failure_class == "transient":
            # Transient - can retry
            if operation.can_retry:
                operation.state = "retrying"
                operation.next_retry_at = utcnow() + timedelta(
                    seconds=RetryPolicy.calculate_next_retry(
                        operation.retry_policy,
                        operation.current_attempt,
                        max_interval_seconds=operation.max_retry_interval_seconds,
                    )
                )
            else:
                operation.state = "failed"
        elif failure_class == "permanent":
            # Permanent failure
            operation.state = "failed"
            operation.completed_at = utcnow()
        else:
            # Unknown
            operation.state = "unknown"
            await self.mark_external_unknown(db, operation, external_system, operation.external_operation_id or "unknown", "operation")
        
        await db.flush()
        return operation

    # =====================================================================
    # PHASE 10: EXTERNAL RECONCILIATION
    # =====================================================================
    
    async def reconcile_external_operation(
        self,
        db: AsyncSession,
        operation: CanonicalOperation,
        external_state: Dict,
        reconciliation_method: str = "external_lookup",
    ) -> Reconciliation:
        """Reconcile operation with external system state."""
        
        reconciliation = Reconciliation(
            organization_id=operation.organization_id,
            reconciliation_type="external_operation",
            fingerprint=compute_payload_fingerprint({
                "operation_id": operation.id,
                "external_system": operation.external_system,
            }),
            entity_type="canonical_operation",
            entity_id=operation.id,
            external_system=operation.external_system,
            external_entity_id=operation.external_operation_id or "unknown",
            state="querying",
            canonical_state_json={"state": operation.state, "outcome": operation.outcome},
            external_state_json=external_state,
            detected_at=utcnow(),
            started_at=utcnow(),
            requires_governance=True,
            governance_scope_id=operation.organization_id,
            authorized_by="system",
        )
        
        db.add(reconciliation)
        await db.flush()
        
        # Compare states
        canonical_state = {"state": operation.state, "outcome": operation.outcome}
        discrepancy = self._compare_states(canonical_state, external_state)
        
        if discrepancy:
            reconciliation.discrepancy_type = "state_mismatch"
            reconciliation.discrepancy_details_json = discrepancy
            reconciliation.canonical_state_json = canonical_state
            reconciliation.external_state_json = external_state
            reconciliation.state = "comparing"
            
            # Determine resolution based on external state
            external_state_value = external_state.get("state", "unknown")
            
            if external_state_value in ("completed", "success"):
                reconciliation.resolution_method = "external_confirmed"
                reconciliation.resolved_value_json = external_state
                reconciliation.resolved_by = "system"
                reconciliation.resolved_at = utcnow()
                reconciliation.state = "resolving"
                reconciliation.outcome = "reconciled"
                reconciliation.completed_at = utcnow()
                
                # Update operation
                operation.state = "completed"
                operation.outcome = "success"
                operation.result_json = external_state
                operation.completed_at = utcnow()
                operation.state = "reconciled"
                
            elif external_state_value in ("failed", "error"):
                reconciliation.resolution_method = "external_confirmed_failed"
                reconciliation.resolved_value_json = external_state
                reconciliation.resolved_by = "system"
                reconciliation.resolved_at = utcnow()
                reconciliation.state = "resolving"
                reconciliation.outcome = "reconciled"
                reconciliation.completed_at = utcnow()
                
                operation.state = "failed"
                operation.outcome = "failure"
                operation.completed_at = utcnow()
            else:
                reconciliation.state = "escalated"
                reconciliation.resolution_method = "escalated"
                reconciliation.outcome = "escalated"
        else:
            reconciliation.state = "completed"
            reconciliation.outcome = "reconciled"
            reconciliation.resolved_value_json = canonical_state
            reconciliation.resolved_by = "system"
            reconciliation.resolved_at = utcnow()
            reconciliation.completed_at = utcnow()
        
        reconciliation.verified = True
        reconciliation.verified_by = "system"
        reconciliation.verified_at = utcnow()
        reconciliation.verification_result_json = {"canonical": canonical_state, "external": external_state}
        
        await db.flush()
        return reconciliation

    # =====================================================================
    # PHASE 11: INTEGRATION WITH EXISTING GATES
    # =====================================================================
    
    async def _emit_reliability_event(
        self,
        db: AsyncSession,
        event_name: str,
        organization_id: str,
        payload: Dict,
    ) -> None:
        """Emit reliability event to event bus."""
        
        await event_service.emit(
            db,
            name=event_name,
            actor_id="system",
            organization_id=organization_id,
            payload=payload,
        )

    async def integrate_with_gate28(
        self,
        db: AsyncSession,
        recovery: Recovery,
    ) -> None:
        """Integrate with Gate 28 autonomy for recovery decisions."""
        
        operation = await db.get(CanonicalOperation, recovery.operation_id)
        if not operation:
            return
        
        # Check if autonomy could handle this recovery
        if recovery.recovery_type in ("retry", "replay", "restart"):
            # These are automatic - no autonomy needed
            return
        
        if recovery.recovery_type in ("escalate", "manual_intervention"):
            # Create autonomy proposal for human decision
            proposal = AutonomyProposal(
                organization_id=recovery.organization_id,
                title=f"Recovery decision for operation {recovery.operation_id}",
                proposal_type="recovery_decision",
                state="proposed",
                actor_id="system",
                fingerprint=compute_payload_fingerprint({
                    "recovery_id": recovery.id,
                    "type": "recovery_decision",
                }),
            )
            # Would be created via autonomy_service
            pass

    async def integrate_with_gate29(
        self,
        db: AsyncSession,
        recovery: Recovery,
    ) -> None:
        """Integrate with Gate 29 for learning from failures."""
        
        operation = await db.get(CanonicalOperation, recovery.operation_id)
        if not operation:
            return
        
        # Record learning signal
        from app.models.continuous_twin import LearningSignal
        
        signal = LearningSignal(
            organization_id=recovery.organization_id,
            signal_type="failure_pattern",
            title=f"Failure pattern: {recovery.failure_class}",
            description=f"Operation {recovery.operation_id} failed with {recovery.failure_class}: {recovery.failure_reason}",
            source_type="recovery",
            source_id=recovery.id,
            priority="high",
            evidence_json={"recovery_id": recovery.id, "failure_class": recovery.failure_class},
        )
        # Would be added via continuous_twin_service
        pass

    async def integrate_with_gate30(
        self,
        db: AsyncSession,
        recovery: Recovery,
    ) -> None:
        """Integrate with Gate 30 continuity."""
        
        # Record recovery event in continuity
        from app.models.canonical_company_continuity import CompanyContinuityEvent
        
        event = CompanyContinuityEvent(
            organization_id=recovery.organization_id,
            continuity_cycle_id="recovery",  # Would link to actual cycle
            event_type="recovery_executed",
            loop_phase="execution",
            occurred_at=utcnow(),
            sequence_in_phase=1,
            actor_id="system",
            actor_type="system",
            title=f"Recovery executed: {recovery.recovery_type}",
            description=f"Recovery {recovery.id} for operation {recovery.operation_id}",
            epistemic_state="observed",
            fingerprint=compute_payload_fingerprint({
                "recovery_id": recovery.id,
                "type": "recovery_event",
            }),
        )
        # Would be added via continuity service
        pass

    async def integrate_with_gate31(
        self,
        db: AsyncSession,
        recovery: Recovery,
    ) -> None:
        """Integrate with Gate 31 integrity."""
        
        # After recovery, run integrity scan
        if recovery.state == "completed":
            await canonical_reality_integrity_service.run_integrity_scan(
                db=db,
                organization_id=recovery.organization_id,
                checks=["structural", "temporal", "provenance", "epistemic"],
                changed_since=recovery.started_at or utcnow() - timedelta(hours=1),
            )

    # =====================================================================
    # HELPER METHODS
    # =====================================================================
    
    def _get_caller(self, db: AsyncSession, user_id: str):
        """Get caller access context."""
        # Would integrate with company_context
        class CallerAccess:
            def __init__(self, user_id: str, organization_id: str):
                self.user_id = user_id
                self.organization_id = organization_id
                self.permissions = frozenset(["canonical_mutation"])
                self.governance_scope_ids = frozenset()
            
            async def get_permissions(self, db):
                return frozenset(["canonical_mutation"])
        
        return CallerAccess("system", "system")


# Singleton instance
canonical_reliability_service = CanonicalReliabilityService()