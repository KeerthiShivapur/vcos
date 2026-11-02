"""
ServiceNow Connector for VCOS.

Provides integration with ServiceNow for IT service management.
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


class ServiceNowConnector(BaseConnector):
    """ServiceNow Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="servicenow",
        display_name="ServiceNow",
        description="IT service management platform",
        category="itsm",
        auth_type=AuthType.BASIC_AUTH,
        config_schema={
            "type": "object",
            "properties": {
                "instance_url": {"type": "string", "description": "ServiceNow instance URL (e.g., https://your-instance.service-now.com)"},
                "username": {"type": "string", "description": "Username for basic auth"},
                "password": {"type": "string", "description": "Password for basic auth"},
                "client_id": {"type": "string", "description": "OAuth client ID"},
                "client_secret": {"type": "string", "description": "OAuth client secret"},
            },
            "required": ["instance_url"],
        },
        required_scopes=[],
        supported_operations=[
            "list_incidents",
            "get_incident",
            "create_incident",
            "update_incident",
            "list_problems",
            "get_problem",
            "create_problem",
            "list_changes",
            "get_change",
            "create_change",
            "list_tasks",
            "get_task",
            "list_users",
            "get_user",
            "list_groups",
            "get_group",
            "list_catalog_items",
            "get_catalog_item",
            "list_knowledge_articles",
            "get_knowledge_article",
        ],
        webhook_events=[],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=60,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/servicenow.svg",
        documentation_url="https://developer.servicenow.com/dev.do#!/reference/api",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.instance_url = connection_config.get("instance_url", "").rstrip("/")
        self.username = connection_config.get("username")
        self.password = connection_config.get("password")
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self._auth_header = None
        self._oauth_token = None

    async def authenticate(self) -> bool:
        """Authenticate with ServiceNow using Basic Auth or OAuth."""
        if self.username and self.password:
            import base64
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            self._auth_header = f"Basic {credentials}"
            self._authenticated = True
            logger.info("ServiceNow authenticated with Basic Auth")
            return True

        if self.client_id and self.client_secret:
            # OAuth authentication
            await self._get_oauth_token()
            return True

        raise ValueError("ServiceNow requires username/password or client_id/client_secret")

    async def _get_oauth_token(self):
        """Get OAuth token for ServiceNow."""
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with self.session.post(
            f"{self.instance_url}/oauth_token.do",
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"}
        ) as resp:
            if resp.status == 200:
                data = await resp.json()
                self._oauth_token = data["access_token"]
                self._authenticated = True
            else:
                raise Exception(f"OAuth failed: {await resp.text()}")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._auth_header:
            headers["Authorization"] = self._auth_header
        elif self._oauth_token:
            headers["Authorization"] = f"Bearer {self._oauth_token}"
        return headers

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.instance_url, f"/api/now{endpoint}")
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
                    raise Exception(f"ServiceNow API error: {resp.status} - {error_text}")
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
            "list_incidents": self._list_incidents,
            "list_problems": self._list_problems,
            "list_changes": self._list_changes,
            "list_tasks": self._list_tasks,
            "list_users": self._list_users,
            "list_groups": self._list_groups,
            "list_catalog_items": self._list_catalog_items,
            "list_knowledge_articles": self._list_knowledge_articles,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_incidents(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"sysparm_limit": 100}
        if filters:
            for key in ["state", "priority", "category", "assignment_group", "assigned_to", "opened_at", "sys_created_on"]:
                if key in filters:
                    params[f"sysparm_query"] = params.get("sysparm_query", "") + f"{key}={filters[key]}^"
        if cursor and cursor.cursor:
            params["sysparm_offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/now/table/incident", params=params)
            for incident in data.get("result", []):
                yield {
                    "type": "incident",
                    "id": incident["sys_id"],
                    "data": incident,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("result", [])) < 100:
                break
            params["sysparm_offset"] = params.get("sysparm_offset", 0) + 100

    async def _list_problems(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"sysparm_limit": 100}
        if filters:
            for key in ["state", "priority", "category", "assignment_group"]:
                if key in filters:
                    params["sysparm_query"] = params.get("sysparm_query", "") + f"{key}={filters[key]}^"
        if cursor and cursor.cursor:
            params["sysparm_offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/now/table/problem", params=params)
            for problem in data.get("result", []):
                yield {
                    "type": "problem",
                    "id": problem["sys_id"],
                    "data": problem,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("result", [])) < 100:
                break
            params["sysparm_offset"] = params.get("sysparm_offset", 0) + 100

    async def _list_changes(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"sysparm_limit": 100}
        if filters:
            for key in ["state", "priority", "category", "assignment_group", "start_date", "end_date"]:
                if key in filters:
                    params["sysparm_query"] = params.get("sysparm_query", "") + f"{key}={filters[key]}^"
        if cursor and cursor.cursor:
            params["sysparm_offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/now/table/change_request", params=params)
            for change in data.get("result", []):
                yield {
                    "type": "change",
                    "id": change["sys_id"],
                    "data": change,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("result", [])) < 100:
                break
            params["sysparm_offset"] = params.get("sysparm_offset", 0) + 100

    async def _list_tasks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"sysparm_limit": 100}
        if filters:
            for key in ["state", "priority", "assignment_group", "assigned_to"]:
                if key in filters:
                    params["sysparm_query"] = params.get("sysparm_query", "") + f"{key}={filters[key]}^"
        if cursor and cursor.cursor:
            params["sysparm_offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/now/table/task", params=params)
            for task in data.get("result", []):
                yield {
                    "type": "task",
                    "id": task["sys_id"],
                    "data": task,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("result", [])) < 100:
                break
            params["sysparm_offset"] = params.get("sysparm_offset", 0) + 100

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"sysparm_limit": 100}
        if filters:
            for key in ["active", "department", "location", "manager"]:
                if key in filters:
                    params["sysparm_query"] = params.get("sysparm_query", "") + f"{key}={filters[key]}^"
        if cursor and cursor.cursor:
            params["sysparm_offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/now/table/sys_user", params=params)
            for user in data.get("result", []):
                yield {
                    "type": "user",
                    "id": user["sys_id"],
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("result", [])) < 100:
                break
            params["sysparm_offset"] = params.get("sysparm_offset", 0) + 100

    async def _list_groups(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"sysparm_limit": 100}
        if cursor and cursor.cursor:
            params["sysparm_offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/now/table/sys_user_group", params=params)
            for group in data.get("result", []):
                yield {
                    "type": "group",
                    "id": group["sys_id"],
                    "data": group,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("result", [])) < 100:
                break
            params["sysparm_offset"] = params.get("sysparm_offset", 0) + 100

    async def _list_catalog_items(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"sysparm_limit": 100}
        if filters:
            for key in ["category", "active", "catalog"]:
                if key in filters:
                    params["sysparm_query"] = params.get("sysparm_query", "") + f"{key}={filters[key]}^"
        if cursor and cursor.cursor:
            params["sysparm_offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/now/table/sc_cat_item", params=params)
            for item in data.get("result", []):
                yield {
                    "type": "catalog_item",
                    "id": item["sys_id"],
                    "data": item,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("result", [])) < 100:
                break
            params["sysparm_offset"] = params.get("sysparm_offset", 0) + 100

    async def _list_knowledge_articles(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"sysparm_limit": 100}
        if filters:
            for key in ["workflow_state", "knowledge_base", "category"]:
                if key in filters:
                    params["sysparm_query"] = params.get("sysparm_query", "") + f"{key}={filters[key]}^"
        if cursor and cursor.cursor:
            params["sysparm_offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/api/now/table/kb_knowledge", params=params)
            for article in data.get("result", []):
                yield {
                    "type": "knowledge_article",
                    "id": article["sys_id"],
                    "data": article,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("result", [])) < 100:
                break
            params["sysparm_offset"] = params.get("sysparm_offset", 0) + 100

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_incident": self._create_incident,
            "update_incident": self._update_incident,
            "create_problem": self._create_problem,
            "create_change": self._create_change,
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

    async def _create_incident(self, incident_data: Dict[str, Any]):
        payload = incident_data.get("incident", {})
        await self._make_request("POST", "/api/now/table/incident", json=payload)

    async def _update_incident(self, incident_data: Dict[str, Any]):
        incident_id = incident_data.get("incident_id")
        if not incident_id:
            raise ValueError("incident_id required")
        payload = incident_data.get("incident", {})
        await self._make_request("PUT", f"/api/now/table/incident/{incident_id}", json=payload)

    async def _create_problem(self, problem_data: Dict[str, Any]):
        payload = problem_data.get("problem", {})
        await self._make_request("POST", "/api/now/table/problem", json=payload)

    async def _create_change(self, change_data: Dict[str, Any]):
        payload = change_data.get("change", {})
        await self._make_request("POST", "/api/now/table/change_request", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/api/now/table/incident", params={"sysparm_limit": 1})
            return "result" in data
        except Exception as e:
            logger.error(f"ServiceNow connection test failed: {e}")
            return False


import base64
from app.connectors.base import connector_registry
connector_registry.register(ServiceNowConnector, ServiceNowConnector.CONFIG)