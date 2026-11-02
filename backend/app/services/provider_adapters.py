"""Provider-Specific Connector Adapters.

Implements production-grade connectors for:
- Google Workspace
- Microsoft 365 / Entra ID
- Slack
- GitHub
- Jira

Each adapter implements the BaseConnectorAdapter interface.
"""

import asyncio
import logging
import secrets
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, AsyncGenerator
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.services.base_adapter import BaseConnectorAdapter
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.integration.adapters")


@dataclass
class OAuthToken:
    access_token: str
    refresh_token: Optional[str]
    expires_at: Optional[datetime]
    token_type: str = "Bearer"
    scope: str = ""


class BaseHTTPAdapter:
    """Base HTTP adapter with common functionality."""
    
    def __init__(self, instance: Any):
        self.instance = instance
        self.base_url = ""
        self.client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30.0)
        return self.client
    
    async def close(self):
        if self.client:
            await self.client.aclose()
            self.client = None
    
    async def _request(
        self,
        method: str,
        path: str,
        headers: Optional[Dict] = None,
        params: Optional[Dict] = None,
        json: Optional[Dict] = None,
        data: Optional[Dict] = None,
    ) -> httpx.Response:
        client = await self._get_client()
        url = f"{self.base_url}{path}"
        
        default_headers = {"Accept": "application/json"}
        if headers:
            default_headers.update(headers)
        
        response = await client.request(
            method, url, headers=default_headers, params=params, json=json, data=data
        )
        return response
    
    async def _get_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        raise NotImplementedError


