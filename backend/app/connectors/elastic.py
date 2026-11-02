"""
Elastic (Elasticsearch) Connector for VCOS.

Provides integration with Elasticsearch/OpenSearch for search, analytics, and observability.
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


class ElasticConnector(BaseConnector):
    """Elasticsearch/OpenSearch Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="elastic",
        display_name="Elasticsearch",
        description="Distributed search and analytics engine",
        category="search_analytics",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "hosts": {"type": "array", "items": {"type": "string"}, "description": "Elasticsearch hosts (e.g., ['https://localhost:9200'])"},
                "api_key": {"type": "string", "description": "Base64 encoded API key (id:key)"},
                "username": {"type": "string", "description": "Username for basic auth"},
                "password": {"type": "string", "description": "Password for basic auth"},
                "cloud_id": {"type": "string", "description": "Elastic Cloud deployment ID"},
                "api_key_id": {"type": "string", "description": "API key ID"},
                "api_key_value": {"type": "string", "description": "API key value"},
                "ca_certs": {"type": "string", "description": "Path to CA certificates"},
                "verify_certs": {"type": "boolean", "default": true},
            },
            "required": [],
        },
        required_scopes=[],
        supported_operations=[
            "search",
            "index_document",
            "get_document",
            "update_document",
            "delete_document",
            "bulk_index",
            "bulk_update",
            "bulk_delete",
            "create_index",
            "delete_index",
            "get_index",
            "list_indices",
            "create_index_template",
            "get_index_template",
            "list_index_templates",
            "rollover_index",
            "shrink_index",
            "split_index",
            "reindex",
            "scroll_search",
            "list_indices",
            "get_index_settings",
            "update_index_settings",
            "create_ilm_policy",
            "get_ilm_policy",
            "list_ilm_policies",
        ],
        webhook_events=[],
        rate_limits=RateLimitConfig(
            requests_per_second=50,
            requests_per_minute=500,
            burst=100,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/elasticsearch.svg",
        documentation_url="https://www.elastic.co/guide/en/elasticsearch/reference/current/rest-apis.html",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.hosts = connection_config.get("hosts", [])
        self.api_key = connection_config.get("api_key")
        self.username = connection_config.get("username")
        self.password = connection_config.get("password")
        self.cloud_id = connection_config.get("cloud_id")
        self.api_key_id = connection_config.get("api_key_id")
        self.api_key_value = connection_config.get("api_key_value")
        self.ca_certs = connection_config.get("ca_certs")
        self.verify_certs = connection_config.get("verify_certs", True)
        self._es_client = None
        self._async_client = None

    async def authenticate(self) -> bool:
        """Authenticate with Elasticsearch."""
        try:
            from elasticsearch import AsyncElasticsearch

            # Build client configuration
            kwargs = {
                "request_timeout": 30,
                "max_retries": 3,
                "retry_on_timeout": True,
            }

            if self.cloud_id:
                kwargs["cloud_id"] = self.cloud_id
            elif self.hosts:
                kwargs["hosts"] = self.hosts

            if self.api_key:
                import base64
                decoded = base64.b64decode(self.api_key).decode()
                api_key_id, api_key_value = decoded.split(":", 1)
                kwargs["api_key"] = (self.api_key_id or "default", self.api_key_value or "")
            elif self.username and self.password:
                kwargs["basic_auth"] = (self.username, self.password)

            if hasattr(self, "ca_certs") and self.ca_certs:
                kwargs["ca_certs"] = self.ca_certs
            kwargs["verify_certs"] = self.verify_certs

            from elasticsearch import AsyncElasticsearch
            self._async_client = AsyncElasticsearch(**kwargs)

            # Test connection
            await self._async_client.ping()
            self._authenticated = True
            logger.info("Elasticsearch authenticated")
            return True

        except Exception as e:
            logger.error(f"Elasticsearch authentication failed: {e}")
            raise

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.hosts[0] if self.hosts else f"https://{self.cloud_id}.es.io", endpoint)
        headers = {"Accept": "application/json", "Content-Type": "application/json"}

        await self.rate_limiter.acquire()

        async def _request():
            async with aiohttp.ClientSession() as session:
                async with session.request(method, url, headers=headers, **kwargs) as resp:
                    if resp.status == 429:
                        retry_after = int(resp.headers.get("Retry-After", "1"))
                        await asyncio.sleep(retry_after)
                        return await _request()
                    if resp.status >= 400:
                        error_text = await resp.text()
                        raise Exception(f"Elasticsearch API error: {resp.status} - {error_text}")
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
            "list_indices": self._list_indices,
            "scroll_search": self._scroll_search,
            "list_indices": self._list_indices,
            "get_index_settings": self._get_index_settings,
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
        index = filters.get("index") if filters else "*"
        query = filters.get("query", {"match_all": {}})
        size = filters.get("size", 100)
        from_ = filters.get("from", 0)

        if cursor and cursor.cursor:
            from_ = cursor.cursor

        body = {
            "query": query,
            "size": size,
            "from": from_,
        }

        data = await self._make_request("POST", f"/{filters.get('index', '*')}/_search", json=body)
        for hit in data.get("hits", {}).get("hits", []):
            yield {
                "type": "document",
                "id": hit["_id"],
                "data": hit["_source"],
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_indices(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        data = await self._make_request("GET", "/_cat/indices?format=json&h=index,docs.count,store.size,health,status")
        for index in data:
            yield {
                "type": "index",
                "id": index["index"],
                "data": index,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _scroll_search(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        index = filters.get("index", "*")
        query = filters.get("query", {"match_all": {}})
        scroll = filters.get("scroll", "5m")
        size = filters.get("size", 100)

        body = {"query": filters.get("query", {"match_all": {}}), "size": size}
        data = await self._make_request("POST", f"/{filters.get('index', '*')}/_search?scroll={scroll}", json=body)

        scroll_id = data.get("_scroll_id")
        hits = data.get("hits", {}).get("hits", [])

        while hits:
            for hit in hits:
                yield {
                    "type": "document",
                    "id": hit["_id"],
                    "data": hit["_source"],
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(hits) < filters.get("size", 100):
                break

            # Continue scrolling
            scroll_data = await self._make_request("POST", "/_search/scroll", json={"scroll": scroll, "scroll_id": scroll_id})
            scroll_id = scroll_data.get("_scroll_id")
            hits = scroll_data.get("hits", {}).get("hits", [])

        # Clear scroll
        await self._make_request("DELETE", "/_search/scroll", json={"scroll_id": [scroll_id]})

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "index_document": self._index_document,
            "bulk_index": self._bulk_index,
            "create_index": self._create_index,
            "delete_index": self._delete_index,
        }

        handler = {
            "index_document": self._index_document,
            "bulk_index": self._bulk_index,
            "create_index": self._create_index,
            "delete_index": self._delete_index,
        }.get(operation)

        if not handler:
            return SyncResult(success=False, started_at=datetime.utcnow(), errors=[{"error": f"Unsupported push operation: {operation}"}])

        result = SyncResult(success=True, started_at=datetime.utcnow())
        for item in data:
            try:
                await handler(item)
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/")
            return "version" in data
        except Exception as e:
            logger.error(f"Elasticsearch connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(ElasticConnector, ElasticConnector.CONFIG)