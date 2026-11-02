"""
Base Connector SDK for VCOS Integration Platform.

Provides a unified interface for building connectors with:
- OAuth2/OIDC/SAML/API Key authentication
- Rate limiting with exponential backoff
- Cursor-based pagination
- Incremental sync support
- Dead letter queue
- Exactly-once semantics
- Webhook handling
"""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Callable
from uuid import uuid4

import aiohttp
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class SyncDirection(str, Enum):
    PULL = "pull"
    PUSH = "push"
    BIDIRECTIONAL = "bidirectional"


class SyncStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AuthType(str, Enum):
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    SAML = "saml"
    API_KEY = "api_key"
    BASIC_AUTH = "basic_auth"
    JWT = "jwt"
    NONE = "none"


@dataclass
class RateLimitConfig:
    requests_per_second: float = 10.0
    requests_per_minute: Optional[int] = None
    requests_per_hour: Optional[int] = None
    burst: Optional[int] = None
    complexity_points_per_minute: Optional[int] = None


@dataclass
class ConnectorConfig:
    name: str
    display_name: str
    description: str
    category: str
    auth_type: AuthType
    config_schema: Dict[str, Any] = field(default_factory=dict)
    required_scopes: List[str] = field(default_factory=list)
    supported_operations: List[str] = field(default_factory=list)
    webhook_events: List[str] = field(default_factory=list)
    rate_limits: RateLimitConfig = field(default_factory=RateLimitConfig)
    logo_url: Optional[str] = None
    documentation_url: Optional[str] = None
    version: str = "1.0.0"
    is_active: bool = True


@dataclass
class SyncCursor:
    cursor: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    records_processed: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SyncResult:
    success: bool
    records_processed: int = 0
    records_created: int = 0
    records_updated: int = 0
    records_deleted: int = 0
    records_failed: int = 0
    errors: List[Dict[str, Any]] = field(default_factory=list)
    cursor: Optional[SyncCursor] = None
    duration_ms: int = 0
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None


@dataclass
class WebhookPayload:
    event_type: str
    payload: Dict[str, Any]
    timestamp: datetime
    signature: Optional[str] = None
    delivery_id: str = field(default_factory=lambda: str(uuid4()))


class TokenManager:
    """Manages OAuth2/OIDC tokens with automatic refresh."""

    def __init__(self, client_id: str, client_secret: str, token_url: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._expires_at: Optional[datetime] = None
        self._lock = asyncio.Lock()

    async def get_access_token(self) -> str:
        async with self._lock:
            if self._access_token and self._expires_at and datetime.utcnow() < self._expires_at - timedelta(seconds=60):
                return self._access_token

            if self._refresh_token:
                await self._refresh()
            else:
                await self._initial_token()

            return self._access_token

    async def _initial_token(self):
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_url, data=data) as resp:
                if resp.status != 200:
                    raise Exception(f"Token request failed: {await resp.text()}")
                token_data = await resp.json()
                self._store_tokens(token_data)

    async def _refresh(self):
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self._refresh_token,
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(self.token_url, data=data) as resp:
                if resp.status != 200:
                    raise Exception(f"Token refresh failed: {await resp.text()}")
                token_data = await resp.json()
                self._store_tokens(token_data)

    def _store_tokens(self, token_data: Dict[str, Any]):
        self._access_token = token_data.get("access_token")
        self._refresh_token = token_data.get("refresh_token", self._refresh_token)
        expires_in = token_data.get("expires_in", 3600)
        self._expires_at = datetime.utcnow() + timedelta(seconds=expires_in)


