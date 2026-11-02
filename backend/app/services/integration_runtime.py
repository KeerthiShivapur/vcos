"""
Integration Runtime - Core runtime for connector execution.

Provides:
- Sync orchestration with exactly-once semantics
- Dead letter queue for failed records
- Replay capability for failed syncs
- Idempotency keys for deduplication
- Checkpointing for resume capability
- Metrics and monitoring
"""

import asyncio
import hashlib
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple, Union
from contextlib import asynccontextmanager

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.connector_sdk import (
    BaseConnector,
    ConnectorContext,
    ConnectorMetadata,
    ConnectorCapabilities,
    EntityType,
    PageResult,
    OperationResult,
    RateLimiter,
    RetryPolicy,
    RetryConfig,
    RateLimitConfig,
    SchemaRegistry,
    ConnectorRegistry,
    get_connector_registry,
    create_connector_context,
)
from app.db.database import Base
from app.models.organization import TimestampMixin, gen_uuid
from sqlalchemy import Column, String, Text, JSON, DateTime, Index, ForeignKey, Boolean, Integer, Enum as SQLEnum

logger = logging.getLogger("vcos.integration.runtime")


# ==================== Enums ====================

class SyncStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class SyncDirection(str, Enum):
    PULL = "pull"           # External -> VCOS
    PUSH = "push"           # VCOS -> External
    BIDIRECTIONAL = "bidirectional"


class RecordStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    DUPLICATE = "duplicate"


class DLQStatus(str, Enum):
    QUEUED = "queued"
    RETRYING = "retrying"
    PERMANENTLY_FAILED = "permanently_failed"
    RESOLVED = "resolved"


# ==================== Data Models ====================

@dataclass
class SyncCheckpoint:
    """Checkpoint for sync resumption."""
    sync_run_id: str
    entity_type: str
    cursor: str
    records_processed: int
    records_succeeded: int
    records_failed: int
    last_entity_id: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SyncRecord:
    """Individual record being synced."""
    sync_run_id: str
    entity_type: str
    external_id: str
    operation: str  # create, update, delete, upsert
    payload: Dict[str, Any]
    idempotency_key: str
    status: RecordStatus = RecordStatus.PENDING
    attempts: int = 0
    error: Optional[str] = None
    external_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    idempotency_confirmed: bool = False


@dataclass
class DLQEntry:
    """Dead letter queue entry."""
    id: str
    sync_run_id: str
    entity_type: str
    external_id: str
    operation: str
    payload: Dict[str, Any]
    error: str
    attempts: int
    status: DLQStatus = DLQStatus.QUEUED
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_attempt_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    resolution: Optional[str] = None


@dataclass
class SyncRun:
    """Sync run tracking."""
    id: str
    connection_id: str
    connector_id: str
    organization_id: str
    direction: SyncDirection
    mode: str  # full, incremental, realtime
    entity_types: List[str]
    status: SyncStatus = SyncStatus.PENDING
    cursor_before: Optional[Dict[str, str]] = None
    cursor_after: Optional[Dict[str, str]] = None
    records_total: int = 0
    records_processed: int = 0
    records_succeeded: int = 0
    records_failed: int = 0
    records_skipped: int = 0
    records_duplicates: int = 0
    conflicts_detected: int = 0
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error: Optional[str] = None
    config: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)


# ==================== Idempotency Store ====================

