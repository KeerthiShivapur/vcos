"""Yjs CRDT WebSocket Server for Real-time Collaborative Editing.

Provides WebSocket endpoints for Yjs awareness, document synchronization,
cursor positions, and selection ranges.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.organization import Organization
from app.models.user import User
from app.services.permission_service import permission_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/yjs", tags=["Yjs CRDT"])


async def get_current_organization(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get current organization from user."""
    org = await db.get(Organization, user.organization_id)
    if org is None or org.status != "active":
        raise HTTPException(status_code=403, detail="Organization is not active")
    return org


class RequirePermission:
    """Dependency to require a specific permission."""
    
    def __init__(self, permission: str):
        self.permission = permission
    
    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
    ) -> User:
        codes = await permission_service.user_permission_codes(db, user.id, user.organization_id)
        if self.permission not in codes:
            raise HTTPException(
                status_code=403,
                detail=f"Missing permission: {self.permission}",
            )
        return user


def require_permission(permission: str) -> RequirePermission:
    return RequirePermission(permission)


@dataclass
class YjsConnection:
    """A Yjs WebSocket connection with awareness state."""
    ws: WebSocket
    document_id: str
    client_id: int
    user_id: str
    user_name: str
    awareness_state: dict = field(default_factory=dict)
    connected_at: float = field(default_factory=time.time)


@dataclass
class YjsDocument:
    """Yjs document state with connected clients."""
    document_id: str
    binary_state: bytes = b""
    clients: dict[int, YjsConnection] = field(default_factory=dict)
    awareness_states: dict[int, dict] = field(default_factory=dict)
    version: int = 0
    updated_at: float = field(default_factory=time.time)


# In-memory document store (replace with Redis for multi-instance)
_documents: dict[str, YjsDocument] = {}


def get_document(document_id: str) -> YjsDocument:
    """Get or create a Yjs document."""
    if document_id not in _documents:
        _documents[document_id] = YjsDocument(document_id=document_id)
    return _documents[document_id]


def remove_document(document_id: str):
    """Remove a document if no clients connected."""
    if document_id in _documents and not _documents[document_id].clients:
        del _documents[document_id]


async def broadcast_awareness(doc: YjsDocument, exclude_client: Optional[int] = None):
    """Broadcast awareness states to all connected clients."""
    awareness_data = {
        "type": "awareness",
        "states": {
            client_id: state 
            for client_id, state in doc.awareness_states.items() 
            if client_id != exclude_client
        },
    }
    
    message = json.dumps(awareness_data)
    
    for client_id, conn in doc.clients.items():
        if client_id == exclude_client:
            continue
        try:
            await conn.ws.send_text(message)
        except Exception:
            pass


async def broadcast_sync(doc: YjsDocument, message: str, exclude_client: Optional[int] = None):
    """Broadcast sync message to all clients except sender."""
    for client_id, conn in doc.clients.items():
        if client_id == exclude_client:
            continue
        try:
            await conn.ws.send_text(message)
        except Exception:
            pass


