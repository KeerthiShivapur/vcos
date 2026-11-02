"""
Real-Time WebSocket Gateway for VCOS.

Provides WebSocket infrastructure for real-time collaboration:
- Connection management with auth
- Presence tracking with Redis
- Message broadcasting
- Room/channel management
- Yjs CRDT integration for collaborative editing
"""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Set
from weakref import WeakSet

import jwt
import redis.asyncio as redis
import socketio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from fastapi.responses import HTMLResponse

from app.core.config import get_settings
from app.core.security import decode_token, ACCESS
from app.core.realtime.presence import PresenceService, PresenceData
from app.core.realtime.crdt import CRDTEngine, CRDTDocument

logger = logging.getLogger("vcos.realtime")


@dataclass
class ConnectionInfo:
    """WebSocket connection metadata."""
    connection_id: str
    user_id: str
    organization_id: str
    user_name: str
    user_color: str
    connected_at: datetime
    last_ping: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)
    subscribed_rooms: Set[str] = field(default_factory=set)
    cursor_position: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, int]] = None


@dataclass
class RoomInfo:
    """Room/channel information."""
    room_id: str
    room_type: str  # document, whiteboard, meeting, channel
    organization_id: str
    name: str
    created_at: datetime
    created_by: str
    participants: Set[str] = field(default_factory=set)  # connection_ids
    settings: Dict[str, Any] = field(default_factory=dict)
    crdt_document: Optional["CRDTDocument"] = None


