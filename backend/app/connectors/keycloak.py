"""
Keycloak Connector for VCOS.

Provides integration with Keycloak for identity and access management.
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


class KeycloakConnector(BaseConnector):
    """Keycloak Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="keycloak",
        display_name="Keycloak",
        description="Open source identity and access management",
        category="identity",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "server_url": {"type": "string", "description": "Keycloak server URL (e.g., https://keycloak.example.com)"},
                "realm": {"type": "string", "description": "Keycloak realm name"},
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "admin_username": {"type": "string", "description": "Admin username for direct admin API access"},
                "admin_password": {"type": "string", "description": "Admin password for direct admin API access"},
            },
            "required": ["server_url", "realm", "client_id", "client_secret"],
        },
        required_scopes=[],
        supported_operations=[
            "list_users",
            "get_user",
            "create_user",
            "update_user",
            "delete_user",
            "get_user_groups",
            "add_user_to_group",
            "remove_user_from_group",
            "list_roles",
            "get_role",
            "create_role",
            "delete_role",
            "assign_role",
            "remove_role",
            "list_groups",
            "get_group",
            "create_group",
            "update_group",
            "delete_group",
            "list_clients",
            "get_client",
            "create_client",
        ],
        webhook_events=[],
        rate_limits=RateLimitConfig(
            requests_per_second=20,
            requests_per_minute=200,
            burst=50,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/keycloak.svg",
        documentation_url="https://www.keycloak.org/docs-api/latest/rest-api/index.html",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.server_url = connection_config.get("server_url", "").rstrip("/")
        self.realm = connection_config.get("realm")
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self.admin_username = connection_config.get("admin_username")
        self.admin_password = connection_config.get("admin_password")
        self._access_token = None
        self._token_expires = 0
        self._admin_token = None
        self._admin_token_expires = 0

    def _get_admin_url(self) -> str:
        return f"{self.server_url}/admin/realms/{self.realm}"

    def _get_token_url(self) -> str:
        return f"{self.server_url}/realms/{self.realm}/protocol/openid-connect/token"

    async def authenticate(self) -> bool:
        """Authenticate with Keycloak using client credentials or admin credentials."""
        if await self._get_client_token():
            self._authenticated = True
            return True

        if self.admin_username and self.admin_password:
            if await self._get_admin_token():
                self._authenticated = True
                return True

        raise ValueError("Keycloak requires client credentials or admin credentials")

    async def _get_client_token(self) -> bool:
        """Get access token using client credentials."""
        if not self.client_id or not self.client_secret:
            return False

        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }

        try:
            async with self.session.post(
                self._get_token_url(),
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._access_token = data["access_token"]
                    self._token_expires = time.time() + data.get("expires_in", 300)
                    return True
        except Exception as e:
            logger.warning(f"Client credentials auth failed: {e}")
        return False

    async def _get_admin_token(self) -> bool:
        """Get admin token using username/password."""
        if not self.admin_username or not self.admin_password:
            return False

        data = {
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": self.admin_username,
            "password": self.admin_password,
        }

        try:
            async with self.session.post(
                self._get_token_url(),
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._admin_token = data["access_token"]
                    self._admin_token_expires = time.time() + data.get("expires_in", 300)
                    return True
        except Exception as e:
            logger.warning(f"Admin credentials auth failed: {e}")
        return False

    async def _get_token(self) -> str:
        """Get valid token, preferring admin token for admin operations."""
        now = time.time()

        if self._admin_token and self._admin_token_expires > now + 60:
            return self._admin_token

        if self._access_token and self._token_expires > now + 60:
            return self._access_token

        if await self._get_admin_token():
            return self._admin_token

        if await self._get_client_token():
            return self._access_token

        raise Exception("Failed to obtain access token")

    async def _get_headers(self) -> Dict[str, str]:
        token = await self._get_token()
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self._get_admin_url(), endpoint)
        headers = await self._get_headers()

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
                    raise Exception(f"Keycloak API error: {resp.status} - {error_text}")
                if resp.status == 204:
                    return {}
                return await resp.json()

        return await self.retry_policy.execute(_request)

    async def authenticate(self) -> bool:
        """Authenticate with Keycloak."""
        return await self._get_client_token() or await self._get_admin_token()

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
            "list_roles": self._list_roles,
            "list_groups": self._list_groups,
            "list_clients": self._list_clients,
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
        params = {"max": 100, "briefRepresentation": "false"}
        if filters:
            for key in ["search", "email", "username", "firstName", "lastName", "enabled"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["first"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/users", params=params)
            for user in data:
                yield {
                    "type": "user",
                    "id": user["id"],
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data) < 100:
                break
            params["first"] = params.get("first", 0) + 100

    async def _list_roles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"max": 100}
        if cursor and cursor.cursor:
            params["first"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/roles", params=params)
            for role in data:
                yield {
                    "type": "role",
                    "id": role["id"],
                    "data": role,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data) < 100:
                break
            params["first"] = params.get("first", 0) + 100

    async def _list_groups(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"max": 100}
        if cursor and cursor.cursor:
            params["first"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/groups", params=params)
            for group in data:
                yield {
                    "type": "group",
                    "id": group["id"],
                    "data": group,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data) < 100:
                break
            params["first"] = params.get("first", 0) + 100

    async def _list_clients(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"max": 100}
        if filters:
            for key in ["clientId", "search"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["first"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/clients", params=params)
            for client in data:
                yield {
                    "type": "client",
                    "id": client["id"],
                    "data": client,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data) < 100:
                break
            params["first"] = params.get("first", 0) + 100

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
            "create_role": self._create_role,
            "delete_role": self._delete_role,
            "assign_role": self._assign_role,
            "remove_role": self._remove_role,
            "create_group": self._create_group,
            "update_group": self._update_group,
            "delete_group": self._delete_group,
            "create_client": self._create_client,
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
                result.records_updated += 1 if "update" in operation else 0
                result.records_deleted += 1 if "delete" in operation else 0
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
        await self._make_request("PUT", f"/users/{user_id}", json=payload)

    async def _delete_user(self, user_data: Dict[str, Any]):
        user_id = user_data.get("user_id")
        if not user_id:
            raise ValueError("user_id required")
        await self._make_request("DELETE", f"/users/{user_id}")

    async def _create_role(self, role_data: Dict[str, Any]):
        payload = role_data.get("role", {})
        await self._make_request("POST", "/roles", json=payload)

    async def _delete_role(self, role_data: Dict[str, Any]):
        role_id = role_data.get("role_id")
        if not role_id:
            raise ValueError("role_id required")
        await self._make_request("DELETE", f"/roles/{role_id}")

    async def _assign_role(self, role_data: Dict[str, Any]):
        user_id = role_data.get("user_id")
        role_id = role_data.get("role_id")
        if not user_id or not role_id:
            raise ValueError("user_id and role_id required")
        role = await self._make_request("GET", f"/roles/{role_id}")
        await self._make_request("POST", f"/users/{user_id}/role-mappings/realm", json=[role])

    async def _remove_role(self, role_data: Dict[str, Any]):
        user_id = role_data.get("user_id")
        role_id = role_data.get("role_id")
        if not user_id or not role_id:
            raise ValueError("user_id and role_id required")
        role = await self._make_request("GET", f"/roles/{role_id}")
        await self._make_request("DELETE", f"/users/{user_id}/role-mappings/realm", json=[role])

    async def _create_group(self, group_data: Dict[str, Any]):
        payload = group_data.get("group", {})
        await self._make_request("POST", "/groups", json=payload)

    async def _update_group(self, group_data: Dict[str, Any]):
        group_id = group_data.get("group_id")
        if not group_id:
            raise ValueError("group_id required")
        payload = group_data.get("group", {})
        await self._make_request("PUT", f"/groups/{group_id}", json=payload)

    async def _delete_group(self, group_data: Dict[str, Any]):
        group_id = group_data.get("group_id")
        if not group_id:
            raise ValueError("group_id required")
        await self._make_request("DELETE", f"/groups/{group_id}")

    async def _create_client(self, client_data: Dict[str, Any]):
        payload = client_data.get("client", {})
        await self._make_request("POST", "/clients", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/users", params={"max": 1})
            return isinstance(data, list)
        except Exception as e:
            logger.error(f"Keycloak connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(KeycloakConnector, KeycloakConnector.CONFIG)