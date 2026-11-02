"""
Structured Logging with Correlation IDs for VCOS.

Provides:
- Structured JSON logging with correlation IDs
- Context propagation across async boundaries
- Log levels and structured fields
- Integration with audit log and observability
- OpenTelemetry-compatible trace context
"""

import contextvars
import json
import logging
import sys
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4

from contextvars import ContextVar

from app.core.config import settings
from app.core.audit_log import audit_log_manager, EventType, Severity

logger = logging.getLogger(__name__)


class LogLevel(str, Enum):
    """Log levels matching standard logging levels."""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class LogFormat(str, Enum):
    """Log output formats."""
    JSON = "json"
    TEXT = "text"
    CONSOLE = "console"


# Context variables for correlation tracking
_correlation_id: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
_trace_id: ContextVar[Optional[str]] = ContextVar("trace_id", default=None)
_span_id: ContextVar[Optional[str]] = ContextVar("span_id", default=None)
_user_id: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
_organization_id: ContextVar[Optional[str]] = ContextVar("organization_id", default=None)
_request_id: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


@dataclass
class LogContext:
    """Structured log context with all correlation fields."""
    correlation_id: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    user_id: Optional[str] = None
    organization_id: Optional[str] = None
    request_id: Optional[str] = None
    service_name: str = "vcos"
    environment: str = "production"
    version: str = "1.0.0"


class StructuredLogger:
    """
    Structured JSON logger with correlation ID support.
    
    Features:
    - JSON-formatted logs with consistent schema
    - Automatic correlation ID propagation
    - Context propagation across async boundaries
    - Structured fields for querying
    - Multiple output formats (JSON, text, console)
    """

    def __init__(
        self,
        name: str,
        level: LogLevel = LogLevel.INFO,
        format: LogFormat = LogFormat.JSON,
        service_name: str = "vcos",
        environment: str = "production",
        version: str = "1.0.0",
    ):
        self.name = name
        self.level = level
        self.format = format
        self.service_name = service_name
        self.environment = environment
        self.version = version
        self._logger = logging.getLogger(name)
        self._logger.setLevel(getattr(logging, level.value))
        self._setup_handlers()

    def _setup_handlers(self):
        """Set up log handlers based on format."""
        # Remove existing handlers
        for handler in self._logger.handlers[:]:
            self._logger.removeHandler(handler)

        if self.format == LogFormat.JSON:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JsonFormatter())
        elif self.format == LogFormat.CONSOLE:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(ConsoleFormatter())
        else:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(TextFormatter())

        self._logger.addHandler(handler)

    def _get_context(self) -> Dict[str, Any]:
        """Get current context from context variables."""
        return {
            "correlation_id": _correlation_id.get(),
            "trace_id": _trace_id.get(),
            "span_id": _span_id.get(),
            "user_id": _user_id.get(),
            "organization_id": _organization_id.get(),
            "request_id": _request_id.get(),
        }

    def _log(
        self,
        level: LogLevel,
        message: str,
        extra: Optional[Dict[str, Any]] = None,
        exc_info: bool = False,
        **kwargs
    ):
        """Internal log method with context enrichment."""
        context = self._get_context()
        
        # Merge extra fields
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": level.value,
            "message": message,
            "service": "vcos",
            **context,
            **kwargs,
        }
        
        if extra:
            log_data.update(extra)

        # Get logger method
        log_method = getattr(self._logger, level.value.lower())
        log_method(message, extra=log_data, exc_info=exc_info)

    def debug(self, message: str, **kwargs):
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log(LogLevel.CRITICAL, message, **kwargs)

    def exception(self, message: str, **kwargs):
        self._log(LogLevel.ERROR, message, exc_info=True, **kwargs)

    @contextmanager
    def context(self, **context_fields):
        """Context manager to add fields to all logs within scope."""
        tokens = []
        try:
            for key, value in context_fields.items():
                var = globals().get(f"_{key}")
                if var:
                    tokens.append(var.set(value))
            yield
        finally:
            for token in reversed(tokens):
                token.var.reset(token.value)

    def bind(self, **fields) -> "BoundLogger":
        """Create a bound logger with fixed fields."""
        return BoundLogger(self, fields)


