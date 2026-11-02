"""Real-time WebSocket API with Redis-backed Presence."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query, HTTPException
from typing import Dict, List, Set, Optional, Any
from datetime import datetime, timezone
import json
import asyncio
import logging
from uuid import uuid4
from dataclasses import asdict

from app.api.deps import get_current_user_ws, get_current_organization_ws
from app.models.organization import Organization
from app.models.user import User
from app.core.config import get_settings
from app.core.presence_redis import PresenceService, PresenceData

router = APIRouter(tags=["realtime"])
logger = logging.getLogger(__name__)

settings = get_settings()


class RedisConnectionManager:
    """Manages WebSocket connections using Redis-backed presence."""
    
    def __init__(self):
        # Local connection mapping: organization_id -> {user_id: {connection_id: WebSocket}}
        self.active_connections: Dict[str, Dict[str, Dict[str, WebSocket]]] = {}
        # connection_id -> {organization_id, user_id, user_info}
        self.connection_metadata: Dict[str, Dict[str, Any]] = {}
    
    async def connect(
        self,
        websocket: WebSocket,
        organization_id: str,
        user_id: str,
        user_info: dict,
        presence_service: PresenceService,
    ) -> str:
        """Accept a new WebSocket connection."""
        await websocket.accept()
        
        connection_id = str(uuid4())
        
        # Initialize organization if not exists
        if organization_id not in self.active_connections:
            self.active_connections[organization_id] = {}
        
        if user_id not in self.active_connections[organization_id]:
            self.active_connections[organization_id][user_id] = {}
        
        # Store local connection
        self.active_connections[organization_id][user_id][connection_id] = websocket
        
        # Store metadata
        self.connection_metadata[connection_id] = {
            "organization_id": organization_id,
            "user_id": user_id,
            "user_info": user_info,
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "last_activity": datetime.now(timezone.utc).isoformat(),
        }
        
        # Register with Presence service
        await presence_service.register_connection(
            connection_id=connection_id,
            user_id=user_id,
            organization_id=organization_id,
            metadata={"user_info": user_info},
        )
        
        # Set presence
        await presence_service.set_presence(
            user_id=user_id,
            organization_id=organization_id,
            user_name=user_info.get("name", "Unknown"),
            user_color=self._get_user_color(user_id),
            status="online",
        )
        
        logger.info(f"WebSocket connected: user={user_id}, org={organization_id}, conn={connection_id}")
        return connection_id
    
    def _get_user_color(self, user_id: str) -> str:
        """Generate consistent color for user."""
        colors = [
            "#FF6B6B", "#4ECDC4", "#45B7D1", "#FFBE0B", "#FB5607",
            "#8338EC", "#3A86FF", "#06D6A0", "#FF9F1C", "#FF6F61",
        ]
        hash_val = 0
        for c in user_id:
            hash_val = (hash_val * 31 + ord(c)) & 0xFFFFFFFF
        return colors[hash_val % len(colors)]
    
    def disconnect(self, connection_id: str) -> Optional[Dict[str, Any]]:
        """Remove a WebSocket connection."""
        if connection_id not in self.connection_metadata:
            return None
        
        metadata = self.connection_metadata.pop(connection_id)
        organization_id = metadata["organization_id"]
        user_id = metadata["user_id"]
        user_info = metadata.get("user_info", {})
        
        # Remove from local connections
        if (organization_id in self.active_connections and
            user_id in self.active_connections[organization_id] and
            connection_id in self.active_connections[organization_id][user_id]):
            
            del self.active_connections[organization_id][user_id][connection_id]
            
            # Clean up empty dicts
            if not self.active_connections[organization_id][user_id]:
                del self.active_connections[organization_id][user_id]
            if not self.active_connections[organization_id]:
                del self.active_connections[organization_id]
        
        logger.info(f"WebSocket disconnected: user={user_id}, org={organization_id}, conn={connection_id}")
        return {"organization_id": organization_id, "user_id": user_id, "user_info": user_info}
    
    async def broadcast_to_organization(
        self,
        organization_id: str,
        message: dict,
        exclude_user: Optional[str] = None,
    ):
        """Broadcast a message to all connections in an organization."""
        if organization_id not in self.active_connections:
            return
        
        message_json = json.dumps(message)
        disconnected = []
        
        for user_id, connections in self.active_connections[organization_id].items():
            if exclude_user and user_id == exclude_user:
                continue
            
            for conn_id, ws in connections.items():
                try:
                    await ws.send_text(message_json)
                except Exception as e:
                    logger.warning(f"Failed to send to {conn_id}: {e}")
                    disconnected.append(conn_id)
        
        # Clean up disconnected
        for conn_id in disconnected:
            self.disconnect(conn_id)
    
    async def send_to_user(
        self,
        organization_id: str,
        user_id: str,
        message: dict,
    ):
        """Send a message to a specific user's all connections."""
        if organization_id not in self.active_connections:
            return
        if user_id not in self.active_connections[organization_id]:
            return
        
        message_json = json.dumps(message)
        disconnected = []
        
        for conn_id, ws in self.active_connections[organization_id][user_id].items():
            try:
                await ws.send_text(message_json)
            except Exception as e:
                logger.warning(f"Failed to send to {conn_id}: {e}")
                disconnected.append(conn_id)
        
        for conn_id in disconnected:
            self.disconnect(conn_id)
    
    async def send_to_connection(self, connection_id: str, message: dict):
        """Send a message to a specific connection."""
        if connection_id not in self.connection_metadata:
            return
        
        metadata = self.connection_metadata[connection_id]
        organization_id = metadata["organization_id"]
        user_id = metadata["user_id"]
        
        if (organization_id in self.active_connections and
            user_id in self.active_connections[organization_id] and
            connection_id in self.active_connections[organization_id][user_id]):
            
            ws = self.active_connections[organization_id][user_id][connection_id]
            try:
                await ws.send_text(json.dumps(message))
            except Exception as e:
                logger.warning(f"Failed to send to {connection_id}: {e}")
                self.disconnect(connection_id)
    
    def get_online_users(self, organization_id: str) -> List[dict]:
        """Get list of online users in an organization."""
        if organization_id not in self.active_connections:
            return []
        
        online_users = []
        for user_id, connections in self.active_connections[organization_id].items():
            if connections:
                conn_id = next(iter(connections))
                metadata = self.connection_metadata.get(conn_id, {})
                online_users.append({
                    "user_id": user_id,
                    "user_info": metadata.get("user_info", {}),
                    "connection_count": len(connections),
                    "last_activity": metadata.get("last_activity"),
                })
        return online_users
    
    def is_user_online(self, organization_id: str, user_id: str) -> bool:
        """Check if a user is online in an organization."""
        return (organization_id in self.active_connections and
                user_id in self.active_connections[organization_id] and
                len(self.active_connections[organization_id][user_id]) > 0)
    
    def get_connection_count(self, organization_id: str) -> int:
        """Get total connection count for an organization."""
        if organization_id not in self.active_connections:
            return 0
        return sum(
            len(conns) for conns in self.active_connections[organization_id].values()
        )


