"""
Notion Connector for VCOS.

Provides integration with Notion for pages, databases, blocks, and comments.
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


class NotionConnector(BaseConnector):
    """Notion Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="notion",
        display_name="Notion",
        description="All-in-one workspace for notes, docs, and databases",
        category="productivity",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "access_token": {"type": "string", "description": "Notion integration token"},
                "workspace_id": {"type": "string", "description": "Notion workspace ID"},
            },
            "required": ["client_id", "client_secret", "redirect_uri"],
        },
        required_scopes=[
            "read_content",
            "update_content",
            "insert_content",
            "delete_content",
            "read_comments",
            "write_comments",
            "read_users",
            "write_users",
        ],
        supported_operations=[
            "list_pages",
            "get_page",
            "create_page",
            "update_page",
            "delete_page",
            "list_databases",
            "get_database",
            "query_database",
            "create_database_item",
            "update_database_item",
            "list_blocks",
            "get_block",
            "append_blocks",
            "update_block",
            "delete_block",
            "list_comments",
            "create_comment",
            "list_users",
            "search",
        ],
        webhook_events=[
            "page.created",
            "page.updated",
            "page.deleted",
            "database.created",
            "database.updated",
            "database.deleted",
            "block.created",
            "block.updated",
            "block.deleted",
            "comment.created",
            "comment.updated",
            "comment.deleted",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=3,
            requests_per_minute=100,
            burst=10,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/notion.svg",
        documentation_url="https://developers.notion.com/reference",
    )

    BASE_URL = "https://api.notion.com/v1"
    TOKEN_URL = "https://api.notion.com/v1/oauth/token"
    API_VERSION = "2022-06-28"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.access_token = connection_config.get("access_token")
        self.workspace_id = connection_config.get("workspace_id")
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Notion using OAuth2 or integration token."""
        if self.access_token:
            self._authenticated = True
            logger.info("Notion authenticated with integration token")
            return True

        client_id = self.connection_config.get("client_id")
        client_secret = self.connection_config.get("client_secret")
        
        if client_id and client_secret:
            from app.connectors.base import TokenManager
            self._token_manager = TokenManager(client_id, client_secret, self.TOKEN_URL)
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("Notion authenticated with OAuth2")
            return True

        raise ValueError("Notion requires access_token or OAuth2 credentials (client_id, client_secret)")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Notion-Version": self.API_VERSION,
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        elif self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make Notion API request with error handling."""
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.BASE_URL, endpoint)
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
                    raise Exception(f"Notion API error: {resp.status} - {error_text}")
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
            "list_pages": self._list_pages,
            "list_databases": self._list_databases,
            "query_database": self._query_database,
            "list_blocks": self._list_blocks,
            "list_comments": self._list_comments,
            "list_users": self._list_users,
            "search": self._search,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_pages(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List pages using search API with filter."""
        payload = {
            "filter": {"property": "object", "value": "page"},
            "page_size": 100,
        }
        if cursor and cursor.cursor:
            payload["start_cursor"] = cursor.cursor
        if filters and filters.get("query"):
            payload["query"] = filters["query"]

        while True:
            data = await self._make_request("POST", "/search", json=payload)
            for page in data.get("results", []):
                if page["object"] == "page":
                    yield {
                        "type": "page",
                        "id": page["id"],
                        "data": page,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

            if data.get("has_more") and data.get("next_cursor"):
                payload["start_cursor"] = data["next_cursor"]
            else:
                break

    async def _list_databases(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List databases using search API with filter."""
        payload = {
            "filter": {"property": "object", "value": "database"},
            "page_size": 100,
        }
        if cursor and cursor.cursor:
            payload["start_cursor"] = cursor.cursor
        if filters and filters.get("query"):
            payload["query"] = filters["query"]

        while True:
            data = await self._make_request("POST", "/search", json=payload)
            for db in data.get("results", []):
                if db["object"] == "database":
                    yield {
                        "type": "database",
                        "id": db["id"],
                        "data": db,
                        "synced_at": datetime.utcnow().isoformat(),
                    }

            if data.get("has_more") and data.get("next_cursor"):
                payload["start_cursor"] = data["next_cursor"]
            else:
                break

    async def _query_database(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Query a database."""
        database_id = filters.get("database_id")
        if not database_id:
            raise ValueError("database_id filter required")

        payload = {"page_size": 100}
        if filters and filters.get("filter"):
            payload["filter"] = filters["filter"]
        if filters and filters.get("sorts"):
            payload["sorts"] = filters["sorts"]
        if cursor and cursor.cursor:
            payload["start_cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", f"/databases/{database_id}/query", json=payload)
            for page in data.get("results", []):
                yield {
                    "type": "database_item",
                    "id": page["id"],
                    "data": page,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("has_more") and data.get("next_cursor"):
                payload["start_cursor"] = data["next_cursor"]
            else:
                break

    async def _list_blocks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List block children."""
        block_id = filters.get("block_id")
        if not block_id:
            raise ValueError("block_id filter required")

        params = {"page_size": 100}
        if cursor and cursor.cursor:
            params["start_cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/blocks/{block_id}/children", params=params)
            for block in data.get("results", []):
                yield {
                    "type": "block",
                    "id": block["id"],
                    "data": block,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("has_more") and data.get("next_cursor"):
                params["start_cursor"] = data["next_cursor"]
            else:
                break

    async def _list_comments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List comments on a page or block."""
        block_id = filters.get("block_id")
        if not block_id:
            raise ValueError("block_id filter required")

        params = {"page_size": 100}
        if cursor and cursor.cursor:
            params["start_cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/comments", params=params)
            for comment in data.get("results", []):
                yield {
                    "type": "comment",
                    "id": comment["id"],
                    "data": comment,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("has_more") and data.get("next_cursor"):
                params["start_cursor"] = data["next_cursor"]
            else:
                break

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List users in the workspace."""
        params = {"page_size": 100}
        if cursor and cursor.cursor:
            params["start_cursor"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/users", params=params)
            for user in data.get("results", []):
                yield {
                    "type": "user",
                    "id": user["id"],
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("has_more") and data.get("next_cursor"):
                params["start_cursor"] = data["next_cursor"]
            else:
                break

    async def _search(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Search across the workspace."""
        query = filters.get("query", "")
        payload = {
            "query": query,
            "page_size": 100,
        }
        if filters and filters.get("filter"):
            payload["filter"] = filters["filter"]
        if filters and filters.get("sort"):
            payload["sort"] = filters["sort"]
        if cursor and cursor.cursor:
            payload["start_cursor"] = cursor.cursor

        while True:
            data = await self._make_request("POST", "/search", json=payload)
            for result in data.get("results", []):
                yield {
                    "type": result["object"],
                    "id": result["id"],
                    "data": result,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if data.get("has_more") and data.get("next_cursor"):
                payload["start_cursor"] = data["next_cursor"]
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
            "create_page": self._create_page,
            "update_page": self._update_page,
            "delete_page": self._delete_page,
            "create_database_item": self._create_database_item,
            "update_database_item": self._update_database_item,
            "append_blocks": self._append_blocks,
            "update_block": self._update_block,
            "delete_block": self._delete_block,
            "create_comment": self._create_comment,
        }

        handler = handlers.get(operation)
        if not handler:
            result.success = False
            result.errors.append({"error": f"Unsupported push operation: {operation}"})
            return result

        for item in data:
            try:
                await handler(item)
                result.records_created += 1 if "create" in operation or "append" in operation else 0
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

    async def _create_page(self, page_data: Dict[str, Any]):
        """Create a new page."""
        parent = page_data.get("parent", {"workspace": True})
        properties = page_data.get("properties", {})
        children = page_data.get("children", [])

        payload = {
            "parent": parent,
            "properties": properties,
            "children": children,
        }
        await self._make_request("POST", "/pages", json=payload)

    async def _update_page(self, page_data: Dict[str, Any]):
        """Update page properties."""
        page_id = page_data.get("page_id")
        if not page_id:
            raise ValueError("page_id required")

        properties = page_data.get("properties", {})
        await self._make_request("PATCH", f"/pages/{page_id}", json={"properties": properties})

    async def _delete_page(self, page_data: Dict[str, Any]):
        """Archive (delete) a page."""
        page_id = page_data.get("page_id")
        if not page_id:
            raise ValueError("page_id required")

        await self._make_request("PATCH", f"/pages/{page_id}", json={"archived": True})

    async def _create_database_item(self, item_data: Dict[str, Any]):
        """Create a new database item (page)."""
        database_id = item_data.get("database_id")
        if not database_id:
            raise ValueError("database_id required")

        properties = item_data.get("properties", {})
        children = item_data.get("children", [])

        payload = {
            "parent": {"database_id": database_id},
            "properties": properties,
            "children": children,
        }
        await self._make_request("POST", "/pages", json=payload)

    async def _update_database_item(self, item_data: Dict[str, Any]):
        """Update a database item."""
        page_id = item_data.get("page_id")
        if not page_id:
            raise ValueError("page_id required")

        properties = item_data.get("properties", {})
        await self._make_request("PATCH", f"/pages/{page_id}", json={"properties": properties})

    async def _append_blocks(self, block_data: Dict[str, Any]):
        """Append blocks to a page or block."""
        block_id = block_data.get("block_id")
        if not block_id:
            raise ValueError("block_id required")

        children = block_data.get("children", [])
        await self._make_request("PATCH", f"/blocks/{block_id}/children", json={"children": children})

    async def _update_block(self, block_data: Dict[str, Any]):
        """Update a block."""
        block_id = block_data.get("block_id")
        if not block_id:
            raise ValueError("block_id required")

        payload = {k: v for k, v in block_data.items() if k != "block_id"}
        await self._make_request("PATCH", f"/blocks/{block_id}", json=payload)

    async def _delete_block(self, block_data: Dict[str, Any]):
        """Delete (archive) a block."""
        block_id = block_data.get("block_id")
        if not block_id:
            raise ValueError("block_id required")

        await self._make_request("PATCH", f"/blocks/{block_id}", json={"archived": True})

    async def _create_comment(self, comment_data: Dict[str, Any]):
        """Create a comment on a page or block."""
        parent = comment_data.get("parent")
        if not parent:
            raise ValueError("parent (page_id or block_id) required")

        rich_text = comment_data.get("rich_text", [])
        payload = {
            "parent": parent,
            "rich_text": rich_text,
        }
        await self._make_request("POST", "/comments", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/users/me")
            return "id" in data
        except Exception as e:
            logger.error(f"Notion connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(NotionConnector, NotionConnector.CONFIG)