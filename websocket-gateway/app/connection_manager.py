"""
Connection Manager for WebSocket Gateway
Manages WebSocket connections with Redis-backed state
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

import redis.asyncio as redis

from app.config import settings
from app.models import ConnectionInfo


@dataclass
class Connection:
    """Internal connection representation"""
    connection_id: str
    websocket: Any
    resource_id: str
    connection_type: str
    user_id: str
    organization_id: str
    connected_at: float
    last_activity: float
    metadata: Dict[str, Any] = field(default_factory=dict)
    _send_queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    _send_task: Optional[asyncio.Task] = None


class ConnectionManager:
    """
    Manages WebSocket connections with Redis-backed state for horizontal scaling
    """
    
    def __init__(self, redis_client: redis.Redis, config: settings):
        self.redis = redis_client
        self.config = config
        self.connections: Dict[str, Connection] = {}
        self.resource_connections: Dict[str, Set[str]] = {}  # resource_id -> connection_ids
        self.user_connections: Dict[str, Set[str]] = {}  # user_id -> connection_ids
        self.org_connections: Dict[str, Set[str]] = {}  # org_id -> connection_ids
        self._cleanup_task: Optional[asyncio.Task] = None
        
    async def add_connection(
        self,
        connection_id: str,
        websocket: Any,
        resource_id: str,
        connection_info: "ConnectionInfo",
    ) -> None:
        """Add a new connection"""
        connection = Connection(
            connection_id=connection_id,
            websocket=websocket,
            resource_id=connection_info.resource_id if hasattr(connection_info, 'resource_id') else resource_id,
            connection_type=connection_info.connection_type,
            user_id=connection_info.user_id,
            organization_id=connection_info.organization_id,
            connected_at=connection_info.connected_at,
            last_activity=connection_info.last_activity,
            metadata=connection_info.metadata,
        )
        
        self.connections[connection_id] = connection
        
        # Index by resource
        if resource_id not in self.resource_connections:
            self.resource_connections[resource_id] = set()
        self.resource_connections[resource_id].add(connection_id)
        
        # Index by user
        if connection_info.user_id not in self.user_connections:
            self.user_connections[connection_info.user_id] = set()
        self.user_connections[connection_info.user_id].add(connection_id)
        
        # Index by organization
        if connection_info.organization_id not in self.org_connections:
            self.org_connections[connection_info.organization_id] = set()
        self.org_connections[connection_info.organization_id].add(connection_id)
        
        # Start send task
        connection._send_task = asyncio.create_task(self._send_loop(connection))
        
        # Store in Redis for horizontal scaling
        await self._store_connection(connection_id, connection)
        
        # Update metrics
        await self._update_redis_metrics()
    
    async def remove_connection(self, connection_id: str) -> bool:
        """Remove a connection"""
        connection = self.connections.pop(connection_id, None)
        if not connection:
            return False
        
        # Cancel send task
        if connection._send_task:
            connection._send_task.cancel()
            try:
                await connection._send_task
            except asyncio.CancelledError:
                pass
        
        # Remove from indexes
        resource_id = connection.resource_id
        if resource_id in self.resource_connections:
            self.resource_connections[resource_id].discard(connection_id)
            if not self.resource_connections[resource_id]:
                del self.resource_connections[resource_id]
        
        user_id = connection.user_id
        if user_id in self.user_connections:
            self.user_connections[user_id].discard(connection_id)
            if not self.user_connections[user_id]:
                del self.user_connections[user_id]
        
        org_id = connection.organization_id
        if org_id in self.org_connections:
            self.org_connections[org_id].discard(connection_id)
            if not self.org_connections[org_id]:
                del self.org_connections[org_id]
        
        # Remove from Redis
        await self._remove_connection(connection_id)
        
        # Update metrics
        await self._update_redis_metrics()
        
        return True
    
    async def get_connection(self, connection_id: str) -> Optional[Connection]:
        """Get connection by ID"""
        return self.connections.get(connection_id)
    
    async def get_connections_for_resource(self, resource_id: str) -> List[Connection]:
        """Get all connections for a resource"""
        connection_ids = self.resource_connections.get(resource_id, set())
        return [self.connections[cid] for cid in connection_ids if cid in self.connections]
    
    async def get_connections_for_user(self, user_id: str) -> List[Connection]:
        """Get all connections for a user"""
        connection_ids = self.user_connections.get(user_id, set())
        return [self.connections[cid] for cid in connection_ids if cid in self.connections]
    
    async def get_connections_for_org(self, org_id: str) -> List[Connection]:
        """Get all connections for an organization"""
        connection_ids = self.org_connections.get(org_id, set())
        return [self.connections[cid] for cid in connection_ids if cid in self.connections]
    
    async def send_to_connection(self, connection_id: str, message: Dict[str, Any]) -> bool:
        """Send message to a specific connection"""
        connection = self.connections.get(connection_id)
        if not connection:
            return False
        
        try:
            await connection._send_queue.put(message)
            return True
        except Exception:
            return False
    
    async def broadcast_to_resource(
        self,
        resource_id: str,
        message: Dict[str, Any],
        exclude: Optional[str] = None,
    ) -> int:
        """Broadcast message to all connections for a resource"""
        connection_ids = self.resource_connections.get(resource_id, set())
        sent = 0
        
        for conn_id in connection_ids:
            if conn_id != exclude:
                if await self.send_to_connection(conn_id, message):
                    sent += 1
        
        return sent
    
    async def broadcast_to_user(
        self,
        user_id: str,
        message: Dict[str, Any],
        exclude: Optional[str] = None,
    ) -> int:
        """Broadcast message to all connections for a user"""
        connection_ids = self.user_connections.get(user_id, set())
        sent = 0
        
        for conn_id in connection_ids:
            if conn_id != exclude:
                if await self.send_to_connection(conn_id, message):
                    sent += 1
        
        return sent
    
    async def broadcast_to_org(
        self,
        org_id: str,
        message: Dict[str, Any],
        exclude: Optional[str] = None,
    ) -> int:
        """Broadcast message to all connections in an organization"""
        connection_ids = self.org_connections.get(org_id, set())
        sent = 0
        
        for conn_id in connection_ids:
            if conn_id != exclude:
                if await self.send_to_connection(conn_id, message):
                    sent += 1
        
        return sent
    
    async def broadcast_to_channel(self, channel: str, data: Dict[str, Any]) -> int:
        """Broadcast message from PubSub channel to relevant connections"""
        # This would determine which connections should receive the message
        # based on the channel and message content
        # For now, broadcast to all connections (can be optimized)
        sent = 0
        for connection in self.connections.values():
            if await self.send_to_connection(connection.connection_id, data):
                sent += 1
        return sent
    
    async def update_activity(self, connection_id: str) -> None:
        """Update last activity timestamp"""
        connection = self.connections.get(connection_id)
        if connection:
            connection.last_activity = time.time()
            await self._store_connection(connection.connection_id, connection)
    
    async def cleanup_stale(self, timeout: float = 60) -> int:
        """Remove stale connections"""
        now = time.time()
        stale_ids = []
        
        for conn_id, conn in self.connections.items():
            if now - conn.last_activity > timeout:
                stale_ids.append(conn_id)
        
        for conn_id in stale_ids:
            await self.remove_connection(conn_id)
        
        return len(stale_ids)
    
    def get_stats(self) -> Dict[str, int]:
        """Get connection statistics"""
        stats = {
            "total": len(self.connections),
            "crdt": 0,
            "signaling": 0,
            "presence": 0,
        }
        
        for conn in self.connections.values():
            if conn.connection_type in stats:
                stats[conn.connection_type] += 1
        
        stats["resources"] = len(self.resource_connections)
        stats["users"] = len(self.user_connections)
        stats["organizations"] = len(self.org_connections)
        
        return stats
    
    async def shutdown(self) -> None:
        """Shutdown all connections"""
        for conn_id in list(self.connections.keys()):
            await self.remove_connection(conn_id)
    
    # ==================== Private Methods ====================
    
    async def _send_loop(self, connection: Connection) -> None:
        """Send messages from queue to WebSocket"""
        try:
            while True:
                message = await connection._send_queue.get()
                try:
                    await connection.websocket.send_json(message)
                except Exception as e:
                    # Connection closed or error
                    break
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
    
    async def _store_connection(self, connection_id: str, connection: Connection) -> None:
        """Store connection in Redis for horizontal scaling"""
        key = f"vcos:ws:conn:{connection_id}"
        data = {
            "connection_id": connection.connection_id,
            "resource_id": connection.resource_id,
            "connection_type": connection.connection_type,
            "user_id": connection.user_id,
            "organization_id": connection.organization_id,
            "connected_at": connection.connected_at,
            "last_activity": connection.last_activity,
            "metadata": connection.metadata,
            "gateway_id": settings.gateway_id if hasattr(settings, 'gateway_id') else "gateway-1",
        }
        await self.redis.setex(key, 3600, json.dumps(data))
    
    async def _remove_connection(self, connection_id: str) -> None:
        """Remove connection from Redis"""
        key = f"vcos:ws:conn:{connection_id}"
        await self.redis.delete(key)
    
    async def _update_redis_metrics(self) -> None:
        """Update metrics in Redis"""
        stats = self.get_stats()
        await self.redis.hset("vcos:ws:metrics", mapping={
            "total_connections": str(stats["total"]),
            "crdt_connections": str(stats.get("crdt", 0)),
            "signaling_connections": str(stats.get("signaling", 0)),
            "presence_connections": str(stats.get("presence", 0)),
            "resources": str(stats.get("resources", 0)),
            "users": str(stats.get("users", 0)),
            "organizations": str(stats.get("organizations", 0)),
            "updated_at": str(time.time()),
        })