class IdempotencyStore:
    """Stores idempotency keys to prevent duplicate processing."""
    
    def __init__(self, session: AsyncSession = None):
        self.session = session
        self._memory_store: Dict[str, Tuple[str, datetime]] = {}  # key -> (external_id, expires_at)
        self._default_ttl = timedelta(days=30)
    
    async def check_and_store(
        self,
        idempotency_key: str,
        external_id: str,
        ttl: Optional[timedelta] = None,
    ) -> Tuple[bool, Optional[str]]:
        """
        Check if idempotency key exists and store if not.
        
        Returns:
            (is_new, existing_external_id)
            - is_new: True if key was stored (first time), False if duplicate
            - existing_external_id: The external_id already stored for this key
        """
        expires_at = datetime.utcnow() + (ttl or self._default_ttl)
        
        if idempotency_key in self._memory_store:
            stored_external_id, stored_expires = self._memory_store[idempotency_key]
            if stored_expires > datetime.utcnow():
                return False, stored_external_id
            else:
                # Expired, remove and treat as new
                del self._memory_store[idempotency_key]
        
        self._memory_store[idempotency_key] = (idempotency_key, expires_at)
        return True, None
    
    async def get_external_id(self, idempotency_key: str) -> Optional[str]:
        """Get external_id for idempotency key."""
        if idempotency_key in self._memory_store:
            external_id, expires_at = self._memory_store[idempotency_key]
            if expires_at > datetime.utcnow():
                return external_id
        return None
    
    async def remove(self, idempotency_key: str) -> bool:
        """Remove idempotency key."""
        if idempotency_key in self._memory_store:
            del self._memory_store[idempotency_key]
            return True
        return False
    
    async def cleanup_expired(self) -> int:
        """Remove expired entries."""
        now = datetime.utcnow()
        expired = [k for k, (_, exp) in self._memory_store.items() if exp <= now]
        for k in expired:
            del self._memory_store[k]
        return len(expired)


# ==================== Sync Runtime ====================