class WebSocketGateway:
    """
    WebSocket Gateway for real-time communication.
    
    Features:
    - Connection lifecycle management
    - Authentication via JWT
    - Room/channel management
    - Message broadcasting
    - Presence tracking
    - Yjs CRDT integration for collaborative editing
    """
    
    def __init__(self, app: FastAPI):
        self.app = app
        self.settings = get_settings()
        
        # Socket.IO server
        self.sio = socketio.AsyncServer(
            async_mode="asgi",
            cors_allowed_origins=self.settings.CORS_ORIGINS,
            logger=True,
            engineio_logger=True,
            ping_timeout=60,
            ping_interval=25,
        )
        
        # ASGI app for Socket.IO
        self.socket_app = socketio.ASGIApp(self.sio)
        
        # Connection management
        self.connections: Dict[str, ConnectionInfo] = {}
        self.user_connections: Dict[str, Set[str]] = {}  # user_id -> set of connection_ids
        self.org_connections: Dict[str, Set[str]] = {}   # org_id -> set of connection_ids
        
        # Room management
        self.rooms: Dict[str, RoomInfo] = {}
        
        # Redis for presence and pub/sub
        self.redis: Optional[redis.Redis] = None
        self.presence_service: Optional[PresenceService] = None
        self.crdt_engine: Optional[CRDTEngine] = None
        
        # Event handlers
        self._event_handlers: Dict[str, List[Callable]] = {}
        
        # Register event handlers
        self._register_handlers()
    
    def _register_handlers(self):
        """Register Socket.IO event handlers."""
        
        @self.sio.event
        async def connect(sid, environ, auth):
            """Handle new WebSocket connection."""
            try:
                # Authenticate user
                token = auth.get("token") if auth else None
                if not token:
                    await self.sio.disconnect(sid)
                    return False
                
                # Validate JWT
                payload = decode_token(token, ACCESS)
                user_id = payload.get("sub")
                org_id = payload.get("org")
                
                if not user_id or not org_id:
                    await self.sio.disconnect(sid)
                    return False
                
                # Get user info (would fetch from DB in production)
                user_info = await self._get_user_info(user_id, org_id)
                
                # Create connection info
                conn_info = ConnectionInfo(
                    connection_id=sid,
                    user_id=user_id,
                    organization_id=org_id,
                    user_name=user_info.get("full_name", "Unknown"),
                    user_color=user_info.get("color", self._generate_color(user_id)),
                    connected_at=datetime.now(timezone.utc),
                    last_ping=datetime.now(timezone.utc),
                )
                
                # Store connection
                self.connections[sid] = conn_info
                self.user_connections.setdefault(user_id, set()).add(sid)
                self.org_connections.setdefault(org_id, set()).add(sid)
                
                # Update presence
                if self.presence_service:
                    await self.presence_service.set_presence(
                        org_id, user_id, user_info, "online"
                    )
                
                # Join organization room
                await self.sio.enter_room(sid, f"org:{org_id}")
                
                # Emit connection success
                await self.sio.emit("connected", {
                    "connection_id": sid,
                    "user_id": user_id,
                    "organization_id": org_id,
                    "server_time": datetime.now(timezone.utc).isoformat(),
                }, room=sid)
                
                # Notify others in org
                await self.sio.emit("user_joined", {
                    "user_id": user_id,
                    "user_name": user_info.get("full_name"),
                    "user_color": user_info.get("color"),
                }, room=f"org:{org_id}", skip_sid=sid)
                
                logger.info(f"User {user_id} connected (sid={sid})")
                return True
                
            except Exception as e:
                logger.error(f"Connection failed: {e}")
                await self.sio.disconnect(sid)
                return False
        
        @self.sio.event
        async def disconnect(sid):
            """Handle WebSocket disconnection."""
            conn = self.connections.get(sid)
            if not conn:
                return
            
            user_id = conn.user_id
            org_id = conn.organization_id
            
            # Leave all rooms
            for room_id in conn.subscribed_rooms:
                await self._leave_room(sid, room_id)
            
            # Leave organization room
            await self.sio.leave_room(sid, f"org:{org_id}")
            
            # Update presence
            if self.presence_service:
                await self.presence_service.set_presence(
                    org_id, user_id, None, "offline"
                )
            
            # Clean up
            self.connections.pop(sid, None)
            self.user_connections.get(user_id, set()).discard(sid)
            self.org_connections.get(org_id, set()).discard(sid)
            
            # Notify others
            await self.sio.emit("user_left", {
                "user_id": user_id,
                "user_name": conn.user_name,
            }, room=f"org:{org_id}")
            
            logger.info(f"User {user_id} disconnected (sid={sid})")
        
        @self.sio.event
        async def ping(sid, data):
            """Handle ping/pong for connection health."""
            conn = self.connections.get(sid)
            if conn:
                conn.last_ping = datetime.now(timezone.utc)
                return {"pong": True, "server_time": datetime.now(timezone.utc).isoformat()}
            return {"pong": False}
        
        @self.sio.event
        async def join_room(sid, data):
            """Join a collaboration room."""
            room_id = data.get("room_id")
            room_type = data.get("room_type", "document")
            
            conn = self.connections.get(sid)
            if not conn:
                return {"error": "Not connected"}
            
            # Verify org access
            if not await self._can_access_room(conn, room_id, room_type):
                return {"error": "Access denied"}
            
            # Join room
            await self._join_room(sid, room_id, room_type)
            return {"success": True, "room_id": room_id}
        
        @self.sio.event
        async def leave_room(sid, data):
            """Leave a collaboration room."""
            room_id = data.get("room_id")
            if room_id:
                await self._leave_room(sid, room_id)
                return {"success": True}
            return {"error": "Room ID required"}
        
        @self.sio.event
        async def cursor_update(sid, data):
            """Handle cursor position updates."""
            conn = self.connections.get(sid)
            if not conn:
                return
            
            room_id = data.get("room_id")
            cursor = data.get("cursor")
            selection = data.get("selection")
            
            if not room_id:
                return
            
            conn.cursor_position = cursor
            conn.selection = selection
            
            # Broadcast to room
            await self.sio.emit("cursor_update", {
                "user_id": conn.user_id,
                "user_name": conn.user_name,
                "user_color": conn.user_color,
                "cursor": cursor,
                "selection": selection,
            }, room=room_id, skip_sid=sid)
        
        @self.sio.event
        async def crdt_update(sid, data):
            """Handle CRDT document updates."""
            room_id = data.get("room_id")
            update = data.get("update")
            
            if not room_id or not update:
                return
            
            conn = self.connections.get(sid)
            if not conn:
                return
            
            # Apply to CRDT document
            if self.crdt_engine:
                doc = await self.crdt_engine.get_document(room_id)
                if doc:
                    await doc.apply_update(update, conn.user_id)
                    
                    # Broadcast to room
                    await self.sio.emit("crdt_update", {
                        "user_id": conn.user_id,
                        "update": update,
                    }, room=room_id, skip_sid=sid)
        
        @self.sio.event
        async def message(sid, data):
            """Handle chat messages in rooms."""
            conn = self.connections.get(sid)
            if not conn:
                return
            
            room_id = data.get("room_id")
            content = data.get("content")
            message_type = data.get("type", "text")
            
            if not room_id or not content:
                return
            
            # Broadcast message
            await self.sio.emit("message", {
                "id": str(uuid.uuid4()),
                "user_id": conn.user_id,
                "user_name": conn.user_name,
                "user_color": conn.user_color,
                "content": content,
                "type": message_type,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }, room=room_id)
        
        @self.sio.event
        async def typing_start(sid, data):
            """Handle typing indicator start."""
            conn = self.connections.get(sid)
            if not conn:
                return
            
            room_id = data.get("room_id")
            if room_id:
                await self.sio.emit("typing_start", {
                    "user_id": conn.user_id,
                    "user_name": conn.user_name,
                }, room=room_id, skip_sid=sid)
        
        @self.sio.event
        async def typing_stop(sid, data):
            """Handle typing indicator stop."""
            conn = self.connections.get(sid)
            if not conn:
                return
            
            room_id = data.get("room_id")
            if room_id:
                await self.sio.emit("typing_stop", {
                    "user_id": conn.user_id,
                }, room=room_id, skip_sid=sid)
    
    async def _get_user_info(self, user_id: str, org_id: str) -> Dict[str, Any]:
        """Get user info (placeholder - would fetch from DB)."""
        # In production, fetch from database
        return {
            "user_id": user_id,
            "full_name": f"User {user_id[:8]}",
            "color": self._generate_color(user_id),
        }
    
    def _generate_color(self, user_id: str) -> str:
        """Generate consistent color for user."""
        colors = [
            "#EF4444", "#F97316", "#F59E0B", "#EAB308", "#84CC16",
            "#22C55E", "#10B981", "#14B8A6", "#06B6D4", "#0EA5E9",
            "#3B82F6", "#6366F1", "#8B5CF6", "#A855F7", "#D946EF",
            "#EC4899", "#F43F5E", "#F97316", "#F59E0B", "#EAB308",
        ]
        hash_val = hash(user_id)
        return colors[abs(hash_val) % len(colors)]
    
    async def _can_access_room(self, conn: ConnectionInfo, room_id: str, room_type: str) -> bool:
        """Check if user can access room."""
        room = self.rooms.get(room_id)
        if not room:
            return True  # Allow creating new rooms
        return room.organization_id == conn.organization_id
    
    async def _join_room(self, sid: str, room_id: str, room_type: str):
        """Join a collaboration room."""
        conn = self.connections.get(sid)
        if not conn:
            return
        
        conn.subscribed_rooms.add(room_id)
        await self.sio.enter_room(sid, room_id)
        
        # Create room if doesn't exist
        if room_id not in self.rooms:
            self.rooms[room_id] = RoomInfo(
                room_id=room_id,
                room_type=room_type,
                organization_id=self.connections[sid].organization_id,
                name=f"{room_type} {room_id}",
                created_at=datetime.now(timezone.utc),
                created_by=self.connections[sid].user_id,
            )
        
        room = self.rooms[room_id]
        room.participants.add(sid)
        
        # Initialize CRDT document if needed
        if room_type in ("document", "whiteboard") and self.crdt_engine:
            if not room.crdt_document:
                room.crdt_document = await self.crdt_engine.get_or_create_document(room_id)
        
        # Send room state to user
        await self.sio.emit("room_state", {
            "room_id": room_id,
            "room_type": room_type,
            "participants": [
                {
                    "connection_id": pid,
                    "user_id": self.connections[pid].user_id,
                    "user_name": self.connections[pid].user_name,
                    "user_color": self.connections[pid].user_color,
                    "cursor": self.connections[pid].cursor_position,
                }
                for pid in room.participants if pid in self.connections
            ],
            "document": room.crdt_document.get_state() if room.crdt_document else None,
        }, room=sid)
        
        # Notify others
        conn = self.connections[sid]
        await self.sio.emit("user_joined_room", {
            "room_id": room_id,
            "user_id": conn.user_id,
            "user_name": conn.user_name,
            "user_color": conn.user_color,
        }, room=room_id, skip_sid=sid)
    
    async def _leave_room(self, sid: str, room_id: str):
        """Leave a collaboration room."""
        conn = self.connections.get(sid)
        if not conn:
            return
        
        conn.subscribed_rooms.discard(room_id)
        await self.sio.leave_room(sid, room_id)
        
        room = self.rooms.get(room_id)
        if room:
            room.participants.discard(sid)
            
            # Notify others
            await self.sio.emit("user_left_room", {
                "room_id": room_id,
                "user_id": conn.user_id,
            }, room=room_id)
            
            # Clean up empty rooms
            if not room.participants:
                if room.crdt_document:
                    await self.crdt_engine.save_document(room.crdt_document)
                del self.rooms[room_id]
    
    async def broadcast(self, event: str, data: Dict, room: Optional[str] = None, skip_sid: Optional[str] = None):
        """Broadcast event to room or all connections."""
        if room:
            await self.sio.emit(event, data, room=room, skip_sid=skip_sid)
        else:
            await self.sio.emit(event, data, skip_sid=skip_sid)
    
    def get_connection(self, sid: str) -> Optional[ConnectionInfo]:
        return self.connections.get(sid)
    
    def get_room(self, room_id: str) -> Optional[RoomInfo]:
        return self.rooms.get(room_id)
    
    def get_org_connections(self, org_id: str) -> Set[str]:
        return self.org_connections.get(org_id, set())
    
    def get_user_connections(self, user_id: str) -> Set[str]:
        return self.user_connections.get(user_id, set())
    
    async def shutdown(self):
        """Graceful shutdown."""
        # Save all CRDT documents
        if self.crdt_engine:
            for room in self.rooms.values():
                if room.crdt_document:
                    await self.crdt_engine.save_document(room.crdt_document)
        
        # Close all connections
        for sid in list(self.connections.keys()):
            await self.sio.disconnect(sid)
        
        if self.redis:
            await self.redis.close()


