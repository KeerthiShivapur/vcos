"""Gate 24 — Synchronization Service.

Implements the universal synchronization semantics:
- Initial synchronization
- Incremental synchronization
- Webhook event processing
- Polling
- Cursor/checkpoint management
- Retries & replay
- Failure recovery

Reuses existing worker/event infrastructure.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import select, and_, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    SyncRun,
    SyncCursor,
    ExternalEvent,
    ConnectorInstance,
    SYNC_STATES,
    SYNC_MODES,
    EXTERNAL_EVENT_STATES,
    compute_event_fingerprint,
)
from app.intelligence.canonical_mutation import (
    canonical_create,
    CanonicalMutationContext,
    MutationType,
    EpistemicStatus,
)

logger = logging.getLogger("vcos.integration.sync")


class SynchronizationService:
    """Universal synchronization service."""
    
    # ------------------------------------------------------------ Sync Run Management
    
    async def create_sync_run(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        sync_mode: str,
        triggered_by: str = "scheduled",
        trigger_id: Optional[str] = None,
        cursor_before: Optional[str] = None,
        since_timestamp: Optional[datetime] = None,
        until_timestamp: Optional[datetime] = None,
        metadata: Optional[dict] = None,
        created_by: Optional[str] = None,
    ) -> SyncRun:
        """Create a new synchronization run."""
        
        if sync_mode not in SYNC_MODES:
            raise ValueError(f"Invalid sync mode: {sync_mode}")
        
        instance = await db.get(ConnectorInstance, connector_instance_id)
        if instance is None or instance.organization_id != organization_id:
            raise ValueError("Invalid connector instance")
        
        sync_run = SyncRun(
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            sync_mode=sync_mode,
            triggered_by=triggered_by,
            trigger_id=trigger_id,
            cursor_before=cursor_before,
            since_timestamp=since_timestamp,
            until_timestamp=until_timestamp,
            state="pending",
            metadata_json=metadata,
            created_by=created_by,
        )
        
        db.add(sync_run)
        await db.flush()
        
        # Update instance next sync time
        if sync_mode in ("incremental", "polling"):
            instance.last_sync_at = utcnow()
        
        await publish_event(
            db,
            name="sync.run.started",
            organization_id=organization_id,
            actor_id=created_by,
            payload={
                "sync_run_id": sync_run.id,
                "connector_instance_id": connector_instance_id,
                "sync_mode": sync_mode,
            },
        )
        
        return sync_run
    
    async def start_sync_run(
        self, db: AsyncSession, sync_run_id: str
    ) -> Optional[SyncRun]:
        """Mark a sync run as running."""
        sync_run = await db.get(SyncRun, sync_run_id)
        if sync_run is None or sync_run.state != "pending":
            return None
        
        sync_run.state = "running"
        sync_run.started_at = utcnow()
        await db.flush()
        return sync_run
    
    async def complete_sync_run(
        self,
        db: AsyncSession,
        sync_run_id: str,
        *,
        state: str = "completed",
        error: Optional[str] = None,
        entities_processed: int = 0,
        entities_created: int = 0,
        entities_updated: int = 0,
        entities_deleted: int = 0,
        entities_failed: int = 0,
        conflicts_detected: int = 0,
        events_processed: int = 0,
        cursor_after: Optional[str] = None,
    ) -> Optional[SyncRun]:
        """Complete a sync run."""
        if state not in SYNC_STATES:
            raise ValueError(f"Invalid sync state: {state}")
        
        sync_run = await db.get(SyncRun, sync_run_id)
        if sync_run is None:
            return None
        
        sync_run.state = state
        sync_run.error = error
        sync_run.entities_processed = entities_processed
        sync_run.entities_created = entities_created
        sync_run.entities_updated = entities_updated
        sync_run.entities_deleted = entities_deleted
        sync_run.entities_failed = entities_failed
        sync_run.conflicts_detected = conflicts_detected
        sync_run.events_processed = events_processed
        sync_run.cursor_after = cursor_after
        sync_run.completed_at = utcnow()
        
        if sync_run.started_at:
            duration = (sync_run.completed_at - sync_run.started_at).total_seconds() * 1000
            sync_run.duration_ms = int(duration)
        
        # Update connector instance
        instance = await db.get(ConnectorInstance, sync_run.connector_instance_id)
        if instance:
            instance.last_sync_at = utcnow()
            if state == "completed":
                instance.error = None
                instance.state = "connected"
            elif state in ("failed", "partial"):
                instance.error = error
                instance.state = "error"
        
        await db.flush()
        
        await publish_event(
            db,
            name="sync.run.completed",
            organization_id=sync_run.organization_id,
            payload={
                "sync_run_id": sync_run_id,
                "state": state,
                "entities_processed": entities_processed,
                "entities_created": entities_created,
                "entities_updated": entities_updated,
                "entities_failed": entities_failed,
                "conflicts_detected": conflicts_detected,
                "duration_ms": sync_run.duration_ms,
            },
        )
        
        return sync_run
    
    async def get_sync_run(
        self, db: AsyncSession, sync_run_id: str
    ) -> Optional[SyncRun]:
        """Get a sync run by ID."""
        return await db.get(SyncRun, sync_run_id)
    
    async def list_sync_runs(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        connector_instance_id: Optional[str] = None,
        state: Optional[str] = None,
        limit: int = 50,
    ) -> list[SyncRun]:
        """List sync runs."""
        query = select(SyncRun).where(SyncRun.organization_id == organization_id)
        if connector_instance_id:
            query = query.where(SyncRun.connector_instance_id == connector_instance_id)
        if state:
            query = query.where(SyncRun.state == state)
        query = query.order_by(desc(SyncRun.started_at)).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    # ------------------------------------------------------------ Cursor Management
    
    async def get_cursor(
        self,
        db: AsyncSession,
        organization_id: str,
        connector_instance_id: str,
        entity_type: str,
    ) -> Optional[SyncCursor]:
        """Get the current cursor for an entity type."""
        result = await db.execute(
            select(SyncCursor).where(
                SyncCursor.organization_id == organization_id,
                SyncCursor.connector_instance_id == connector_instance_id,
                SyncCursor.entity_type == entity_type,
            )
        )
        return result.scalar_one_or_none()
    
    async def update_cursor(
        self,
        db: AsyncSession,
        organization_id: str,
        connector_instance_id: str,
        entity_type: str,
        cursor_value: str,
        cursor_type: str = "timestamp",
        sync_run_id: Optional[str] = None,
        entity_count: int = 0,
    ) -> SyncCursor:
        """Update or create a sync cursor."""
        
        cursor = await self.get_cursor(db, organization_id, connector_instance_id, entity_type)
        
        if cursor is None:
            cursor = SyncCursor(
                organization_id=organization_id,
                connector_instance_id=connector_instance_id,
                entity_type=entity_type,
                cursor_value=cursor_value,
                cursor_type=cursor_type,
                last_sync_run_id=sync_run_id,
                entity_count=entity_count,
            )
            db.add(cursor)
        else:
            cursor.cursor_value = cursor_value
            cursor.cursor_type = cursor_type
            cursor.last_sync_run_id = sync_run_id
            cursor.entity_count = entity_count
            cursor.last_updated_at = utcnow()
        
        await db.flush()
        return cursor
    
    async def list_cursors(
        self,
        db: AsyncSession,
        organization_id: str,
        connector_instance_id: Optional[str] = None,
    ) -> list[SyncCursor]:
        """List all cursors."""
        query = select(SyncCursor).where(SyncCursor.organization_id == organization_id)
        if connector_instance_id:
            query = query.where(SyncCursor.connector_instance_id == connector_instance_id)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    # ------------------------------------------------------------ External Event Processing
    
    async def ingest_external_event(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        external_event_id: str,
        event_type: str,
        source_id: Optional[str] = None,
        source_type: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        external_actor_id: Optional[str] = None,
        external_actor_type: Optional[str] = None,
        external_timestamp: Optional[datetime] = None,
        webhook_delivery_id: Optional[str] = None,
        max_retries: int = 3,
    ) -> ExternalEvent:
        """Ingest an external event with exact-once semantics."""
        
        # Compute fingerprint for exact-once
        fingerprint = compute_event_fingerprint(
            connector_instance_id=connector_instance_id,
            external_event_id=external_event_id,
            event_type=event_type,
            source_id=source_id,
        )
        
        # Check for existing event (exact-once)
        existing = await db.execute(
            select(ExternalEvent).where(
                ExternalEvent.connector_instance_id == connector_instance_id,
                ExternalEvent.external_event_id == external_event_id,
            )
        )
        existing_event = existing.scalar_one_or_none()
        
        payload = payload or {}
        payload_hash = compute_event_fingerprint(
            connector_instance_id=connector_instance_id,
            external_event_id=external_event_id,
            event_type=event_type,
            source_id=source_id,
        )
        
        if existing_event:
            # Duplicate event - exact-once: always return existing, mark as duplicate if not already
            if existing_event.state != "duplicate":
                existing_event.state = "duplicate"
                existing_event.processing_fingerprint = fingerprint
                await db.flush()
                
                await publish_event(
                    db,
                    name="external_event.duplicate",
                    organization_id=organization_id,
                    payload={
                        "event_id": existing_event.id,
                        "external_event_id": external_event_id,
                        "connector_instance_id": connector_instance_id,
                    },
                )
            return existing_event
        event = ExternalEvent(
            organization_id=organization_id,
            connector_instance_id=connector_instance_id,
            external_event_id=external_event_id,
            event_type=event_type,
            source_id=source_id,
            source_type=source_type,
            payload=payload,
            payload_hash=payload_hash,
            external_actor_id=external_actor_id,
            external_actor_type=external_actor_type,
            external_timestamp=external_timestamp,
            state="pending",
            max_retries=max_retries,
            processing_fingerprint=fingerprint,
            webhook_delivery_id=webhook_delivery_id,
            epistemic_status=None,
        )
        
        db.add(event)
        await db.flush()
        
        await publish_event(
            db,
            name="external_event.received",
            organization_id=organization_id,
            payload={
                "event_id": event.id,
                "external_event_id": external_event_id,
                "event_type": event_type,
                "connector_instance_id": connector_instance_id,
            },
        )
        
        return event
    
    async def process_external_event(
        self,
        db: AsyncSession,
        event_id: str,
        processor: callable,
        sync_run_id: Optional[str] = None,
    ) -> ExternalEvent:
        """Process an external event through the given processor function."""
        
        event = await db.get(ExternalEvent, event_id)
        if event is None:
            raise ValueError(f"Event not found: {event_id}")
        
        if event.state not in ("pending", "failed"):
            return event
        
        event.state = "pending"
        await db.flush()
        
        try:
            # Process through the handler
            result = await processor(db, event)
            
            event.state = "processed"
            event.processed_at = utcnow()
            event.processed_by_sync_run = sync_run_id
            event.error = None
            
            await publish_event(
                db,
                name="external_event.processed",
                organization_id=event.organization_id,
                payload={
                    "event_id": event.id,
                    "external_event_id": event.external_event_id,
                    "event_type": event.event_type,
                    "result": result,
                },
            )
            
        except Exception as e:
            event.retry_count += 1
            event.error = str(e)
            
            if event.retry_count >= event.max_retries:
                event.state = "failed"
                
                await publish_event(
                    db,
                    name="external_event.failed",
                    organization_id=event.organization_id,
                    payload={
                        "event_id": event.id,
                        "external_event_id": event.external_event_id,
                        "error": str(e),
                        "retries": event.retry_count,
                    },
                )
            else:
                event.state = "pending"
            
            logger.warning("External event processing failed: %s", e)
        
        await db.flush()
        return event
    
    async def retry_failed_events(
        self,
        db: AsyncSession,
        organization_id: str,
        connector_instance_id: Optional[str] = None,
        limit: int = 100,
    ) -> int:
        """Retry failed external events."""
        query = select(ExternalEvent).where(
            ExternalEvent.organization_id == organization_id,
            ExternalEvent.state == "failed",
            ExternalEvent.retry_count < ExternalEvent.max_retries,
        )
        if connector_instance_id:
            query = query.where(ExternalEvent.connector_instance_id == connector_instance_id)
        query = query.order_by(ExternalEvent.received_at.asc()).limit(limit)
        
        result = await db.execute(query)
        events = list(result.scalars().all())
        
        for event in events:
            event.state = "pending"
            event.error = None
        
        await db.flush()
        return len(events)
    
    # ------------------------------------------------------------ Event Queries
    
    async def get_event(
        self, db: AsyncSession, event_id: str
    ) -> Optional[ExternalEvent]:
        """Get an external event by ID."""
        return await db.get(ExternalEvent, event_id)
    
    async def list_events(
        self,
        db: AsyncSession,
        organization_id: str,
        *,
        connector_instance_id: Optional[str] = None,
        state: Optional[str] = None,
        event_type: Optional[str] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> list[ExternalEvent]:
        """List external events with filters."""
        query = select(ExternalEvent).where(ExternalEvent.organization_id == organization_id)
        if connector_instance_id:
            query = query.where(ExternalEvent.connector_instance_id == connector_instance_id)
        if state:
            query = query.where(ExternalEvent.state == state)
        if event_type:
            query = query.where(ExternalEvent.event_type == event_type)
        if since:
            query = query.where(ExternalEvent.received_at >= since)
        query = query.order_by(desc(ExternalEvent.received_at)).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    # ------------------------------------------------------------ Canonical Entity Processing
    
    async def process_entity_from_external(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        connector_instance_id: str,
        vcos_entity_type: str,
        vcos_entity_id: Optional[str],
        external_id: str,
        external_data: dict[str, Any],
        event_id: str,
        sync_run_id: Optional[str] = None,
        operation: str = "upsert",
        field_mapping: Optional[dict[str, str]] = None,
        epistemic_status: EpistemicStatus = EpistemicStatus.EVIDENCE_BACKED,
        provenance: Optional[dict] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        Process an external entity into canonical reality.
        
        Returns: (was_created, canonical_entity_id)
        
        This is the bridge from external observation to canonical reality.
        The external system provides EVIDENCE; VCOS determines canonical interpretation.
        """
        
        # Build provenance chain
        full_provenance = {
            "provider": "external",
            "connector_instance_id": connector_instance_id,
            "external_event_id": event_id,
            "external_id": external_id,
            "sync_run_id": sync_run_id,
            "ingested_at": utcnow().isoformat(),
            "operation": operation,
            **(provenance or {}),
        }
        
        # Use canonical mutation boundary for exact-once and governance
        # The actual entity creation/update depends on the entity type
        # This is a generic handler; specific processors should be implemented per entity type
        
        # For now, return a placeholder - actual implementation delegates to
        # the specific canonical service (e.g., workforce, knowledge, etc.)
        return False, None


synchronization_service = SynchronizationService()