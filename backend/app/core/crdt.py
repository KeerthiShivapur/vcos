"""Offline-First CRDT Data Layer with Conflict Resolution."""

import asyncio
import json
import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from collections import defaultdict

logger = logging.getLogger(__name__)


class CRDTType(str, Enum):
    """Types of CRDTs supported."""
    LWW_REGISTER = "lww_register"  # Last-Writer-Wins Register
    LWW_MAP = "lww_map"            # Last-Writer-Wins Map
    OR_SET = "or_set"              # Observed-Remove Set
    GC_COUNTER = "gc_counter"      # Grow-only Counter
    PN_COUNTER = "pn_counter"      # Positive-Negative Counter
    RGA = "rga"                    # Replicated Growable Array (for text)


class OperationType(str, Enum):
    """Types of operations."""
    SET = "set"
    DELETE = "delete"
    INCREMENT = "increment"
    DECREMENT = "decrement"
    ADD = "add"
    REMOVE = "remove"
    INSERT = "insert"


@dataclass
class CRDTOperation:
    """A single CRDT operation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    crdt_type: CRDTType = CRDTType.LWW_REGISTER
    crdt_id: str = ""
    operation: OperationType = OperationType.SET
    key: str = ""
    value: Any = None
    timestamp: float = field(default_factory=time.time)
    author_id: str = ""
    version: int = 1
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CRDTState:
    """Current state of a CRDT."""
    crdt_id: str
    crdt_type: CRDTType
    data: Any = None
    version: int = 0
    last_modified: float = field(default_factory=time.time)
    last_modified_by: str = ""
    history: List[CRDTOperation] = field(default_factory=list)


class BaseCRDT(ABC):
    """Base class for all CRDTs."""
    
    def __init__(self, crdt_id: str, crdt_type: CRDTType):
        self.crdt_id = crdt_id
        self.crdt_type = crdt_type
        self.version = 0
        self.last_modified = time.time()
        self.last_modified_by = ""
        self.operations: List[CRDTOperation] = []
    
    @abstractmethod
    def apply(self, operation: CRDTOperation) -> bool:
        """Apply an operation. Returns True if state changed."""
        pass
    
    @abstractmethod
    def merge(self, other: 'BaseCRDT') -> bool:
        """Merge with another CRDT of same type. Returns True if state changed."""
        pass
    
    @abstractmethod
    def get_state(self) -> Any:
        """Get current state for serialization."""
        pass
    
    @abstractmethod
    def load_state(self, state: Any):
        """Load state from serialization."""
        pass
    
    def _can_apply(self, operation: CRDTOperation) -> bool:
        """Check if operation can be applied (version check)."""
        return operation.version >= self.version
    
    def _create_operation(
        self,
        operation: OperationType,
        key: str = "",
        value: Any = None,
        author_id: str = "",
        metadata: Dict[str, Any] = None
    ) -> CRDTOperation:
        """Create a new operation with incremented version."""
        self.version += 1
        return CRDTOperation(
            crdt_type=self.crdt_type,
            crdt_id=self.crdt_id,
            operation=operation,
            key=key,
            value=value,
            author_id=author_id,
            version=self.version,
            metadata=metadata or {},
        )


class LWWRegister(BaseCRDT):
    """Last-Writer-Wins Register CRDT."""
    
    def __init__(self, crdt_id: str, initial_value: Any = None):
        super().__init__(crdt_id, CRDTType.LWW_REGISTER)
        self._value = initial_value
        self._timestamp = 0
        self._author = ""
    
    def apply(self, operation: CRDTOperation) -> bool:
        if not self._can_apply(operation):
            return False
        
        if operation.operation in (OperationType.SET, OperationType.DELETE):
            new_timestamp = operation.timestamp
            if new_timestamp > self._timestamp or (
                new_timestamp == self._timestamp and operation.author_id > self._author
            ):
                if operation.operation == OperationType.SET:
                    self._value = operation.value
                else:
                    self._value = None
                self._timestamp = new_timestamp
                self._author = operation.author_id
                self.version = operation.version
                self.last_modified = operation.timestamp
                self.last_modified_by = operation.author_id
                self.operations.append(operation)
                return True
        return False
    
    def merge(self, other: 'LWWRegister') -> bool:
        if not isinstance(other, LWWRegister):
            return False
        
        if other._timestamp > self._timestamp or (
            other._timestamp == self._timestamp and other._author > self._author
        ):
            self._value = other._value
            self._timestamp = other._timestamp
            self._author = other._author
            self.version = max(self.version, other.version)
            self.last_modified = other.last_modified
            self.last_modified_by = other.last_modified_by
            return True
        return False
    
    def get_state(self) -> Dict[str, Any]:
        return {
            "value": self._value,
            "timestamp": self._timestamp,
            "author": self._author,
            "version": self.version,
        }
    
    def load_state(self, state: Dict[str, Any]):
        self._value = state.get("value")
        self._timestamp = state.get("timestamp", 0)
        self._author = state.get("author", "")
        self.version = state.get("version", 0)
    
    def set(self, value: Any, author_id: str) -> CRDTOperation:
        op = self._create_operation(OperationType.SET, value=value, author_id=author_id)
        self.apply(op)
        return op
    
    def delete(self, author_id: str) -> CRDTOperation:
        op = self._create_operation(OperationType.DELETE, author_id=author_id)
        self.apply(op)
        return op
    
    def get(self) -> Any:
        return self._value


class LWWMap(BaseCRDT):
    """Last-Writer-Wins Map CRDT."""
    
    def __init__(self, crdt_id: str):
        super().__init__(crdt_id, CRDTType.LWW_MAP)
        self._map: Dict[str, Any] = {}
        self._timestamps: Dict[str, float] = {}
        self._authors: Dict[str, str] = {}
    
    def apply(self, operation: CRDTOperation) -> bool:
        if not self._can_apply(operation):
            return False
        
        key = operation.key
        new_timestamp = operation.timestamp
        
        current_timestamp = self._timestamps.get(key, 0)
        
        if new_timestamp > current_timestamp or (
            new_timestamp == current_timestamp and operation.author_id > self._authors.get(key, "")
        ):
            if operation.operation == OperationType.SET:
                self._map[key] = operation.value
            elif operation.operation == OperationType.DELETE:
                self._map.pop(key, None)
            
            self._timestamps[key] = new_timestamp
            self._authors[key] = operation.author_id
            self.version = operation.version
            self.last_modified = operation.timestamp
            self.last_modified_by = operation.author_id
            self.operations.append(operation)
            return True
        return False
    
    def merge(self, other: 'LWWMap') -> bool:
        if not isinstance(other, LWWMap):
            return False
        
        changed = False
        all_keys = set(self._map.keys()) | set(other._map.keys())
        
        for key in all_keys:
            other_ts = other._timestamps.get(key, 0)
            self_ts = self._timestamps.get(key, 0)
            
            if other_ts > self_ts or (other_ts == self_ts and other._authors.get(key, "") > self._authors.get(key, "")):
                if key in other._map:
                    self._map[key] = other._map[key]
                else:
                    self._map.pop(key, None)
                self._timestamps[key] = other_ts
                self._authors[key] = other._authors.get(key, "")
                changed = True
        
        if changed:
            self.version = max(self.version, other.version)
            self.last_modified = other.last_modified
            self.last_modified_by = other.last_modified_by
        
        return changed
    
    def get_state(self) -> Dict[str, Any]:
        return {
            "map": self._map,
            "timestamps": self._timestamps,
            "authors": self._authors,
            "version": self.version,
        }
    
    def load_state(self, state: Dict[str, Any]):
        self._map = state.get("map", {})
        self._timestamps = state.get("timestamps", {})
        self._authors = state.get("authors", {})
        self.version = state.get("version", 0)
    
    def set(self, key: str, value: Any, author_id: str) -> CRDTOperation:
        op = self._create_operation(OperationType.SET, key=key, value=value, author_id=author_id)
        self.apply(op)
        return op
    
    def delete(self, key: str, author_id: str) -> CRDTOperation:
        op = self._create_operation(OperationType.DELETE, key=key, author_id=author_id)
        self.apply(op)
        return op
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._map.get(key, default)
    
    def keys(self) -> List[str]:
        return list(self._map.keys())
    
    def items(self) -> List[tuple]:
        return list(self._map.items())


class ORSet(BaseCRDT):
    """Observed-Remove Set CRDT."""
    
    def __init__(self, crdt_id: str):
        super().__init__(crdt_id, CRDTType.OR_SET)
        self._elements: Dict[str, Set[str]] = {}  # element -> set of tags
        self._removed_tags: Set[str] = set()
        self._tag_counter = 0
    
    def _generate_tag(self, author_id: str) -> str:
        self._tag_counter += 1
        return f"{author_id}:{self._tag_counter}:{time.time()}"
    
    def apply(self, operation: CRDTOperation) -> bool:
        if not self._can_apply(operation):
            return False
        
        element = operation.key
        tag = operation.metadata.get("tag", self._generate_tag(operation.author_id))
        
        if operation.operation == OperationType.ADD:
            if element not in self._elements:
                self._elements[element] = set()
            self._elements[element].add(tag)
            self._removed_tags.discard(tag)
            
        elif operation.operation == OperationType.REMOVE:
            if element in self._elements:
                self._removed_tags.update(self._elements[element])
                del self._elements[element]
        
        self.version = operation.version
        self.last_modified = operation.timestamp
        self.last_modified_by = operation.author_id
        self.operations.append(operation)
        return True
    
    def merge(self, other: 'ORSet') -> bool:
        if not isinstance(other, ORSet):
            return False
        
        changed = False
        
        # Merge elements (union of tags)
        for element, tags in other._elements.items():
            if element not in self._elements:
                self._elements[element] = set()
            new_tags = tags - self._removed_tags
            if new_tags:
                if element not in self._elements:
                    self._elements[element] = set()
                    changed = True
                self._elements[element].update(new_tags)
                changed = True
        
        # Merge removed tags
        new_removed = other._removed_tags - self._removed_tags
        if new_removed:
            self._removed_tags.update(new_removed)
            # Remove elements that are now fully removed
            for element in list(self._elements.keys()):
                if self._elements[element].issubset(self._removed_tags):
                    del self._elements[element]
                    changed = True
        
        if changed:
            self.version = max(self.version, other.version)
            self.last_modified = other.last_modified
            self.last_modified_by = other.last_modified_by
        
        return changed
    
    def get_state(self) -> Dict[str, Any]:
        return {
            "elements": {k: list(v) for k, v in self._elements.items()},
            "removed_tags": list(self._removed_tags),
            "version": self.version,
        }
    
    def load_state(self, state: Dict[str, Any]):
        self._elements = {k: set(v) for k, v in state.get("elements", {}).items()}
        self._removed_tags = set(state.get("removed_tags", []))
        self.version = state.get("version", 0)
    
    def add(self, element: str, author_id: str) -> CRDTOperation:
        tag = f"{author_id}:{self._tag_counter + 1}:{time.time()}"
        self._tag_counter += 1
        op = self._create_operation(
            OperationType.ADD,
            key=element,
            author_id=author_id,
            metadata={"tag": tag}
        )
        self.apply(op)
        return op
    
    def remove(self, element: str, author_id: str) -> CRDTOperation:
        op = self._create_operation(OperationType.REMOVE, key=element, author_id=author_id)
        self.apply(op)
        return op
    
    def contains(self, element: str) -> bool:
        return element in self._elements
    
    def elements(self) -> List[str]:
        return list(self._elements.keys())


class PNCounter(BaseCRDT):
    """Positive-Negative Counter CRDT."""
    
    def __init__(self, crdt_id: str):
        super().__init__(crdt_id, CRDTType.PN_COUNTER)
        self._positive: Dict[str, int] = defaultdict(int)  # author -> count
        self._negative: Dict[str, int] = defaultdict(int)
    
    def apply(self, operation: CRDTOperation) -> bool:
        if not self._can_apply(operation):
            return False
        
        author = operation.author_id
        amount = operation.value if isinstance(operation.value, int) else 1
        
        if operation.operation == OperationType.INCREMENT:
            self._positive[author] += amount
        elif operation.operation == OperationType.DECREMENT:
            self._negative[author] += amount
        
        self.version = operation.version
        self.last_modified = operation.timestamp
        self.last_modified_by = operation.author_id
        self.operations.append(operation)
        return True
    
    def merge(self, other: 'PNCounter') -> bool:
        if not isinstance(other, PNCounter):
            return False
        
        changed = False
        all_authors = set(self._positive.keys()) | set(other._positive.keys()) | \
                      set(self._negative.keys()) | set(other._negative.keys())
        
        for author in all_authors:
            other_pos = other._positive.get(author, 0)
            other_neg = other._negative.get(author, 0)
            
            if other_pos > self._positive.get(author, 0):
                self._positive[author] = other_pos
                changed = True
            if other_neg > self._negative.get(author, 0):
                self._negative[author] = other_neg
                changed = True
        
        if changed:
            self.version = max(self.version, other.version)
            self.last_modified = other.last_modified
            self.last_modified_by = other.last_modified_by
        
        return changed
    
    def get_state(self) -> Dict[str, Any]:
        return {
            "positive": dict(self._positive),
            "negative": dict(self._negative),
            "version": self.version,
        }
    
    def load_state(self, state: Dict[str, Any]):
        self._positive = defaultdict(int, state.get("positive", {}))
        self._negative = defaultdict(int, state.get("negative", {}))
        self.version = state.get("version", 0)
    
    def increment(self, author_id: str, amount: int = 1) -> CRDTOperation:
        op = self._create_operation(OperationType.INCREMENT, value=amount, author_id=author_id)
        self.apply(op)
        return op
    
    def decrement(self, author_id: str, amount: int = 1) -> CRDTOperation:
        op = self._create_operation(OperationType.DECREMENT, value=amount, author_id=author_id)
        self.apply(op)
        return op
    
    def value(self) -> int:
        total_pos = sum(self._positive.values())
        total_neg = sum(self._negative.values())
        return total_pos - total_neg


class CRDTManager:
    """Manages multiple CRDTs and handles persistence/sync."""
    
    def __init__(self, storage_path: str = "./crdt_data"):
        self.storage_path = storage_path
        self.crdts: Dict[str, BaseCRDT] = {}
        self._persistence_tasks: Dict[str, asyncio.Task] = {}
        self._sync_callbacks: List[Callable] = []
    
    def create_crdt(self, crdt_type: CRDTType, crdt_id: str, **kwargs) -> BaseCRDT:
        """Create a new CRDT."""
        if crdt_id in self.crdts:
            raise ValueError(f"CRDT {crdt_id} already exists")
        
        if crdt_type == CRDTType.LWW_REGISTER:
            crdt = LWWRegister(crdt_id, kwargs.get("initial_value"))
        elif crdt_type == CRDTType.LWW_MAP:
            crdt = LWWMap(crdt_id)
        elif crdt_type == CRDTType.OR_SET:
            crdt = ORSet(crdt_id)
        elif crdt_type == CRDTType.PN_COUNTER:
            crdt = PNCounter(crdt_id)
        else:
            raise ValueError(f"Unsupported CRDT type: {crdt_type}")
        
        self.crdts[crdt_id] = crdt
        return crdt
    
    def get_crdt(self, crdt_id: str) -> Optional[BaseCRDT]:
        return self.crdts.get(crdt_id)
    
    def delete_crdt(self, crdt_id: str) -> bool:
        if crdt_id in self.crdts:
            del self.crdts[crdt_id]
            return True
        return False
    
    def list_crdts(self) -> List[Dict[str, Any]]:
        return [
            {
                "crdt_id": crdt.crdt_id,
                "crdt_type": crdt.crdt_type.value,
                "version": crdt.version,
                "last_modified": crdt.last_modified,
            }
            for crdt in self.crdts.values()
        ]
    
    async def persist_all(self):
        """Persist all CRDTs to disk."""
        # In a real implementation, this would save to database/filesystem
        pass
    
    async def load_all(self):
        """Load all CRDTs from disk."""
        # In a real implementation, this would load from database/filesystem
        pass
    
    def register_sync_callback(self, callback: Callable):
        """Register a callback for sync events."""
        self._sync_callbacks.append(callback)
    
    async def _notify_sync(self, crdt_id: str, operation: CRDTOperation):
        for callback in self._sync_callbacks:
            try:
                await callback(crdt_id, operation)
            except Exception as e:
                logger.error(f"Sync callback error: {e}")


# Global CRDT manager instance
_crdt_manager: Optional[CRDTManager] = None


def get_crdt_manager() -> CRDTManager:
    """Get global CRDT manager instance."""
    global _crdt_manager
    if _crdt_manager is None:
        _crdt_manager = CRDTManager()
    return _crdt_manager