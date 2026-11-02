"""
HubSpot Connector for VCOS.

Provides integration with HubSpot for CRM data including contacts, companies,
deals, tickets, and marketing automation.
"""

import logging
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional
from urllib.parse import urljoin

from app.connectors.base import (
    BaseConnector,
    ConnectorConfig,
    AuthType,
    RateLimitConfig,
    SyncCursor,
    SyncResult,
)

logger = logging.getLogger(__name__)


class HubSpotConnector(BaseConnector):
    """HubSpot CRM Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="hubspot",
        display_name="HubSpot",
        description="Inbound marketing, sales, and service platform",
        category="crm",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "access_token": {"type": "string", "description": "Private app access token or OAuth access token"},
                "refresh_token": {"type": "string"},
            },
            "required": [],
            "oneOf": [
                {"required": ["access_token"]},
                {"required": ["client_id", "client_secret", "redirect_uri"]},
            ],
        },
        required_scopes=[
            "crm.objects.contacts.read",
            "crm.objects.contacts.write",
            "crm.objects.companies.read",
            "crm.objects.companies.write",
            "crm.objects.deals.read",
            "crm.objects.deals.write",
            "crm.objects.tickets.read",
            "crm.objects.tickets.write",
            "crm.objects.line_items.read",
            "crm.objects.line_items.write",
            "crm.objects.products.read",
            "crm.objects.products.write",
            "crm.objects.quotes.read",
            "crm.objects.quotes.write",
            "crm.schemas.contacts.read",
            "crm.schemas.companies.read",
            "crm.schemas.deals.read",
        ],
        supported_operations=[
            "list_contacts",
            "get_contact",
            "create_contact",
            "update_contact",
            "delete_contact",
            "list_companies",
            "get_company",
            "create_company",
            "update_company",
            "delete_company",
            "list_deals",
            "get_deal",
            "create_deal",
            "update_deal",
            "delete_deal",
            "list_tickets",
            "get_ticket",
            "create_ticket",
            "update_ticket",
            "list_line_items",
            "get_line_item",
            "list_products",
            "get_product",
            "create_product",
            "list_quotes",
            "get_quote",
            "list_engagements",
            "list_pipelines",
            "list_owners",
        ],
        webhook_events=[
            "contact.creation",
            "contact.propertyChange",
            "contact.deletion",
            "company.creation",
            "company.propertyChange",
            "company.deletion",
            "deal.creation",
            "deal.propertyChange",
            "deal.deletion",
            "ticket.creation",
            "ticket.propertyChange",
            "ticket.deletion",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=100,
            burst=20,
        ),
    )

    BASE_URL = "https://api.hubapi.com"
    TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.client_id = connection_config.get("client_id")
        self.client_secret = connection_config.get("client_secret")
        self.access_token = connection_config.get("access_token")
        self.refresh_token = connection_config.get("refresh_token")
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with HubSpot using OAuth2 or private app token."""
        if self.access_token:
            self._authenticated = True
            logger.info("HubSpot authenticated with access token")
            return True

        if self.refresh_token and self.client_id and self.client_secret:
            from app.connectors.base import TokenManager
            self._token_manager = TokenManager(
                self.client_id,
                self.client_secret,
                self.TOKEN_URL,
            )
            # TokenManager would need modification for refresh token flow
            self._authenticated = True
            logger.info("HubSpot authenticated with refresh token")
            return True

        raise ValueError("HubSpot requires access_token or refresh_token + client credentials")

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

    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        handlers = {
            "list_contacts": self._list_contacts,
            "list_companies": self._list_companies,
            "list_deals": self._list_deals,
            "list_tickets": self._list_tickets,
            "list_line_items": self._list_line_items,
            "list_products": self._list_products,
            "list_quotes": self._list_quotes,
            "list_engagements": self._list_engagements,
            "list_pipelines": self._list_pipelines,
            "list_owners": self._list_owners,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _paginated_get(
        self,
        endpoint: str,
        params: Dict[str, Any] = None,
        properties: List[str] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Handle HubSpot pagination."""
        url = urljoin(self.BASE_URL, endpoint)
        params = params or {}
        params.setdefault("limit", 100)

        if properties:
            params["properties"] = ",".join(properties)

        while True:
            headers = await self._get_headers()
            async with self.session.get(url, headers=headers, params=params) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for item in data.get("results", []):
                    yield item

                paging = data.get("paging", {})
                if "next" in paging and "after" in paging["next"]:
                    params["after"] = paging["next"]["after"]
                else:
                    break

    async def _list_contacts(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        properties = [
            "email", "firstname", "lastname", "phone", "company", "jobtitle",
            "lifecyclestage", "createdate", "lastmodifieddate", "hs_lead_status",
            "hs_analytics_source", "hubspot_owner_id", "num_associated_deals",
            "num_contacted_notes", "recent_deal_amount", "recent_deal_close_date",
        ]
        if filters and filters.get("properties"):
            properties = filters["properties"]

        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["after"] = cursor.cursor
        if filters and filters.get("since"):
            params["createdAfter"] = int(filters["since"].timestamp() * 1000) if isinstance(filters["since"], datetime) else filters["since"]

        async for contact in self._paginated_get("/crm/v3/objects/contacts", params, properties):
            yield {
                "type": "contact",
                "id": contact["id"],
                "data": contact,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_companies(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        properties = [
            "name", "domain", "city", "state", "country", "phone", "website",
            "industry", "numberofemployees", "annualrevenue", "lifecyclestage",
            "createdate", "hs_lastmodifieddate", "hubspot_owner_id",
        ]
        if filters and filters.get("properties"):
            properties = filters["properties"]

        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["after"] = cursor.cursor

        async for company in self._paginated_get("/crm/v3/objects/companies", params, properties):
            yield {
                "type": "company",
                "id": company["id"],
                "data": company,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_deals(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        properties = [
            "dealname", "amount", "dealstage", "pipeline", "closedate",
            "dealtype", "description", "hubspot_owner_id", "createdate",
            "closedate", "hs_lastmodifieddate", "num_associated_contacts",
            "num_contacted_notes",
        ]
        if filters and filters.get("properties"):
            properties = filters["properties"]

        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["after"] = cursor.cursor
        if filters and filters.get("pipeline"):
            params["pipeline"] = filters["pipeline"]

        async for deal in self._paginated_get("/crm/v3/objects/deals", params, properties):
            yield {
                "type": "deal",
                "id": deal["id"],
                "data": deal,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_tickets(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        properties = [
            "subject", "content", "hs_pipeline", "hs_pipeline_stage",
            "hs_ticket_priority", "hs_ticket_category", "hubspot_owner_id",
            "createdate", "hs_lastmodifieddate", "closed_date",
        ]
        if filters and filters.get("properties"):
            properties = filters["properties"]

        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["after"] = cursor.cursor
        if filters and filters.get("pipeline"):
            params["hs_pipeline"] = filters["pipeline"]

        async for ticket in self._paginated_get("/crm/v3/objects/tickets", params, properties):
            yield {
                "type": "ticket",
                "id": ticket["id"],
                "data": ticket,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_line_items(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        properties = ["name", "quantity", "price", "hs_product_id", "hs_deal_id"]
        async for item in self._paginated_get("/crm/v3/objects/line_items", {"limit": 100}, properties):
            yield {
                "type": "line_item",
                "id": item["id"],
                "data": item,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_products(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        properties = ["name", "description", "price", "unit", "recurringbillingfrequency", "hs_folder_id"]
        if filters and filters.get("properties"):
            properties = filters["properties"]

        async for product in self._paginated_get("/crm/v3/objects/products", {"limit": 100}, properties):
            yield {
                "type": "product",
                "id": product["id"],
                "data": product,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_quotes(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        properties = ["hs_title", "hs_expiration_date", "hs_proposal_slug", "hs_status", "hs_template_type"]
        async for quote in self._paginated_get("/crm/v3/objects/quotes", {"limit": 100}, properties):
            yield {
                "type": "quote",
                "id": quote["id"],
                "data": quote,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_engagements(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["after"] = cursor.cursor
        if filters and filters.get("contact_id"):
            params["contactId"] = filters["contact_id"]
        if filters and filters.get("company_id"):
            params["companyId"] = filters["company_id"]
        if filters and filters.get("deal_id"):
            params["dealId"] = filters["deal_id"]

        async for engagement in self._paginated_get("/engagements/v1/engagements/paged", params):
            yield {
                "type": "engagement",
                "id": str(engagement["engagement"]["id"]),
                "data": engagement,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_pipelines(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        object_type = filters.get("object_type", "deals")
        url = f"/crm/v3/pipelines/{object_type}"
        headers = await self._get_headers()
        
        async with self.session.get(urljoin(self.BASE_URL, url), headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()

            for pipeline in data.get("results", []):
                yield {
                    "type": "pipeline",
                    "id": pipeline["id"],
                    "data": pipeline,
                    "synced_at": datetime.utcnow().isoformat(),
                }

    async def _list_owners(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        url = "/crm/v3/owners"
        headers = await self._get_headers()

        async with self.session.get(urljoin(self.BASE_URL, url), headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()

            for owner in data.get("results", []):
                yield {
                    "type": "owner",
                    "id": owner["id"],
                    "data": owner,
                    "synced_at": datetime.utcnow().isoformat(),
                }

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

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_contact": lambda d: self._create_object("contacts", d),
            "update_contact": lambda d: self._update_object("contacts", d),
            "delete_contact": lambda d: self._delete_object("contacts", d),
            "create_company": lambda d: self._create_object("companies", d),
            "update_company": lambda d: self._update_object("companies", d),
            "delete_company": lambda d: self._delete_object("companies", d),
            "create_deal": lambda d: self._create_object("deals", d),
            "update_deal": lambda d: self._update_object("deals", d),
            "delete_deal": lambda d: self._delete_object("deals", d),
            "create_ticket": lambda d: self._create_object("tickets", d),
            "update_ticket": lambda d: self._update_object("tickets", d),
            "create_product": lambda d: self._create_object("products", d),
        }

        handler = handlers.get(operation)
        if not handler:
            result.success = False
            result.errors.append({"error": f"Unsupported push operation: {operation}"})
            return result

        for item in data:
            try:
                await handler(item)
                if "create" in operation:
                    result.records_created += 1
                else:
                    result.records_updated += 1
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_object(self, object_type: str, data: Dict[str, Any]):
        properties = {k: v for k, v in data.items() if k != "id"}
        payload = {"properties": properties}
        headers = await self._get_headers()
        
        async with self.session.post(
            urljoin(self.BASE_URL, f"/crm/v3/objects/{object_type}"),
            headers=headers,
            json=payload,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_object(self, object_type: str, data: Dict[str, Any]):
        object_id = data.get("id")
        properties = {k: v for k, v in data.items() if k != "id"}
        payload = {"properties": properties}
        headers = await self._get_headers()

        async with self.session.patch(
            urljoin(self.BASE_URL, f"/crm/v3/objects/{object_type}/{object_id}"),
            headers=headers,
            json=payload,
        ) as resp:
            resp.raise_for_status()

    async def _delete_object(self, object_type: str, data: Dict[str, Any]):
        object_id = data.get("id")
        headers = await self._get_headers()

        async with self.session.delete(
            urljoin(self.BASE_URL, f"/crm/v3/objects/{object_type}/{object_id}"),
            headers=headers,
        ) as resp:
            resp.raise_for_status()

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

    async def test_connection(self) -> bool:
        try:
            async with self.session.get(
                f"{self.BASE_URL}/crm/v3/objects/contacts?limit=1",
                headers=await self._get_headers(),
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"HubSpot connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(HubSpotConnector, HubSpotConnector.CONFIG)