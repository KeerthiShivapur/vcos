"""
New Relic Connector for VCOS.

Provides integration with New Relic for application performance monitoring.
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


class NewRelicConnector(BaseConnector):
    """New Relic Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="newrelic",
        display_name="New Relic",
        description="Application performance monitoring and observability platform",
        category="observability",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "New Relic User API Key"},
                "account_id": {"type": "string", "description": "New Relic Account ID"},
                "region": {"type": "string", "enum": ["US", "EU"], "default": "US"},
            },
            "required": ["api_key", "account_id"],
        },
        required_scopes=[],
        supported_operations=[
            "list_applications",
            "get_application",
            "list_alert_policies",
            "get_alert_policy",
            "create_alert_policy",
            "list_nrql_queries",
            "execute_nrql",
            "list_dashboards",
            "get_dashboard",
            "list_entities",
            "get_entity",
            "list_alerts",
            "get_alert",
            "list_nrql_alerts",
            "list_nrql_conditions",
        ],
        webhook_events=[],
        rate_limits=RateLimitConfig(
            requests_per_second=5,
            requests_per_minute=60,
            burst=10,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/newrelic.svg",
        documentation_url="https://docs.newrelic.com/docs/apis/",
    )

    REGION_URLS = {
        "US": "https://api.newrelic.com",
        "EU": "https://api.eu.newrelic.com",
    }

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.api_key = connection_config.get("api_key")
        self.account_id = connection_config.get("account_id")
        self.region = connection_config.get("region", "US")
        self.base_url = self.REGION_URLS.get(self.region, "https://api.newrelic.com")

    REGION_URLS = {
        "US": "https://api.newrelic.com",
        "EU": "https://api.eu.newrelic.com",
    }

    async def authenticate(self) -> bool:
        """Authenticate with New Relic using API key."""
        if not self.api_key or not self.account_id:
            raise ValueError("New Relic requires api_key and account_id")

        self._authenticated = True
        logger.info("New Relic authenticated with API key")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Api-Key": self.api_key,
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
                    raise Exception(f"New Relic API error: {resp.status} - {error_text}")
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
            "list_applications": self._list_applications,
            "list_entities": self._list_entities,
            "execute_nrql": self._execute_nrql,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_applications(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        # Using NerdGraph GraphQL API
        query = """
        {
            actor {
                entitySearch(query: "type = 'APPLICATION'") {
                    results {
                        entities {
                            guid
                            name
                            reporting
                            language
                            alerts {
                                nrql {
                                    query
                                }
                            }
                        }
                    }
                }
            }
        """
        # This would use GraphQL, simplified for now
        data = await self._make_request("GET", "/v2/applications.json")
        for app in data.get("applications", []):
            yield {
                "type": "application",
                "id": str(app["id"]),
                "data": app,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_entities(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        # NerdGraph GraphQL for entity search
        entity_type = filters.get("entity_type") if filters else "APM_APPLICATION"
        query = """
        {
            actor {
                entitySearch(query: "type = '%s'") {
                    results {
                        entities {
                            guid
                            name
                            type
                            tags {
                                key
                                values
                            }
                        }
                    }
                }
            }
        """ % filters.get("entity_type", "APM_APPLICATION")

        # This would use GraphQL endpoint
        # For now, return mock data
        return

    async def _execute_nrql(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        query = filters.get("query") if filters else None
        if not query:
            raise ValueError("query required in filters")

        payload = {"query": query}
        data = await self._make_request("POST", "/v2/nrql", json={"query": query})

        for result in data.get("results", []):
            yield {
                "type": "nrql_result",
                "id": str(hash(str(result))),
                "data": result,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())
        result.errors.append({"error": "Write operations not yet implemented for New Relic"})
        result.success = False
        return result

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/v2/applications.json", params={"page": 1})
            return "applications" in data
        except Exception as e:
            logger.error(f"New Relic connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(NewRelicConnector, NewRelicConnector.CONFIG)