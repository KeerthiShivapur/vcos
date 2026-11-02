"""
Real-Time Services Initialization and Configuration.

Centralizes initialization of all real-time collaboration services:
- CRDT Engine & Persistence
- Presence Service (Redis)
- Signaling Server (WebRTC)
- TURN Manager
- Push Service
- LiveKit Integration
"""

import asyncio
import logging
from typing import Optional

from app.core.config import get_settings
from app.core.crdt_engine import (
    CRDTEngine,
    get_crdt_engine,
    init_crdt_engine,
)
from app.core.crdt_persistence import (
    CRDTPersistence,
    PersistenceMode,
    get_crdt_persistence,
    init_crdt_persistence,
)
from app.core.signaling import (
    SignalingServer,
    get_signaling_server,
    init_signaling_server,
)
from app.core.presence_redis import (
    PresenceService,
    get_presence_service,
    init_presence_service,
)
from app.core.push_service import (
    PushService,
    get_push_service,
    init_push_service,
)
from app.core.turn_manager import (
    TurnManager,
    TurnServer,
    TurnAuthType,
    get_turn_manager,
    init_turn_manager,
)

logger = logging.getLogger(__name__)

# Global service instances
_realtime_services_initialized = False


async def initialize_realtime_services(
    redis_url: Optional[str] = None,
    livekit_url: Optional[str] = None,
    livekit_api_key: Optional[str] = None,
    livekit_api_secret: Optional[str] = None,
    vapid_subject: str = "mailto:admin@vcos.io",
    fcm_server_key: Optional[str] = None,
    fcm_project_id: Optional[str] = None,
    apns_team_id: Optional[str] = None,
    apns_key_id: Optional[str] = None,
    apns_bundle_id: Optional[str] = None,
    apns_private_key_path: Optional[str] = None,
    apns_use_sandbox: bool = True,
    turn_servers: Optional[list] = None,
    turn_stun_servers: Optional[list] = None,
) -> dict:
    """
    Initialize all real-time collaboration services.
    
    Returns:
        dict: Status of each service initialization
    """
    global _realtime_services_initialized
    
    settings = get_settings()
    
    # Check if Redis is enabled before using it
    redis_enabled = getattr(settings, "REDIS_ENABLED", False)
    if not redis_enabled:
        redis_url = None
    else:
        # Use provided values or fall back to settings
        redis_url = redis_url or getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
    
    livekit_url = livekit_url or getattr(settings, "LIVEKIT_URL", None)
    livekit_api_key = livekit_api_key or getattr(settings, "LIVEKIT_API_KEY", None)
    livekit_api_secret = livekit_api_secret or getattr(settings, "LIVEKIT_API_SECRET", None)
    vapid_subject = vapid_subject or getattr(settings, "VAPID_SUBJECT", "mailto:admin@vcos.io")
    fcm_server_key = fcm_server_key or getattr(settings, "FCM_SERVER_KEY", None)
    fcm_project_id = fcm_project_id or getattr(settings, "FCM_PROJECT_ID", None)
    apns_team_id = apns_team_id or getattr(settings, "APNS_TEAM_ID", None)
    apns_key_id = apns_key_id or getattr(settings, "APNS_KEY_ID", None)
    apns_bundle_id = apns_bundle_id or getattr(settings, "APNS_BUNDLE_ID", None)
    apns_private_key_path = apns_private_key_path or getattr(settings, "APNS_PRIVATE_KEY_PATH", None)
    apns_use_sandbox = apns_use_sandbox if apns_use_sandbox is not None else getattr(settings, "APNS_USE_SANDBOX", True)
    
    results = {}
    
    # ==================== 1. Presence Service ====================
    try:
        presence_service = init_presence_service(
            redis_url=redis_url,
            use_redis=True,
        )
        await presence_service.initialize()
        results["presence"] = {"status": "initialized", "redis_url": redis_url}
        logger.info("Presence Service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Presence Service: {e}")
        results["presence"] = {"status": "failed", "error": str(e)}
    
    # ==================== 2. CRDT Engine ====================
    try:
        crdt_engine = init_crdt_engine(presence_service=None)
        results["crdt_engine"] = {"status": "initialized"}
        logger.info("CRDT Engine initialized")
    except Exception as e:
        logger.error(f"Failed to initialize CRDT Engine: {e}")
        results["crdt_engine"] = {"status": "failed", "error": str(e)}
    
    # ==================== 3. CRDT Persistence ====================
    try:
        crdt_engine = get_crdt_engine()
        crdt_persistence = init_crdt_persistence(
            redis_url=redis_url,
            persistence_mode=PersistenceMode.ASYNC,
            crdt_engine=crdt_engine,
        )
        await crdt_persistence.initialize()
        results["crdt_persistence"] = {"status": "initialized", "redis_url": redis_url}
        logger.info("CRDT Persistence initialized")
    except Exception as e:
        logger.error(f"Failed to initialize CRDT Persistence: {e}")
        results["crdt_persistence"] = {"status": "failed", "error": str(e)}
    
    # ==================== 4. Signaling Server ====================
    try:
        turn_manager = None
        try:
            turn_manager = get_turn_manager()
        except:
            pass
            
        signaling_server = init_signaling_server(
            presence_service=results.get("presence", {}).get("service"),
            livekit_url=livekit_url,
            livekit_api_key=livekit_api_key,
            livekit_api_secret=livekit_api_secret,
            turn_manager=turn_manager,
        )
        await signaling_server.initialize_livekit()
        results["signaling"] = {"status": "initialized", "livekit": livekit_url is not None}
        logger.info("Signaling Server initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Signaling Server: {e}")
        results["signaling"] = {"status": "failed", "error": str(e)}
    
    # ==================== 5. TURN Manager ====================
    try:
        if turn_servers:
            servers = [
                TurnServer(
                    host=s.host,
                    port=s.port,
                    tls_port=s.tls_port,
                    realm=s.realm,
                    auth_type=TurnAuthType(s.auth_type),
                    static_username=s.static_username,
                    static_password=s.static_password,
                    shared_secret=s.shared_secret,
                    cert_path=s.cert_path,
                    key_path=s.key_path,
                    max_bps=s.max_bps,
                    max_connections=s.max_connections,
                )
                for s in turn_servers
            ]
        else:
            # Default configuration from settings
            servers = [
                TurnServer(
                    host=getattr(settings, "TURN_HOST", "turn.vcos.io"),
                    port=getattr(settings, "TURN_PORT", 3478),
                    tls_port=getattr(settings, "TURN_TLS_PORT", 5349),
                    realm=getattr(settings, "TURN_REALM", "vcos.io"),
                    auth_type=TurnAuthType.EPHEMERAL,
                    shared_secret=getattr(settings, "TURN_SHARED_SECRET", "changeme_shared_secret_please_rotate"),
                ),
            ]
        
        turn_manager = init_turn_manager(
            servers=servers,
            default_ttl=getattr(settings, "TURN_DEFAULT_TTL", 86400),
            stun_servers=turn_stun_servers or [
                "stun:stun.l.google.com:19302",
                "stun:stun1.l.google.com:19302",
            ],
        )
        await turn_manager.start_health_monitoring(interval=60)
        results["turn"] = {"status": "initialized", "servers": len(servers)}
        logger.info("TURN Manager initialized")
    except Exception as e:
        logger.error(f"Failed to initialize TURN Manager: {e}")
        results["turn"] = {"status": "failed", "error": str(e)}
    
    # ==================== 6. Push Service ====================
    try:
        push_service = init_push_service(
            vapid_subject=vapid_subject,
            fcm_server_key=fcm_server_key,
            fcm_project_id=fcm_project_id,
            apns_team_id=apns_team_id,
            apns_key_id=apns_key_id,
            apns_bundle_id=apns_bundle_id,
            apns_private_key_path=apns_private_key_path,
            apns_use_sandbox=apns_use_sandbox,
            redis_url=redis_url,
        )
        await push_service.initialize()
        results["push"] = {"status": "initialized", "redis_url": redis_url}
        logger.info("Push Service initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Push Service: {e}")
        results["push"] = {"status": "failed", "error": str(e)}
    
    _realtime_services_initialized = True
    
    logger.info("All real-time services initialization complete", extra={"results": results})
    return results