# Global connection manager
connection_manager = RedisConnectionManager()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    organization_id: str = Query(...),
):
    """
    WebSocket endpoint for real-time communication.
    
    Query parameters:
    - token: JWT access token
    - organization_id: Organization ID
    """
    # Validate token
    try:
        user_id = "test-user-id"  # TODO: Extract from token
        user_info = {
            "id": user_id,
            "name": "Test User",
            "email": "test@example.com",
            "avatar": None,
        }
    except Exception:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    # Get Presence service
    presence_service = PresenceService()
    await presence_service.initialize()
    
    connection_id = await connection_manager.connect(
        websocket, organization_id, user_id, user_info, presence_service
    )
    
    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
                await handle_message(connection_id, message, redis_presence)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "payload": {"message": "Invalid JSON"}
                }))
            except Exception as e:
                logger.error(f"Error handling message: {e}")
                await websocket.send_text(json.dumps({
                    "type": "error",
                    "payload": {"message": str(e)}
                }))
    except WebSocketDisconnect:
        metadata = connection_manager.disconnect(connection_id)
        if metadata:
            await presence_service.unregister_connection(connection_id)
            # Remove presence
            await presence_service.remove_presence(
                metadata["user_id"],
                metadata["organization_id"]
            )
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        metadata = connection_manager.disconnect(connection_id)
        if metadata:
            await presence_service.unregister_connection(connection_id)
            await presence_service.remove_presence(
                metadata["user_id"],
                metadata["organization_id"]
            )


