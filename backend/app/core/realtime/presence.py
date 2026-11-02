"""
Presence Service for VCOS Real-Time Collaboration.

Manages user presence state with Redis backend:
- Online/offline status
- User activity tracking
- Organization-wide presence
- TTL-based expiration
"""

import json
import logging
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import redis.asyncio as redis

logger = logging.getLogger("vcos.realtime.presence")


@dataclass
class PresenceData:
    """User presence data."""
    user_id: str
    user_name: str
    user_color: str
    organization_id: str
    status: str = "online"  # online, idle, away, offline
    cursor: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, int]] = None
    status_message: str = ""
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "user_color": self.user_color,
            "organization_id": self.organization_id,
            "status": self.status,
            "cursor": self.cursor,
            "selection": self.selection,
            "status_message": self.status_message,
            "last_active": self.last_active.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresenceData":
        return cls(
            user_id=data["user_id"],
            user_name=data["user_name"],
            user_color=data["user_color"],
            organization_id=data["organization_id"],
            status=data.get("status", "online"),
            cursor=data.get("cursor"),
            selection=data.get("selection"),
            status_message=data.get("status_message", ""),
            last_active=datetime.fromisoformat(data["last_active"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ConnectionInfo:
    """WebSocket connection info for presence."""
    connection_id: str
    user_id: str
    user_name: str
    user_color: str
    organization_id: str
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_ping: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    subscribed_rooms: Set[str] = field(default_factory=set)
    cursor_position: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, int]] = None


class PresenceService:
    """
    Redis-backed presence service for real-time user presence.
    
    Features:
    - TTL-based presence expiration
    - Organization-wide presence queries
    - Real-time presence updates via pub/sub
    - Connection tracking
    - Heartbeat/heartbeat monitoring
    """
    
    # Redis key prefixes
    PRESENCE_KEY_PREFIX = "vcos:presence:"
    CONNECTION_KEY_PREFIX = "vcos:connection:"
    ORG_PRESENCE_SET = "vcos:org_presence:"
    USER_CONNECTIONS_SET = "vcos:user_connections:"
    ORG_CONNECTIONS_SET = "vcos:org_connections:"
    HEARTBEAT_CHANNEL = "vcos:heartbeat"
    PRESENCE_CHANNEL = "vcos:presence_updates"
    
    # TTL settings (seconds)
    PRESENCE_TTL = 300  # 5 minutes
    CONNECTION_TTL = 3600  # 1 hour
    HEARTBEAT_INTERVAL = 30  # 30 seconds
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._running = False
        self._heartbeat_task = None
        self._listener_task = None
        self._pubsub = None
    
    async def initialize(self):
        """Initialize presence service."""
        self._running = True
        
        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Subscribe to presence channel
        self._pubsub = self.redis.pubsub()
        await self._pubsub.subscribe(self.PRESENCE_CHANNEL)
        self._listener_task = asyncio.create_task(self._listen_for_updates())
        
        logger.info("Presence service initialized")
    
    async def close(self):
        """Close presence service."""
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        if self._pubsub:
            await self._pubsub.unsubscribe(self.PRESENCE_CHANNEL)
            await self._pubsub.close()
    
    async def _heartbeat_loop(self):
        """Periodic heartbeat to clean up stale connections."""
        while True:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                
                # Scan for expired connections
                await self._cleanup_expired()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _cleanup_expired(self):
        """Remove expired connections and presence data."""
        try:
            # Use SCAN to find expired connection keys
            pattern = f"{self.CONNECTION_KEY_PREFIX}*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                
                if keys:
                    # Check TTL for each key
                    pipe = self.redis.pipeline()
                    for key in keys:
                        pipe.ttl(key)
                    ttls = await pipe.execute()
                    
                    expired_keys = [key for key, ttl in zip(keys, ttls) if ttl <= 0]
                    
                    if expired_keys:
                        # Clean up expired connections
                        await self._cleanup_connections(expired_keys)
                
                if cursor == 0:
                    break
                    
        except Exception as e:
            logger.error(f"Failed to cleanup expired: {e}")
    
    async def _cleanup_connections(self, expired_keys: List[str]):
        """Clean up expired connection data."""
        try:
            pipe = self.redis.pipeline()
            
            for key in expired_keys:
                # Get connection data before deleting
                conn_data = await self.redis.get(key)
                if conn_data:
                    try:
                        conn_info = json.loads(conn_data)
                        user_id = conn_info.get("user_id")
                        org_id = conn_info.get("organization_id")
                        conn_id = conn_info.get("connection_id")
                        
                        if user_id and org_id:
                            # Remove from user/org sets
                            await self.redis.srem(f"{self.USER_CONNECTIONS_SET}{user_id}", conn_id)
                            await self.redis.srem(f"{self.ORG_CONNECTIONS_SET}{org_id}", conn_id)
                            await self.redis.srem(f"{self.ORG_PRESENCE_SET}{org_id}", user_id)
                            
                            # Publish offline event
                            await self.redis.publish(
                                self.PRESENCE_CHANNEL,
                                json.dumps({
                                    "type": "offline",
                                    "user_id": user_id,
                                    "organization_id": org_id,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })
                            )
                    except Exception:
                        pass
                
                pipe.delete(key)
            
            await pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to cleanup connections: {e}")
    
    async def _listen_for_updates(self):
        """Listen for presence updates from other instances."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self._handle_presence_update(data)
                    except Exception as e:
                        logger.error(f"Failed to handle presence update: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Presence listener error: {e}")
    
    async def _handle_presence_update(self, data: Dict[str, Any]):
        """Handle presence update from another instance."""
        event_type = data.get("type")
        
        if event_type == "online":
            # Update local presence cache
            pass
        elif event_type == "offline":
            # Remove from local cache
            pass
        elif event_type == "cursor":
            # Update cursor position
            pass
    
    # ==================== Public API ====================
    
    async def set_presence(
        self,
        organization_id: str,
        user_id: str,
        user_info: Optional[Dict[str, Any]] = None,
        status: str = "online",
    ) -> PresenceData:
        """
        Set user presence status.
        
        Args:
            organization_id: Organization ID
            user_id: User ID
            user_info: Optional user info (name, color)
            status: Presence status (online, idle, away, offline)
        """
        presence = PresenceData(
            user_id=user_id,
            user_name=user_info.get("full_name", f"User {user_id[:8]}") if user_info else f"User {user_id[:8]}",
            user_color=user_info.get("color", f"#{hash(user_id) % 0xFFFFFF:06x}") if user_info else f"#{hash(user_id) % 0xFFFFFF:06x}",
            organization_id=organization_id,
            status=status,
        )
        
        # Store in Redis
        key = f"{self.PRESENCE_KEY_PREFIX}{organization_id}:{user_id}"
        await self.redis.setex(
            key,
            self.PRESENCE_TTL,
            json.dumps(presence.to_dict())
        )
        
        # Add to organization presence set
        await self.redis.sadd(f"{self.ORG_PRESENCE_SET}{organization_id}", user_id)
        
        # Publish update
        await self.redis.publish(
            self.PRESENCE_CHANNEL,
            json.dumps({
                "type": "online" if status != "offline" else "offline",
                "presence": presence.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        )
        
        return presence
    
    async def get_presence(
        self,
        organization_id: str,
        user_id: str
    ) -> Optional[PresenceData]:
        """Get presence data for a user."""
        key = f"{self.PRESENCE_KEY_PREFIX}{organization_id}:{user_id}"
        data = await self.redis.get(key)
        
        if not data:
            return None
        
        try:
            return PresenceData.from_dict(json.loads(data))
        except Exception:
            return None
    
    async def get_org_presence(
        self,
        organization_id: str,
        status_filter: Optional[str] = None
    ) -> List[PresenceData]:
        """Get all presence data for an organization."""
        user_ids = await self.redis.smembers(f"{self.ORG_PRESENCE_SET}{organization_id}")
        
        results = []
        for user_id in user_ids:
            presence = await self.get_presence(organization_id, user_id)
            if presence:
                if status_filter is None or presence.status == status_filter:
                    results.append(presence)
        
        return results
    
    async def update_presence(
        self,
        organization_id: str,
        user_id: str,
        **updates
    ) -> Optional[PresenceData]:
        """Update presence fields."""
        presence = await self.get_presence(organization_id, user_id)
        if not presence:
            return None
        
        for key, value in updates.items():
            if hasattr(presence, key):
                setattr(presence, key, value)
        
        presence.last_active = datetime.now(timezone.utc)
        
        key = f"{self.PRESENCE_KEY_PREFIX}{organization_id}:{user_id}"
        await self.redis.setex(key, self.PRESENCE_TTL, json.dumps(presence.to_dict()))
        
        # Publish update
        await self.redis.publish(
            self.PRESENCE_CHANNEL,
            json.dumps({
                "type": "update",
                "presence": presence.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        )
        
        return presence
    
    async def update_cursor(
        self,
        organization_id: str,
        user_id: str,
        cursor: Optional[Dict[str, float]] = None,
        selection: Optional[Dict[str, int]] = None,
    ) -> Optional[PresenceData]:
        """Update cursor and selection position."""
        return await self.update_presence(organization_id, user_id, cursor=cursor, selection=selection)
    
    async def set_idle(self, organization_id: str, user_id: str) -> Optional[PresenceData]:
        """Mark user as idle."""
        return await self.update_presence(organization_id, user_id, status="idle")
    
    async def set_away(self, organization_id: str, user_id: str) -> Optional[PresenceData]:
        """Mark user as away."""
        return await self.update_presence(organization_id, user_id, status="away")
    
    async def go_offline(
        self,
        organization_id: str,
        user_id: str,
        connection_id: Optional[str] = None
    ) -> bool:
        """Mark user as offline."""
        presence = await self.get_presence(organization_id, user_id)
        if not presence:
            return False
        
        presence.status = "offline"
        presence.last_active = datetime.now(timezone.utc)
        
        key = f"{self.PRESENCE_KEY_PREFIX}{organization_id}:{user_id}"
        await self.redis.setex(key, self.PRESENCE_TTL, json.dumps(presence.to_dict()))
        
        # Remove from org presence set after TTL
        await asyncio.sleep(self.PRESENCE_TTL)
        await self.redis.srem(f"{self.ORG_PRESENCE_SET}{organization_id}", user_id)
        
        # Publish offline event
        await self.redis.publish(
            self.PRESENCE_CHANNEL,
            json.dumps({
                "type": "offline",
                "user_id": user_id,
                "organization_id": organization_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        )
        
        return True
    
    # ==================== Connection Management ====================
    
    async def register_connection(
        self,
        connection_id: str,
        user_id: str,
        user_name: str,
        organization_id: str,
        user_color: str = "#3B82F6",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ConnectionInfo:
        """Register a new WebSocket connection."""
        conn = ConnectionInfo(
            connection_id=connection_id,
            user_id=user_id,
            user_name=user_name,
            organization_id=organization_id,
            user_color=user_color,
            metadata=metadata or {},
        )
        
        # Store connection
        key = f"{self.CONNECTION_KEY_PREFIX}{connection_id}"
        await self.redis.setex(
            key,
            self.CONNECTION_TTL,
            json.dumps({
                "connection_id": connection_id,
                "user_id": user_id,
                "user_name": user_name,
                "organization_id": organization_id,
                "user_color": connection.user_color,
                "connected_at": connection.connected_at.isoformat(),
                "last_ping": connection.last_ping.isoformat(),
                "metadata": metadata or {},
            })
        )
        
        # Track user/org connections
        await self.redis.sadd(f"{self.USER_CONNECTIONS_SET}{user_id}", connection_id)
        await self.redis.sadd(f"{self.ORG_CONNECTIONS_SET}{organization_id}", connection_id)
        await self.redis.sadd(f"{self.ORG_PRESENCE_SET}{organization_id}", user_id)
        
        # Set presence
        await self.set_presence(
            organization_id=organization_id,
            user_id=user_id,
            user_info={"full_name": user_name, "color": user_color},
            status="online",
        )
        
        return connection
    
    async def unregister_connection(self, connection_id: str) -> bool:
        """Unregister a WebSocket connection."""
        key = f"{self.CONNECTION_KEY_PREFIX}{connection_id}"
        
        conn_data = await self.redis.get(key)
        if not conn_data:
            return False
        
        try:
            conn_info = json.loads(conn_data)
            user_id = conn_info.get("user_id")
            org_id = conn_info.get("organization_id")
            
            # Remove from sets
            await self.redis.srem(f"{self.USER_CONNECTIONS_SET}{user_id}", connection_id)
            await self.redis.srem(f"{self.ORG_CONNECTIONS_SET}{org_id}", connection_id)
            
            # Check if user has other connections
            remaining = await self.redis.scard(f"{self.USER_CONNECTIONS_SET}{user_id}")
            if remaining == 0:
                # User has no more connections - mark offline
                await self.go_offline(org_id, user_id)
            
            # Delete connection key
            await self.redis.delete(key)
            
            return True
        except Exception as e:
            logger.error(f"Failed to unregister connection: {e}")
            return False
    
    async def update_connection_ping(self, connection_id: str):
        """Update last ping time for connection."""
        key = f"{self.CONNECTION_KEY_PREFIX}{connection_id}"
        conn_data = await self.redis.get(key)
        
        if conn_data:
            try:
                conn_info = json.loads(conn_data)
                conn_info["last_ping"] = datetime.now(timezone.utc).isoformat()
                await self.redis.setex(key, self.CONNECTION_TTL, json.dumps(conn_info))
            except Exception:
                pass
    
    async def get_connection(self, connection_id: str) -> Optional[ConnectionInfo]:
        """Get connection info."""
        key = f"{self.CONNECTION_KEY_PREFIX}{connection_id}"
        data = await self.redis.get(key)
        
        if not data:
            return None
        
        try:
            data = json.loads(data)
            return ConnectionInfo(
                connection_id=data["connection_id"],
                user_id=data["user_id"],
                user_name=data["user_name"],
                user_color=data["user_color"],
                organization_id=data["organization_id"],
                connected_at=datetime.fromisoformat(data["connected_at"]),
                last_ping=datetime.fromisoformat(data["last_ping"]),
                metadata=data.get("metadata", {}),
                subscribed_rooms=set(data.get("subscribed_rooms", [])),
            )
        except Exception:
            return None
    
    async def get_user_connections(self, user_id: str) -> List[ConnectionInfo]:
        """Get all connections for a user."""
        conn_ids = await self.redis.smembers(f"{self.USER_CONNECTIONS_SET}{user_id}")
        
        connections = []
        for conn_id in conn_ids:
            conn = await self.get_connection(conn_id)
            if conn:
                connections.append(conn)
        return connections
    
    async def get_org_connections(self, org_id: str) -> List[ConnectionInfo]:
        """Get all connections in an organization."""
        conn_ids = await self.redis.smembers(f"{self.ORG_CONNECTIONS_SET}{org_id}")
        
        connections = []
        for conn_id in conn_ids:
            conn = await self.get_connection(conn_id)
            if conn:
                connections.append(conn)
        return connections
    
    # ==================== Presence Queries ====================
    
    async def get_online_users(self, organization_id: str) -> List[PresenceData]:
        """Get all online users in an organization."""
        return await self.get_org_presence(organization_id, status_filter="online")
    
    async def get_user_status(self, organization_id: str, user_id: str) -> str:
        """Get user's current status."""
        presence = await self.get_presence(organization_id, user_id)
        return presence.status if presence else "offline"
    
    async def is_user_online(self, organization_id: str, user_id: str) -> bool:
        """Check if user is online."""
        presence = await self.get_presence(organization_id, user_id)
        return presence is not None and presence.status == "online"
    
    async def get_online_count(self, organization_id: str) -> int:
        """Get count of online users in organization."""
        user_ids = await self.redis.smembers(f"{self.ORG_PRESENCE_SET}{organization_id}")
        count = 0
        for user_id in user_ids:
            if await self.is_user_online(organization_id, user_id):
                count += 1
        return count

import asyncio
import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import redis.asyncio as redis

logger = logging.getLogger("vcos.realtime.presence")

# Re-import missing imports
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

import redis.asyncio as redis

logger = logging.getLogger("vcos.realtime.presence")


@dataclass
class PresenceData:
    """User presence data."""
    user_id: str
    user_name: str
    user_color: str
    organization_id: str
    status: str = "online"  # online, idle, away, offline
    cursor: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, int]] = None
    status_message: str = ""
    last_active: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "user_color": self.user_color,
            "organization_id": self.organization_id,
            "status": self.status,
            "cursor": self.cursor,
            "selection": self.selection,
            "status_message": self.status_message,
            "last_active": self.last_active.isoformat(),
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PresenceData":
        return cls(
            user_id=data["user_id"],
            user_name=data["user_name"],
            user_color=data["user_color"],
            organization_id=data["organization_id"],
            status=data.get("status", "online"),
            cursor=data.get("cursor"),
            selection=data.get("selection"),
            status_message=data.get("status_message", ""),
            last_active=datetime.fromisoformat(data["last_active"]),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ConnectionInfo:
    """WebSocket connection info for presence."""
    connection_id: str
    user_id: str
    user_name: str
    user_color: str
    organization_id: str
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_ping: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)
    subscribed_rooms: Set[str] = field(default_factory=set)
    cursor_position: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, int]] = None