async def shutdown_realtime_services():
    """Gracefully shutdown all real-time services."""
    global _realtime_services_initialized
    
    results = {}
    
    # Shutdown Presence
    try:
        presence = get_presence_service()
        await presence.close()
        results["presence"] = "shutdown"
    except Exception as e:
        logger.error(f"Error shutting down Presence: {e}")
        results["presence"] = f"error: {e}"
    
    # Shutdown CRDT Persistence
    try:
        persistence = get_crdt_persistence()
        await persistence.close()
        results["crdt_persistence"] = "shutdown"
    except Exception as e:
        logger.error(f"Error shutting down CRDT Persistence: {e}")
        results["crdt_persistence"] = f"error: {e}"
    
    # Shutdown Push
    try:
        push = get_push_service()
        await push.close()
        results["push"] = "shutdown"
    except Exception as e:
        logger.error(f"Error shutting down Push: {e}")
        results["push"] = f"error: {e}"
    
    # Shutdown TURN
    try:
        turn = get_turn_manager()
        await turn.stop_health_monitoring()
        results["turn"] = "shutdown"
    except Exception as e:
        logger.error(f"Error shutting down TURN: {e}")
        results["turn"] = f"error: {e}"
    
    _realtime_services_initialized = False
    
    logger.info("All real-time services shutdown complete", extra={"results": results})
    return results


def is_realtime_initialized() -> bool:
    """Check if real-time services are initialized."""
    return _realtime_services_initialized


async def get_realtime_health() -> dict:
    """Get health status of all real-time services."""
    health = {}
    
    # Presence
    try:
        presence = get_presence_service()
        stats = await presence.get_stats("default")
        health["presence"] = {"status": "healthy", "stats": stats}
    except Exception as e:
        health["presence"] = {"status": "unhealthy", "error": str(e)}
    
    # CRDT Persistence
    try:
        persistence = get_crdt_persistence()
        stats = await persistence.get_stats()
        health["crdt_persistence"] = {"status": "healthy", "stats": stats}
    except Exception as e:
        health["crdt_persistence"] = {"status": "unhealthy", "error": str(e)}
    
    # Push
    try:
        push = get_push_service()
        stats = await push.get_stats("default")
        health["push"] = {"status": "healthy", "stats": stats}
    except Exception as e:
        health["push"] = {"status": "unhealthy", "error": str(e)}
    
    # TURN
    try:
        turn = get_turn_manager()
        health_turn = await turn.get_turn_health()
        health["turn"] = {"status": "healthy", "stats": health_turn}
    except Exception as e:
        health["turn"] = {"status": "unhealthy", "error": str(e)}
    
    # Signaling
    try:
        signaling = get_signaling_server()
        calls = signaling.get_active_calls()
        health["signaling"] = {"status": "healthy", "active_calls": len(calls)}
    except Exception as e:
        health["signaling"] = {"status": "unhealthy", "error": str(e)}
    
    return health