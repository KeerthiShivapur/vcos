"""
Calendar Connectors - Universal Integration Platform.

Connectors for Calendar and Scheduling platforms.
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

logger = logging.getLogger("vcos.integration.connectors.calendar")


# ==================== Google Calendar Connector ====================

@connector(
    metadata=ConnectorMetadata(
        id="google_calendar",
        name="Google Calendar",
        display_name="Google Calendar",
        description="Google Calendar API",
        category="calendar",
        logo_url="https://cdn.vcos.io/connectors/google_calendar.png",
        documentation_url="https://docs.vcos.io/integrations/google_calendar",
        version="1.0.0",
        author="VCOS",
        tags=["calendar", "google", "scheduling", "events"],
        auth_schemes=["oauth2"],
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "OAuth2 client ID"},
                "client_secret": {"type": "string", "description": "OAuth2 client secret"},
                "redirect_uri": {"type": "string", "description": "OAuth2 redirect URI"},
            },
            "required": ["client_id", "client_secret", "redirect_uri"],
        },
        required_scopes=[
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events.readonly",
        ],
    ),
    capabilities=ConnectorCapabilities(
        supported_entities=["event", "calendar", "attendee", "reminder"],
        supported_operations=["read", "create", "update", "delete"],
        supports_incremental=True,
        supports_webhooks=True,
        supports_oauth=True,
        supports_realtime=True,
    ),
    auth=AuthConfig(scheme="oauth2"),
    rate_limit=RateLimitConfig(requests_per_second=10.0, burst_size=20),
    pagination=PaginationConfig(strategy="cursor", cursor_param="pageToken", limit_param="pageSize", max_page_size=250),
    retry=RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0),
)
class GoogleCalendarConnector(BaseConnectorWithMixins):
    """Google Calendar connector."""
    
    BASE_URL = "https://www.googleapis.com"
    
    OAUTH_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
    OAUTH_USER_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    SUPPORTED_SCOPES = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]
    
    def __init__(self, context):
        super().__init__(context)
        self._token = None
        self._token_expires = None
    
    async def authenticate(self) -> bool:
        try:
            token = await self._get_token()
            return bool(token)
        except Exception as e:
            logger.error(f"Google Calendar authentication failed: {e}")
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
        
        # Refresh token
        refresh_token = credentials.get("refresh_token")
        if not refresh_token:
            raise RuntimeError("No refresh token available")
        
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        
        if not client_id or not client_secret:
            raise RuntimeError("Missing OAuth client credentials")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://oauth2.googleapis.com/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": credentials["refresh_token"],
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            response.raise_for_status()
            token_data = response.json()
            
            self.context.credentials = {
                **credentials,
                "access_token": token_data["access_token"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])).isoformat(),
            }
            
            if "refresh_token" in token_data:
                self.context.credentials["refresh_token"] = token_data["refresh_token"]
            
            return token_data["access_token"]
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = super()._get_default_headers()
        # Token added per-request
        return headers
    
    async def _make_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        token = await self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        return await super()._make_request(method, path, headers=headers, **kwargs)
    
    async def _test_connection_impl(self) -> str:
        response = await self._make_request("GET", "/calendar/v3/calendars/primary")
        return "Google Calendar connected"
    
    async def fetch_page(
        self,
        entity_type: EntityType,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        
        if entity_type == EntityType.EVENT:
            endpoint = "calendar/v3/calendars/primary/events"
        elif entity_type == EntityType.CUSTOM:
            endpoint = "calendar/v3/calendars"
        else:
            return PageResult()
        
        params = {"maxResults": min(page_size, 250)}
        if cursor:
            params["pageToken"] = cursor
        if since:
            params["timeMin"] = since.isoformat() + "Z"
        
        response = await self._make_request("GET", f"/{endpoint}", params=params)
        data = response.json()
        
        entities = data.get("items", [])
        next_cursor = data.get("nextPageToken")
        
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


# ==================== Outlook Calendar Connector ====================

@connector(
    metadata=ConnectorMetadata(
        id="outlook_calendar",
        name="Outlook Calendar",
        display_name="Outlook Calendar",
        description="Microsoft Outlook Calendar (Microsoft Graph API)",
        category="calendar",
        logo_url="https://cdn.vcos.io/connectors/outlook_calendar.png",
        documentation_url="https://docs.vcos.io/integrations/outlook_calendar",
        version="1.0.0",
        author="VCOS",
        tags=["calendar", "outlook", "microsoft", "scheduling"],
        auth_schemes=["oauth2"],
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "OAuth2 client ID"},
                "client_secret": {"type": "string", "description": "OAuth2 client secret"},
                "redirect_uri": {"type": "string", "description": "OAuth2 redirect URI"},
                "tenant_id": {"type": "string", "description": "Microsoft 365 tenant ID"},
            },
            "required": ["client_id", "client_secret", "redirect_uri", "tenant_id"],
        },
        required_scopes=[
            "https://graph.microsoft.com/Calendars.Read",
            "https://graph.microsoft.com/Calendars.ReadWrite",
            "https://graph.microsoft.com/User.Read",
        ],
    ),
    capabilities=ConnectorCapabilities(
        supported_entities=["event", "calendar", "attendee", "reminder"],
        supported_operations=["read", "create", "update", "delete"],
        supports_incremental=True,
        supports_webhooks=True,
        supports_oauth=True,
        supports_realtime=True,
    ),
    auth=AuthConfig(scheme="oauth2"),
    rate_limit=RateLimitConfig(requests_per_second=10.0, burst_size=20),
    pagination=PaginationConfig(strategy="cursor", cursor_param="$skiptoken", limit_param="$top", max_page_size=100),
    retry=RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0),
)
class OutlookCalendarConnector(BaseConnectorWithMixins):
    """Microsoft Outlook Calendar connector (Microsoft Graph API)."""
    
    BASE_URL = "https://graph.microsoft.com/v1.0"
    
    OAUTH_AUTHORIZE_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    OAUTH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    OAUTH_USER_URL = "https://graph.microsoft.com/v1.0/me"
    
    SUPPORTED_SCOPES = [
        "https://graph.microsoft.com/Calendars.Read",
        "https://graph.microsoft.com/Calendars.ReadWrite",
        "https://graph.microsoft.com/User.Read",
    ]
    
    def __init__(self, context):
        super().__init__(context)
        self._tenant_id = None
    
    @property
    def BASE_URL(self) -> str:
        return "https://graph.microsoft.com/v1.0"
    
    async def authenticate(self) -> bool:
        config = self._get_config()
        self._tenant_id = config.get("tenant_id")
        if not self._tenant_id:
            raise RuntimeError("Microsoft tenant_id not configured")
        
        try:
            response = await self._make_request("GET", "/me")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Outlook Calendar authentication failed: {e}")
            return False
    
    async def validate_config(self) -> bool:
        config = self._get_config()
        credentials = self._get_credentials()
        return bool(
            config.get("tenant_id") and
            config.get("client_id") and
            config.get("client_secret") and
            (credentials.get("access_token") or credentials.get("refresh_token"))
        )
    
    async def _get_token(self) -> str:
        credentials = self._get_credentials()
        
        if "access_token" in credentials and "expires_at" in credentials:
            expires_at = datetime.fromisoformat(credentials["expires_at"].replace('Z', '+00:00'))
            if expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
                return credentials["access_token"]
        
        # Refresh token
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        tenant_id = self._get_config().get("tenant_id")
        
        if not all([refresh_token, client_id, client_secret, tenant_id]):
            raise RuntimeError("Missing Microsoft OAuth credentials")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                },
            )
            response.raise_for_status()
            token_data = response.json()
            
            self.context.credentials = {
                **credentials,
                "access_token": token_data["access_token"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])).isoformat(),
                "refresh_token": token_data.get("refresh_token", refresh_token),
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
        response = await self._make_request("GET", "/me")
        data = response.json()
        return f"Outlook Calendar connected as {data.get('displayName', data.get('userPrincipalName', 'unknown'))}"
    
    async def fetch_page(
        self,
        entity_type: EntityType,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        
        if entity_type == EntityType.EVENT:
            endpoint = "me/calendar/events"
        elif entity_type == EntityType.CUSTOM:
            endpoint = "me/calendars"
        else:
            return PageResult()
        
        params = {"$top": min(page_size, 100)}
        if cursor:
            params["$skiptoken"] = cursor
        
        if since:
            params["$filter"] = f"start/dateTime ge '{since.isoformat()}'"
        
        response = await self._make_request("GET", f"/{endpoint}", params=params)
        data = response.json()
        
        entities = data.get("value", [])
        next_cursor = data.get("@odata.nextLink", data.get("@odata.deltaLink"))
        if next_cursor:
            import urllib.parse
            parsed = urllib.parse.urlparse(next_cursor)
            query = urllib.parse.parse_qs(parsed.query)
            next_cursor = query.get("$skiptoken", [None])[0]
        
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


# ==================== Calendly Connector ====================

@connector(
    metadata=ConnectorMetadata(
        id="calendly",
        name="Calendly",
        display_name="Calendly",
        description="Calendly Scheduling Automation",
        category="calendar",
        logo_url="https://cdn.vcos.io/connectors/calendly.png",
        documentation_url="https://docs.vcos.io/integrations/calendly",
        version="1.0.0",
        author="VCOS",
        tags=["calendar", "calendly", "scheduling", "booking"],
        auth_schemes=["oauth2", "api_key"],
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "OAuth2 client ID"},
                "client_secret": {"type": "string", "description": "OAuth2 client secret"},
                "redirect_uri": {"type": "string", "description": "OAuth2 redirect URI"},
                "api_key": {"type": "string", "description": "Calendly Personal Access Token"},
            },
            "required": ["client_id", "client_secret"],
        },
        required_scopes=["scheduling:read", "scheduling:write", "user:read"],
    ),
    capabilities=ConnectorCapabilities(
        supported_entities=["person", "event", "event_type", "invitee", "webhook"],
        supported_operations=["read", "create", "update"],
        supports_incremental=True,
        supports_webhooks=True,
        supports_oauth=True,
    ),
    auth=AuthConfig(scheme="oauth2"),
    rate_limit=RateLimitConfig(requests_per_second=10.0, burst_size=20),
    pagination=PaginationConfig(strategy="cursor", cursor_param="page_token", limit_param="count", max_page_size=100),
    retry=RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0),
)
class CalendlyConnector(BaseConnectorWithMixins):
    """Calendly Scheduling connector."""
    
    BASE_URL = "https://api.calendly.com"
    
    OAUTH_AUTHORIZE_URL = "https://calendly.com/oauth/authorize"
    OAUTH_TOKEN_URL = "https://auth.calendly.com/oauth/token"
    OAUTH_USER_URL = "https://api.calendly.com/users/me"
    SUPPORTED_SCOPES = ["scheduling:read", "scheduling:write", "user:read"]
    
    def __init__(self, context):
        super().__init__(context)
        self._token = None
        self._token_expires = None
    
    async def authenticate(self) -> bool:
        try:
            response = await self._make_request("GET", "/users/me")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Calendly authentication failed: {e}")
            return False
    
    async def validate_config(self) -> bool:
        credentials = self._get_credentials()
        return bool(credentials.get("api_key") or (credentials.get("client_id") and credentials.get("client_secret")))
    
    async def _get_token(self) -> str:
        credentials = self._get_credentials()
        
        # Check for personal access token
        pat = credentials.get("api_key")
        if pat:
            return pat
        
        # Check for OAuth token
        access_token = credentials.get("access_token")
        if access_token:
            expires_at = credentials.get("expires_at")
            if expires_at:
                try:
                    exp_time = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) < exp_time:
                        return access_token
                except Exception:
                    pass
            
            # Try to refresh
            if await self._refresh_token(credentials):
                return credentials.get("access_token", "")
        
        raise RuntimeError("Calendly token not configured or refresh failed")
    
    async def _refresh_token(self, credentials: Dict[str, Any]) -> bool:
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        
        if not refresh_token or not credentials.get("client_id") or not credentials.get("client_secret"):
            return False
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://auth.calendly.com/oauth/token",
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": credentials["client_id"],
                        "client_secret": credentials["client_secret"],
                    },
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    raise ValueError(f"Token refresh failed: {data.get('error_description', data.get('error'))}")
                
                self.context.credentials = {
                    **credentials,
                    "access_token": data["access_token"],
                    "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=data["expires_in"])).isoformat(),
                    "refresh_token": data.get("refresh_token", refresh_token),
                }
                return True
        except Exception as e:
            logger.error(f"Calendly token refresh error: {e}")
            return False
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = super()._get_default_headers()
        # Token added per-request
        return headers
    
    async def _make_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        token = await self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {await self._get_token()}"
        return await super()._make_request(method, path, headers=headers, **kwargs)
    
    async def _test_connection_impl(self) -> str:
        response = await self._make_request("GET", "/users/me")
        data = response.json()
        return f"Calendly connected as {data.get('resource', {}).get('name', 'unknown')}"
    
    async def fetch_page(
        self,
        entity_type: EntityType,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        
        if entity_type == EntityType.EVENT:
            endpoint = "scheduled_events"
        elif entity_type == EntityType.CUSTOM:
            endpoint = "event_types"
        else:
            return PageResult()
        
        params = {"count": min(page_size, 100)}
        if cursor:
            params["page_token"] = cursor
        
        response = await self._make_request("GET", f"/{endpoint}", params=params)
        data = response.json()
        
        entities = data.get("collection", [])
        next_cursor = data.get("next_page_token")
        
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


# ==================== Doodle Connector ====================

@connector(
    metadata=ConnectorMetadata(
        id="doodle",
        name="Doodle",
        display_name="Doodle",
        description="Doodle Scheduling and Polling Platform",
        category="calendar",
        logo_url="https://cdn.vcos.io/connectors/doodle.png",
        documentation_url="https://docs.vcos.io/integrations/doodle",
        version="1.0.0",
        author="VCOS",
        tags=["calendar", "doodle", "scheduling", "polling"],
        auth_schemes=["api_key", "oauth2"],
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string", "description": "OAuth2 client ID"},
                "client_secret": {"type": "string", "description": "OAuth2 client secret"},
                "redirect_uri": {"type": "string", "description": "OAuth2 redirect URI"},
                "api_key": {"type": "string", "description": "Doodle API key"},
            },
            "required": ["client_id", "client_secret"],
        },
        required_scopes=["polls:read", "polls:write", "user:read"],
    ),
    capabilities=ConnectorCapabilities(
        supported_entities=["person", "poll", "participant", "choice"],
        supported_operations=["read", "create", "update"],
        supports_incremental=True,
        supports_webhooks=True,
        supports_oauth=True,
    ),
    auth=AuthConfig(scheme="oauth2"),
    rate_limit=RateLimitConfig(requests_per_second=10.0, burst_size=20),
    pagination=PaginationConfig(strategy="cursor", cursor_param="cursor", limit_param="limit", max_page_size=100),
    retry=RetryConfig(max_retries=3, base_delay=1.0, max_delay=60.0),
)
class DoodleConnector(BaseConnectorWithMixins):
    """Doodle Scheduling connector."""
    
    BASE_URL = "https://api.doodle.com/v2"
    
    OAUTH_AUTHORIZE_URL = "https://doodle.com/oauth/authorize"
    OAUTH_TOKEN_URL = "https://api.doodle.com/oauth/token"
    OAUTH_USER_URL = "https://api.doodle.com/v2/users/me"
    SUPPORTED_SCOPES = ["polls:read", "polls:write", "user:read"]
    
    def __init__(self, context):
        super().__init__(context)
        self._token = None
        self._token_expires = None
    
    async def authenticate(self) -> bool:
        try:
            response = await self._make_request("GET", "/users/me")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Doodle authentication failed: {e}")
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
        
        # Refresh token
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        
        if not refresh_token or not credentials.get("client_id") or not credentials.get("client_secret"):
            raise RuntimeError("Missing OAuth credentials")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.doodle.com/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": credentials["refresh_token"],
                    "client_id": credentials["client_id"],
                    "client_secret": credentials["client_secret"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            token_data = response.json()
            
            if "error" in token_data:
                raise ValueError(f"Token refresh failed: {token_data.get('error_description', token_data.get('error'))}")
            
            self.context.credentials = {
                **credentials,
                "access_token": token_data["access_token"],
                "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])).isoformat(),
                "refresh_token": token_data.get("refresh_token", credentials["refresh_token"]),
            }
            
            return token_data["access_token"]
    
    def _get_default_headers(self) -> Dict[str, str]:
        headers = super()._get_default_headers()
        # Token added per-request
        return headers
    
    async def _make_request(self, method: str, path: str, **kwargs) -> httpx.Response:
        token = await self._get_token()
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {token}"
        return await super()._make_request(method, path, headers=headers, **kwargs)
    
    async def _test_connection_impl(self) -> str:
        response = await self._make_request("GET", "/users/me")
        data = response.json()
        return f"Doodle connected as {data.get('name', 'unknown')}"
    
    async def fetch_page(
        self,
        entity_type: EntityType,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
        filters: Optional[Dict[str, Any]] = None,
    ) -> PageResult:
        
        if entity_type == EntityType.EVENT:
            endpoint = "polls"
        elif entity_type == EntityType.CUSTOM:
            endpoint = "participants"
        else:
            return PageResult()
        
        params = {"limit": min(page_size, 50)}
        if cursor:
            params["cursor"] = cursor
        
        response = await self._make_request("GET", f"/{endpoint}", params=params)
        data = response.json()
        
        entities = data.get("items", data.get("polls", []))
        next_cursor = data.get("next_cursor")
        
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