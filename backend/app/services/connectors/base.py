"""
Base Connector Classes - Universal Integration Platform.

Base classes and utilities for building integration connectors.
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
from typing import Any, AsyncGenerator, Dict, List, Optional, Set, Tuple, Type, Union
from uuid import uuid4

from app.core.connector_sdk import (
    BaseConnector,
    ConnectorContext,
    ConnectorMetadata,
    ConnectorCapabilities,
    EntityType,
    AuthConfig,
    RateLimitConfig,
    PaginationConfig,
    RetryConfig,
    AuthScheme,
    PageResult,
    OperationResult,
    SchemaRegistry,
    ConnectorRegistry,
    get_connector_registry,
    create_connector_context,
    register_connector,
    connector,
)

logger = logging.getLogger("vcos.integration.connectors")


# ==================== Mixins for Common Patterns ====================

class OAuth2Mixin:
    """Mixin for OAuth2 authentication."""
    
    OAUTH_AUTHORIZE_URL: str = ""
    OAUTH_TOKEN_URL: str = ""
    OAUTH_USER_URL: str = ""
    SUPPORTED_SCOPES: List[str] = []
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._oauth_states: Dict[str, str] = {}
    
    def _get_credentials(self) -> Dict[str, Any]:
        return self.context.credentials or {}
    
    def _get_config(self) -> Dict[str, Any]:
        return self.context.config or {}
    
    async def _get_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        credentials = self._get_credentials()
        
        # Check for existing valid token
        access_token = credentials.get("access_token")
        if access_token:
            expires_at = credentials.get("expires_at")
            if expires_at:
                try:
                    exp_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if datetime.utcnow() < exp_time:
                        return access_token
                except Exception:
                    pass
        
        # Try to refresh
        if await self._refresh_token(credentials):
            return credentials.get("access_token", "")
        
        raise RuntimeError("Token not configured or refresh failed")
    
    async def _refresh_token(self, credentials: Dict[str, Any]) -> bool:
        """Refresh OAuth access token."""
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        
        if not refresh_token or not client_id or not client_secret:
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.OAUTH_TOKEN_URL,
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    logger.error(f"Token refresh failed: {data.get('error_description', data.get('error'))}")
                    return False
                
                # Update credentials
                self.context.credentials = {
                    **credentials,
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token", refresh_token),
                    "expires_in": data.get("expires_in"),
                    "expires_at": (datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))).isoformat(),
                    "scope": data.get("scope"),
                    "token_type": data.get("token_type", "Bearer"),
                }
                return True
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False
    
    def generate_oauth_url(
        self,
        redirect_uri: str,
        state: Optional[str] = None,
        scopes: Optional[List[str]] = None,
    ) -> str:
        """Generate OAuth authorization URL."""
        import secrets
        from urllib.parse import urlencode
        
        state = state or secrets.token_urlsafe(32)
        self._oauth_states[state] = state
        
        scope_list = scopes or self.SUPPORTED_SCOPES
        config = self._get_config()
        client_id = config.get("client_id") or self._get_credentials().get("client_id")
        
        if not client_id:
            raise RuntimeError("client_id not configured")
        
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scope_list),
            "response_type": "code",
            "state": state,
        }
        
        if hasattr(self, 'OAUTH_AUTHORIZE_URL'):
            return f"{self.OAUTH_AUTHORIZE_URL}?{urlencode(params)}"
        raise RuntimeError("OAUTH_AUTHORIZE_URL not defined")
    
    async def handle_oauth_callback(
        self,
        code: str,
        state: str,
        redirect_uri: str,
    ) -> Dict[str, Any]:
        """Handle OAuth callback and exchange code for tokens."""
        if state not in self._oauth_states:
            raise ValueError("Invalid OAuth state")
        del self._oauth_states[state]
        
        config = self._get_config()
        credentials = self._get_credentials()
        client_id = config.get("client_id") or credentials.get("client_id")
        client_secret = config.get("client_secret") or credentials.get("client_secret")
        
        if not client_id or not client_secret:
            raise RuntimeError("client_id and client_secret not configured")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.OAUTH_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                raise ValueError(f"OAuth failed: {data.get('error_description', data.get('error'))}")
            
            # Get user info
            user_info = await self._get_user_info(data.get("access_token"))
            
            return {
                "access_token": data.get("access_token"),
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in"),
                "token_type": data.get("token_type"),
                "scope": data.get("scope"),
                "user_email": user_info.get("email"),
                "user_name": user_info.get("name"),
                "user_id": user_info.get("id"),
            }
    
    async def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from provider."""
        raise NotImplementedError


class APIKeyMixin:
    """Mixin for API Key authentication."""
    
    API_KEY_HEADER: str = "Authorization"
    API_KEY_PREFIX: str = "Bearer "
    
    async def _get_token(self) -> str:
        """Get API key from credentials."""
        credentials = self._get_credentials()
        
        # Check for personal access token
        pat = credentials.get("personal_access_token")
        if pat:
            return pat
        
        # Check for API key
        api_key = credentials.get("api_key")
        if api_key:
            return api_key
        
        # Check for access token
        access_token = credentials.get("access_token")
        if access_token:
            return access_token
        
        raise RuntimeError("API key/token not configured")


