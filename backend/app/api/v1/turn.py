"""
TURN/STUN Configuration API Routes.

Provides endpoints for:
- ICE server configuration
- TURN credentials generation
- Server health status
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.deps import get_current_user, get_db
from app.core.turn_manager import (
    TurnManager,
    TurnServer,
    TurnAuthType,
    get_turn_manager,
)
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(tags=["TURN/STUN Configuration"])

logger = logging.getLogger(__name__)


# ==================== Models ====================

class IceServerResponse(BaseModel):
    urls: List[str]
    username: Optional[str] = None
    credential: Optional[str] = None
    credentialType: str = "password"


class TurnCredentialsResponse(BaseModel):
    username: str
    password: str
    ttl: int
    urls: List[str]


class TurnServerConfig(BaseModel):
    host: str
    port: int = 3478
    tls_port: int = 5349
    realm: str = "vcos.io"
    auth_type: str = "ephemeral"
    static_username: Optional[str] = None
    static_password: Optional[str] = None
    shared_secret: Optional[str] = None
    cert_path: Optional[str] = None
    key_path: Optional[str] = None
    max_bps: Optional[int] = None
    max_connections: int = 1000


class TurnServerResponse(BaseModel):
    host: str
    port: int
    tls_port: int
    realm: str
    auth_type: str
    healthy: bool
    latency_ms: Optional[float] = None
    last_check: Optional[float] = None
    errors: List[str] = []


class TurnConfigTemplateResponse(BaseModel):
    coturn_config: str
    docker_compose: str
    kubernetes: str


# ==================== ICE Servers ====================

@router.get("/turn/ice-servers", response_model=List[IceServerResponse])
async def get_ice_servers(
    ttl: Optional[int] = Query(None, ge=300, le=604800),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get ICE server configuration for WebRTC.
    
    Returns list of STUN and TURN servers with credentials.
    """
    turn_manager = get_turn_manager()
    ice_servers = turn_manager.get_ice_servers_json(ttl)
    return ice_servers


@router.get("/turn/credentials", response_model=TurnCredentialsResponse)
async def get_turn_credentials(
    ttl: Optional[int] = Query(None, ge=300, le=604800),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get TURN credentials for current user.
    
    Generates ephemeral credentials per RFC 8656.
    """
    turn_manager = get_turn_manager()
    creds = await turn_manager.get_credentials_for_user(user.id, ttl)
    return TurnCredentialsResponse(
        username=creds.username,
        password=creds.password,
        ttl=creds.ttl,
        urls=creds.urls,
    )


# ==================== Server Management (Admin) ====================

@router.get("/turn/servers", response_model=List[TurnServerResponse])
async def list_turn_servers(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all configured TURN servers with health status (admin only)."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")

    turn_manager = get_turn_manager()
    stats = turn_manager.get_server_stats()

    servers = []
    for server in turn_manager.servers:
        server_stats = stats.get(server.host, {})
        servers.append(TurnServerResponse(
            host=server.host,
            port=server.port,
            tls_port=server.tls_port,
            realm=server.realm,
            auth_type=server.auth_type.value,
            healthy=server_stats.get("healthy", False),
            latency_ms=server_stats.get("latency_ms"),
            last_check=server_stats.get("last_check"),
            errors=server_stats.get("errors", []),
        ))

    return servers


@router.post("/turn/servers", response_model=TurnServerResponse)
async def add_turn_server(
    config: TurnServerConfig,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Add a new TURN server (admin only)."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")

    turn_manager = get_turn_manager()

    auth_type = TurnAuthType(config.auth_type)
    server = TurnServer(
        host=config.host,
        port=config.port,
        tls_port=config.tls_port,
        realm=config.realm,
        auth_type=auth_type,
        static_username=config.static_username,
        static_password=config.static_password,
        shared_secret=config.shared_secret,
        cert_path=config.cert_path,
        key_path=config.key_path,
        max_bps=config.max_bps,
        max_connections=config.max_connections,
    )

    await turn_manager.add_server(server)

    stats = turn_manager.get_server_stats().get(server.host, {})
    return TurnServerResponse(
        host=server.host,
        port=server.port,
        tls_port=server.tls_port,
        realm=server.realm,
        auth_type=server.auth_type.value,
        healthy=stats.get("healthy", False),
        latency_ms=stats.get("latency_ms"),
        last_check=stats.get("last_check"),
        errors=stats.get("errors", []),
    )


@router.delete("/turn/servers/{host}")
async def remove_turn_server(
    host: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a TURN server (admin only)."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")

    turn_manager = get_turn_manager()
    await turn_manager.remove_server(host)
    return {"success": True}


@router.patch("/turn/servers/{host}", response_model=TurnServerResponse)
async def update_turn_server(
    host: str,
    config: TurnServerConfig,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update TURN server configuration (admin only)."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")

    turn_manager = get_turn_manager()

    update_data = config.dict(exclude_unset=True)
    if "auth_type" in update_data:
        update_data["auth_type"] = TurnAuthType(update_data["auth_type"])

    await turn_manager.update_server(host, **update_data)

    stats = turn_manager.get_server_stats().get(host, {})
    server = next((s for s in turn_manager.servers if s.host == host), None)
    if not server:
        raise HTTPException(404, "Server not found")

    return TurnServerResponse(
        host=server.host,
        port=server.port,
        tls_port=server.tls_port,
        realm=server.realm,
        auth_type=server.auth_type.value,
        healthy=stats.get("healthy", False),
        latency_ms=stats.get("latency_ms"),
        last_check=stats.get("last_check"),
        errors=stats.get("errors", []),
    )


@router.post("/turn/servers/{host}/health-check")
async def check_turn_server_health(
    host: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Trigger health check for a specific TURN server (admin only)."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")

    turn_manager = get_turn_manager()
    server = next((s for s in turn_manager.servers if s.host == host), None)
    if not server:
        raise HTTPException(404, "Server not found")

    stats = await turn_manager._check_server_health(server)
    return stats


# ==================== Configuration Templates ====================

@router.get("/turn/templates", response_model=TurnConfigTemplateResponse)
async def get_turn_templates(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get TURN server configuration templates (admin only)."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")

    turn_manager = get_turn_manager()

    return TurnConfigTemplateResponse(
        coturn_config=turn_manager.get_coturn_config_template(),
        docker_compose=turn_manager.get_docker_compose_template(),
        kubernetes=turn_manager.get_kubernetes_template(),
    )


# ==================== Health & Stats ====================

@router.get("/turn/health")
async def get_turn_health(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get overall TURN service health."""
    turn_manager = get_turn_manager()
    stats = turn_manager.get_server_stats()
    healthy_servers = turn_manager.get_healthy_servers()

    return {
        "total_servers": len(turn_manager.servers),
        "healthy_servers": len(healthy_servers),
        "servers": stats,
        "stun_servers": turn_manager.stun_servers,
    }


@router.get("/turn/stats")
async def get_turn_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get TURN service statistics."""
    if not user.is_superuser:
        raise HTTPException(403, "Admin access required")

    turn_manager = get_turn_manager()
    stats = turn_manager.get_server_stats()

    total_checks = len(stats)
    healthy_count = sum(1 for s in stats.values() if s.get("healthy", False))
    avg_latency = None
    latencies = [s.get("latency_ms") for s in stats.values() if s.get("latency_ms")]
    if latencies:
        avg_latency = sum(latencies) / len(latencies)

    return {
        "total_servers": total_checks,
        "healthy": healthy_count,
        "unhealthy": total_checks - healthy_count,
        "average_latency_ms": avg_latency,
        "servers": stats,
    }