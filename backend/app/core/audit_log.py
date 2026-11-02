from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import hashlib
import json
import asyncio
import threading
from collections import deque
from contextvars import ContextVar
import uuid


class EventType(str, Enum):
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PERMISSION_CHANGE = "permission_change"
    ROLE_ASSIGN = "role_assign"
    ROLE_REMOVE = "role_remove"
    POLICY_CREATE = "policy_create"
    POLICY_UPDATE = "policy_update"
    POLICY_DELETE = "policy_delete"
    DATA_EXPORT = "data_export"
    DATA_IMPORT = "data_import"
    CONFIG_CHANGE = "config_change"
    SECURITY_EVENT = "security_event"
    API_CALL = "api_call"
    WEBHOOK_RECEIVED = "webhook_received"
    WORKFLOW_START = "workflow_start"
    WORKFLOW_COMPLETE = "workflow_complete"
    WORKFLOW_FAILED = "workflow_failed"


class Severity(str, Enum):
    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    event_type: EventType = EventType.API_CALL
    severity: Severity = Severity.INFO
    actor_id: Optional[str] = None
    actor_type: str = "user"
    actor_ip: Optional[str] = None
    actor_user_agent: Optional[str] = None
    organization_id: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    action: Optional[str] = None
    outcome: str = "success"
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    previous_hash: Optional[str] = None
    hash: Optional[str] = None
    merkle_proof: Optional[List[str]] = None
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "actor_ip": self.actor_ip,
            "actor_user_agent": self.actor_user_agent,
            "organization_id": self.organization_id,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "action": self.action,
            "outcome": self.outcome,
            "error_message": self.error_message,
            "metadata": self.metadata,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
            "merkle_proof": self.merkle_proof,
        }
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)


class MerkleNode:
    def __init__(self, data: bytes, left: Optional['MerkleNode'] = None, right: Optional['MerkleNode'] = None):
        self.data = data
        self.left = left
        self.right = right
        self.hash = hashlib.sha256(data).hexdigest()
    
    def __repr__(self):
        return f"MerkleNode({self.hash[:16]}...)"


class MerkleTree:
    def __init__(self, leaves: List[bytes] = None):
        self.leaves: List[MerkleNode] = []
        self.root: Optional[MerkleNode] = None
        if leaves:
            self.build(leaves)
    
    def build(self, leaves: List[bytes]):
        self.leaves = [MerkleNode(leaf) for leaf in leaves]
        self.root = self._build_tree(self.leaves)
    
    def _build_tree(self, nodes: List[MerkleNode]) -> MerkleNode:
        if len(nodes) == 1:
            return nodes[0]
        
        next_level = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else left
            combined = left.hash + right.hash
            parent = MerkleNode(
                hashlib.sha256(combined.encode()).digest(),
                left=left,
                right=right
            )
            next_level.append(parent)
        
        return self._build_tree(next_level)
    
    def get_root_hash(self) -> Optional[str]:
        return self.root.hash if self.root else None
    
    def get_proof(self, leaf_index: int) -> List[str]:
        if leaf_index >= len(self.leaves):
            return []
        
        proof = []
        index = leaf_index
        level = self.leaves
        
        while len(level) > 1:
            next_level = []
            for i in range(0, len(level), 2):
                left = level[i]
                right = level[i + 1] if i + 1 < len(level) else left
                next_level.append(MerkleNode(
                    hashlib.sha256((left.hash + right.hash).encode()).digest(),
                    left=left,
                    right=right
                ))
                
                if i == index or i + 1 == index:
                    sibling = right if i == index else left
                    proof.append(sibling.hash)
            
            level = next_level
            index = index // 2
        
        return proof
    
    def verify_proof(self, leaf_hash: str, proof: List[str], root_hash: str) -> bool:
        current_hash = leaf_hash
        for sibling_hash in proof:
            if current_hash < sibling_hash:
                current_hash = hashlib.sha256((current_hash + sibling_hash).encode()).hexdigest()
            else:
                current_hash = hashlib.sha256((sibling_hash + current_hash).encode()).hexdigest()
        return current_hash == root_hash


