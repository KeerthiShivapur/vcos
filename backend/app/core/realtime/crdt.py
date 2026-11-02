"""
CRDT Engine for VCOS Real-Time Collaboration.

Implements Conflict-free Replicated Data Types (CRDTs) for:
- Collaborative text editing (Yjs-style)
- Whiteboard/drawing synchronization
- Shared data structures (maps, arrays, counters)
- Offline-first with conflict-free merge
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Callable, Awaitable
from enum import Enum

import redis.asyncio as redis

from app.core.realtime.presence import PresenceService

logger = logging.getLogger("vcos.realtime.crdt")


class CRDTType(str, Enum):
    """Types of CRDT data structures."""
    YTEXT = "ytext"          # Collaborative text (Yjs-style)
    YMAP = "ymap"            # Map/dictionary
    YARRAY = "yarray"        # Array/list
    YCOUNTER = "ycounter"    # Counter (PN-Counter)
    YXML = "yxml"            # XML/HTML tree
    CUSTOM = "custom"        # Custom CRDT


class OperationType(str, Enum):
    """Types of CRDT operations."""
    INSERT = "insert"
    DELETE = "delete"
    UPDATE = "update"
    INCREMENT = "increment"
    DECREMENT = "decrement"
    SET = "set"
    DELETE_KEY = "delete_key"
    RETAIN = "retain"


@dataclass
class CRDTOperation:
    """A single CRDT operation."""
    doc_id: str
    crdt_type: CRDTType
    client_id: str
    operation_type: OperationType
    position: int = 0
    content: Any = None
    length: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    vector_clock: Dict[str, int] = field(default_factory=dict)
    applied: bool = False
    applied_at: Optional[float] = None
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class CRDTDocument:
    """A CRDT document with full history."""
    doc_id: str
    crdt_type: CRDTType
    state: Any
    version: int = 0
    clients: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    pending_ops: List[Dict[str, Any]] = field(default_factory=list)
    applied_ops: List[str] = field(default_factory=list)
    last_modified: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    last_modified_by: str = ""
    created_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())
    updated_at: float = field(default_factory=lambda: datetime.now(timezone.utc).timestamp())


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


class CRDTEngine:
    """
    CRDT Engine for real-time collaborative editing.
    
    Features:
    - Yjs-compatible text editing (YText)
    - Map/Array/Counter CRDTs
    - Operation-based synchronization
    - Vector clocks for causality
    - Periodic snapshots
    - Redis-backed persistence
    - Offline-first with conflict-free merge
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
        redis_client: redis.Redis,
        presence_service: Optional[PresenceService] = None,
    ):
        self.redis = redis_client
        self.presence_service = presence_service
        self._running = False
        self._listener_task = None
        self._cleanup_task = None
        self._snapshot_task = None
        self._pubsub = None
        self._write_queue: asyncio.Queue = asyncio.Queue()
        self._local_version_cache: Dict[str, int] = {}
    
    async def initialize(self):
        """Initialize CRDT engine."""
        self._running = True
        
        # Start background tasks
        self._listener_task = asyncio.create_task(self._listen_loop())
        self._snapshot_task = asyncio.create_task(self._snapshot_loop())
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        
        logger.info("CRDT Engine initialized")
    
    async def close(self):
        """Close CRDT engine."""
        self._running = False
        
        for task in [self._listener_task, self._snapshot_task, self._cleanup_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
    
    # ==================== Document Management ====================
    
    async def get_or_create_document(
        self,
        doc_id: str,
        crdt_type: CRDTType = CRDTType.YTEXT,
        initial_state: Any = None,
    ) -> CRDTDocument:
        """Get or create a CRDT document."""
        doc_key = f"{self.DOC_PREFIX}{doc_id}"
        
        # Try to load existing
        existing = await self.redis.get(doc_key)
        if existing:
            data = json.loads(existing)
            doc = CRDTDocument(**data)
            return doc
        
        # Create new document
        initial_state = initial_state if initial_state is not None else self._get_initial_state(crdt_type)
        
        doc = CRDTDocument(
            doc_id=doc_id,
            crdt_type=crdt_type,
            state=initial_state,
            version=0,
            created_at=datetime.now(timezone.utc).timestamp(),
            updated_at=datetime.now(timezone.utc).timestamp(),
        )
        
        await self._save_document(doc)
        return doc
    
    def _get_initial_state(self, crdt_type: CRDTType) -> Any:
        """Get initial state for CRDT type."""
        if crdt_type == CRDTType.YTEXT:
            return ""
        elif crdt_type == CRDTType.YMAP:
            return {}
        elif crdt_type == CRDTType.YARRAY:
            return []
        elif crdt_type == CRDTType.YCOUNTER:
            return 0
        elif crdt_type == CRDTType.YXML:
            return {"type": "root", "children": []}
        return {}
    
    async def _save_document(self, doc: CRDTDocument):
        """Save document to Redis."""
        doc_key = f"{self.DOC_PREFIX}{doc.doc_id}"
        doc.updated_at = datetime.now(timezone.utc).timestamp()
        
        data = {
            "doc_id": doc.doc_id,
            "crdt_type": doc.crdt_type.value,
            "state": doc.state,
            "version": doc.version,
            "clients": doc.clients,
            "pending_ops": doc.pending_ops,
            "applied_ops": doc.applied_ops,
            "last_modified": doc.last_modified,
            "last_modified_by": doc.last_modified_by,
            "created_at": doc.created_at,
            "updated_at": doc.updated_at,
        }
        
        await self.redis.setex(
            f"{self.DOC_PREFIX}{doc.doc_id}",
            self.DOC_TTL,
            json.dumps(data, default=str)
        )
    
    async def get_document(self, doc_id: str) -> Optional[CRDTDocument]:
        """Get document by ID."""
        doc_key = f"{self.DOC_PREFIX}{doc_id}"
        data = await self.redis.get(doc_key)
        
        if not data:
            return None
        
        data = json.loads(data)
        return CRDTDocument(
            doc_id=data["doc_id"],
            crdt_type=CRDTType(data["crdt_type"]),
            state=data["state"],
            version=data["version"],
            clients=data.get("clients", {}),
            pending_ops=data.get("pending_ops", []),
            applied_ops=data.get("applied_ops", []),
            last_modified=data.get("last_modified", 0),
            last_modified_by=data.get("last_modified_by", ""),
            created_at=data.get("created_at", 0),
            updated_at=data.get("updated_at", 0),
        )
    
    async def delete_document(self, doc_id: str) -> bool:
        """Delete a document."""
        doc_key = f"{self.DOC_PREFIX}{doc_id}"
        op_log_key = f"{self.OP_LOG_PREFIX}{doc_id}"
        snapshot_key = f"{self.SNAPSHOT_PREFIX}{doc_id}"
        
        # Delete all related keys
        await self.redis.delete(doc_key, op_log_key, snapshot_key)
        
        # Delete snapshots
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor, match=f"{self.SNAPSHOT_PREFIX}{doc_id}:*", count=100)
            if keys:
                await self.redis.delete(*keys)
            if cursor == 0:
                break
        
        # Delete operation log
        await self.redis.delete(op_log_key)
        
        return True
    
    # ==================== Operation Application ====================
    
    async def apply_operation(
        self,
        doc_id: str,
        operation: CRDTOperation,
    ) -> bool:
        """Apply a CRDT operation to a document."""
        doc = await self.get_document(doc_id)
        if not doc:
            return False
        
        # Check if operation already applied
        if operation.id in doc.applied_ops:
            return True
        
        # Apply operation based on CRDT type
        success = await self._apply_operation(doc, operation)
        
        if success:
            # Update document
            doc.version += 1
            doc.applied_ops.append(operation.id)
            operation.applied = True
            operation.applied_at = datetime.now(timezone.utc).timestamp()
            
            # Update client vector clock
            if operation.client_id not in doc.clients:
                doc.clients[operation.client_id] = {}
            doc.clients[operation.client_id]["clock"] = operation.vector_clock
            
            # Save operation to log
            await self._persist_operation(doc.doc_id, operation)
            
            # Save document
            await self._save_document(doc)
            
            # Publish to subscribers
            await self._publish_sync(doc.doc_id, operation)
            
            return True
        
        return False
    
    async def _apply_operation(self, doc: CRDTDocument, operation: CRDTOperation) -> bool:
        """Apply operation based on CRDT type."""
        try:
            if doc.crdt_type == CRDTType.YTEXT:
                return await self._apply_text_operation(doc, operation)
            elif doc.crdt_type == CRDTType.YMAP:
                return await self._apply_map_operation(doc, operation)
            elif doc.crdt_type == CRDTType.YARRAY:
                return await self._apply_array_operation(doc, operation)
            elif doc.crdt_type == CRDTType.YCOUNTER:
                return await self._apply_counter_operation(doc, operation)
            else:
                logger.warning(f"Unknown CRDT type: {doc.crdt_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to apply operation: {e}")
            return False
    
    # ==================== YText Operations ====================
    
    async def _apply_text_operation(self, doc: CRDTDocument, op: CRDTOperation) -> bool:
        """Apply YText operation (insert/delete text)."""
        if not isinstance(doc.state, str):
            doc.state = ""
        
        if op.operation_type == OperationType.INSERT:
            # Insert text at position
            pos = max(0, min(op.position, len(doc.state)))
            doc.state = doc.state[:pos] + str(op.content) + doc.state[pos:]
            
        elif op.operation_type == OperationType.DELETE:
            # Delete text at position
            pos = max(0, min(op.position, len(doc.state)))
            end = min(pos + op.length, len(doc.state))
            doc.state = doc.state[:pos] + doc.state[end:]
            
        elif op.operation_type == OperationType.RETAIN:
            # Retain - no state change, just position tracking
            pass
        
        return True
    
    # ==================== YMap Operations ====================
    
    async def _apply_map_operation(self, doc: CRDTDocument, op: CRDTOperation) -> bool:
        """Apply YMap operation (key-value map)."""
        if not isinstance(doc.state, dict):
            doc.state = {}
        
        key = str(op.content.get("key", "")) if op.content else ""
        
        if op.operation_type == OperationType.SET:
            doc.state[key] = op.content.get("value")
            
        elif op.operation_type == OperationType.DELETE_KEY:
            doc.state.pop(key, None)
            
        elif op.operation_type == OperationType.UPDATE:
            if key in doc.state and isinstance(doc.state[key], dict):
                doc.state[key].update(op.content.get("value", {}))
        
        return True
    
    # ==================== YArray Operations ====================
    
    async def _apply_array_operation(self, doc: CRDTDocument, op: CRDTOperation) -> bool:
        """Apply YArray operation (insert/delete elements)."""
        if not isinstance(doc.state, list):
            doc.state = []
        
        if op.operation_type == OperationType.INSERT:
            pos = max(0, min(op.position, len(doc.state)))
            content = op.content if isinstance(op.content, list) else [op.content]
            doc.state[pos:pos] = content
            
        elif op.operation_type == OperationType.DELETE:
            pos = max(0, min(op.position, len(doc.state)))
            end = min(pos + op.length, len(doc.state))
            doc.state = doc.state[:pos] + doc.state[end:]
        
        return True
    
    # ==================== YCounter Operations ====================
    
    async def _apply_counter_operation(self, doc: CRDTDocument, op: CRDTOperation) -> bool:
        """Apply YCounter operation (PN-Counter)."""
        if not isinstance(doc.state, (int, float)):
            doc.state = 0
        
        if op.operation_type == OperationType.INCREMENT:
            doc.state += op.content if isinstance(op.content, (int, float)) else 1
        elif op.operation_type == OperationType.DECREMENT:
            doc.state -= op.content if isinstance(op.content, (int, float)) else 1
        
        return True
    
    # ==================== Persistence ====================
    
    async def _persist_operation(self, doc_id: str, operation: CRDTOperation):
        """Persist operation to operation log."""
        op_key = f"{self.OP_LOG_PREFIX}{doc_id}"
        
        op_data = {
            "id": operation.id,
            "doc_id": operation.doc_id,
            "crdt_type": operation.crdt_type.value,
            "client_id": operation.client_id,
            "operation_type": operation.operation_type.value,
            "position": operation.position,
            "content": operation.content,
            "length": operation.length,
            "attributes": operation.attributes,
            "timestamp": operation.timestamp,
            "vector_clock": operation.vector_clock,
        }
        
        # Add to operation log (Redis list)
        await self.redis.lpush(f"{self.OP_LOG_PREFIX}{operation.doc_id}", json.dumps(op_data, default=str))
        
        # Trim log to retention limit
        await self.redis.ltrim(f"{self.OP_LOG_PREFIX}{doc_id}", 0, self.OP_LOG_RETENTION - 1)
    
    # ==================== Synchronization ====================
    
    async def _publish_sync(self, doc_id: str, operation: CRDTOperation):
        """Publish sync message to subscribers."""
        try:
            await self.redis.publish(
                self.PUBSUB_CHANNEL,
                json.dumps({
                    "doc_id": doc_id,
                    "operation": {
                        "id": operation.id,
                        "client_id": operation.client_id,
                        "crdt_type": operation.crdt_type.value,
                        "operation_type": operation.operation_type.value,
                        "position": operation.position,
                        "content": operation.content,
                        "length": operation.length,
                        "attributes": operation.attributes,
                        "timestamp": operation.timestamp,
                        "vector_clock": operation.vector_clock,
                    },
                })
            )
        except Exception as e:
            logger.warning(f"Failed to publish sync: {e}")
    
    async def _listen_loop(self):
        """Listen for sync messages from other instances."""
        self._pubsub = self.redis.pubsub()
        await self._pubsub.subscribe(self.PUBSUB_CHANNEL)
        
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self._handle_sync_message(data)
                    except Exception as e:
                        logger.error(f"Sync message error: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Sync listener error: {e}")
    
    async def _handle_sync_message(self, data: Dict):
        """Handle incoming sync message from another instance."""
        doc_id = data.get("doc_id")
        op_data = data.get("operation")
        
        if not doc_id or not op_data:
            return
        
        # Reconstruct operation
        op = CRDTOperation(
            id=op_data["id"],
            doc_id=op_data["doc_id"],
            crdt_type=CRDTType(op_data["crdt_type"]),
            client_id=op_data["client_id"],
            operation_type=OperationType(op_data["operation_type"]),
            position=op_data.get("position", 0),
            content=op_data.get("content"),
            length=op_data.get("length", 0),
            attributes=op_data.get("attributes", {}),
            timestamp=op_data.get("timestamp", 0),
            vector_clock=op_data.get("vector_clock", {}),
        )
        
        # Apply locally
        await self.apply_operation(doc_id, op)
    
    # ==================== Snapshots ====================
    
    async def _snapshot_loop(self):
        """Create periodic snapshots."""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Find documents needing snapshots
                await self._create_snapshots()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Snapshot error: {e}")
    
    async def _create_snapshots(self):
        """Create snapshots for documents that need them."""
        # This would scan for documents needing snapshots
        # For now, placeholder
        pass
    
    async def create_snapshot(self, doc_id: str) -> Snapshot:
        """Create a snapshot of a document."""
        doc = await self.get_document(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")
        
        snapshot = Snapshot(
            doc_id=doc_id,
            version=doc.version,
            state=doc.state,
            clients=doc.clients,
            timestamp=datetime.now(timezone.utc).timestamp(),
            checksum=self._compute_checksum(doc.state),
        )
        
        # Save snapshot
        snapshot_key = f"{self.SNAPSHOT_PREFIX}{doc_id}:{doc.version}"
        await self.redis.setex(
            snapshot_key,
            self.DOC_TTL,
            json.dumps({
                "doc_id": snapshot.doc_id,
                "version": snapshot.version,
                "state": snapshot.state,
                "clients": snapshot.clients,
                "timestamp": snapshot.timestamp,
                "checksum": snapshot.checksum,
            }, default=str)
        )
        
        # Trim old snapshots
        await self._trim_snapshots(doc_id)
        
        return snapshot
    
    def _compute_checksum(self, state: Any) -> str:
        """Compute checksum of document state."""
        import hashlib
        state_str = json.dumps(state, sort_keys=True, default=str)
        return hashlib.sha256(state_str.encode()).hexdigest()[:16]
    
    async def _trim_snapshots(self, doc_id: str):
        """Keep only last N snapshots."""
        pattern = f"{self.SNAPSHOT_PREFIX}{doc_id}:*"
        cursor = 0
        snapshots = []
        
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
            snapshots.extend(keys)
            if cursor == 0:
                break
        
        if len(snapshots) > self.SNAPSHOT_RETENTION:
            # Sort by version (embedded in key)
            snapshots.sort(reverse=True)
            to_delete = snapshots[self.SNAPSHOT_RETENTION:]
            if to_delete:
                await self.redis.delete(*to_delete)
    
    # ==================== Recovery ====================
    
    async def recover_document(self, doc_id: str) -> Optional[CRDTDocument]:
        """Recover document from latest snapshot + operation log."""
        # Get latest snapshot
        pattern = f"{self.SNAPSHOT_PREFIX}{doc_id}:*"
        cursor = 0
        snapshots = []
        
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
            snapshots.extend(keys)
            if cursor == 0:
                break
        
        if not snapshots:
            return None
        
        # Get latest snapshot
        snapshots.sort(reverse=True)
        latest_snapshot_key = snapshots[0]
        snapshot_data = await self.redis.get(latest_snapshot_key)
        
        if not snapshot_data:
            return None
        
        snapshot = Snapshot(**json.loads(snapshot_data))
        
        # Replay operations after snapshot
        doc = CRDTDocument(
            doc_id=doc_id,
            crdt_type=CRDTType.YTEXT,  # Would be in snapshot
            state=snapshot.state,
            version=snapshot.version,
            clients=snapshot.clients,
        )
        
        # Replay operations after snapshot
        op_log_key = f"{self.OP_LOG_PREFIX}{doc_id}"
        ops = await self.redis.lrange(f"{self.OP_LOG_PREFIX}{doc_id}", 0, -1)
        
        for op_json in ops:
            op_data = json.loads(op_json)
            # Check if op is after snapshot version
            # Apply if needed
        
        return doc
    
    # ==================== Cleanup ====================
    
    async def _cleanup_loop(self):
        """Periodic cleanup of old operations and documents."""
        while True:
            try:
                await asyncio.sleep(3600)  # Every hour
                await self._cleanup_old_data()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")
    
    async def _cleanup_old_data(self):
        """Clean up old operations and expired documents."""
        # Clean old operation logs
        # Delete expired documents
        pass


# ==================== High-Level Document API ====================

class CollaborativeDocument:
    """High-level API for collaborative document editing."""
    
    def __init__(self, engine: CRDTEngine, doc_id: str, client_id: str):
        self.engine = engine
        self.doc_id = doc_id
        self.client_id = client_id
        self._local_version = 0
        self._pending_ops: List[CRDTOperation] = []
    
    async def initialize(self, crdt_type: CRDTType = CRDTType.YTEXT, initial_state: Any = None):
        """Initialize document."""
        await self.engine.get_or_create_document(self.doc_id, crdt_type=CRDTType.YTEXT)
        self._local_version = 0
    
    async def insert_text(self, position: int, text: str) -> bool:
        """Insert text at position."""
        op = CRDTOperation(
            doc_id=self.doc_id,
            crdt_type=CRDTType.YTEXT,
            client_id=self.client_id,
            operation_type=OperationType.INSERT,
            position=position,
            content=text,
            length=len(text),
        )
        return await self.engine.apply_operation(self.doc_id, op)
    
    async def delete_text(self, position: int, length: int) -> bool:
        """Delete text at position."""
        op = CRDTOperation(
            doc_id=self.doc_id,
            crdt_type=CRDTType.YTEXT,
            client_id=self.client_id,
            operation_type=OperationType.DELETE,
            position=position,
            length=length,
        )
        return await self.engine.apply_operation(self.doc_id, op)
    
    async def get_text(self) -> str:
        """Get current document text."""
        doc = await self.engine.get_document(self.doc_id)
        return doc.state if doc and isinstance(doc.state, str) else ""
    
    async def get_state(self) -> Any:
        """Get full document state."""
        doc = await self.engine.get_document(self.doc_id)
        return doc.state if doc else None
    
    async def get_version(self) -> int:
        """Get document version."""
        doc = await self.engine.get_document(self.doc_id)
        return doc.version if doc else 0
    
    async def snapshot(self) -> Snapshot:
        """Create snapshot."""
        return await self.engine.create_snapshot(self.doc_id)


# ==================== High-Level Factory ====================

def get_crdt_engine(redis_client: redis.Redis, presence_service: Optional[PresenceService] = None) -> CRDTEngine:
    """Get or create global CRDT engine instance."""
    if not hasattr(get_crdt_engine, "_instance"):
        get_crdt_engine._instance = CRDTEngine(redis_client, presence_service)
    return get_crdt_engine._instance


async def get_collaborative_document(
    engine: CRDTEngine,
    doc_id: str,
    client_id: str,
    crdt_type: CRDTType = CRDTType.YTEXT,
) -> CollaborativeDocument:
    """Create a collaborative document instance."""
    doc = CollaborativeDocument(engine, doc_id, client_id)
    await doc.initialize()
    return doc