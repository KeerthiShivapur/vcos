"""
Data models for WebSocket Gateway
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import time


@dataclass
class ConnectionInfo:
    """Connection information from client"""
    connection_id: str
    user_id: str
    organization_id: str
    resource_id: str
    connection_type: str  # crdt, signaling, presence
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)


class WebSocketMessage(BaseModel):
    """WebSocket message format"""
    type: str
    payload: Dict[str, Any] = Field(default_factory=dict)
    request_id: Optional[str] = None
    timestamp: float = Field(default_factory=time.time)


class CRDTOperation(BaseModel):
    """CRDT operation message"""
    document_id: str
    operation: Dict[str, Any]
    client_id: str
    timestamp: float = Field(default_factory=time.time)
    vector_clock: Dict[str, int] = Field(default_factory=dict)


class AwarenessUpdate(BaseModel):
    """Awareness update message"""
    document_id: str
    user_id: str
    user_name: str
    user_color: str
    cursor: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, int]] = None
    status: str = "online"


class SignalingMessage(BaseModel):
    """WebRTC signaling message"""
    call_id: str
    type: str  # offer, answer, ice_candidate, join, leave
    from_user: str
    to_user: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class PresenceUpdate(BaseModel):
    """Presence update message"""
    organization_id: str
    user_id: str
    user_name: str
    user_color: str
    status: str  # online, idle, away, offline
    cursor: Optional[Dict[str, float]] = None
    selection: Optional[Dict[str, int]] = None


class SyncRequest(BaseModel):
    """Sync request message"""
    document_id: str
    client_state: Optional[Dict[str, Any]] = None


class SyncResponse(BaseModel):
    """Sync response message"""
    document_id: str
    state: Dict[str, Any]
    version: int
    conflicts: List[Dict[str, Any]] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Error response"""
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ConnectionStats(BaseModel):
    """Connection statistics"""
    total: int = 0
    crdt: int = 0
    signaling: int = 0
    presence: int = 0
    resources: int = 0
    users: int = 0
    organizations: int = 0


class GatewayInfo(BaseModel):
    """Gateway information"""
    gateway_id: str
    region: str
    status: str
    started_at: float
    connections: int
    uptime: float
    version: str = "1.0.0"


# Redis key prefixes
class RedisKeys:
    CONNECTION = "vcos:ws:conn:"
    CONNECTIONS_BY_RESOURCE = "vcos:ws:resource:"
    CONNECTIONS_BY_USER = "vcos:ws:user:"
    CONNECTIONS_BY_ORG = "vcos:ws:org:"
    METRICS = "vcos:ws:metrics"
    RATE_LIMIT = "vcos:ws:ratelimit:"
    SLIDING_WINDOW = "vcos:ws:ratelimit:sw:"
    GATEWAY_REGISTRY = "vcos:ws:gateways"
    SESSION = "vcos:ws:session:"