# ============================================================================
# FastAPI Integration
# ============================================================================

def create_realtime_app() -> FastAPI:
    """Create FastAPI app with WebSocket support."""
    app = FastAPI(title="VCOS Real-Time Gateway")
    
    # Initialize gateway
    gateway = WebSocketGateway(app)
    app.state.realtime_gateway = gateway
    
    # Mount Socket.IO
    app.mount("/socket.io", gateway.socket_app)
    
    @app.on_event("startup")
    async def startup():
        # Initialize Redis
        settings = get_settings()
        if settings.REDIS_ENABLED and settings.REDIS_URL:
            gateway.redis = redis.from_url(settings.REDIS_URL, decode_responses=True)
            await gateway.redis.ping()
            
            # Initialize presence service
            gateway.presence_service = PresenceService(gateway.redis)
            
            # Initialize CRDT engine
            gateway.crdt_engine = CRDTEngine(gateway.redis)
        
        logger.info("Real-time gateway initialized")
    
    @app.on_event("shutdown")
    async def shutdown():
        await gateway.shutdown()
    
    @app.get("/health/realtime")
    async def realtime_health():
        return {
            "status": "healthy",
            "connections": len(gateway.connections),
            "rooms": len(gateway.rooms),
            "orgs": len(gateway.org_connections),
        }
    
    @app.get("/realtime/stats")
    async def realtime_stats():
        return {
            "connections": len(gateway.connections),
            "rooms": len(gateway.rooms),
            "orgs": len(gateway.org_connections),
            "users": len(gateway.user_connections),
        }
    
    return app


# ============================================================================
# Convenience function to add real-time to existing FastAPI app
# ============================================================================

def add_realtime_to_app(app: FastAPI) -> WebSocketGateway:
    """Add real-time capabilities to existing FastAPI app."""
    gateway = WebSocketGateway(app)
    app.state.realtime_gateway = gateway
    app.mount("/socket.io", gateway.socket_app)
    
    # Add health and stats endpoints
    @app.get("/health/realtime")
    async def realtime_health():
        return {
            "status": "healthy",
            "connections": len(gateway.connections),
            "rooms": len(gateway.rooms),
            "orgs": len(gateway.org_connections),
        }
    
    @app.get("/realtime/stats")
    async def realtime_stats():
        return {
            "connections": len(gateway.connections),
            "rooms": len(gateway.rooms),
            "orgs": len(gateway.org_connections),
            "users": len(gateway.user_connections),
        }
    
    return gateway