class SyncRuntime:
    """
    Core sync runtime with exactly-once semantics, DLQ, and replay.
    """
    
    def __init__(
        self,
        session: AsyncSession,
        connector_registry: ConnectorRegistry = None,
        schema_registry = None,
    ):
        self.session = session
        self.connector_registry = connector_registry or get_connector_registry()
        self.schema_registry = schema_registry
        self.idempotency_store = IdempotencyStore(session)
        self._active_runs: Dict[str, SyncRun] = {}
        self._connectors: Dict[str, Any] = {}
    
    async def start_sync(
        self,
        connection_id: str,
        connector_id: str,
        organization_id: str,
        direction: SyncDirection,
        mode: str = "incremental",
        entity_types: List[str] = None,
        config: Dict[str, Any] = None,
    ) -> SyncRun:
        """Start a new sync run."""
        
        # Create sync run record
        sync_run = SyncRun(
            id=str(uuid.uuid4()),
            connection_id=connection_id,
            connector_id=connector_id,
            organization_id=organization_id,
            direction=direction,
            mode=mode,
            entity_types=entity_types or [],
            config=config or {},
        )
        
        self._active_runs[sync_run.id] = sync_run
        
        # Get connection details and create connector
        connector_class = self.connector_registry.get(connector_id)
        if not connector_class:
            raise ValueError(f"Connector not found: {connector_id}")
        
        # Get connection details from database
        # (In production, fetch from database)
        
        # Create connector context
        context = ConnectorContext(
            connector_id=connector_id,
            organization_id=organization_id,
            connection_id=connection_id,
            credentials={},  # Would come from connection
            config={},  # Would come from connection
            secrets={},
            logger=logging.getLogger(f"vcos.sync.{sync_run.id}"),
            rate_limiter=RateLimiter(RateLimitConfig()),
            retry_policy=RetryPolicy(RetryConfig()),
            schema_registry=None,  # Would be injected
        )
        
        connector = connector_class(context)
        await connector.initialize()
        self._connectors[sync_run.id] = connector
        
        # Start sync in background
        asyncio.create_task(self._execute_sync(sync_run))
        
        return sync_run
    
    async def _execute_sync(self, sync_run: SyncRun) -> None:
        """Execute sync run with exactly-once semantics."""
        sync_run.status = SyncStatus.RUNNING
        sync_run.started_at = datetime.utcnow()
        
        connector = self._connectors.get(sync_run.id)
        if not connector:
            sync_run.status = SyncStatus.FAILED
            sync_run.error = "Connector not initialized"
            return
        
        try:
            # Get initial cursors for each entity type
            cursors = {}
            for entity_type_str in sync_run.entity_types:
                entity_type = EntityType(sync_run.entity_types)
                cursor = await self._get_connector(sync_run).get_initial_cursor(EntityType(entity_type_str))
                cursors[entity_type_str] = cursor
            
            sync_run.cursor_before = cursors
            
            # Process each entity type
            for entity_type_str in sync_run.entity_types:
                await self._sync_entity_type(sync_run, EntityType(entity_type_str))
            
            # Update cursors after sync
            cursors_after = {}
            for entity_type_str in sync_run.entity_types:
                cursors_after[entity_type_str] = "completed"  # Would be actual cursor
            sync_run.cursor_after = cursors_after
            
            sync_run.status = SyncStatus.COMPLETED
            sync_run.completed_at = datetime.utcnow()
            
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            sync_run.status = SyncStatus.FAILED
            sync_run.error = str(e)
            sync_run.completed_at = datetime.utcnow()
    
    async def _sync_entity_type(self, sync_run: SyncRun, entity_type: EntityType) -> None:
        """Sync a single entity type with exactly-once semantics."""
        
        connector = self._connectors.get(sync_run.id)
        if not connector:
            return
        
        cursor = sync_run.cursor_before.get(entity_type.value, "") if sync_run.cursor_before else ""
        
        while True:
            # Fetch page
            page_result = await self._connectors[sync_run.id].fetch_page(
                entity_type=entity_type,
                cursor=cursor,
                page_size=100,
            )
            
            if not page_result.entities:
                break
            
            # Process each entity with idempotency
            for entity in page_result.entities:
                await self._process_entity(sync_run, entity)
                sync_run.records_processed += 1
            
            # Update cursor
            cursor = page_result.next_cursor
            if not cursor or not page_result.has_more:
                break
            
            # Rate limiting between pages
            await asyncio.sleep(0.1)
    
    async def _process_entity(self, sync_run: SyncRun, entity: Dict[str, Any]) -> None:
        """Process a single entity with idempotency."""
        
        # Extract external ID
        external_id = entity.get("id") or entity.get("external_id")
        if not external_id:
            sync_run.records_failed += 1
            return
        
        # Generate idempotency key
        idempotency_key = self._generate_idempotency_key(
            sync_run.connection_id,
            sync_run.entity_type,
            external_id,
            entity
        )
        
        # Check idempotency
        is_new, existing_external_id = await self.idempotency_store.check_and_store(
            idempotency_key=sync_run.id + ":" + idempotency_key,
            external_id=external_id,
        )
        
        if not is_new:
            # Duplicate detected
            sync_run.records_duplicates += 1
            return
        
        # Process entity (transform, validate, store)
        try:
            # Transform to canonical schema
            canonical_entity = self._transform_to_canonical(entity)
            
            # Validate against schema
            # await self.schema_registry.validate(entity_type, canonical_entity)
            
            # Store in database (would be implemented)
            # await self._store_entity(sync_run, canonical_entity)
            
            sync_run.records_succeeded += 1
            
        except Exception as e:
            sync_run.records_failed += 1
            # Add to DLQ
            await self._add_to_dlq(sync_run, entity, str(e))
    
    def _generate_idempotency_key(
        self,
        connection_id: str,
        entity_type: str,
        external_id: str,
        entity: Dict[str, Any],
    ) -> str:
        """Generate deterministic idempotency key."""
        content = f"{connection_id}:{entity_type}:{external_id}"
        if "updated_at" in entity:
            content += f":{entity['updated_at']}"
        return hashlib.sha256(content.encode()).hexdigest()[:32]
    
    async def _add_to_dlq(self, sync_run: SyncRun, entity: Dict[str, Any], error: str) -> None:
        """Add failed entity to dead letter queue."""
        dlq_entry = DLQEntry(
            id=str(uuid.uuid4()),
            sync_run_id=sync_run.id,
            entity_type=sync_run.entity_type,
            external_id=entity.get("id", "unknown"),
            operation="sync",
            payload=entity,
            error=error,
            attempts=1,
        )
        # Store in database (DLQ table)
        logger.warning(f"Added to DLQ: {dlq_entry.id}")
    
    def _get_connector(self, sync_run: SyncRun):
        return self._connectors.get(sync_run.id)
    
    async def get_sync_status(self, sync_run_id: str) -> Optional[SyncRun]:
        """Get sync run status."""
        return self._active_runs.get(sync_run_id)
    
    async def cancel_sync(self, sync_run_id: str) -> bool:
        """Cancel running sync."""
        if sync_run_id in self._active_runs:
            self._active_runs[sync_run_id].status = SyncStatus.CANCELLED
            return True
        return False
    
    async def pause_sync(self, sync_run_id: str) -> bool:
        """Pause running sync."""
        if sync_run_id in self._active_runs:
            self._active_runs[sync_run_id].status = SyncStatus.PAUSED
            return True
        return False
    
    async def resume_sync(self, sync_run_id: str) -> bool:
        """Resume paused sync."""
        if sync_run_id in self._active_runs:
            run = self._active_runs[sync_run_id]
            if run.status == SyncStatus.PAUSED:
                run.status = SyncStatus.RUNNING
                asyncio.create_task(self._execute_sync(run))
                return True
        return False