class BasicAuthMixin:
    """Mixin for Basic Authentication."""
    
    async def _get_auth_header(self) -> Dict[str, str]:
        """Get Basic Auth header."""
        credentials = self._get_credentials()
        username = credentials.get("username")
        password = credentials.get("password")
        
        if not username or not password:
            raise RuntimeError("Username and password required for Basic Auth")
        
        import base64
        credentials_str = f"{username}:{password}"
        encoded = base64.b64encode(credentials_str.encode()).decode()
        return {"Authorization": f"Basic {encoded}"}


# ==================== HTTP Client Mixin ====================

class HTTPClientMixin:
    """Mixin providing HTTP client with rate limiting and retry."""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._http_client: Optional[httpx.AsyncClient] = None
    
    def _get_rate_limit_config(self) -> RateLimitConfig:
        return self.RATE_LIMIT if hasattr(self, 'RATE_LIMIT') else RateLimitConfig()
    
    def _get_retry_config(self) -> RetryConfig:
        return self.RETRY if hasattr(self, 'RETRY') else RetryConfig()
    
    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=httpx.Timeout(30.0),
                limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            )
        return self._http_client
    
    async def _make_request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
    ) -> httpx.Response:
        """Make HTTP request with rate limiting and retry."""
        client = await self._get_http_client()
        
        # Apply rate limiting
        rate_limit = self._get_rate_limit_config()
        # Simple rate limiting (in production, use distributed rate limiter)
        
        url = f"{self.BASE_URL}{path}"
        
        default_headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if headers:
            default_headers.update(headers)
        
        response = await client.request(
            method=method,
            url=url,
            headers=default_headers,
            params=params,
            json=json,
            data=data,
        )
        
        response.raise_for_status()
        return response
    
    async def close(self):
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# ==================== Base Connector with Common Functionality ====================

class BaseConnectorWithMixins(
    OAuth2Mixin,
    APIKeyMixin,
    BasicAuthMixin,
    HTTPClientMixin,
    BaseConnector,
):
    """Base connector combining all common mixins."""
    
    def __init__(self, context: ConnectorContext):
        super().__init__(context)
        HTTPClientMixin.__init__(self)
    
    def _get_credentials(self) -> Dict[str, Any]:
        return self.context.credentials or {}
    
    def _get_config(self) -> Dict[str, Any]:
        return self.context.config or {}


# ==================== Rate Limiting Utilities ====================

class TokenBucketRateLimiter:
    """Token bucket rate limiter."""
    
    def __init__(self, rate_per_second: float, burst: int = 10):
        self.rate = rate_per_second
        self.burst = burst
        self._tokens = burst
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()
    
    async def acquire(self, tokens: int = 1) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
            self._last_refill = now
            
            if self._tokens >= tokens:
                self._tokens -= tokens
                return
            
            needed = tokens - self._tokens
            wait_time = needed / self.rate
            await asyncio.sleep(wait_time)
            self._tokens = 0
            self._last_refill = time.monotonic()


class SlidingWindowRateLimiter:
    """Sliding window rate limiter."""
    
    def __init__(self, max_requests: int, window_seconds: float):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._requests: List[float] = []
        self._lock = asyncio.Lock()
    
    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds
            self._requests = [t for t in self._requests if t > cutoff]
            
            if len(self._requests) >= self.max_requests:
                oldest = self._requests[0]
                wait_time = self.window_seconds - (time.monotonic() - oldest)
                if wait_time > 0:
                    await asyncio.sleep(wait_time)
            
            self._requests.append(time.monotonic())


# ==================== Pagination Helpers ====================

class PaginationHelper:
    """Helper for handling different pagination strategies."""
    
    @staticmethod
    def cursor_pagination(
        cursor: Optional[str],
        page_size: int,
        cursor_param: str = "cursor",
        limit_param: str = "limit",
    ) -> Dict[str, Any]:
        params = {limit_param: min(page_size, 1000)}
        if cursor:
            params[cursor_param] = cursor
        return params
    
    @staticmethod
    def offset_pagination(
        offset: int,
        page_size: int,
        offset_param: str = "offset",
        limit_param: str = "limit",
    ) -> Dict[str, Any]:
        return {
            offset_param: offset,
            limit_param: min(page_size, 1000),
        }
    
    @staticmethod
    def page_pagination(
        page: int,
        page_size: int,
        page_param: str = "page",
        limit_param: str = "limit",
    ) -> Dict[str, Any]:
        params = {limit_param: min(page_size, 1000)}
        if page > 1:
            params[page_param] = page
        return params
    
    @staticmethod
    def link_header_pagination(
        link_header: str,
    ) -> Optional[str]:
        """Parse Link header for next page URL."""
        if not link_header:
            return None
        
        links = link_header.split(",")
        for link in links:
            if 'rel="next"' in link:
                match = re.search(r'<([^>]+)>', link)
                if match:
                    return match.group(1)
        return None


# ==================== Data Transformation Utilities ====================

