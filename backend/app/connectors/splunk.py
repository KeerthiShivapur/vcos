"""
Splunk Connector for VCOS.

Provides integration with Splunk for log management and SIEM.
"""

import base64
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


class SplunkConnector(BaseConnector):
    """Splunk Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="splunk",
        display_name="Splunk",
        description="Platform for searching, monitoring, and analyzing machine-generated data",
        category="observability",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "host": {"type": "string", "description": "Splunk host (e.g., https://your-splunk-instance.com:8089)"},
                "username": {"type": "string", "description": "Username for basic auth"},
                "password": {"type": "string", "description": "Password for basic auth"},
                "token": {"type": "string", "description": "Bearer token for authentication"},
            },
            "required": ["host"],
        },
        required_scopes=[],
        supported_operations=[
            "search",
            "list_saved_searches",
            "run_saved_search",
            "list_dashboards",
            "get_dashboard",
            "list_reports",
            "run_report",
            "list_alerts",
            "get_alert",
            "list_data_models",
            "get_data_model",
            "list_indices",
            "get_index",
            "list_sourcetypes",
        ],
        webhook_events=[],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=60,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/splunk.svg",
        documentation_url="https://docs.splunk.com/Documentation/Splunk/latest/RESTREF/RESTref",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.host = connection_config.get("host", "").rstrip("/")
        self.username = connection_config.get("username")
        self.password = connection_config.get("password")
        self.token = connection_config.get("token")

    async def authenticate(self) -> bool:
        """Authenticate with Splunk using token or basic auth."""
        if self.token:
            self._authenticated = True
            logger.info("Splunk authenticated with token")
            return True

        if self.username and self.password:
            import base64
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            self._auth_header = f"Basic {credentials}"
            self._authenticated = True
            logger.info("Splunk authenticated with basic auth")
            return True

        raise ValueError("Splunk requires token or username/password")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        elif hasattr(self, '_auth_header'):
            headers["Authorization"] = self._auth_header
        return headers

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.host, f"/services{endpoint}")
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        async def _request():
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    await asyncio.sleep(retry_after)
                    return await _request()
                if resp.status >= 400:
                    error_text = await resp.text()
                    raise Exception(f"Splunk API error: {resp.status} - {error_text}")
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
            "search": self._search,
            "list_saved_searches": self._list_saved_searches,
            "list_dashboards": self._list_dashboards,
            "list_reports": self._list_reports,
            "list_alerts": self._list_alerts,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _search(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        search_query = filters.get("query") if filters else None
        if not search_query:
            raise ValueError("query required in filters")

        params = {
            "search": search_query,
            "output_mode": "json",
            "count": 100,
        }
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/services/search/jobs/export", params=params)
            for result in data.get("results", []):
                yield {
                    "type": "event",
                    "id": result.get("_raw", ""),
                    "data": result,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("results"):
                break

    async def _list_saved_searches(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"output_mode": "json", "count": 100}
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/services/saved/searches", params=params)
            for search in data.get("entry", []):
                yield {
                    "type": "saved_search",
                    "id": search["name"],
                    "data": search["content"],
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("entry", [])) < 100:
                break

    async def _list_dashboards(self, cursor: Optional[SyncCursor], filters: Optional[Dict[str, Any]]) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"output_mode": "json", "count": 100}
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/services/data/ui/views", params=params)
            for dashboard in data.get("entry", []):
                yield {
                    "type": "dashboard",
                    "id": dashboard["name"],
                    "data": dashboard["content"],
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("entry", [])) < 100:
                break

    async def push_data(self, operation: str, data: List[Dict[str, Any]]) -> SyncResult:
        result = SyncResult(success=True, started_at=datetime.utcnow())
        result.errors.append({"error": "Write operations not yet implemented for Splunk"})
        result.success = False
        return result

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/services/server/info", params={"output_mode": "json"})
            return "entry" in data
        except Exception as e:
            logger.error(f"Splunk connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(SplunkConnector, SplunkConnector.CONFIG)