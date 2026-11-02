"""External Operation Service — VCOS canonical action → external system execution.

Implements:
- External operation lifecycle (VCOS → external system)
- Governance chain verification
- External request execution
- Result verification
- UNKNOWN state handling (35-H semantics)
- Retry with canonical recovery

Flow:
VCOS operation
    ↓
ExternalOperation
    ↓
external request
    ↓
result
    ↓
verification
    ↓
canonical outcome
    ↓
reconciliation

If external result becomes ambiguous → UNKNOWN.
Use 35-H/35-H recovery semantics.
Never assume timeout == failure.
Never assume timeout == success.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, and_, or_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    ExternalOperation,
    ConnectorInstance,
    Connector,
    ExternalIdentityMapping,
    EXTERNAL_EVENT_STATES,
)
from app.models.canonical_reliability import (
    CanonicalOperation,
    OperationAttempt,
    ExternalUnknownState,
    WorkerLease,
    OperationCheckpoint,
)
from app.intelligence.canonical_mutation import canonical_mutation_boundary
from app.intelligence.canonical_types import (
    ConcurrencyContext,
    ConcurrencyControlType,
    ConcurrencyResult,
)
from app.intelligence.company_context import CallerAccess

logger = logging.getLogger("vcos.integration.operation")


class OperationType(Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    TRANSITION = "transition"
    COMMENT = "comment"
    ASSIGN = "assign"


class AmbiguousExternalResultError(Exception):
    """External request may have been delivered but its result is unknowable.

    Raised for transport outcomes where the request may or may not have reached
    the external system (timeout mid-request, connection reset after send,
    gateway ambiguity). Callers must mark the operation UNKNOWN — never
    failure, never success (35-H semantics).
    """


class ExternalOperationState(Enum):
    PENDING = "pending"
    QUEUED = "queued"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"  # 35-H: external result ambiguous


@dataclass
class OperationRequest:
    """Request to execute an external operation."""
    source_action_id: Optional[str]
    source_decision_id: Optional[str]
    source_authorization_id: Optional[str]
    source_commitment_id: Optional[str]
    operation_type: OperationType
    target_entity_type: str
    target_external_id: Optional[str]
    payload: Dict[str, Any]
    governance_verified: bool = False
    max_retries: int = 3


class ExternalOperationService:
    """External operation service — VCOS canonical → external system.
    
    Ensures all external mutations go through governance and
    are verified against external reality.
    """
    
    # ------------------------------------------------------------ Operation Lifecycle
    
    async def create_operation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        request: OperationRequest,
        caller: CallerAccess,
    ) -> ExternalOperation:
        """Create a new external operation request.
        
        All external mutations must go through this service.
        Direct external API calls are forbidden.
        """
        instance = await db.get(ConnectorInstance, connector_instance_id)
        if not instance or instance.organization_id != organization_id:
            raise ValueError("Invalid connector instance")
        
        # Verify governance chain
        if not request.governance_verified:
            raise ValueError("Operation must be governance-verified")
        
        # Verify at least one canonical source is provided
        if not any([request.source_action_id, request.source_decision_id, request.source_authorization_id, request.source_commitment_id]):
            raise ValueError("Operation must have canonical source (decision/authorization/commitment/action)")
        
        # Verify connector supports the requested operation
        connector = await db.get(Connector, instance.connector_id)
        if not connector:
            raise ValueError("Connector not found")
        
        # Verify connector supports the requested operation type
        if request.operation_type.value not in connector.outbound_capabilities:
            raise ValueError(f"Connector does not support operation type: {request.operation_type.value}")
        
        # Verify connector supports the target entity type
        if request.target_entity_type not in connector.supported_entities:
            raise ValueError(f"Connector does not support entity type: {request.target_entity_type}")
        
        # Verify authorization exists for action
        if request.source_authorization_id:
            from app.models.execution_strategy import CompanyAuthorization
            auth = await db.get(CompanyAuthorization, request.source_authorization_id)
            if not auth or auth.organization_id != organization_id:
                raise ValueError("Invalid authorization")
            if auth.state not in ("approved", "conditional"):
                raise ValueError("Authorization not approved")
        
        # Verify commitment exists if provided
        if request.source_commitment_id:
            from app.models.execution_strategy import CompanyCommitment
            commitment = await db.get(CompanyCommitment, request.source_commitment_id)
            if not commitment or commitment.organization_id != organization_id:
                raise ValueError("Invalid commitment")
        
        # Create operation record
        operation = ExternalOperation(
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            source_action_id=request.source_action_id,
            source_decision_id=request.source_decision_id,
            source_authorization_id=request.source_authorization_id,
            source_commitment_id=request.source_commitment_id,
            operation_type=request.operation_type.value,
            target_entity_type=request.target_entity_type,
            target_external_id=request.target_external_id,
            payload=request.payload,
            governance_verified=request.governance_verified,
            max_retries=request.max_retries,
            state="pending",
            queued_at=utcnow(),
        )
        db.add(operation)
        await db.flush()
        
        await publish_event(
            db,
            name="external_operation.queued",
            organization_id=organization_id,
            actor_id=caller.employee_id,
            payload={
                "operation_id": operation.id,
                "connector_instance_id": connector_instance_id,
                "operation_type": request.operation_type.value,
                "target_entity_type": request.target_entity_type,
            },
        )
        
        return operation

    async def execute_operation(
        self,
        db: AsyncSession,
        operation_id: str,
        caller: CallerAccess,
    ) -> ExternalOperation:
        """Execute a queued external operation."""
        operation = await db.get(ExternalOperation, operation_id)
        if not operation:
            raise ValueError("Operation not found")
        
        if operation.state != "pending":
            raise ValueError(f"Operation not in pending state: {operation.state}")
        
        instance = await db.get(ConnectorInstance, operation.connector_instance_id)
        if not instance:
            raise ValueError("Connector instance not found")
        
        connector = await db.get(Connector, instance.connector_id)
        if not connector:
            raise ValueError("Connector not found")
        
        # Update state to executing
        operation.state = "executing"
        operation.started_at = utcnow()
        await db.flush()
        
        try:
            # Execute through provider-specific adapter
            result = await self._execute_with_adapter(
                db=db,
                instance=instance,
                connector=connector,
                operation=operation,
            )
            
            operation.external_operation_id = result.get("external_operation_id")
            operation.result_payload = result.get("payload")
            operation.completed_at = utcnow()
            operation.state = "completed"
            
        except AmbiguousExternalResultError as e:
            # External outcome unknowable — mark UNKNOWN (35-H semantics),
            # never silently failed or completed.
            logger.warning(f"External operation outcome ambiguous: {operation.id}: {e}")
            operation.retry_count += 1
            await self._mark_unknown(db, operation, str(e), caller)
            await db.flush()
            return operation
        except NotImplementedError as e:
            # Capability gap — explicit, non-retryable failure (never faked success)
            logger.error(f"External operation unsupported: {operation.id}: {e}")
            operation.state = "failed"
            operation.error = str(e)
            operation.completed_at = utcnow()
            await db.flush()
            raise
        except Exception as e:
            logger.error(f"External operation failed: {operation.id}: {e}")
            
            operation.retry_count += 1
            operation.error = str(e)
            
            if operation.retry_count >= operation.max_retries:
                operation.state = "failed"
                operation.completed_at = utcnow()
            else:
                operation.state = "pending"  # Will retry
            
            await db.flush()
            raise
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_operation.completed",
            organization_id=operation.organization_id,
            payload={
                "operation_id": operation.id,
                "state": operation.state,
                "external_operation_id": operation.external_operation_id,
            },
        )
        
        return operation

    async def _execute_with_adapter(
        self,
        db: AsyncSession,
        instance: ConnectorInstance,
        connector: Connector,
        operation: ExternalOperation,
    ) -> Dict[str, Any]:
        """Execute operation through the provider's connector adapter.

        Honesty rules:
        - No registered adapter, failed authentication, or no outbound
          capability → explicit failure (never a fake success).
        - Ambiguous transport outcome (timeout mid-request, connection reset
          after send) → AmbiguousExternalResultError → UNKNOWN, never failed
          or completed.
        """
        from app.services.adapter_registry import get_adapter

        adapter = get_adapter(connector.provider)
        if adapter is None:
            raise NotImplementedError(
                f"No connector adapter registered for provider '{connector.provider}'"
            )

        if not await adapter.authenticate(instance):
            raise PermissionError(
                f"Connector instance '{instance.id}' failed authentication for provider '{connector.provider}'"
            )

        import httpx

        try:
            return await adapter.execute_operation(
                instance=instance,
                operation_type=operation.operation_type,
                entity_type=operation.target_entity_type,
                external_id=operation.target_external_id,
                payload=operation.payload or {},
                idempotency_key=operation.id,
            )
        except httpx.TimeoutException as e:
            raise AmbiguousExternalResultError(
                f"Timeout with unknown delivery status for provider '{connector.provider}': {e}"
            ) from e
        except httpx.ConnectError as e:
            # Never reached the remote system — safe to treat as failed
            raise ConnectionError(
                f"Could not connect to provider '{connector.provider}': {e}"
            ) from e
        except httpx.TransportError as e:
            raise AmbiguousExternalResultError(
                f"Transport error with unknown delivery status for provider '{connector.provider}': {e}"
            ) from e

    # ------------------------------------------------------------ Verification & Recovery
    
    async def verify_operation(
        self,
        db: AsyncSession,
        operation_id: str,
        external_result: Dict[str, Any],
        caller: CallerAccess,
    ) -> ExternalOperation:
        """Verify external operation result and update canonical state."""
        operation = await db.get(ExternalOperation, operation_id)
        if not operation:
            raise ValueError("Operation not found")
        
        if operation.state not in ("executing", "completed"):
            raise ValueError(f"Cannot verify operation in state: {operation.state}")
        
        # Verify result against payload
        if not self._verify_result(operation, external_result):
            # Mark as UNKNOWN — 35-H semantics
            return await self._mark_unknown(db, operation, "Result verification failed", caller)
        
        # Mark as verified
        operation.verified = True
        operation.verified_at = utcnow()
        operation.observation_received = True
        operation.result_payload = external_result
        
        await db.flush()
        
        # Trigger reconciliation if needed
        await self._trigger_reconciliation(db, operation)
        
        await publish_event(
            db,
            name="external_operation.verified",
            payload={"operation_id": operation.id, "verified_by": caller.employee_id},
        )
        
        return operation

    def _verify_result(self, operation: ExternalOperation, result: Dict) -> bool:
        """Verify external result matches expected outcome."""
        # Basic verification — would be provider-specific
        if "error" in result:
            return False
        if "id" not in result and "external_id" not in result:
            return False
        return True

    async def _mark_unknown(
        self,
        db: AsyncSession,
        operation: ExternalOperation,
        reason: str,
        caller: CallerAccess,
    ) -> ExternalOperation:
        """Mark operation result as UNKNOWN per 35-H semantics.
        
        When external result is ambiguous (timeout, partial response,
        verification failure), mark as UNKNOWN rather than success/failure.
        """
        operation.state = "unknown"
        operation.error = f"UNKNOWN: {reason}"
        operation.observation_received = False
        operation.verified = False
        operation.updated_at = utcnow()
        
        # Create ExternalUnknownState record for reconciliation
        from app.models.canonical_reliability import ExternalUnknownState
        import hashlib
        import json
        fingerprint_data = json.dumps({
            "organization_id": operation.organization_id,
            "operation_id": operation.id,
            "external_system": "connector",
            "operation_type": operation.operation_type,
            "target_external_id": operation.target_external_id,
            "payload": operation.payload,
        }, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(fingerprint_data.encode()).hexdigest()[:160]
        
        unknown = ExternalUnknownState(
            organization_id=operation.organization_id,
            operation_id=operation.id,
            external_system="connector",
            external_operation_id=operation.external_operation_id or f"local-{operation.id}",
            external_operation_type=operation.operation_type,
            request_payload_json=operation.payload,
            request_fingerprint=fingerprint,
            state="unknown",
            fingerprint=fingerprint,
        )
        db.add(unknown)
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_operation.unknown",
            organization_id=operation.organization_id,
            actor_id=caller.employee_id if hasattr(caller, 'employee_id') else None,
            payload={
                "operation_id": operation.id,
                "reason": reason,
            },
        )
        
        return operation

    async def _trigger_reconciliation(
        self,
        db: AsyncSession,
        operation: ExternalOperation,
    ):
        """Trigger reconciliation after successful external operation."""
        # This would integrate with ReconciliationService
        pass

    # ------------------------------------------------------------ Retry & Recovery
    
    async def retry_operation(
        self,
        db: AsyncSession,
        operation_id: str,
        caller: CallerAccess,
    ) -> ExternalOperation:
        """Retry a failed or unknown operation."""
        operation = await db.get(ExternalOperation, operation_id)
        if not operation:
            raise ValueError("Operation not found")
        
        if operation.state not in ("failed", "unknown"):
            raise ValueError(f"Cannot retry operation in state: {operation.state}")
        
        if operation.retry_count >= operation.max_retries:
            raise ValueError("Max retries exceeded")
        
        operation.state = "pending"
        operation.error = None
        operation.updated_at = utcnow()
        await db.flush()
        
        return await self.execute_operation(db, operation_id, caller)

    async def cancel_operation(
        self,
        db: AsyncSession,
        operation_id: str,
        caller: CallerAccess,
        reason: str,
    ) -> ExternalOperation:
        """Cancel a pending operation."""
        operation = await db.get(ExternalOperation, operation_id)
        if not operation:
            raise ValueError("Operation not found")
        
        if operation.state in ("completed", "cancelled"):
            raise ValueError(f"Cannot cancel operation in state: {operation.state}")
        
        operation.state = "cancelled"
        operation.error = f"Cancelled: {reason}"
        operation.completed_at = utcnow()
        operation.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_operation.cancelled",
            payload={"operation_id": operation.id, "reason": reason},
        )
        
        return operation

    # ------------------------------------------------------------ Unknown State Recovery
    
    async def reconcile_unknown(
        self,
        db: AsyncSession,
        unknown_id: str,
        caller: CallerAccess,
        resolved: bool,
        resolution_notes: str,
    ):
        """Reconcile an UNKNOWN external operation."""
        from app.models.canonical_reliability import ExternalUnknownState
        
        unknown = await db.get(ExternalUnknownState, unknown_id)
        if not unknown:
            raise ValueError("Unknown state not found")
        
        # Create reconciliation operation
        operation = ExternalOperation(
            organization_id=unknown.organization_id,
            connector_instance_id="",  # Would need mapping
            source_action_id=unknown.source_operation_id,
            operation_type=unknown.operation_type,
            target_entity_type=unknown.target_entity_type,
            target_external_id=unknown.target_external_id,
            payload=unknown.payload,
            state="pending",
        )
        db.add(operation)
        await db.flush()
        
        if resolved:
            # Retry the operation
            await self.execute_operation(db, operation.id, caller)
        else:
            # Mark as permanently failed
            unknown.state = "resolved_failed"
            unknown.resolution_notes = resolution_notes
            unknown.resolved_at = utcnow()
            unknown.resolved_by = caller.employee_id
        
        unknown.resolved = resolved
        unknown.resolved_at = utcnow()
        unknown.resolved_by = caller.employee_id
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_unknown.reconciled",
            payload={"unknown_id": unknown.id, "resolved": resolved},
        )

    # ------------------------------------------------------------ Query Operations
    
    async def get_operations(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        connector_instance_id: Optional[str] = None,
        state: Optional[str] = None,
        source_action_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List:
        query = select(ExternalOperation).where(
            ExternalOperation.organization_id == organization_id
        )
        
        if connector_instance_id:
            query = query.where(ExternalOperation.connector_instance_id == connector_instance_id)
        if state:
            query = query.where(ExternalOperation.state == state)
        if source_action_id:
            query = query.where(ExternalOperation.source_action_id == source_action_id)
        
        query = query.order_by(desc(ExternalOperation.created_at)).limit(limit).offset(offset)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_unknown_operations(
        self,
        db: AsyncSession,
        organization_id: str,
        limit: int = 100,
    ) -> List:
        from app.models.canonical_reliability import ExternalUnknownState
        
        result = await db.execute(
            select(ExternalUnknownState).where(
                ExternalUnknownState.organization_id == organization_id,
                ExternalUnknownState.resolved == False,
            ).order_by(desc(ExternalUnknownState.created_at)).limit(limit)
        )
        return list(result.scalars().all())

    async def get_operations_by_action(
        self,
        db: AsyncSession,
        source_action_id: str,
    ) -> List:
        result = await db.execute(
            select(ExternalOperation).where(
                ExternalOperation.source_action_id == source_action_id
            ).order_by(desc(ExternalOperation.created_at))
        )
        return list(result.scalars().all())


# Global instance
external_operation_service = ExternalOperationService()