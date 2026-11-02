"""Gate 24 — Salesforce Connector.

Implements Salesforce integration for accounts, contacts, opportunities, and leads.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, AsyncIterator

from app.intelligence.connectors.base import BaseConnector, connector_registry
from app.models.canonical_integration import ConnectorInstance

logger = logging.getLogger("vcos.connectors.salesforce")


class SalesforceConnector(BaseConnector):
    """Salesforce connector implementation."""

    @property
    def provider(self) -> str:
        return "salesforce"

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
        instance_url = credentials.get("instance_url")

        if not access_token or not instance_url:
            return False, "No access token or instance URL configured"

        try:
            import httpx
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{instance_url}/services/data/v58.0/limits",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
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
        instance_url = credentials.get("instance_url")

        # Sync users
        if "read_users" in instance.connector.inbound_capabilities:
            async for user in self._sync_users(access_token, instance_url):
                yield user

        # Sync accounts
        if "read_accounts" in instance.connector.inbound_capabilities:
            async for account in self._sync_accounts(access_token, instance_url, since, until):
                yield account

        # Sync contacts
        if "read_contacts" in instance.connector.inbound_capabilities:
            async for contact in self._sync_contacts(access_token, instance_url, since, until):
                yield contact

        # Sync opportunities
        if "read_opportunities" in instance.connector.inbound_capabilities:
            async for opportunity in self._sync_opportunities(access_token, instance_url, since, until):
                yield opportunity

        # Sync leads
        if "read_leads" in instance.connector.inbound_capabilities:
            async for lead in self._sync_leads(access_token, instance_url, since, until):
                yield lead

    async def _sync_users(self, access_token: str, instance_url: str) -> AsyncIterator[dict[str, Any]]:
        import httpx

        async with httpx.AsyncClient(timeout=30.0) as client:
            query = "SELECT Id, Username, Email, FirstName, LastName, Name, Title, Phone, MobilePhone, IsActive, CreatedDate, LastLoginDate, Profile.Name, UserRole.Name FROM User WHERE IsActive = true LIMIT 1000"
            url = f"{instance_url}/services/data/v58.0/query/?q={query}"
            
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{instance_url}/services/data/v58.0/query/",
                    headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                    params={"q": query},
                )

                if response.status_code != 200:
                    return

                data = response.json()
                for user in data.get("records", []):
                    yield {
                        "entity_type": "person",
                        "external_id": user["Id"],
                        "operation": "upsert",
                        "data": {
                            "external_id": user["Id"],
                            "external_email": user.get("Email"),
                            "external_display_name": user.get("Name"),
                            "external_metadata": {
                                "username": user.get("Username"),
                                "first_name": user.get("FirstName"),
                                "last_name": user.get("LastName"),
                                "title": user.get("Title"),
                                "phone": user.get("Phone"),
                                "mobile_phone": user.get("MobilePhone"),
                                "is_active": user.get("IsActive"),
                                "profile_name": user.get("Profile", {}).get("Name"),
                                "role_name": user.get("UserRole", {}).get("Name"),
                                "created_date": user.get("CreatedDate"),
                                "last_login": user.get("LastLoginDate"),
                            },
                        },
                    }

    async def _sync_accounts(self, access_token: str, instance_url: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = "SELECT Id, Name, Type, Industry, AnnualRevenue, NumberOfEmployees, BillingStreet, BillingCity, BillingState, BillingPostalCode, BillingCountry, Phone, Fax, Website, OwnerId, CreatedDate, LastModifiedDate FROM Account"
        if since:
            query += f" WHERE LastModifiedDate >= {since.isoformat()}Z"
        query += " LIMIT 1000"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{instance_url}/services/data/v58.0/query/",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                params={"q": query},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for account in data.get("records", []):
                yield {
                    "entity_type": "account",
                    "external_id": account["Id"],
                    "operation": "upsert",
                    "data": {
                        "external_id": account["Id"],
                        "external_display_name": account.get("Name"),
                        "external_metadata": {
                            "type": account.get("Type"),
                            "industry": account.get("Industry"),
                            "annual_revenue": account.get("AnnualRevenue"),
                            "number_of_employees": account.get("NumberOfEmployees"),
                            "billing_address": {
                                "street": account.get("BillingStreet"),
                                "city": account.get("BillingCity"),
                                "state": account.get("BillingState"),
                                "postal_code": account.get("BillingPostalCode"),
                                "country": account.get("BillingCountry"),
                            },
                            "phone": account.get("Phone"),
                            "fax": account.get("Fax"),
                            "website": account.get("Website"),
                            "owner_id": account.get("OwnerId"),
                            "created_date": account.get("CreatedDate"),
                            "last_modified": account.get("LastModifiedDate"),
                        },
                    },
                }

    async def _sync_contacts(self, access_token: str, instance_url: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = "SELECT Id, FirstName, LastName, Email, Phone, MobilePhone, Title, Department, AccountId, OwnerId, CreatedDate, LastModifiedDate FROM Contact LIMIT 1000"
        if since:
            query = "SELECT Id, FirstName, LastName, Email, Phone, MobilePhone, Title, Department, AccountId, OwnerId, CreatedDate, LastModifiedDate FROM Contact WHERE LastModifiedDate >= " + since.isoformat() + "Z LIMIT 1000"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{instance_url}/services/data/v58.0/query/",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                params={"q": query},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for contact in data.get("records", []):
                yield {
                    "entity_type": "contact",
                    "external_id": contact["Id"],
                    "operation": "upsert",
                    "data": {
                        "external_id": contact["Id"],
                        "external_display_name": f"{contact.get('FirstName', '')} {contact.get('LastName', '')}".strip(),
                        "external_email": contact.get("Email"),
                        "external_metadata": {
                            "first_name": contact.get("FirstName"),
                            "last_name": contact.get("LastName"),
                            "phone": contact.get("Phone"),
                            "mobile_phone": contact.get("MobilePhone"),
                            "title": contact.get("Title"),
                            "department": contact.get("Department"),
                            "account_id": contact.get("AccountId"),
                            "owner_id": contact.get("OwnerId"),
                            "created_date": contact.get("CreatedDate"),
                            "last_modified": contact.get("LastModifiedDate"),
                        },
                    },
                }

    async def _sync_opportunities(self, access_token: str, instance_url: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = "SELECT Id, Name, Amount, StageName, CloseDate, Type, LeadSource, AccountId, OwnerId, Probability, ExpectedRevenue, CreatedDate, LastModifiedDate FROM Opportunity LIMIT 1000"
        if since:
            query = "SELECT Id, Name, Amount, StageName, CloseDate, Type, LeadSource, AccountId, OwnerId, Probability, ExpectedRevenue, CreatedDate, LastModifiedDate FROM Opportunity WHERE LastModifiedDate >= " + since.isoformat() + "Z LIMIT 1000"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{instance_url}/services/data/v58.0/query/",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                params={"q": query},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for opp in data.get("records", []):
                yield {
                    "entity_type": "opportunity",
                    "external_id": opp["Id"],
                    "operation": "upsert",
                    "data": {
                        "external_id": opp["Id"],
                        "external_display_name": opp.get("Name"),
                        "external_metadata": {
                            "amount": opp.get("Amount"),
                            "stage_name": opp.get("StageName"),
                            "close_date": opp.get("CloseDate"),
                            "type": opp.get("Type"),
                            "lead_source": opp.get("LeadSource"),
                            "account_id": opp.get("AccountId"),
                            "owner_id": opp.get("OwnerId"),
                            "probability": opp.get("Probability"),
                            "expected_revenue": opp.get("ExpectedRevenue"),
                            "created_date": opp.get("CreatedDate"),
                            "last_modified": opp.get("LastModifiedDate"),
                        },
                    },
                }

    async def _sync_leads(self, access_token: str, instance_url: str, since: Optional[datetime], until: Optional[datetime]) -> AsyncIterator[dict[str, Any]]:
        import httpx

        query = "SELECT Id, FirstName, LastName, Email, Phone, Company, Title, Status, LeadSource, OwnerId, CreatedDate, LastModifiedDate FROM Lead LIMIT 1000"
        if since:
            query = "SELECT Id, FirstName, LastName, Email, Phone, Company, Title, Status, LeadSource, OwnerId, CreatedDate, LastModifiedDate FROM Lead WHERE LastModifiedDate >= " + since.isoformat() + "Z LIMIT 1000"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                f"{instance_url}/services/data/v58.0/query/",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                params={"q": query},
            )

            if response.status_code != 200:
                return

            data = response.json()
            for lead in data.get("records", []):
                yield {
                    "entity_type": "lead",
                    "external_id": lead["Id"],
                    "operation": "upsert",
                    "data": {
                        "external_id": lead["Id"],
                        "external_display_name": f"{lead.get('FirstName', '')} {lead.get('LastName', '')}".strip(),
                        "external_email": lead.get("Email"),
                        "external_metadata": {
                            "first_name": lead.get("FirstName"),
                            "last_name": lead.get("LastName"),
                            "company": lead.get("Company"),
                            "title": lead.get("Title"),
                            "phone": lead.get("Phone"),
                            "status": lead.get("Status"),
                            "lead_source": lead.get("LeadSource"),
                            "owner_id": lead.get("OwnerId"),
                            "created_date": lead.get("CreatedDate"),
                            "last_modified": lead.get("LastModifiedDate"),
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
        instance_url = credentials.get("instance_url")

        import httpx
        async with httpx.AsyncClient(timeout=30.0) as client:
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

            if operation_type == "create" and target_entity_type in ["account", "contact", "opportunity", "lead"]:
                object_type = target_entity_type.capitalize()
                url = f"{instance_url}/services/data/v58.0/sobjects/{object_type}/"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        json=payload,
                    )

                    if response.status_code in (200, 201):
                        data = response.json()
                        return {
                            "success": True,
                            "external_operation_id": data.get("id"),
                            "data": data,
                        }

                    return {"success": False, "error": response.text}

            elif operation_type == "update" and target_entity_type in ["account", "contact", "opportunity", "lead"]:
                object_type = target_entity_type.capitalize()
                url = f"{instance_url}/services/data/v58.0/sobjects/{object_type}/{target_external_id}"

                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.patch(
                        url,
                        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
                        json=payload,
                    )

                    if response.status_code == 204:
                        return {"success": True, "data": {}}

                    return {"success": False, "error": response.text}

        return {"success": False, "error": f"Operation {operation_type} not implemented"}

    async def get_webhook_events(
        self,
        instance: ConnectorInstance,
        payload: dict[str, Any],
    ) -> list[dict[str, Any]]:
        events = []

        # Salesforce Change Data Capture events
        for event in payload.get("payload", []):
            event_type = event.get("event", {}).get("type", "")
            object_type = event.get("event", {}).get("objectType", "")

            events.append({
                "external_event_id": event.get("event", {}).get("replayId", ""),
                "event_type": f"salesforce.{object_type}.{event_type}",
                "source_id": event.get("event", {}).get("recordIds", [""])[0] if event.get("event", {}).get("recordIds") else "",
                "source_type": event.get("event", {}).get("objectType", "").lower(),
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
                    "https://login.salesforce.com/services/oauth2/token",
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
                    new_credentials["instance_url"] = data["instance_url"]
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
        instance_url = credentials.get("instance_url")

        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{instance_url}/services/data/v58.0/sobjects/User/{external_id}",
                headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            )

            if response.status_code == 200:
                data = response.json()
                return {
                    "external_id": data.get("Id"),
                    "external_email": data.get("Email"),
                    "external_display_name": data.get("Name"),
                    "external_metadata": {
                        "username": data.get("Username"),
                        "first_name": data.get("FirstName"),
                        "last_name": data.get("LastName"),
                        "title": data.get("Title"),
                        "profile_name": data.get("Profile", {}).get("Name"),
                        "role_name": data.get("UserRole", {}).get("Name"),
                    },
                }

        return None

    async def discover_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return {
            "inbound_capabilities": ["read_users", "read_accounts", "read_contacts", "read_opportunities", "read_leads", "read_cases", "read_campaigns"],
            "outbound_capabilities": ["create_account", "create_contact", "create_opportunity", "create_lead", "update_account", "update_contact", "update_opportunity", "update_lead"],
            "supported_entities": ["user", "account", "contact", "opportunity", "lead", "case", "campaign", "task", "event"],
            "supported_events": ["created", "updated", "deleted", "undeleted"],
            "sync_modes": ["full", "incremental", "webhook", "cdc"],
            "auth_types": ["oauth2"],
            "oauth_scopes": [
                "api",
                "refresh_token",
                "full",
            ],
            "required_config_fields": ["client_id", "client_secret", "refresh_token"],
            "optional_config_fields": ["instance_url"],
            "rate_limits": {
                "api": {"requests_per_24h": 5000000, "burst": 100},
                "concurrent": {"limit": 25},
            },
        }

    async def get_capabilities(self, instance: ConnectorInstance) -> dict[str, Any]:
        return await self.discover_capabilities(instance)

    async def validate_config(self, instance: ConnectorInstance) -> tuple[bool, Optional[str]]:
        credentials = instance.credentials
        if not credentials:
            return False, "No credentials configured"
        if not credentials.get("access_token") or not credentials.get("instance_url"):
            return False, "No access_token or instance_url configured"
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
        consumer_secret = credentials.get("consumer_secret")
        if not consumer_secret:
            return False
        expected = hmac.new(consumer_secret.encode(), payload, hashlib.sha256).hexdigest()
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
connector_registry.register(SalesforceConnector())