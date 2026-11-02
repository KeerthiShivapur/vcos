"""Gate 24 — HubSpot Connector.

Implements HubSpot integration for contacts, companies, deals, and tickets.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, AsyncIterator

from app.intelligence.connectors.base import BaseConnector, connector_registry
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.connectors.hubspot")


class HubSpotConnector(BaseConnector):
    """HubSpot connector implementation."""

    @property
    def provider(self) -> str:
        return "hubspot"

    @property
    def kind(self) -> str:
        return "crm"

    async def authenticate(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials

        if not credentials:
            return False, "No credentials configured"

        access_token = credentials.get("access_token")
        if not access_token:
            return False, "No access token configured"

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    "https://api.hubapi.com/oauth/v1/access-tokens/" + access_token,
                    headers={"Authorization": f"Bearer {access_token}"},
                )

            if response.status_code == 200:
                return True, None
            return False, f"Authentication failed: {response.text}"
        except Exception as e:
            return False, f"Authentication test failed: {str(e)}"

    async def test_connection(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str]]:
        return await self.authenticate(instance)

    async def full_sync(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
        until: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        ok, error = await self.authenticate(instance)
        if not ok:
            raise RuntimeError(f"Authentication failed: {error}")

        credentials = instance.credentials
        access_token = credentials.get("access_token")

        # Sync contacts
        if "read_contacts" in instance.connector.inbound_capabilities:
            async for contact in self._sync_contacts(access_token, since, until):
                yield contact

        # Sync companies
        if "read_companies" in instance.connector.inbound_capabilities:
            async for company in self._sync_companies(access_token, since, until):
                yield company

        # Sync deals
        if "read_deals" in instance.connector.inbound_capabilities:
            async for deal in self._sync_deals(access_token, since, until):
                yield deal

        # Sync tickets
        if "read_tickets" in instance.connector.inbound_capabilities:
            async for ticket in self._sync_tickets(access_token, since, until):
                yield ticket

        # Sync owners (users)
        if "read_owners" in instance.connector.inbound_capabilities:
            async for owner in self._sync_owners(access_token):
                yield owner

    async def _sync_contacts(self, access_token: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        properties = "email,firstname,lastname,phone,company,jobtitle,createdate,lastmodifieddate,lifecyclestage,owner_id,associatedcompanyid"
        url = "https://api.hubapi.com/crm/v3/objects/contacts"
        params = {"properties": properties, "limit": 100, "archived": "false"}
        
        if since:
            params["createdAfter"] = int(since.timestamp() * 1000)

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    params=params,
                )

                if response.status_code != 200:
                    break

                data = response.json()
                for contact in data.get("results", []):
                    props = contact.get("properties", {})
                    yield {
                        "entity_type": "contact",
                        "external_id": contact["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": contact["id"],
                            "external_email": props.get("email"),
                            "external_display_name": f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                            "external_metadata": {
                                "first_name": props.get("firstname"),
                                "last_name": props.get("lastname"),
                                "phone": props.get("phone"),
                                "company": props.get("company"),
                                "job_title": props.get("jobtitle"),
                                "lifecycle_stage": props.get("lifecyclestage"),
                                "owner_id": props.get("owner_id"),
                                "associated_company_id": props.get("associatedcompanyid"),
                                "created_date": props.get("createdate"),
                                "last_modified": props.get("lastmodifieddate"),
                            },
                        },
                    }

                paging = data.get("paging", {})
                if not paging.get("next"):
                    break
                params["after"] = paging["next"].get("after")

    async def _sync_companies(self, access_token: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        properties = "name,domain,phone,website,industry,numberofemployees,createdate,lastmodifieddate,lifecyclestage,owner_id"
        url = "https://api.hubapi.com/crm/v3/objects/companies"
        params = {"properties": properties, "limit": 100, "archived": "false"}
        
        if since:
            params["createdAfter"] = int(since.timestamp() * 1000)

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                response = await client.get(
                    "https://api.hubapi.com/crm/v3/objects/companies",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    params=params,
                )

                if response.status_code != 200:
                    break

                data = response.json()
                for company in data.get("results", []):
                    props = company.get("properties", {})
                    yield {
                        "entity_type": "account",
                        "external_id": company["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": company["id"],
                            "external_display_name": props.get("name"),
                            "external_metadata": {
                                "domain": props.get("domain"),
                                "phone": props.get("phone"),
                                "website": props.get("website"),
                                "industry": props.get("industry"),
                                "number_of_employees": props.get("numberofemployees"),
                                "lifecycle_stage": props.get("lifecyclestage"),
                                "owner_id": props.get("owner_id"),
                                "created_date": props.get("createdate"),
                                "last_modified": props.get("lastmodifieddate"),
                            },
                        },
                    }

                paging = data.get("paging", {})
                if not paging.get("next"):
                    break
                params["after"] = paging["next"].get("after")

    async def _sync_deals(self, access_token: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        properties = "dealname,amount,dealstage,pipeline,closedate,dealtype,amount_in_home_currency,createdate,lastmodifieddate,owner_id,associatedcompanyids,associatedcontactids"
        url = "https://api.hubapi.com/crm/v3/objects/deals"
        params = {"properties": properties, "limit": 100, "archived": "false"}
        
        if since:
            params["createdAfter"] = int(since.timestamp() * 1000)

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    params=params,
                )

                if response.status_code != 200:
                    break

                data = response.json()
                for deal in data.get("results", []):
                    props = deal.get("properties", {})
                    yield {
                        "entity_type": "opportunity",
                        "external_id": deal["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": deal["id"],
                            "external_display_name": props.get("dealname"),
                            "external_metadata": {
                                "amount": props.get("amount"),
                                "stage": props.get("dealstage"),
                                "pipeline": props.get("pipeline"),
                                "close_date": props.get("closedate"),
                                "type": props.get("dealtype"),
                                "owner_id": props.get("owner_id"),
                                "associated_company_ids": props.get("associatedcompanyids", "").split(";") if props.get("associatedcompanyids") else [],
                                "associated_contact_ids": props.get("associatedcontactids", "").split(";") if props.get("associatedcontactids") else [],
                                "created_date": props.get("createdate"),
                                "last_modified": props.get("lastmodifieddate"),
                            },
                        },
                    }

                paging = data.get("paging", {})
                if not paging.get("next"):
                    break
                params["after"] = paging["next"].get("after")

    async def _sync_tickets(self, access_token: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        properties = "subject,content,hs_pipeline,hs_pipeline_stage,hs_ticket_category,hs_ticket_priority,createdate,lastmodifieddate,owner_id,hs_ticket_id"
        url = "https://api.hubapi.com/crm/v3/objects/tickets"
        params = {"properties": properties, "limit": 100, "archived": "false"}
        
        if since:
            params["createdAfter"] = int(since.timestamp() * 1000)

        async with httpx.AsyncClient(timeout=30.0) as client:
            while True:
                response = await client.get(
                    url,
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    params=params,
                )

                if response.status_code != 200:
                    break

                data = response.json()
                for ticket in data.get("results", []):
                    props = ticket.get("properties", {})
                    yield {
                        "entity_type": "ticket",
                        "external_id": ticket["id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": ticket["id"],
                            "external_display_name": props.get("subject"),
                            "external_metadata": {
                                "content": props.get("content"),
                                "pipeline": props.get("hs_pipeline"),
                                "stage": props.get("hs_pipeline_stage"),
                                "category": props.get("hs_ticket_category"),
                                "priority": props.get("hs_ticket_priority"),
                                "owner_id": props.get("owner_id"),
                                "ticket_id": props.get("hs_ticket_id"),
                                "created_date": props.get("createdate"),
                                "last_modified": props.get("lastmodifieddate"),
                            },
                        },
                    }

                paging = data.get("paging", {})
                if not paging.get("next"):
                    break
                params["after"] = paging["next"].get("after")

    async def _sync_owners(self, access_token: str) -> AsyncIterator[dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.hubapi.com/crm/v3/owners",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for owner in data.get("results", []):
                yield {
                    "entity_type": "person",
                    "external_id": str(owner["id"]),
                    "operation": "upsert",
                    "data": {
                        "external_id": str(owner["id"]),
                        "external_email": owner.get("email"),
                        "external_display_name": f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip(),
                        "external_metadata": {
                            "user_id": owner.get("userId"),
                            "type": owner.get("type"),
                            "team_ids": owner.get("teamIds", []),
                        },
                    },
                }

    async def incremental_sync(
        self,
        instance: ConnectorInstance,
        cursor: Optional[str] = None,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        async for entity in self.full_sync(instance, since=since):
            yield entity

    async def poll_events(
        self,
        instance: ConnectorInstance,
        since: Optional[datetime] = None,
    ) -> AsyncIterator[dict[str, Any]]:
        return
        yield

    async def execute_operation(
        self,
        instance: ConnectorInstance,
        operation_type: str,
        target_entity_type: str,
        target_external_id: Optional[str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return {"success": False, "error": error}

        credentials = instance.credentials
        access_token = credentials.get("access_token")

        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

            if operation_type == "create" and target_entity_type in ["contact", "company", "deal", "ticket"]:
                object_type = target_entity_type
                url = f"https://api.hubapi.com/crm/v3/objects/{object_type}"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        json={"properties": payload},
                    )

                    if response.status_code in (200, 201):
                        data = response.json()
                        return {
                            "success": True,
                            "external_operation_id": data.get("id"),
                            "data": data,
                        }

                    return {"success": False, "error": response.text}

            elif operation_type == "update" and target_entity_type in ["contact", "company", "deal", "ticket"]:
                object_type = target_entity_type
                url = f"https://api.hubapi.com/crm/v3/objects/{object_type}/{target_external_id}"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.patch(
                        url,
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        json={"properties": payload},
                    )

                    if response.status_code == 200:
                        return {"success": True, "data": response.json()}

                    return {"success": False, "error": response.text}

        return {"success": False, "error": f"Operation {operation_type} not implemented"}

    async def get_webhook_events(
        self,
        instance: ConnectorInstance,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        events = []

        # HubSpot webhook events
        for event in payload.get("events", []):
            event_type = event.get("eventType", "")
            object_type = event.get("objectType", "")
            object_id = event.get("objectId", "")

            events.append({
                "external_event_id": event.get("eventId", ""),
                "event_type": f"hubspot.{object_type}.{event_type}",
                "source_id": object_id,
                "source_type": object_type.lower(),
                "payload": event,
                "external_timestamp": datetime.now(timezone.utc),
            })

        return events

    async def refresh_credentials(
        self, instance: ConnectorInstance
    ) -> tuple[bool, Optional[str], Optional[dict]]:
        credentials = instance.credentials
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")

        if not refresh_token or not client_id or not client_secret:
            return False, "Missing refresh token or client credentials", None

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.hubapi.com/oauth/v1/token",
                    data={
                        "grant_type": "refresh_token",
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                    },
                )

                if response.status_code == 200:
                    data = response.json()
                    new_credentials = credentials.copy()
                    new_credentials["access_token"] = data["access_token"]
                    new_credentials["expires_in"] = data.get("expires_in")
                    if "refresh_token" in data:
                        new_credentials["refresh_token"] = data["refresh_token"]
                    return True, None, new_credentials

        except Exception as e:
            return False, f"Token refresh failed: {str(e)}", None

        return False, "Token refresh failed", None

    async def get_rate_limit_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        return {"remaining": "unknown", "reset_at": None}

    async def resolve_identity(
        self,
        instance: ConnectorInstance,
        external_id: str,
    ) -> Optional[dict[str, Any]]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return None

        credentials = instance.credentials
        access_token = credentials.get("access_token")

        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"https://api.hubapi.com/crm/v3/objects/contacts/{external_id}",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                params={"properties": "email,firstname,lastname,phone,company,jobtitle,createdate,lastmodifieddate"},
            )

            if response.status_code == 200:
                data = response.json()
                props = data.get("properties", {})
                return {
                    "external_id": data.get("id"),
                    "external_email": props.get("email"),
                    "external_display_name": f"{props.get('firstname', '')} {props.get('lastname', '')}".strip(),
                    "external_metadata": {
                        "first_name": props.get("firstname"),
                        "last_name": props.get("lastname"),
                        "phone": props.get("phone"),
                        "company": props.get("company"),
                        "job_title": props.get("jobtitle"),
                        "created_date": props.get("createdate"),
                        "last_modified": props.get("lastmodifieddate"),
                    },
                }

        return None

    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return {
            "inbound_capabilities": ["read_contacts", "read_companies", "read_deals", "read_tickets", "read_owners", "read_engagements", "read_products"],
            "outbound_capabilities": ["create_contact", "create_company", "create_deal", "create_ticket", "update_contact", "update_company", "update_deal", "update_ticket", "create_engagement"],
            "supported_entities": ["contact", "company", "deal", "ticket", "owner", "engagement", "product", "line_item", "quote"],
            "supported_events": ["contact.creation", "contact.propertyChange", "contact.deletion", "company.creation", "company.propertyChange", "company.deletion", "deal.creation", "deal.propertyChange", "deal.deletion", "ticket.creation", "ticket.propertyChange", "ticket.deletion"],
            "sync_modes": ["full", "incremental", "webhook"],
            "auth_types": ["oauth2", "private_app"],
            "oauth_scopes": [
                "contacts",
                "companies",
                "deals",
                "tickets",
                "automation",
                "content",
                "oauth",
                "reports",
            ],
            "required_config_fields": ["client_id", "client_secret", "refresh_token"],
            "optional_config_fields": ["access_token"],
            "rate_limits": {
                "api": {"requests_per_second": 100, "burst": 20},
                "daily": {"limit": 4000000},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("access_token") and not credentials.get("refresh_token"):
            return False, "No access_token or refresh_token configured"
        return True, None

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        ok, error = await self.authenticate(instance)
        if not ok:
            return {
                "status": "unhealthy",
                "last_check": datetime.now(timezone.utc).isoformat(),
                "details": {"error": error},
                "latency_ms": 0,
            }
        return {
            "status": "healthy",
            "last_check": datetime.now(timezone.utc).isoformat(),
            "details": {"authenticated": True},
            "latency_ms": 0,
        }

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        import hmac
        import hashlib
        credentials = instance.credentials
        client_secret = credentials.get("client_secret")
        if not client_secret:
            return False
        expected = hmac.new(client_secret.encode(), payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(signature, expected)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        return await self.validate_webhook_signature(instance, payload, signature, timestamp)

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def get_health_status(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.get_health_status(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        return await self.validate_config(instance)

    async def validate_webhook_signature(
        self,
        instance: ConnectorInstance,
        payload: bytes,
        signature: str,
        timestamp: Optional[str] = None,
    ) -> bool:
        return await self.validate_webhook_signature(instance, payload, signature, timestamp)


# Register the connector
connector_registry.register(HubSpotConnector())