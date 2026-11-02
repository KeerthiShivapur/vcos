"""Presence Service with Redis backend and in-memory fallback."""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from uuid import uuid4

logger = logging.getLogger(__name__)

try:
    import redis.asyncio as redis
    from redis.asyncio import Redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None
    Redis = None


@dataclass
class PresenceData:
    """User presence data."""
    user_id: str
    user_name: str
    user_color: str
    organization_id: str
    cursor: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, int]] = None
    status: str = "online"  # online, idle, away, offline
    last_active: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectionInfo:
    """WebSocket connection info."""
    connection_id: str
    user_id: str
    organization_id: str
    connected_at: float
    last_ping: float
    metadata: Dict[str, Any] = field(default_factory=dict)


class PresenceService:
    """Presence service with Redis backend and in-memory fallback."""
    
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
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0", use_redis: bool = True):
        self.redis_url = redis_url
        self._redis = None
        self._pubsub = None
        self._running = False
        self._heartbeat_task = None
        self._listener_task = None
        self._use_redis = use_redis and REDIS_AVAILABLE and redis_url is not None
        
        # In-memory fallback storage
        self._memory_presence: Dict[str, PresenceData] = {}
        self._memory_connections: Dict[str, ConnectionInfo] = {}
        self._memory_org_presence: Dict[str, Set[str]] = {}
        self._memory_org_connections: Dict[str, Set[str]] = {}
        self._memory_user_connections: Dict[str, Set[str]] = {}
        self._running = False
        self._heartbeat_task = None
        self._listener_task = None
        
    async def initialize(self):
        """Initialize Redis connection or use in-memory fallback."""
        if self._use_redis and REDIS_AVAILABLE:
            try:
                self._redis = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=50,
                )
                await self._redis.ping()
                logger.info("Presence Service initialized with Redis backend")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis, using in-memory fallback: {e}")
                self._redis = None
        
        if not self._redis:
            logger.info("Presence Service initialized with in-memory fallback")
        
        self._running = True
        logger.info("Presence Service initialized")
    
    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()
        logger.info("Presence Service closed")
    
    # =========================================================================
    # Connection Management
    # =========================================================================
    
    def _get_redis(self):
        """Get Redis client if available."""
        return self._redis
    
    async def register_connection(
        self,
        connection_id: str,
        user_id: str,
        organization_id: str,
        metadata: Dict[str, Any] = None,
    ):
        """Register a new WebSocket connection."""
        now = time.time()
        conn = ConnectionInfo(
            connection_id=connection_id,
            user_id=user_id,
            organization_id=organization_id,
            connected_at=time.time(),
            last_ping=time.time(),
            metadata=metadata or {},
        )
        
        if self._redis:
            # Redis backend
            conn_key = f"vcos:connection:{connection_id}"
            await self._redis.setex(
                f"vcos:connection:{connection_id}",
                3600,
                json.dumps(asdict(conn)),
            )
            await self._redis.sadd(f"vcos:org_connections:{organization_id}", connection_id)
            await self._redis.sadd(f"vcos:user_connections:{user_id}", connection_id)
        else:
            # In-memory fallback
            self._memory_connections[connection_id] = ConnectionInfo(
                connection_id=connection_id,
                user_id=user_id,
                organization_id=organization_id,
                connected_at=time.time(),
                last_ping=time.time(),
                metadata=metadata or {},
            )
            if organization_id not in self._memory_org_connections:
                self._memory_org_connections[organization_id] = set()
            self._memory_org_connections[organization_id].add(connection_id)
            
            if user_id not in self._memory_user_connections:
                self._memory_user_connections[user_id] = set()
            self._memory_user_connections[user_id].add(connection_id)
        
        logger.info(f"Registered connection for user in org {organization_id}")
    
    async def unregister_connection(self, connection_id: str) -> bool:
        """Unregister a WebSocket connection."""
        if self._redis:
            # Redis backend - would need to fetch connection data first
            pass
        else:
            if connection_id not in self._memory_connections:
                return False
            conn = self._memory_connections.pop(connection_id)
            organization_id = conn.organization_id
            user_id = conn.user_id
            
            if organization_id in self._memory_org_connections:
                self._memory_org_connections[organization_id].discard(connection_id)
            if conn.user_id in self._memory_user_connections:
                self._memory_user_connections[user_id].discard(connection_id)
            return True
        return False
    
    async def get_connection(self, connection_id: str):
        if self._redis:
            pass
        else:
            return self._memory_connections.get(connection_id)
        return None
    
    async def get_organization_connections(self, organization_id: str):
        if self._redis:
            pass
        else:
            return list(self._memory_org_connections.get(organization_id, set()))
        return []
    
    # =========================================================================
    # Presence Management
    # =========================================================================
    
    async def set_presence(
        self,
        user_id: str,
        organization_id: str,
        user_name: str,
        user_color: str,
        cursor: Optional[Dict[str, float]] = None,
        selection: Optional[Dict[str, int]] = None,
        status: str = "online",
        metadata: Dict[str, Any] = None,
    ):
        presence = PresenceData(
            user_id=user_id,
            user_name=user_name,
            user_color=user_color,
            organization_id=organization_id,
            cursor=cursor,
            selection=selection,
            status=status,
            last_active=time.time(),
            metadata=metadata or {},
        )
        
        if self._redis:
            await self._redis.setex(
                f"vcos:presence:{organization_id}:{user_id}",
                300,
                json.dumps(asdict(presence)),
            )
            await self._redis.sadd(f"vcos:org_presence:{organization_id}", user_id)
        else:
            key = f"{organization_id}:{user_id}"
            self._memory_presence[key] = presence
            if organization_id not in self._memory_org_presence:
                self._memory_org_presence[organization_id] = set()
            self._memory_org_presence[organization_id].add(user_id)
        
        return presence
    
    async def get_presence(self, user_id: str, organization_id: str):
        if self._redis:
            return None
        else:
            key = f"{organization_id}:{user_id}"
            return self._memory_presence.get(key)
    
    async def get_organization_presence(self, organization_id: str):
        if self._redis:
            return []
        else:
            user_ids = self._memory_org_presence.get(organization_id, set())
            presences = []
            for user_id in user_ids:
                key = f"{organization_id}:{user_id}"
                if key in self._memory_presence:
                    presences.append(self._memory_presence[key])
            return presences
    
    async def remove_presence(self, user_id: str, organization_id: str) -> bool:
        if self._redis:
            pass
        else:
            key = f"{organization_id}:{user_id}"
            if key in self._memory_presence:
                del self._memory_presence[key]
            if organization_id in self._memory_org_presence:
                self._memory_org_presence[organization_id].discard(user_id)
            return True
        return False
    
    async def update_cursor(self, user_id: str, organization_id: str, cursor: Dict[str, float]) -> bool:
        presence = await self.get_presence(user_id, organization_id)
        if not presence:
            return False
        presence.cursor = cursor
        presence.last_active = time.time()
        await self.set_presence(
            user_id, organization_id, presence.user_name, presence.user_color,
            cursor=cursor, selection=presence.selection, status=presence.status
        )
        return True
    
    async def update_selection(self, user_id: str, organization_id: str, selection: Dict[str, int]) -> bool:
        presence = await self.get_presence(user_id, organization_id)
        if not presence:
            return False
        presence.selection = selection
        presence.last_active = time.time()
        await self.set_presence(
            user_id, organization_id, presence.user_name, presence.user_color,
            cursor=presence.cursor, selection=selection, status=presence.status
        )
        return True
    
    async def update_status(self, user_id: str, organization_id: str, status: str) -> bool:
        presence = await self.get_presence(user_id, organization_id)
        if not presence:
            return False
        presence.status = status
        presence.last_active = time.time()
        await self.set_presence(
            user_id, organization_id, presence.user_name, presence.user_color,
            cursor=presence.cursor, selection=presence.selection, status=status
        )
        return True
    
    async def get_presence(self, user_id: str, organization_id: str):
        if self._redis:
            return None
        else:
            key = f"{organization_id}:{user_id}"
            return self._memory_presence.get(key)
    
    async def get_organization_presence(self, organization_id: str):
        if self._redis:
            return []
        else:
            user_ids = self._memory_org_presence.get(organization_id, set())
            presences = []
            for user_id in user_ids:
                key = f"{organization_id}:{user_id}"
                if key in self._memory_presence:
                    presences.append(self._memory_presence[key])
            return presences
    
    async def remove_presence(self, user_id: str, organization_id: str) -> bool:
        if self._redis:
            return False
        else:
            key = f"{organization_id}:{user_id}"
            if key in self._memory_presence:
                del self._memory_presence[key]
            if organization_id in self._memory_org_presence:
                self._memory_org_presence[organization_id].discard(user_id)
            return True
    
    async def update_cursor(self, user_id: str, organization_id: str, cursor: Dict[str, float]) -> bool:
        presence = await self.get_presence(user_id, organization_id)
        if not presence:
            return False
        presence.cursor = cursor
        presence.last_active = time.time()
        await self.set_presence(
            user_id, organization_id, presence.user_name, presence.user_color,
            cursor=cursor, selection=presence.selection, status=presence.status
        )
        return True
    
    async def update_selection(self, user_id: str, organization_id: str, selection: Dict[str, int]) -> bool:
        presence = await self.get_presence(user_id, organization_id)
        if not presence:
            return False
        presence.selection = selection
        presence.last_active = time.time()
        await self.set_presence(
            user_id, organization_id, presence.user_name, presence.user_color,
            cursor=presence.cursor, selection=selection, status=presence.status
        )
        return True
    
    async def update_status(self, user_id: str, organization_id: str, status: str) -> bool:
        presence = await self.get_presence(user_id, organization_id)
        if not presence:
            return False
        presence.status = status
        presence.last_active = time.time()
        await self.set_presence(
            user_id, organization_id, presence.user_name, presence.user_color,
            cursor=presence.cursor, selection=presence.selection, status=status
        )
        return True
    
    async def get_organization_presence(self, organization_id: str):
        if self._redis:
            return []
        else:
            user_ids = self._memory_org_presence.get(organization_id, set())
            presences = []
            for user_id in user_ids:
                key = f"{organization_id}:{user_id}"
                if key in self._memory_presence:
                    presences.append(self._memory_presence[key])
            return presences
    
    async def remove_presence(self, user_id: str, organization_id: str) -> bool:
        if self._redis:
            return False
        else:
            key = f"{organization_id}:{user_id}"
            if key in self._memory_presence:
                del self._memory_presence[key]
            if organization_id in self._memory_org_presence:
                self._memory_org_presence[organization_id].discard(user_id)
            return True
    
    async def get_organization_connections(self, organization_id: str):
        if self._redis:
            return []
        else:
            return list(self._memory_org_connections.get(organization_id, set()))
    
    async def get_organization_presence(self, organization_id: str):
        if self._redis:
            return []
        else:
            user_ids = self._memory_org_presence.get(organization_id, set())
            presences = []
            for user_id in user_ids:
                key = f"{organization_id}:{user_id}"
                if key in self._memory_presence:
                    presences.append(self._memory_presence[key])
            return presences
    
    async def remove_presence(self, user_id: str, organization_id: str) -> bool:
        if self._redis:
            return False
        else:
            key = f"{organization_id}:{user_id}"
            if key in self._memory_presence:
                del self._memory_presence[key]
            if organization_id in self._memory_org_presence:
                self._memory_org_presence[organization_id].discard(user_id)
            return True
    
    async def get_organization_connections(self, organization_id: str):
        if self._redis:
            return []
        else:
            return list(self._memory_org_connections.get(organization_id, set()))
    
    async def get_stats(self, organization_id: str):
        presences = await self.get_organization_presence(organization_id)
        connections = await self.get_organization_connections(organization_id)
        
        online_count = sum(1 for p in presences if p.status == "online")
        idle_count = sum(1 for p in presences if p.status == "idle")
        away_count = sum(1 for p in presences if p.status == "away")
        
        return {
            "organization_id": organization_id,
            "total_presences": len(presences),
            "total_connections": len(connections),
            "online": online_count,
            "idle": idle_count,
            "away": away_count,
            "offline": len(presences) - online_count - idle_count - away_count,
        }


# Global presence service instance
_presence_service: Optional[PresenceService] = None


def get_presence_service() -> PresenceService:
    """Get or create presence service singleton."""
    global _presence_service
    if _presence_service is None:
        _presence_service = PresenceService()
    return _presence_service


def init_presence_service(redis_url: str = "redis://localhost:6379/0", use_redis: bool = True) -> PresenceService:
    """Initialize presence service."""
    global _presence_service
    _presence_service = PresenceService(redis_url, use_redis)
    return _presence_service