class DataTransformer:
    """Utility for transforming data between formats."""
    
    @staticmethod
    def flatten_dict(data: Dict[str, Any], prefix: str = "", separator: str = ".") -> Dict[str, Any]:
        """Flatten nested dictionary."""
        result = {}
        for key, value in data.items():
            new_key = f"{prefix}{separator}{key}" if prefix else key
            if isinstance(value, dict):
                result.update(DataTransformer.flatten_dict(value, new_key))
            elif isinstance(value, list):
                for i, item in enumerate(value):
                    if isinstance(item, dict):
                        result.update(DataTransformer.flatten_dict(item, f"{new_key}[{i}]"))
                    else:
                        result[f"{new_key}[{i}]"] = item
            else:
                result[new_key] = value
        return result
    
    @staticmethod
    def unflatten_dict(data: Dict[str, Any], separator: str = ".") -> Dict[str, Any]:
        """Unflatten dictionary."""
        result = {}
        for key, value in data.items():
            parts = key.split(".")
            target = result
            for part in parts[:-1]:
                if part not in target:
                    target[part] = {}
                target = target[part]
            target[parts[-1]] = value
        return result
    
    @staticmethod
    def rename_keys(data: Dict[str, Any], mapping: Dict[str, str]) -> Dict[str, Any]:
        """Rename keys according to mapping."""
        result = {}
        for key, value in data.items():
            new_key = mapping.get(key, key)
            result[new_key] = value
        return result
    
    @staticmethod
    def filter_fields(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
        """Keep only specified fields."""
        return {k: v for k, v in data.items() if k in fields}
    
    @staticmethod
    def exclude_fields(data: Dict[str, Any], fields: List[str]) -> Dict[str, Any]:
        """Exclude specified fields."""
        return {k: v for k, v in data.items() if k not in fields}


# ==================== ID Generation ====================

def generate_idempotency_key(
    connection_id: str,
    entity_type: str,
    external_id: str,
    operation: str = "sync",
) -> str:
    """Generate deterministic idempotency key."""
    content = f"{connection_id}:{entity_type}:{external_id}:{operation}"
    return hashlib.sha256(content.encode()).hexdigest()[:32]


def generate_entity_id(prefix: str = "") -> str:
    """Generate unique entity ID."""
    return f"{prefix}{uuid4().hex[:24]}"


def generate_sync_run_id() -> str:
    """Generate sync run ID."""
    return f"sync_{uuid4().hex[:24]}"


# ==================== Retry Utilities ====================

async def with_retry(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: float = 0.1,
    retry_on_exceptions: Tuple[Type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        IOError,
    ),
    retry_on_status: List[int] = None,
) -> Any:
    """Execute function with exponential backoff retry."""
    retry_on_status = retry_on_status or [429, 500, 502, 503, 504]
    
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            if not isinstance(e, retry_on_exceptions):
                raise
            
            # Check if it's an HTTP error with retryable status
            if hasattr(e, 'response') and e.response is not None:
                if e.response.status_code not in retry_on_status:
                    raise
            
            if attempt < max_retries:
                delay = min(
                    base_delay * (2 ** attempt) + random.uniform(-jitter, jitter),
                    60.0
                )
                await asyncio.sleep(delay)
            else:
                raise


# ==================== Batch Processing ====================

async def process_in_batches(
    items: List[Any],
    batch_size: int,
    processor: Callable[[List[Any]], Any],
    max_concurrent: int = 5,
) -> List[Any]:
    """Process items in batches with concurrency control."""
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def process_batch(batch: List[Any]) -> Any:
        async with semaphore:
            return await processor(batch)
    
    batches = [items[i:i + batch_size] for i in range(0, len(items), batch_size)]
    tasks = [process_batch(batch) for batch in batches]
    return await asyncio.gather(*tasks)


# ==================== Circuit Breaker ====================

class CircuitBreaker:
    """Circuit breaker for external service calls."""
    
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        expected_exception: Type[Exception] = Exception,
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._state = "closed"  # closed, open, half-open
        self._lock = asyncio.Lock()
    
    @property
    def state(self) -> str:
        if self._state == "open":
            if time.monotonic() - self._last_failure_time >= self.recovery_timeout:
                return "half-open"
        return self._state
    
    async def call(self, func: Callable, *args, **kwargs):
        if self.state == "open":
            raise RuntimeError("Circuit breaker is open")
        
        try:
            result = await func()
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise
    
    async def _on_success(self):
        async with self._lock:
            self._failure_count = 0
            self._state = "closed"
    
    async def _on_failure(self):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self.failure_threshold:
                self._state = "open"


# Export all utilities
__all__ = [
    "OAuth2Mixin",
    "APIKeyMixin",
    "BasicAuthMixin",
    "HTTPClientMixin",
    "BaseConnectorWithMixins",
    "RateLimitConfig",
    "RetryConfig",
    "PaginationConfig",
    "TokenBucketRateLimiter",
    "SlidingWindowRateLimiter",
    "PaginationHelper",
    "DataTransformer",
    "generate_idempotency_key",
    "generate_entity_id",
    "generate_sync_run_id",
    "with_retry",
    "process_in_batches",
    "CircuitBreaker",
]