async def get_current_organization_ws(
    token: str = Query(...),
    organization_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Optional[Organization]:
    """Get current organization for WebSocket connections."""
    from app.api.deps import get_current_user_ws
    user = await get_current_user_ws(token, organization_id, db)
    if not user:
        return None
    
    from sqlalchemy import select
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    org = result.scalar_one_or_none()
    
    if org and org.is_active:
        return org
    
    return None


@router.websocket("/ws/{document_id}")
async def yjs_websocket(
    websocket: WebSocket,
    document_id: str,
    token: str = Query(..., description="Auth token"),
    organization_id: str = Query(..., description="Organization ID"),
):
    """Yjs WebSocket endpoint for real-time collaboration."""
    await websocket.accept()
    
    # Validate token and get organization
    org = await get_current_organization_ws(token, organization_id, None)
    if not org:
        await websocket.close(code=4001, reason="Invalid token or organization")
        return
    
    # TODO: Get user from token
    user_id = "user_123"
    user_name = "Test User"
    client_id = int(time.time() * 1000) % 1000000
    
    doc = get_document(document_id)
    conn = YjsConnection(
        ws=websocket,
        document_id=document_id,
        client_id=client_id,
        user_id=user_id,
        user_name=user_name,
    )
    
    doc.clients[client_id] = conn
    
    try:
        # Send sync step 1: current document state
        if doc.binary_state:
            await websocket.send_text(json.dumps({
                "type": "sync",
                "step": 1,
                "state": doc.binary_state.hex(),
            }))
        
        # Send awareness states of other clients
        await broadcast_awareness(doc, exclude_client=client_id)
        
        # Send own client ID
        await websocket.send_text(json.dumps({
            "type": "init",
            "client_id": client_id,
            "document_id": document_id,
        }))
        
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            msg_type = message.get("type")
            
            if msg_type == "sync":
                step = message.get("step")
                if step == 1:
                    # Client requesting sync
                    if doc.binary_state:
                        await websocket.send_text(json.dumps({
                            "type": "sync",
                            "step": 2,
                            "state": doc.binary_state.hex(),
                        }))
                elif step == 2:
                    # Client sending update
                    update_hex = message.get("state", "")
                    if update_hex:
                        update_bytes = bytes.fromhex(update_hex)
                        # Apply update to document state (simplified - in production use ypy)
                        doc.binary_state = update_bytes
                        doc.version += 1
                        doc.update_at = time.time()
                        
                        # Broadcast to other clients
                        await broadcast_sync(doc, data, exclude_client=client_id)
            
            elif msg_type == "awareness":
                # Update awareness state
                state = message.get("state", {})
                state["user"] = {
                    "id": user_id,
                    "name": user_name,
                    "color": f"hsl({client_id % 360}, 70%, 50%)",
                }
                conn.awareness_state = state
                doc.awareness_states[client_id] = state
                
                # Broadcast to others
                await broadcast_awareness(doc, exclude_client=client_id)
            
            elif msg_type == "cursor":
                # Cursor position update (part of awareness)
                cursor = message.get("cursor", {})
                if conn.awareness_state:
                    conn.awareness_state["cursor"] = cursor
                    doc.awareness_states[client_id] = conn.awareness_state
                    await broadcast_awareness(doc, exclude_client=client_id)
            
            elif msg_type == "selection":
                # Selection range update
                selection = message.get("selection", {})
                if conn.awareness_state:
                    conn.awareness_state["selection"] = selection
                    doc.awareness_states[client_id] = conn.awareness_state
                    await broadcast_awareness(doc, exclude_client=client_id)
    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Yjs WebSocket error: {e}")
    finally:
        doc.clients.pop(client_id, None)
        doc.awareness_states.pop(client_id, None)
        await broadcast_awareness(doc, exclude_client=client_id)
        remove_document(document_id)


@router.get("/documents/{document_id}/state")
async def get_document_state(
    document_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("documents:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get current document state for initialization."""
    doc = get_document(document_id)
    return {
        "document_id": document_id,
        "state": doc.binary_state.hex() if doc.binary_state else "",
        "version": doc.version,
        "clients": len(doc.clients),
        "updated_at": doc.updated_at,
    }


@router.post("/documents/{document_id}/state")
async def set_document_state(
    document_id: str,
    state: str,  # hex encoded binary state
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("documents:write")),
    db: AsyncSession = Depends(get_db),
):
    """Set document state (for persistence/restore)."""
    doc = get_document(document_id)
    doc.binary_state = bytes.fromhex(state) if state else b""
    doc.version += 1
    doc.updated_at = time.time()
    return {"success": True, "version": doc.version}


@router.get("/documents/{document_id}/awareness")
async def get_awareness(
    document_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("documents:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get current awareness states."""
    doc = get_document(document_id)
    return {
        "document_id": document_id,
        "states": doc.awareness_states,
    }