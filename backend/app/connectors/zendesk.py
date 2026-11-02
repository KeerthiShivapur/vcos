"""
Zendesk Connector for VCOS.

Provides integration with Zendesk for customer support and ticketing.
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


class ZendeskConnector(BaseConnector):
    """Zendesk Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="zendesk",
        display_name="Zendesk",
        description="Customer service and engagement platform",
        category="support",
        auth_type=AuthType.BASIC_AUTH,
        config_schema={
            "type": "object",
            "properties": {
                "subdomain": {"type": "string", "description": "Zendesk subdomain (e.g., yourcompany)"},
                "email": {"type": "string", "description": "Agent email for authentication"},
                "api_token": {"type": "string", "description": "API token for authentication"},
                "oauth_token": {"type": "string", "description": "OAuth access token"},
            },
            "required": ["subdomain"],
        },
        required_scopes=[],
        supported_operations=[
            "list_tickets",
            "get_ticket",
            "create_ticket",
            "update_ticket",
            "list_users",
            "get_user",
            "create_user",
            "update_user",
            "list_organizations",
            "get_organization",
            "create_organization",
            "list_groups",
            "get_group",
            "list_views",
            "get_view",
            "execute_view",
            "list_macros",
            "get_macro",
            "list_brands",
            "list_forms",
            "list_fields",
            "list_tags",
            "list_slas",
        ],
        webhook_events=[
            "ticket_created",
            "ticket_updated",
            "ticket_solved",
            "comment_created",
            "user_created",
            "organization_created",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=700,
            burst=100,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/zendesk.svg",
        documentation_url="https://developer.zendesk.com/api-reference/",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.subdomain = connection_config.get("subdomain")
        self.email = connection_config.get("email")
        self.api_token = connection_config.get("api_token")
        self.oauth_token = connection_config.get("oauth_token")

        if self.subdomain:
            self.base_url = f"https://{self.subdomain}.zendesk.com/api/v2"
        else:
            raise ValueError("Zendesk requires subdomain")

    async def authenticate(self) -> bool:
        """Authenticate with Zendesk using Basic Auth or OAuth."""
        if self.email and self.api_token:
            import base64
            credentials = base64.b64encode(f"{self.email}/token:{self.api_token}".encode()).decode()
            self._auth_header = f"Basic {credentials}"
            self._authenticated = True
            logger.info("Zendesk authenticated with Basic Auth (email/token)")
            return True

        if self.oauth_token:
            self._oauth_token = self.oauth_token
            self._authenticated = True
            logger.info("Zendesk authenticated with OAuth token")
            return True

        raise ValueError("Zendesk requires email/api_token or oauth_token")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self._auth_header:
            headers["Authorization"] = self._auth_header
        elif self.oauth_token:
            headers["Authorization"] = f"Bearer {self.oauth_token}"
        return headers

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
                    raise Exception(f"Zendesk API error: {resp.status} - {error_text}")
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
            "list_tickets": self._list_tickets,
            "list_users": self._list_users,
            "list_organizations": self._list_organizations,
            "list_groups": self._list_groups,
            "list_views": self._list_views,
            "execute_view": self._execute_view,
            "list_macros": self._list_macros,
            "list_brands": self._list_brands,
            "list_forms": self._list_forms,
            "list_fields": self._list_fields,
            "list_tags": self._list_tags,
            "list_slas": self._list_slas,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_tickets(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if filters:
            for key in ["status", "type", "priority", "assignee_id", "group_id", "organization_id", "tags"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/tickets.json", params=params)
            for ticket in data.get("tickets", []):
                yield {
                    "type": "ticket",
                    "id": str(ticket["id"]),
                    "data": ticket,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            # Zendesk uses cursor-based pagination
            if data.get("next_page"):
                params["page"] = data.get("next_page", "").split("page=")[-1].split("&")[0]
            else:
                break

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if filters:
            for key in ["role", "organization_id", "email", "external_id"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/users.json", params=params)
            for user in data.get("users", []):
                yield {
                    "type": "user",
                    "id": str(user["id"]),
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _list_organizations(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if filters:
            for key in ["name", "domain_names", "external_id"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/organizations.json", params=params)
            for org in data.get("organizations", []):
                yield {
                    "type": "organization",
                    "id": str(org["id"]),
                    "data": org,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _list_groups(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/groups.json", params=params)
            for group in data.get("groups", []):
                yield {
                    "type": "group",
                    "id": str(group["id"]),
                    "data": group,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _list_views(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if filters and filters.get("active"):
            params["active"] = filters["active"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/views.json", params=params)
            for view in data.get("views", []):
                yield {
                    "type": "view",
                    "id": str(view["id"]),
                    "data": view,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _execute_view(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        view_id = filters.get("view_id") if filters else None
        if not view_id:
            raise ValueError("view_id filter required for execute_view")

        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", f"/views/{view_id}/execute.json", params=params)
            for row in data.get("rows", []):
                yield {
                    "type": "view_row",
                    "id": str(row.get("ticket", {}).get("id", "")),
                    "data": row,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _list_macros(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if filters and filters.get("active"):
            params["active"] = filters["active"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/macros.json", params=params)
            for macro in data.get("macros", []):
                yield {
                    "type": "macro",
                    "id": str(macro["id"]),
                    "data": macro,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _list_brands(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/brands.json", params=params)
            for brand in data.get("brands", []):
                yield {
                    "type": "brand",
                    "id": str(brand["id"]),
                    "data": brand,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _list_forms(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/ticket_forms.json", params=params)
            for form in data.get("ticket_forms", []):
                yield {
                    "type": "form",
                    "id": str(form["id"]),
                    "data": form,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _list_fields(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/ticket_fields.json", params=params)
            for field in data.get("ticket_fields", []):
                yield {
                    "type": "field",
                    "id": str(field["id"]),
                    "data": field,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _list_tags(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if filters and filters.get("search"):
            params["search"] = filters["search"]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/tags.json", params=params)
            for tag in data.get("tags", []):
                yield {
                    "type": "tag",
                    "id": str(tag["id"]),
                    "data": tag,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def _list_slas(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"per_page": 100}
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/slas/policies.json", params=params)
            for sla in data.get("sla_policies", []):
                yield {
                    "type": "sla_policy",
                    "id": str(sla["id"]),
                    "data": sla,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if not data.get("next_page"):
                break
            params["page"] = data["next_page"].split("page=")[-1].split("&")[0]

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_ticket": self._create_ticket,
            "update_ticket": self._update_ticket,
            "create_user": self._create_user,
            "update_user": self._update_user,
            "create_organization": self._create_organization,
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

    async def _create_ticket(self, ticket_data: Dict[str, Any]):
        payload = {"ticket": ticket_data.get("ticket", {})}
        await self._make_request("POST", "/tickets.json", json=payload)

    async def _update_ticket(self, ticket_data: Dict[str, Any]):
        ticket_id = ticket_data.get("ticket_id")
        if not ticket_id:
            raise ValueError("ticket_id required")
        payload = {"ticket": ticket_data.get("ticket", {})}
        await self._make_request("PUT", f"/tickets/{ticket_id}.json", json=payload)

    async def _create_user(self, user_data: Dict[str, Any]):
        payload = {"user": user_data.get("user", {})}
        await self._make_request("POST", "/users.json", json=payload)

    async def _update_user(self, user_data: Dict[str, Any]):
        user_id = user_data.get("user_id")
        if not user_id:
            raise ValueError("user_id required")
        payload = {"user": user_data.get("user", {})}
        await self._make_request("PUT", f"/users/{user_id}.json", json=payload)

    async def _create_organization(self, org_data: Dict[str, Any]):
        payload = {"organization": org_data.get("organization", {})}
        await self._make_request("POST", "/organizations.json", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/users/me.json")
            return "user" in data
        except Exception as e:
            logger.error(f"Zendesk connection test failed: {e}")
            return False


import base64
from app.connectors.base import connector_registry
connector_registry.register(ZendeskConnector, ZendeskConnector.CONFIG)