class AuditLog:
    def __init__(self, max_buffer_size: int = 10000):
        self.events: deque = deque(maxlen=max_buffer_size)
        self.merkle_tree: MerkleTree = MerkleTree()
        self.leaf_hashes: List[str] = []
        self.root_hashes: List[str] = []
        self.lock = threading.Lock()
        self._last_hash: Optional[str] = None
    
    def append(self, event: AuditEvent) -> str:
        with self.lock:
            if self._last_hash:
                event.previous_hash = self._last_hash
            
            event_data = event.to_json().encode()
            event_hash = hashlib.sha256(event_data).hexdigest()
            event.hash = event_hash
            
            self.leaf_hashes.append(event_hash)
            self.merkle_tree = MerkleTree(self.leaf_hashes)
            root_hash = self.merkle_tree.get_root_hash()
            self.root_hashes.append(root_hash)
            
            if root_hash:
                event.merkle_proof = self.merkle_tree.get_proof(len(self.leaf_hashes) - 1)
            
            self.events.append(event)
            self._last_hash = event_hash
            
            return event.id
    
    def get_event(self, event_id: str) -> Optional[AuditEvent]:
        for event in self.events:
            if event.id == event_id:
                return event
        return None
    
    def get_events(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        event_type: Optional[EventType] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        severity: Optional[Severity] = None,
        outcome: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[AuditEvent]:
        filtered = []
        for event in self.events:
            if start_time and event.timestamp < start_time:
                continue
            if end_time and event.timestamp > end_time:
                continue
            if event_type and event.event_type != event_type:
                continue
            if actor_id and event.actor_id != actor_id:
                continue
            if resource_type and event.resource_type != resource_type:
                continue
            if resource_id and event.resource_id != resource_id:
                continue
            if severity and event.severity != severity:
                continue
            if outcome and event.outcome != outcome:
                continue
            filtered.append(event)
        
        filtered.sort(key=lambda e: e.timestamp, reverse=True)
        return filtered[offset:offset + limit]
    
    def get_merkle_proof(self, event_id: str) -> Optional[Dict]:
        event = self.get_event(event_id)
        if not event:
            return None
        
        index = self.leaf_hashes.index(event.hash) if event.hash in self.leaf_hashes else -1
        if index < 0:
            return None
        
        proof = self.merkle_tree.get_proof(index)
        root_hash = self.merkle_tree.get_root_hash()
        
        return {
            "event_id": event_id,
            "leaf_hash": event.hash,
            "proof": proof,
            "root_hash": root_hash,
            "index": index,
        }
    
    def verify_event(self, event_id: str) -> bool:
        proof_data = self.get_merkle_proof(event_id)
        if not proof_data:
            return False
        
        return self.merkle_tree.verify_proof(
            proof_data["leaf_hash"],
            proof_data["proof"],
            proof_data["root_hash"]
        )
    
    def verify_chain(self, start_index: int = 0, end_index: Optional[int] = None) -> bool:
        if end_index is None:
            end_index = len(self.leaf_hashes)
        
        for i in range(start_index, end_index):
            if i >= len(self.leaf_hashes):
                break
            
            if i > 0:
                event = self.events[i]
                if event.previous_hash != self.leaf_hashes[i - 1]:
                    return False
        
        return True
    
    def get_root_hash_at(self, index: int) -> Optional[str]:
        if 0 <= index < len(self.root_hashes):
            return self.root_hashes[index]
        return None
    
    def get_current_root_hash(self) -> Optional[str]:
        return self.root_hashes[-1] if self.root_hashes else None
    
    def get_stats(self) -> Dict:
        return {
            "total_events": len(self.events),
            "buffer_size": self.events.maxlen,
            "leaf_count": len(self.leaf_hashes),
            "current_root_hash": self.get_current_root_hash(),
            "first_event_time": self.events[0].timestamp.isoformat() if self.events else None,
            "last_event_time": self.events[-1].timestamp.isoformat() if self.events else None,
        }


class AsyncAuditLog(AuditLog):
    def __init__(self, max_buffer_size: int = 10000, flush_interval: float = 1.0):
        super().__init__(max_buffer_size)
        self.flush_interval = flush_interval
        self.pending: deque = deque()
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(self):
        self._running = True
        self._flush_task = asyncio.create_task(self._periodic_flush())
    
    async def stop(self):
        self._running = False
        if self._flush_task:
            await self._flush_task
        await self._flush()
    
    async def log(self, event: AuditEvent) -> str:
        self.pending.append(event)
        return event.id
    
    async def _flush(self):
        while self.pending:
            event = self.pending.popleft()
            self.append(event)
    
    async def _periodic_flush(self):
        while self._running:
            await asyncio.sleep(self.flush_interval)
            await self._flush()


class AuditLogManager:
    def __init__(self):
        self.audit_log = AsyncAuditLog()
        self.correlation_context: ContextVar[Optional[str]] = ContextVar('correlation_id', default=None)
        self.causation_context: ContextVar[Optional[str]] = ContextVar('causation_id', default=None)
    
    async def start(self):
        await self.audit_log.start()
    
    async def stop(self):
        await self.audit_log.stop()
    
    def set_correlation_id(self, correlation_id: str):
        self.correlation_context.set(correlation_id)
    
    def set_causation_id(self, causation_id: str):
        self.causation_context.set(causation_id)
    
    async def log(
        self,
        event_type: EventType,
        actor_id: Optional[str] = None,
        actor_type: str = "user",
        actor_ip: Optional[str] = None,
        actor_user_agent: Optional[str] = None,
        organization_id: Optional[str] = None,
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        action: Optional[str] = None,
        outcome: str = "success",
        error_message: Optional[str] = None,
        metadata: Dict[str, Any] = None,
        severity: Severity = Severity.INFO,
    ) -> str:
        event = AuditEvent(
            event_type=event_type,
            severity=severity,
            actor_id=actor_id,
            actor_type=actor_type,
            actor_ip=actor_ip,
            actor_user_agent=actor_user_agent,
            organization_id=organization_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            outcome=outcome,
            error_message=error_message,
            metadata=metadata or {},
            correlation_id=self.correlation_context.get(),
            causation_id=self.causation_context.get(),
        )
        
        return await self.audit_log.log(event)
    
    async def log_api_call(
        self,
        method: str,
        path: str,
        status_code: int,
        actor_id: Optional[str] = None,
        actor_ip: Optional[str] = None,
        actor_user_agent: Optional[str] = None,
        organization_id: Optional[str] = None,
        duration_ms: Optional[int] = None,
        request_size: Optional[int] = None,
        response_size: Optional[int] = None,
    ) -> str:
        return await self.log(
            event_type=EventType.API_CALL,
            actor_id=actor_id,
            actor_ip=actor_ip,
            actor_user_agent=actor_user_agent,
            organization_id=organization_id,
            action=f"{method} {path}",
            outcome="success" if 200 <= status_code < 400 else "failure",
            severity=Severity.INFO if 200 <= status_code < 400 else Severity.WARNING,
            metadata={
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": duration_ms,
                "request_size": request_size,
                "response_size": response_size,
            }
        )
    
    async def log_security_event(
        self,
        event_type: EventType,
        actor_id: Optional[str] = None,
        actor_ip: Optional[str] = None,
        organization_id: Optional[str] = None,
        details: Dict[str, Any] = None,
    ) -> str:
        return await self.log(
            event_type=event_type,
            actor_id=actor_id,
            actor_ip=actor_ip,
            organization_id=organization_id,
            severity=Severity.CRITICAL,
            outcome="failure",
            metadata=details or {},
        )


audit_log_manager = AuditLogManager()


async def get_audit_log_manager() -> AuditLogManager:
    return audit_log_manager


async def log_audit_event(
    event_type: EventType,
    actor_id: Optional[str] = None,
    actor_type: str = "user",
    actor_ip: Optional[str] = None,
    actor_user_agent: Optional[str] = None,
    organization_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    resource_id: Optional[str] = None,
    action: Optional[str] = None,
    outcome: str = "success",
    error_message: Optional[str] = None,
    metadata: Dict[str, Any] = None,
    severity: Severity = Severity.INFO,
) -> str:
    return await audit_log_manager.log(
        event_type=event_type,
        actor_id=actor_id,
        actor_type=actor_type,
        actor_ip=actor_ip,
        actor_user_agent=actor_user_agent,
        organization_id=organization_id,
        resource_type=resource_type,
        resource_id=resource_id,
        action=action,
        outcome=outcome,
        error_message=error_message,
        metadata=metadata,
        severity=severity,
    )