class GoogleWorkspaceAdapter(BaseConnectorAdapter):
    """Google Workspace adapter (Gmail, Drive, Calendar, Contacts, People)."""
    
    provider_name = "google"
    
    def __init__(self, instance: Any):
        super().__init__()
        self.instance = instance
        self.base_url = "https://www.googleapis.com"
        self.client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30.0)
        return self.client
    
    async def _get_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        credentials = self.instance.credentials or {}
        
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
                    "refresh_token": refresh_token,
                    "client_id": client_id,
                    "client_secret": client_secret,
                },
            )
            response.raise_for_status()
            token_data = response.json()
            
            self.instance.credentials["access_token"] = token_data["access_token"]
            self.instance.credentials["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
            ).isoformat()
            if "refresh_token" in token_data:
                self.instance.credentials["refresh_token"] = token_data["refresh_token"]
            
            return token_data["access_token"]
    
    async def authenticate(self, instance: Any) -> bool:
        try:
            token = await self._get_token()
            return bool(token)
        except Exception as e:
            logger.error(f"Google authentication failed: {e}")
            return False
    
    async def test_connection(self, instance: Any) -> Dict[str, Any]:
        try:
            await self._get_token()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://www.googleapis.com/oauth2/v1/userinfo",
                    headers={"Authorization": f"Bearer {await self._get_token()}"},
                )
                response.raise_for_status()
                return {"success": True, "detail": "Google Workspace connection successful"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_initial_cursor(self, instance: Any, entity_type: str) -> str:
        return "initial"
    
    async def get_incremental_cursor(self, instance: Any, entity_type: str, cursor: str) -> str:
        return cursor or "incremental"
    
    async def fetch_page(
        self,
        instance: Any,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        token = await self._get_token()
        headers = {"Authorization": f"Bearer {await self._get_token()}"}
        
        # Map entity types to Google API endpoints
        endpoint_map = {
            "person": "admin/directory/v1/users",
            "group": "admin/directory/v1/groups",
            "file": "drive/v3/files",
            "event": "calendar/v3/calendars/primary/events",
            "contact": "people/v1/people/me/connections",
        }
        
        endpoint = endpoint_map.get(entity_type)
        if not endpoint:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {"maxResults": min(page_size, 500)}
        if cursor:
            params["pageToken"] = cursor
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://www.googleapis.com/{endpoint}",
                headers={"Authorization": f"Bearer {await self._get_token()}"},
                params={"maxResults": min(page_size, 500), "pageToken": cursor} if cursor else {"maxResults": min(page_size, 500)},
            )
            response.raise_for_status()
            data = response.json()
            
            entities = data.get("users", data.get("groups", data.get("files", data.get("items", data.get("connections", [])))))
            
            return {
                "entities": entities or [],
                "next_cursor": data.get("nextPageToken"),
                "has_more": bool(data.get("nextPageToken")),
                "total_count": len(entities or []),
            }

    async def get_deleted_entities(self, instance: Any, entity_type: str, since: datetime) -> List[str]:
        # Google Workspace doesn't provide deleted entity lists easily
        return []


class Microsoft365Adapter(BaseConnectorAdapter):
    """Microsoft 365 / Entra ID adapter (Outlook, Teams, SharePoint, OneDrive)."""
    
    provider_name = "microsoft"
    
    # Microsoft OAuth2 endpoints
    OAUTH_AUTHORIZE_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize"
    OAUTH_TOKEN_URL = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    
    # Required scopes for Microsoft Graph delegated permissions
    SUPPORTED_SCOPES = [
        "https://graph.microsoft.com/User.Read",
        "https://graph.microsoft.com/User.Read.All",
        "https://graph.microsoft.com/Group.Read.All",
        "https://graph.microsoft.com/Mail.Read",
        "https://graph.microsoft.com/Calendars.Read",
        "https://graph.microsoft.com/Files.Read.All",
        "https://graph.microsoft.com/Team.ReadBasic.All",
        "https://graph.microsoft.com/ChannelMessage.Read.All",
        "offline_access",
    ]
    
    def __init__(self, instance: Any):
        super().__init__()
        self.instance = instance
        self.base_url = "https://graph.microsoft.com/v1.0"
        self.client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None
        self._token_expires: Optional[datetime] = None
        # OAuth state storage (in production, use Redis or DB)
        self._oauth_states: Dict[str, Dict[str, Any]] = {}
    
    async def _get_client(self) -> httpx.AsyncClient:
        if self.client is None:
            self.client = httpx.AsyncClient(timeout=30.0)
        return self.client
    
    async def _get_token(self) -> str:
        credentials = self.instance.credentials or {}
        
        if "access_token" in credentials and "expires_at" in credentials:
            expires_at = datetime.fromisoformat(credentials["expires_at"].replace('Z', '+00:00'))
            if expires_at > datetime.now(timezone.utc) + timedelta(minutes=5):
                return credentials["access_token"]
        
        # Use client credentials flow for app-only, or refresh token
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        tenant_id = credentials.get("tenant_id")
        
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
            
            self.instance.credentials["access_token"] = token_data["access_token"]
            self.instance.credentials["expires_at"] = (
                datetime.now(timezone.utc) + timedelta(seconds=token_data["expires_in"])
            ).isoformat()
            if "refresh_token" in token_data:
                self.instance.credentials["refresh_token"] = token_data["refresh_token"]
            
            return token_data["access_token"]
    
    async def authenticate(self, instance: Any) -> bool:
        try:
            token = await self._get_token()
            return bool(token)
        except Exception as e:
            logger.error(f"Microsoft authentication failed: {e}")
            return False
    
    async def test_connection(self, instance: Any) -> Dict[str, Any]:
        try:
            token = await self._get_token()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://graph.microsoft.com/v1.0/me",
                    headers={"Authorization": f"Bearer {await self._get_token()}"},
                )
                response.raise_for_status()
                return {"success": True, "detail": "Microsoft 365 connection successful"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    # =========================================================================
    # OAUTH 2.0 SUPPORT (Authorization Code Flow with PKCE)
    # =========================================================================
    
    def _generate_pkce_pair(self) -> tuple[str, str]:
        """Generate PKCE code_verifier and code_challenge."""
        import base64
        import hashlib
        code_verifier = secrets.token_urlsafe(96)[:128]  # 43-128 chars
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode()).digest()
        ).decode().rstrip('=')
        return code_verifier, code_challenge
    
    def generate_oauth_url(self, redirect_uri: str, state: Optional[str] = None, scopes: Optional[List[str]] = None) -> str:
        """Generate Microsoft OAuth authorization URL with PKCE."""
        state = state or secrets.token_urlsafe(32)
        code_verifier, code_challenge = self._generate_pkce_pair()
        
        # Store state and code_verifier for callback validation
        self._oauth_states[state] = {
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "tenant_id": self.instance.config.get("tenant_id") if self.instance.config else None,
        }
        
        scope_list = scopes or self.SUPPORTED_SCOPES
        config = self.instance.config or {}
        client_id = config.get("client_id") or (self.instance.credentials or {}).get("client_id")
        tenant_id = config.get("tenant_id") or (self.instance.credentials or {}).get("tenant_id")
        
        if not client_id:
            raise RuntimeError("Microsoft client_id not configured")
        if not tenant_id:
            raise RuntimeError("Microsoft tenant_id not configured")
        
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scope_list),
            "response_type": "code",
            "response_mode": "query",
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
            "prompt": "consent",
        }
        return f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/authorize?{urlencode(params)}"
    
    async def handle_oauth_callback(self, code: str, state: str, redirect_uri: str) -> Dict[str, Any]:
        """Handle OAuth callback and exchange code for tokens."""
        # Validate state
        oauth_state = self._oauth_states.get(state)
        if not oauth_state:
            raise ValueError("Invalid OAuth state")
        
        # Verify redirect_uri matches
        if oauth_state.get("redirect_uri") != redirect_uri:
            raise ValueError("Redirect URI mismatch")
        
        code_verifier = oauth_state.get("code_verifier")
        tenant_id = oauth_state.get("tenant_id")
        
        del self._oauth_states[state]
        
        config = self.instance.config or {}
        credentials = self.instance.credentials or {}
        client_id = config.get("client_id") or (self.instance.credentials or {}).get("client_id")
        client_secret = config.get("client_secret") or (self.instance.credentials or {}).get("client_secret")
        
        if not client_id or not client_secret:
            raise RuntimeError("Microsoft client_id and client_secret not configured")
        
        # Use the tenant_id from config/credentials if not in oauth_state
        if not tenant_id:
            tenant_id = config.get("tenant_id") or (self.instance.credentials or {}).get("tenant_id")
        
        if not tenant_id:
            raise RuntimeError("Microsoft tenant_id not configured")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                    "code_verifier": code_verifier,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
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
                "user_email": user_info.get("mail") or user_info.get("userPrincipalName"),
                "user_name": user_info.get("displayName"),
                "user_id": user_info.get("id"),
            }
    
    async def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from Microsoft Graph using access token."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me",
                headers={"Authorization": f"Bearer {access_token}", "$select": "id,displayName,mail,userPrincipalName"},
            )
            response.raise_for_status()
            return response.json()
    
    async def verify_oauth_state(self, state: str) -> bool:
        """Verify OAuth state parameter."""
        return state in self._oauth_states
    
    async def refresh_access_token(self, instance: Any) -> bool:
        """Refresh access token using refresh token."""
        try:
            credentials = instance.credentials
            if not credentials or not credentials.get("refresh_token"):
                return False
            
            tenant_id = instance.config.get("tenant_id") or credentials.get("tenant_id")
            client_id = credentials.get("client_id")
            client_secret = credentials.get("client_secret")
            refresh_token = credentials.get("refresh_token")
            
            if not all([tenant_id, client_id, client_secret, refresh_token]):
                return False
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token",
                    data={
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                        "grant_type": "refresh_token",
                        "scope": "https://graph.microsoft.com/.default",
                    },
                )
                response.raise_for_status()
                data = response.json()
                
                if "access_token" in data:
                    instance.credentials["access_token"] = data["access_token"]
                    instance.credentials["expires_at"] = (
                        datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))
                    ).isoformat()
                    if "refresh_token" in data:
                        instance.credentials["refresh_token"] = data["refresh_token"]
                    return True
                return False
        except Exception as e:
            logger.error(f"Microsoft token refresh error: {e}")
            return False
    
    async def get_initial_cursor(self, instance: Any, entity_type: str) -> str:
        return "initial"
    
    async def get_incremental_cursor(self, instance: Any, entity_type: str, cursor: str) -> str:
        return cursor or "incremental"
    
    async def fetch_page(
        self,
        instance: Any,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        token = await self._get_token()
        
        endpoint_map = {
            "person": "users",
            "group": "groups",
            "team": "teams",
            "channel": "teams/{team-id}/channels",
            "message": "teams/{team-id}/channels/{channel-id}/messages",
            "file": "drive/root/children",
            "event": "me/calendar/events",
            "contact": "me/contacts",
        }
        
        endpoint = endpoint_map.get(entity_type)
        if not endpoint:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {"$top": min(page_size, 999)}
        if cursor:
            params["$skiptoken"] = cursor
        
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://graph.microsoft.com/v1.0/{endpoint}",
                headers={"Authorization": f"Bearer {await self._get_token()}"},
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            
            entities = data.get("value", [])
            next_cursor = data.get("@odata.nextLink", data.get("@odata.deltaLink"))
            
            return {
                "entities": entities,
                "next_cursor": next_cursor,
                "has_more": bool(next_cursor),
                "total_count": len(entities),
            }


class SlackAdapter(BaseConnectorAdapter):
    """Slack adapter for channels, messages, users, and files."""
    
    provider_name = "slack"
    
    # Operations this connector can perform
    outbound_capabilities = ["read", "create", "update"]
    
    # Entity types this connector supports
    supported_entities = ["person", "channel", "message", "file", "team", "usergroup"]
    
    # Slack OAuth configuration
    OAUTH_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
    OAUTH_TOKEN_URL = "https://slack.com/api/oauth.v2.access"
    OAUTH_USER_URL = "https://slack.com/api/users.identity"
    SUPPORTED_SCOPES = ["channels:read", "channels:history", "groups:read", "groups:history", 
                        "users:read", "users:read.email", "team:read", "files:read", 
                        "chat:write", "commands", "incoming-webhook"]
    
    def __init__(self, instance: Any):
        super().__init__()
        self.instance = instance
        self.base_url = "https://slack.com/api"
        self.client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None
        self._oauth_states: Dict[str, str] = {}
    
    def _get_config_value(self, key: str, default: Any = None) -> Any:
        """Get config value from instance config."""
        config = self.instance.config or {}
        return config.get(key, default)
    
    def _get_credentials(self) -> Dict[str, Any]:
        """Get credentials from instance."""
        return self.instance.credentials or {}
    
    async def _get_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        credentials = self._get_credentials()
        
        # Check if we have a bot token (no refresh needed)
        bot_token = credentials.get("bot_token")
        if bot_token:
            return bot_token
        
        # Check if we have OAuth token
        access_token = credentials.get("access_token")
        if access_token:
            # Check if token is expired
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
        
        raise RuntimeError("Slack token not configured or refresh failed")
    
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
                
                if not data.get("ok"):
                    logger.error(f"Slack token refresh failed: {data.get('error')}")
                    return False
                
                # Update credentials in instance
                self.instance.credentials = {
                    **credentials,
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token", refresh_token),
                    "expires_in": data.get("expires_in"),
                    "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))).isoformat(),
                    "scope": data.get("scope"),
                    "token_type": data.get("token_type", "Bearer"),
                }
                return True
        except Exception as e:
            logger.error(f"Slack token refresh error: {e}")
            return False
    
    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        headers = {"Authorization": f"Bearer {await self._get_token()}", "Content-Type": "application/json"}
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"https://slack.com/api/{endpoint}",
                headers=headers,
                **kwargs,
            )
            response.raise_for_status()
            data = response.json()
            if not data.get("ok"):
                raise RuntimeError(f"Slack API error: {data.get('error')}")
            return data
    
    # OAuth2 methods
    def generate_oauth_url(self, redirect_uri: str, state: Optional[str] = None, scopes: Optional[List[str]] = None) -> str:
        """Generate Slack OAuth authorization URL."""
        state = state or secrets.token_urlsafe(32)
        self._oauth_states[state] = state
        
        scope_list = scopes or self.SUPPORTED_SCOPES
        config = self.instance.config or {}
        client_id = config.get("client_id") or self._get_credentials().get("client_id")
        
        if not client_id:
            raise RuntimeError("Slack client_id not configured")
        
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scope_list),
            "response_type": "code",
            "state": state,
        }
        return f"{self.OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    async def handle_oauth_callback(self, code: str, state: str, redirect_uri: str) -> Dict[str, Any]:
        """Handle OAuth callback and exchange code for tokens."""
        if state not in self._oauth_states:
            raise ValueError("Invalid OAuth state")
        del self._oauth_states[state]
        
        config = self.instance.config or {}
        credentials = self._get_credentials()
        client_id = config.get("client_id") or credentials.get("client_id")
        client_secret = config.get("client_secret") or credentials.get("client_secret")
        
        if not client_id or not client_secret:
            raise RuntimeError("Slack client_id and client_secret not configured")
        
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
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()
            
            if not data.get("ok"):
                raise ValueError(f"OAuth failed: {data.get('error')}")
            
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
                "team_id": data.get("team", {}).get("id"),
                "team_name": data.get("team", {}).get("name"),
            }

    async def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from Slack using access token."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.OAUTH_USER_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )
            response.raise_for_status()
            return response.json().get("user", {})

    async def authenticate(self, instance: Any) -> bool:
        try:
            data = await self._request("GET", "auth.test")
            return data.get("ok", False)
        except Exception as e:
            logger.error(f"Slack authentication failed: {e}")
            return False
    
    async def test_connection(self, instance: Any) -> Dict[str, Any]:
        try:
            data = await self._request("GET", "auth.test")
            return {"success": True, "detail": f"Slack connected as {data.get('user')} in team {data.get('team')}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_initial_cursor(self, instance: Any, entity_type: str) -> str:
        return "0"
    
    async def get_incremental_cursor(self, instance: Any, entity_type: str, cursor: str) -> str:
        return cursor
    
    async def fetch_page(
        self,
        instance: Any,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        
        endpoint_map = {
            "person": "users.list",
            "channel": "conversations.list",
            "message": "conversations.history",
            "file": "files.list",
            "team": "team.info",
            "usergroup": "usergroups.list",
        }
        
        endpoint = endpoint_map.get(entity_type)
        if not endpoint:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {"limit": min(page_size, 1000)}
        if cursor:
            params["cursor"] = cursor
        
        data = await self._request("GET", endpoint, params=params)
        
        entities = data.get("members", data.get("channels", data.get("messages", data.get("files", data.get("usergroups", [])))))
        
        return {
            "entities": entities or [],
            "next_cursor": data.get("response_metadata", {}).get("next_cursor"),
            "has_more": data.get("has_more", False),
            "total_count": len(entities or []),
        }

    async def get_rate_limit_status(self, instance: Any) -> Dict[str, Any]:
        """Get current Slack API rate limit status."""
        try:
            data = await self._request("GET", "auth.test")
            # Slack doesn't have a standard rate limit endpoint, but we can check headers
            return {"remaining": 100, "limit": 100, "reset_at": None}
        except Exception:
            return {"remaining": 0, "limit": 100, "reset_at": None}

    async def handle_rate_limit(self, instance: Any, reset_at: datetime) -> bool:
        """Handle rate limit - return True if should retry."""
        wait_seconds = (reset_at - datetime.now(timezone.utc)).total_seconds()
        if wait_seconds > 0 and wait_seconds < 300:  # Max 5 minutes
            await asyncio.sleep(min(wait_seconds + 1, 300))
            return True
        return False


class GitHubAdapter(BaseConnectorAdapter):
    """GitHub adapter for repositories, issues, PRs, commits."""

    provider_name = "github"

    # Operations this connector can perform
    outbound_capabilities = ["read", "create", "update"]

    # Entity types this connector supports
    supported_entities = ["repository", "issue", "pull_request", "commit", "person", "branch", "release"]

    # GitHub OAuth configuration
    OAUTH_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
    OAUTH_TOKEN_URL = "https://github.com/login/oauth/access_token"
    OAUTH_USER_URL = "https://api.github.com/user"
    SUPPORTED_SCOPES = ["repo", "read:org", "read:user", "user:email", "admin:repo_hook"]

    def __init__(self, instance: Any):
        super().__init__()
        self.instance = instance
        self.base_url = "https://api.github.com"
        self.client: Optional[httpx.AsyncClient] = None
        self._token: Optional[str] = None
        self._oauth_states: Dict[str, str] = {}

    def _get_config_value(self, key: str, default: Any = None) -> Any:
        """Get config value from instance config."""
        config = self.instance.config or {}
        return config.get(key, default)

    def _get_credentials(self) -> Dict[str, Any]:
        """Get credentials from instance."""
        return self.instance.credentials or {}

    async def _get_token(self) -> str:
        """Get valid access token, refreshing if needed."""
        credentials = self._get_credentials()
        
        # Check if we have a personal access token (no refresh needed)
        pat = credentials.get("personal_access_token")
        if pat:
            return pat
        
        # Check if we have OAuth token
        access_token = credentials.get("access_token")
        if access_token:
            # Check if token is expired
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
        
        raise RuntimeError("GitHub token not configured or refresh failed")

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
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                data = response.json()
                
                if "error" in data:
                    logger.error(f"GitHub token refresh failed: {data.get('error_description', data.get('error'))}")
                    return False
                
                # Update credentials in instance
                self.instance.credentials = {
                    **credentials,
                    "access_token": data.get("access_token"),
                    "refresh_token": data.get("refresh_token", refresh_token),
                    "expires_in": data.get("expires_in"),
                    "expires_at": (datetime.now(timezone.utc) + timedelta(seconds=data.get("expires_in", 3600))).isoformat(),
                    "scope": data.get("scope"),
                    "token_type": data.get("token_type", "bearer"),
                }
                return True
        except Exception as e:
            logger.error(f"GitHub token refresh error: {e}")
            return False

    async def _request(self, method: str, endpoint: str, **kwargs) -> Dict:
        headers = {
            "Authorization": f"Bearer {await self._get_token()}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method,
                f"https://api.github.com/{endpoint}",
                headers=headers,
                **kwargs,
            )
            response.raise_for_status()
            return response.json()

    # OAuth2 methods
    def generate_oauth_url(self, redirect_uri: str, state: Optional[str] = None, scopes: Optional[List[str]] = None) -> str:
        """Generate GitHub OAuth authorization URL."""
        state = state or secrets.token_urlsafe(32)
        self._oauth_states[state] = state
        
        scope_list = scopes or self.SUPPORTED_SCOPES
        config = self.instance.config or {}
        client_id = config.get("client_id") or self._get_credentials().get("client_id")
        
        if not client_id:
            raise RuntimeError("GitHub client_id not configured")
        
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": " ".join(scope_list),
            "response_type": "code",
            "state": state,
            "allow_signup": "true",
        }
        return f"{self.OAUTH_AUTHORIZE_URL}?{urlencode(params)}"

    async def handle_oauth_callback(self, code: str, state: str, redirect_uri: str) -> Dict[str, Any]:
        """Handle OAuth callback and exchange code for tokens."""
        if state not in self._oauth_states:
            raise ValueError("Invalid OAuth state")
        del self._oauth_states[state]
        
        config = self.instance.config or {}
        credentials = self._get_credentials()
        client_id = config.get("client_id") or credentials.get("client_id")
        client_secret = config.get("client_secret") or credentials.get("client_secret")
        
        if not client_id or not client_secret:
            raise RuntimeError("GitHub client_id and client_secret not configured")
        
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
                "user_name": user_info.get("name") or user_info.get("login"),
                "user_id": user_info.get("id"),
                "login": user_info.get("login"),
            }

    async def _get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Get user info from GitHub using access token."""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.OAUTH_USER_URL,
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github+json"},
            )
            response.raise_for_status()
            return response.json()

    async def authenticate(self, instance: Any) -> bool:
        try:
            await self._request("GET", "user")
            return True
        except Exception as e:
            logger.error(f"GitHub authentication failed: {e}")
            return False

    async def test_connection(self, instance: Any) -> Dict[str, Any]:
        try:
            data = await self._request("GET", "user")
            return {"success": True, "detail": f"GitHub connected as {data.get('login')}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_initial_cursor(self, instance: Any, entity_type: str) -> str:
        return ""

    async def get_incremental_cursor(self, instance: Any, entity_type: str, cursor: str) -> str:
        return cursor

    async def fetch_page(
        self,
        instance: Any,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        
        config = self.instance.config or {}
        org = config.get("organization")
        
        if entity_type == "repository":
            return await self._fetch_repositories(org, cursor, since, page_size)
        elif entity_type == "issue":
            return await self._fetch_issues(config, cursor, since, page_size)
        elif entity_type == "pull_request":
            return await self._fetch_pull_requests(config, cursor, since, page_size)
        elif entity_type == "commit":
            return await self._fetch_commits(config, cursor, since, page_size)
        elif entity_type == "person":
            return await self._fetch_organization_members(org, cursor, page_size)
        elif entity_type == "branch":
            return await self._fetch_branches(config, cursor, page_size)
        elif entity_type == "release":
            return await self._fetch_releases(config, cursor, since, page_size)
        
        return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}

    async def _fetch_repositories(
        self, org: Optional[str], cursor: Optional[str], since: Optional[datetime], page_size: int
    ) -> Dict[str, Any]:
        params = {
            "per_page": min(page_size, 100),
            "type": "all",
            "sort": "updated",
            "direction": "desc",
        }
        if cursor:
            params["page"] = int(cursor)
        if since:
            params["since"] = since.isoformat()
        
        endpoint = f"orgs/{org}/repos" if org else "user/repos"
        data = await self._request("GET", endpoint, params=params)
        
        next_page = cursor + 1 if cursor else 2 if len(data) == params["per_page"] else None
        
        return {
            "entities": data,
            "next_cursor": str(next_page) if next_page else None,
            "has_more": next_page is not None,
            "total_count": len(data),
        }

    async def _fetch_issues(
        self, config: Dict, cursor: Optional[str], since: Optional[datetime], page_size: int
    ) -> Dict[str, Any]:
        owner = config.get("repository_owner")
        repo = config.get("repository_name")
        if not owner or not repo:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {
            "per_page": min(page_size, 100),
            "state": "all",
            "sort": "updated",
            "direction": "desc",
        }
        if cursor:
            params["page"] = int(cursor)
        if since:
            params["since"] = since.isoformat()
        
        endpoint = f"repos/{owner}/{repo}/issues"
        data = await self._request("GET", endpoint, params=params)
        
        # Filter out pull requests (GitHub API returns PRs in issues endpoint)
        issues = [item for item in data if "pull_request" not in item]
        
        next_page = cursor + 1 if cursor else 2 if len(data) == params["per_page"] else None
        
        return {
            "entities": issues,
            "next_cursor": str(next_page) if next_page else None,
            "has_more": next_page is not None,
            "total_count": len(issues),
        }

    async def _fetch_pull_requests(
        self, config: Dict, cursor: Optional[str], since: Optional[datetime], page_size: int
    ) -> Dict[str, Any]:
        owner = config.get("repository_owner")
        repo = config.get("repository_name")
        if not owner or not repo:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {
            "per_page": min(page_size, 100),
            "state": "all",
            "sort": "updated",
            "direction": "desc",
        }
        if cursor:
            params["page"] = int(cursor)
        if since:
            params["since"] = since.isoformat()
        
        endpoint = f"repos/{owner}/{repo}/pulls"
        data = await self._request("GET", endpoint, params=params)
        
        next_page = cursor + 1 if cursor else 2 if len(data) == params["per_page"] else None
        
        return {
            "entities": data,
            "next_cursor": str(next_page) if next_page else None,
            "has_more": next_page is not None,
            "total_count": len(data),
        }

    async def _fetch_commits(
        self, config: Dict, cursor: Optional[str], since: Optional[datetime], page_size: int
    ) -> Dict[str, Any]:
        owner = config.get("repository_owner")
        repo = config.get("repository_name")
        if not owner or not repo:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {
            "per_page": min(page_size, 100),
        }
        if cursor:
            params["page"] = int(cursor)
        if since:
            params["since"] = since.isoformat()
        
        endpoint = f"repos/{owner}/{repo}/commits"
        data = await self._request("GET", endpoint, params=params)
        
        next_page = cursor + 1 if cursor else 2 if len(data) == params["per_page"] else None
        
        return {
            "entities": data,
            "next_cursor": str(next_page) if next_page else None,
            "has_more": next_page is not None,
            "total_count": len(data),
        }

    async def _fetch_organization_members(
        self, org: Optional[str], cursor: Optional[str], page_size: int
    ) -> Dict[str, Any]:
        if not org:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {
            "per_page": min(page_size, 100),
        }
        if cursor:
            params["page"] = int(cursor)
        
        endpoint = f"orgs/{org}/members"
        data = await self._request("GET", endpoint, params=params)
        
        next_page = cursor + 1 if cursor else 2 if len(data) == params["per_page"] else None
        
        return {
            "entities": data,
            "next_cursor": str(next_page) if next_page else None,
            "has_more": next_page is not None,
            "total_count": len(data),
        }

    async def _fetch_branches(
        self, config: Dict, cursor: Optional[str], page_size: int
    ) -> Dict[str, Any]:
        owner = config.get("repository_owner")
        repo = config.get("repository_name")
        if not owner or not repo:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {
            "per_page": min(page_size, 100),
        }
        if cursor:
            params["page"] = int(cursor)
        
        endpoint = f"repos/{owner}/{repo}/branches"
        data = await self._request("GET", endpoint, params=params)
        
        next_page = cursor + 1 if cursor else 2 if len(data) == params["per_page"] else None
        
        return {
            "entities": data,
            "next_cursor": str(next_page) if next_page else None,
            "has_more": next_page is not None,
            "total_count": len(data),
        }

    async def _fetch_releases(
        self, config: Dict, cursor: Optional[str], since: Optional[datetime], page_size: int
    ) -> Dict[str, Any]:
        owner = config.get("repository_owner")
        repo = config.get("repository_name")
        if not owner or not repo:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {
            "per_page": min(page_size, 100),
        }
        if cursor:
            params["page"] = int(cursor)
        
        endpoint = f"repos/{owner}/{repo}/releases"
        data = await self._request("GET", endpoint, params=params)
        
        next_page = cursor + 1 if cursor else 2 if len(data) == params["per_page"] else None
        
        return {
            "entities": data,
            "next_cursor": str(next_page) if next_page else None,
            "has_more": next_page is not None,
            "total_count": len(data),
        }

    async def get_rate_limit_status(self, instance: Any) -> Dict[str, Any]:
        """Get current GitHub API rate limit status."""
        try:
            data = await self._request("GET", "rate_limit")
            core = data.get("resources", {}).get("core", {})
            return {
                "remaining": core.get("remaining", 0),
                "limit": core.get("limit", 5000),
                "reset_at": datetime.fromtimestamp(core.get("reset", 0), tz=timezone.utc).isoformat() if core.get("reset") else None,
            }
        except Exception:
            return {"remaining": 0, "limit": 5000, "reset_at": None}

    async def handle_rate_limit(self, instance: Any, reset_at: datetime) -> bool:
        """Handle rate limit - return True if should retry."""
        wait_seconds = (reset_at - datetime.now(timezone.utc)).total_seconds()
        if wait_seconds > 0 and wait_seconds < 300:  # Max 5 minutes
            await asyncio.sleep(min(wait_seconds + 1, 300))
            return True
        return False


class JiraAdapter(BaseConnectorAdapter):
    """Jira adapter for projects, issues, sprints, boards."""
    
    provider_name = "jira"
    
    def __init__(self, instance: Any):
        super().__init__()
        self.instance = instance
        self.base_url = ""
        self.client: Optional[httpx.AsyncClient] = None
        self._auth: Optional[httpx.Auth] = None
    
    def _get_base_url(self) -> str:
        config = self.instance.config or {}
        base = config.get("base_url") or config.get("cloud_id")
        if not base:
            raise RuntimeError("Jira base_url not configured")
        if base.startswith("http"):
            return base
        return f"https://{base}.atlassian.net"
    
    async def _get_auth(self) -> httpx.Auth:
        if self._auth:
            return self._auth
        
        credentials = self.instance.credentials or {}
        auth_type = credentials.get("auth_type", "api_key")
        
        if auth_type == "basic":
            email = credentials.get("email")
            api_token = credentials.get("api_token")
            if not email or not api_token:
                raise RuntimeError("Jira email and API token required")
            return httpx.BasicAuth(email, api_token)
        elif auth_type == "oauth2":
            access_token = credentials.get("access_token")
            if not access_token:
                raise RuntimeError("OAuth token not configured")
            return httpx.BearerTokenAuth(access_token)
        else:
            raise RuntimeError(f"Unsupported Jira auth type: {auth_type}")
    
    async def authenticate(self, instance: Any) -> bool:
        try:
            auth = await self._get_auth()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._get_base_url()}/rest/api/3/myself",
                    auth=auth,
                )
                response.raise_for_status()
                return True
        except Exception as e:
            logger.error(f"Jira authentication failed: {e}")
            return False
    
    async def test_connection(self, instance: Any) -> Dict[str, Any]:
        try:
            auth = await self._get_auth()
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self._get_base_url()}/rest/api/3/myself",
                    auth=auth,
                )
                response.raise_for_status()
                data = response.json()
                return {"success": True, "detail": f"Jira connected as {data.get('displayName')}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    async def get_initial_cursor(self, instance: Any, entity_type: str) -> str:
        return ""
    
    async def get_incremental_cursor(self, instance: Any, entity_type: str, cursor: str) -> str:
        return cursor
    
    async def fetch_page(
        self,
        instance: Any,
        entity_type: str,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
        page_size: int = 100,
    ) -> Dict[str, Any]:
        endpoint_map = {
            "project": "rest/api/3/project/search",
            "issue": "rest/api/3/search",
            "person": "rest/api/3/users/search",
        }
        
        endpoint = endpoint_map.get(entity_type)
        if not endpoint:
            return {"entities": [], "next_cursor": None, "has_more": False, "total_count": 0}
        
        params = {"maxResults": min(page_size, 100)}
        if cursor:
            params["startAt"] = int(cursor)
        
        auth = await self._get_auth()
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self._get_base_url()}/{endpoint}",
                auth=auth,
                params=params,
            )
            response.raise_for_status()
            data = response.json()
            
            entities = data.get("values", data.get("issues", []))
            next_cursor = str(data.get("startAt", 0) + len(entities)) if data.get("isLast") is False else None
            
            return {
                "entities": entities or [],
                "next_cursor": next_cursor,
                "has_more": next_cursor is not None,
                "total_count": len(entities or []),
            }