"""
Real-Time Collaboration Module for VCOS.

Provides:
- WebSocket Gateway (Socket.io)
- Redis-backed Presence Service
- CRDT Engine for collaborative editing
- WebRTC SFU integration (LiveKit)
"""

from app.core.realtime.websocket_gateway import (
    WebSocketGateway,
    ConnectionInfo,
    RoomInfo,
    create_realtime_app,
    add_realtime_to_app,
)

from app.core.realtime.presence import (
    PresenceService,
    PresenceData,
    ConnectionInfo,
)

from app.core.realtime.crdt import (
    CRDTEngine,
    CRDTDocument,
    CRDTOperation,
    CRDTType,
    OperationType,
    CollaborativeDocument,
    get_crdt_engine,
    get_collaborative_document,
    CRDTEngine,
    CRDTDocument,
    CRDTOperation,
    CRDTType,
    OperationType,
    CollaborativeDocument,
    get_crdt_engine,
    get_collaborative_document,
)

__all__ = [
    # WebSocket Gateway
    "WebSocketGateway",
    "ConnectionInfo",
    "RoomInfo",
    "create_realtime_app",
    "add_realtime_to_app",
    
    # Presence Service
    "PresenceService",
    "PresenceData",
    "ConnectionInfo",
    
    # CRDT Engine
    "CRDTEngine",
    "CRDTDocument",
    "CRDTOperation",
    "CRDTType",
    "OperationType",
    "CollaborativeDocument",
    "get_crdt_engine",
    "get_collaborative_document",
]