class PresenceService:
    """
    Redis-backed presence service for real-time user presence.
    
    Features:
    - TTL-based presence expiration
    - Organization-wide presence queries
    - Real-time presence updates via pub/sub
    - Connection tracking
    - Heartbeat/heartbeat monitoring
    """
    
    # Redis key prefixes
    PRESENCE_KEY_PREFIX = "vcos:presence:"
    CONNECTION_KEY_PREFIX = "vcos:connection:"
    ORG_PRESENCE_SET = "vcos:org_presence:"
    USER_CONNECTIONS_SET = "vcos:user_connections:"
    ORG_CONNECTIONS_SET = "vcos:org_connections:"
    HEARTBEAT_CHANNEL = "vcos:heartbeat"
    PRESENCE_CHANNEL = "vcos:presence_updates"
    
    # TTL settings (seconds)
    PRESENCE_TTL = 300  # 5 minutes
    CONNECTION_TTL = 3600  # 1 hour
    HEARTBEAT_INTERVAL = 30  # 30 seconds
    
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self._running = False
        self._heartbeat_task = None
        self._listener_task = None
        self._pubsub = None
    
    async def initialize(self):
        """Initialize presence service."""
        self._running = True
        
        # Start heartbeat task
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        
        # Subscribe to presence channel
        self._pubsub = self.redis.pubsub()
        await self._pubsub.subscribe(self.PRESENCE_CHANNEL)
        self._listener_task = asyncio.create_task(self._listen_for_updates())
        
        logger.info("Presence service initialized")
    
    async def close(self):
        """Close presence service."""
        self._running = False
        
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
        
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass
        
        if self._pubsub:
            await self._pubsub.unsubscribe(self.PRESENCE_CHANNEL)
            await self._pubsub.close()
    
    async def _heartbeat_loop(self):
        """Periodic heartbeat to clean up stale connections."""
        while True:
            try:
                await asyncio.sleep(self.HEARTBEAT_INTERVAL)
                
                # Scan for expired connections
                await self._cleanup_expired()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
    
    async def _cleanup_expired(self):
        """Remove expired connections and presence data."""
        try:
            # Scan for expired connection keys
            pattern = f"{self.CONNECTION_KEY_PREFIX}*"
            cursor = 0
            while True:
                cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
                
                if keys:
                    # Check TTL for each key
                    pipe = self.redis.pipeline()
                    for key in keys:
                        pipe.ttl(key)
                    ttls = await pipe.execute()
                    
                    expired_keys = [key for key, ttl in zip(keys, ttls) if ttl <= 0]
                    
                    if expired_keys:
                        # Clean up expired connections
                        await self._cleanup_connections(expired_keys)
                
                if cursor == 0:
                    break
                    
        except Exception as e:
            logger.error(f"Failed to cleanup expired: {e}")
    
    async def _cleanup_connections(self, expired_keys: List[str]):
        """Clean up expired connection data."""
        try:
            pipe = self.redis.pipeline()
            
            for key in expired_keys:
                # Get connection data before deleting
                conn_data = await self.redis.get(key)
                if conn_data:
                    try:
                        conn_info = json.loads(conn_data)
                        user_id = conn_info.get("user_id")
                        org_id = conn_info.get("organization_id")
                        conn_id = conn_info.get("connection_id")
                        
                        if user_id and org_id:
                            # Remove from user/org sets
                            await self.redis.srem(f"{self.USER_CONNECTIONS_SET}{user_id}", conn_id)
                            await self.redis.srem(f"{self.ORG_CONNECTIONS_SET}{org_id}", conn_id)
                            await self.redis.srem(f"{self.ORG_PRESENCE_SET}{org_id}", user_id)
                            
                            # Publish offline event
                            await self.redis.publish(
                                self.PRESENCE_CHANNEL,
                                json.dumps({
                                    "type": "offline",
                                    "user_id": user_id,
                                    "organization_id": org_id,
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                })
                            )
                    except Exception:
                        pass
                
                pipe.delete(key)
            
            await pipe.execute()
            
        except Exception as e:
            logger.error(f"Failed to cleanup connections: {e}")
    
    async def _listen_for_updates(self):
        """Listen for presence updates from other instances."""
        try:
            async for message in self._pubsub.listen():
                if message["type"] == "message":
                    try:
                        data = json.loads(message["data"])
                        await self._handle_presence_update(data)
                    except Exception as e:
                        logger.error(f"Failed to handle presence update: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Presence listener error: {e}")
    
    async def _handle_presence_update(self, data: Dict[str, Any]):
        """Handle presence update from another instance."""
        event_type = data.get("type")
        
        if event_type == "online":
            # Update local presence cache
            pass
        elif event_type == "offline":
            # Remove from local cache
            pass
        elif event_type == "cursor":
            # Update cursor position
            pass
    
    # ==================== Public API ====================
    
    async def set_presence(
        self,
        organization_id: str,
        user_id: str,
        user_info: Optional[Dict[str, Any]] = None,
        status: str = "online",
    ) -> "PresenceData":
        """
        Set user presence status.
        
        Args:
            organization_id: Organization ID
            user_id: User ID
            user_info: Optional user info (name, color)
            status: Presence status (online, idle, away, offline)
        """
        presence = PresenceData(
            user_id=user_id,
            user_name=user_info.get("full_name", f"User {user_id[:8]}") if user_info else f"User {user_id[:8]}",
            user_color=user_info.get("color", f"#{hash(user_id) % 0xFFFFFF:06x}") if user_info else f"#{hash(user_id) % 0xFFFFFF:06x}",
            organization_id=organization_id,
            status=status,
        )
        
        # Store in Redis
        key = f"{self.PRESENCE_KEY_PREFIX}{organization_id}:{user_id}"
        await self.redis.setex(
            key,
            self.PRESENCE_TTL,
            json.dumps(presence.to_dict())
        )
        
        # Add to organization presence set
        await self.redis.sadd(f"{self.ORG_PRESENCE_SET}{organization_id}", user_id)
        
        # Publish update
        await self.redis.publish(
            self.PRESENCE_CHANNEL,
            json.dumps({
                "type": "online" if status != "offline" else "offline",
                "presence": presence.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        )
        
        return presence
    
    async def get_presence(
        self,
        organization_id: str,
        user_id: str
    ) -> Optional["PresenceData"]:
        """Get presence data for a user."""
        key = f"{self.PRESENCE_KEY_PREFIX}{organization_id}:{user_id}"
        data = await self.redis.get(key)
        
        if not data:
            return None
        
        try:
            return PresenceData.from_dict(json.loads(data))
        except Exception:
            return None
    
    async def get_org_presence(
        self,
        organization_id: str,
        status_filter: Optional[str] = None
    ) -> List["PresenceData"]:
        """Get all presence data for an organization."""
        user_ids = await self.redis.smembers(f"{self.ORG_PRESENCE_SET}{organization_id}")
        
        results = []
        for user_id in user_ids:
            presence = await self.get_presence(organization_id, user_id)
            if presence:
                if status_filter is None or presence.status == status_filter:
                    results.append(presence)
        
        return results
    
    async def update_presence(
        self,
        organization_id: str,
        user_id: str,
        **updates
    ) -> Optional["PresenceData"]:
        """Update presence fields."""
        presence = await self.get_presence(organization_id, user_id)
        if not presence:
            return None
        
        for key, value in updates.items():
            if hasattr(presence, key):
                setattr(presence, key, value)
        
        presence.last_active = datetime.now(timezone.utc)
        
        key = f"{self.PRESENCE_KEY_PREFIX}{organization_id}:{user_id}"
        await self.redis.setex(key, self.PRESENCE_TTL, json.dumps(presence.to_dict()))
        
        # Publish update
        await self.redis.publish(
            self.PRESENCE_CHANNEL,
            json.dumps({
                "type": "update",
                "presence": presence.to_dict(),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        )
        
        return presence
    
    async def update_cursor(
        self,
        organization_id: str,
        user_id: str,
        cursor: Optional[Dict[str, float]] = None,
        selection: Optional[Dict[str, int]] = None,
    ) -> Optional["PresenceData"]:
        """Update cursor and selection position."""
        return await self.update_presence(organization_id, user_id, cursor=cursor, selection=selection)
    
    async def set_idle(self, organization_id: str, user_id: str) -> Optional["PresenceData"]:
        """Mark user as idle."""
        return await self.update_presence(organization_id, user_id, status="idle")
    
    async def set_away(self, organization_id: str, user_id: str) -> Optional["PresenceData"]:
        """Mark user as away."""
        return await self.update_presence(organization_id, user_id, status="away")
    
    async def go_offline(
        self,
        organization_id: str,
        user_id: str,
        connection_id: Optional[str] = None
    ) -> bool:
        """Mark user as offline."""
        presence = await self.get_presence(organization_id, user_id)
        if not presence:
            return False
        
        presence.status = "offline"
        presence.last_active = datetime.now(timezone.utc)
        
        key = f"{self.PRESENCE_KEY_PREFIX}{organization_id}:{user_id}"
        await self.redis.setex(key, self.PRESENCE_TTL, json.dumps(presence.to_dict()))
        
        # Remove from org presence set after TTL
        await asyncio.sleep(self.PRESENCE_TTL)
        await self.redis.srem(f"{self.ORG_PRESENCE_SET}{organization_id}", user_id)
        
        # Publish offline event
        await self.redis.publish(
            self.PRESENCE_CHANNEL,
            json.dumps({
                "type": "offline",
                "user_id": user_id,
                "organization_id": organization_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        )
        
        return True
    
    # ==================== Connection Management ====================
    
    async def register_connection(
        self,
        connection_id: str,
        user_id: str,
        user_name: str,
        organization_id: str,
        user_color: str = "#3B82F6",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "ConnectionInfo":
        """Register a new WebSocket connection."""
        conn = ConnectionInfo(
            connection_id=connection_id,
            user_id=user_id,
            user_name=user_name,
            organization_id=organization_id,
            user_color=user_color,
            metadata=metadata or {},
        )
        
        # Store connection
        key = f"{self.CONNECTION_KEY_PREFIX}{connection_id}"
        await self.redis.setex(
            key,
            self.CONNECTION_TTL,
            json.dumps({
                "connection_id": connection_id,
                "user_id": user_id,
                "user_name": user_name,
                "organization_id": organization_id,
                "user_color": conn.user_color,
                "connected_at": conn.connected_at.isoformat(),
                "last_ping": conn.last_ping.isoformat(),
                "metadata": metadata or {},
            })
        )
        
        # Track user/org connections
        await self.redis.sadd(f"{self.USER_CONNECTIONS_SET}{user_id}", connection_id)
        await self.redis.sadd(f"{self.ORG_CONNECTIONS_SET}{organization_id}", connection_id)
        await self.redis.sadd(f"{self.ORG_PRESENCE_SET}{organization_id}", user_id)
        
        # Set presence
        await self.set_presence(
            organization_id=organization_id,
            user_id=user_id,
            user_info={"full_name": user_name, "color": user_color},
            status="online",
        )
        
        return conn
    
    async def unregister_connection(self, connection_id: str) -> bool:
        """Unregister a WebSocket connection."""
        key = f"{self.CONNECTION_KEY_PREFIX}{connection_id}"
        
        conn_data = await self.redis.get(key)
        if not conn_data:
            return False
        
        try:
            conn_info = json.loads(conn_data)
            user_id = conn_info.get("user_id")
            org_id = conn_info.get("organization_id")
            
            # Remove from user/org sets
            await self.redis.srem(f"{self.USER_CONNECTIONS_SET}{user_id}", connection_id)
            await self.redis.srem(f"{self.ORG_CONNECTIONS_SET}{org_id}", connection_id)
            
            # Check if user has other connections
            remaining = await self.redis.scard(f"{self.USER_CONNECTIONS_SET}{user_id}")
            if remaining == 0:
                # User has no more connections - mark offline
                await self.go_offline(org_id, user_id)
            
            # Delete connection key
            await self.redis.delete(key)
            
            return True
        except Exception as e:
            logger.error(f"Failed to unregister connection: {e}")
            return False
    
    async def update_connection_ping(self, connection_id: str):
        """Update last ping time for connection."""
        key = f"{self.CONNECTION_KEY_PREFIX}{connection_id}"
        conn_data = await self.redis.get(key)
        
        if conn_data:
            try:
                conn_info = json.loads(conn_data)
                conn_info["last_ping"] = datetime.now(timezone.utc).isoformat()
                await self.redis.setex(key, self.CONNECTION_TTL, json.dumps(conn_info))
            except Exception:
                pass
    
    async def get_connection(self, connection_id: str) -> Optional[ConnectionInfo]:
        """Get connection info."""
        key = f"{self.CONNECTION_KEY_PREFIX}{connection_id}"
        data = await self.redis.get(key)
        
        if not data:
            return None
        
        try:
            conn_info = json.loads(data)
            return ConnectionInfo(
                connection_id=conn_info["connection_id"],
                user_id=conn_info["user_id"],
                user_name=conn_info["user_name"],
                user_color=conn_info["user_color"],
                organization_id=conn_info["organization_id"],
                connected_at=datetime.fromisoformat(conn_info["connected_at"]),
                last_ping=datetime.fromisoformat(conn_info["last_ping"]),
                metadata=conn_info.get("metadata", {}),
                subscribed_rooms=set(conn_info.get("subscribed_rooms", [])),
            )
        except Exception:
            return None
    
    async def get_user_connections(self, user_id: str) -> List[ConnectionInfo]:
        """Get all connections for a user."""
        conn_ids = await self.redis.smembers(f"{self.USER_CONNECTIONS_SET}{user_id}")
        
        connections = []
        for conn_id in conn_ids:
            conn = await self.get_connection(conn_id)
            if conn:
                connections.append(conn)
        return connections
    
    async def get_org_connections(self, org_id: str) -> List[ConnectionInfo]:
        """Get all connections in an organization."""
        conn_ids = await self.redis.smembers(f"{self.ORG_CONNECTIONS_SET}{org_id}")
        
        connections = []
        for conn_id in conn_ids:
            conn = await self.get_connection(conn_id)
            if conn:
                connections.append(conn)
        return connections
    
    # ==================== Presence Queries ====================
    
    async def get_online_users(self, organization_id: str) -> List[PresenceData]:
        """Get all online users in an organization."""
        return await self.get_org_presence(organization_id, status_filter="online")
    
    async def get_user_status(self, organization_id: str, user_id: str) -> str:
        """Get user's current status."""
        presence = await self.get_presence(organization_id, user_id)
        return presence.status if presence else "offline"
    
    async def is_user_online(self, organization_id: str, user_id: str) -> bool:
        """Check if user is online."""
        presence = await self.get_presence(organization_id, user_id)
        return presence is not None and presence.status == "online"
    
    async def get_online_count(self, organization_id: str) -> int:
        """Get count of online users in organization."""
        user_ids = await self.redis.smembers(f"{self.ORG_PRESENCE_SET}{organization_id}")
        count = 0
        for user_id in user_ids:
            if await self.is_user_online(organization_id, user_id):
                count += 1
        return count