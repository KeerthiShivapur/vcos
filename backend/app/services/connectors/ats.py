"""
ATS Connectors - Universal Integration Platform.

Connectors for Applicant Tracking Systems.
"""

import asyncio
import httpx
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

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
    register_connector,
    connector,
)

from app.services.connectors.base import (
    OAuth2Mixin,
    BaseConnectorWithMixins,
    HTTPClientMixin,
)

logger = logging.getLogger("vcos.integration.connectors.ats")


# ==================== Greenhouse Connector ====================

@connector(
    metadata=ConnectorMetadata(
        id="greenhouse",
        name="Greenhouse",
        display_name="Greenhouse",
        description="Greenhouse Applicant Tracking System",
        category="ats",
        logo_url="https://cdn.vcos.io/connectors/greenhouse.png",
        documentation_url="https://docs.vcos.io/integrations/greenhouse",
        version="1.0.0",
        author="VCOS",
        tags=["ats", "greenhouse", "recruiting", "hiring"],
        auth_schemes=["api_key", "basic_auth"],
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Greenhouse API key"},
            },
            "required": ["api_key"],
        },
    ),
    capabilities=ConnectorCapabilities(
        supported_entities=["person", "job", "application", "candidate", "interview", "offer"],
        supported_operations=["read", "create", "update"],
        supports_incremental=True,
        supports_webhooks=True,
        supports_oauth=False,
    ),
    auth=AuthConfig(scheme="api_key"),
    rate_limit=RateLimitConfig(requests_per_second=10.0, burst_size=20),
    pagination=PaginationConfig(strategy="cursor", cursor_param="page", limit_param="per_page", max_page_size=100),
    retry=RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0),
)
class GreenhouseConnector(BaseConnectorWithMixins):
    """Greenhouse ATS connector."""
    
    BASE_URL = "https://harvest.greenhouse.io/v1"
    
    def __init__(self, context):
        super().__init__(context)
    
    async def authenticate(self) -> bool:
        try:
            response = await self._make_request("GET", "/users/me")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Greenhouse authentication failed: {e}")
            return False
    
    async def validate_config(self) -> bool:
        credentials = self._get_credentials()
        return bool(credentials.get("api_key"))
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = super()._get_default_headers()
        api_key = self._get_credentials().get("api_key")
        if api_key:
            import base64
            auth = base64.b64encode(f"{api_key}:".encode()).decode()
            headers["Authorization"] = f"Basic {auth}"
        return headers
    
    async def _test_connection_impl(self) -> str:
        response = await self._make_request("GET", "/users/me")
        data = response.json()
        return f"Greenhouse connected as {data.get('email', 'unknown')}"
    
    async def fetch_page(
        self,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        
        endpoint_map = {
            EntityType.USER: "users",
            EntityType.CUSTOM: "candidates",
            EntityType.CUSTOM: "jobs",
            EntityType.CUSTOM: "applications",
        }
        
        # Map entity types to Greenhouse endpoints
        if entity_type == EntityType.USER:
            endpoint = "users"
        elif entity_type == EntityType.CUSTOM:
            # Need to determine which custom entity based on context
            endpoint = "candidates"
        else:
            return PageResult()
        
        params = {"per_page": min(page_size, 100)}
        if cursor:
            params["page"] = cursor
        
        response = await self._make_request("GET", f"/{endpoint}", params=params)
        data = response.json()
        
        next_cursor = str(int(cursor or 0) + 1) if len(data) >= page_size else None
        
        return PageResult(
            entities=data,
            next_cursor=next_cursor,
            has_more=bool(next_cursor),
            total_count=len(data),
        )
    
    async def get_initial_cursor(self, entity_type: EntityType) -> str:
        return "1"
    
    async def get_incremental_cursor(self, entity_type: EntityType, cursor: str) -> str:
        return cursor


# ==================== Lever Connector ====================

@connector(
    metadata=ConnectorMetadata(
        id="lever",
        name="Lever",
        display_name="Lever",
        description="Lever Talent Acquisition Suite",
        category="ats",
        logo_url="https://cdn.vcos.io/connectors/lever.png",
        documentation_url="https://docs.vcos.io/integrations/lever",
        version="1.0.0",
        author="VCOS",
        tags=["ats", "lever", "recruiting", "hiring"],
        auth_schemes=["api_key"],
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Lever API key"},
            },
            "required": ["api_key"],
        },
    ),
    capabilities=ConnectorCapabilities(
        supported_entities=["person", "candidate", "job", "application", "interview", "offer"],
        supported_operations=["read", "create", "update"],
        supports_incremental=True,
        supports_webhooks=True,
        supports_oauth=False,
    ),
    auth=AuthConfig(scheme="api_key"),
    rate_limit=RateLimitConfig(requests_per_second=10.0, burst_size=20),
    pagination=PaginationConfig(strategy="cursor", cursor_param="offset", limit_param="limit", max_page_size=100),
    retry=RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0),
)
class LeverConnector(BaseConnectorWithMixins):
    """Lever ATS connector."""
    
    BASE_URL = "https://api.lever.co/v1"
    
    def __init__(self, context):
        super().__init__(context)
    
    async def authenticate(self) -> bool:
        try:
            response = await self._make_request("GET", "/me")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Lever authentication failed: {e}")
            return False
    
    async def validate_config(self) -> bool:
        credentials = self._get_credentials()
        return bool(credentials.get("api_key"))
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = super()._get_default_headers()
        api_key = self._get_credentials().get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers
    
    async def _test_connection_impl(self) -> str:
        response = await self._make_request("GET", "/me")
        data = response.json()
        return f"Lever connected as {data.get('name', 'unknown')}"
    
    async def fetch_page(
        self,
        entity_type: EntityType,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        
        endpoint_map = {
            EntityType.USER: "users",
            EntityType.CUSTOM: "candidates",
            EntityType.CUSTOM: "postings",
            EntityType.CUSTOM: "opportunities",
        }
        
        # Map entity types to Lever endpoints
        if entity_type == EntityType.USER:
            endpoint = "users"
        elif entity_type == EntityType.CUSTOM:
            endpoint = "candidates"
        else:
            return PageResult()
        
        params = {"limit": min(page_size, 100)}
        if cursor:
            params["offset"] = cursor
        
        response = await self._make_request("GET", f"/{endpoint}", params=params)
        data = response.json()
        
        entities = data.get("data", [])
        next_cursor = str(int(cursor or 0) + page_size) if len(entities) >= page_size else None
        
        return PageResult(
            entities=entities,
            next_cursor=next_cursor,
            has_more=bool(next_cursor),
            total_count=len(entities),
        )
    
    async def get_initial_cursor(self, entity_type: EntityType) -> str:
        return "0"
    
    async def get_incremental_cursor(self, entity_type: EntityType, cursor: str) -> str:
        return cursor


# ==================== Ashby Connector ====================

@connector(
    metadata=ConnectorMetadata(
        id="ashby",
        name="Ashby",
        display_name="Ashby",
        description="Ashby Recruiting Platform",
        category="ats",
        logo_url="https://cdn.vcos.io/connectors/ashby.png",
        documentation_url="https://docs.vcos.io/integrations/ashby",
        version="1.0.0",
        author="VCOS",
        tags=["ats", "ashby", "recruiting"],
        auth_schemes=["api_key"],
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Ashby API key"},
            },
            "required": ["api_key"],
        },
    ),
    capabilities=ConnectorCapabilities(
        supported_entities=["person", "candidate", "job", "application", "interview", "offer"],
        supported_operations=["read", "create", "update"],
        supports_incremental=True,
        supports_webhooks=True,
        supports_oauth=False,
    ),
    auth=AuthConfig(scheme="api_key"),
    rate_limit=RateLimitConfig(requests_per_second=10.0, burst_size=20),
    pagination=PaginationConfig(strategy="cursor", cursor_param="cursor", limit_param="limit", max_page_size=100),
    retry=RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0),
)
class AshbyConnector(BaseConnectorWithMixins):
    """Ashby ATS connector."""
    
    BASE_URL = "https://api.ashbyhq.com/v1"
    
    def __init__(self, context):
        super().__init__(context)
    
    async def authenticate(self) -> bool:
        try:
            response = await self._make_request("GET", "/users")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Ashby authentication failed: {e}")
            return False
    
    async def validate_config(self) -> bool:
        credentials = self._get_credentials()
        return bool(credentials.get("api_key"))
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = super()._get_default_headers()
        api_key = self._get_credentials().get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers
    
    async def _test_connection_impl(self) -> str:
        response = await self._make_request("GET", "/users")
        data = response.json()
        return f"Ashby connected, {len(data.get('results', []))} users"
    
    async def fetch_page(
        self,
        entity_type: EntityType,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        
        if entity_type == EntityType.USER:
            endpoint = "users"
        elif entity_type == EntityType.CUSTOM:
            endpoint = "candidates"
        else:
            return PageResult()
        
        params = {"limit": min(page_size, 100)}
        if cursor:
            params["cursor"] = cursor
        
        response = await self._make_request("GET", f"/{endpoint}", params=params)
        data = response.json()
        
        entities = data.get("results", [])
        next_cursor = data.get("nextCursor")
        
        return PageResult(
            entities=entities,
            next_cursor=next_cursor,
            has_more=bool(next_cursor),
            total_count=len(entities),
        )
    
    async def get_initial_cursor(self, entity_type: EntityType) -> str:
        return ""
    
    async def get_incremental_cursor(self, entity_type: EntityType, cursor: str) -> str:
        return cursor


# ==================== Workable Connector ====================

@connector(
    metadata=ConnectorMetadata(
        id="workable",
        name="Workable",
        display_name="Workable",
        description="Workable Recruiting Software",
        category="ats",
        logo_url="https://cdn.vcos.io/connectors/workable.png",
        documentation_url="https://docs.vcos.io/integrations/workable",
        version="1.0.0",
        author="VCOS",
        tags=["ats", "workable", "recruiting"],
        auth_schemes=["api_key"],
        config_schema={
            "type": "object",
            "properties": {
                "subdomain": {"type": "string", "description": "Workable subdomain"},
                "api_key": {"type": "string", "description": "Workable API key"},
            },
            "required": ["subdomain", "api_key"],
        },
    ),
    capabilities=ConnectorCapabilities(
        supported_entities=["person", "candidate", "job", "application", "interview"],
        supported_operations=["read", "create", "update"],
        supports_incremental=True,
        supports_webhooks=True,
        supports_oauth=False,
    ),
    auth=AuthConfig(scheme="api_key"),
    rate_limit=RateLimitConfig(requests_per_second=10.0, burst_size=20),
    pagination=PaginationConfig(strategy="cursor", cursor_param="page", limit_param="per_page", max_page_size=100),
    retry=RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0),
)
class WorkableConnector(BaseConnectorWithMixins):
    """Workable ATS connector."""
    
    BASE_URL = "https://{subdomain}.workable.com/spi/v3"
    
    def __init__(self, context):
        super().__init__(context)
        self._subdomain = None
    
    async def authenticate(self) -> bool:
        self._subdomain = self._get_config().get("subdomain")
        if not self._subdomain:
            raise RuntimeError("Workable subdomain not configured")
        
        try:
            response = await self._make_request("GET", "/account")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Workable authentication failed: {e}")
            return False
    
    async def validate_config(self) -> bool:
        config = self._get_config()
        credentials = self._get_credentials()
        return bool(config.get("subdomain") and credentials.get("api_key"))
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = super()._get_default_headers()
        api_key = self._get_credentials().get("api_key")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers
    
    @property
    def BASE_URL(self) -> str:
        return f"https://{self._get_config().get('subdomain')}.workable.com/spi/v3"
    
    async def _test_connection_impl(self) -> str:
        response = await self._make_request("GET", "/account")
        data = response.json()
        return f"Workable connected for {data.get('account', {}).get('name', 'unknown')}"
    
    async def fetch_page(
        self,
        entity_type: EntityType,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        
        if entity_type == "person":
            endpoint = "members"
        elif entity_type == "candidate":
            endpoint = "candidates"
        else:
            return PageResult()
        
        params = {"page": int(cursor or 0) + 1, "per_page": min(page_size, 100)}
        
        response = await self._make_request("GET", f"/{endpoint}", params=params)
        data = response.json()
        
        entities = data.get("candidates", data.get("members", []))
        next_cursor = str(int(cursor or 0) + 1) if len(data.get("candidates", [])) >= page_size else None
        
        return PageResult(
            entities=entities,
            next_cursor=next_cursor,
            has_more=bool(next_cursor),
            total_count=len(entities),
        )
    
    async def get_initial_cursor(self, entity_type: EntityType) -> str:
        return "1"
    
    async def get_incremental_cursor(self, entity_type: EntityType, cursor: str) -> str:
        return cursor


# ==================== SmartRecruiters Connector ====================

@connector(
    metadata=ConnectorMetadata(
        id="smartrecruiters",
        name="SmartRecruiters",
        display_name="SmartRecruiters",
        description="SmartRecruiters Talent Acquisition Suite",
        category="ats",
        logo_url="https://cdn.vcos.io/connectors/smartrecruiters.png",
        documentation_url="https://docs.vcos.io/integrations/smartrecruiters",
        version="1.0.0",
        author="VCOS",
        tags=["ats", "smartrecruiters", "recruiting"],
        auth_schemes=["oauth2", "api_key"],
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "OAuth2 client ID"},
                "client_secret": {"type": "string", "description": "OAuth2 client secret"},
            },
            "required": ["client_id", "client_secret"],
        },
        required_scopes=["candidates:read", "jobs:read", "postings:read"],
    ),
    capabilities=ConnectorCapabilities(
        supported_entities=["person", "candidate", "job", "application", "interview"],
        supported_operations=["read", "create", "update"],
        supports_incremental=True,
        supports_webhooks=True,
        supports_oauth=True,
    ),
    auth=AuthConfig(scheme="oauth2"),
    rate_limit=RateLimitConfig(requests_per_second=10.0, burst_size=20),
    pagination=PaginationConfig(strategy="cursor", cursor_param="page", limit_param="limit", max_page_size=100),
    retry=RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0),
)
class SmartRecruitersConnector(BaseConnectorWithMixins):
    """SmartRecruiters ATS connector."""
    
    BASE_URL = "https://api.smartrecruiters.com/v1"
    
    OAUTH_AUTHORIZE_URL = "https://www.smartrecruiters.com/identity/oauth/authorize"
    OAUTH_TOKEN_URL = "https://www.smartrecruiters.com/identity/oauth/token"
    SUPPORTED_SCOPES = ["candidates:read", "jobs:read", "postings:read", "offers:read"]
    
    def __init__(self, context):
        super().__init__(context)
    
    async def authenticate(self) -> bool:
        try:
            response = await self._make_request("GET", "/users/me")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"SmartRecruiters authentication failed: {e}")
            return False
    
    async def validate_config(self) -> bool:
        credentials = self._get_credentials()
        return bool(credentials.get("client_id") and credentials.get("client_secret"))
    
    async def _get_token(self) -> str:
        credentials = self._get_credentials()
        
        if "access_token" in credentials and "expires_at" in credentials:
            expires_at = datetime.fromisoformat(credentials["expires_at"].replace('Z', '+00:00'))
            if expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
                return credentials["access_token"]
        
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        
        if not client_id or not client_secret:
            raise RuntimeError("Missing OAuth client credentials")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://www.smartrecruiters.com/identity/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": credentials["client_id"],
                    "client_secret": credentials["client_secret"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()
            
            self.context.credentials = {
                **self._get_credentials(),
                "access_token": token_data["access_token"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])).isoformat(),
            }
            
            return token_data["access_token"]
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = super()._get_default_headers()
        return headers
    
    async def _make_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        token = await self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        return await super()._make_request(method, path, headers=headers, **kwargs)
    
    async def _test_connection_impl(self) -> str:
        response = await self._make_request("GET", "/users/me")
        data = response.json()
        return f"SmartRecruiters connected as {data.get('email', 'unknown')}"
    
    async def fetch_page(
        self,
        entity_type: EntityType,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        
        if entity_type == "person":
            endpoint = "users"
        elif entity_type == "candidate":
            endpoint = "candidates"
        else:
            return PageResult()
        
        params = {"limit": min(page_size, 100)}
        if cursor:
            params["page"] = cursor
        
        response = await self._make_request("GET", f"/{endpoint}", params=params)
        data = response.json()
        
        entities = data.get("content", data.get("results", []))
        next_cursor = str(int(cursor or 0) + 1) if len(entities) >= page_size else None
        
        return PageResult(
            entities=entities,
            next_cursor=next_cursor,
            has_more=bool(next_cursor),
            total_count=len(entities),
        )
    
    async def get_initial_cursor(self, entity_type: EntityType) -> str:
        return "0"
    
    async def get_incremental_cursor(self, entity_type: EntityType, cursor: str) -> str:
        return cursor