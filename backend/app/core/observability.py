"""OpenTelemetry Observability Setup."""

import logging
import os
from contextlib import asynccontextmanager
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, Request, Response
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.prometheus import PrometheusMetricReader
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.metrics import Observation
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, PeriodicExportingMetricReader
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.semconv.resource import ResourceAttributes
from prometheus_client import Counter, Gauge, Histogram, generate_latest

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

# Global metrics
_meter = None
_tracer = None


def init_observability(app: FastAPI) -> None:
    """Initialize OpenTelemetry observability."""
    global _meter, _tracer
    
    # Create resource
    resource = Resource.create({
        ResourceAttributes.SERVICE_NAME: settings.APP_NAME,
        ResourceAttributes.SERVICE_VERSION: "1.0.0",
        ResourceAttributes.DEPLOYMENT_ENVIRONMENT: settings.ENVIRONMENT,
    })
    
    # Setup tracing
    trace_provider = TracerProvider(resource=resource)
    
    # Add OTLP exporter if configured
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otlp_endpoint:
        span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
        trace_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        logger.info(f"OTLP trace exporter configured: {otlp_endpoint}")
    else:
        # Console exporter for development
        trace_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
        logger.info("Console trace exporter configured")
    
    trace.set_tracer_provider(trace_provider)
    _tracer = trace.get_tracer(__name__)
    
    # Setup metrics
    metric_readers = []
    
    # Prometheus exporter
    prometheus_reader = PrometheusMetricReader()
    metric_readers.append(prometheus_reader)
    
    # OTLP metric exporter if configured
    if otlp_endpoint:
        metric_exporter = OTLPMetricExporter(endpoint=otlp_endpoint)
        metric_readers.append(PeriodicExportingMetricReader(metric_exporter))
    else:
        # Console exporter for development
        metric_readers.append(PeriodicExportingMetricReader(ConsoleMetricExporter()))
    
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=metric_readers,
    )
    metrics.set_meter_provider(meter_provider)
    _meter = metrics.get_meter(__name__)
    
    # Auto-instrument FastAPI
    FastAPIInstrumentor.instrument_app(app)
    
    # Auto-instrument logging
    LoggingInstrumentor().instrument(set_logging_format=True)
    
    # Auto-instrument SQLAlchemy
    SQLAlchemyInstrumentor().instrument()
    
    # Auto-instrument Redis
    if getattr(settings, "REDIS_ENABLED", False):
        RedisInstrumentor().instrument()
    
    logger.info("Observability initialized")


# =========================================================================
# Custom Metrics
# =========================================================================

class VCOSMetrics:
    """VCOS custom metrics."""
    
    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
    
    def counter(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None) -> Counter:
        """Get or create a counter."""
        key = f"{name}_{hash(str(sorted(labels.items())) if labels else '')}"
        if key not in self._counters:
            self._counters[key] = Counter(name, description, labelnames=list(labels.keys()) if labels else [])
        return self._counters[key]
    
    def gauge(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None) -> Gauge:
        """Get or create a gauge."""
        key = f"{name}_{hash(str(sorted(labels.items())) if labels else '')}"
        if key not in self._gauges:
            self._gauges[key] = Gauge(name, description, labelnames=list(labels.keys()) if labels else [])
        return self._gauges[key]
    
    def histogram(self, name: str, description: str = "", labels: Optional[Dict[str, str]] = None, buckets=None) -> Histogram:
        """Get or create a histogram."""
        key = f"{name}_{hash(str(sorted(labels.items())) if labels else '')}"
        if key not in self._histograms:
            self._histograms[key] = Histogram(
                name, description, 
                labelnames=list(labels.keys()) if labels else [],
                buckets=buckets or Histogram.DEFAULT_BUCKETS
            )
        return self._histograms[key]


# Global metrics instance
vcos_metrics = VCOSMetrics()


# =========================================================================
# Pre-defined VCOS Metrics
# =========================================================================

# HTTP Request Metrics
http_requests_total = vcos_metrics.counter(
    "vcos_http_requests_total",
    "Total HTTP requests",
    {"method": "", "endpoint": "", "status": ""}
)

http_request_duration = vcos_metrics.histogram(
    "vcos_http_request_duration_seconds",
    "HTTP request duration",
    {"method": "", "endpoint": ""},
)

