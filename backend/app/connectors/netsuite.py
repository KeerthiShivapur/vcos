"""
NetSuite Connector for VCOS.

Provides integration with NetSuite for ERP, CRM, and e-commerce data.
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


class NetSuiteConnector(BaseConnector):
    """NetSuite Connector Implementation using REST API."""

    CONFIG = ConnectorConfig(
        name="netsuite",
        display_name="NetSuite",
        description="Cloud-based ERP, CRM, and e-commerce platform",
        category="erp",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "account_id": {"type": "string", "description": "NetSuite account ID"},
                "consumer_key": {"type": "string"},
                "consumer_secret": {"type": "string"},
                "token_id": {"type": "string"},
                "token_secret": {"type": "string"},
                "base_url": {"type": "string", "default": "https://rest.netsuite.com", "description": "NetSuite REST API base URL"},
            },
            "required": ["account_id", "consumer_key", "consumer_secret", "token_id", "token_secret"],
        },
        required_scopes=[],
        supported_operations=[
            "list_customers",
            "get_customer",
            "create_customer",
            "update_customer",
            "list_vendors",
            "get_vendor",
            "create_vendor",
            "update_vendor",
            "list_items",
            "get_item",
            "create_item",
            "update_item",
            "list_sales_orders",
            "get_sales_order",
            "create_sales_order",
            "list_purchase_orders",
            "get_purchase_order",
            "list_invoices",
            "get_invoice",
            "list_payments",
            "list_journal_entries",
            "list_accounts",
            "get_account",
            "list_departments",
            "get_department",
            "list_locations",
            "get_location",
            "list_employees",
            "get_employee",
            "list_subsidiaries",
            "get_subsidiary",
        ],
        webhook_events=[],
        rate_limits=RateLimitConfig(
            requests_per_second=10,
            requests_per_minute=60,
            burst=10,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/netsuite.svg",
        documentation_url="https://docs.oracle.com/en/cloud/saas/netsuite/ns-online-help/section_1546938065.html",
    )

    BASE_URL = "https://rest.netsuite.com"
    OAUTH_BASE_URL = "https://rest.netsuite.com"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.account_id = connection_config.get("account_id")
        self.consumer_key = connection_config.get("consumer_key")
        self.consumer_secret = connection_config.get("consumer_secret")
        self.token_id = connection_config.get("token_id")
        self.token_secret = connection_config.get("token_secret")
        self.base_url = connection_config.get("base_url", "https://rest.netsuite.com")

    def _build_oauth_header(self, method: str, url: str, params: Dict[str, Any] = None) -> str:
        """Build OAuth 1.0a Authorization header for NetSuite."""
        import hmac
        import hashlib
        import base64
        import time
        import random
        import urllib.parse

        # OAuth parameters
        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_token": self.token_id,
            "oauth_signature_method": "HMAC-SHA256",
            "oauth_timestamp": str(int(time.time())),
            "oauth_nonce": str(random.randint(1000000, 9999999)),
            "oauth_version": "1.0",
        }

        # Add any additional params
        if params:
            oauth_params.update(params)

        # Create parameter string
        param_str = "&".join(f"{urllib.parse.quote(k, safe='')}={urllib.parse.quote(v, safe='')}" 
                            for k, v in sorted(oauth_params.items()))

        # Create base string
        base_string = f"{method.upper()}&{urllib.parse.quote(url, safe='')}&{urllib.parse.quote(param_str, safe='')}"

        # Create signing key
        signing_key = f"{urllib.parse.quote(self.consumer_secret, safe='')}&{urllib.parse.quote(self.token_secret, safe='')}"

        # Generate signature
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha256).digest()
        ).decode()

        # Build authorization header
        oauth_params["oauth_signature"] = signature
        auth_header = "OAuth " + ", ".join(
            f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"' 
            for k, v in sorted(oauth_params.items())
        )

        return auth_header

    async def authenticate(self) -> bool:
        """Authenticate with NetSuite using OAuth 1.0a."""
        # NetSuite uses OAuth 1.0a for authentication
        # The authenticate method validates that credentials are present
        if not all([self.account_id, self.consumer_key, self.consumer_secret, self.token_id, self.token_secret]):
            raise ValueError("NetSuite requires account_id, consumer_key, consumer_secret, token_id, token_secret")

        # Test connection
        try:
            await self._make_request("GET", "/application", params={})
            self._authenticated = True
            logger.info("NetSuite authenticated with OAuth 1.0a")
            return True
        except Exception as e:
            logger.error(f"NetSuite authentication failed: {e}")
            raise

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Prefer": "transient",
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.BASE_URL, f"/services/rest/record/v1{endpoint}")
        headers = self._get_headers()

        # Add OAuth header
        import time
        import random
        import urllib.parse
        import hashlib
        import hmac
        import base64

        # For simplicity, we'll add the OAuth header here
        # In production, use a proper OAuth 1.0a library
        import random
        import time

        url = urljoin(self.BASE_URL, f"/services/rest/record/v1{endpoint}")
        headers = self._get_headers()

        # Build OAuth header
        oauth_params = {
            "oauth_consumer_key": self.consumer_key,
            "oauth_token": self.token_id,
            "oauth_signature_method": "HMAC-SHA256",
            "oauth_timestamp": str(int(time.time())),
            "oauth_nonce": str(random.randint(1000000, 9999999)),
            "oauth_version": "1.0",
        }

        # Build signature base string
        param_str = "&".join(f"{k}={v}" for k, v in sorted(oauth_params.items()))
        base_string = f"GET&{urllib.parse.quote(self.base_url + endpoint, safe='')}&{urllib.parse.quote(param_str, safe='')}"
        signing_key = f"{urllib.parse.quote(self.consumer_secret, safe='')}&{urllib.parse.quote(self.token_secret, safe='')}"
        signature = base64.b64encode(
            hmac.new(signing_key.encode(), base_string.encode(), hashlib.sha256).digest()
        ).decode()

        oauth_params["oauth_signature"] = signature
        auth_header = "OAuth " + ", ".join(
            f'{urllib.parse.quote(k, safe="")}="{urllib.parse.quote(v, safe="")}"'
            for k, v in sorted(oauth_params.items())
        )

        headers["Authorization"] = auth_header

        await self.rate_limiter.acquire()

        async def _request():
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                if resp.status == 429:
                    retry_after = int(resp.headers.get("Retry-After", "60"))
                    await asyncio.sleep(retry_after)
                    return await _request()
                if resp.status >= 400:
                    error_text = await resp.text()
                    raise Exception(f"NetSuite API error: {resp.status} - {error_text}")
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
            "list_customers": self._list_customers,
            "list_vendors": self._list_vendors,
            "list_items": self._list_items,
            "list_sales_orders": self._list_sales_orders,
            "list_purchase_orders": self._list_purchase_orders,
            "list_invoices": self._list_invoices,
            "list_payments": self._list_payments,
            "list_journal_entries": self._list_journal_entries,
            "list_accounts": self._list_accounts,
            "list_departments": self._list_departments,
            "list_locations": self._list_locations,
            "list_employees": self._list_employees,
            "list_subsidiaries": self._list_subsidiaries,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_customers(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["email", "name", "subsidiary", "entityStatus", "dateCreated", "lastModifiedDate"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/customer", params=params)
            for customer in data.get("items", []):
                yield {
                    "type": "customer",
                    "id": customer["id"],
                    "data": customer,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_vendors(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["email", "name", "subsidiary", "entityStatus", "dateCreated", "lastModifiedDate"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/vendor", params=params)
            for vendor in data.get("items", []):
                yield {
                    "type": "vendor",
                    "id": vendor["id"],
                    "data": vendor,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_items(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["name", "type", "subsidiary", "itemType", "upcCode", "lastModifiedDate"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/item", params=params)
            for item in data.get("items", []):
                yield {
                    "type": "item",
                    "id": item["id"],
                    "data": item,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_sales_orders(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["entityId", "status", "startDate", "endDate", "subsidiary", "createdDate"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/salesOrder", params=params)
            for order in data.get("items", []):
                yield {
                    "type": "sales_order",
                    "id": order["id"],
                    "data": order,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_purchase_orders(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["entityId", "status", "startDate", "endDate", "subsidiary", "createdDate"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/purchaseOrder", params=params)
            for po in data.get("items", []):
                yield {
                    "type": "purchase_order",
                    "id": po["id"],
                    "data": po,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_invoices(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["entityId", "status", "tranDateStart", "tranDateEnd", "subsidiary"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/invoice", params=params)
            for invoice in data.get("items", []):
                yield {
                    "type": "invoice",
                    "id": invoice["id"],
                    "data": invoice,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_payments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["customerId", "accountId", "tranDateStart", "tranDateEnd", "paymentMethod"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/customerPayment", params=params)
            for payment in data.get("items", []):
                yield {
                    "type": "payment",
                    "id": payment["id"],
                    "data": payment,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_journal_entries(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["accountId", "subsidiaryId", "tranDateStart", "tranDateEnd", "postingPeriodId"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/journalEntry", params=params)
            for entry in data.get("items", []):
                yield {
                    "type": "journal_entry",
                    "id": entry["id"],
                    "data": entry,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_accounts(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["name", "number", "type", "accountType", "subsidiary", "isInactive"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/account", params=params)
            for account in data.get("items", []):
                yield {
                    "type": "account",
                    "id": account["id"],
                    "data": account,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_departments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/department", params=params)
            for dept in data.get("items", []):
                yield {
                    "type": "department",
                    "id": dept["id"],
                    "data": dept,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_locations(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters and filters.get("subsidiary"):
            params["subsidiary"] = filters["subsidiary"]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/location", params=params)
            for loc in data.get("items", []):
                yield {
                    "type": "location",
                    "id": loc["id"],
                    "data": loc,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_employees(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters:
            for key in ["email", "firstName", "lastName", "subsidiary", "department", "location", "employeeStatus", "supervisorId"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/employee", params=params)
            for emp in data.get("items", []):
                yield {
                    "type": "employee",
                    "id": emp["id"],
                    "data": emp,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def _list_subsidiaries(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        if filters and filters.get("parent"):
            params["parent"] = filters["parent"]
        if cursor and cursor.cursor:
            params["offset"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/subsidiary", params=params)
            for sub in data.get("items", []):
                yield {
                    "type": "subsidiary",
                    "id": sub["id"],
                    "data": sub,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("items", [])) < params.get("limit", 100):
                break
            params["offset"] = params.get("offset", 0) + params["limit"]

    async def push_data(
        self,
        operation: str,
        data: List[Dict[str, Any]],
    ) -> SyncResult:
        if not self._authenticated:
            await self.authenticate()

        result = SyncResult(success=True, started_at=datetime.utcnow())

        handlers = {
            "create_customer": self._create_customer,
            "update_customer": self._update_customer,
            "create_vendor": self._create_vendor,
            "create_item": self._create_item,
            "create_sales_order": self._create_sales_order,
            "create_purchase_order": self._create_purchase_order,
            "create_invoice": self._create_invoice,
            "create_journal_entry": self._create_journal_entry,
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

    async def _create_customer(self, customer_data: Dict[str, Any]):
        payload = customer_data.get("customer", {})
        await self._make_request("POST", "/customer", json=payload)

    async def _update_customer(self, customer_data: Dict[str, Any]):
        customer_id = customer_data.get("customer_id")
        if not customer_id:
            raise ValueError("customer_id required")
        payload = customer_data.get("customer", {})
        await self._make_request("PUT", f"/customer/{customer_id}", json=payload)

    async def _create_vendor(self, vendor_data: Dict[str, Any]):
        payload = vendor_data.get("vendor", {})
        await self._make_request("POST", "/vendor", json=payload)

    async def _create_item(self, item_data: Dict[str, Any]):
        payload = item_data.get("item", {})
        await self._make_request("POST", "/item", json=payload)

    async def _create_sales_order(self, order_data: Dict[str, Any]):
        payload = order_data.get("sales_order", {})
        await self._make_request("POST", "/salesOrder", json=payload)

    async def _create_purchase_order(self, order_data: Dict[str, Any]):
        payload = order_data.get("purchase_order", {})
        await self._make_request("POST", "/purchaseOrder", json=payload)

    async def _create_invoice(self, invoice_data: Dict[str, Any]):
        payload = invoice_data.get("invoice", {})
        await self._make_request("POST", "/invoice", json=payload)

    async def _create_journal_entry(self, entry_data: Dict[str, Any]):
        payload = entry_data.get("journal_entry", {})
        await self._make_request("POST", "/journalEntry", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/application")
            return "id" in data
        except Exception as e:
            logger.error(f"NetSuite connection test failed: {e}")
            return False


import time
import random
import urllib.parse
import hashlib
import hmac
import base64
from app.connectors.base import connector_registry
connector_registry.register(NetSuiteConnector, NetSuiteConnector.CONFIG)