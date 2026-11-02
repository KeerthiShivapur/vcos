"""
Pipedrive Connector for VCOS.

Provides integration with Pipedrive for CRM data including deals, contacts, and activities.
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


class PipedriveConnector(BaseConnector):
    """Pipedrive Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="pipedrive",
        display_name="Pipedrive",
        description="Sales CRM and pipeline management software",
        category="crm",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "api_key": {"type": "string", "description": "Pipedrive API Key"},
                "company_domain": {"type": "string", "description": "Pipedrive company domain (e.g., 'mycompany' for mycompany.pipedrive.com)"},
            },
            "required": ["api_key", "company_domain"],
        },
        required_scopes=[],
        supported_operations=[
            "list_deals",
            "get_deal",
            "create_deal",
            "update_deal",
            "delete_deal",
            "list_persons",
            "get_person",
            "create_person",
            "update_person",
            "delete_person",
            "list_organizations",
            "get_organization",
            "create_organization",
            "update_organization",
            "delete_organization",
            "list_activities",
            "get_activity",
            "create_activity",
            "update_activity",
            "delete_activity",
            "list_pipelines",
            "get_pipeline",
            "list_stages",
            "get_stage",
            "list_users",
            "get_user",
            "list_products",
            "get_product",
            "create_product",
            "list_notes",
            "create_note",
            "list_files",
            "get_file",
            "list_webhooks",
            "create_webhook",
            "delete_webhook",
        ],
        webhook_events=[
            "deal.created",
            "deal.updated",
            "deal.deleted",
            "deal.stage_changed",
            "person.created",
            "person.updated",
            "person.deleted",
            "organization.created",
            "organization.updated",
            "organization.deleted",
            "activity.created",
            "activity.updated",
            "activity.deleted",
            "note.created",
            "note.updated",
            "note.deleted",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=20,
            requests_per_minute=100,
            burst=50,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/pipedrive.svg",
        documentation_url="https://developers.pipedrive.com/docs/api/v1",
    )

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.api_key = connection_config.get("api_key")
        self.company_domain = connection_config.get("company_domain")
        self.base_url = f"https://{self.company_domain}.pipedrive.com/api/v1"

    async def authenticate(self) -> bool:
        """Authenticate with Pipedrive using API Key."""
        if not self.api_key or not self.company_domain:
            raise ValueError("Pipedrive requires api_key and company_domain")

        self._authenticated = True
        logger.info("Pipedrive authenticated with API Key")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make Pipedrive API request with error handling."""
        if not self._authenticated:
            await self.authenticate()

        # Add api_token to query params
        params = kwargs.pop("params", {})
        params["api_token"] = self.api_key

        url = urljoin(self.base_url, endpoint)
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        async def _request():
            async with self.session.request(method, url, headers=headers, params=params, **kwargs) as resp:
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
                    raise Exception(f"Pipedrive API error: {resp.status} - {error_text}")
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
            "list_deals": self._list_deals,
            "list_persons": self._list_persons,
            "list_organizations": self._list_organizations,
            "list_activities": self._list_activities,
            "list_pipelines": self._list_pipelines,
            "list_stages": self._list_stages,
            "list_users": self._list_users,
            "list_products": self._list_products,
            "list_notes": self._list_notes,
            "list_files": self._list_files,
            "list_webhooks": self._list_webhooks,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_deals(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List deals."""
        params = {"limit": 100}
        if filters and filters.get("filter_id"):
            params["filter_id"] = filters["filter_id"]
        if filters and filters.get("stage_id"):
            params["stage_id"] = filters["stage_id"]
        if filters and filters.get("pipeline_id"):
            params["pipeline_id"] = filters["pipeline_id"]
        if filters and filters.get("status"):
            params["status"] = filters["status"]
        if filters and filters.get("start"):
            params["start"] = filters["start"]
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/deals", params=params)
            for deal in data.get("data", []):
                yield {
                    "type": "deal",
                    "id": str(deal["id"]),
                    "data": deal,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                params["start"] = pagination.get("next_start", 0)
            else:
                break

    async def _list_persons(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List persons (contacts)."""
        params = {"limit": 100}
        if filters and filters.get("filter_id"):
            params["filter_id"] = filters["filter_id"]
        if filters and filters.get("org_id"):
            params["org_id"] = filters["org_id"]
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/persons", params=params)
            for person in data.get("data", []):
                yield {
                    "type": "person",
                    "id": str(person["id"]),
                    "data": person,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                params["start"] = pagination.get("next_start", 0)
            else:
                break

    async def _list_organizations(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List organizations."""
        params = {"limit": 100}
        if filters and filters.get("filter_id"):
            params["filter_id"] = filters["filter_id"]
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/organizations", params=params)
            for org in data.get("data", []):
                yield {
                    "type": "organization",
                    "id": str(org["id"]),
                    "data": org,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                params["start"] = pagination.get("next_start", 0)
            else:
                break

    async def _list_activities(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List activities."""
        params = {"limit": 100}
        if filters and filters.get("user_id"):
            params["user_id"] = filters["user_id"]
        if filters and filters.get("deal_id"):
            params["deal_id"] = filters["deal_id"]
        if filters and filters.get("person_id"):
            params["person_id"] = filters["person_id"]
        if filters and filters.get("type"):
            params["type"] = filters["type"]
        if filters and filters.get("start_date"):
            params["start_date"] = filters["start_date"]
        if filters and filters.get("end_date"):
            params["end_date"] = filters["end_date"]
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/activities", params=params)
            for activity in data.get("data", []):
                yield {
                    "type": "activity",
                    "id": str(activity["id"]),
                    "data": activity,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                params["start"] = pagination.get("next_start", 0)
            else:
                break

    async def _list_pipelines(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List pipelines."""
        data = await self._make_request("GET", "/pipelines")
        for pipeline in data.get("data", []):
            yield {
                "type": "pipeline",
                "id": str(pipeline["id"]),
                "data": pipeline,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_stages(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List stages."""
        params = {}
        if filters and filters.get("pipeline_id"):
            params["pipeline_id"] = filters["pipeline_id"]

        data = await self._make_request("GET", "/stages", params=params)
        for stage in data.get("data", []):
            yield {
                "type": "stage",
                "id": str(stage["id"]),
                "data": stage,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_users(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List users."""
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/users", params=params)
            for user in data.get("data", []):
                yield {
                    "type": "user",
                    "id": str(user["id"]),
                    "data": user,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                params["start"] = pagination.get("next_start", 0)
            else:
                break

    async def _list_products(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List products."""
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/products", params=params)
            for product in data.get("data", []):
                yield {
                    "type": "product",
                    "id": str(product["id"]),
                    "data": product,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                params["start"] = pagination.get("next_start", 0)
            else:
                break

    async def _list_notes(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List notes."""
        params = {"limit": 100}
        if filters and filters.get("deal_id"):
            params["deal_id"] = filters["deal_id"]
        if filters and filters.get("person_id"):
            params["person_id"] = filters["person_id"]
        if filters and filters.get("org_id"):
            params["org_id"] = filters["org_id"]
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/notes", params=params)
            for note in data.get("data", []):
                yield {
                    "type": "note",
                    "id": str(note["id"]),
                    "data": note,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                params["start"] = pagination.get("next_start", 0)
            else:
                break

    async def _list_files(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List files."""
        params = {"limit": 100}
        if filters and filters.get("deal_id"):
            params["deal_id"] = filters["deal_id"]
        if filters and filters.get("person_id"):
            params["person_id"] = filters["person_id"]
        if filters and filters.get("org_id"):
            params["org_id"] = filters["org_id"]
        if cursor and cursor.cursor:
            params["start"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/files", params=params)
            for file in data.get("data", []):
                yield {
                    "type": "file",
                    "id": str(file["id"]),
                    "data": file,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            pagination = data.get("additional_data", {}).get("pagination", {})
            if pagination.get("more_items_in_collection"):
                params["start"] = pagination.get("next_start", 0)
            else:
                break

    async def _list_webhooks(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List webhooks."""
        data = await self._make_request("GET", "/webhooks")
        for webhook in data.get("data", []):
            yield {
                "type": "webhook",
                "id": str(webhook["id"]),
                "data": webhook,
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

        handlers = {
            "create_deal": self._create_deal,
            "update_deal": self._update_deal,
            "delete_deal": self._delete_deal,
            "create_person": self._create_person,
            "update_person": self._update_person,
            "delete_person": self._delete_person,
            "create_organization": self._create_organization,
            "update_organization": self._update_organization,
            "delete_organization": self._delete_organization,
            "create_activity": self._create_activity,
            "update_activity": self._update_activity,
            "delete_activity": self._delete_activity,
            "create_product": self._create_product,
            "create_note": self._create_note,
            "create_webhook": self._create_webhook,
            "delete_webhook": self._delete_webhook,
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

    async def _create_deal(self, deal_data: Dict[str, Any]):
        """Create a new deal."""
        payload = deal_data.get("deal", {})
        await self._make_request("POST", "/deals", json=payload)

    async def _update_deal(self, deal_data: Dict[str, Any]):
        """Update a deal."""
        deal_id = deal_data.get("deal_id")
        if not deal_id:
            raise ValueError("deal_id required")

        payload = deal_data.get("deal", {})
        await self._make_request("PUT", f"/deals/{deal_id}", json=payload)

    async def _delete_deal(self, deal_data: Dict[str, Any]):
        """Delete a deal."""
        deal_id = deal_data.get("deal_id")
        if not deal_id:
            raise ValueError("deal_id required")

        await self._make_request("DELETE", f"/deals/{deal_id}")

    async def _create_person(self, person_data: Dict[str, Any]):
        """Create a new person."""
        payload = person_data.get("person", {})
        await self._make_request("POST", "/persons", json=payload)

    async def _update_person(self, person_data: Dict[str, Any]):
        """Update a person."""
        person_id = person_data.get("person_id")
        if not person_id:
            raise ValueError("person_id required")

        payload = person_data.get("person", {})
        await self._make_request("PUT", f"/persons/{person_id}", json=payload)

    async def _delete_person(self, person_data: Dict[str, Any]):
        """Delete a person."""
        person_id = person_data.get("person_id")
        if not person_id:
            raise ValueError("person_id required")

        await self._make_request("DELETE", f"/persons/{person_id}")

    async def _create_organization(self, org_data: Dict[str, Any]):
        """Create a new organization."""
        payload = org_data.get("organization", {})
        await self._make_request("POST", "/organizations", json=payload)

    async def _update_organization(self, org_data: Dict[str, Any]):
        """Update an organization."""
        org_id = org_data.get("organization_id")
        if not org_id:
            raise ValueError("organization_id required")

        payload = org_data.get("organization", {})
        await self._make_request("PUT", f"/organizations/{org_id}", json=payload)

    async def _delete_organization(self, org_data: Dict[str, Any]):
        """Delete an organization."""
        org_id = org_data.get("organization_id")
        if not org_id:
            raise ValueError("organization_id required")

        await self._make_request("DELETE", f"/organizations/{org_id}")

    async def _create_activity(self, activity_data: Dict[str, Any]):
        """Create a new activity."""
        payload = activity_data.get("activity", {})
        await self._make_request("POST", "/activities", json=payload)

    async def _update_activity(self, activity_data: Dict[str, Any]):
        """Update an activity."""
        activity_id = activity_data.get("activity_id")
        if not activity_id:
            raise ValueError("activity_id required")

        payload = activity_data.get("activity", {})
        await self._make_request("PUT", f"/activities/{activity_id}", json=payload)

    async def _delete_activity(self, activity_data: Dict[str, Any]):
        """Delete an activity."""
        activity_id = activity_data.get("activity_id")
        if not activity_id:
            raise ValueError("activity_id required")

        await self._make_request("DELETE", f"/activities/{activity_id}")

    async def _create_product(self, product_data: Dict[str, Any]):
        """Create a new product."""
        payload = product_data.get("product", {})
        await self._make_request("POST", "/products", json=payload)

    async def _create_note(self, note_data: Dict[str, Any]):
        """Create a new note."""
        payload = {
            "content": note_data.get("content"),
            "deal_id": note_data.get("deal_id"),
            "person_id": note_data.get("person_id"),
            "org_id": note_data.get("org_id"),
        }
        await self._make_request("POST", "/notes", json=payload)

    async def _create_webhook(self, webhook_data: Dict[str, Any]):
        """Create a new webhook."""
        payload = {
            "subscription_url": webhook_data.get("subscription_url"),
            "event_action": webhook_data.get("event_action"),
            "event_object": webhook_data.get("event_object"),
        }
        await self._make_request("POST", "/webhooks", json=payload)

    async def _delete_webhook(self, webhook_data: Dict[str, Any]):
        """Delete a webhook."""
        webhook_id = webhook_data.get("webhook_id")
        if not webhook_id:
            raise ValueError("webhook_id required")

        await self._make_request("DELETE", f"/webhooks/{webhook_id}")

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/users", params={"limit": 1})
            return "data" in data
        except Exception as e:
            logger.error(f"Pipedrive connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(PipedriveConnector, PipedriveConnector.CONFIG)