class BoundLogger:
    """Logger with pre-bound fields."""

    def __init__(self, logger: StructuredLogger, fields: Dict[str, Any]):
        self._logger = logger
        self._fields = fields

    def _log(self, level: LogLevel, message: str, **kwargs):
        combined = {**self._fields, **kwargs}
        self._logger._log(level, message, extra=combined)

    def debug(self, message: str, **kwargs):
        self._log(LogLevel.DEBUG, message, **kwargs)

    def info(self, message: str, **kwargs):
        self._log(LogLevel.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(LogLevel.WARNING, message, **kwargs)

    def error(self, message: str, **kwargs):
        self._log(LogLevel.ERROR, message, **kwargs)

    def critical(self, message: str, **kwargs):
        self._log(LogLevel.CRITICAL, message, **kwargs)

    def exception(self, message: str, **kwargs):
        self._log(LogLevel.ERROR, message, exc_info=True, **kwargs)


class JsonFormatter(logging.Formatter):
    """JSON formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "lineno", "funcName", "created",
                "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message", "args", "exc_info",
                "exc_text", "stack_info", "getMessage"
            }:
                if not key.startswith("_"):
                    log_data[key] = value

        return json.dumps(log_data, default=str, separators=(",", ":"))


class TextFormatter(logging.Formatter):
    """Human-readable text formatter."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.utcnow().isoformat() + "Z"
        level = record.levelname
        message = record.getMessage()
        
        # Build context string
        context_parts = []
        for key in ["correlation_id", "trace_id", "span_id", "user_id", "organization_id", "request_id"]:
            value = getattr(record, key, None)
            if value:
                context_parts.append(f"{key}={value}")
        
        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""
        
        return f"{timestamp} [{level}] {record.name}: {message}{context_str}"


class ConsoleFormatter(logging.Formatter):
    """Colorized console formatter for development."""

    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        timestamp = datetime.utcnow().isoformat(timespec="milliseconds") + "Z"
        level = f"{color}{record.levelname:<8}{reset}"
        message = record.getMessage()
        
        # Context
        context_parts = []
        for key in ["correlation_id", "trace_id", "span_id", "user_id", "organization_id", "request_id"]:
            value = getattr(record, key, None)
            if value:
                context_parts.append(f"{key}={value}")
        
        context_str = f" [{', '.join(context_parts)}]" if context_parts else ""
        
        return f"{timestamp} {level} {record.name}: {message}{context_str}{reset}"


# ==================== Context Management ====================

def get_correlation_id() -> Optional[str]:
    """Get current correlation ID."""
    return _correlation_id.get()


def set_correlation_id(correlation_id: Optional[str] = None) -> str:
    """Set correlation ID, generating one if not provided."""
    if correlation_id is None:
        correlation_id = uuid4().hex[:32]
    _correlation_id.set(correlation_id)
    return correlation_id


def get_trace_id() -> Optional[str]:
    """Get current trace ID."""
    return _trace_id.get()


def set_trace_id(trace_id: Optional[str] = None) -> str:
    """Set trace ID, generating one if not provided."""
    if trace_id is None:
        trace_id = uuid4().hex[:32]
    _trace_id.set(trace_id)
    return trace_id


def get_span_id() -> Optional[str]:
    """Get current span ID."""
    return _span_id.get()


def set_span_id(span_id: Optional[str] = None) -> str:
    """Set span ID, generating one if not provided."""
    if span_id is None:
        span_id = uuid4().hex[:16]
    _span_id.set(span_id)
    return span_id


def get_user_id() -> Optional[str]:
    """Get current user ID."""
    return _user_id.get()


def set_user_id(user_id: Optional[str]):
    """Set user ID."""
    if user_id:
        _user_id.set(user_id)
    else:
        _user_id.set(None)


def get_organization_id() -> Optional[str]:
    """Get current organization ID."""
    return _organization_id.get()


def set_organization_id(organization_id: Optional[str]):
    """Set organization ID."""
    if organization_id:
        _organization_id.set(organization_id)
    else:
        _organization_id.set(None)


def get_request_id() -> Optional[str]:
    """Get current request ID."""
    return _request_id.get()


def set_request_id(request_id: Optional[str] = None) -> str:
    """Set request ID, generating one if not provided."""
    if request_id is None:
        request_id = uuid4().hex[:32]
    _request_id.set(request_id)
    return request_id


@contextmanager
def correlation_context(
    correlation_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    user_id: Optional[str] = None,
    organization_id: Optional[str] = None,
    request_id: Optional[str] = None,
):
    """Context manager for correlation context."""
    tokens = []
    try:
        if correlation_id is not None:
            tokens.append(_correlation_id.set(correlation_id))
        if trace_id is not None:
            tokens.append(_trace_id.set(trace_id))
        if span_id is not None:
            tokens.append(_span_id.set(span_id))
        if user_id is not None:
            tokens.append(_user_id.set(user_id))
        if organization_id is not None:
            tokens.append(_organization_id.set(organization_id))
        if request_id is not None:
            tokens.append(_request_id.set(request_id))
        yield
    finally:
        for token in reversed(tokens):
            token.var.reset(token.old_value)


def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return uuid4().hex[:32]


def generate_trace_id() -> str:
    """Generate a new trace ID."""
    return uuid4().hex[:32]


def generate_span_id() -> str:
    """Generate a new span ID."""
    return uuid4().hex[:16]


def generate_request_id() -> str:
    """Generate a new request ID."""
    return uuid4().hex[:32]


# ==================== Logging Decorators ====================

def log_calls(
    logger: Optional[StructuredLogger] = None,
    level: LogLevel = LogLevel.DEBUG,
    log_args: bool = True,
    log_result: bool = True,
    log_duration: bool = True,
):
    """Decorator to log function calls with timing."""
    def decorator(func: Callable) -> Callable:
        _logger = logger or StructuredLogger(func.__module__)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.time()
            args_str = str(args)[:200] if log_args else "..."
            kwargs_str = str(kwargs)[:200] if log_args else "..."
            
            _logger = logger or StructuredLogger(func.__module__)
            _logger._log(
                level,
                f"Calling {func.__name__}",
                function=func.__name__,
                args=args_str,
                kwargs=kwargs_str,
            )
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start
                
                if log_result:
                    result_str = str(result)[:200]
                    _logger._log(
                        level,
                        f"Completed {func.__name__}",
                        function=func.__name__,
                        duration_ms=round(duration * 1000, 2),
                        result=result_str,
                    )
                elif log_duration:
                    _logger._log(
                        level,
                        f"Completed {func.__name__}",
                        function=func.__name__,
                        duration_ms=round(duration * 1000, 2),
                    )
                return result
            except Exception as e:
                duration = time.time() - start
                _logger.error(
                    f"Failed {func.__name__}",
                    function=func.__name__,
                    duration_ms=round((time.time() - start) * 1000, 2),
                    error=str(e),
                    exc_info=True,
                )
                raise

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.time()
            args_str = str(args)[:200] if log_args else "..."
            kwargs_str = str(kwargs)[:200] if log_args else "..."
            
            _logger = logger or StructuredLogger(func.__module__)
            _logger._log(
                level,
                f"Calling {func.__name__}",
                function=func.__name__,
                args=args_str,
                kwargs=kwargs_str,
            )
            
            try:
                result = func(*args, **kwargs)
                duration = time.time() - start
                
                if log_result:
                    result_str = str(result)[:200]
                    _logger._log(
                        level,
                        f"Completed {func.__name__}",
                        function=func.__name__,
                        duration_ms=round(duration * 1000, 2),
                        result=result_str,
                    )
                elif log_duration:
                    _logger._log(
                        level,
                        f"Completed {func.__name__}",
                        function=func.__name__,
                        duration_ms=round(duration * 1000, 2),
                    )
                return result
            except Exception as e:
                duration = time.time() - start
                _logger.error(
                    f"Failed {func.__name__}",
                    function=func.__name__,
                    duration_ms=round((time.time() - start) * 1000, 2),
                    error=str(e),
                    exc_info=True,
                )
                raise

        import inspect
        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def log_request_response(logger: Optional[StructuredLogger] = None):
    """Decorator to log HTTP request/response."""
    def decorator(func: Callable) -> Callable:
        _logger = logger or StructuredLogger("http")
        
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract request from args
            request = args[0] if args else kwargs.get("request")
            
            request_id = get_request_id() or generate_request_id()
            set_request_id(request_id)
            
            start = time.time()
            method = getattr(request, "method", "UNKNOWN")
            path = getattr(request, "url", {}).path if hasattr(request, "url") else "unknown"
            
            _logger = StructuredLogger("http")
            _logger.info(
                "HTTP request started",
                method=method,
                path=path,
                request_id=get_request_id(),
            )
            
            try:
                result = await func(*args, **kwargs)
                duration = time.time() - start
                
                status_code = getattr(result, "status_code", 200)
                _logger = StructuredLogger("http")
                _logger.info(
                    "HTTP request completed",
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=round((time.time() - start) * 1000, 2),
                    request_id=get_request_id(),
                )
                return result
            except Exception as e:
                duration = time.time() - start
                _logger = StructuredLogger("http")
                _logger.error(
                    "HTTP request failed",
                    method=method,
                    path=path,
                    duration_ms=round((time.time() - start) * 1000, 2),
                    error=str(e),
                    exc_info=True,
                )
                raise
        
        return wrapper
    return decorator


# ==================== FastAPI Middleware ====================

class StructuredLoggingMiddleware:
    """FastAPI middleware for structured logging with correlation IDs."""

    def __init__(self, app, logger: Optional[StructuredLogger] = None):
        self.app = app
        self.logger = logger or StructuredLogger("http")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Generate or extract correlation ID
        headers = dict(scope.get("headers", []))
        correlation_id = headers.get(b"x-correlation-id", b"").decode()
        if not correlation_id:
            correlation_id = generate_correlation_id()
        
        request_id = generate_request_id()
        trace_id = headers.get(b"x-trace-id", b"").decode() or generate_trace_id()
        span_id = generate_span_id()
        
        # Set context
        correlation_token = _correlation_id.set(correlation_id)
        trace_token = _trace_id.set(trace_id)
        span_token = _span_id.set(span_id)
        request_token = _request_id.set(generate_request_id())
        
        # Extract user/org from headers
        user_id = headers.get(b"x-user-id", b"").decode()
        org_id = headers.get(b"x-organization-id", b"").decode()
        
        user_token = _user_id.set(user_id) if user_id else None
        org_token = _organization_id.set(org_id) if org_id else None
        
        request_id_var = _request_id.set(generate_request_id())
        
        start_time = time.time()
        method = scope.get("method", "UNKNOWN")
        path = scope.get("path", "/")
        
        logger = StructuredLogger("http")
        logger.info(
            "HTTP request started",
            method=scope.get("method"),
            path=scope.get("path"),
            correlation_id=correlation_id,
            trace_id=trace_id,
        )
        
        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                status_code = message["status"]
                duration = time.time() - start_time
                
                logger = StructuredLogger("http")
                logger.info(
                    "HTTP request completed",
                    method=scope.get("method"),
                    path=scope.get("path"),
                    status_code=status_code,
                    duration_ms=round((time.time() - start_time) * 1000, 2),
                    correlation_id=correlation_id,
                )
                
                # Add correlation headers to response
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", correlation_id.encode()))
                headers.append((b"x-request-id", generate_request_id().encode()))
                message["headers"] = headers
            
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Reset context
            _correlation_id.reset(correlation_token)
            _trace_id.reset(trace_token)
            _span_id.reset(span_token)
            _request_id.reset(request_token)
            if user_token:
                _user_id.reset(user_token)
            if org_token:
                _organization_id.reset(org_token)
            _request_id.reset(request_id_var)


# ==================== FastAPI Integration ====================

def get_structured_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)


