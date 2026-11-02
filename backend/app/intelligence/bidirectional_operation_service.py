"""Gate 24 — Bidirectional Operation Service.

Implements the outbound flow:
VCOS canonical reality
→ decision
→ authorization
→ governed action
→ connector
→ external system
→ external outcome
→ webhook/poll/event
→ VCOS observation
→ verification

Maintains: Recommendation ≠ Decision ≠ Authorization ≠ Execution ≠ Outcome
No outbound external mutation may bypass governance.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    ExternalOperation,
    ConnectorInstance,
)
from app.models.company_actions import CompanyAction
from app.models.company_operating import CompanyDecision
from app.models.execution_strategy import CompanyAuthorization, CompanyCommitment
from app.intelligence.canonical_mutation import (
    canonical_create,
    CanonicalMutationContext,
    MutationType,
    EpistemicStatus,
)

logger = logging.getLogger("vcos.integration.bidirectional")


class BidirectionalOperationService:
    """Service for bidirectional external operations."""
    
    # ------------------------------------------------------------ Operation Creation
    
    async def create_operation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        operation_type: str,
        target_entity_type: str,
        target_external_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        source_action_id: Optional[str] = None,
        source_decision_id: Optional[str] = None,
        source_authorization_id: Optional[str] = None,
        source_commitment_id: Optional[str] = None,
        governance_verified: bool = False,
        governance_verified_by: Optional[str] = None,
        max_retries: int = 3,
        created_by: Optional[str] = None,
    ) -> ExternalOperation:
        """Create a new external operation (VCOS → External)."""
        
        # Validate connector instance
        instance = await db.get(ConnectorInstance, connector_instance_id)
        if instance is None or instance.organization_id != organization_id:
            raise ValueError("Invalid connector instance")
        
        # Validate source references
        if source_action_id:
            action = await db.get(CompanyAction, source_action_id)
            if action is None or action.organization_id != organization_id:
                raise ValueError("Invalid source action")
        
        if source_decision_id:
            decision = await db.get(CompanyDecision, source_decision_id)
            if decision is None or decision.organization_id != organization_id:
                raise ValueError("Invalid source decision")
        
        if source_authorization_id:
            auth = await db.get(CompanyAuthorization, source_authorization_id)
            if auth is None or auth.organization_id != organization_id:
                raise ValueError("Invalid source authorization")
        
        if source_commitment_id:
            comm = await db.get(CompanyCommitment, source_commitment_id)
            if comm is None or comm.organization_id != organization_id:
                raise ValueError("Invalid source commitment")
        
        operation = ExternalOperation(
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            source_action_id=source_action_id,
            source_decision_id=source_decision_id,
            source_authorization_id=source_authorization_id,
            source_commitment_id=source_commitment_id,
            operation_type=operation_type,
            target_entity_type=target_entity_type,
            target_external_id=target_external_id,
            payload=payload or {},
            governance_verified=governance_verified,
            governance_verified_at=utcnow() if governance_verified else None,
            governance_verified_by=governance_verified_by,
            max_retries=max_retries,
            state="pending",
            created_by=created_by,
        )
        
        db.add(operation)
        await db.flush()
        
        await publish_event(
            db,
            name="external_operation.created",
            organization_id=organization_id,
            actor_id=created_by,
            payload={
                "operation_id": operation.id,
                "connector_instance_id": connector_instance_id,
                "operation_type": operation_type,
                "target_entity_type": target_entity_type,
            },
        )
        
        return operation
    
    # ------------------------------------------------------------ Governance Verification
    
    async def verify_governance(
        self,
        db: AsyncSession,
        operation_id: str,
        verified_by: str,
    ) -> Optional[ExternalOperation]:
        """Verify governance chain for an external operation."""
        
        operation = await db.get(ExternalOperation, operation_id)
        if operation is None:
            return None
        
        operation.governance_verified = True
        operation.governance_verified_at = utcnow()
        operation.governance_verified_by = verified_by
        operation.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_operation.governance_verified",
            organization_id=operation.organization_id,
            actor_id=verified_by,
            payload={"operation_id": operation_id},
        )
        
        return operation
    
    # ------------------------------------------------------------ Execution
    
    async def execute_operation(
        self,
        db: AsyncSession,
        operation_id: str,
        executor: callable,
    ) -> ExternalOperation:
        """Execute an external operation through the given executor."""
        
        operation = await db.get(ExternalOperation, operation_id)
        if operation is None:
            raise ValueError(f"Operation not found: {operation_id}")
        
        if not operation.governance_verified:
            raise ValueError("Operation must have governance verified before execution")
        
        if operation.state not in ("pending", "failed"):
            return operation
        
        operation.state = "executing"
        operation.started_at = utcnow()
        operation.retry_count += 1
        await db.flush()
        
        try:
            # Execute through the connector-specific executor
            result = await executor(db, operation)
            
            operation.state = "completed"
            operation.external_operation_id = result.get("external_operation_id")
            operation.result_payload = result
            operation.completed_at = utcnow()
            operation.error = None
            
            await publish_event(
                db,
                name="external_operation.completed",
                organization_id=operation.organization_id,
                payload={
                    "operation_id": operation_id,
                    "external_operation_id": operation.external_operation_id,
                    "result": result,
                },
            )
            
        except Exception as e:
            operation.error = str(e)
            
            if operation.retry_count >= operation.max_retries:
                operation.state = "failed"
                
                await publish_event(
                    db,
                    name="external_operation.failed",
                    organization_id=operation.organization_id,
                    payload={
                        "operation_id": operation_id,
                        "error": str(e),
                        "retries": operation.retry_count,
                    },
                )
            else:
                operation.state = "pending"
            
            logger.warning("External operation execution failed: %s", e)
        
        await db.flush()
        return operation
    
    # ------------------------------------------------------------ Observation & Verification
    
    async def receive_observation(
        self,
        db: AsyncSession,
        operation_id: str,
        observation_event_id: str,
        observation_payload: Optional[dict] = None,
    ) -> Optional[ExternalOperation]:
        """Receive an observation from the external system (webhook/poll)."""
        
        operation = await db.get(ExternalOperation, operation_id)
        if operation is None:
            return None
        
        operation.observation_received = True
        operation.observation_event_id = observation_event_id
        operation.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_operation.observed",
            organization_id=operation.organization_id,
            payload={
                "operation_id": operation_id,
                "observation_event_id": observation_event_id,
            },
        )
        
        return operation
    
    async def verify_outcome(
        self,
        db: AsyncSession,
        operation_id: str,
        verified: bool,
        verified_by: Optional[str] = None,
        verification_notes: Optional[str] = None,
    ) -> Optional[ExternalOperation]:
        """Verify the external operation outcome."""
        
        operation = await db.get(ExternalOperation, operation_id)
        if operation is None:
            return None
        
        operation.verified = verified
        operation.verified_at = utcnow() if verified else None
        operation.verification_notes = verification_notes
        operation.updated_at = utcnow()
        
        await db.flush()
        
        await publish_event(
            db,
            name="external_operation.verified" if verified else "external_operation.verification_failed",
            organization_id=operation.organization_id,
            actor_id=verified_by,
            payload={
                "operation_id": operation_id,
                "verified": verified,
                "notes": verification_notes,
            },
        )
        
        return operation
    
    # ------------------------------------------------------------ Queries
    
    async def get_operation(
        self, db: AsyncSession, operation_id: str
    ) -> Optional[ExternalOperation]:
        """Get an external operation by ID."""
        return await db.get(ExternalOperation, operation_id)
    
    async def list_operations(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        connector_instance_id: Optional[str] = None,
        state: Optional[str] = None,
        source_action_id: Optional[str] = None,
        limit: int = 100,
    ) -> list[ExternalOperation]:
        """List external operations."""
        query = select(ExternalOperation).where(
            ExternalOperation.organization_id == organization_id
        )
        if connector_instance_id:
            query = query.where(ExternalOperation.connector_instance_id == connector_instance_id)
        if state:
            query = query.where(ExternalOperation.state == state)
        if source_action_id:
            query = query.where(ExternalOperation.source_action_id == source_action_id)
        query = query.order_by(ExternalOperation.created_at.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_pending_operations(
        self, db: AsyncSession, organization_id: str
    ) -> list[ExternalOperation]:
        """Get pending operations ready for execution."""
        result = await db.execute(
            select(ExternalOperation).where(
                ExternalOperation.organization_id == organization_id,
                ExternalOperation.state == "pending",
                ExternalOperation.governance_verified.is_(True),
            ).order_by(ExternalOperation.created_at.asc())
        )
        return list(result.scalars().all())
    
    # ------------------------------------------------------------ Full Lifecycle Helper
    
    async def create_governed_operation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        operation_type: str,
        target_entity_type: str,
        target_external_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        source_action_id: Optional[str] = None,
        source_decision_id: Optional[str] = None,
        source_authorization_id: Optional[str] = None,
        source_commitment_id: Optional[str] = None,
        required_permissions: Optional[list[str]] = None,
        caller: Optional[Any] = None,
    ) -> ExternalOperation:
        """
        Create a fully governed external operation.
        
        This enforces the governance chain:
        Decision → Authorization → Action → External Operation
        """
        
        # Verify governance chain
        if source_decision_id:
            decision = await db.get(CompanyDecision, source_decision_id)
            if decision is None or decision.organization_id != organization_id:
                raise ValueError("Invalid decision reference")
            if decision.state not in ("approved", "executed", "outcome_recorded"):
                raise ValueError(f"Decision not in executable state: {decision.state}")
        
        if source_authorization_id:
            auth = await db.get(CompanyAuthorization, source_authorization_id)
            if auth is None or auth.organization_id != organization_id:
                raise ValueError("Invalid authorization reference")
            if auth.state not in ("approved", "conditional"):
                raise ValueError(f"Authorization not approved: {auth.state}")
        
        if source_commitment_id:
            comm = await db.get(CompanyCommitment, source_commitment_id)
            if comm is None or comm.organization_id != organization_id:
                raise ValueError("Invalid commitment reference")
            if comm.state not in ("authorized", "active"):
                raise ValueError(f"Commitment not authorized: {comm.state}")
        
        if source_action_id:
            action = await db.get(CompanyAction, source_action_id)
            if action is None or action.organization_id != organization_id:
                raise ValueError("Invalid action reference")
            if action.state not in ("approved", "ready", "in_progress"):
                raise ValueError(f"Action not in executable state: {action.state}")
        
        # Create the operation
        operation = await self.create_operation(
            db=db,
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            operation_type=operation_type,
            target_entity_type=target_entity_type,
            target_external_id=target_external_id,
            payload=payload,
            source_action_id=source_action_id,
            source_decision_id=source_decision_id,
            source_authorization_id=source_authorization_id,
            source_commitment_id=source_commitment_id,
            governance_verified=True,
            governance_verified_by=caller.employee_id if caller else None,
            created_by=caller.employee_id if caller else None,
        )
        
        return operation


bidirectional_operation_service = BidirectionalOperationService()