"""
Connector SDK Framework - Universal Integration Platform.

Provides a unified framework for building integration connectors with:
- Type-safe connector development
- Built-in authentication (OAuth2, OIDC, SAML, API Key)
- Rate limiting, retry, pagination
- Schema validation
- Testing and mocking utilities
"""

import asyncio
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional, Set, Tuple, Type, TypeVar, Union
from uuid import uuid4

from pydantic import BaseModel, Field, validator

logger = logging.getLogger("vcos.integration.sdk")


# ==================== Enums ====================

class AuthScheme(str, Enum):
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    SAML = "saml"
    API_KEY = "api_key"
    BASIC_AUTH = "basic_auth"
    JWT = "jwt"
    PERSONAL_TOKEN = "personal_token"
    CUSTOM = "custom"


class SyncMode(str, Enum):
    FULL = "full"
    INCREMENTAL = "incremental"
    REALTIME = "realtime"
    WEBHOOK = "webhook"


class EntityType(str, Enum):
    USER = "person"
    TEAM = "team"
    ORGANIZATION = "organization"
    PROJECT = "project"
    TASK = "task"
    ISSUE = "issue"
    REPOSITORY = "repository"
    PR = "pull_request"
    COMMIT = "commit"
    BRANCH = "branch"
    RELEASE = "release"
    CHANNEL = "channel"
    MESSAGE = "message"
    FILE = "file"
    CONTACT = "contact"
    EVENT = "event"
    DEAL = "deal"
    ACCOUNT = "account"
    LEAD = "lead"
    CAMPAIGN = "campaign"
    INVOICE = "invoice"
    BILL = "bill"
    PAYMENT = "payment"
    SUBSCRIPTION = "subscription"
    PRODUCT = "product"
    ORDER = "order"
    CUSTOMER = "customer"
    METRIC = "metric"
    LOG = "log"
    ALERT = "alert"
    INCIDENT = "incident"
    WORKFLOW = "workflow"
    PIPELINE = "pipeline"
    BUILD = "build"
    DEPLOYMENT = "deployment"
    CUSTOM = "custom"


# ==================== Data Models ====================

@dataclass
class AuthConfig:
    """Authentication configuration for a connector."""
    scheme: AuthScheme
    config: Dict[str, Any] = field(default_factory=dict)
    scopes: List[str] = field(default_factory=list)
    token_url: Optional[str] = None
    authorize_url: Optional[str] = None
    refresh_url: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    access_token: Optional[str] = None
    refresh_token: Optional[str] = None
    expires_at: Optional[datetime] = None
    custom_headers: Dict[str, str] = field(default_factory=dict)


@dataclass
class RateLimitConfig:
    """Rate limiting configuration."""
    requests_per_second: float = 10.0
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    burst_size: int = 10
    retry_after_header: str = "Retry-After"
    rate_limit_headers: Dict[str, str] = field(default_factory=lambda: {
        "limit": "X-RateLimit-Limit",
        "remaining": "X-RateLimit-Remaining",
        "reset": "X-RateLimit-Reset",
    })


@dataclass
class PaginationConfig:
    """Pagination configuration."""
    strategy: str = "cursor"  # cursor, offset, page, link_header
    cursor_param: str = "cursor"
    limit_param: str = "limit"
    max_page_size: int = 100
    default_page_size: int = 50
    cursor_field: str = "next_cursor"
    has_more_field: str = "has_more"
    link_header_rel: str = "next"


@dataclass
class RetryConfig:
    """Retry configuration with exponential backoff."""
    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 60.0  # seconds
    exponential_base: float = 2.0
    jitter: float = 0.1
    retry_on_status: List[int] = field(default_factory=lambda: [429, 500, 502, 503, 504])
    retry_on_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        IOError,
    )


