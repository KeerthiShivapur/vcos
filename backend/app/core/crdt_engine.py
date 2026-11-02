"""
CRDT Engine for Real-time Collaboration.

Implements Conflict-free Replicated Data Types for concurrent editing
of documents, whiteboards, and collaborative data structures.
Supports Yjs-compatible CRDTs with awareness protocol.
"""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.core.presence_redis import PresenceService

logger = logging.getLogger(__name__)


class CRDTType(str, Enum):
    """Types of CRDTs supported."""
    YTEXT = "ytext"           # Rich text (Yjs Y.Text)
    YARRAY = "yarray"         # Array (Yjs Y.Array)
    YMAP = "ymap"             # Map/Object (Yjs Y.Map)
    YXML = "yxml"             # XML/HTML (Yjs Y.XmlFragment)
    COUNTER = "counter"       # G-Counter / PN-Counter
    AWARENESS = "awareness"   # Presence/awareness


class OperationType(str, Enum):
    """Types of CRDT operations."""
    INSERT = "insert"
    DELETE = "delete"
    UPDATE = "update"
    RETAIN = "retain"


@dataclass
class CRDTOperation:
    """A single CRDT operation."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    crdt_type: CRDTType = CRDTType.YTEXT
    doc_id: str = ""
    client_id: str = ""
    operation_type: OperationType = OperationType.INSERT
    position: int = 0
    content: Any = None
    length: int = 0
    attributes: Dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    vector_clock: Dict[str, int] = field(default_factory=dict)


@dataclass
class CRDTDocument:
    """CRDT Document state."""
    doc_id: str
    crdt_type: CRDTType
    state: Any = None
    version: int = 0
    clients: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    pending_ops: List[CRDTOperation] = field(default_factory=list)
    applied_ops: Set[str] = field(default_factory=set)
    last_modified: float = field(default_factory=time.time)
    last_modified_by: str = ""


@dataclass
class AwarenessState:
    """User awareness/presence state."""
    client_id: str
    user_id: str
    user_name: str
    user_color: str
    cursor: Optional[Dict[str, Any]] = None
    selection: Optional[Dict[str, Any]] = None
    status: str = "online"
    last_active: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class CRDTEngine:
    """
    CRDT Engine for real-time collaboration.
    
    Manages CRDT documents, applies operations, handles conflicts,
    and synchronizes state across clients.
    """
    
    def __init__(self, presence_service: Optional["PresenceService"] = None):
        self.presence_service = presence_service
        self.documents: Dict[str, CRDTDocument] = {}
        self.client_docs: Dict[str, Set[str]] = defaultdict(set)
        self.operation_handlers: Dict[CRDTType, Callable] = {}
        self._register_handlers()
        
    def _register_handlers(self):
        """Register operation handlers for each CRDT type."""
        self.operation_handlers[CRDTType.YTEXT] = self._handle_text_op
        self.operation_handlers[CRDTType.YARRAY] = self._handle_array_op
        self.operation_handlers[CRDTType.YMAP] = self._handle_map_op
        self.operation_handlers[CRDTType.COUNTER] = self._handle_counter_op
        self.operation_handlers[CRDTType.AWARENESS] = self._handle_awareness_op
        
    def create_document(
        self,
        doc_id: str,
        crdt_type: CRDTType = CRDTType.YTEXT,
        initial_state: Any = None,
    ) -> CRDTDocument:
        """Create a new CRDT document."""
        doc = CRDTDocument(
            doc_id=doc_id,
            crdt_type=crdt_type,
            state=initial_state or self._get_initial_state(crdt_type),
        )
        self.documents[doc_id] = doc
        logger.info(f"Created CRDT document: {doc_id} ({crdt_type.value})")
        return doc
        
    def _get_initial_state(self, crdt_type: CRDTType) -> Any:
        """Get initial state for CRDT type."""
        if crdt_type == CRDTType.YTEXT:
            return ""
        elif crdt_type == CRDTType.YARRAY:
            return []
        elif crdt_type == CRDTType.YMAP:
            return {}
        elif crdt_type == CRDTType.COUNTER:
            return 0
        return None
        
    def get_document(self, doc_id: str) -> Optional[CRDTDocument]:
        """Get document by ID."""
        return self.documents.get(doc_id)
        
    def delete_document(self, doc_id: str) -> bool:
        """Delete a document."""
        if doc_id in self.documents:
            # Remove client references
            for client_id, docs in self.client_docs.items():
                docs.discard(doc_id)
            del self.documents[doc_id]
            logger.info(f"Deleted CRDT document: {doc_id}")
            return True
        return False
        
    async def apply_operation(
        self,
        doc_id: str,
        operation: CRDTOperation,
        client_id: str,
    ) -> Dict[str, Any]:
        """
        Apply a CRDT operation to a document.
        
        Returns the updated document state and any conflicts.
        """
        doc = self.documents.get(doc_id)
        if not doc:
            raise ValueError(f"Document not found: {doc_id}")
            
        # Check if operation already applied (idempotency)
        if operation.id in doc.applied_ops:
            return {
                "success": True,
                "state": doc.state,
                "version": doc.version,
                "duplicate": True,
            }
            
        # Apply operation
        handler = self.operation_handlers.get(doc.crdt_type)
        if not handler:
            raise ValueError(f"No handler for CRDT type: {doc.crdt_type}")
            
        try:
            new_state, conflicts = handler(doc, operation)
            doc.state = new_state
            doc.version += 1
            doc.applied_ops.add(operation.id)
            doc.last_modified = time.time()
            doc.last_modified_by = client_id
            
            # Track client-document association
            self.client_docs[client_id].add(doc_id)
            
            # Broadcast to other clients via presence service
            if self.presence_service:
                await self._broadcast_operation(doc_id, operation, client_id)
                
            return {
                "success": True,
                "state": doc.state,
                "version": doc.version,
                "conflicts": conflicts,
            }
        except Exception as e:
            logger.error(f"Failed to apply operation: {e}")
            return {
                "success": False,
                "error": str(e),
            }
            
    def _handle_text_op(self, doc: CRDTDocument, op: CRDTOperation) -> tuple:
        """Handle Y.Text operations (insert/delete)."""
        text = doc.state or ""
        
        if op.operation_type == OperationType.INSERT:
            pos = min(op.position, len(text))
            new_text = text[:pos] + str(op.content) + text[pos:]
        elif op.operation_type == OperationType.DELETE:
            pos = min(op.position, len(text))
            end = min(pos + op.length, len(text))
            new_text = text[:pos] + text[end:]
        else:
            new_text = text
            
        conflicts = []
        # Detect concurrent edits at same position
        # (Simplified - real implementation would use vector clocks)
        
        return new_text, conflicts
        
    def _handle_array_op(self, doc: CRDTDocument, op: CRDTOperation) -> tuple:
        """Handle Y.Array operations."""
        arr = doc.state or []
        
        if op.operation_type == OperationType.INSERT:
            pos = min(op.position, len(arr))
            arr.insert(pos, op.content)
        elif op.operation_type == OperationType.DELETE:
            pos = min(op.position, len(arr))
            end = min(pos + op.length, len(arr))
            del arr[pos:end]
            
        return arr, []
        
    def _handle_map_op(self, doc: CRDTDocument, op: CRDTOperation) -> tuple:
        """Handle Y.Map operations."""
        map_obj = doc.state or {}
        
        if op.operation_type == OperationType.INSERT:
            map_obj[op.content] = op.attributes
        elif op.operation_type == OperationType.DELETE:
            map_obj.pop(op.content, None)
        elif op.operation_type == OperationType.UPDATE:
            if op.content in map_obj:
                map_obj[op.content].update(op.attributes)
                
        return map_obj, []
        
    def _handle_counter_op(self, doc: CRDTDocument, op: CRDTOperation) -> tuple:
        """Handle Counter operations."""
        counter = doc.state or 0
        
        if op.operation_type == OperationType.INSERT:  # Increment
            counter += op.content or 1
        elif op.operation_type == OperationType.DELETE:  # Decrement
            counter -= op.content or 1
            
        return counter, []
        
    def _handle_awareness_op(self, doc: CRDTDocument, op: CRDTOperation) -> tuple:
        """Handle Awareness operations."""
        # Awareness state is managed separately
        return doc.state, []
        
    async def _broadcast_operation(
        self,
        doc_id: str,
        operation: CRDTOperation,
        sender_id: str,
    ):
        """Broadcast operation to other clients via presence service."""
        if not self.presence_service:
            return
            
        message = {
            "type": "crdt:operation",
            "payload": {
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
            },
        }
        
        # Broadcast to all clients in the document
        for client_id in self.client_docs:
            if client_id != sender_id and doc_id in self.client_docs.get(client_id, set()):
                # Send via presence service
                pass  # Implementation depends on presence service
                
    def get_client_documents(self, client_id: str) -> Set[str]:
        """Get all documents a client is connected to."""
        return self.client_docs.get(client_id, set())
        
    def register_client(self, client_id: str, doc_id: str):
        """Register client as connected to document."""
        self.client_docs[client_id].add(doc_id)
        if doc_id in self.documents:
            self.documents[doc_id].clients[client_id] = {
                "joined_at": time.time(),
                "cursor": None,
                "selection": None,
            }
            
    def unregister_client(self, client_id: str, doc_id: str):
        """Unregister client from document."""
        if client_id in self.client_docs:
            self.client_docs[client_id].discard(doc_id)
        if doc_id in self.documents:
            self.documents[doc_id].clients.pop(client_id, None)
            
    def update_awareness(
        self,
        doc_id: str,
        client_id: str,
        awareness: AwarenessState,
    ):
        """Update client awareness state."""
        if doc_id not in self.documents:
            return
            
        doc = self.documents[doc_id]
        if client_id in doc.clients:
            doc.clients[client_id].update({
                "cursor": awareness.cursor,
                "selection": awareness.selection,
                "status": awareness.status,
                "last_active": awareness.last_active,
                "user_name": awareness.user_name,
                "user_color": awareness.user_color,
            })
            
    def get_document_state(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Get full document state for sync."""
        doc = self.documents.get(doc_id)
        if not doc:
            return None
            
        return {
            "doc_id": doc.doc_id,
            "crdt_type": doc.crdt_type.value,
            "state": doc.state,
            "version": doc.version,
            "clients": {
                cid: {
                    "cursor": info.get("cursor"),
                    "selection": info.get("selection"),
                    "status": info.get("status", "online"),
                    "user_name": info.get("user_name"),
                    "user_color": info.get("user_color"),
                }
                for cid, info in doc.clients.items()
            },
            "last_modified": doc.last_modified,
            "last_modified_by": doc.last_modified_by,
        }


