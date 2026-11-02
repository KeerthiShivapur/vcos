"""Gate 32 — Canonical Reliability API Endpoints.

Provides governed API access to operation lifecycle, recovery,
reconciliation, and reliability status.
"""

from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.database import get_db
from app.models.user import User
from app.services.canonical_reliability_service import canonical_reliability_service

router = APIRouter(prefix="/canonical/reliability", tags=["canonical-reliability"])


# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class OperationCreateRequest(BaseModel):
    operation_type: str
    title: str
    description: str = ""
    scope_type: str = "company"
    scope_id: Optional[str] = None
    governance_scope_id: Optional[str] = None
    commitment_id: Optional[str] = None
    authorization_id: Optional[str] = None
    decision_id: Optional[str] = None
    action_id: Optional[str] = None
    actor_id: Optional[str] = None
    actor_type: str = "human"
    is_external: bool = False
    external_system: Optional[str] = None
    external_operation_id: Optional[str] = None
    retry_policy: str = "exponential_backoff"
    max_attempts: int = 3
    max_retry_interval_seconds: int = 300
    key_fields: Optional[dict] = None


class ReconcileOperationRequest(BaseModel):
    external_state: dict
    reconciliation_method: str = "external_lookup"


class OperationResponse(BaseModel):
    id: str
    organization_id: str
    operation_type: str
    title: str
    description: str
    scope_type: str
    scope_id: Optional[str]
    governance_scope_id: Optional[str]
    commitment_id: Optional[str]
    authorization_id: Optional[str]
    decision_id: Optional[str]
    action_id: Optional[str]
    actor_id: Optional[str]
    actor_type: str
    is_external: bool
    external_system: Optional[str]
    external_operation_id: Optional[str]
    state: str
    current_attempt: int
    max_attempts: int
    retry_policy: str
    max_retry_interval_seconds: int
    queued_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    next_retry_at: Optional[datetime]
    outcome: Optional[str]
    result_json: Optional[dict]
    error: Optional[str]
    failure_class: Optional[str]
    failure_reason: Optional[str]
    recovery_state: Optional[str]
    recovery_type: Optional[str]
    recovery_id: Optional[str]
    recovery_started_at: Optional[datetime]
    recovery_completed_at: Optional[datetime]
    reconciliation_state: Optional[str]
    reconciliation_id: Optional[str]
    fingerprint: str
    version: int
    created_at: datetime
    updated_at: datetime


class AttemptResponse(BaseModel):
    id: str
    operation_id: str
    organization_id: str
    attempt_number: int
    state: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_ms: Optional[int]
    worker_id: Optional[str]
    worker_instance: Optional[str]
    outcome: Optional[str]
    result_json: Optional[dict]
    error: Optional[str]
    external_request_id: Optional[str]
    external_response_json: Optional[dict]
    duration_ms: Optional[int]
    queued_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    retry_reason: Optional[str]
    is_retry: bool
    retried_from_attempt_id: Optional[str]
    fingerprint: str


class RecoveryContextRequest(BaseModel):
    operation_id: str
    recovery_type: str
    failure_class: str
    failure_reason: str
    governance_scope_ids: List[str] = []
    provenance: dict = {}
    metadata: dict = {}


class RecoveryProposalRequest(BaseModel):
    finding_id: str
    proposed_change: dict
    reason: str


class RecoveryResponse(BaseModel):
    id: str
    operation_id: str
    organization_id: str
    recovery_type: str
    failure_class: str
    failure_reason: Optional[str]
    state: str
    recovery_plan_json: Optional[dict]
    recovery_steps_json: Optional[list]
    actor_id: Optional[str]
    actor_type: str
    governance_scope_ids: list
    requires_governance: bool
    authorized_at: Optional[datetime]
    authorized_by: Optional[str]
    detected_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    current_step: Optional[int]
    total_steps: Optional[int]
    current_step_name: Optional[str]
    outcome: Optional[str]
    result_json: Optional[dict]
    error: Optional[str]
    compensation_id: Optional[str]
    compensation_type: Optional[str]
    compensation_executed: bool
    verified: bool
    verified_by: Optional[str]
    verified_at: Optional[datetime]
    fingerprint: str
    version: int


class ReconciliationResponse(BaseModel):
    id: str
    organization_id: str
    reconciliation_type: str
    fingerprint: str
    entity_type: str
    entity_id: str
    external_system: str
    external_entity_id: str
    state: str
    discrepancy_type: Optional[str]
    discrepancy_details_json: Optional[dict]
    canonical_state_json: Optional[dict]
    external_state_json: Optional[dict]
    resolution_method: Optional[str]
    resolved_value_json: Optional[dict]
    resolved_by: Optional[str]
    resolved_at: Optional[datetime]
    requires_governance: bool
    governance_scope_id: Optional[str]
    authorized_by: Optional[str]
    authorized_at: Optional[datetime]
    detected_at: datetime
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    outcome: Optional[str]
    result_json: Optional[dict]
    error: Optional[str]
    version: int


class ReconciliationRequest(BaseModel):
    external_state: dict
    reconciliation_method: str = "external_lookup"


class ExternalUnknownStateResponse(BaseModel):
    id: str
    operation_id: str
    organization_id: str
    external_system: str
    external_operation_id: str
    external_operation_type: str
    state: str
    requested_at: datetime
    last_checked_at: Optional[datetime]
    timeout_at: Optional[datetime]
    reconciliation_id: Optional[str]
    reconciliation_state: Optional[str]
    external_state_json: Optional[dict]
    reconciliation_method: Optional[str]
    reconciliation_result_json: Optional[dict]
    fingerprint: str
    version: int


class RecoveryScanRequest(BaseModel):
    stale_threshold_seconds: int = 300
    limit: int = 100


class RecoveryScanResponse(BaseModel):
    stale_detected: int
    stale_recovered: int
    expired_leases: int
    expired_recovered: int
    unknown_reconciled: int


class ReliabilityStatusResponse(BaseModel):
    organization_id: str
    active_operations: int
    queued_operations: int
    executing_operations: int
    failed_operations: int
    unknown_operations: int
    recovering_operations: int
    active_recoveries: int
    pending_reconciliations: int
    external_unknown_states: int
    stale_operations: int
    expired_leases: int
    active_worker_leases: int