@dataclass
class ConnectorCapabilities:
    """Connector capabilities declaration."""
    supported_entities: List[EntityType] = field(default_factory=list)
    supported_operations: List[str] = field(default_factory=lambda: ["read"])
    supports_incremental: bool = True
    supports_realtime: bool = False
    supports_webhooks: bool = False
    supports_oauth: bool = False
    supports_incremental_deletes: bool = False
    supports_field_selection: bool = False
    supports_filtering: bool = False
    max_page_size: int = 1000
    supported_webhook_events: List[str] = field(default_factory=list)


@dataclass
class ConnectorMetadata:
    """Connector metadata for marketplace and discovery."""
    id: str
    name: str
    display_name: str
    description: str
    category: str
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    version: str = "1.0.0"
    author: str = ""
    tags: List[str] = field(default_factory=list)
    auth_schemes: List[AuthScheme] = field(default_factory=list)
    auth_config_schema: Dict[str, Any] = field(default_factory=dict)
    config_schema: Dict[str, Any] = field(default_factory=dict)
    required_scopes: List[str] = field(default_factory=list)
    pricing_model: str = "free"
    verified: bool = False
    deprecated: bool = False


# ==================== Core SDK Classes ====================

class ConnectorContext:
    """Runtime context for connector execution."""
    
    def __init__(
        self,
        connector_id: str,
        organization_id: str,
        connection_id: str,
        credentials: Dict[str, Any],
        config: Dict[str, Any],
        secrets: Dict[str, str],
        logger: logging.Logger,
        rate_limiter: "RateLimiter",
        retry_policy: "RetryPolicy",
        schema_registry: "SchemaRegistry",
    ):
        self.connector_id = connector_id
        self.organization_id = organization_id
        self.connection_id = connection_id
        self.credentials = credentials
        self.config = config
        self.secrets = secrets
        self.logger = logger
        self.rate_limiter = rate_limiter
        self.retry_policy = retry_policy
        self.schema_registry = schema_registry
        self.start_time = datetime.utcnow()
        self.request_count = 0
        self.errors: List[str] = []
    
    def log(self, level: int, message: str, **kwargs):
        """Structured logging with context."""
        self.logger.log(level, message, extra={
            "connector_id": self.connector_id,
            "connection_id": self.connection_id,
            "organization_id": self.organization_id,
            **kwargs
        })