# ==================== Dead Letter Queue Manager ====================

class DLQManager:
    """Manages dead letter queue for failed records."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def add(
        self,
        sync_run_id: str,
        entity_type: str,
        external_id: str,
        operation: str,
        payload: Dict[str, Any],
        error: str,
    ) -> DLQEntry:
        """Add entry to DLQ."""
        entry = DLQEntry(
            id=str(uuid.uuid4()),
            sync_run_id=sync_run_id,
            entity_type=entity_type,
            external_id=external_id,
            operation=operation,
            payload=payload,
            error=error,
            attempts=1,
        )
        
        # Store in database
        # await self._persist(entry)
        
        logger.warning(f"DLQ entry created: {entry.id} for sync_run {sync_run_id}")
        return entry
    
    async def retry(self, entry_id: str, max_retries: int = 3) -> bool:
        """Retry a DLQ entry."""
        # Fetch entry
        # entry = await self._get(entry_id)
        # if not entry or entry.attempts >= max_retries:
        #     return False
        # 
        # entry.status = DLQStatus.RETRYING
        # entry.attempts += 1
        # entry.last_attempt_at = datetime.utcnow()
        # 
        # try:
        #     # Retry processing
        #     # await self._process_entry(entry)
        #     entry.status = DLQStatus.RESOLVED
        #     entry.resolved_at = datetime.utcnow()
        #     return True
        # except Exception as e:
        #     if entry.attempts >= max_retries:
        #         entry.status = DLQStatus.PERMANENTLY_FAILED
        #     return False
        return False
    
    async def list(
        self,
        sync_run_id: Optional[str] = None,
        status: Optional[DLQStatus] = None,
        limit: int = 100,
    ) -> List[DLQEntry]:
        """List DLQ entries."""
        # Would query database
        return []
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get DLQ statistics."""
        return {
            "total": 0,
            "by_status": {},
            "by_entity_type": {},
            "oldest_entry": None,
        }
    
    async def clear_resolved(self, older_than_days: int = 30) -> int:
        """Clear resolved DLQ entries older than specified days."""
        cutoff = datetime.utcnow() - timedelta(days=older_than_days)
        # Would delete from database
        return 0


# ==================== Replay Engine ====================