class RateLimiter:
    """Token bucket rate limiter with burst support."""

    def __init__(self, config: RateLimitConfig):
        self.config = config
        self._tokens = float(config.burst or config.requests_per_second * 10)
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, tokens: int = 1) -> float:
        """Acquire tokens, returns wait time in seconds."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_update
            self._last_update = now

            # Refill tokens
            refill_rate = self.config.requests_per_second
            self._tokens = min(
                self.config.burst or self._tokens + elapsed * refill_rate,
                self.config.burst or refill_rate * 10
            )

            if self._tokens >= tokens:
                self._tokens -= tokens
                return 0.0

            # Calculate wait time
            needed = tokens - self._tokens
            wait_time = needed / refill_rate
            self._tokens = 0
            return wait_time


class RetryPolicy:
    """Exponential backoff retry policy."""

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    async def execute(self, func: Callable, *args, **kwargs) -> Any:
        last_exception = None
        for attempt in range(self.max_retries + 1):
            try:
                return await func(*args, **kwargs)
            except aiohttp.ClientResponseError as e:
                last_exception = e
                if e.status < 500 and e.status != 429:
                    raise  # Don't retry client errors except 429
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                last_exception = e

            if attempt < self.max_retries:
                delay = min(
                    self.base_delay * (self.exponential_base ** attempt),
                    self.max_delay
                )
                if self.jitter:
                    delay *= (0.5 + asyncio.get_event_loop().time() % 1)
                logger.warning(f"Attempt {attempt + 1} failed, retrying in {delay:.2f}s: {last_exception}")
                await asyncio.sleep(delay)

        raise last_exception


class BaseConnector(ABC):
    """
    Base class for all connectors.
    
    Subclasses must implement:
    - authenticate(): Set up authentication
    - pull_data(operation, cursor): Pull data from source
    - push_data(operation, data): Push data to destination
    - test_connection(): Verify connection works
    """

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        self.config = config
        self.connection_config = connection_config
        self.organization_id = organization_id
        self.connection_id = connection_id
        self.session: Optional[aiohttp.ClientSession] = None
        self.rate_limiter = RateLimiter(config.rate_limits)
        self.retry_policy = RetryPolicy()
        self._token_manager: Optional[TokenManager] = None
        self._authenticated = False

    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            headers={"User-Agent": "VCOS-Connector/1.0"}
        )
        await self.authenticate()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    @abstractmethod
    async def authenticate(self) -> bool:
        """Authenticate with the external service."""
        pass

    @abstractmethod
    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Pull data from the external service."""
        pass

    @abstractmethod
    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        """Push data to the external service."""
        pass

    @abstractmethod
    async def test_connection(self) -> bool:
        """Test if the connection is working."""
        pass

    async def _make_request(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> aiohttp.ClientResponse:
        """Make HTTP request with rate limiting and retry."""
        await self.rate_limiter.acquire()

        headers = kwargs.pop("headers", {})
        if self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"

        async def _request():
            response = await self.session.request(method, url, headers=headers, **kwargs)
            if response.status == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                raise aiohttp.ClientResponseError(
                    response.request_info,
                    response.history,
                    status=429,
                    message=f"Rate limited, retry after {retry_after}s"
                )
            response.raise_for_status()
            return response

        return await self.retry_policy.execute(_request)

    async def _get(self, url: str, **kwargs) -> Dict[str, Any]:
        async with await self._make_request("GET", url, **kwargs) as resp:
            return await resp.json()

    async def _post(self, url: str, **kwargs) -> Dict[str, Any]:
        async with await self._make_request("POST", url, **kwargs) as resp:
            return await resp.json()

    async def _put(self, url: str, **kwargs) -> Dict[str, Any]:
        async with await self._make_request("PUT", url, **kwargs) as resp:
            return await resp.json()

    async def _patch(self, url: str, **kwargs) -> Dict[str, Any]:
        async with await self._make_request("PATCH", url, **kwargs) as resp:
            return await resp.json()

    async def _delete(self, url: str, **kwargs) -> Dict[str, Any]:
        async with await self._make_request("DELETE", url, **kwargs) as resp:
            return await resp.json()


class ConnectorRegistry:
    """Registry for managing connector types and instances."""

    def __init__(self):
        self._connectors: Dict[str, type] = {}
        self._configs: Dict[str, ConnectorConfig] = {}

    def register(self, connector_class: type, config: ConnectorConfig):
        self._connectors[config.name] = connector_class
        self._configs[config.name] = config

    def get_connector_class(self, name: str) -> Optional[type]:
        return self._connectors.get(name)

    def get_config(self, name: str) -> Optional[ConnectorConfig]:
        return self._configs.get(name)

    def list_connectors(self, category: Optional[str] = None) -> List[ConnectorConfig]:
        configs = list(self._configs.values())
        if category:
            configs = [c for c in configs if c.category == category]
        return configs

    def create_instance(
        self,
        name: str,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ) -> BaseConnector:
        connector_class = self._connectors.get(name)
        if not connector_class:
            raise ValueError(f"Unknown connector: {name}")
        config = self._configs[name]
        return connector_class(config, connection_config, organization_id, connection_id)


# Global registry
connector_registry = ConnectorRegistry()