"""
Ping Identity (PingOne) Connector for VCOS.

Provides integration with Ping Identity for identity management and authentication.
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


class PingConnector(BaseConnector):
    """Ping Identity (PingOne) Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="ping",
        display_name="Ping Identity",
        description="Enterprise identity and access management platform",
        category="identity",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "environment_id": {"type": "string", "description": "PingOne environment ID"},
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "region": {"type": "string", "default": "US", "enum": ["US", "EU", "CA", "AU", "AP"]},
                "access_token": {"type": "string", "description": "Management API access token"},
            },
            "required": ["environment_id", "client_id", "client_secret"],
        },
        required_scopes=[
            "p1:read:user",
            "p1:read:population",
            "p1:read:role",
            "p1:read:group",
            "p1:read:application",
        ],
        supported_operations=[
            "list_users",
            "get_user",
            "create_user",
            "update_user",
            "delete_user",
            "list_populations",
            "get_population",
            "list_roles",
            "get_role",
            "assign_role",
            "remove_role",
            "list_groups",
            "get_group",
            "add_user_to_group",
            "remove_user_from_group",
            "list_applications",
            "get_application",
        ],
        webhook_events=[
            "user.created",
            "user.updated",
            "user.deleted",
            "user.activated",
            "user.deactivated",
            "role.assigned",
            "role.removed",
            "group.member.added",
            "group.member.removed",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=20,
            requests_per_minute=200,
            burst=50,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/pingidentity.svg",
        documentation_url="https://apidocs.pingidentity.com/pingone/v1/",
    )

    REGION_URLS = {
        "US": "https://api.pingone.com/v1",
        "EU": "https://api.eu.pingone.com/v1",
        "CA": "https://api.ca.pingone.com/v1",
        "AU": "https://api.au.pingone.com/v1",
        "AP": "https://api.ap.pingone.com/v1",
    }
    TOKEN_URL_TEMPLATE = "https://auth.pingone.com/{environment_id}/as/token"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.environment_id = connection_config.get("environment_id")
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self.region = connection_config.get("region", "US")
        self.access_token = connection_config.get("access_token")
        self.base_url = self.REGION_URLS.get(self.region, self.REGION_URLS["US"])
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with PingOne using access token or OAuth2 client credentials."""
        if self.access_token:
            self._authenticated = True
            logger.info("Ping authenticated with access token")
            return True

        if self.client_id and self.client_secret and self.environment_id:
            from app.connectors.base import TokenManager
            token_url = self.TOKEN_URL_TEMPLATE.format(environment_id=self.environment_id)
            self._token_manager = TokenManager(self.client_id, self.client_secret, token_url)
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("Ping authenticated with OAuth2")
            return True

        raise ValueError("Ping requires access_token or OAuth2 credentials (environment_id, client_id, client_secret)")

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
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.base_url, f"/environments/{self.environment_id}{endpoint}")
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
                    raise Exception(f"Ping API error: {resp.status} - {error_text}")
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
            "list_populations": self._list_populations,
            "list_roles": self._list_roles,
            "list_groups": self._list_groups,
            "list_applications": self._list_applications,
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
        params = {"limit": 100}
        if filters:
            for key in ["filter", "expand", "sort"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/users", params=params)
            for user in data.get("_embedded", {}).get("users", []):
                yield {
                    "type": "user",
                    "id": user["id"],
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            links = data.get("_links", {})
            if "next" in links:
                # Extract cursor from next link
                next_url = links["next"]["href"]
                import re
                match = re.search(r"cursor=([^&]+)", next_url)
                if match:
                    params["cursor"] = match.group(1)
                else:
                    break
            else:
                break

    async def _list_populations(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/populations", params=params)
            for pop in data.get("_embedded", {}).get("populations", []):
                yield {
                    "type": "population",
                    "id": pop["id"],
                    "data": pop,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            links = data.get("_links", {})
            if "next" in links:
                next_url = links["next"]["href"]
                import re
                match = re.search(r"cursor=([^&]+)", next_url)
                if match:
                    params["cursor"] = match.group(1)
                else:
                    break
            else:
                break

    async def _list_roles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/roles", params=params)
            for role in data.get("_embedded", {}).get("roles", []):
                yield {
                    "type": "role",
                    "id": role["id"],
                    "data": role,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            links = data.get("_links", {})
            if "next" in links:
                next_url = links["next"]["href"]
                import re
                match = re.search(r"cursor=([^&]+)", next_url)
                if match:
                    params["cursor"] = match.group(1)
                else:
                    break
            else:
                break

    async def _list_groups(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters and filters.get("population_id"):
            params["populationId"] = filters["population_id"]
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/groups", params=params)
            for group in data.get("_embedded", {}).get("groups", []):
                yield {
                    "type": "group",
                    "id": group["id"],
                    "data": group,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            links = data.get("_links", {})
            if "next" in links:
                next_url = links["next"]["href"]
                import re
                match = re.search(r"cursor=([^&]+)", next_url)
                if match:
                    params["cursor"] = match.group(1)
                else:
                    break
            else:
                break

    async def _list_applications(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/applications", params=params)
            for app in data.get("_embedded", {}).get("applications", []):
                yield {
                    "type": "application",
                    "id": app["id"],
                    "data": app,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            links = data.get("_links", {})
            if "next" in links:
                next_url = links["next"]["href"]
                import re
                match = re.search(r"cursor=([^&]+)", next_url)
                if match:
                    params["cursor"] = match.group(1)
                else:
                    break
            else:
                break

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

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/environments", params={"limit": 1})
            return "_embedded" in data
        except Exception as e:
            logger.error(f"Ping connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(PingConnector, PingConnector.CONFIG)