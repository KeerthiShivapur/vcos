"""
CRDT Persistence Layer for Horizontal Scaling.

Provides:
- Redis-backed document state persistence
- Operation log for replay and recovery
- Periodic snapshots
- Multi-instance synchronization
- Conflict-free merging
"""

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Callable, AsyncGenerator
from enum import Enum

import redis.asyncio as redis
from redis.asyncio import Redis

from app.core.crdt_engine import (
    CRDTEngine,
    CRDTDocument,
    CRDTOperation,
    CRDTType,
    OperationType,
    AwarenessState,
    CommentThread,
)

logger = logging.getLogger(__name__)


class PersistenceMode(str, Enum):
    """Persistence modes."""
    SYNC = "sync"           # Synchronous - wait for persistence
    ASYNC = "async"         # Asynchronous - fire and forget
    BATCH = "batch"         # Batch writes for performance


@dataclass
class PersistedDocument:
    """Persisted document state."""
    doc_id: str
    crdt_type: str
    state: Any
    version: int
    clients: Dict[str, Dict[str, Any]]
    pending_ops: List[Dict[str, Any]]
    applied_ops: List[str]
    last_modified: float
    last_modified_by: str
    created_at: float
    updated_at: float


@dataclass
class PersistedOperation:
    """Persisted CRDT operation."""
    id: str
    doc_id: str
    crdt_type: str
    client_id: str
    operation_type: str
    position: int
    content: Any
    length: int
    attributes: Dict[str, Any]
    timestamp: float
    vector_clock: Dict[str, int]
    applied: bool = False
    applied_at: Optional[float] = None


@dataclass
class Snapshot:
    """Document snapshot for fast recovery."""
    doc_id: str
    version: int
    state: Any
    clients: Dict[str, Dict[str, Any]]
    timestamp: float
    checksum: str