# Database Metrics
db_query_duration = vcos_metrics.histogram(
    "vcos_db_query_duration_seconds",
    "Database query duration",
    {"operation": "", "table": ""},
)

db_connections_active = vcos_metrics.gauge(
    "vcos_db_connections_active",
    "Active database connections",
    {"pool": ""},
)

# WebSocket Metrics
ws_connections_active = vcos_metrics.gauge(
    "vcos_ws_connections_active",
    "Active WebSocket connections",
    {"organization": ""},
)

ws_messages_total = vcos_metrics.counter(
    "vcos_ws_messages_total",
    "Total WebSocket messages",
    {"type": "", "direction": ""},
)

# Authentication Metrics
auth_attempts_total = vcos_metrics.counter(
    "vcos_auth_attempts_total",
    "Total authentication attempts",
    {"method": "", "result": ""},
)

# API Rate Limit Metrics
rate_limit_hits = vcos_metrics.counter(
    "vcos_rate_limit_hits_total",
    "Rate limit hits",
    {"endpoint": "", "user": ""},
)

# Business Metrics
active_users = vcos_metrics.gauge(
    "vcos_active_users",
    "Active users",
    {"organization": ""},
)

active_organizations = vcos_metrics.gauge(
    "vcos_active_organizations",
    "Active organizations",
)

# Integration Metrics
integration_sync_duration = vcos_metrics.histogram(
    "vcos_integration_sync_duration_seconds",
    "Integration sync duration",
    {"connector": "", "operation": ""},
)

integration_sync_total = vcos_metrics.counter(
    "vcos_integration_sync_total",
    "Total integration syncs",
    {"connector": "", "result": ""},
)


# =========================================================================
# SLI/SLO Definitions
# =========================================================================

class SLIDefinition:
    """Service Level Indicator definition."""
    
    def __init__(
        self,
        name: str,
        description: str,
        sli_query: str,
        slo_target: float,
        window: str = "30d",
    ):
        self.name = name
        self.description = description
        self.sli_query = sli_query
        self.slo_target = slo_target
        self.window = window


# Pre-defined VCOS SLIs
VCOS_SLIS = [
    SLIDefinition(
        name="availability",
        description="API availability (successful requests / total requests)",
        sli_query="sum(rate(vcos_http_requests_total{status=~'2..'}[5m])) / sum(rate(vcos_http_requests_total[5m]))",
        slo_target=0.999,  # 99.9% availability
    ),
    SLIDefinition(
        name="latency_p99",
        description="P99 latency for API requests",
        sli_query="histogram_quantile(0.99, rate(vcos_http_request_duration_seconds_bucket[5m]))",
        slo_target=0.2,  # 200ms P99
    ),
    SLIDefinition(
        name="error_rate",
        description="Error rate (5xx errors / total requests)",
        sli_query="sum(rate(vcos_http_requests_total{status=~'5..'}[5m])) / sum(rate(vcos_http_requests_total[5m]))",
        slo_target=0.001,  # 0.1% error rate
    ),
    SLIDefinition(
        name="websocket_availability",
        description="WebSocket connection availability",
        sli_query="avg(vcos_ws_connections_active) > 0",
        slo_target=0.9999,
    ),
    SLIDefinition(
        name="database_availability",
        description="Database availability",
        sli_query="sum(vcos_db_connections_active) > 0",
        slo_target=0.9999,
    ),
]


# =========================================================================
# Alert Rules
# =========================================================================

class AlertRule:
    """Alert rule definition."""
    
    def __init__(
        self,
        name: str,
        description: str,
        condition: str,
        severity: str = "warning",
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, str]] = None,
        for_duration: str = "5m",
    ):
        self.name = name
        self.description = description
        self.condition = condition
        self.severity = severity
        self.labels = labels or {}
        self.annotations = annotations or {}
        self.for_duration = for_duration


