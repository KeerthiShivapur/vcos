"""
Salesforce Connector for VCOS.

Provides integration with Salesforce for CRM data including accounts, contacts,
opportunities, leads, and custom objects.
"""

import logging
import time
import urllib.parse
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


class SalesforceConnector(BaseConnector):
    """Salesforce Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="salesforce",
        display_name="Salesforce",
        description="Customer relationship management platform",
        category="crm",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "login_url": {"type": "string", "default": "https://login.salesforce.com", "description": "Login URL (use https://test.salesforce.com for sandbox)"},
                "instance_url": {"type": "string", "description": "Instance URL (e.g., https://mycompany.my.salesforce.com)"},
                "access_token": {"type": "string", "description": "OAuth access token"},
                "refresh_token": {"type": "string", "description": "OAuth refresh token"},
            },
            "required": ["client_id", "client_secret", "redirect_uri"],
        },
        required_scopes=[
            "api",
            "refresh_token",
            "offline_access",
        ],
        supported_operations=[
            "query",
            "create",
            "update",
            "upsert",
            "delete",
            "describe",
            "list_sobjects",
            "describe_sobject",
            "search",
            "get_user",
            "list_users",
        ],
        webhook_events=[
            "created",
            "updated",
            "deleted",
            "undeleted",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=25,
            requests_per_minute=1000,
            burst=50,
        ),
    )

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
        self.redirect_uri = connection_config.get("redirect_uri")
        self.login_url = connection_config.get("login_url", "https://login.salesforce.com")
        self.instance_url = connection_config.get("instance_url")
        self.access_token = connection_config.get("access_token")
        self.refresh_token = connection_config.get("refresh_token")
        self._token_manager = None
        self._api_version = "v60.0"

    @property
    def BASE_URL(self) -> str:
        if self.instance_url:
            return f"{self.instance_url}/services/data/{self._api_version}"
        return f"{self.login_url}/services/data/{self._api_version}"

    @property
    def TOKEN_URL(self) -> str:
        return f"{self.login_url}/services/oauth2/token"

    async def authenticate(self) -> bool:
        """Authenticate with Salesforce using OAuth2."""
        if self.access_token and self.instance_url:
            self._authenticated = True
            logger.info("Salesforce authenticated with existing tokens")
            return True

        if self.refresh_token:
            await self._refresh_access_token()
            return True

        # OAuth2 flow would need authorization code
        from app.connectors.base import TokenManager
        self._token_manager = TokenManager(
            self.client_id,
            self.client_secret,
            self.TOKEN_URL,
        )
        # For OAuth2, we'd need the authorization code
        # This is typically handled by the web flow
        logger.info("Salesforce OAuth2 requires authorization code flow")
        return False

    async def _refresh_access_token(self) -> bool:
        """Refresh the access token using refresh token."""
        data = {
            "grant_type": "refresh_token",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
        }
        async with self.session.post(self.TOKEN_URL, data=data) as resp:
            if resp.status != 200:
                return False
            data = await resp.json()
            self.access_token = data.get("access_token")
            self.instance_url = data.get("instance_url")
            if data.get("refresh_token"):
                self.refresh_token = data["refresh_token"]
            return True

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

    async def _ensure_authenticated(self):
        """Ensure we have a valid access token."""
        if not self.access_token or not self.instance_url:
            if self.refresh_token:
                await self._refresh_access_token()
            else:
                raise Exception("Not authenticated. Please complete OAuth2 flow first.")

    async def pull_data(
        self,
        operation: str,
        cursor: Optional[SyncCursor] = None,
        filters: Optional[Dict[str, Any]] = None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        await self._ensure_authenticated()

        handlers = {
            "query": self._query,
            "list_sobjects": self._list_sobjects,
            "describe_sobject": self._describe_sobject,
            "search": self._search,
            "get_user": self._get_user,
            "list_users": self._list_users,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _query(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute SOQL query."""
        soql = filters.get("soql") if filters else "SELECT Id, Name FROM Account LIMIT 2000"
        if not soql:
            raise ValueError("SOQL query required")

        if cursor and cursor.cursor:
            next_records_url = cursor.cursor
        else:
            next_records_url = f"/services/data/{self._api_version}/query/?q={urllib.parse.quote(soql)}"

        while next_records_url:
            headers = await self._get_headers()
            url = urljoin(self.instance_url, next_records_url)
            async with self.session.get(url, headers=headers) as resp:
                resp.raise_for_status()
                data = await resp.json()

                for record in data.get("records", []):
                    yield {
                        "type": "record",
                        "id": record.get("Id"),
                        "data": {k: v for k, v in record.items() if k != "attributes"},
                        "synced_at": datetime.utcnow().isoformat(),
                    }

                if data.get("done"):
                    break
                next_records_url = data.get("nextRecordsUrl")

    async def _list_sobjects(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """List all sObjects."""
        headers = await self._get_headers()
        async with self.session.get(
            f"{self.instance_url}/services/data/{self._api_version}/sobjects/",
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

            for sobject in data.get("sobjects", []):
                yield {
                    "type": "sobject",
                    "id": sobject["name"],
                    "data": sobject,
                    "synced_at": datetime.utcnow().isoformat(),
                }

    async def _describe_sobject(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        sobject_name = filters.get("sobject") if filters else None
        if not sobject_name:
            raise ValueError("sobject filter required")

        headers = await self._get_headers()
        async with self.session.get(
            f"{self.instance_url}/services/data/{self._api_version}/sobjects/{sobject_name}/describe",
            headers=headers,
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()

            yield {
                "type": "sobject_describe",
                "id": data["name"],
                "data": data,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _search(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute SOSL search."""
        sosl = filters.get("sosl") if filters else None
        if not sosl:
            raise ValueError("SOSL search string required")

        headers = await self._get_headers()
        url = f"{self.instance_url}/services/data/{self._api_version}/search/?q={urllib.parse.quote(filters['sosl'])}"
        
        async with self.session.get(url, headers=headers) as resp:
            resp.raise_for_status()
            data = await resp.json()

            for record in data.get("searchRecords", []):
                yield {
                    "type": "search_result",
                    "id": record.get("attributes", {}).get("type", "record"),
                    "data": record,
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
        headers["Sforce-Call-Options"] = "client=VCOS"
        return headers

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        """Push data to Salesforce using REST API."""
        await self._ensure_authenticated()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create": self._create_record,
            "update": self._update_record,
            "upsert": self._upsert_record,
            "delete": self._delete_record,
        }

        handler = handlers.get(operation)
        if not handler:
            result.success = False
            result.errors.append({"error": f"Unsupported push operation: {operation}"})
            return result

        for item in data:
            try:
                await handler(item)
                result.records_created += 1 if operation == "create" else 0
                result.records_updated += 1 if operation in ["update", "upsert"] else 0
                result.records_processed += 1
            except Exception as e:
                result.records_failed += 1
                result.errors.append({"item": item, "error": str(e)})

        result.success = result.records_failed == 0
        result.completed_at = datetime.utcnow()
        result.duration_ms = int((result.completed_at - result.started_at).total_seconds() * 1000)
        return result

    async def _create_record(self, record_data: Dict[str, Any]):
        """Create a new record."""
        sobject = record_data.get("sobject")
        if not sobject:
            raise ValueError("sobject required")

        fields = {k: v for k, v in record_data.items() if k != "sobject"}
        headers = await self._get_headers()
        async with self.session.post(
            f"{self.instance_url}/services/data/{self._api_version}/sobjects/{record_data['sobject']}/",
            headers=headers,
            json=fields,
        ) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def _update_record(self, record_data: Dict[str, Any]):
        sobject = record_data.get("sobject")
        record_id = record_data.get("id")
        if not sobject or not record_id:
            raise ValueError("sobject and id required")

        fields = {k: v for k, v in record_data.items() if k not in ["sobject", "id"]}
        url = f"{self.instance_url}/services/data/{self._api_version}/sobjects/{sobject}/{record_id}"
        headers = await self._get_headers()
        async with self.session.patch(url, json={k: v for k, v in record_data.items() if k not in ["sobject", "id"]}) as resp:
            resp.raise_for_status()

    async def _upsert_record(self, record_data: Dict[str, Any]):
        sobject = record_data.get("sobject")
        external_id_field = record_data.get("external_id_field")
        external_id = record_data.get("external_id")
        if not sobject or not external_id_field or not external_id:
            raise ValueError("sobject, external_id_field, and external_id required")

        fields = {k: v for k, v in record_data.items() if k not in ["sobject", "external_id_field", "external_id"]}
        url = f"{self.instance_url}/services/data/{self._api_version}/sobjects/{sobject}/{external_id_field}/{external_id}"
        headers = await self._get_headers()
        async with self.session.patch(url, json=fields) as resp:
            resp.raise_for_status()

    async def _delete_record(self, record_data: Dict[str, Any]):
        sobject = record_data.get("sobject")
        record_id = record_data.get("id")
        if not sobject or not record_id:
            raise ValueError("sobject and id required")

        url = f"{self.instance_url}/services/data/{self._api_version}/sobjects/{sobject}/{record_id}"
        headers = await self._get_headers()
        async with self.session.delete(url, headers=headers) as resp:
            if resp.status == 204:
                return
            resp.raise_for_status()

    async def test_connection(self) -> bool:
        try:
            headers = await self._get_headers()
            async with self.session.get(
                f"{self.instance_url}/services/data/{self._api_version}/limits",
                headers=headers,
            ) as resp:
                return resp.status == 200
        except Exception as e:
            logger.error(f"Salesforce connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(SalesforceConnector, SalesforceConnector.CONFIG)