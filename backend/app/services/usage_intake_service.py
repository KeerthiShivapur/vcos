"""Usage Event Intake Service — Stage 5.1 Pay-As-You-Go Billing.

Implements tenant-safe, idempotent usage event ingestion with:
- Schema and semantic validation
- Database-enforced deduplication (exact-once)
- Tenant/account ownership verification
- Source authorization
- Provenance recording
- Processing state tracking
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.finance import (
    CommercialAccount,
    Subscription,
    UsageRecord,
    Entitlement,
)
from app.models.organization import Organization
from app.schemas.usage_metering import (
    UsageEventCreate,
    UsageEventInternal,
    UsageEventState,
    UsageEventResponse,
    UsageBatchRequest,
    UsageBatchResponse,
    UsageMetricCode,
    UsageEventSource,
    get_metric_metadata,
    validate_metric_unit,
)
from app.services.commercial_service import commercial_service
from app.services.audit_service import audit_service

logger = logging.getLogger("vcos.billing.usage_intake")


class UsageIntakeError(Exception):
    """Base exception for usage intake errors."""
    pass


class ValidationError(UsageIntakeError):
    """Usage event validation failed."""
    pass


class TenantIsolationError(UsageIntakeError):
    """Cross-tenant access attempt."""
    pass


class DuplicateEventError(UsageIntakeError):
    """Duplicate event detected."""
    pass


class UnauthorizedSourceError(UsageIntakeError):
    """Source system not authorized for organization."""
    pass


class UsageIntakeService:
    """Service for ingesting and processing usage events."""
    
    # Maximum events per batch
    MAX_BATCH_SIZE = 1000
    
    # Clock skew tolerance for timestamp validation
    CLOCK_SKEW_TOLERANCE = timedelta(minutes=10)
    
    # Future timestamp tolerance
    FUTURE_TOLERANCE = timedelta(minutes=5)
    
    def __init__(self):
        self._source_authorizations: Dict[str, Dict[str, Any]] = {}
    
    # =========================================================================
    # SINGLE EVENT INGESTION
    # =========================================================================
    
    async def ingest_event(
        self,
        db: AsyncSession,
        event: UsageEventCreate,
        caller_org_id: Optional[str] = None,
    ) -> UsageEventResponse:
        """
        Ingest a single usage event with full validation and idempotency.
        
        Flow:
        1. Validate schema and semantics
        2. Verify tenant/account ownership
        3. Verify subscription association
        4. Check source authorization
        5. Attempt atomic insert with deduplication
        6. Record provenance
        7. Return processing result
        """
        # Track processing timestamps
        received_at = utcnow()
        event_internal = UsageEventInternal(
            **event.model_dump(),
            state=UsageEventState.RECEIVED,
            received_at=received_at,
        )
        
        try:
            # Step 1: Schema and semantic validation
            await self._validate_event(db, event_internal, caller_org_id)
            event_internal.state = UsageEventState.VALIDATED
            event_internal.validated_at = utcnow()
            
            # Step 2: Tenant/account ownership verification
            await self._verify_ownership(db, event_internal)
            
            # Step 3: Subscription verification
            await self._verify_subscription(db, event_internal)
            
            # Step 4: Source authorization
            await self._verify_source_authorization(db, event_internal)
            
            # Step 5: Atomic insert with deduplication
            usage_record, is_duplicate = await self._insert_with_deduplication(
                db, event_internal
            )
            
            if is_duplicate:
                event_internal.state = UsageEventState.DUPLICATE
                event_internal.is_duplicate = True
                event_internal.original_event_id = usage_record.event_id
                return UsageEventResponse(
                    event_id=event.event_id,
                    state=UsageEventState.DUPLICATE,
                    message="Duplicate event - already processed",
                    accepted_at=usage_record.created_at,
                    duplicate_of=usage_record.event_id,
                )
            
            # Step 6: Record provenance
            await self._record_provenance(db, event_internal, usage_record)
            
            # Step 7: Update entitlement usage tracking
            await self._update_entitlement_usage(db, event_internal, usage_record)
            
            # Mark accepted
            event_internal.state = UsageEventState.ACCEPTED
            event_internal.accepted_at = utcnow()
            
            # Emit event for downstream processing
            await publish_event(
                db,
                name="usage.event.accepted",
                organization_id=event.organization_id,
                payload={
                    "usage_record_id": usage_record.id,
                    "event_id": event.event_id,
                    "metric_code": event.metric_code,
                    "quantity": str(event.quantity),
                    "period": event.period,
                },
            )
            
            await audit_service.log(
                db,
                organization_id=event.organization_id,
                action="usage.event.accepted",
                resource_type="usage_record",
                resource_id=usage_record.id,
                details={
                    "event_id": event.event_id,
                    "metric_code": event.metric_code,
                    "quantity": str(event.quantity),
                    "period": event.period,
                },
            )
            
            return UsageEventResponse(
                event_id=event.event_id,
                state=UsageEventState.ACCEPTED,
                message="Event accepted and recorded",
                accepted_at=event_internal.accepted_at,
            )
            
        except ValidationError as e:
            event_internal.state = UsageEventState.REJECTED
            event_internal.validation_errors.append(str(e))
            logger.warning(f"Usage event validation failed: {e}")
            return UsageEventResponse(
                event_id=event.event_id,
                state=UsageEventState.REJECTED,
                message=f"Validation failed: {e}",
            )
        except TenantIsolationError as e:
            event_internal.state = UsageEventState.REJECTED
            event_internal.validation_errors.append(str(e))
            logger.warning(f"Tenant isolation violation: {e}")
            return UsageEventResponse(
                event_id=event.event_id,
                state=UsageEventState.REJECTED,
                message=f"Tenant isolation violation: {e}",
            )
        except DuplicateEventError as e:
            event_internal.state = UsageEventState.DUPLICATE
            return UsageEventResponse(
                event_id=event.event_id,
                state=UsageEventState.DUPLICATE,
                message=str(e),
            )
        except UnauthorizedSourceError as e:
            event_internal.state = UsageEventState.REJECTED
            event_internal.validation_errors.append(str(e))
            logger.warning(f"Unauthorized source: {e}")
            return UsageEventResponse(
                event_id=event.event_id,
                state=UsageEventState.REJECTED,
                message=f"Unauthorized source: {e}",
            )
        except Exception as e:
            event_internal.state = UsageEventState.REJECTED
            event_internal.validation_errors.append(str(e))
            logger.exception(f"Usage event ingestion failed: {e}")
            return UsageEventResponse(
                event_id=event.event_id,
                state=UsageEventState.REJECTED,
                message=f"Internal error: {e}",
            )
    
    # =========================================================================
    # BATCH EVENT INGESTION
    # =========================================================================
    
    async def ingest_batch(
        self,
        db: AsyncSession,
        batch: UsageBatchRequest,
        caller_org_id: Optional[str] = None,
    ) -> UsageBatchResponse:
        """
        Ingest a batch of usage events.
        
        Processes each event independently - partial failure doesn't affect others.
        Uses savepoints for transaction isolation per event.
        """
        results = []
        accepted = 0
        duplicates = 0
        rejected = 0
        
        for event in batch.events:
            try:
                # Use savepoint for each event to isolate failures
                async with db.begin_nested():
                    result = await self.ingest_event(db, event, caller_org_id)
                    results.append(result)
                    
                    if result.state == UsageEventState.ACCEPTED:
                        accepted += 1
                    elif result.state == UsageEventState.DUPLICATE:
                        duplicates += 1
                    else:
                        rejected += 1
                        
            except Exception as e:
                # Event-level failure - record rejection
                logger.exception(f"Batch event failed: {e}")
                results.append(UsageEventResponse(
                    event_id=event.event_id,
                    state=UsageEventState.REJECTED,
                    message=f"Processing error: {e}",
                ))
                rejected += 1
        
        return UsageBatchResponse(
            accepted=accepted,
            duplicates=duplicates,
            rejected=rejected,
            results=results,
        )
    
    # =========================================================================
    # VALIDATION
    # =========================================================================
    
    async def _validate_event(
        self,
        db: AsyncSession,
        event: UsageEventInternal,
        caller_org_id: Optional[str],
    ) -> None:
        """Validate event schema, semantics, and business rules."""
        
        # 1. Cross-tenant validation
        if caller_org_id and event.organization_id != caller_org_id:
            raise TenantIsolationError(
                f"Caller org {caller_org_id} cannot submit events for org {event.organization_id}"
            )
        
        # 2. Organization exists
        org = await db.get(Organization, event.organization_id)
        if not org:
            raise ValidationError(f"Organization not found: {event.organization_id}")
        
        # 3. Commercial account exists
        account = await db.get(CommercialAccount, event.commercial_account_id)
        if not account:
            raise ValidationError(f"Commercial account not found: {event.commercial_account_id}")
        if account.organization_id != event.organization_id:
            raise TenantIsolationError(
                f"Commercial account {event.commercial_account_id} "
                f"does not belong to organization {event.organization_id}"
            )
        
        # 4. Metric code is valid
        metric_meta = get_metric_metadata(event.metric_code)
        if not metric_meta:
            raise ValidationError(f"Unknown metric code: {event.metric_code}")
        
        # 5. Unit matches metric
        if not validate_metric_unit(event.metric_code, event.unit):
            raise ValidationError(
                f"Unit {event.unit} does not match metric {event.metric_code} "
                f"(expected {metric_meta.get('unit')})"
            )
        
        # 6. Quantity is positive and within reasonable bounds
        if event.quantity <= 0:
            raise ValidationError("Quantity must be positive")
        if event.quantity > Decimal("1000000000"):  # 1B max
            raise ValidationError("Quantity exceeds maximum allowed value")
        
        # 7. Timestamp validity
        now = utcnow()
        if event.occurred_at > now + self.FUTURE_TOLERANCE:
            raise ValidationError("occurred_at cannot be in the future")
        if event.received_at > now + self.FUTURE_TOLERANCE:
            raise ValidationError("received_at cannot be in the future")
        if event.occurred_at < now - timedelta(days=365):
            raise ValidationError("occurred_at cannot be more than 365 days in the past")
        
        # 8. Period matches occurred_at
        expected_period = event.occurred_at.strftime("%Y-%m")
        if event.period != expected_period:
            raise ValidationError(
                f"Period mismatch: expected {expected_period} for occurred_at {event.occurred_at}"
            )
        
        # 9. Source entity/operation IDs format
        if event.source_entity_id and len(event.source_entity_id) > 120:
            raise ValidationError("source_entity_id exceeds maximum length")
        if event.source_operation_id and len(event.source_operation_id) > 120:
            raise ValidationError("source_operation_id exceeds maximum length")
    
    async def _verify_ownership(
        self,
        db: AsyncSession,
        event: UsageEventInternal,
    ) -> None:
        """Verify tenant and account ownership."""
        # Verify organization owns the commercial account
        account = await db.get(CommercialAccount, event.commercial_account_id)
        if not account or account.organization_id != event.organization_id:
            raise TenantIsolationError(
                f"Commercial account {event.commercial_account_id} "
                f"does not belong to organization {event.organization_id}"
            )
        
        # Verify subscription belongs to organization
        if event.subscription_id:
            sub = await db.get(Subscription, event.subscription_id)
            if not sub or sub.organization_id != event.organization_id:
                raise TenantIsolationError(
                    f"Subscription {event.subscription_id} "
                    f"does not belong to organization {event.organization_id}"
                )
    
    async def _verify_subscription(
        self,
        db: AsyncSession,
        event: UsageEventInternal,
    ) -> None:
        """Verify subscription is valid and active."""
        if not event.subscription_id:
            # Auto-resolve subscription for organization
            subscription = await commercial_service.get_subscription(db, event.organization_id)
            if not subscription:
                raise ValidationError("No active subscription found for organization")
            # Update event with resolved subscription
            event.subscription_id = subscription.id
        else:
            sub = await db.get(Subscription, event.subscription_id)
            if not sub:
                raise ValidationError(f"Subscription not found: {event.subscription_id}")
            if sub.state not in ("trialing", "active", "past_due", "grace"):
                raise ValidationError(
                    f"Subscription not in billable state: {sub.state}"
                )
    
    async def _verify_source_authorization(
        self,
        db: AsyncSession,
        event: UsageEventInternal,
    ) -> None:
        """Verify source system is authorized for this organization."""
        # Check if source system is registered for this organization
        # This would integrate with integration/connector framework
        source_key = f"{event.organization_id}:{event.source_system}"
        
        if source_key in self._source_authorizations:
            auth = self._source_authorizations[source_key]
            if not auth.get("enabled", True):
                raise UnauthorizedSourceError(
                    f"Source system {event.source_system} is disabled for organization"
                )
        
        # For now, allow all configured source systems
        # In production, this would check ConnectorInstance configuration
        allowed_sources = {
            UsageEventSource.AI_INFERENCE,
            UsageEventSource.WORKFLOW_ENGINE,
            UsageEventSource.INTEGRATION_SYNC,
            UsageEventSource.DOCUMENT_PROCESSING,
            UsageEventSource.STORAGE,
            UsageEventSource.API_GATEWAY,
            UsageEventSource.SYSTEM,
            UsageEventSource.WORKER,
            UsageEventSource.WEBHOOK,
        }
        if event.source_system not in allowed_sources:
            raise UnauthorizedSourceError(
                f"Unknown source system: {event.source_system}"
            )
    
    # =========================================================================
    # IDEMPOTENT INSERTION WITH DATABASE-LEVEL DEDUPLICATION
    # =========================================================================
    
    async def _insert_with_deduplication(
        self,
        db: AsyncSession,
        event: UsageEventInternal,
    ) -> Tuple[UsageRecord, bool]:
        """
        Atomically insert usage record with database-enforced deduplication.
        
        Uses PostgreSQL INSERT ... ON CONFLICT to ensure exactly-once semantics.
        The UsageRecord table has a unique constraint on:
        (organization_id, entitlement_key, period, event_id)
        
        Returns: (UsageRecord, is_duplicate)
        """
        # Get entitlement for this metric
        entitlement_result = await db.execute(
            select(Entitlement).where(
                Entitlement.organization_id == event.organization_id,
                Entitlement.key == event.metric_code,
            )
        )
        entitlement = entitlement_result.scalar_one_or_none()
        
        subscription = None
        if event.subscription_id:
            subscription = await db.get(Subscription, event.subscription_id)
        
        usage_record = UsageRecord(
            organization_id=event.organization_id,
            subscription_id=subscription.id if subscription else None,
            entitlement_id=entitlement.id if entitlement else None,
            entitlement_key=event.metric_code,
            period=event.period,
            quantity=event.quantity,
            unit=event.unit,
            event_id=event.event_id,
            event_source=event.source_system.value,
            event_timestamp=event.occurred_at,
            metadata_json={
                "source_system": event.source_system.value,
                "source_entity_id": event.source_entity_id,
                "source_operation_id": event.source_operation_id,
                "provenance": event.provenance,
                "metadata": event.metadata,
                "event_schema_version": event.event_schema_version.value,
            },
        )
        
        db.add(usage_record)
        
        try:
            await db.flush()
            return usage_record, False
        except IntegrityError as e:
            await db.rollback()
            # Check if it's our unique constraint violation
            if "uq_usage_exact_once" in str(e.orig):
                # Find the existing record
                existing_result = await db.execute(
                    select(UsageRecord).where(
                        UsageRecord.organization_id == event.organization_id,
                        UsageRecord.entitlement_key == event.metric_code,
                        UsageRecord.period == event.period,
                        UsageRecord.event_id == event.event_id,
                    )
                )
                existing = existing_result.scalar_one_or_none()
                if existing:
                    raise DuplicateEventError(
                        f"Duplicate event {event.event_id} already recorded"
                    ) from e
            raise
    
    # =========================================================================
    # PROVENANCE RECORDING
    # =========================================================================
    
    async def _record_provenance(
        self,
        db: AsyncSession,
        event: UsageEventInternal,
        usage_record: UsageRecord,
    ) -> None:
        """Record provenance chain for the usage record."""
        # The provenance is stored in usage_record.metadata_json
        # Additional provenance events can be emitted
        
        await publish_event(
            db,
            name="usage.provenance.recorded",
            organization_id=event.organization_id,
            payload={
                "usage_record_id": usage_record.id,
                "event_id": event.event_id,
                "source_system": event.source_system.value,
                "source_entity_id": event.source_entity_id,
                "source_operation_id": event.source_operation_id,
                "provenance": event.provenance,
                "occurred_at": event.occurred_at.isoformat(),
            },
        )
    
    # =========================================================================
    # ENTITLEMENT USAGE TRACKING
    # =========================================================================
    
    async def _update_entitlement_usage(
        self,
        db: AsyncSession,
        event: UsageEventInternal,
        usage_record: UsageRecord,
    ) -> None:
        """Update entitlement current usage for limit enforcement."""
        if not event.entitlement_id:
            return
        
        entitlement = await db.get(Entitlement, event.entitlement_id)
        if not entitlement:
            return
        
        # For limit-type entitlements, track current usage
        if entitlement.entitlement_type == "limit" and entitlement.numeric_value:
            # Current usage is computed via aggregation, not stored on entitlement
            # This is where we could update a denormalized current_usage field
            # if the schema supported it
            pass
        
        # Emit usage update event for real-time limit checking
        await publish_event(
            db,
            name="usage.entitlement.updated",
            organization_id=event.organization_id,
            payload={
                "entitlement_id": entitlement.id,
                "entitlement_key": event.metric_code,
                "usage_record_id": usage_record.id,
                "quantity": str(event.quantity),
                "period": event.period,
            },
        )
    
    # =========================================================================
    # QUERY METHODS
    # =========================================================================
    
    async def get_event_status(
        self,
        db: AsyncSession,
        organization_id: str,
        event_id: str,
    ) -> Optional[UsageEventInternal]:
        """Get processing status of a usage event by event_id."""
        result = await db.execute(
            select(UsageRecord).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.event_id == event_id,
            )
        )
        record = result.scalar_one_or_none()
        if not record:
            return None
        
        return UsageEventInternal(
            event_id=record.event_id,
            event_schema_version=record.metadata_json.get("event_schema_version", "1.0.0"),
            organization_id=record.organization_id,
            commercial_account_id="",  # Would need join
            subscription_id=record.subscription_id,
            metric_code=record.entitlement_key,
            quantity=record.quantity,
            unit=record.unit,
            occurred_at=record.event_timestamp,
            received_at=record.created_at,
            source_system=UsageEventSource(record.event_source),
            source_entity_id=record.metadata_json.get("source_entity_id"),
            source_operation_id=record.metadata_json.get("source_operation_id"),
            provenance=record.metadata_json.get("provenance", {}),
            metadata=record.metadata_json.get("metadata", {}),
            period=record.period,
            state=UsageEventState.ACCEPTED,
        )
    
    async def get_events_by_source(
        self,
        db: AsyncSession,
        organization_id: str,
        source_system: UsageEventSource,
        period: Optional[str] = None,
        limit: int = 100,
    ) -> List[UsageRecord]:
        """Get usage events by source system."""
        query = select(UsageRecord).where(
            UsageRecord.organization_id == organization_id,
            UsageRecord.event_source == source_system.value,
        )
        if period:
            query = query.where(UsageRecord.period == period)
        query = query.order_by(UsageRecord.created_at.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())


# Global instance
usage_intake_service = UsageIntakeService()


# Import timedelta for validators
from datetime import timedelta