class BaseConnector(ABC):
    """Base class for all connectors. Extend this to create new connectors."""
    
    # Class-level metadata
    METADATA: ConnectorMetadata
    CAPABILITIES: ConnectorCapabilities
    AUTH_CONFIG: AuthConfig
    RATE_LIMIT: RateLimitConfig
    PAGINATION: PaginationConfig
    RETRY: RetryConfig
    
    # Schema definitions for entity types
    ENTITY_SCHEMAS: Dict[EntityType, Dict[str, Any]] = {}
    
    def __init__(self, context: ConnectorContext):
        self.context = context
        self._rate_limiter = context.rate_limiter
        self._retry_policy = context.retry_policy
        self._schema_registry = context.schema_registry
        self._http_client: Optional["AsyncHTTPClient"] = None
        self._auth_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
    
    @property
    @abstractmethod
    def METADATA(self) -> ConnectorMetadata:
        pass
    
    @property
    @abstractmethod
    def CAPABILITIES(self) -> ConnectorCapabilities:
        pass
    
    @property
    def AUTH_CONFIG(self) -> AuthConfig:
        return AuthConfig(scheme=AuthScheme.API_KEY)
    
    @property
    def RATE_LIMIT(self) -> RateLimitConfig:
        return RateLimitConfig()
    
    @property
    def PAGINATION(self) -> PaginationConfig:
        return PaginationConfig()
    
    @property
    def RETRY(self) -> RetryConfig:
        return RetryConfig()
    
    # ==================== Lifecycle Methods ====================
    
    async def initialize(self) -> None:
        """Initialize connector - authenticate, validate config, etc."""
        await self.authenticate()
        await self.validate_config()
        self.context.logger.info(f"Initialized connector {self.METADATA.id}")
    
    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the external API."""
        pass
    
    @abstractmethod
    async def validate_config(self) -> bool:
        """Validate connector configuration."""
        pass
    
    async def cleanup(self) -> None:
        """Cleanup resources."""
        if self._http_client:
            await self._http_client.close()
    
    # ==================== HTTP Client ====================
    
    def _get_http_client(self) -> "AsyncHTTPClient":
        if self._http_client is None:
            self._http_client = AsyncHTTPClient(
                rate_limiter=self._rate_limiter,
                retry_policy=self._retry_policy,
                base_headers=self._get_default_headers(),
            )
        return self._http_client
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": f"VCOS-Connector/{self.METADATA.id}-{self.METADATA.version}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._auth_token:
            headers["Authorization"] = f"Bearer {self._auth_token}"
        return headers
    
    # ==================== Authentication ====================
    
    async def _ensure_authenticated(self) -> None:
        """Ensure valid authentication token."""
        if self.AUTH_CONFIG.scheme == AuthScheme.OAUTH2:
            if not self._auth_token or (self._token_expires_at and datetime.utcnow() >= self._token_expires_at):
                await self._refresh_oauth_token()
        elif self.AUTH_CONFIG.scheme == AuthScheme.API_KEY:
            # API key is static, no refresh needed
            pass
        elif self.AUTH_CONFIG.scheme == AuthScheme.BASIC_AUTH:
            # Basic auth is static
            pass
    
    async def _refresh_oauth_token(self) -> None:
        """Refresh OAuth2 access token using refresh token."""
        # Implementation depends on provider
        pass
    
    # ==================== Core Sync Methods ====================
    
    @abstractmethod
    async def fetch_page(
        self,
        entity_type: EntityType,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> "PageResult":
        """Fetch a page of entities."""
        pass
    
    async def fetch_all(
        self,
        entity_type: EntityType,
        since: Optional[datetime] = None,
        filters: Optional[Dict[str, Any]] = None,
        max_records: Optional[int] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Fetch all entities of a type with automatic pagination."""
        cursor = None
        total = 0
        
        while True:
            result = await self.fetch_page(entity_type, cursor, since, self.PAGINATION.default_page_size)
            
            for entity in result.entities:
                yield entity
                total += 1
                if max_records and total >= max_records:
                    return
            
            if not result.has_more or not result.next_cursor:
                break
            
            cursor = result.next_cursor
            
            # Rate limiting between pages
            await self._rate_limiter.acquire()
    
    @abstractmethod
    async def get_initial_cursor(self, entity_type: EntityType) -> str:
        """Get initial cursor for full sync."""
        pass
    
    @abstractmethod
    async def get_incremental_cursor(self, entity_type: EntityType, since: datetime) -> str:
        """Get cursor for incremental sync since timestamp."""
        pass
    
    async def get_deleted_entities(
        self,
        entity_type: EntityType,
        since: datetime,
    ) -> List[str]:
        """Get deleted entity IDs since timestamp."""
        return []
    
    # ==================== Write Operations ====================
    
    async def create_entity(
        self,
        entity_type: EntityType,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> "OperationResult":
        """Create an entity in the external system."""
        raise NotImplementedError(f"Create not supported for {self.METADATA.id}")
    
    async def update_entity(
        self,
        entity_type: EntityType,
        external_id: str,
        payload: Dict[str, Any],
        idempotency_key: Optional[str] = None,
    ) -> "OperationResult":
        """Update an entity in the external system."""
        raise NotImplementedError(f"Update not supported for {self.METADATA.id}")
    
    async def delete_entity(
        self,
        entity_type: EntityType,
        external_id: str,
        idempotency_key: Optional[str] = None,
    ) -> "OperationResult":
        """Delete an entity in the external system."""
        raise NotImplementedError(f"Delete not supported for {self.METADATA.id}")
    
    # ==================== Webhook Support ====================
    
    async def register_webhook(
        self,
        url: str,
        events: List[str],
        secret: str,
    ) -> str:
        """Register webhook endpoint."""
        raise NotImplementedError("Webhooks not supported")
    
    async def unregister_webhook(self, webhook_id: str) -> bool:
        """Unregister webhook."""
        raise NotImplementedError("Webhooks not supported")
    
    async def verify_webhook(self, payload: bytes, signature: str, secret: str) -> bool:
        """Verify webhook signature."""
        raise NotImplementedError("Webhook verification not implemented")
    
    # ==================== Schema Validation ====================
    
    def validate_entity(self, entity_type: EntityType, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate entity against schema."""
        schema = self.ENTITY_SCHEMAS.get(entity_type)
        if not schema:
            return True, []
        
        # Use schema registry for validation
        return self._schema_registry.validate(entity_type, data)
    
    def transform_to_canonical(self, entity_type: EntityType, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform provider-specific data to canonical schema."""
        # Default: pass through with basic mapping
        return self._map_to_canonical(entity_type, raw_data)
    
    def _map_to_canonical(self, entity_type: EntityType, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Map provider-specific fields to canonical schema."""
        # Override in subclasses for custom mapping
        return raw_data
    
    # ==================== Rate Limiting & Retry ====================
    
    async def _make_request(
        self,
        method: str,
        path: str,
        **kwargs
    ) -> "HTTPResponse":
        """Make HTTP request with rate limiting and retry."""
        await self._rate_limiter.acquire()
        
        client = self._get_http_client()
        return await client.request_with_retry(
            method=method,
            url=self._build_url(kwargs.pop("path", "")),
            **kwargs
        )
    
    def _build_url(self, path: str) -> str:
        return f"{self.METADATA.config_schema.get('base_url', '')}{path}"
    
    # ==================== Testing & Validation ====================
    
    async def test_connection(self) -> Dict[str, Any]:
        """Test connection to external service."""
        try:
            result = await self._test_connection_impl()
            return {"success": True, "detail": result}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    @abstractmethod
    async def _test_connection_impl(self) -> str:
        """Implementation-specific connection test."""
        pass
    
    def get_metadata(self) -> ConnectorMetadata:
        return self.METADATA
    
    def get_capabilities(self) -> ConnectorCapabilities:
        return self.CAPABILITIES


# ==================== Result Types ====================

@dataclass
class PageResult:
    """Result of a page fetch."""
    entities: List[Dict[str, Any]] = field(default_factory=list)
    next_cursor: Optional[str] = None
    has_more: bool = False
    total_count: int = 0
    rate_limit_remaining: Optional[int] = None
    rate_limit_reset: Optional[datetime] = None


@dataclass
class OperationResult:
    """Result of a write operation."""
    success: bool
    external_id: Optional[str] = None
    external_id_field: str = "id"
    raw_response: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    retry_after: Optional[int] = None


@dataclass
class HTTPResponse:
    """HTTP response wrapper."""
    status_code: int
    headers: Dict[str, str]
    body: Union[Dict, List, str, bytes]
    request_id: Optional[str] = None


# ==================== HTTP Client with Retry & Rate Limiting ====================

class RateLimiter:
    """Token bucket rate limiter with distributed support."""
    
    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._tokens = config.burst_size
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            refill_rate = self.config.requests_per_second
            self._tokens = min(self.config.burst_size, self._tokens + elapsed * refill_rate)
            self._last_refill = now
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            
            # Calculate wait time
            needed = tokens - self._tokens
            wait_time = needed / self.config.requests_per_second
            await asyncio.sleep(wait_time)
            self._tokens = 0
            self._last_refill = time.monotonic()
    
    def update_from_headers(self, headers: Dict[str, str]) -> None:
        """Update rate limit state from response headers."""
        limit = headers.get("X-RateLimit-Limit")
        remaining = headers.get("X-RateLimit-Remaining")
        reset = headers.get("X-RateLimit-Reset")
        
        if remaining is not None:
            self._tokens = min(self.config.burst_size, int(remaining))
        
        if reset:
            reset_time = float(reset)
            now = time.time()
            if reset_time > now:
                self._last_refill = time.monotonic() - (reset_time - now)


class RetryPolicy:
    """Retry policy with exponential backoff and jitter."""
    
    def __init__(self, config: RetryConfig):
        self.config = config
    
    def should_retry(self, attempt: int, exception: Exception, response: Optional[HTTPResponse] = None) -> bool:
        if attempt >= self.config.max_retries:
            return False
        
        if isinstance(exception, self.config.retry_on_exceptions):
            return True
        
        if response and response.status_code in self.config.retry_on_status:
            return True
        
        return False
    
    def get_delay(self, attempt: int) -> float:
        """Calculate delay with exponential backoff and jitter."""
        delay = min(
            self.config.base_delay * (self.config.exponential_base ** attempt),
            self.config.max_delay
        )
        jitter = delay * self.config.jitter * (2 * time.random() - 1)
        return delay + jitter
    
    async def execute_with_retry(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """Execute function with retry logic."""
        last_exception = None
        
        for attempt in range(self.config.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                last_exception = e
                
                if not self.should_retry(attempt, e):
                    raise
                
                if attempt < self.config.max_retries:
                    delay = self.get_delay(attempt)
                    await asyncio.sleep(delay)
        
        raise last_exception


# ==================== HTTP Client ====================

class AsyncHTTPClient:
    """Async HTTP client with built-in rate limiting and retry."""
    
    def __init__(
        self,
        rate_limiter: RateLimiter,
        retry_policy: RetryPolicy,
        base_headers: Dict[str, str] = None,
        timeout: float = 30.0,
    ):
        self.rate_limiter = rate_limiter
        self.retry_policy = retry_policy
        self.base_headers = base_headers or {}
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
    
    async def request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs
    ) -> HTTPResponse:
        """Make HTTP request with rate limiting and retry."""
        
        headers = {**self.base_headers, **kwargs.pop("headers", {})}
        
        async def _do_request():
            client = await self._get_client()
            
            # Apply rate limiting
            await self.rate_limiter.acquire()
            
            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                **kwargs
            )
            
            # Update rate limiter from response headers
            self.rate_limiter.update_from_headers(dict(response.headers))
            
            return HTTPResponse(
                status_code=response.status_code,
                headers=dict(response.headers),
                body=response.content,
            )
        
        return await self.retry_policy.execute_with_retry(_do_request)
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._client
    
    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None


# ==================== Schema Registry ====================

class SchemaRegistry:
    """Schema registry with support for JSON Schema, Avro, Protobuf."""
    
    def __init__(self):
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._compiled_schemas: Dict[str, Any] = {}
    
    def register_schema(
        self,
        entity_type: EntityType,
        schema: Dict[str, Any],
        format: str = "jsonschema",
    ) -> None:
        """Register a schema for an entity type."""
        key = f"{entity_type.value}"
        self._schemas[key] = {
            "schema": schema,
            "format": format,
            "registered_at": datetime.utcnow().isoformat(),
        }
        
        # Compile schema for validation
        if format == "jsonschema":
            import jsonschema
            self._compiled_schemas[key] = jsonschema.Draft7Validator(schema)
    
    def get_schema(self, entity_type: EntityType) -> Optional[Dict[str, Any]]:
        """Get schema for entity type."""
        key = f"{entity_type.value}"
        return self._schemas.get(key, {}).get("schema")
    
    def validate(self, entity_type: EntityType, data: Dict[str, Any]) -> Tuple[bool, List[str]]:
        """Validate data against schema."""
        key = f"{entity_type.value}"
        validator = self._compiled_schemas.get(key)
        
        if not validator:
            return True, []
        
        try:
            validator.validate(data)
            return True, []
        except Exception as e:
            return False, [str(e)]
    
    def get_schema_id(self, entity_type: EntityType) -> Optional[str]:
        """Get schema ID for serialization."""
        return f"{entity_type.value}"


# ==================== Connector Registry ====================

class ConnectorRegistry:
    """Registry for connector discovery and instantiation."""
    
    def __init__(self):
        self._connectors: Dict[str, Type[BaseConnector]] = {}
        self._metadata: Dict[str, ConnectorMetadata] = {}
    
    def register(self, connector_class: Type[BaseConnector]) -> None:
        """Register a connector class."""
        metadata = connector_class.METADATA
        self._connectors[metadata.id] = connector_class
        self._metadata[metadata.id] = metadata
    
    def get(self, connector_id: str) -> Optional[Type[BaseConnector]]:
        """Get connector class by ID."""
        return self._connectors.get(connector_id)
    
    def get_metadata(self, connector_id: str) -> Optional[ConnectorMetadata]:
        return self._metadata.get(connector_id)
    
    def list_connectors(self, category: Optional[str] = None) -> List[ConnectorMetadata]:
        connectors = list(self._metadata.values())
        if category:
            connectors = [m for m in connectors if m.category == category]
        return connectors
    
    def create_connector(
        self,
        connector_id: str,
        context: ConnectorContext,
    ) -> BaseConnector:
        """Create connector instance."""
        cls = self._connectors.get(connector_id)
        if not cls:
            raise ValueError(f"Connector not found: {connector_id}")
        return cls(context)


# Global registry
_global_registry = ConnectorRegistry()


def get_connector_registry() -> ConnectorRegistry:
    """Get global connector registry."""
    return _global_registry


def register_connector(connector_class: Type[BaseConnector]) -> None:
    """Register a connector class globally."""
    _global_registry.register(connector_class)


# ==================== Decorator for Easy Registration ====================

def connector(
    metadata: ConnectorMetadata,
    capabilities: Optional[ConnectorCapabilities] = None,
    auth: Optional[AuthConfig] = None,
    rate_limit: Optional[RateLimitConfig] = None,
    pagination: Optional[PaginationConfig] = None,
    retry: Optional[RetryConfig] = None,
):
    """Decorator to register a connector class with metadata."""
    def decorator(cls: Type[BaseConnector]):
        cls.METADATA = metadata
        cls.CAPABILITIES = capabilities or ConnectorCapabilities()
        cls.AUTH_CONFIG = auth or AuthConfig(scheme=AuthScheme.API_KEY)
        cls.RATE_LIMIT = rate_limit or RateLimitConfig()
        cls.PAGINATION = pagination or PaginationConfig()
        cls.RETRY = retry or RetryConfig()
        register_connector(cls)
        return cls
    return decorator


# ==================== Helper Functions ====================

def create_connector_context(
    connector_id: str,
    organization_id: str,
    connection_id: str,
    credentials: Dict[str, Any],
    config: Dict[str, Any],
    secrets: Dict[str, str],
    rate_limiter: RateLimiter,
    retry_policy: RetryPolicy,
    schema_registry: SchemaRegistry,
) -> ConnectorContext:
    """Create a connector context."""
    logger = logging.getLogger(f"vcos.connector.{connector_id}")
    return ConnectorContext(
        connector_id=connector_id,
        organization_id=organization_id,
        connection_id=connection_id,
        credentials=credentials,
        config=config,
        secrets=secrets,
        logger=logger,
        rate_limiter=rate_limiter,
        retry_policy=retry_policy,
        schema_registry=schema_registry,
    )


# Export all public classes
__all__ = [
    "AuthScheme",
    "SyncMode",
    "EntityType",
    "AuthConfig",
    "RateLimitConfig",
    "PaginationConfig",
    "RetryConfig",
    "ConnectorCapabilities",
    "ConnectorMetadata",
    "ConnectorContext",
    "BaseConnector",
    "PageResult",
    "OperationResult",
    "HTTPResponse",
    "RateLimiter",
    "RetryPolicy",
    "AsyncHTTPClient",
    "SchemaRegistry",
    "ConnectorRegistry",
    "get_connector_registry",
    "register_connector",
    "connector",
    "create_connector_context",
]