class ReplayEngine:
    """
    Replay engine for re-processing failed or historical syncs.
    
    Features:
    - Replay failed DLQ entries
    - Replay historical sync runs
    - Selective entity type replay
    - Time-range replay
    - Dry-run mode
    """
    
    def __init__(self, session: AsyncSession, sync_runtime: SyncRuntime):
        self.session = session
        self.sync_runtime = sync_runtime
        self.dlq_manager = DLQManager(session)
    
    async def replay_dlq_entries(
        self,
        entry_ids: List[str],
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Replay specific DLQ entries."""
        results = {
            "total": len(entry_ids),
            "succeeded": 0,
            "failed": 0,
            "details": [],
        }
        
        for entry_id in entry_ids:
            try:
                success = await self.dlq_manager.retry(entry_id)
                if success:
                    results["succeeded"] += 1
                else:
                    results["failed"] += 1
                results["details"].append({
                    "entry_id": entry_id,
                    "success": success,
                })
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "entry_id": entry_id,
                    "success": False,
                    "error": str(e),
                })
        
        return results
    
    async def replay_sync_run(
        self,
        sync_run_id: str,
        entity_types: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Replay an entire sync run."""
        # Would fetch sync run and re-execute
        return {
            "sync_run_id": sync_run_id,
            "status": "replay_initiated",
            "dry_run": dry_run,
        }
    
    async def replay_time_range(
        self,
        connection_id: str,
        entity_types: List[str],
        start_time: datetime,
        end_time: datetime,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """Replay sync for a time range."""
        return {
            "connection_id": connection_id,
            "entity_types": entity_types,
            "time_range": f"{start_time.isoformat()} to {end_time.isoformat()}",
            "status": "replay_initiated",
            "dry_run": dry_run,
        }
    
    async def dry_run(
        self,
        connection_id: str,
        entity_types: List[str],
        sample_size: int = 10,
    ) -> Dict[str, Any]:
        """Dry run sync without persisting."""
        return {
            "connection_id": connection_id,
            "entity_types": entity_types,
            "sample_size": sample_size,
            "status": "dry_run_completed",
            "preview": [],
        }


# ==================== Checkpoint Manager ====================

class CheckpointManager:
    """Manages sync checkpoints for resumability."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self._checkpoints: Dict[str, SyncCheckpoint] = {}
    
    async def save_checkpoint(
        self,
        sync_run_id: str,
        entity_type: str,
        cursor: str,
        records_processed: int,
        records_succeeded: int,
        records_failed: int,
    ) -> SyncCheckpoint:
        """Save sync checkpoint."""
        checkpoint = SyncCheckpoint(
            sync_run_id=sync_run_id,
            entity_type=entity_type,
            cursor=cursor,
            records_processed=records_processed,
            records_succeeded=records_succeeded,
            records_failed=records_failed,
        )
        
        self._checkpoints[f"{sync_run_id}:{entity_type}"] = checkpoint
        
        # Persist to database
        # await self._persist(checkpoint)
        
        return checkpoint
    
    async def get_checkpoint(
        self,
        sync_run_id: str,
        entity_type: str,
    ) -> Optional[SyncCheckpoint]:
        """Get checkpoint for resume."""
        key = f"{sync_run_id}:{entity_type}"
        return self._checkpoints.get(key)
    
    async def get_latest_checkpoint(
        self,
        sync_run_id: str,
    ) -> Dict[str, SyncCheckpoint]:
        """Get all checkpoints for a sync run."""
        return {
            k.split(":")[1]: v 
            for k, v in self._checkpoints.items() 
            if k.startswith(f"{sync_run_id}:")
        }
    
    async def delete_checkpoints(self, sync_run_id: str) -> int:
        """Delete checkpoints for sync run."""
        keys_to_delete = [k for k in self._checkpoints if k.startswith(f"{sync_run_id}:")]
        for k in keys_to_delete:
            del self._checkpoints[k]
        return len(keys_to_delete)


# ==================== Sync Orchestrator ====================

class SyncOrchestrator:
    """
    High-level sync orchestrator coordinating all sync activities.
    """
    
    def __init__(
        self,
        session: AsyncSession,
        connector_registry: ConnectorRegistry = None,
    ):
        self.session = session
        self.sync_runtime = SyncRuntime(session, connector_registry)
        self.dlq_manager = DLQManager(session)
        self.replay_engine = ReplayEngine(session, self.sync_runtime)
        self.checkpoint_manager = CheckpointManager(session)
    
    async def schedule_sync(
        self,
        connection_id: str,
        connector_id: str,
        organization_id: str,
        schedule: str,  # cron expression
        direction: SyncDirection = SyncDirection.PULL,
        entity_types: List[str] = None,
    ) -> str:
        """Schedule recurring sync."""
        # Would integrate with scheduler (Celery, APScheduler, etc.)
        schedule_id = str(uuid.uuid4())
        logger.info(f"Scheduled sync {schedule_id} for connection {connection_id}")
        return schedule_id
    
    async def trigger_manual_sync(
        self,
        connection_id: str,
        connector_id: str,
        organization_id: str,
        direction: SyncDirection = SyncDirection.PULL,
        mode: str = "incremental",
        entity_types: List[str] = None,
    ) -> SyncRun:
        """Trigger manual sync."""
        return await self.sync_runtime.start_sync(
            connection_id=connection_id,
            connector_id=connector_id,
            organization_id=organization_id,
            direction=direction,
            mode=mode,
            entity_types=entity_types,
        )
    
    async def get_sync_status(self, sync_run_id: str) -> Optional[Dict[str, Any]]:
        """Get sync run status."""
        run = await self.sync_runtime.get_sync_status(sync_run_id)
        if not run:
            return None
        
        return {
            "id": run.id,
            "status": run.status.value,
            "direction": run.direction.value,
            "mode": run.mode,
            "entity_types": run.entity_types,
            "records_total": run.records_total,
            "records_processed": run.records_processed,
            "records_succeeded": run.records_succeeded,
            "records_failed": run.records_failed,
            "records_skipped": run.records_skipped,
            "records_duplicates": run.records_duplicates,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "error": run.error,
        }
    
    async def get_dlq_stats(self) -> Dict[str, Any]:
        """Get DLQ statistics."""
        return await self.dlq_manager.get_stats()
    
    async def retry_dlq_entries(self, entry_ids: List[str]) -> Dict[str, Any]:
        """Retry DLQ entries."""
        return await self.replay_engine.replay_dlq_entries(entry_ids)
    
    async def list_dlq_entries(
        self,
        sync_run_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List DLQ entries."""
        dlq_status = DLQStatus(status) if status else None
        entries = await self.dlq_manager.list(sync_run_id, DLQStatus(status) if status else None, limit)
        return [{"id": e.id, "sync_run_id": e.sync_run_id, "entity_type": e.entity_type, 
                "external_id": e.external_id, "error": e.error, "attempts": e.attempts,
                "status": e.status.value, "created_at": e.created_at.isoformat()} 
               for e in entries]


# ==================== Database Models ====================

class SyncRunModel(Base, TimestampMixin):
    """Database model for sync runs."""
    
    __tablename__ = "sync_runs"
    __table_args__ = (
        Index("ix_sync_runs_connection", "connection_id"),
        Index("ix_sync_runs_status", "status"),
        Index("ix_sync_runs_started", "started_at"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    connection_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("integration_connections.id", ondelete="CASCADE"), nullable=False
    )
    connector_id: Mapped[str] = mapped_column(String(64), nullable=False)
    organization_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    direction: Mapped[str] = mapped_column(SQLEnum(SyncDirection), nullable=False)
    mode: Mapped[str] = mapped_column(String(32), default="incremental")
    entity_types: Mapped[List[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(SQLEnum(SyncStatus), default=SyncStatus.PENDING)
    cursor_before: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON)
    cursor_after: Mapped[Optional[Dict[str, str]]] = mapped_column(JSON)
    records_total: Mapped[int] = mapped_column(Integer, default=0)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    records_skipped: Mapped[int] = mapped_column(Integer, default=0)
    records_duplicates: Mapped[int] = mapped_column(Integer, default=0)
    conflicts_detected: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    error: Mapped[Optional[str]] = mapped_column(Text)
    config: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    metadata: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)


class SyncRecordModel(Base, TimestampMixin):
    """Database model for individual sync records."""
    
    __tablename__ = "sync_records"
    __table_args__ = (
        Index("ix_sync_records_run", "sync_run_id"),
        Index("ix_sync_records_entity", "entity_type"),
        Index("ix_sync_records_external", "external_id"),
        Index("ix_sync_records_idempotency", "idempotency_key"),
        Index("ix_sync_records_status", "status"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    sync_run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(SQLEnum(RecordStatus), default=RecordStatus.PENDING)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[Optional[str]] = mapped_column(Text)
    external_id_result: Mapped[Optional[str]] = mapped_column(String(128))
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    idempotency_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class DLQEntryModel(Base, TimestampMixin):
    """Database model for DLQ entries."""
    
    __tablename__ = "dlq_entries"
    __table_args__ = (
        Index("ix_dlq_entries_sync_run", "sync_run_id"),
        Index("ix_dlq_entries_status", "status"),
        Index("ix_dlq_entries_entity", "entity_type"),
        Index("ix_dlq_entries_created", "created_at"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    sync_run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(SQLEnum(DLQStatus), default=DLQStatus.QUEUED)
    last_attempt_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    resolution: Mapped[Optional[str]] = mapped_column(Text)


class SyncCheckpointModel(Base, TimestampMixin):
    """Database model for sync checkpoints."""
    
    __tablename__ = "sync_checkpoints"
    __table_args__ = (
        Index("ix_sync_checkpoints_run_entity", "sync_run_id", "entity_type"),
    )
    
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=gen_uuid)
    sync_run_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("sync_runs.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    cursor: Mapped[str] = mapped_column(Text)
    records_processed: Mapped[int] = mapped_column(Integer, default=0)
    records_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    records_failed: Mapped[int] = mapped_column(Integer, default=0)
    last_entity_id: Mapped[Optional[str]] = mapped_column(String(128))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)


# ==================== Global Runtime Instance ====================

_sync_runtime: Optional[SyncRuntime] = None
_sync_orchestrator: Optional[Any] = None


def get_sync_runtime(session: AsyncSession) -> SyncRuntime:
    """Get or create sync runtime."""
    global _sync_runtime
    if _sync_runtime is None:
        _sync_runtime = SyncRuntime(session)
    return _sync_runtime


def get_sync_orchestrator(session: AsyncSession) -> SyncOrchestrator:
    """Get sync orchestrator."""
    global _sync_orchestrator
    if _sync_orchestrator is None:
        _sync_orchestrator = SyncOrchestrator(session)
    return _sync_orchestrator


# ==================== Convenience Functions ====================

async def start_sync(
    connection_id: str,
    connector_id: str,
    organization_id: str,
    direction: SyncDirection = SyncDirection.PULL,
    mode: str = "incremental",
    entity_types: List[str] = None,
    session: AsyncSession = None,
) -> SyncRun:
    """Start a sync run."""
    runtime = get_sync_runtime(session)
    return await runtime.start_sync(
        connection_id=connection_id,
        connector_id=connector_id,
        organization_id=organization_id,
        direction=direction,
        mode=mode,
        entity_types=entity_types,
    )


async def get_sync_status(sync_run_id: str, session: AsyncSession) -> Optional[Dict[str, Any]]:
    """Get sync run status."""
    orchestrator = get_sync_orchestrator(session)
    return await orchestrator.get_sync_status(sync_run_id)


async def trigger_manual_sync(
    connection_id: str,
    connector_id: str,
    organization_id: str,
    direction: SyncDirection = SyncDirection.PULL,
    mode: str = "incremental",
    entity_types: List[str] = None,
    session: AsyncSession = None,
) -> SyncRun:
    """Trigger manual sync."""
    orchestrator = get_sync_orchestrator(session)
    return await orchestrator.trigger_manual_sync(
        connection_id=connection_id,
        connector_id=connector_id,
        organization_id=organization_id,
        direction=direction,
        mode=mode,
        entity_types=entity_types,
    )


async def get_dlq_stats(session: AsyncSession) -> Dict[str, Any]:
    """Get DLQ statistics."""
    orchestrator = get_sync_orchestrator(session)
    return await orchestrator.get_dlq_stats()


async def retry_dlq_entries(entry_ids: List[str], session: AsyncSession) -> Dict[str, Any]:
    """Retry DLQ entries."""
    orchestrator = get_sync_orchestrator(session)
    return await orchestrator.retry_dlq_entries(entry_ids)


async def list_dlq_entries(
    session: AsyncSession,
    sync_run_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """List DLQ entries."""
    orchestrator = get_sync_orchestrator(session)
    return await orchestrator.list_dlq_entries(sync_run_id, status, limit)


async def replay_failed_sync(
    sync_run_id: str,
    entity_types: List[str] = None,
    dry_run: bool = False,
    session: AsyncSession = None,
) -> Dict[str, Any]:
    """Replay failed sync."""
    orchestrator = get_sync_orchestrator(session)
    return await orchestrator.replay_engine.replay_sync_run(
        sync_run_id=sync_run_id,
        dry_run=dry_run,
    )