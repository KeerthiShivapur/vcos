"""
Confluence Connector for VCOS.

Provides integration with Atlassian Confluence for wiki and documentation.
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


class ConfluenceConnector(BaseConnector):
    """Confluence Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="confluence",
        display_name="Confluence",
        description="Team workspace for documentation and knowledge sharing",
        category="collaboration",
        auth_type=AuthType.BASIC_AUTH,
        config_schema={
            "type": "object",
            "properties": {
                "server_url": {"type": "string", "description": "Confluence server URL (e.g., https://your-domain.atlassian.net)"},
                "email": {"type": "string", "description": "Email for basic auth"},
                "api_token": {"type": "string", "description": "API token for authentication"},
                "cloud": {"type": "boolean", "default": true, "description": "Whether using Confluence Cloud"},
            },
            "required": ["server_url", "email", "api_token"],
        },
        required_scopes=[],
        supported_operations=[
            "list_spaces",
            "get_space",
            "create_space",
            "update_space",
            "list_pages",
            "get_page",
            "create_page",
            "update_page",
            "delete_page",
            "list_blogs",
            "get_blog",
            "create_blog",
            "list_comments",
            "create_comment",
            "list_attachments",
            "upload_attachment",
            "download_attachment",
            "list_labels",
            "add_label",
            "remove_label",
            "search",
        ],
        webhook_events=[
            "page_created",
            "page_updated",
            "page_deleted",
            "comment_created",
            "attachment_created",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=60,
            burst=20,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/atlassian.svg",
        documentation_url="https://developer.atlassian.com/cloud/confluence/rest/",
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
        self.email = connection_config.get("email")
        self.api_token = connection_config.get("api_token")
        self.cloud = connection_config.get("cloud", True)

    async def authenticate(self) -> bool:
        """Authenticate with Confluence using Basic Auth."""
        if not self.email or not self.api_token:
            raise ValueError("Confluence requires email and api_token")

        import base64
        credentials = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        self._auth_header = f"Basic {credentials}"
        self._authenticated = True
        logger.info("Confluence authenticated with Basic Auth")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": self._auth_header,
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.server_url, f"/wiki/rest/api{endpoint}")
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
                    raise Exception(f"Confluence API error: {resp.status} - {error_text}")
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
            "list_spaces": self._list_spaces,
            "list_pages": self._list_pages,
            "list_blogs": self._list_blogs,
            "list_comments": self._list_comments,
            "list_attachments": self._list_attachments,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_spaces(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100, "start": 0}
        if filters:
            for key in ["spaceKey", "type", "status"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/space", params=params)
            for space in data.get("results", []):
                yield {
                    "type": "space",
                    "id": space["id"],
                    "data": space,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("results", [])) < params.get("limit", 100):
                break
            params["start"] += params["limit"]

    async def _list_pages(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        space_key = filters.get("spaceKey") if filters else None
        if not space_key:
            raise ValueError("spaceKey filter required for list_pages")

        params = {"limit": 100, "start": 0, "expand": "body.storage,version,space"}
        if filters:
            for key in ["title", "type", "status", "ancestorId"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            params["spaceKey"] = space_key
            data = await self._make_request("GET", "/content", params=params)
            for page in data.get("results", []):
                yield {
                    "type": "page",
                    "id": page["id"],
                    "data": page,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("results", [])) < params.get("limit", 100):
                break
            params["start"] += params["limit"]

    async def _list_blogs(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        space_key = filters.get("spaceKey") if filters else None
        if not space_key:
            raise ValueError("spaceKey filter required for list_blogs")

        params = {"limit": 100, "start": 0, "expand": "body.storage,version,space"}
        if filters:
            for key in ["title", "status"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            params["spaceKey"] = space_key
            data = await self._make_request("GET", "/content", params=params)
            for blog in data.get("results", []):
                yield {
                    "type": "blog",
                    "id": blog["id"],
                    "data": blog,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("results", [])) < params.get("limit", 100):
                break
            params["start"] += params["limit"]

    async def _list_comments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        content_id = filters.get("contentId") if filters else None
        if not content_id:
            raise ValueError("contentId filter required for list_comments")

        params = {"limit": 100, "start": 0, "expand": "body.storage,version"}
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/content/{content_id}/child/comment", params=params)
            for comment in data.get("results", []):
                yield {
                    "type": "comment",
                    "id": comment["id"],
                    "data": comment,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("results", [])) < params.get("limit", 100):
                break
            params["start"] += params["limit"]

    async def _list_attachments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        content_id = filters.get("contentId") if filters else None
        if not content_id:
            raise ValueError("contentId filter required for list_attachments")

        params = {"limit": 100, "start": 0}
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/content/{content_id}/child/attachment", params=params)
            for attachment in data.get("results", []):
                yield {
                    "type": "attachment",
                    "id": attachment["id"],
                    "data": attachment,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("results", [])) < params.get("limit", 100):
                break
            params["start"] += params["limit"]

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
            "create_blog": self._create_blog,
            "create_comment": self._create_comment,
            "upload_attachment": self._upload_attachment,
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

    async def _create_page(self, page_data: Dict[str, Any]):
        space_key = page_data.get("spaceKey")
        if not space_key:
            raise ValueError("spaceKey required")

        payload = {
            "type": "page",
            "title": page_data.get("title"),
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": page_data.get("body", ""),
                    "representation": "storage",
                },
            },
        }
        if page_data.get("ancestors"):
            payload["ancestors"] = [{"id": aid} for aid in page_data["ancestors"]]

        await self._make_request("POST", "/content", json=payload)

    async def _update_page(self, page_data: Dict[str, Any]):
        page_id = page_data.get("page_id")
        if not page_id:
            raise ValueError("page_id required")

        version = page_data.get("version", {})
        payload = {
            "version": {"number": version.get("number", 1) + 1},
            "title": page_data.get("title"),
            "body": {
                "storage": {
                    "value": page_data.get("body", ""),
                    "representation": "storage",
                },
            },
        }
        await self._make_request("PUT", f"/content/{page_id}", json=payload)

    async def _delete_page(self, page_data: Dict[str, Any]):
        page_id = page_data.get("page_id")
        if not page_id:
            raise ValueError("page_id required")

        version = page_data.get("version", {})
        params = {"version": version.get("number", 1)}
        await self._make_request("DELETE", f"/content/{page_id}", params=params)

    async def _create_blog(self, blog_data: Dict[str, Any]):
        space_key = blog_data.get("spaceKey")
        if not space_key:
            raise ValueError("spaceKey required")

        payload = {
            "type": "blogpost",
            "title": blog_data.get("title"),
            "space": {"key": space_key},
            "body": {
                "storage": {
                    "value": blog_data.get("body", ""),
                    "representation": "storage",
                },
            },
        }
        await self._make_request("POST", "/content", json=payload)

    async def _create_comment(self, comment_data: Dict[str, Any]):
        content_id = comment_data.get("contentId")
        if not content_id:
            raise ValueError("contentId required")

        payload = {
            "type": "comment",
            "container": {"id": content_id, "type": "page"},
            "body": {
                "storage": {
                    "value": comment_data.get("body", ""),
                    "representation": "storage",
                },
            },
        }
        await self._make_request("POST", "/content", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/space", params={"limit": 1})
            return "results" in data
        except Exception as e:
            logger.error(f"Confluence connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(ConfluenceConnector, ConfluenceConnector.CONFIG)