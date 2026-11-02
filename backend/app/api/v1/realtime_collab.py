"""
Real-time Collaboration API Routes.

Provides WebSocket endpoints for CRDT-based collaborative editing,
presence, cursors, comments, and WebRTC signaling.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.core.crdt_engine import (
    CRDTEngine,
    CRDTDocument,
    CRDTOperation,
    CRDTType,
    OperationType,
    AwarenessState,
    CommentThread,
    get_crdt_engine,
)
from app.core.signaling import (
    SignalingServer,
    SignalingMessage,
    SignalingMessageType,
    CallType,
    CallState,
    get_signaling_server,
)
from app.core.presence_redis import PresenceService, get_presence_service
from app.models.organization import Organization
from app.models.user import User
from app.services.permission_service import permission_service

router = APIRouter(tags=["Real-time Collaboration"])

logger = logging.getLogger(__name__)


# ==================== CRDT Models ====================

class CreateDocumentRequest(BaseModel):
    doc_id: str
    crdt_type: str = "ytext"
    initial_state: Optional[Any] = None


class DocumentStateResponse(BaseModel):
    doc_id: str
    crdt_type: str
    state: Any
    version: int
    clients: Dict[str, Any]
    last_modified: float
    last_modified_by: str


class OperationRequest(BaseModel):
    operation: Dict[str, Any]


class AwarenessUpdateRequest(BaseModel):
    status: Optional[str] = None
    cursor: Optional[Dict[str, Any]] = None
    selection: Optional[Dict[str, Any]] = None


class CommentCreateRequest(BaseModel):
    thread_id: str
    content: str
    parent_id: Optional[str] = None


class CommentThreadResponse(BaseModel):
    thread_id: str
    doc_id: str
    anchor: Dict[str, Any]
    comments: List[Dict[str, Any]]
    resolved: bool
    created_at: float
    created_by: str
    updated_at: float


# ==================== CRDT Document Endpoints ====================

@router.post("/crdt/documents", response_model=DocumentStateResponse)
async def create_crdt_document(
    request: CreateDocumentRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new CRDT document for collaborative editing."""
    crdt_engine = get_crdt_engine()
    
    try:
        crdt_type = CRDTType(request.crdt_type)
    except ValueError:
        raise HTTPException(400, f"Invalid CRDT type: {request.crdt_type}")
    
    doc = crdt_engine.create_document(
        doc_id=request.doc_id,
        crdt_type=crdt_type,
        initial_state=request.initial_state,
    )
    
    crdt_engine.register_client(user.id, request.doc_id)
    
    return DocumentStateResponse(**doc.get_document_state(request.doc_id))


