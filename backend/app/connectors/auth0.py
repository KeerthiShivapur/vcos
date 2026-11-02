"""
Auth0 Connector for VCOS.

Provides integration with Auth0 for identity management and authentication.
"""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urljoin

import aiohttp

from app.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    AuthType,
    RateLimitConfig,
    SyncCursor,
    SyncResult,
)

logger = logging.getLogger(__name__)


class Auth0Connector(BaseConnector):
    """Auth0 Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="auth0",
        display_name="Auth0",
        description="Identity platform for authentication and authorization",
        category="identity",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "domain": {"type": "string", "description": "Auth0 domain (e.g., your-tenant.auth0.com)"},
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "audience": {"type": "string", "description": "API audience identifier"},
                "redirect_uri": {"type": "string"},
                "access_token": {"type": "string", "description": "Management API access token"},
            },
            "required": ["domain", "client_id", "client_secret"],
        },
        required_scopes=[
            "read:users",
            "read:users_app_metadata",
            "read:roles",
            "read:clients",
            "read:connections",
            "read:logs",
        ],
        supported_operations=[
            "list_users",
            "get_user",
            "create_user",
            "update_user",
            "delete_user",
            "get_user_logs",
            "list_roles",
            "get_role",
            "assign_role",
            "remove_role",
            "list_clients",
            "get_client",
            "list_connections",
            "get_connection",
            "list_logs",
        ],
        webhook_events=[
            "user.created",
            "user.updated",
            "user.deleted",
            "user.logged_in",
            "user.logged_out",
            "role.assigned",
            "role.removed",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=100,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/auth0.svg",
        documentation_url="https://auth0.com/docs/api/management/v2",
    )

    BASE_URL_TEMPLATE = "https://{domain}/api/v2"
    TOKEN_URL_TEMPLATE = "https://{domain}/oauth/token"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.domain = connection_config.get("domain")
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self.audience = connection_config.get("audience")
        self.access_token = connection_config.get("access_token")
        self.base_url = self.BASE_URL_TEMPLATE.format(domain=self.domain) if self.domain else None
        self.token_url = self.TOKEN_URL_TEMPLATE.format(domain=self.domain) if self.domain else None
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Auth0 using Management API token or OAuth2."""
        if self.access_token:
            self._authenticated = True
            logger.info("Auth0 authenticated with access token")
            return True

        if self.client_id and self.client_secret and self.domain:
            from app.connectors.base import TokenManager
            self._token_manager = TokenManager(self.client_id, self.client_secret, self.token_url)
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("Auth0 authenticated with OAuth2")
            return True

        raise ValueError("Auth0 requires access_token or OAuth2 credentials (domain, client_id, client_secret)")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make Auth0 Management API request with error handling."""
        if not self._authenticated:
            await self.authenticate()

        if not self.base_url:
            raise ValueError("Auth0 domain not configured")

        url = urljoin(self.base_url, endpoint)
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        async def _request():
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    raise aiohttp.ClientResponseError(
                        resp.request_info,
                        resp.history,
                        status=429,
                        message=f"Rate limited, retry after {retry_after}s"
                    )
                if resp.status >= 400:
                    error_text = await resp.text()
                    raise Exception(f"Auth0 API error: {resp.status} - {error_text}")
                return await resp.json()

        return await self.retry_policy.execute(_request)

    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not self._authenticated:
            await self.authenticate()

        handlers = {
            "list_users": self._list_users,
            "get_user_logs": self._get_user_logs,
            "list_roles": self._list_roles,
            "list_clients": self._list_clients,
            "list_connections": self._list_connections,
            "list_logs": self._list_logs,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100, "include_totals": "false"}
        if filters:
            for key in ["q", "search_engine", "fields", "include_fields", "sort", "connection"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/users", params=params)
            for user in data:
                yield {
                    "type": "user",
                    "id": user["user_id"],
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            # Auth0 uses page-based pagination
            if len(data) < params["per_page"]:
                break
            params["page"] = params.get("page", 0) + 1

    async def _get_user_logs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if filters:
            for key in ["user_id", "client_id", "connection_id", "type", "start", "end"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/logs", params=params)
            for log in data:
                yield {
                    "type": "log",
                    "id": log.get("log_id", ""),
                    "data": log,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data) < params["per_page"]:
                break
            params["page"] = params.get("page", 0) + 1

    async def _list_roles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/roles", params=params)
            for role in data:
                yield {
                    "type": "role",
                    "id": role["id"],
                    "data": role,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data) < params["per_page"]:
                break
            params["page"] = params.get("page", 0) + 1

    async def _list_clients(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if filters:
            for key in ["name", "app_type", "is_first_party", "is_global"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/clients", params=params)
            for client in data:
                yield {
                    "type": "client",
                    "id": client["client_id"],
                    "data": client,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data) < params["per_page"]:
                break
            params["page"] = params.get("page", 0) + 1

    async def _list_connections(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if filters and filters.get("strategy"):
            params["strategy"] = filters["strategy"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/connections", params=params)
            for conn in data:
                yield {
                    "type": "connection",
                    "id": conn["id"],
                    "data": conn,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data) < params["per_page"]:
                break
            params["page"] = params.get("page", 0) + 1

    async def _list_logs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100, "include_totals": "false"}
        if filters:
            for key in ["q", "page", "per_page", "sort", "take", "from", "to"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/logs", params=params)
            for log in data.get("logs", []):
                yield {
                    "type": "log",
                    "id": log.get("log_id", ""),
                    "data": log,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("logs", [])) < params["per_page"]:
                break
            params["page"] = params.get("page", 0) + 1

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_user": self._create_user,
            "update_user": self._update_user,
            "delete_user": self._delete_user,
            "assign_role": self._assign_role,
            "remove_role": self._remove_role,
        }

        handler = handlers.get(operation)
        if not handler:
            result.success = False
            result.errors.append({"error": f"Unsupported push operation: {operation}"})
            return result

        for item in data:
            try:
                await handler(item)
                result.records_created += 1 if "create" in operation else 0
                result.records_updated += 1 if "update" in operation or "assign" in operation or "remove" in operation else 0
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_user(self, user_data: Dict[str, Any]):
        payload = user_data.get("user", {})
        await self._make_request("POST", "/users", json=payload)

    async def _update_user(self, user_data: Dict[str, Any]):
        user_id = user_data.get("user_id")
        if not user_id:
            raise ValueError("user_id required")
        payload = user_data.get("user", {})
        await self._make_request("PATCH", f"/users/{user_id}", json=payload)

    async def _delete_user(self, user_data: Dict[str, Any]):
        user_id = user_data.get("user_id")
        if not user_id:
            raise ValueError("user_id required")
        await self._make_request("DELETE", f"/users/{user_id}")

    async def _assign_role(self, role_data: Dict[str, Any]):
        role_id = role_data.get("role_id")
        user_id = role_data.get("user_id")
        if not role_id or not user_id:
            raise ValueError("role_id and user_id required")
        await self._make_request("POST", f"/roles/{role_id}/users", json={"users": [user_id]})

    async def _remove_role(self, role_data: Dict[str, Any]):
        role_id = role_data.get("role_id")
        user_id = role_data.get("user_id")
        if not role_id or not user_id:
            raise ValueError("role_id and user_id required")
        await self._make_request("DELETE", f"/roles/{role_id}/users", json={"users": [user_id]})

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/users", params={"per_page": 1})
            return isinstance(data, list)
        except Exception as e:
            logger.error(f"Auth0 connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(Auth0Connector, Auth0Connector.CONFIG)