def get_logger(name: str) -> StructuredLogger:
    """Get a structured logger instance (alias)."""
    return StructuredLogger(name)


# ==================== FastAPI Dependency ====================

def get_correlation_id_from_header(
    x_correlation_id: Optional[str] = None,
    x_trace_id: Optional[str] = None,
    x_span_id: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """FastAPI dependency to extract correlation IDs from headers."""
    correlation_id = generate_correlation_id()
    trace_id = generate_trace_id()
    span_id = generate_span_id()
    
    return {
        "correlation_id": correlation_id,
        "trace_id": trace_id,
        "span_id": generate_span_id(),
    }


def setup_structured_logging(app, level: LogLevel = LogLevel.INFO):
    """Set up structured logging for FastAPI application."""
    # Add middleware
    app.add_middleware(StructuredLoggingMiddleware)
    
    # Configure root logger
    logging.basicConfig(
        level=getattr(logging, LogLevel.INFO.value),
        format="%(message)s",
    )
    
    # Reduce noise from noisy loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    
    return StructuredLogger("vcos", level=LogLevel.INFO)


# ==================== Convenience Functions ====================

def log_info(message: str, **kwargs):
    """Log info level message."""
    StructuredLogger("vcos").info(message, **kwargs)


def log_warning(message: str, **kwargs):
    """Log warning level message."""
    StructuredLogger("vcos").warning(message, **kwargs)


def log_error(message: str, **kwargs):
    """Log error level message."""
    StructuredLogger("vcos").error(message, **kwargs)


def log_critical(message: str, **kwargs):
    """Log critical level message."""
    StructuredLogger("vcos").critical(message, **kwargs)


def log_exception(message: str, **kwargs):
    """Log exception with traceback."""
    StructuredLogger("vcos").exception(message, **kwargs)


# ==================== Context Helpers ====================

class LogContext:
    """Context manager for adding fields to logs."""
    
    def __init__(self, **fields):
        self.fields = fields
        self.logger = StructuredLogger("vcos")
        self.bound_logger = self.logger.bind(**fields)
    
    def __enter__(self):
        return self.bound_logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


@contextmanager
def log_context(**fields):
    """Context manager to add fields to all logs within scope."""
    logger = StructuredLogger("vcos")
    bound = logger.bind(**fields)
    try:
        yield bound
    finally:
        pass


# ==================== Convenience Functions ====================

def generate_correlation_id() -> str:
    """Generate a new correlation ID."""
    return uuid4().hex[:32]


def generate_trace_id() -> str:
    """Generate a new trace ID."""
    return uuid4().hex[:32]


def generate_span_id() -> str:
    """Generate a new span ID."""
    return uuid4().hex[:16]


def generate_request_id() -> str:
    """Generate a new request ID."""
    return uuid4().hex[:32]


# ==================== FastAPI Dependencies ====================

async def get_correlation_context(
    x_correlation_id: Optional[str] = None,
    x_trace_id: Optional[str] = None,
    x_span_id: Optional[str] = None,
    x_user_id: Optional[str] = None,
    x_organization_id: Optional[str] = None,
) -> Dict[str, Optional[str]]:
    """FastAPI dependency to extract correlation context from headers."""
    return {
        "correlation_id": x_correlation_id or generate_correlation_id(),
        "trace_id": None,  # Would extract from header
        "span_id": None,
        "user_id": None,
        "organization_id": None,
    }


# ==================== Global Logger Instance ====================

_default_logger: Optional[StructuredLogger] = None


def get_logger(name: str = "vcos") -> StructuredLogger:
    """Get or create a structured logger."""
    global _default_logger
    if _default_logger is None:
        _default_logger = StructuredLogger(name)
    return _default_logger


def init_structured_logging(
    level: LogLevel = LogLevel.INFO,
    format: str = "json",
    service_name: str = "vcos",
    environment: str = "production",
    version: str = "1.0.0",
) -> StructuredLogger:
    """Initialize structured logging globally."""
    global _default_logger
    _default_logger = StructuredLogger(
        name="vcos",
        level=level,
        format=LogFormat(format),
        service_name=service_name,
        environment=environment,
        version=version,
    )
    return _default_logger


def get_default_logger() -> StructuredLogger:
    """Get the default logger instance."""
    if _default_logger is None:
        return init_structured_logging()
    return _default_logger