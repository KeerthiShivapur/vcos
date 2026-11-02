"""
Metrics for WebSocket Gateway
"""

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST
from fastapi.responses import Response


# Custom registry
registry = CollectorRegistry()

# Connection metrics
ws_connections_total = Counter(
    'ws_connections_total',
    'Total WebSocket connections',
    ['status', 'type', 'gateway'],
    registry=registry
)

ws_active_connections = Gauge(
    'ws_active_connections',
    'Currently active WebSocket connections',
    ['type', 'gateway'],
    registry=registry
)

ws_connections_by_resource = Gauge(
    'ws_connections_by_resource',
    'Active connections per resource',
    ['resource_id', 'type', 'gateway'],
    registry=registry
)

# Message metrics
ws_messages_total = Counter(
    'ws_messages_total',
    'Total WebSocket messages',
    ['direction', 'type', 'gateway'],
    registry=registry
)

ws_message_size = Histogram(
    'ws_message_size_bytes',
    'WebSocket message size in bytes',
    ['direction', 'type'],
    buckets=[64, 256, 1024, 4096, 16384, 65536, 262144, 1048576],
    registry=registry
)

ws_message_latency = Histogram(
    'ws_message_latency_seconds',
    'WebSocket message processing latency',
    ['type', 'gateway'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry
)

# Error metrics
ws_errors_total = Counter(
    'ws_errors_total',
    'Total WebSocket errors',
    ['type', 'code', 'gateway'],
    registry=registry
)

# Connection lifecycle
ws_connection_duration = Histogram(
    'ws_connection_duration_seconds',
    'WebSocket connection duration',
    ['type', 'gateway'],
    buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600, 7200, 86400],
    registry=registry
)

# Rate limiting
ws_rate_limited = Counter(
    'ws_rate_limited_total',
    'Total rate limited requests',
    ['key', 'gateway'],
    registry=registry
)

# PubSub metrics
ws_pubsub_messages = Counter(
    'ws_pubsub_messages_total',
    'Total PubSub messages',
    ['channel', 'direction', 'gateway'],
    registry=registry
)

ws_pubsub_latency = Histogram(
    'ws_pubsub_latency_seconds',
    'PubSub message delivery latency',
    ['channel', 'gateway'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry
)

# Redis metrics
ws_redis_operations = Counter(
    'ws_redis_operations_total',
    'Total Redis operations',
    ['operation', 'gateway'],
    registry=registry
)

ws_redis_latency = Histogram(
    'ws_redis_latency_seconds',
    'Redis operation latency',
    ['operation', 'gateway'],
    buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0],
    registry=registry
)

# Gateway info
ws_gateway_info = Gauge(
    'ws_gateway_info',
    'Gateway information',
    ['gateway_id', 'region', 'version'],
    registry=registry
)


def setup_metrics(gateway_id: str = "gateway-1", region: str = "local", version: str = "1.0.0"):
    """Initialize metrics with gateway info"""
    ws_gateway_info.labels(
        gateway_id=gateway_id,
        region=region,
        version=version
    ).set(1)


def get_metrics() -> bytes:
    """Get Prometheus metrics output"""
    return generate_latest(registry)


def get_metrics_response() -> Response:
    """Get Prometheus metrics as FastAPI response"""
    return Response(
        content=generate_latest(registry),
        media_type="text/plain; version=0.0.4; charset=utf-8"
    )