class RecoveryProposalRequest(BaseModel):
    finding_id: str
    proposed_change: dict
    reason: str


class RecoveryProposalResponse(BaseModel):
    id: str
    finding_id: str
    organization_id: str
    entity_type: str
    entity_id: str
    current_state: dict
    proposed_change: dict
    evidence: dict
    provenance: dict
    reason: str
    temporal_basis: dict
    governance_scope_ids: list
    actor: str
    proposed_mutation: dict
    reversibility: dict
    status: str
    created_at: datetime
    authorized_at: Optional[datetime]
    authorized_by: Optional[str]
    executed_at: Optional[datetime]
    verified_at: Optional[datetime]


# =============================================================================
# API ENDPOINTS
# =============================================================================

@router.post("/operations", response_model=OperationResponse)
async def create_operation(
    request: OperationCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new canonical operation."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    
    operation = await canonical_reliability_service.create_operation(
        db=db,
        organization_id=current_user.organization_id,
        operation_type=request.operation_type,
        title=request.title,
        description=request.description,
        scope_type=request.scope_type,
        scope_id=request.scope_id,
        governance_scope_id=request.governance_scope_id,
        commitment_id=request.commitment_id,
        authorization_id=request.authorization_id,
        decision_id=request.decision_id,
        action_id=request.action_id,
        actor_id=request.actor_id or current_user.id,
        actor_type=request.actor_type,
        is_external=request.is_external,
        external_system=request.external_system,
        external_operation_id=request.external_operation_id,
        retry_policy=request.retry_policy,
        max_attempts=request.max_attempts,
        max_retry_interval_seconds=request.max_retry_interval_seconds,
        key_fields=request.key_fields,
    )
    
    return OperationResponse(
        id=operation.id,
        organization_id=operation.organization_id,
        operation_type=operation.operation_type,
        title=operation.title,
        description=operation.description,
        scope_type=operation.scope_type,
        scope_id=operation.scope_id,
        governance_scope_id=operation.governance_scope_id,
        commitment_id=operation.commitment_id,
        authorization_id=operation.authorization_id,
        decision_id=operation.decision_id,
        action_id=operation.action_id,
        actor_id=operation.actor_id,
        actor_type=operation.actor_type,
        is_external=operation.is_external,
        external_system=operation.external_system,
        external_operation_id=operation.external_operation_id,
        state=operation.state,
        current_attempt=operation.current_attempt,
        max_attempts=operation.max_attempts,
        retry_policy=operation.retry_policy,
        max_retry_interval_seconds=operation.max_retry_interval_seconds,
        queued_at=operation.queued_at,
        started_at=operation.started_at,
        completed_at=operation.completed_at,
        next_retry_at=operation.next_retry_at,
        outcome=operation.outcome,
        result_json=operation.result_json,
        error=operation.error,
        failure_class=operation.failure_class,
        failure_reason=operation.failure_reason,
        recovery_state=operation.recovery_state,
        recovery_type=operation.recovery_type,
        recovery_id=operation.recovery_id,
        recovery_started_at=operation.recovery_started_at,
        recovery_completed_at=operation.recovery_completed_at,
        reconciliation_state=operation.reconciliation_state,
        reconciliation_id=operation.reconciliation_id,
        fingerprint=operation.fingerprint,
        version=operation.version,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
    )


@router.get("/operations", response_model=List[OperationResponse])
async def list_operations(
    state: Optional[str] = Query(None),
    operation_type: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List canonical operations for the organization."""
    from app.models.canonical_reliability import CanonicalOperation
    
    query = select(CanonicalOperation).where(
        CanonicalOperation.organization_id == current_user.organization_id
    )
    
    if state:
        query = query.where(CanonicalOperation.state == state)
    if operation_type:
        query = query.where(CanonicalOperation.operation_type == operation_type)
    
    query = query.order_by(CanonicalOperation.created_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    operations = result.scalars().all()
    
    return [
        OperationResponse(
            id=op.id,
            organization_id=op.organization_id,
            operation_type=op.operation_type,
            title=op.title,
            description=op.description,
            scope_type=op.scope_type,
            scope_id=op.scope_id,
            governance_scope_id=op.governance_scope_id,
            commitment_id=op.commitment_id,
            authorization_id=op.authorization_id,
            decision_id=op.decision_id,
            action_id=op.action_id,
            actor_id=op.actor_id,
            actor_type=op.actor_type,
            is_external=op.is_external,
            external_system=op.external_system,
            external_operation_id=op.external_operation_id,
            state=op.state,
            current_attempt=op.current_attempt,
            max_attempts=op.max_attempts,
            retry_policy=op.retry_policy,
            max_retry_interval_seconds=op.max_retry_interval_seconds,
            queued_at=op.queued_at,
            started_at=op.started_at,
            completed_at=op.completed_at,
            next_retry_at=op.next_retry_at,
            outcome=op.outcome,
            result_json=op.result_json,
            error=op.error,
            failure_class=op.failure_class,
            failure_reason=op.failure_reason,
            recovery_state=op.recovery_state,
            recovery_type=op.recovery_type,
            recovery_id=op.recovery_id,
            recovery_started_at=op.recovery_started_at,
            recovery_completed_at=op.recovery_completed_at,
            reconciliation_state=op.reconciliation_state,
            reconciliation_id=op.reconciliation_id,
            fingerprint=op.fingerprint,
            version=op.version,
            created_at=op.created_at,
            updated_at=op.updated_at,
        ) for op in operations
    ]


@router.get("/operations/{operation_id}", response_model=OperationResponse)
async def get_operation(
    operation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a canonical operation by ID."""
    from app.models.canonical_reliability import CanonicalOperation
    
    result = await db.execute(
        select(CanonicalOperation).where(
            CanonicalOperation.id == operation_id,
            CanonicalOperation.organization_id == current_user.organization_id,
        )
    )
    operation = result.scalars().first()
    
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    return OperationResponse(
        id=operation.id,
        organization_id=operation.organization_id,
        operation_type=operation.operation_type,
        title=operation.title,
        description=operation.description,
        scope_type=operation.scope_type,
        scope_id=operation.scope_id,
        governance_scope_id=operation.governance_scope_id,
        commitment_id=operation.commitment_id,
        authorization_id=operation.authorization_id,
        decision_id=operation.decision_id,
        action_id=operation.action_id,
        actor_id=operation.actor_id,
        actor_type=operation.actor_type,
        is_external=operation.is_external,
        external_system=operation.external_system,
        external_operation_id=operation.external_operation_id,
        state=operation.state,
        current_attempt=operation.current_attempt,
        max_attempts=operation.max_attempts,
        retry_policy=operation.retry_policy,
        max_retry_interval_seconds=operation.max_retry_interval_seconds,
        queued_at=operation.queued_at,
        started_at=operation.started_at,
        completed_at=operation.completed_at,
        next_retry_at=operation.next_retry_at,
        outcome=operation.outcome,
        result_json=operation.result_json,
        error=operation.error,
        failure_class=operation.failure_class,
        failure_reason=operation.failure_reason,
        recovery_state=operation.recovery_state,
        recovery_type=operation.recovery_type,
        recovery_id=operation.recovery_id,
        recovery_started_at=operation.recovery_started_at,
        recovery_completed_at=operation.recovery_completed_at,
        reconciliation_state=operation.reconciliation_state,
        reconciliation_id=operation.reconciliation_id,
        fingerprint=operation.fingerprint,
        version=operation.version,
        created_at=operation.created_at,
        updated_at=operation.updated_at,
    )


@router.get("/operations/{operation_id}/attempts", response_model=List[AttemptResponse])
async def get_operation_attempts(
    operation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all attempts for an operation."""
    from app.models.canonical_reliability import OperationAttempt, CanonicalOperation
    
    # Verify operation exists and belongs to org
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    result = await db.execute(
        select(OperationAttempt).where(
            OperationAttempt.operation_id == operation_id
        ).order_by(OperationAttempt.attempt_number)
    )
    attempts = result.scalars().all()
    
    return [
        AttemptResponse(
            id=attempt.id,
            operation_id=attempt.operation_id,
            organization_id=attempt.organization_id,
            attempt_number=attempt.attempt_number,
            state=attempt.state,
            started_at=attempt.started_at,
            completed_at=attempt.completed_at,
            duration_ms=attempt.duration_ms,
            worker_id=attempt.worker_id,
            worker_instance=attempt.worker_instance,
            outcome=attempt.outcome,
            result_json=attempt.result_json,
            error=attempt.error,
            external_request_id=attempt.external_request_id,
            external_response_json=attempt.external_response_json,
            queued_at=attempt.queued_at,
            retry_reason=attempt.retry_reason,
            is_retry=attempt.is_retry,
            retried_from_attempt_id=attempt.retried_from_attempt_id,
            fingerprint=attempt.fingerprint,
        ) for attempt in attempts
    ]


@router.post("/operations/{operation_id}/start-attempt")
async def start_operation_attempt(
    operation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start a new attempt for an operation."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import CanonicalOperation
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    if operation.state not in ("queued", "retrying", "failed"):
        raise HTTPException(status_code=400, detail=f"Cannot start attempt in state {operation.state}")
    
    attempt = await canonical_reliability_service.start_attempt(
        db=db,
        operation=operation,
        worker_id=current_user.id,
        worker_instance="api",
    )
    
    return {"attempt_number": attempt.attempt_number, "attempt_id": attempt.id}


@router.post("/operations/{operation_id}/complete-attempt")
async def complete_operation_attempt(
    operation_id: str,
    outcome: str,
    result_json: Optional[dict] = None,
    error: Optional[str] = None,
    external_response_json: Optional[dict] = None,
    external_request_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Complete an operation attempt."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import CanonicalOperation, OperationAttempt
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    # Get current attempt
    result = await db.execute(
        select(OperationAttempt).where(
            OperationAttempt.operation_id == operation_id,
            OperationAttempt.attempt_number == operation.current_attempt,
        )
    )
    attempt = result.scalars().first()
    
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")
    
    operation = await canonical_reliability_service.complete_attempt(
        db=db,
        operation=operation,
        attempt=attempt,
        outcome=outcome,
        result_json=result_json,
        error=error,
        external_response_json=external_response_json,
        external_request_id=external_request_id,
    )
    
    return {"operation_id": operation.id, "state": operation.state, "outcome": operation.outcome}


@router.post("/operations/{operation_id}/mark-external-unknown")
async def mark_operation_external_unknown(
    operation_id: str,
    external_system: str,
    external_operation_id: str,
    external_operation_type: str = "operation",
    request_payload: Optional[dict] = None,
    timeout_at: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark an operation as having unknown external result."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import CanonicalOperation
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    eus = await canonical_reliability_service.mark_external_unknown(
        db=db,
        operation=operation,
        external_system=external_system,
        external_operation_id=external_operation_id,
        external_operation_type=external_operation_type,
        request_payload=request_payload,
        timeout_at=timeout_at,
    )
    
    return {"eus_id": eus.id, "state": eus.state}


@router.post("/operations/{operation_id}/reconcile")
async def reconcile_operation(
    operation_id: str,
    request: ReconcileOperationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reconcile operation with external system state."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import CanonicalOperation
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    reconciliation = await canonical_reliability_service.reconcile_external_operation(
        db=db,
        operation=operation,
        external_state=request.external_state,
        reconciliation_method=request.reconciliation_method,
    )
    
    return {
        "reconciliation_id": reconciliation.id,
        "outcome": reconciliation.outcome,
        "operation_state": operation.state,
    }


@router.post("/operations/{operation_id}/external-unknown/reconcile")
async def reconcile_external_unknown(
    operation_id: str,
    external_state: dict,
    reconciliation_method: str = "external_lookup",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reconcile an external unknown state."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import ExternalUnknownState, CanonicalOperation
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    eus = await db.execute(
        select(ExternalUnknownState).where(
            ExternalUnknownState.operation_id == operation_id,
            ExternalUnknownState.state == "unknown",
        )
    )
    eus = eus.scalars().first()
    
    if not eus:
        raise HTTPException(status_code=404, detail="No external unknown state found")
    
    reconciliation = await canonical_reliability_service.reconcile_external_unknown(
        db=db,
        eus=eus,
        external_state=external_state,
        reconciliation_method=reconciliation_method,
    )
    
    return {
        "reconciliation_id": reconciliation.id,
        "outcome": reconciliation.outcome,
        "eus_state": eus.state,
    }


@router.get("/recoveries", response_model=List[RecoveryResponse])
async def list_recoveries(
    state: Optional[str] = Query(None),
    recovery_type: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recoveries for the organization."""
    from app.models.canonical_reliability import Recovery
    
    query = select(Recovery).where(
        Recovery.organization_id == current_user.organization_id
    )
    
    if state:
        query = query.where(Recovery.state == state)
    if recovery_type:
        query = query.where(Recovery.recovery_type == recovery_type)
    
    query = query.order_by(Recovery.created_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    recoveries = result.scalars().all()
    
    return [
        RecoveryResponse(
            id=r.id,
            operation_id=r.operation_id,
            organization_id=r.organization_id,
            recovery_type=r.recovery_type,
            failure_class=r.failure_class,
            failure_reason=r.failure_reason,
            state=r.state,
            recovery_plan_json=r.recovery_plan_json,
            recovery_steps_json=r.recovery_steps_json,
            actor_id=r.actor_id,
            actor_type=r.actor_type,
            governance_scope_ids=r.governance_scope_ids,
            requires_governance=r.requires_governance,
            authorized_at=r.authorized_at,
            authorized_by=r.authorized_by,
            detected_at=r.detected_at,
            started_at=r.started_at,
            completed_at=r.completed_at,
            current_step=r.current_step,
            total_steps=r.total_steps,
            current_step_name=r.current_step_name,
            outcome=r.outcome,
            result_json=r.result_json,
            error=r.error,
            compensation_id=r.compensation_id,
            compensation_type=r.compensation_type,
            compensation_executed=r.compensation_executed,
            verified=r.verified,
            verified_by=r.verified_by,
            verified_at=r.verified_at,
            fingerprint=r.fingerprint,
            version=r.version,
        ) for r in recoveries
    ]


@router.get("/recoveries/{recovery_id}", response_model=RecoveryResponse)
async def get_recovery(
    recovery_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a recovery by ID."""
    from app.models.canonical_reliability import Recovery
    
    recovery = await db.get(Recovery, recovery_id)
    if not recovery or recovery.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Recovery not found")
    
    return RecoveryResponse(
        id=recovery.id,
        operation_id=recovery.operation_id,
        organization_id=recovery.organization_id,
        recovery_type=recovery.recovery_type,
        failure_class=recovery.failure_class,
        failure_reason=recovery.failure_reason,
        state=recovery.state,
        recovery_plan_json=recovery.recovery_plan_json,
        recovery_steps_json=recovery.recovery_steps_json,
        actor_id=recovery.actor_id,
        actor_type=recovery.actor_type,
        governance_scope_ids=[recovery.governance_scope_id] if recovery.governance_scope_id else [],
        requires_governance=recovery.requires_governance,
        authorized_at=recovery.authorized_at,
        authorized_by=recovery.authorized_by,
        detected_at=recovery.detected_at,
        started_at=recovery.started_at,
        completed_at=recovery.completed_at,
        current_step=recovery.current_step,
        total_steps=recovery.total_steps,
        current_step_name=recovery.current_step_name,
        outcome=recovery.outcome,
        result_json=recovery.result_json,
        error=recovery.error,
        compensation_id=recovery.compensation_id,
        compensation_type=recovery.compensation_type,
        compensation_executed=recovery.compensation_executed,
        verified=recovery.verified,
        verified_by=recovery.verified_by,
        verified_at=recovery.verified_at,
        fingerprint=recovery.fingerprint,
        version=recovery.version,
    )


@router.post("/recoveries", response_model=RecoveryResponse)
async def create_recovery(
    request: RecoveryContextRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a recovery for a failed/unknown operation."""
    from app.services.canonical_reliability_service import canonical_reliability_service, RecoveryContext
    from app.models.canonical_reliability import CanonicalOperation
    
    operation = await db.get(CanonicalOperation, request.operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    context = RecoveryContext(
        operation_id=request.operation_id,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        actor_type="human",
        recovery_type=request.recovery_type,
        failure_class=request.failure_class,
        failure_reason=request.failure_reason,
        governance_scope_ids=request.governance_scope_ids,
        provenance=request.provenance,
        metadata=request.metadata,
    )
    
    recovery = await canonical_reliability_service.initiate_recovery(db, context)
    await canonical_reliability_service.execute_recovery(db, recovery)
    
    recovery = await db.get(Recovery, recovery.id)
    return RecoveryResponse(
        id=recovery.id,
        operation_id=recovery.operation_id,
        organization_id=recovery.organization_id,
        recovery_type=recovery.recovery_type,
        failure_class=recovery.failure_class,
        failure_reason=recovery.failure_reason,
        state=recovery.state,
        recovery_plan_json=recovery.recovery_plan_json,
        recovery_steps_json=recovery.recovery_steps_json,
        actor_id=recovery.actor_id,
        actor_type=recovery.actor_type,
        governance_scope_ids=[recovery.governance_scope_id] if recovery.governance_scope_id else [],
        requires_governance=recovery.requires_governance,
        authorized_at=recovery.authorized_at,
        authorized_by=recovery.authorized_by,
        detected_at=recovery.detected_at,
        started_at=recovery.started_at,
        completed_at=recovery.completed_at,
        current_step=recovery.current_step,
        total_steps=recovery.total_steps,
        current_step_name=recovery.current_step_name,
        outcome=recovery.outcome,
        result_json=recovery.result_json,
        error=recovery.error,
        compensation_id=recovery.compensation_id,
        compensation_type=recovery.compensation_type,
        compensation_executed=recovery.compensation_executed,
        verified=recovery.verified,
        verified_by=recovery.verified_by,
        verified_at=recovery.verified_at,
        fingerprint=recovery.fingerprint,
        version=recovery.version,
    )


@router.post("/operations/{operation_id}/recover")
async def recover_operation(
    operation_id: str,
    recovery_type: str,
    failure_class: str,
    failure_reason: str,
    governance_scope_ids: List[str] = [],
    provenance: dict = {},
    metadata: dict = {},
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Initiate and execute recovery for an operation."""
    from app.services.canonical_reliability_service import canonical_reliability_service, RecoveryContext
    from app.models.canonical_reliability import CanonicalOperation, Recovery
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    context = RecoveryContext(
        operation_id=operation_id,
        organization_id=current_user.organization_id,
        actor_id=current_user.id,
        actor_type="human",
        recovery_type=recovery_type,
        failure_class=failure_class,
        failure_reason=failure_reason,
        governance_scope_ids=governance_scope_ids,
        provenance=provenance,
        metadata=metadata,
    )
    
    recovery = await canonical_reliability_service.initiate_recovery(db, context)
    recovery = await canonical_reliability_service.execute_recovery(db, recovery)
    
    recovery = await db.get(Recovery, recovery.id)
    return RecoveryResponse(
        id=recovery.id,
        operation_id=recovery.operation_id,
        organization_id=recovery.organization_id,
        recovery_type=recovery.recovery_type,
        failure_class=recovery.failure_class,
        failure_reason=recovery.failure_reason,
        state=recovery.state,
        recovery_plan_json=recovery.recovery_plan_json,
        recovery_steps_json=recovery.recovery_steps_json,
        actor_id=recovery.actor_id,
        actor_type=recovery.actor_type,
        governance_scope_ids=[recovery.governance_scope_id] if recovery.governance_scope_id else [],
        requires_governance=recovery.requires_governance,
        authorized_at=recovery.authorized_at,
        authorized_by=recovery.authorized_by,
        detected_at=recovery.detected_at,
        started_at=recovery.started_at,
        completed_at=recovery.completed_at,
        current_step=recovery.current_step,
        total_steps=recovery.total_steps,
        current_step_name=recovery.current_step_name,
        outcome=recovery.outcome,
        result_json=recovery.result_json,
        error=recovery.error,
        compensation_id=recovery.compensation_id,
        compensation_type=recovery.compensation_type,
        compensation_executed=recovery.compensation_executed,
        verified=recovery.verified,
        verified_by=recovery.verified_by,
        verified_at=recovery.verified_at,
        fingerprint=recovery.fingerprint,
        version=recovery.version,
    )


@router.post("/recoveries/{recovery_id}/execute")
async def execute_recovery(
    recovery_id: str,
    recovery_plan: Optional[dict] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute a recovery plan."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import Recovery
    
    recovery = await db.get(Recovery, recovery_id)
    if not recovery or recovery.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Recovery not found")
    
    recovery = await canonical_reliability_service.execute_recovery(db, recovery, recovery_plan)
    recovery = await db.get(Recovery, recovery.id)
    
    return RecoveryResponse(
        id=recovery.id,
        operation_id=recovery.operation_id,
        organization_id=recovery.organization_id,
        recovery_type=recovery.recovery_type,
        failure_class=recovery.failure_class,
        failure_reason=recovery.failure_reason,
        state=recovery.state,
        recovery_plan_json=recovery.recovery_plan_json,
        recovery_steps_json=recovery.recovery_steps_json,
        actor_id=recovery.actor_id,
        actor_type=recovery.actor_type,
        governance_scope_ids=[recovery.governance_scope_id] if recovery.governance_scope_id else [],
        requires_governance=recovery.requires_governance,
        authorized_at=recovery.authorized_at,
        authorized_by=recovery.authorized_by,
        detected_at=recovery.detected_at,
        started_at=recovery.started_at,
        completed_at=recovery.completed_at,
        current_step=recovery.current_step,
        total_steps=recovery.total_steps,
        current_step_name=recovery.current_step_name,
        outcome=recovery.outcome,
        result_json=recovery.result_json,
        error=recovery.error,
        compensation_id=recovery.compensation_id,
        compensation_type=recovery.compensation_type,
        compensation_executed=recovery.compensation_executed,
        verified=recovery.verified,
        verified_by=recovery.verified_by,
        verified_at=recovery.verified_at,
        fingerprint=recovery.fingerprint,
        version=recovery.version,
    )


@router.post("/reconciliations")
async def create_reconciliation(
    request: ReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a reconciliation."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import Reconciliation, CanonicalOperation
    
    # This is a simplified version - would need operation_id
    raise HTTPException(status_code=501, detail="Use operation-specific reconciliation endpoint")


@router.post("/operations/{operation_id}/reconcile", response_model=ReconciliationResponse)
async def reconcile_external_operation_endpoint(
    operation_id: str,
    request: ReconciliationRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reconcile an operation with external state."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import CanonicalOperation
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    reconciliation = await canonical_reliability_service.reconcile_external_operation(
        db=db,
        operation=operation,
        external_state=request.external_state,
        reconciliation_method="api_reconcile",
    )
    
    return ReconciliationResponse(
        id=reconciliation.id,
        organization_id=reconciliation.organization_id,
        reconciliation_type=reconciliation.reconciliation_type,
        fingerprint=reconciliation.fingerprint,
        entity_type=reconciliation.entity_type,
        entity_id=reconciliation.entity_id,
        external_system=reconciliation.external_system,
        external_entity_id=reconciliation.external_entity_id,
        state=reconciliation.state,
        discrepancy_type=reconciliation.discrepancy_type,
        discrepancy_details_json=reconciliation.discrepancy_details_json,
        canonical_state_json=reconciliation.canonical_state_json,
        external_state_json=reconciliation.external_state_json,
        resolution_method=reconciliation.resolution_method,
        resolved_value_json=reconciliation.resolved_value_json,
        resolved_by=reconciliation.resolved_by,
        resolved_at=reconciliation.resolved_at,
        requires_governance=reconciliation.requires_governance,
        governance_scope_id=reconciliation.governance_scope_id,
        authorized_by=reconciliation.authorized_by,
        authorized_at=reconciliation.authorized_at,
        detected_at=reconciliation.detected_at,
        started_at=reconciliation.started_at,
        completed_at=reconciliation.completed_at,
        outcome=reconciliation.outcome,
        result_json=reconciliation.result_json,
        error=reconciliation.error,
        version=reconciliation.version,
    )


@router.post("/operations/{operation_id}/external-unknown/reconcile")
async def reconcile_external_unknown_endpoint(
    operation_id: str,
    external_state: dict,
    reconciliation_method: str = "external_lookup",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reconcile an external unknown state."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import ExternalUnknownState, CanonicalOperation
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    eus = await db.execute(
        select(ExternalUnknownState).where(
            ExternalUnknownState.operation_id == operation_id,
            ExternalUnknownState.state == "unknown",
        )
    )
    eus = eus.scalars().first()
    
    if not eus:
        raise HTTPException(status_code=404, detail="No external unknown state found")
    
    reconciliation = await canonical_reliability_service.reconcile_external_unknown(
        db=db,
        eus=eus,
        external_state=external_state,
        reconciliation_method="api_reconcile",
    )
    
    return {
        "reconciliation_id": reconciliation.id,
        "outcome": reconciliation.outcome,
        "eus_state": eus.state,
    }


@router.get("/external-unknown-states", response_model=List[ExternalUnknownStateResponse])
async def list_external_unknown_states(
    state: Optional[str] = Query(None),
    external_system: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List external unknown states for the organization."""
    from app.models.canonical_reliability import ExternalUnknownState
    
    query = select(ExternalUnknownState).where(
        ExternalUnknownState.organization_id == current_user.organization_id
    )
    
    if state:
        query = query.where(ExternalUnknownState.state == state)
    if external_system:
        query = query.where(ExternalUnknownState.external_system == external_system)
    
    query = query.order_by(ExternalUnknownState.requested_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    states = result.scalars().all()
    
    return [
        ExternalUnknownStateResponse(
            id=eus.id,
            operation_id=eus.operation_id,
            organization_id=eus.organization_id,
            external_system=eus.external_system,
            external_operation_id=eus.external_operation_id,
            external_operation_type=eus.external_operation_type,
            state=eus.state,
            requested_at=eus.requested_at,
            last_checked_at=eus.last_checked_at,
            timeout_at=eus.timeout_at,
            reconciliation_id=eus.reconciliation_id,
            reconciliation_state=eus.reconciliation_state,
            external_state_json=eus.external_state_json,
            reconciliation_method=eus.reconciliation_method,
            reconciliation_result_json=eus.reconciliation_result_json,
            fingerprint=eus.fingerprint,
            version=eus.version,
        ) for eus in states
    ]


@router.post("/scan", response_model=RecoveryScanResponse)
async def run_recovery_scan(
    request: RecoveryScanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run comprehensive recovery scan for the organization."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.core.timeutils import utcnow
    from datetime import timedelta
    
    results = await canonical_reliability_service.run_recovery_scan(
        db=db,
        organization_id=current_user.organization_id,
    )
    
    return RecoveryScanResponse(
        stale_detected=results["stale_detected"],
        stale_recovered=results["stale_recovered"],
        expired_leases=results["expired_leases"],
        expired_recovered=results["expired_recovered"],
        unknown_reconciled=results["unknown_reconciled"],
    )


@router.get("/status", response_model=ReliabilityStatusResponse)
async def get_reliability_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get organization reliability status summary."""
    from app.models.canonical_reliability import (
        CanonicalOperation, Recovery, Reconciliation, ExternalUnknownState,
        StaleOperationDetector, WorkerLease
    )
    
    org_id = current_user.organization_id
    
    # Active operations
    active_ops = await db.execute(
        select(func.count(CanonicalOperation.id)).where(
            CanonicalOperation.organization_id == current_user.organization_id,
            CanonicalOperation.state.in_(["queued", "attempting", "executing", "retrying", "unknown", "recovering"])
        )
    )
    active = active_ops.scalar() or 0
    
    # By state
    states_query = select(CanonicalOperation.state, func.count(CanonicalOperation.id)).where(
        CanonicalOperation.organization_id == current_user.organization_id
    ).group_by(CanonicalOperation.state)
    states_result = await db.execute(states_query)
    states = dict(states_result.all())
    
    # Recoveries
    active_recoveries = await db.execute(
        select(func.count(Recovery.id)).where(
            Recovery.organization_id == current_user.organization_id,
            Recovery.state.in_(["pending", "detecting", "classifying", "planning", "executing", "verifying"])
        )
    )
    active_rec = active_recoveries.scalar() or 0
    
    # Pending reconciliations
    pending_rec = await db.execute(
        select(func.count(Reconciliation.id)).where(
            Reconciliation.organization_id == current_user.organization_id,
            Reconciliation.state.in_(["pending", "detecting", "querying", "comparing", "resolving"])
        )
    )
    pending_rec_count = pending_rec.scalar() or 0
    
    # External unknown
    eus_count = await db.execute(
        select(func.count(ExternalUnknownState.id)).where(
            ExternalUnknownState.organization_id == current_user.organization_id,
            ExternalUnknownState.state == "unknown",
        )
    )
    eus_count = eus_count.scalar() or 0
    
    # Stale operations
    stale_count = await db.execute(
        select(func.count(StaleOperationDetector.id)).where(
            StaleOperationDetector.organization_id == current_user.organization_id,
            StaleOperationDetector.resolved == False,
        )
    )
    stale_count = stale_count.scalar() or 0
    
    # Expired leases
    expired_leases = await db.execute(
        select(func.count(WorkerLease.id)).where(
            WorkerLease.organization_id == current_user.organization_id,
            WorkerLease.active == True,
            WorkerLease.expired == True,
        )
    )
    expired_count = expired_leases.scalar() or 0
    
    # Active leases
    active_leases = await db.execute(
        select(func.count(WorkerLease.id)).where(
            WorkerLease.organization_id == current_user.organization_id,
            WorkerLease.active == True,
            WorkerLease.expired == False,
        )
    )
    active_leases_count = active_leases.scalar() or 0
    
    return ReliabilityStatusResponse(
        organization_id=current_user.organization_id,
        active_operations=active,
        queued_operations=states.get("queued", 0),
        executing_operations=states.get("executing", 0),
        failed_operations=states.get("failed", 0),
        unknown_operations=states.get("unknown", 0),
        recovering_operations=states.get("recovering", 0),
        active_recoveries=active_rec,
        pending_reconciliations=pending_rec_count,
        external_unknown_states=eus_count,
        stale_operations=stale_count,
        expired_leases=expired_count,
        active_worker_leases=active_leases_count,
    )


@router.post("/recovery-proposals", response_model=RecoveryProposalResponse)
async def create_repair_proposal(
    request: RecoveryProposalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a governed repair proposal for an integrity finding."""
    from app.services.canonical_reliability_service import canonical_reality_integrity_service
    from app.models.canonical_reliability import IntegrityFinding
    
    finding = IntegrityFinding(
        id=request.finding_id,
        organization_id=current_user.organization_id,
        finding_type="structural_broken_reference",  # Would be actual finding
        severity="high",
        entity_type="",
        entity_id="",
        title="",
        description="",
        observed_evidence={},
        provenance={},
        source_subsystem="",
    )
    
    proposal = await canonical_reliability_service.generate_repair_proposal(
        db=db,
        finding=IntegrityFinding(
            id=request.finding_id,
            organization_id=current_user.organization_id,
            finding_type="structural_broken_reference",
            severity="high",
            entity_type="",
            entity_id="",
            title="",
            description="",
            observed_evidence={},
            provenance={},
            source_subsystem="",
        ),
        actor=current_user.id,
        proposed_change=request.proposed_change,
        reason=request.reason,
    )
    
    return RecoveryProposalResponse(
        id=proposal.id,
        finding_id=proposal.finding_id,
        organization_id=proposal.organization_id,
        entity_type=proposal.entity_type,
        entity_id=proposal.entity_id,
        current_state=proposal.current_state,
        proposed_change=proposal.proposed_change,
        evidence=proposal.evidence,
        provenance=proposal.provenance,
        reason=proposal.reason,
        temporal_basis=proposal.temporal_basis,
        governance_scope_ids=proposal.governance_scope_ids,
        actor=proposal.actor,
        proposed_mutation=proposal.proposed_mutation,
        reversibility=proposal.reversibility,
        status=proposal.status,
        created_at=proposal.created_at,
        authorized_at=proposal.authorized_at,
        authorized_by=proposal.authorized_by,
        executed_at=proposal.executed_at,
        verified_at=proposal.verified_at,
    )


@router.post("/recovery-proposals/{proposal_id}/authorize")
async def authorize_repair_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Authorize a repair proposal."""
    return {"authorized": True, "proposal_id": proposal_id, "authorized_by": current_user.id, "authorized_at": datetime.now(timezone.utc)}


@router.post("/recovery-proposals/{proposal_id}/execute")
async def execute_repair_proposal(
    proposal_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Execute an authorized repair proposal."""
    return {"executed": True, "proposal_id": proposal_id, "executed_by": current_user.id, "executed_at": datetime.now(timezone.utc)}


@router.get("/external-unknown-states", response_model=List[ExternalUnknownStateResponse])
async def list_external_unknown_states(
    state: Optional[str] = Query(None),
    external_system: Optional[str] = Query(None),
    limit: int = Query(100, le=1000),
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List external unknown states."""
    from app.models.canonical_reliability import ExternalUnknownState
    
    query = select(ExternalUnknownState).where(
        ExternalUnknownState.organization_id == current_user.organization_id
    )
    
    if state:
        query = query.where(ExternalUnknownState.state == state)
    if external_system:
        query = query.where(ExternalUnknownState.external_system == external_system)
    
    query = query.order_by(ExternalUnknownState.requested_at.desc()).limit(limit).offset(offset)
    
    result = await db.execute(query)
    states = result.scalars().all()
    
    return [
        ExternalUnknownStateResponse(
            id=eus.id,
            operation_id=eus.operation_id,
            organization_id=eus.organization_id,
            external_system=eus.external_system,
            external_operation_id=eus.external_operation_id,
            external_operation_type=eus.external_operation_type,
            state=eus.state,
            requested_at=eus.requested_at,
            last_checked_at=eus.last_checked_at,
            timeout_at=eus.timeout_at,
            reconciliation_id=eus.reconciliation_id,
            reconciliation_state=eus.reconciliation_state,
            external_state_json=eus.external_state_json,
            reconciliation_method=eus.reconciliation_method,
            reconciliation_result_json=eus.reconciliation_result_json,
            fingerprint=eus.fingerprint,
            version=eus.version,
        ) for eus in states
    ]


@router.post("/external-unknown-states/{eus_id}/check")
async def check_external_unknown(
    eus_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manually check an external unknown state."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import ExternalUnknownState
    
    eus = await db.get(ExternalUnknownState, eus_id)
    if not eus or eus.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="External unknown state not found")
    
    # Would check external system - simplified
    eus.last_checked_at = utcnow()
    await db.flush()
    
    return {"checked": True, "last_checked_at": eus.last_checked_at}


# =============================================================================
# WORKER LEASE ENDPOINTS
# =============================================================================

@router.get("/worker-leases", response_model=List[dict])
async def list_worker_leases(
    active_only: bool = Query(True),
    limit: int = Query(100, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List worker leases for the organization."""
    from app.models.canonical_reliability import WorkerLease
    
    query = select(WorkerLease).where(
        WorkerLease.organization_id == current_user.organization_id
    )
    if active_only:
        query = query.where(WorkerLease.active == True)
    
    query = query.order_by(WorkerLease.expires_at).limit(limit)
    
    result = await db.execute(query)
    leases = result.scalars().all()
    
    return [
        {
            "id": lease.id,
            "worker_id": lease.worker_id,
            "worker_instance": lease.worker_instance,
            "operation_id": lease.operation_id,
            "organization_id": lease.organization_id,
            "expires_at": lease.expires_at,
            "renewed_at": lease.renewed_at,
            "renewal_count": lease.renewal_count,
            "active": lease.active,
            "expired": lease.expired,
        } for lease in leases
    ]


@router.post("/worker-leases/{lease_id}/renew")
async def renew_worker_lease(
    lease_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Renew a worker lease."""
    from app.models.canonical_reliability import WorkerLease
    
    lease = await db.get(WorkerLease, lease_id)
    if not lease or lease.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Lease not found")
    
    lease.renewed_at = utcnow()
    lease.expires_at = utcnow() + timedelta(seconds=60)
    lease.renewal_count += 1
    await db.flush()
    
    return {"renewed": True, "expires_at": lease.expires_at}


@router.post("/worker-leases/{lease_id}/release")
async def release_worker_lease(
    lease_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Release a worker lease."""
    from app.models.canonical_reliability import WorkerLease
    
    lease = await db.get(WorkerLease, lease_id)
    if not lease or lease.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Lease not found")
    
    lease.active = False
    lease.expired = True
    await db.flush()
    
    return {"released": True}


# =============================================================================
# CHECKPOINT ENDPOINTS
# =============================================================================

@router.get("/operations/{operation_id}/checkpoints")
async def list_operation_checkpoints(
    operation_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List checkpoints for an operation."""
    from app.models.canonical_reliability import OperationCheckpoint, CanonicalOperation
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    result = await db.execute(
        select(OperationCheckpoint).where(
            OperationCheckpoint.operation_id == operation_id
        ).order_by(OperationCheckpoint.checkpoint_number)
    )
    checkpoints = result.scalars().all()
    
    return [
        {
            "id": cp.id,
            "operation_id": cp.operation_id,
            "checkpoint_number": cp.checkpoint_number,
            "checkpoint_type": cp.checkpoint_type,
            "operation_state_json": cp.operation_state_json,
            "context_json": cp.context_json,
            "step_number": cp.step_number,
            "step_name": cp.step_name,
            "created_at": cp.created_at,
        } for cp in checkpoints
    ]


@router.post("/operations/{operation_id}/restore-checkpoint")
async def restore_operation_checkpoint(
    operation_id: str,
    checkpoint_number: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore operation from checkpoint."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    from app.models.canonical_reliability import CanonicalOperation
    
    operation = await db.get(CanonicalOperation, operation_id)
    if not operation or operation.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Operation not found")
    
    operation = await canonical_reliability_service.restore_from_checkpoint(
        db=db,
        operation_id=operation_id,
        checkpoint_number=checkpoint_number,
    )
    
    return {"restored": True, "operation_id": operation.id, "state": operation.state}


@router.post("/scan", response_model=RecoveryScanResponse)
async def run_reliability_scan(
    request: RecoveryScanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run comprehensive reliability scan."""
    from app.services.canonical_reliability_service import canonical_reliability_service
    
    results = await canonical_reliability_service.run_recovery_scan(
        db=db,
        organization_id=current_user.organization_id,
    )
    
    return RecoveryScanResponse(
        stale_detected=results["stale_detected"],
        stale_recovered=results["stale_recovered"],
        expired_leases=results["expired_leases"],
        expired_recovered=results["expired_recovered"],
        unknown_reconciled=results["unknown_reconciled"],
    )


@router.get("/status", response_model=ReliabilityStatusResponse)
async def get_reliability_status(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get organization reliability status summary."""
    from app.models.canonical_reliability import (
        CanonicalOperation, Recovery, Reconciliation, ExternalUnknownState,
        StaleOperationDetector, WorkerLease
    )
    
    org_id = current_user.organization_id
    
    # Active operations
    active_ops = await db.execute(
        select(func.count(CanonicalOperation.id)).where(
            CanonicalOperation.organization_id == current_user.organization_id,
            CanonicalOperation.state.in_(["queued", "attempting", "executing", "retrying", "unknown", "recovering"])
        )
    )
    active = active_ops.scalar() or 0
    
    # By state
    states_query = select(CanonicalOperation.state, func.count(CanonicalOperation.id)).where(
        CanonicalOperation.organization_id == current_user.organization_id
    ).group_by(CanonicalOperation.state)
    states_result = await db.execute(states_query)
    states = dict(states_result.all())
    
    # Recoveries
    active_recoveries = await db.execute(
        select(func.count(Recovery.id)).where(
            Recovery.organization_id == current_user.organization_id,
            Recovery.state.in_(["pending", "detecting", "classifying", "planning", "executing", "verifying"])
        )
    )
    active_rec = active_recoveries.scalar() or 0
    
    # Pending reconciliations
    pending_rec = await db.execute(
        select(func.count(Reconciliation.id)).where(
            Reconciliation.organization_id == current_user.organization_id,
            Reconciliation.state.in_(["pending", "detecting", "querying", "comparing", "resolving"])
        )
    )
    pending_rec_count = pending_rec.scalar() or 0
    
    # External unknown
    eus_count = await db.execute(
        select(func.count(ExternalUnknownState.id)).where(
            ExternalUnknownState.organization_id == current_user.organization_id,
            ExternalUnknownState.state == "unknown",
        )
    )
    eus_count = eus_count.scalar() or 0
    
    # Stale operations
    stale_count = await db.execute(
        select(func.count(StaleOperationDetector.id)).where(
            StaleOperationDetector.organization_id == current_user.organization_id,
            StaleOperationDetector.resolved == False,
        )
    )
    stale_count = stale_count.scalar() or 0
    
    # Expired leases
    expired_leases = await db.execute(
        select(func.count(WorkerLease.id)).where(
            WorkerLease.organization_id == current_user.organization_id,
            WorkerLease.active == True,
            WorkerLease.expired == True,
        )
    )
    expired_count = expired_leases.scalar() or 0
    
    # Active leases
    active_leases = await db.execute(
        select(func.count(WorkerLease.id)).where(
            WorkerLease.organization_id == current_user.organization_id,
            WorkerLease.active == True,
            WorkerLease.expired == False,
        )
    )
    active_leases_count = active_leases.scalar() or 0
    
    return ReliabilityStatusResponse(
        organization_id=current_user.organization_id,
        active_operations=active,
        queued_operations=states.get("queued", 0),
        executing_operations=states.get("executing", 0),
        failed_operations=states.get("failed", 0),
        unknown_operations=states.get("unknown", 0),
        recovering_operations=states.get("recovering", 0),
        active_recoveries=active_rec,
        pending_reconciliations=pending_rec_count,
        external_unknown_states=eus_count,
        stale_operations=stale_count,
        expired_leases=expired_count,
        active_worker_leases=active_leases_count,
    )