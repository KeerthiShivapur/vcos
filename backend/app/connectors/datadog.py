"""
Datadog Connector for VCOS.

Provides integration with Datadog for monitoring, logging, and observability.
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


class DatadogConnector(BaseConnector):
    """Datadog Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="datadog",
        display_name="Datadog",
        description="Monitoring and analytics platform for cloud applications",
        category="observability",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Datadog API Key"},
                "app_key": {"type": "string", "description": "Datadog Application Key"},
                "site": {"type": "string", "enum": ["datadoghq.com", "datadoghq.eu", "us3.datadoghq.com", "us5.datadoghq.com", "ap1.datadoghq.com"], "default": "datadoghq.com"},
            },
            "required": ["api_key", "app_key"],
        },
        required_scopes=[],
        supported_operations=[
            "list_monitors",
            "get_monitor",
            "create_monitor",
            "update_monitor",
            "delete_monitor",
            "list_dashboards",
            "get_dashboard",
            "create_dashboard",
            "update_dashboard",
            "list_metrics",
            "query_metrics",
            "list_logs",
            "query_logs",
            "list_hosts",
            "get_host",
            "list_incidents",
            "get_incident",
            "list_slos",
            "get_slo",
            "list_synthetics_tests",
            "get_synthetics_test",
        ],
        webhook_events=[],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=60,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/datadog.svg",
        documentation_url="https://docs.datadoghq.com/api/",
    )

    BASE_URL_TEMPLATE = "https://api.{site}/api/v1"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.api_key = connection_config.get("api_key")
        self.app_key = connection_config.get("app_key")
        self.site = connection_config.get("site", "datadoghq.com")
        self.base_url = self.BASE_URL_TEMPLATE.format(site=self.site)

    async def authenticate(self) -> bool:
        """Authenticate with Datadog using API keys."""
        if not self.api_key or not self.app_key:
            raise ValueError("Datadog requires api_key and app_key")

        self._authenticated = True
        logger.info("Datadog authenticated with API keys")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "DD-API-KEY": self.api_key,
            "DD-APPLICATION-KEY": self.app_key,
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.base_url, endpoint)
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
                    raise Exception(f"Datadog API error: {resp.status} - {error_text}")
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
            "list_monitors": self._list_monitors,
            "list_dashboards": self._list_dashboards,
            "list_metrics": self._list_metrics,
            "query_metrics": self._query_metrics,
            "list_logs": self._list_logs,
            "query_logs": self._query_logs,
            "list_hosts": self._list_hosts,
            "list_incidents": self._list_incidents,
            "list_slos": self._list_slos,
            "list_synthetics_tests": self._list_synthetics_tests,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_monitors(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 0, "per_page": 100}
        if filters:
            for key in ["monitor_tags", "name", "type"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/monitor", params=params)
            for monitor in data:
                yield {
                    "type": "monitor",
                    "id": monitor["id"],
                    "data": monitor,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data) < 100:
                break
            params["page"] += 1

    async def _list_dashboards(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 0, "per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/dashboard/lists", params=params)
            for dashboard in data.get("dashboards", []):
                yield {
                    "type": "dashboard",
                    "id": dashboard["id"],
                    "data": dashboard,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("dashboards", [])) < 100:
                break
            params["page"] += 1

    async def _list_metrics(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 0, "per_page": 100}
        if filters and filters.get("filter"):
            params["filter"] = filters["filter"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/metrics", params=params)
            for metric in data.get("metrics", []):
                yield {
                    "type": "metric",
                    "id": metric,
                    "data": {"name": metric},
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("metrics", [])) < 100:
                break
            params["page"] += 1

    async def _query_metrics(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not filters or not filters.get("query"):
            raise ValueError("query required in filters")

        params = {
            "query": filters["query"],
            "from": filters.get("from", int(datetime.utcnow().timestamp()) - 3600),
            "to": filters.get("to", int(datetime.utcnow().timestamp())),
        }

        data = await self._make_request("GET", "/query", params=params)
        for series in data.get("series", []):
            yield {
                "type": "metric_query",
                "id": series["metric"],
                "data": series,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_logs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 0, "limit": 100}
        if filters:
            for key in ["query", "from", "to", "index"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/logs-queries/list", params=params)
            for log in data.get("logs", []):
                yield {
                    "type": "log",
                    "id": log.get("id", ""),
                    "data": log,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("logs", [])) < 100:
                break
            params["page"] += 1

    async def _query_logs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        if not filters or not filters.get("query"):
            raise ValueError("query required in filters")

        payload = {
            "filter": filters.get("filter", {}),
            "options": filters.get("options", {}),
            "page": {"limit": 100},
        }

        if cursor and cursor.cursor:
            payload["page"]["cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/logs-queries/list", json=payload)
            for log in data.get("logs", []):
                yield {
                    "type": "log",
                    "id": log.get("id", ""),
                    "data": log,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("page", {}).get("next_record_id"):
                break
            payload["page"]["cursor"] = data["page"]["next_record_id"]

    async def _list_hosts(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 0, "per_page": 100}
        if filters:
            for key in ["filter", "host_name"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/hosts", params=params)
            for host in data.get("hosts", []):
                yield {
                    "type": "host",
                    "id": host["id"],
                    "data": host,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("hosts", [])) < 100:
                break
            params["page"] += 1

    async def _list_incidents(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 0, "per_page": 100}
        if filters:
            for key in ["state", "priority", "service"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/incidents", params=params)
            for incident in data.get("incidents", []):
                yield {
                    "type": "incident",
                    "id": incident["id"],
                    "data": incident,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("incidents", [])) < 100:
                break
            params["page"] += 1

    async def _list_slos(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 0, "per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/slo", params=params)
            for slo in data.get("data", []):
                yield {
                    "type": "slo",
                    "id": slo["id"],
                    "data": slo,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("data", [])) < 100:
                break
            params["page"] += 1

    async def _list_synthetics_tests(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 0, "per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/synthetics/tests", params=params)
            for test in data.get("tests", []):
                yield {
                    "type": "synthetics_test",
                    "id": test["public_id"],
                    "data": test,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("tests", [])) < 100:
                break
            params["page"] += 1

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_monitor": self._create_monitor,
            "update_monitor": self._update_monitor,
            "delete_monitor": self._delete_monitor,
            "create_dashboard": self._create_dashboard,
            "update_dashboard": self._update_dashboard,
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
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_monitor(self, monitor_data: Dict[str, Any]):
        payload = monitor_data.get("monitor", {})
        await self._make_request("POST", "/monitor", json=payload)

    async def _update_monitor(self, monitor_data: Dict[str, Any]):
        monitor_id = monitor_data.get("monitor_id")
        if not monitor_id:
            raise ValueError("monitor_id required")
        payload = monitor_data.get("monitor", {})
        await self._make_request("PUT", f"/monitor/{monitor_id}", json=payload)

    async def _delete_monitor(self, monitor_data: Dict[str, Any]):
        monitor_id = monitor_data.get("monitor_id")
        if not monitor_id:
            raise ValueError("monitor_id required")
        await self._make_request("DELETE", f"/monitor/{monitor_id}")

    async def _create_dashboard(self, dashboard_data: Dict[str, Any]):
        payload = dashboard_data.get("dashboard", {})
        await self._make_request("POST", "/dashboard", json=payload)

    async def _update_dashboard(self, dashboard_data: Dict[str, Any]):
        dashboard_id = dashboard_data.get("dashboard_id")
        if not dashboard_id:
            raise ValueError("dashboard_id required")
        payload = dashboard_data.get("dashboard", {})
        await self._make_request("PUT", f"/dashboard/{dashboard_id}", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/validate")
            return data.get("valid", False)
        except Exception as e:
            logger.error(f"Datadog connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(DatadogConnector, DatadogConnector.CONFIG)