async def handle_message(connection_id: str, message: dict, presence_service: PresenceService):
    """Handle incoming WebSocket message."""
    msg_type = message.get("type")
    payload = message.get("payload", {})
    
    if msg_type == "ping":
        # Respond to ping with pong
        metadata = connection_manager.connection_metadata.get(connection_id)
        if metadata:
            await connection_manager.send_to_connection(connection_id, {
                "type": "pong",
                "payload": {"timestamp": datetime.now(timezone.utc).isoformat()}
            })
    
    elif msg_type == "presence:update":
        # Update user presence status
        status = payload.get("status", "online")
        metadata = connection_manager.connection_metadata.get(connection_id)
        if metadata:
            await presence_service.update_status(
                metadata["user_id"],
                metadata["organization_id"],
                status
            )
    
    elif msg_type == "cursor:update":
        # Broadcast cursor position for collaborative editing
        metadata = connection_manager.connection_metadata.get(connection_id)
        if metadata:
            position = payload.get("position")
            selection = payload.get("selection")
            
            if position:
                await presence_service.update_cursor(
                    metadata["user_id"],
                    metadata["organization_id"],
                    position
                )
            
            if selection:
                await presence_service.update_selection(
                    metadata["user_id"],
                    metadata["organization_id"],
                    selection
                )
    
    elif msg_type == "document:edit":
        # Broadcast document edit for collaborative editing
        metadata = connection_manager.connection_metadata.get(connection_id)
        if metadata:
            # Broadcast to organization
            await connection_manager.broadcast_to_organization(
                metadata["organization_id"],
                {
                    "type": "document:edit",
                    "payload": {
                        "user_id": metadata["user_id"],
                        "user_name": metadata["user_info"].get("name", "Unknown"),
                        "position": payload.get("position"),
                        "selection": payload.get("selection"),
                    }
                },
                exclude_user=metadata["user_id"]
            )
    
    elif msg_type == "typing:start":
        metadata = connection_manager.connection_metadata.get(connection_id)
        if metadata:
            await connection_manager.broadcast_to_organization(
                metadata["organization_id"],
                {
                    "type": "typing:start",
                    "payload": {
                        "user_id": metadata["user_id"],
                        "user_name": metadata["user_info"].get("name", "Unknown"),
                    }
                },
                exclude_user=metadata["user_id"]
            )
    
    elif msg_type == "typing:stop":
        metadata = connection_manager.connection_metadata.get(connection_id)
        if metadata:
            await connection_manager.broadcast_to_organization(
                metadata["organization_id"],
                {
                    "type": "typing:stop",
                    "payload": {
                        "user_id": metadata["user_id"],
                        "user_name": metadata["user_info"].get("name", "Unknown"),
                    }
                },
                exclude_user=metadata["user_id"]
            )
    
    elif msg_type == "subscribe:presence":
        # Subscribe to presence updates for organization
        metadata = connection_manager.connection_metadata.get(connection_id)
        if metadata:
            logger.info(f"User {metadata['user_id']} subscribed to presence updates")


@router.get("/presence")
async def get_online_users(
    organization_id: str,
    presence_service: PresenceService = Depends(lambda: PresenceService()),
):
    """Get list of online users in the organization."""
    await presence_service.initialize()
    presences = await presence_service.get_organization_presence(organization_id)
    return {"online_users": [asdict(p) for p in presences]}


@router.get("/presence/{user_id}")
async def get_user_presence(
    user_id: str,
    organization_id: str,
    presence_service: PresenceService = Depends(lambda: PresenceService()),
):
    """Get presence status for a specific user."""
    await presence_service.initialize()
    presence = await presence_service.get_presence(user_id, organization_id)
    
    if not presence:
        return {
            "user_id": user_id,
            "is_online": False,
            "last_activity": None,
        }
    
    return {
        "user_id": presence.user_id,
        "is_online": presence.status == "online",
        "status": presence.status,
        "last_activity": presence.last_active,
        "cursor": presence.cursor,
        "selection": presence.selection,
    }


@router.get("/stats")
async def get_connection_stats(
    organization_id: str,
    presence_service: PresenceService = Depends(lambda: PresenceService()),
):
    """Get connection statistics for an organization."""
    await presence_service.initialize()
    stats = await presence_service.get_stats(organization_id)
    return stats


# Add to main.py lifespan to initialize/close Redis presence
# from app.core.presence_redis import get_redis_presence_service, close_redis_presence_service