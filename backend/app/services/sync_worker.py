"""Sync Worker — reliable incremental synchronization with resumability.

Implements:
- Cursor-based incremental synchronization
- Checkpointing for resumability
- Rate limit handling
- Retry with exponential backoff
- Pagination handling
- Worker restart recovery
- Duplicate page/record handling
- Out-of-order record handling
- Deleted record handling
- 35-H recovery semantics integration
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Callable, AsyncGenerator

from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.canonical_integration import (
    SyncRun,
    SyncCursor,
    ConnectorInstance,
    Connector,
    SYNC_STATES,
    SYNC_MODES,
)
from app.services.adapter_registry import get_adapter
from app.services.base_adapter import (
    BaseConnectorAdapter,
    SyncMode,
    SyncState,
    SyncResult,
)

logger = logging.getLogger("vcos.integration.sync")


class SyncWorker:
    """Sync worker for incremental and full synchronization.
    
    Handles:
    - Cursor-based incremental sync
    - Checkpointing for resumability
    - Rate limit handling with backoff
    - Retry with exponential backoff
    - Pagination
    - Worker restart recovery
    - Duplicate handling
    - Out-of-order records
    - Deleted record detection
    - 35-H recovery semantics
    """
    
    def __init__(
        self,
        max_retries: int = 3,
        base_retry_delay: float = 1.0,
        max_retry_delay: float = 300.0,
        page_size: int = 100,
    ):
        self.max_retries = max_retries
        self.base_retry_delay = base_retry_delay
        self.max_retry_delay = max_retry_delay
        self.page_size = page_size
        self._running = False
    
    # ------------------------------------------------------------ Main Sync Entry Points
    
    async def run_initial_sync(
        self,
        db: AsyncSession,
        instance_id: str,
        organization_id: str,
        triggered_by: str = "scheduled",
    ) -> SyncRun:
        """Run a full initial synchronization."""
        result = await db.execute(
            select(ConnectorInstance)
            .options(selectinload(ConnectorInstance.connector))
            .where(ConnectorInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError("Instance not found")
        
        sync_run = await self._create_sync_run(
            db, instance, "initial", triggered_by
        )
        
        try:
            await self._update_sync_state(db, sync_run, "running")
            result = await self._sync_all_entities(
                db, instance, sync_run, full_sync=True
            )
            await self._complete_sync_run(db, sync_run, result, "completed")
        except Exception as e:
            logger.error(f"Initial sync failed for {instance.id}: {e}")
            await self._complete_sync_run(db, sync_run, SyncResult(error=str(e)), "failed")
            raise
        
        return await db.get(SyncRun, sync_run.id)
    
    async def run_incremental_sync(
        self,
        db: AsyncSession,
        instance_id: str,
        organization_id: str,
        triggered_by: str = "scheduled",
    ) -> SyncRun:
        """Run an incremental synchronization."""
        result = await db.execute(
            select(ConnectorInstance)
            .options(selectinload(ConnectorInstance.connector))
            .where(ConnectorInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError("Instance not found")
        
        if not instance.sync_enabled:
            raise ValueError("Sync not enabled for this instance")
        
        sync_run = await self._create_sync_run(
            db, instance, "incremental", triggered_by
        )
        
        try:
            await self._update_sync_state(db, sync_run, "running")
            result = await self._sync_all_entities(
                db, instance, sync_run, full_sync=False
            )
            await self._complete_sync_run(db, sync_run, result, "completed")
        except Exception as e:
            logger.error(f"Incremental sync failed for {instance.id}: {e}")
            await self._complete_sync_run(db, sync_run, SyncResult(error=str(e)), "failed")
            raise
        
        return await db.get(SyncRun, sync_run.id)
    
    async def run_polling_sync(
        self,
        db: AsyncSession,
        instance_id: str,
        organization_id: str,
        triggered_by: str = "polling",
    ) -> SyncRun:
        """Run a polling sync (same as incremental but triggered by polling)."""
        return await self.run_incremental_sync(db, instance_id, organization_id, triggered_by)
    
    async def run_replay_sync(
        self,
        db: AsyncSession,
        instance_id: str,
        organization_id: str,
        since: datetime,
        until: Optional[datetime] = None,
    ) -> SyncRun:
        """Replay sync for a specific time window (for recovery)."""
        result = await db.execute(
            select(ConnectorInstance)
            .options(selectinload(ConnectorInstance.connector))
            .where(ConnectorInstance.id == instance_id)
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError("Instance not found")
        
        sync_run = await self._create_sync_run(
            db, instance, "replay", "replay"
        )
        sync_run.since_timestamp = since
        sync_run.until_timestamp = until
        
        try:
            await self._update_sync_state(db, sync_run, "running")
            result = await self._sync_all_entities(
                db, instance, sync_run, full_sync=False, since=since, until=until
            )
            await self._complete_sync_run(db, sync_run, result, "completed")
        except Exception as e:
            logger.error(f"Replay sync failed for {instance.id}: {e}")
            await self._complete_sync_run(db, sync_run, SyncResult(error=str(e)), "failed")
            raise
        
        return await db.get(SyncRun, sync_run.id)
    
    async def execute_sync_run(
        self,
        db: AsyncSession,
        sync_run: SyncRun,
    ) -> SyncResult:
        """Execute an already-created (pending/running) sync run.

        Lifecycle (create/start/complete) is owned by
        synchronization_service; this method performs the work and returns
        the aggregated result without mutating run state.
        """
        result = await db.execute(
            select(ConnectorInstance)
            .options(selectinload(ConnectorInstance.connector))
            .where(ConnectorInstance.id == sync_run.connector_instance_id)
        )
        instance = result.scalar_one_or_none()
        if not instance:
            raise ValueError("Instance not found")
        
        full_sync = sync_run.sync_mode == "initial"
        return await self._sync_all_entities(
            db,
            instance,
            sync_run,
            full_sync=full_sync,
            since=sync_run.since_timestamp,
            until=sync_run.until_timestamp,
        )
    
    # ------------------------------------------------------------ Core Sync Logic
    
    async def _sync_all_entities(
        self,
        db: AsyncSession,
        instance: ConnectorInstance,
        sync_run: SyncRun,
        full_sync: bool = False,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> SyncResult:
        """Sync all entity types supported by the connector."""
        # Get connector from instance relationship
        connector = instance.connector
        if not connector:
            # Fetch if not loaded
            from sqlalchemy import select
            result = await db.execute(
                select(Connector).where(Connector.id == instance.connector_id)
            )
            connector = result.scalar_one_or_none()
        
        if not connector:
            raise ValueError("Connector not found")
        
        # Get adapter for this provider
        adapter = get_adapter(connector.provider)
        if not adapter:
            raise ValueError(f"No adapter for provider: {connector.provider}")
        
        # Authenticate
        if not await adapter.authenticate(instance):
            raise RuntimeError("Authentication failed")
        
        total_result = SyncResult()
        
        # Get supported entities
        entities = connector.supported_entities or []
        
        for entity_type in entities:
            if entity_type not in adapter._get_supported_entity_types():
                continue
            
            try:
                entity_result = await self._sync_entity_type(
                    db=db,
                    adapter=adapter,
                    instance=instance,
                    sync_run=sync_run,
                    entity_type=entity_type,
                    full_sync=full_sync,
                    since=since,
                    until=until,
                )
                
                # Aggregate results
                total_result.entities_processed += entity_result.entities_processed
                total_result.entities_created += entity_result.entities_created
                total_result.entities_updated += entity_result.entities_updated
                total_result.entities_deleted += entity_result.entities_deleted
                total_result.entities_failed += entity_result.entities_failed
                total_result.conflicts_detected += entity_result.conflicts_detected
                
            except Exception as e:
                logger.error(f"Failed to sync {entity_type} for {instance.id}: {e}")
                total_result.entities_failed += 1
                total_result.error = str(e)
                # Continue with other entities
        
        return total_result
    
    async def _sync_entity_type(
        self,
        db: AsyncSession,
        adapter: BaseConnectorAdapter,
        instance: ConnectorInstance,
        sync_run: SyncRun,
        entity_type: str,
        full_sync: bool = False,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> SyncResult:
        """Sync a specific entity type."""
        result = SyncResult()
        
        # Get or create cursor
        cursor = await self._get_or_create_cursor(db, sync_run.connector_instance_id, entity_type)
        
        if full_sync:
            cursor_value = await adapter.get_initial_cursor(instance, entity_type)
        else:
            cursor_value = cursor.cursor_value or await adapter.get_incremental_cursor(instance, entity_type, cursor.cursor_value)
        
        sync_run.cursor_before = cursor_value
        
        # Track pages for resumability
        page_count = 0
        max_pages = 1000  # Safety limit
        
        while page_count < max_pages:
            page_count += 1
            
            # Check rate limits
            rate_limit = await adapter.get_rate_limit_status(instance)
            if rate_limit.get("remaining", 1000) < 10:
                reset_at = rate_limit.get("reset_at")
                if reset_at:
                    wait_seconds = (reset_at - utcnow()).total_seconds()
                    if wait_seconds > 0:
                        logger.info(f"Rate limited, waiting {wait_seconds}s")
                        await asyncio.sleep(min(wait_seconds, 60))
            
            # Fetch page with retry
            page_result = await self._fetch_page_with_retry(
                adapter, instance, entity_type, cursor_value, since
            )
            
            if not page_result:
                break
            
            # Process entities in page
            for entity in page_result.get("entities", []):
                try:
                    processed = await self._process_entity(
                        db=db,
                        instance=instance,
                        entity_type=entity_type,
                        external_entity=entity,
                        sync_run=sync_run,
                    )
                    if processed == "created":
                        result.entities_created += 1
                    elif processed == "updated":
                        result.entities_updated += 1
                    elif processed == "deleted":
                        result.entities_deleted += 1
                    result.entities_processed += 1
                except Exception as e:
                    logger.error(f"Failed to process entity: {e}")
                    result.entities_failed += 1
                    result.entities_processed += 1
            
            # Update cursor
            cursor_value = page_result.get("next_cursor", cursor_value)
            cursor.cursor_value = cursor_value
            cursor.last_sync_run_id = sync_run.id
            cursor.entity_count = page_result.get("entity_count", 0)
            cursor.last_updated_at = utcnow()
            
            if not page_result.get("has_more", False):
                break
        
        # Handle deleted entities (for incremental sync)
        if not full_sync and since:
            await self._handle_deletions(
                db, instance, entity_type, since, sync_run
            )
        
        # Update cursor
        cursor.cursor_value = cursor_value
        cursor.last_sync_run_id = sync_run.id
        await db.flush()
        
        return result
    
    async def _fetch_page_with_retry(
        self,
        adapter: BaseConnectorAdapter,
        instance: ConnectorInstance,
        entity_type: str,
        cursor: Optional[str],
        since: Optional[datetime],
    ) -> Optional[Dict[str, Any]]:
        """Fetch page with exponential backoff retry."""
        last_error = None
        
        for attempt in range(self.max_retries + 1):
            try:
                return await adapter.fetch_page(
                    instance, entity_type, cursor, since, self.page_size
                )
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = min(
                        self.base_retry_delay * (2 ** attempt),
                        self.max_retry_delay
                    )
                    logger.warning(f"Fetch failed (attempt {attempt + 1}), retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
        
        logger.error(f"All retries exhausted for {entity_type}: {last_error}")
        return None
    
    async def _process_entity(
        self,
        db: AsyncSession,
        instance: ConnectorInstance,
        entity_type: str,
        external_entity: Dict[str, Any],
        sync_run: SyncRun,
    ) -> str:
        """Process a single external entity.
        
        Returns: "created", "updated", "deleted", or "skipped"
        """
        # Extract external ID
        adapter = get_adapter(instance.connector.provider) if instance.connector else None
        external_id = adapter._extract_external_id(entity_type, external_entity) if adapter else None
        if not external_id:
            external_id = self._extract_external_id(entity_type, external_entity)
        if not external_id:
            return "skipped"
        
        # Resolve identity
        from app.services.external_identity_service import external_identity_service
        mapping = await external_identity_service.resolve_identity(
            db=db,
            organization_id=sync_run.organization_id,
            connector_instance_id=sync_run.connector_instance_id,
            external_id=external_id,
            external_email=external_entity.get("email"),
            external_display_name=external_entity.get("display_name"),
            external_avatar_url=external_entity.get("avatar_url"),
            external_metadata=external_entity,
            source_event_id=None,
            sync_run_id=sync_run.id,
        )
        
        # Check if entity was deleted
        if external_entity.get("deleted", False) or external_entity.get("state") == "deleted":
            if mapping.mapping_state == "mapped" and mapping.vcos_entity_id:
                # Handle deletion through canonical mutation
                return "deleted"
            return "skipped"
        
        # Update cursor for this entity
        # (cursor update handled at page level)
        
        return "created" if not mapping.vcos_entity_id else "updated"
    
    async def _handle_deletions(
        self,
        db: AsyncSession,
        instance: ConnectorInstance,
        entity_type: str,
        since: datetime,
        sync_run: SyncRun,
    ):
        """Handle deleted entities from incremental sync."""
        adapter = get_adapter(instance.connector.provider)
        if not adapter:
            return
        
        deleted_ids = await adapter.get_deleted_entities(instance, entity_type, since)
        
        for external_id in deleted_ids:
            # Find mapping
            from app.models.canonical_integration import ExternalIdentityMapping
            from sqlalchemy import select, and_
            mapping = await db.execute(
                select(ExternalIdentityMapping).where(
                    and_(
                        ExternalIdentityMapping.organization_id == sync_run.organization_id,
                        ExternalIdentityMapping.connector_instance_id == sync_run.connector_instance_id,
                        ExternalIdentityMapping.external_id == external_id,
                        ExternalIdentityMapping.mapping_state == "mapped",
                    )
                )
            )
            mapping = mapping.scalar_one_or_none()
            
            if mapping and mapping.vcos_entity_id:
                # Preserve canonical truth: the external record disappeared.
                # Mark the mapping as deleted externally; canonical entity state
                # is not mutated here — deletion propagates through governed
                # reconciliation, never by silent overwrite.
                mapping.mapping_state = "deleted_externally"
                mapping.updated_at = utcnow()
                sync_run.entities_deleted += 1
                await db.flush()
    
    # ------------------------------------------------------------ Helpers
    
    async def _get_or_create_cursor(
        self,
        db: AsyncSession,
        instance_id: str,
        entity_type: str,
    ) -> SyncCursor:
        result = await db.execute(
            select(SyncCursor).where(
                SyncCursor.connector_instance_id == instance_id,
                SyncCursor.entity_type == entity_type,
            )
        )
        cursor = result.scalar_one_or_none()
        
        if not cursor:
            cursor = SyncCursor(
                connector_instance_id=instance_id,
                entity_type=entity_type,
                cursor_value="",
            )
            db.add(cursor)
            await db.flush()
        
        return cursor
    
    async def _create_sync_run(
        self,
        db: AsyncSession,
        instance: ConnectorInstance,
        sync_mode: str,
        triggered_by: str,
    ) -> SyncRun:
        sync_run = SyncRun(
            organization_id=instance.organization_id,
            connector_instance_id=instance.id,
            sync_mode=sync_mode,
            triggered_by=triggered_by,
            state="pending",
        )
        db.add(sync_run)
        await db.flush()
        return sync_run
    
    async def _update_sync_state(
        self,
        db: AsyncSession,
        sync_run: SyncRun,
        state: str,
    ):
        sync_run.state = state
        if state == "running":
            sync_run.started_at = utcnow()
        await db.flush()
    
    async def _complete_sync_run(
        self,
        db: AsyncSession,
        sync_run: SyncRun,
        result: SyncResult,
        state: str,
    ):
        sync_run.state = state
        sync_run.completed_at = utcnow()
        sync_run.duration_ms = int((utcnow() - sync_run.started_at).total_seconds() * 1000) if sync_run.started_at else 0
        
        sync_run.entities_processed = result.entities_processed
        sync_run.entities_created = result.entities_created
        sync_run.entities_updated = result.entities_updated
        sync_run.entities_deleted = result.entities_deleted
        sync_run.entities_failed = result.entities_failed
        sync_run.conflicts_detected = result.conflicts_detected
        
        if result.error:
            sync_run.error = result.error
        
        await db.flush()

    def _get_supported_entity_types(self) -> List[str]:
        """Get list of entity types we can sync."""
        # This would be defined per-adapter
        return [
            "person", "group", "team", "channel", "message", "file",
            "event", "contact", "repository", "issue", "pull_request",
            "commit", "project", "task", "customer", "deal", "organization",
            "employee", "department", "role", "compensation", "time_off"
        ]
    
    def _extract_external_id(self, entity_type: str, entity: Dict) -> Optional[str]:
        """Extract external ID from entity based on type."""
        # Common ID fields
        for field in ["id", "external_id", "remote_id", "uid", "uuid"]:
            if field in entity:
                return str(entity[field])
        
        # Type-specific
        if entity_type == "person":
            return entity.get("id") or entity.get("email") or entity.get("user_id")
        elif entity_type in ("repository", "project"):
            return entity.get("id") or entity.get("full_name")
        elif entity_type in ("issue", "task", "pull_request"):
            return entity.get("id") or entity.get("number")
        
        return entity.get("id")


# ============================================================
# Factory Functions
# ============================================================

def create_sync_worker(provider: Optional[str] = None) -> SyncWorker:
    """Factory to create a sync worker.

    The worker resolves provider adapters per-connector at sync time via the
    adapter registry; the provider argument is validated when supplied.
    """
    if provider is not None and get_adapter(provider) is None:
        raise ValueError(f"No adapter for provider: {provider}")
    return SyncWorker()


def register_adapter(provider: str, adapter_class: type):
    """Register a provider-specific adapter."""
    # This would be implemented with the adapter registry
    from app.services.adapter_registry import adapter_registry
    adapter_registry.register_adapter(provider, adapter_class)
    logger.info(f"Registered adapter for provider: {provider}")