class CommentThread:
    """Collaborative comment thread with CRDT support."""
    
    def __init__(self, thread_id: str, doc_id: str, anchor: Dict[str, Any]):
        self.thread_id = thread_id
        self.doc_id = doc_id
        self.anchor = anchor  # Position in document
        self.comments: List[Dict[str, Any]] = []
        self.resolved = False
        self.created_at = time.time()
        self.created_by = ""
        self.updated_at = time.time()
        
    def add_comment(
        self,
        comment_id: str,
        author_id: str,
        author_name: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a comment to the thread."""
        comment = {
            "id": comment_id,
            "parent_id": parent_id,
            "author_id": author_id,
            "author_name": author_name,
            "content": content,
            "created_at": time.time(),
            "updated_at": time.time(),
            "resolved": False,
            "reactions": {},
        }
        self.comments.append(comment)
        self.updated_at = time.time()
        return comment
        
    def update_comment(self, comment_id: str, content: str) -> bool:
        """Update a comment."""
        for comment in self.comments:
            if comment["id"] == comment_id:
                comment["content"] = content
                comment["updated_at"] = time.time()
                return True
        return False
        
    def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment."""
        for i, comment in enumerate(self.comments):
            if comment["id"] == comment_id:
                self.comments.pop(i)
                return True
        return False
        
    def resolve(self, resolved_by: str) -> bool:
        """Resolve the thread."""
        self.resolved = True
        self.updated_at = time.time()
        return True


@dataclass
class CommentThread:
    """Comment thread for collaborative documents."""
    thread_id: str
    doc_id: str
    anchor: Dict[str, Any]
    comments: List[Dict[str, Any]] = field(default_factory=list)
    resolved: bool = False
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    created_by: str = ""
    assigned_to: Optional[str] = None
    labels: List[str] = field(default_factory=list)

    def get_document_state(self, thread_id: str) -> Dict[str, Any]:
        return {
            "thread_id": self.thread_id,
            "doc_id": self.doc_id,
            "anchor": self.anchor,
            "comments": self.comments,
            "resolved": self.resolved,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "updated_at": self.updated_at,
        }

    def add_comment(
        self,
        comment_id: str,
        author_id: str,
        author_name: str,
        content: str,
        parent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Add a comment to the thread."""
        comment = {
            "id": comment_id,
            "parent_id": parent_id,
            "author_id": author_id,
            "author_name": author_name,
            "content": content,
            "created_at": time.time(),
            "updated_at": time.time(),
            "resolved": False,
            "reactions": {},
        }
        self.comments.append(comment)
        self.updated_at = time.time()
        return comment

    def update_comment(self, comment_id: str, content: str) -> bool:
        """Update a comment."""
        for comment in self.comments:
            if comment["id"] == comment_id:
                comment["content"] = content
                comment["updated_at"] = time.time()
                return True
        return False

    def delete_comment(self, comment_id: str) -> bool:
        """Delete a comment."""
        for i, comment in enumerate(self.comments):
            if comment["id"] == comment_id:
                self.comments.pop(i)
                return True
        return False

    def resolve(self, resolved_by: str) -> bool:
        """Resolve the thread."""
        self.resolved = True
        self.updated_at = time.time()
        return True


# Global CRDT engine instance
_crdt_engine: Optional[CRDTEngine] = None


def get_crdt_engine(presence_service: Optional["PresenceService"] = None) -> CRDTEngine:
    """Get or create CRDT engine singleton."""
    global _crdt_engine
    if _crdt_engine is None:
        _crdt_engine = CRDTEngine(presence_service)
    return _crdt_engine


def init_crdt_engine(presence_service: Optional["PresenceService"] = None) -> CRDTEngine:
    """Initialize CRDT engine."""
    global _crdt_engine
    _crdt_engine = CRDTEngine(presence_service)
    return _crdt_engine