# Pre-defined VCOS Alert Rules
VCOS_ALERT_RULES = [
    AlertRule(
        name="HighErrorRate",
        description="Error rate exceeds 1% for 5 minutes",
        condition="sum(rate(vcos_http_requests_total{status=~'5..'}[5m])) / sum(rate(vcos_http_requests_total[5m])) > 0.01",
        severity="critical",
        labels={"team": "platform", "component": "api"},
        annotations={
            "summary": "High error rate detected",
            "description": "Error rate has exceeded 1% for more than 5 minutes",
        },
    ),
    AlertRule(
        name="HighLatency",
        description="P99 latency exceeds 500ms for 5 minutes",
        condition="histogram_quantile(0.99, rate(vcos_http_request_duration_seconds_bucket[5m])) > 0.5",
        severity="warning",
        labels={"team": "platform", "component": "api"},
        annotations={
            "summary": "High latency detected",
            "description": "P99 latency has exceeded 500ms for more than 5 minutes",
        },
    ),
    AlertRule(
        name="HighErrorRate5xx",
        description="5xx error rate exceeds 0.1% for 5 minutes",
        condition="sum(rate(vcos_http_requests_total{status=~'5..'}[5m])) / sum(rate(vcos_http_requests_total[5m])) > 0.001",
        severity="critical",
        labels={"team": "platform", "component": "api"},
        annotations={
            "summary": "High 5xx error rate",
            "description": "5xx error rate has exceeded 0.1% for more than 5 minutes",
        },
    ),
    AlertRule(
        name="DatabaseConnectionPoolExhausted",
        description="Database connection pool exhausted",
        condition="vcos_db_connections_active / vcos_db_connections_max > 0.9",
        severity="critical",
        labels={"team": "platform", "component": "database"},
        annotations={
            "summary": "Database connection pool nearly exhausted",
            "description": "Database connection pool usage exceeds 90%",
        },
    ),
    AlertRule(
        name="WebSocketConnectionsDropped",
        description="WebSocket connections dropped significantly",
        condition="rate(vcos_ws_connections_active[5m]) < -10",
        severity="warning",
        labels={"team": "platform", "component": "realtime"},
        annotations={
            "summary": "WebSocket connections dropping",
            "description": "WebSocket connections have dropped by more than 10 in 5 minutes",
        },
    ),
    AlertRule(
        name="HighAuthFailureRate",
        description="Authentication failure rate high",
        condition="sum(rate(vcos_auth_attempts_total{result='failure'}[5m])) / sum(rate(vcos_auth_attempts_total[5m])) > 0.1",
        severity="warning",
        labels={"team": "security", "component": "auth"},
        annotations={
            "summary": "High authentication failure rate",
            "description": "More than 10% of authentication attempts are failing",
        },
    ),
    AlertRule(
        name="IntegrationSyncFailures",
        description="Integration sync failures spike",
        condition="sum(rate(vcos_integration_sync_total{result='failure'}[5m])) > 5",
        severity="warning",
        labels={"team": "integrations", "component": "connectors"},
        annotations={
            "summary": "Integration sync failures",
            "description": "More than 5 integration sync failures per minute",
        },
    ),
]


# =========================================================================
# Middleware for Request Metrics
# =========================================================================

async def metrics_middleware(request: Request, call_next: Callable) -> Response:
    """Middleware to collect request metrics."""
    start_time = time.time()
    method = request.method
    endpoint = request.url.path
    
    try:
        response = await call_next(request)
        status = str(response.status_code)
        
        # Record metrics
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status=status
        ).inc()
        
        http_request_duration.labels(
            method=method,
            endpoint=endpoint
        ).observe(time.time() - start_time)
        
        return response
    except Exception as e:
        http_requests_total.labels(
            method=method,
            endpoint=endpoint,
            status="500"
        ).inc()
        raise


# =========================================================================
# Tracing Utilities
# =========================================================================

def get_tracer(name: str = None):
    """Get tracer instance."""
    return trace.get_tracer(name or __name__)


def get_meter(name: str = None):
    """Get meter instance."""
    return metrics.get_meter(name or __name__)


def start_span(name: str, attributes: Dict[str, Any] = None):
    """Start a new span."""
    tracer = get_tracer()
    return tracer.start_as_current_span(name, attributes=attributes or {})


def add_span_attributes(attributes: Dict[str, Any]):
    """Add attributes to current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        for key, value in attributes.items():
            span.set_attribute(key, value)


def record_exception(exception: Exception):
    """Record exception in current span."""
    span = trace.get_current_span()
    if span and span.is_recording():
        span.record_exception(exception)
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(exception)))


# Initialize time module
import time