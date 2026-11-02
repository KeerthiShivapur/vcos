"""
VCOS WebSocket Gateway - Standalone Service
Provides horizontally scalable WebSocket connections with Redis pub/sub
"""

import asyncio
import json
import logging
import os
import signal
import sys
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional, Set

import redis.asyncio as redis
import structlog
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
from opentelemetry import trace
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource

# Local imports
from app.config import settings, load_config
from app.auth import verify_token, TokenData
from app.connection_manager import ConnectionManager
from app.rate_limiter import RateLimiter
from app.metrics import setup_metrics, ws_connections, ws_messages, ws_errors

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Metrics
ws_connections_total = Counter('ws_connections_total', 'Total WebSocket connections', ['status'])
ws_messages_total = Counter('ws_messages_total', 'Total WebSocket messages', ['direction', 'type'])
ws_latency = Histogram('ws_latency_seconds', 'WebSocket message latency', ['type'])
ws_active_connections = Gauge('ws_active_connections', 'Active WebSocket connections', ['type'])

# Global instances
redis_client: Optional[redis.Redis] = None
connection_manager: Optional[ConnectionManager] = None
rate_limiter: Optional[RateLimiter] = None
pubsub: Optional[redis.client.PubSub] = None
background_tasks: List[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global redis_client, connection_manager, rate_limiter, pubsub, background_tasks
    
    logger.info("starting_websocket_gateway")
    
    # Load configuration
    load_config()
    
    # Initialize Redis
    redis_client = redis.Redis(
        host=settings.redis.host,
        port=settings.redis.port,
        db=settings.redis.db,
        password=settings.redis.password,
        max_connections=settings.redis.max_connections,
        socket_timeout=settings.redis.socket_timeout,
        socket_connect_timeout=settings.redis.socket_connect_timeout,
        decode_responses=True,
    )
    
    # Test Redis connection
    await redis_client.ping()
    logger.info("redis_connected", host=settings.redis.host, port=settings.redis.port)
    
    # Initialize components
    connection_manager = ConnectionManager(redis_client, settings)
    rate_limiter = RateLimiter(redis_client, settings)
    
    # Initialize PubSub
    pubsub = redis_client.pubsub()
    
    # Subscribe to channels
    channels = [
        settings.pubsub.channels.presence,
        settings.pubsub.channels.crdt,
        settings.pubsub.channels.signaling,
        settings.pubsub.channels.notifications,
        settings.pubsub.channels.system,
    ]
    await pubsub.subscribe(*channels)
    logger.info("pubsub_subscribed", channels=channels)
    
    # Start background tasks
    background_tasks = [
        asyncio.create_task(pubsub_listener()),
        asyncio.create_task(connection_cleanup_task()),
        asyncio.create_task(metrics_collection_task()),
        asyncio.create_task(health_check_task()),
    ]
    
    # Setup metrics
    setup_metrics()
    
    logger.info("websocket_gateway_started")
    yield
    
    # Shutdown
    logger.info("shutting_down_websocket_gateway")
    
    for task in background_tasks:
        task.cancel()
    
    await asyncio.gather(*background_tasks, return_exceptions=True)
    
    if pubsub:
        await pubsub.unsubscribe(*channels)
        await pubsub.close()
    
    if connection_manager:
        await connection_manager.shutdown()
    
    if redis_client:
        await redis_client.close()
    
    logger.info("websocket_gateway_stopped")


app = FastAPI(
    title="VCOS WebSocket Gateway",
    description="Standalone WebSocket Gateway for Real-time Collaboration",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Instrumentation
FastAPIInstrumentor.instrument_app(app)
RedisInstrumentor().instrument()


# ==================== Models ====================

class ConnectionInfo(BaseModel):
    connection_id: str
    user_id: str
    organization_id: str
    connection_type: str  # crdt, signaling, presence
    connected_at: float
    last_activity: float
    metadata: Dict[str, Any] = {}


class WebSocketMessage(BaseModel):
    type: str
    payload: Dict[str, Any]
    request_id: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: asyncio.get_event_loop().time())


class HealthResponse(BaseModel):
    status: str
    version: str
    uptime: float
    connections: int
    redis_connected: bool
    pubsub_connected: bool


# ==================== Health Check ====================

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    redis_ok = False
    if redis_client:
        try:
            await redis_client.ping()
            redis_ok = True
        except Exception:
            pass
    
    pubsub_ok = pubsub is not None and pubsub.connection is not None
    
    return HealthResponse(
        status="healthy" if redis_ok and pubsub_ok else "degraded",
        version="1.0.0",
        uptime=asyncio.get_event_loop().time(),
        connections=connection_manager.total_connections if connection_manager else 0,
        redis_connected=redis_ok,
        pubsub_connected=pubsub_ok,
    )


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from fastapi.responses import Response
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ==================== WebSocket Endpoints ====================

@app.websocket("/ws/crdt/{document_id}")
async def crdt_websocket(
    websocket: WebSocket,
    document_id: str,
    token: str = Query(...),
):
    """WebSocket for CRDT document collaboration"""
    await handle_websocket(websocket, document_id, token, "crdt")


@app.websocket("/ws/signaling/{call_id}")
async def signaling_websocket(
    websocket: WebSocket,
    call_id: str,
    token: str = Query(...),
):
    """WebSocket for WebRTC signaling"""
    await handle_websocket(websocket, call_id, token, "signaling")


@app.websocket("/ws/presence/{organization_id}")
async def presence_websocket(
    websocket: WebSocket,
    organization_id: str,
    token: str = Query(...),
):
    """WebSocket for presence updates"""
    await handle_websocket(websocket, organization_id, token, "presence")


async def handle_websocket(
    websocket: WebSocket,
    resource_id: str,
    token: str,
    connection_type: str,
):
    """Main WebSocket handler"""
    connection_id = str(uuid.uuid4())
    
    # Verify token
    try:
        token_data = await verify_token(token, settings.auth.jwt_secret, settings.auth.jwt_algorithm)
    except Exception as e:
        logger.warning("invalid_token", connection_id=connection_id, error=str(e))
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    # Rate limiting
    if settings.rate_limit.enabled:
        allowed = await rate_limiter.check_limit(
            f"{connection_type}:{token_data.user_id}",
            settings.rate_limit.requests_per_second,
            settings.rate_limit.burst
        )
        if not allowed:
            await websocket.close(code=4002, reason="Rate limit exceeded")
            return
    
    # Accept connection
    await websocket.accept()
    
    # Register connection
    connection_info = ConnectionInfo(
        connection_id=connection_id,
        user_id=token_data.user_id,
        organization_id=token_data.organization_id,
        connection_type=connection_type,
        connected_at=asyncio.get_event_loop().time(),
        last_activity=asyncio.get_event_loop().time(),
    )
    
    await connection_manager.add_connection(
        connection_id=connection_id,
        websocket=websocket,
        resource_id=resource_id,
        connection_info=connection_info,
    )
    
    ws_connections_total.labels(status="connected").inc()
    ws_active_connections.labels(type=connection_type).inc()
    
    logger.info(
        "websocket_connected",
        connection_id=connection_id,
        user_id=token_data.user_id,
        resource_id=resource_id,
        type=connection_type,
    )
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_text()
            
            # Rate limit messages
            if settings.rate_limit.enabled:
                allowed = await rate_limiter.check_limit(
                    f"msg:{connection_id}",
                    settings.rate_limit.requests_per_second * 10,
                    settings.rate_limit.burst * 5
                )
                if not allowed:
                    await websocket.send_json({
                        "type": "error",
                        "code": "rate_limit",
                        "message": "Message rate limit exceeded"
                    })
                    continue
            
            # Parse message
            try:
                message = WebSocketMessage.model_validate_json(data)
            except Exception as e:
                await websocket.send_json({
                    "type": "error",
                    "code": "invalid_message",
                    "message": f"Invalid message format: {e}"
                })
                continue
            
            # Update activity
            await connection_manager.update_activity(connection_id)
            
            # Process message
            await process_message(connection_id, resource_id, connection_type, message, token_data)
            
            ws_messages_total.labels(direction="received", type=message.type).inc()
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error("websocket_error", connection_id=connection_id, error=str(e))
        ws_errors.labels(type=type(e).__name__).inc()
    finally:
        # Cleanup
        await connection_manager.remove_connection(connection_id)
        ws_connections_total.labels(status="disconnected").inc()
        ws_active_connections.labels(type=connection_type).dec()
        
        logger.info("websocket_disconnected", connection_id=connection_id)


async def process_message(
    connection_id: str,
    resource_id: str,
    connection_type: str,
    message: WebSocketMessage,
    token_data: TokenData,
):
    """Process incoming WebSocket message"""
    start_time = asyncio.get_event_loop().time()
    
    try:
        if connection_type == "crdt":
            await handle_crdt_message(connection_id, resource_id, message, token_data)
        elif connection_type == "signaling":
            await handle_signaling_message(connection_id, resource_id, message, token_data)
        elif connection_type == "presence":
            await handle_presence_message(connection_id, resource_id, message, token_data)
        else:
            await connection_manager.send_to_connection(connection_id, {
                "type": "error",
                "code": "unknown_type",
                "message": f"Unknown connection type: {connection_type}"
            })
    finally:
        latency = asyncio.get_event_loop().time() - start_time
        ws_latency.labels(type=message.type).observe(latency)


async def handle_crdt_message(
    connection_id: str,
    document_id: str,
    message: WebSocketMessage,
    token_data: TokenData,
):
    """Handle CRDT document messages"""
    payload = message.payload
    msg_type = message.type
    
    if msg_type == "operation":
        # CRDT operation - broadcast to other clients in document
        await pubsub.publish(
            settings.pubsub.channels.crdt,
            json.dumps({
                "type": "crdt:operation",
                "document_id": document_id,
                "connection_id": connection_id,
                "user_id": token_data.user_id,
                "payload": payload,
                "request_id": message.request_id,
            })
        )
        
    elif msg_type == "awareness":
        # Awareness update (cursor, selection, status)
        await pubsub.publish(
            settings.pubsub.channels.presence,
            json.dumps({
                "type": "awareness:update",
                "document_id": document_id,
                "connection_id": connection_id,
                "user_id": token_data.user_id,
                "payload": payload,
            })
        )
        
    elif msg_type == "sync":
        # Full document sync request
        # Would fetch from CRDT persistence and send back
        await connection_manager.send_to_connection(connection_id, {
            "type": "sync",
            "payload": {"document_id": document_id, "status": "synced"},
            "request_id": message.request_id,
        })
        
    elif msg_type == "ping":
        await connection_manager.send_to_connection(connection_id, {
            "type": "pong",
            "timestamp": asyncio.get_event_loop().time(),
        })


async def handle_signaling_message(
    connection_id: str,
    call_id: str,
    message: WebSocketMessage,
    token_data: TokenData,
):
    """Handle WebRTC signaling messages"""
    # Broadcast to other participants in call
    await pubsub.publish(
        settings.pubsub.channels.signaling,
        json.dumps({
            "type": "signaling:message",
            "call_id": call_id,
            "connection_id": connection_id,
            "user_id": token_data.user_id,
            "payload": message.payload,
            "request_id": message.request_id,
        })
    )


async def handle_presence_message(
    connection_id: str,
    organization_id: str,
    message: WebSocketMessage,
    token_data: TokenData,
):
    """Handle presence messages"""
    payload = message.payload
    msg_type = message.type
    
    if msg_type == "awareness":
        # Presence awareness update
        await pubsub.publish(
            settings.pubsub.channels.presence,
            json.dumps({
                "type": "presence:update",
                "organization_id": organization_id,
                "connection_id": connection_id,
                "user_id": token_data.user_id,
                "payload": payload,
            })
        )
        
    elif msg_type == "status":
        # Status change
        await pubsub.publish(
            settings.pubsub.channels.presence,
            json.dumps({
                "type": "presence:status",
                "organization_id": organization_id,
                "connection_id": connection_id,
                "user_id": token_data.user_id,
                "status": payload.get("status"),
            })
        )


# ==================== Background Tasks ====================

async def pubsub_listener():
    """Listen for PubSub messages and broadcast to connections"""
    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue
            
            try:
                data = json.loads(message["data"])
                await broadcast_pubsub_message(message["channel"], data)
            except Exception as e:
                logger.error("pubsub_message_error", error=str(e))
                
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error("pubsub_listener_error", error=str(e))
        await asyncio.sleep(5)
        asyncio.create_task(pubsub_listener())


async def broadcast_pubsub_message(channel: str, data: Dict[str, Any]):
    """Broadcast PubSub message to relevant connections"""
    if connection_manager:
        await connection_manager.broadcast_to_channel(channel, data)


async def connection_cleanup_task():
    """Periodic cleanup of stale connections"""
    while True:
        try:
            await asyncio.sleep(60)
            if connection_manager:
                cleaned = await connection_manager.cleanup_stale(
                    timeout=settings.websocket.ping_timeout * 2
                )
                if cleaned > 0:
                    logger.info("cleaned_stale_connections", count=cleaned)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("cleanup_error", error=str(e))


async def metrics_collection_task():
    """Collect and update metrics"""
    while True:
        try:
            await asyncio.sleep(10)
            if connection_manager:
                stats = connection_manager.get_stats()
                ws_active_connections.labels(type="crdt").set(stats.get("crdt", 0))
                ws_active_connections.labels(type="signaling").set(stats.get("signaling", 0))
                ws_active_connections.labels(type="presence").set(stats.get("presence", 0))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("metrics_error", error=str(e))


async def health_check_task():
    """Periodic health checks"""
    while True:
        try:
            await asyncio.sleep(30)
            # Check Redis
            if redis_client:
                await redis_client.ping()
            # Log stats
            if connection_manager:
                stats = connection_manager.get_stats()
                logger.debug("health_check", **stats)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("health_check_error", error=str(e))


# ==================== Entry Point ====================

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=settings.server.host,
        port=settings.server.port,
        workers=settings.server.workers,
        timeout=settings.server.timeout,
        log_config=None,
    )