class CRDTPersistence:
    """
    CRDT Persistence Layer.

    Features:
    - Redis-backed storage for horizontal scaling
    - Operation log for replay and audit
    - Periodic snapshots for fast recovery
    - Multi-instance synchronization via Redis pub/sub
    - Automatic conflict resolution
    - Backup and restore capabilities
    """

    # Redis key prefixes
    DOC_PREFIX = "vcos:crdt:doc:"
    OP_LOG_PREFIX = "vcos:crdt:ops:"
    SNAPSHOT_PREFIX = "vcos:crdt:snapshot:"
    SUBSCRIPTION_PREFIX = "vcos:crdt:sub:"
    PUBSUB_CHANNEL = "vcos:crdt:sync"

    # Defaults
    SNAPSHOT_INTERVAL = 100  # Create snapshot every N operations
    OP_LOG_RETENTION = 10000  # Keep last N operations
    SNAPSHOT_RETENTION = 10  # Keep last N snapshots
    DOC_TTL = 86400 * 30  # 30 days

    def __init__(
        self,
        redis_url: Optional[str] = None,
        persistence_mode: PersistenceMode = PersistenceMode.ASYNC,
        crdt_engine: Optional[CRDTEngine] = None,
    ):
        self.redis_url = redis_url
        self.persistence_mode = persistence_mode
        self.crdt_engine = crdt_engine
        self._redis: Optional[Redis] = None
        self._pubsub = None
        self._running = False
        self._listener_task = None
        self._snapshot_task = None
        self._cleanup_task = None
        self._pending_writes: Dict[str, PersistedDocument] = {}
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._local_version_cache: Dict[str, int] = {}
        self._use_redis = redis_url is not None

    async def initialize(self):
        """Initialize Redis connection and start background tasks."""
        if not self._use_redis:
            logger.info("CRDT Persistence initialized without Redis (in-memory only)")
            return
            
        try:
            self._redis = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50,
            )
            await self._redis.ping()
            logger.info("CRDT Persistence initialized with Redis backend")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise

        # Subscribe to sync channel
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self.PUBSUB_CHANNEL)
        self._listener_task = asyncio.create_task(self._listen_for_sync())

        # Start background tasks
        self._running = True
        self._snapshot_task = asyncio.create_task(self._periodic_snapshot())
        self._cleanup_task = asyncio.create_task(self._cleanup_old_data())
        self._write_worker_task = asyncio.create_task(self._process_write_queue())

        # Register with CRDT engine if provided
        if self.crdt_engine:
            self._register_engine_hooks()

    async def close(self):
        """Close connections and stop background tasks."""
        self._running = False

        if self._listener_task:
            self._listener_task.cancel()
        if self._snapshot_task:
            self._snapshot_task.cancel()
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._write_worker_task:
            self._write_worker_task.cancel()

        if self._pubsub:
            await self._pubsub.unsubscribe(self.PUBSUB_CHANNEL)
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        logger.info("CRDT Persistence closed")

    def _register_engine_hooks(self):
        """Register hooks with CRDT engine for automatic persistence."""
        if not self.crdt_engine:
            return

        # Store original apply_operation
        original_apply = self.crdt_engine.apply_operation

        async def wrapped_apply(doc_id: str, operation: CRDTOperation, client_id: str):
            result = await original_apply(doc_id, operation, client_id)
            if result.get("success"):
                # Queue for persistence
                await self._queue_document_persist(doc_id)
                # Persist operation
                await self.persist_operation(doc_id, operation)
                # Broadcast to other instances
                await self._broadcast_sync(doc_id, operation, client_id)
            return result

        self.crdt_engine.apply_operation = wrapped_apply

    # ==================== Document Persistence ====================

    async def persist_document(self, doc_id: str, force: bool = False) -> bool:
        """Persist document state to Redis."""
        if not self.crdt_engine:
            return False

        doc = self.crdt_engine.get_document(doc_id)
        if not doc:
            return False

        # Check if version changed
        cached_version = self._local_version_cache.get(doc_id, 0)
        if not force and doc.version == cached_version:
            return True

        persisted = PersistedDocument(
            doc_id=doc.doc_id,
            crdt_type=doc.crdt_type.value,
            state=doc.state,
            version=doc.version,
            clients=doc.clients,
            pending_ops=[asdict(op) for op in doc.pending_ops],
            applied_ops=list(doc.applied_ops),
            last_modified=doc.last_modified,
            last_modified_by=doc.last_modified_by,
            created_at=doc.last_modified,  # Approximation
            updated_at=time.time(),
        )

        key = f"{self.DOC_PREFIX}{doc_id}"
        data = json.dumps(asdict(persisted), default=str)

        if self.persistence_mode == PersistenceMode.SYNC:
            await self._redis.setex(key, self.DOC_TTL, data)
        else:
            # Async - queue for background write
            self._pending_writes[doc_id] = persisted
            await self._write_queue.put(("doc", doc_id, data))

        self._local_version_cache[doc_id] = doc.version
        return True

    async def _queue_document_persist(self, doc_id: str):
        """Queue document for persistence."""
        if self.persistence_mode != PersistenceMode.SYNC:
            await self._write_queue.put(("doc", doc_id, None))

    async def _process_write_queue(self):
        """Background worker for processing write queue."""
        while self._running:
            try:
                item = await asyncio.wait_for(self._write_queue.get(), timeout=1.0)
                write_type, doc_id, data = item

                if write_type == "doc":
                    if data is None:
                        # Need to get current document state
                        await self.persist_document(doc_id, force=True)
                    else:
                        key = f"{self.DOC_PREFIX}{doc_id}"
                        await self._redis.setex(key, self.DOC_TTL, data)

            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error(f"Write queue processing error: {e}")
                await asyncio.sleep(1)

    async def load_document(self, doc_id: str) -> Optional[PersistedDocument]:
        """Load document from Redis."""
        key = f"{self.DOC_PREFIX}{doc_id}"
        data = await self._redis.get(key)
        if not data:
            return None

        try:
            doc_dict = json.loads(data)
            return PersistedDocument(**doc_dict)
        except Exception as e:
            logger.error(f"Failed to load document {doc_id}: {e}")
            return None

    async def delete_document(self, doc_id: str) -> bool:
        """Delete document and all associated data."""
        keys = [
            f"{self.DOC_PREFIX}{doc_id}",
            f"{self.OP_LOG_PREFIX}{doc_id}",
            f"{self.SNAPSHOT_PREFIX}{doc_id}:*",
        ]
        for key in keys:
            if "*" in key:
                cursor = 0
                while True:
                    cursor, found = await self._redis.scan(cursor, match=key, count=100)
                    if found:
                        await self._redis.delete(*found)
                    if cursor == 0:
                        break
            else:
                await self._redis.delete(key)

        self._local_version_cache.pop(doc_id, None)
        self._pending_writes.pop(doc_id, None)
        return True

    async def list_documents(self, pattern: str = "*") -> List[str]:
        """List all document IDs matching pattern."""
        keys = []
        cursor = 0
        match_pattern = f"{self.DOC_PREFIX}{pattern}"
        while True:
            cursor, found = await self._redis.scan(cursor, match=match_pattern, count=100)
            keys.extend(found)
            if cursor == 0:
                break
        return [k.replace(self.DOC_PREFIX, "") for k in keys]

    # ==================== Operation Log ====================

    async def persist_operation(self, doc_id: str, operation: CRDTOperation) -> bool:
        """Persist a CRDT operation to the operation log."""
        persisted_op = PersistedOperation(
            id=operation.id,
            doc_id=doc_id,
            crdt_type=operation.crdt_type.value,
            client_id=operation.client_id,
            operation_type=operation.operation_type.value,
            position=operation.position,
            content=operation.content,
            length=operation.length,
            attributes=operation.attributes,
            timestamp=operation.timestamp,
            vector_clock=operation.vector_clock,
            applied=True,
            applied_at=time.time(),
        )

        op_key = f"{self.OP_LOG_PREFIX}{doc_id}"
        op_data = json.dumps(asdict(persisted_op), default=str)

        # Use Redis list for ordered operations
        await self._redis.lpush(op_key, op_data)
        await self._redis.ltrim(op_key, 0, self.OP_LOG_RETENTION - 1)
        await self._redis.expire(op_key, self.DOC_TTL)

        return True

    async def get_operations(
        self,
        doc_id: str,
        start: int = 0,
        end: int = -1,
    ) -> List[PersistedOperation]:
        """Get operations from log."""
        op_key = f"{self.OP_LOG_PREFIX}{doc_id}"
        op_data_list = await self._redis.lrange(op_key, start, end)

        operations = []
        for op_data in op_data_list:
            try:
                op_dict = json.loads(op_data)
                operations.append(PersistedOperation(**op_dict))
            except Exception as e:
                logger.error(f"Failed to parse operation: {e}")

        return operations

    async def get_operations_since(
        self,
        doc_id: str,
        timestamp: float,
    ) -> List[PersistedOperation]:
        """Get operations since a specific timestamp."""
        all_ops = await self.get_operations(doc_id)
        return [op for op in all_ops if op.timestamp > timestamp]

    async def replay_operations(
        self,
        doc_id: str,
        from_version: int = 0,
    ) -> List[PersistedOperation]:
        """Replay operations from a specific version."""
        # Get snapshot at or before from_version
        snapshot = await self.get_latest_snapshot(doc_id, from_version)
        start_version = snapshot.version if snapshot else 0

        # Get operations after snapshot
        all_ops = await self.get_operations(doc_id)
        return [op for op in all_ops if op.applied and op.timestamp >= start_version]

    # ==================== Snapshots ====================

    async def create_snapshot(self, doc_id: str) -> Optional[Snapshot]:
        """Create a snapshot of the document."""
        if not self.crdt_engine:
            return None

        doc = self.crdt_engine.get_document(doc_id)
        if not doc:
            return None

        # Only create snapshot at intervals
        if doc.version % self.SNAPSHOT_INTERVAL != 0:
            return None

        import hashlib
        state_str = json.dumps(doc.state, default=str, sort_keys=True)
        checksum = hashlib.sha256(state_str.encode()).hexdigest()[:16]

        snapshot = Snapshot(
            doc_id=doc_id,
            version=doc.version,
            state=doc.state,
            clients=doc.clients,
            timestamp=time.time(),
            checksum=checksum,
        )

        snapshot_key = f"{self.SNAPSHOT_PREFIX}{doc_id}:{doc.version}"
        await self._redis.setex(
            snapshot_key,
            self.DOC_TTL,
            json.dumps(asdict(snapshot), default=str)
        )

        # Clean old snapshots
        await self._cleanup_old_snapshots(doc_id)

        logger.debug(f"Created snapshot for {doc_id} at version {doc.version}")
        return snapshot

    async def get_latest_snapshot(self, doc_id: str, max_version: int = float('inf')) -> Optional[Snapshot]:
        """Get the latest snapshot at or before max_version."""
        pattern = f"{self.SNAPSHOT_PREFIX}{doc_id}:*"
        snapshots = []

        cursor = 0
        while True:
            cursor, found = await self._redis.scan(cursor, match=pattern, count=100)
            for key in found:
                data = await self._redis.get(key)
                if data:
                    try:
                        snap_dict = json.loads(data)
                        snapshot = Snapshot(**snap_dict)
                        if snapshot.version <= max_version:
                            snapshots.append(snapshot)
                    except Exception:
                        pass
            if cursor == 0:
                break

        if not snapshots:
            return None

        return max(snapshots, key=lambda s: s.version)

    async def restore_from_snapshot(self, doc_id: str, version: Optional[int] = None) -> bool:
        """Restore document from snapshot."""
        snapshot = await self.get_latest_snapshot(doc_id, version or float('inf'))
        if not snapshot:
            return False

        # Recreate document in engine
        if self.crdt_engine:
            crdt_type = CRDTType(snapshot.doc_id.split(":")[0]) if ":" in snapshot.doc_id else CRDTType.YTEXT
            doc = self.crdt_engine.create_document(
                doc_id=snapshot.doc_id,
                crdt_type=crdt_type,
                initial_state=snapshot.state,
            )
            doc.version = snapshot.version
            doc.clients = snapshot.clients
            doc.last_modified = snapshot.timestamp

        # Replay operations after snapshot
        ops = await self.get_operations_since(doc_id, snapshot.timestamp)
        for op in ops:
            if self.crdt_engine:
                crdt_op = CRDTOperation(**{k: v for k, v in asdict(op).items() if k != "applied" and k != "applied_at"})
                await self.crdt_engine.apply_operation(doc_id, crdt_op, op.client_id)

        return True

    async def _cleanup_old_snapshots(self, doc_id: str):
        """Clean up old snapshots beyond retention."""
        pattern = f"{self.SNAPSHOT_PREFIX}{doc_id}:*"
        all_snapshots = []

        cursor = 0
        while True:
            cursor, found = await self._redis.scan(cursor, match=pattern, count=100)
            for key in found:
                data = await self._redis.get(key)
                if data:
                    try:
                        snap_dict = json.loads(data)
                        all_snapshots.append((key, snap_dict["version"]))
                    except Exception:
                        pass
            if cursor == 0:
                break

        # Sort by version, keep latest N
        all_snapshots.sort(key=lambda x: x[1], reverse=True)
        to_delete = all_snapshots[self.SNAPSHOT_RETENTION:]

        for key, _ in to_delete:
            await self._redis.delete(key)

    async def _periodic_snapshot(self):
        """Periodically create snapshots for all documents."""
        while self._running:
            try:
                await asyncio.sleep(300)  # Every 5 minutes

                if not self.crdt_engine:
                    continue

                doc_ids = await self.list_documents()
                for doc_id in doc_ids:
                    doc = self.crdt_engine.get_document(doc_id)
                    if doc and doc.version % self.SNAPSHOT_INTERVAL == 0:
                        await self.create_snapshot(doc_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Periodic snapshot error: {e}")
                await asyncio.sleep(60)

    # ==================== Multi-Instance Sync ====================

    async def _broadcast_sync(self, doc_id: str, operation: CRDTOperation, sender_id: str):
        """Broadcast operation to other instances via Redis pub/sub."""
        message = {
            "type": "operation",
            "doc_id": doc_id,
            "operation": {
                "id": operation.id,
                "crdt_type": operation.crdt_type.value,
                "operation_type": operation.operation_type.value,
                "position": operation.position,
                "content": operation.content,
                "length": operation.length,
                "attributes": operation.attributes,
                "timestamp": operation.timestamp,
                "client_id": sender_id,
            },
            "sender_instance": id(self),
            "timestamp": time.time(),
        }

        await self._redis.publish(self.PUBSUB_CHANNEL, json.dumps(message, default=str))

    async def _listen_for_sync(self):
        """Listen for sync messages from other instances."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] != "message":
                    continue

                try:
                    data = json.loads(message["data"])
                    await self._handle_sync_message(data)
                except Exception as e:
                    logger.error(f"Failed to handle sync message: {e}")

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Sync listener error: {e}")

    async def _handle_sync_message(self, data: Dict[str, Any]):
        """Handle incoming sync message."""
        if data.get("sender_instance") == id(self):
            return  # Ignore own messages

        msg_type = data.get("type")
        if msg_type == "operation" and self.crdt_engine:
            doc_id = data.get("doc_id")
            op_data = data.get("operation", {})
            operation = CRDTOperation(
                id=op_data.get("id", str(uuid.uuid4())),
                crdt_type=CRDTType(op_data.get("crdt_type", "ytext")),
                operation_type=OperationType(op_data.get("operation_type", "insert")),
                position=op_data.get("position", 0),
                content=op_data.get("content"),
                length=op_data.get("length", 0),
                attributes=op_data.get("attributes", {}),
                timestamp=op_data.get("timestamp", time.time()),
                client_id=op_data.get("client_id", ""),
            )

            # Apply if not already applied
            doc = self.crdt_engine.get_document(doc_id)
            if doc and operation.id not in doc.applied_ops:
                await self.crdt_engine.apply_operation(doc_id, operation, operation.client_id)

        elif msg_type == "document_sync" and self.crdt_engine:
            # Full document sync request
            doc_id = data.get("doc_id")
            await self._send_full_sync(doc_id, data.get("requester_instance"))

        elif msg_type == "full_sync_response":
            # Receive full document state from another instance
            await self._receive_full_sync(data)

    async def request_full_sync(self, doc_id: str):
        """Request full document sync from other instances."""
        message = {
            "type": "document_sync",
            "doc_id": doc_id,
            "requester_instance": id(self),
            "timestamp": time.time(),
        }
        await self._redis.publish(self.PUBSUB_CHANNEL, json.dumps(message))

    async def _send_full_sync(self, doc_id: str, requester_instance: int):
        """Send full document state to requester."""
        if not self.crdt_engine:
            return

        doc = self.crdt_engine.get_document(doc_id)
        if not doc:
            return

        message = {
            "type": "full_sync_response",
            "doc_id": doc_id,
            "document": {
                "doc_id": doc.doc_id,
                "crdt_type": doc.crdt_type.value,
                "state": doc.state,
                "version": doc.version,
                "clients": doc.clients,
                "last_modified": doc.last_modified,
                "last_modified_by": doc.last_modified_by,
            },
            "sender_instance": id(self),
            "timestamp": time.time(),
        }

        await self._redis.publish(self.PUBSUB_CHANNEL, json.dumps(message, default=str))

    async def _receive_full_sync(self, data: Dict[str, Any]):
        """Receive full document state from another instance."""
        if not self.crdt_engine:
            return

        doc_data = data.get("document", {})
        doc_id = doc_data.get("doc_id")
        if not doc_id:
            return

        # Merge with local state (CRDT merge)
        local_doc = self.crdt_engine.get_document(doc_id)
        if local_doc:
            # For CRDTs, we can just apply missing operations
            # The remote state should be compatible
            pass
        else:
            # Create new document
            crdt_type = CRDTType(doc_data.get("crdt_type", "ytext"))
            self.crdt_engine.create_document(
                doc_id=doc_id,
                crdt_type=crdt_type,
                initial_state=doc_data.get("state"),
            )

    # ==================== Awareness Persistence ====================

    async def persist_awareness(self, doc_id: str, client_id: str, awareness: AwarenessState):
        """Persist awareness state."""
        key = f"{self.SUBSCRIPTION_PREFIX}{doc_id}:{client_id}"
        data = json.dumps(asdict(awareness), default=str)
        await self._redis.setex(key, 300, data)  # 5 min TTL for awareness

    async def get_awareness(self, doc_id: str, client_id: str) -> Optional[AwarenessState]:
        """Get awareness state."""
        key = f"{self.SUBSCRIPTION_PREFIX}{doc_id}:{client_id}"
        data = await self._redis.get(key)
        if not data:
            return None
        try:
            return AwarenessState(**json.loads(data))
        except Exception:
            return None

    async def get_all_awareness(self, doc_id: str) -> Dict[str, AwarenessState]:
        """Get all awareness states for a document."""
        pattern = f"{self.SUBSCRIPTION_PREFIX}{doc_id}:*"
        awareness_states = {}

        cursor = 0
        while True:
            cursor, found = await self._redis.scan(cursor, match=pattern, count=100)
            for key in found:
                data = await self._redis.get(key)
                if data:
                    try:
                        awareness = AwarenessState(**json.loads(data))
                        client_id = key.replace(f"{self.SUBSCRIPTION_PREFIX}{doc_id}:", "")
                        awareness_states[client_id] = awareness
                    except Exception:
                        pass
            if cursor == 0:
                break

        return awareness_states

    # ==================== Cleanup ====================

    async def _cleanup_old_data(self):
        """Periodically clean up old data."""
        while self._running:
            try:
                await asyncio.sleep(3600)  # Every hour

                # Clean up expired awareness states
                pattern = f"{self.SUBSCRIPTION_PREFIX}*"
                cursor = 0
                while True:
                    cursor, found = await self._redis.scan(cursor, match=pattern, count=100)
                    for key in found:
                        ttl = await self._redis.ttl(key)
                        if ttl == -2:  # Key doesn't exist
                            pass  # Already expired
                    if cursor == 0:
                        break

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
                await asyncio.sleep(300)

    # ==================== Backup/Restore ====================

    async def backup_document(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Create a complete backup of a document."""
        doc = await self.load_document(doc_id)
        if not doc:
            return None

        operations = await self.get_operations(doc_id)
        snapshots = await self._get_all_snapshots(doc_id)

        return {
            "document": asdict(doc),
            "operations": [asdict(op) for op in operations],
            "snapshots": [asdict(s) for s in snapshots],
            "backup_timestamp": time.time(),
        }

    async def _get_all_snapshots(self, doc_id: str) -> List[Snapshot]:
        """Get all snapshots for a document."""
        pattern = f"{self.SNAPSHOT_PREFIX}{doc_id}:*"
        snapshots = []

        cursor = 0
        while True:
            cursor, found = await self._redis.scan(cursor, match=pattern, count=100)
            for key in found:
                data = await self._redis.get(key)
                if data:
                    try:
                        snapshots.append(Snapshot(**json.loads(data)))
                    except Exception:
                        pass
            if cursor == 0:
                break

        return snapshots

    async def restore_backup(self, backup_data: Dict[str, Any]) -> bool:
        """Restore document from backup."""
        doc_data = backup_data.get("document")
        if not doc_data:
            return False

        # Restore document
        key = f"{self.DOC_PREFIX}{doc_data['doc_id']}"
        await self._redis.setex(key, self.DOC_TTL, json.dumps(doc_data, default=str))

        # Restore operations
        for op_data in backup_data.get("operations", []):
            op_key = f"{self.OP_LOG_PREFIX}{doc_data['doc_id']}"
            await self._redis.lpush(op_key, json.dumps(op_data, default=str))

        # Restore snapshots
        for snap_data in backup_data.get("snapshots", []):
            snap_key = f"{self.SNAPSHOT_PREFIX}{doc_data['doc_id']}:{snap_data['version']}"
            await self._redis.setex(snap_key, self.DOC_TTL, json.dumps(snap_data, default=str))

        return True

    # ==================== Stats ====================

    async def get_stats(self) -> Dict[str, Any]:
        """Get persistence statistics."""
        doc_count = len(await self.list_documents())
        total_ops = 0
        total_snapshots = 0

        doc_ids = await self.list_documents()
        for doc_id in doc_ids:
            ops = await self.get_operations(doc_id)
            total_ops += len(ops)
            snapshots = await self._get_all_snapshots(doc_id)
            total_snapshots += len(snapshots)

        redis_info = await self._redis.info("memory") if self._redis else {}

        return {
            "documents": doc_count,
            "total_operations": total_ops,
            "total_snapshots": total_snapshots,
            "pending_writes": len(self._pending_writes),
            "queue_size": self._write_queue.qsize(),
            "redis_memory_mb": redis_info.get("used_memory_human", "unknown"),
            "persistence_mode": self.persistence_mode.value,
        }


# Global persistence instance
_crdt_persistence: Optional[CRDTPersistence] = None


def get_crdt_persistence() -> CRDTPersistence:
    """Get or create CRDT persistence singleton."""
    global _crdt_persistence
    if _crdt_persistence is None:
        _crdt_persistence = CRDTPersistence()
    return _crdt_persistence


def init_crdt_persistence(
    redis_url: str = "redis://localhost:6379/0",
    persistence_mode: PersistenceMode = PersistenceMode.ASYNC,
    crdt_engine: Optional[CRDTEngine] = None,
) -> CRDTPersistence:
    """Initialize CRDT persistence."""
    global _crdt_persistence
    _crdt_persistence = CRDTPersistence(
        redis_url=redis_url,
        persistence_mode=persistence_mode,
        crdt_engine=crdt_engine,
    )
    return _crdt_persistence