@router.get("/crdt/documents/{doc_id}", response_model=DocumentStateResponse)
async def get_crdt_document(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get CRDT document state."""
    crdt_engine = get_crdt_engine()
    doc_state = crdt_engine.get_document_state(doc_id)
    
    if not doc_state:
        raise HTTPException(404, "Document not found")
    
    return DocumentStateResponse(**doc_state)


@router.post("/crdt/documents/{doc_id}/operations")
async def apply_crdt_operation(
    doc_id: str,
    request: OperationRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Apply a CRDT operation to a document."""
    crdt_engine = get_crdt_engine()
    
    try:
        operation = CRDTOperation(**request.operation)
    except Exception as e:
        raise HTTPException(400, f"Invalid operation: {e}")
    
    result = await crdt_engine.apply_operation(doc_id, operation, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Operation failed"))
    
    return result


@router.post("/crdt/documents/{doc_id}/awareness")
async def update_awareness(
    doc_id: str,
    request: AwarenessUpdateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update user awareness (cursor, selection, status)."""
    crdt_engine = get_crdt_engine()
    
    awareness = AwarenessState(
        client_id=user.id,
        user_id=user.id,
        user_name=user.full_name or user.email,
        user_color=user.avatar_color or "#6366f1",
        cursor=request.cursor,
        selection=request.selection,
        status=request.status or "online",
    )
    
    crdt_engine.update_awareness(doc_id, user.id, awareness)
    
    return {"success": True}


@router.delete("/crdt/documents/{doc_id}")
async def delete_crdt_document(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a CRDT document."""
    crdt_engine = get_crdt_engine()
    
    if crdt_engine.delete_document(doc_id):
        return {"success": True}
    
    raise HTTPException(404, "Document not found")


# ==================== Comment Threads ====================

@router.post("/crdt/documents/{doc_id}/comments", response_model=CommentThreadResponse)
async def create_comment_thread(
    doc_id: str,
    anchor: Dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new comment thread on a document."""
    crdt_engine = get_crdt_engine()
    
    thread_id = str(uuid.uuid4())
    thread = CommentThread(thread_id, doc_id, anchor)
    thread.created_by = user.id
    
    return CommentThreadResponse(
        thread_id=thread.thread_id,
        doc_id=thread.doc_id,
        anchor=thread.anchor,
        comments=thread.comments,
        resolved=thread.resolved,
        created_at=thread.created_at,
        created_by=thread.created_by,
        updated_at=thread.updated_at,
    )


@router.get("/crdt/documents/{doc_id}/comments", response_model=List[CommentThreadResponse])
async def get_comment_threads(
    doc_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get all comment threads for a document."""
    # In production, fetch from database
    return []


@router.post("/crdt/comments/{thread_id}/comments")
async def add_comment(
    thread_id: str,
    request: CommentCreateRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a comment to a thread."""
    # In production, fetch thread from database
    comment_id = str(uuid.uuid4())
    comment = {
        "id": comment_id,
        "parent_id": request.parent_id,
        "author_id": user.id,
        "author_name": user.full_name or user.email,
        "content": request.content,
        "created_at": time.time(),
        "updated_at": time.time(),
        "resolved": False,
        "reactions": {},
    }
    
    return comment


# ==================== WebSocket Endpoints ====================

@router.websocket("/ws/crdt/{doc_id}")
async def crdt_websocket(
    websocket: WebSocket,
    doc_id: str,
    token: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """WebSocket for CRDT document collaboration."""
    await websocket.accept()
    
    crdt_engine = get_crdt_engine()
    presence_service = get_presence_service()
    
    # Register client
    crdt_engine.register_client(user.id, doc_id)
    presence = PresenceService()
    presence.update_awareness(
        user_id=user.id,
        organization_id=user.organization_id,
        user_name=user.full_name or user.email,
        user_color=user.avatar_color or "#6366f1",
        status="online",
    )
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "operation":
                operation = CRDTOperation(**message.get("operation", {}))
                result = await crdt_engine.apply_operation(doc_id, operation, user.id)
                await websocket.send_json({
                    "type": "operation_result",
                    "result": result,
                    "request_id": message.get("request_id"),
                })
                
            elif message.get("type") == "awareness":
                awareness = AwarenessState(
                    client_id=user.id,
                    user_id=user.id,
                    user_name=user.full_name or user.email,
                    user_color=user.avatar_color or "#6366f1",
                    cursor=message.get("cursor"),
                    selection=message.get("selection"),
                    status=message.get("status", "online"),
                )
                crdt_engine.update_awareness(doc_id, user.id, awareness)
                
                # Broadcast to others
                if presence_service:
                    await presence_service.broadcast_to_document(doc_id, {
                        "type": "awareness:update",
                        "payload": {
                            "user_id": user.id,
                            "user_name": user.full_name or user.email,
                            "user_color": user.avatar_color or "#6366f1",
                            "cursor": awareness.cursor,
                            "selection": awareness.selection,
                            "status": awareness.status,
                        },
                    }, exclude=user.id)
                
            elif message.get("type") == "sync":
                # Full document sync
                doc_state = crdt_engine.get_document_state(doc_id)
                if doc_state:
                    await websocket.send_json({
                        "type": "sync",
                        "payload": doc_state,
                    })
                    
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        crdt_engine.unregister_client(user.id, doc_id)
        presence = PresenceService()
        presence.update_awareness(
            user_id=user.id,
            organization_id=user.organization_id,
            user_name=user.full_name or user.email,
            user_color=user.avatar_color or "#6366f1",
            status="offline",
        )


# ==================== WebRTC Signaling ====================

class CallInitRequest(BaseModel):
    call_type: str = "video"
    target_users: List[str] = []
    settings: Dict[str, Any] = {}
    user_name: Optional[str] = None
    user_color: Optional[str] = None


class CallActionRequest(BaseModel):
    call_id: str
    media_state: Optional[Dict[str, bool]] = None
    user_name: Optional[str] = None
    user_color: Optional[str] = None


class SignalingMessageModel(BaseModel):
    type: str
    call_id: str
    from_user: str
    to_user: Optional[str] = None
    payload: Dict[str, Any] = {}


@router.post("/calls", response_model=Dict[str, Any])
async def initiate_call(
    request: CallInitRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Initiate a new call."""
    signaling_server = get_signaling_server()
    
    try:
        call_type = CallType(request.call_type)
    except ValueError:
        raise HTTPException(400, f"Invalid call type: {request.call_type}")
    
    message = SignalingMessage(
        type=SignalingMessageType.CALL_INIT,
        call_id="",  # Will be generated
        from_user=user.id,
        payload={
            "call_type": request.call_type,
            "target_users": request.target_users,
            "settings": request.settings,
            "user_name": request.user_name or user.full_name or user.email,
            "user_color": request.user_color or user.avatar_color or "#6366f1",
        },
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to initiate call"))
    
    return result


@router.post("/calls/{call_id}/accept")
async def accept_call(
    call_id: str,
    request: CallActionRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Accept an incoming call."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.CALL_ACCEPT,
        call_id=call_id,
        from_user=user.id,
        payload={
            "media_state": request.media_state or {
                "audio": True,
                "video": True,
                "screen_share": False,
            },
            "user_name": request.user_name or user.full_name or user.email,
            "user_color": request.user_color or user.avatar_color or "#6366f1",
        },
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to accept call"))
    
    return result


@router.post("/calls/{call_id}/reject")
async def reject_call(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Reject an incoming call."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.CALL_REJECT,
        call_id=call_id,
        from_user=user.id,
        payload={},
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to reject call"))
    
    return result


@router.post("/calls/{call_id}/end")
async def end_call(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """End a call."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.CALL_END,
        call_id=call_id,
        from_user=user.id,
        payload={},
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to end call"))
    
    return result


@router.post("/calls/{call_id}/hold")
async def hold_call(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Put call on hold."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.CALL_HOLD,
        call_id=call_id,
        from_user=user.id,
        payload={},
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to hold call"))
    
    return result


@router.post("/calls/{call_id}/resume")
async def resume_call(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Resume a held call."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.CALL_RESUME,
        call_id=call_id,
        from_user=user.id,
        payload={},
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to resume call"))
    
    return result


@router.post("/calls/{call_id}/mute")
async def mute_call(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mute local audio."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.MUTE,
        call_id=call_id,
        from_user=user.id,
        payload={},
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to mute"))
    
    return result


@router.post("/calls/{call_id}/unmute")
async def unmute_call(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Unmute local audio."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.UNMUTE,
        call_id=call_id,
        from_user=user.id,
        payload={},
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to unmute"))
    
    return result


@router.post("/calls/{call_id}/screen-share/start")
async def start_screen_share(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start screen sharing."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.SCREEN_SHARE_START,
        call_id=call_id,
        from_user=user.id,
        payload={
            "user_name": user.full_name or user.email,
        },
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to start screen share"))
    
    return result


@router.post("/calls/{call_id}/screen-share/stop")
async def stop_screen_share(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop screen sharing."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.SCREEN_SHARE_STOP,
        call_id=call_id,
        from_user=user.id,
        payload={},
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to stop screen share"))
    
    return result


@router.post("/calls/{call_id}/recording/start")
async def start_recording(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Start call recording."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.RECORDING_START,
        call_id=call_id,
        from_user=user.id,
        payload={},
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to start recording"))
    
    return result


@router.post("/calls/{call_id}/recording/stop")
async def stop_recording(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Stop call recording."""
    signaling_server = get_signaling_server()
    
    message = SignalingMessage(
        type=SignalingMessageType.RECORDING_STOP,
        call_id=call_id,
        from_user=user.id,
        payload={},
    )
    
    result = await signaling_server.handle_message(message, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to stop recording"))
    
    return result


@router.post("/calls/{call_id}/signal")
async def send_signaling_message(
    call_id: str,
    message: SignalingMessageModel,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Send WebRTC signaling message (offer, answer, ICE candidate)."""
    signaling_server = get_signaling_server()
    
    try:
        msg_type = SignalingMessageType(message.type)
    except ValueError:
        raise HTTPException(400, f"Invalid message type: {message.type}")
    
    message_obj = SignalingMessage(
        type=msg_type,
        call_id=call_id,
        from_user=user.id,
        to_user=message.to_user,
        payload=message.payload,
    )
    
    result = await signaling_server.handle_message(message_obj, user.id)
    
    if not result.get("success"):
        raise HTTPException(400, result.get("error", "Failed to send signal"))
    
    return result


@router.get("/calls/{call_id}", response_model=Dict[str, Any])
async def get_call_state(
    call_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get call state."""
    signaling_server = get_signaling_server()
    call_state = signaling_server.get_call_state(call_id)
    
    if not call_state:
        raise HTTPException(404, "Call not found")
    
    return call_state


@router.get("/calls", response_model=List[Dict[str, Any]])
async def list_user_calls(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List active calls for current user."""
    signaling_server = get_signaling_server()
    call_ids = signaling_server.get_user_calls(user.id)
    
    calls = []
    for call_id in call_ids:
        call_state = signaling_server.get_call_state(call_id)
        if call_state:
            calls.append(call_state)
    
    return calls


@router.websocket("/ws/signaling/{call_id}")
async def signaling_websocket(
    websocket: WebSocket,
    call_id: str,
    token: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """WebSocket for WebRTC signaling."""
    await websocket.accept()
    
    signaling_server = get_signaling_server()
    presence_service = get_presence_service()
    
    # Join call
    message = SignalingMessage(
        type=SignalingMessageType.JOIN,
        call_id=call_id,
        from_user=user.id,
        payload={
            "user_name": user.full_name or user.email,
            "user_color": user.avatar_color or "#6366f1",
        },
    )
    
    join_result = await signaling_server.handle_message(message, user.id)
    
    if not join_result.get("success"):
        await websocket.close(code=4000, reason=join_result.get("error", "Failed to join"))
        return
    
    # Send join result
    await websocket.send_json({
        "type": "join_result",
        "payload": join_result,
    })
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            try:
                msg_type = SignalingMessageType(message.get("type"))
            except ValueError:
                await websocket.send_json({
                    "type": "error",
                    "error": f"Invalid message type: {message.get('type')}",
                })
                continue
            
            message_obj = SignalingMessage(
                type=msg_type,
                call_id=call_id,
                from_user=user.id,
                to_user=message.get("to_user"),
                payload=message.get("payload", {}),
            )
            
            result = await signaling_server.handle_message(message_obj, user.id)
            
            if result.get("success"):
                await websocket.send_json({
                    "type": "signal_result",
                    "result": result,
                    "request_id": message.get("request_id"),
                })
            else:
                await websocket.send_json({
                    "type": "error",
                    "error": result.get("error", "Operation failed"),
                    "request_id": message.get("request_id"),
                })
                
    except WebSocketDisconnect:
        # Handle leave
        leave_message = SignalingMessage(
            type=SignalingMessageType.LEAVE,
            call_id=call_id,
            from_user=user.id,
            payload={},
        )
        await signaling_server.handle_message(leave_message, user.id)
    except Exception as e:
        logger.error(f"Signaling WebSocket error: {e}")
    finally:
        # Cleanup
        pass


# ==================== Presence WebSocket ====================

@router.websocket("/ws/presence/{organization_id}")
async def presence_websocket(
    websocket: WebSocket,
    organization_id: str,
    token: str = Query(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """WebSocket for real-time presence updates."""
    await websocket.accept()
    
    presence_service = get_presence_service()
    
    # Register presence
    presence_service.update_awareness(
        user_id=user.id,
        organization_id=organization_id,
        user_name=user.full_name or user.email,
        user_color=user.avatar_color or "#6366f1",
        status="online",
    )
    
    # Subscribe to presence updates
    async def send_presence_updates():
        # In production, subscribe to Redis pub/sub
        pass
    
    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)
            
            if message.get("type") == "awareness":
                presence_service.update_awareness(
                    user_id=user.id,
                    organization_id=organization_id,
                    user_name=user.full_name or user.email,
                    user_color=user.avatar_color or "#6366f1",
                    cursor=message.get("cursor"),
                    selection=message.get("selection"),
                    status=message.get("status", "online"),
                )
                
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"Presence WebSocket error: {e}")
    finally:
        presence_service.update_awareness(
            user_id=user.id,
            organization_id=organization_id,
            user_name=user.full_name or user.email,
            user_color=user.avatar_color or "#6366f1",
            status="offline",
        )