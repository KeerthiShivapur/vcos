"""
Xero Connector for VCOS.

Provides integration with Xero for accounting and financial data.
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


class XeroConnector(BaseConnector):
    """Xero Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="xero",
        display_name="Xero",
        description="Cloud-based accounting software for small to medium businesses",
        category="finance",
        auth_type=AuthType.OAUTH2,
        config_schema={
            "type": "object",
            "properties": {
                "client_id": {"type": "string"},
                "client_secret": {"type": "string"},
                "redirect_uri": {"type": "string"},
                "tenant_id": {"type": "string", "description": "Xero tenant ID (organization ID)"},
                "access_token": {"type": "string", "description": "OAuth access token"},
                "refresh_token": {"type": "string"},
            },
            "required": ["client_id", "client_secret", "redirect_uri"],
        },
        required_scopes=[
            "accounting.contacts.read",
            "accounting.contacts.write",
            "accounting.transactions.read",
            "accounting.transactions.write",
            "accounting.settings.read",
            "accounting.settings.write",
            "accounting.reports.read",
            "files.read",
            "files.write",
        ],
        supported_operations=[
            "list_contacts",
            "get_contact",
            "create_contact",
            "update_contact",
            "list_invoices",
            "get_invoice",
            "create_invoice",
            "update_invoice",
            "list_bills",
            "get_bill",
            "create_bill",
            "update_bill",
            "list_bank_transactions",
            "get_bank_transaction",
            "list_bank_accounts",
            "list_accounts",
            "get_account",
            "create_account",
            "update_account",
            "list_items",
            "get_item",
            "create_item",
            "update_item",
            "list_payments",
            "get_payment",
            "list_credit_notes",
            "get_credit_note",
            "create_credit_note",
            "list_payments",
            "get_payment",
            "list_journals",
            "get_journal",
            "list_reports",
            "run_report",
        ],
        webhook_events=[
            "contact.created",
            "contact.updated",
            "invoice.created",
            "invoice.updated",
            "invoice.voided",
            "bill.created",
            "bill.updated",
            "payment.created",
            "contact.created",
            "contact.updated",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=5,
            requests_per_minute=60,
            burst=10,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/xero.svg",
        documentation_url="https://developer.xero.com/documentation/api/",
    )

    BASE_URL = "https://api.xero.com/api.xro/2.0"
    TOKEN_URL = "https://identity.xero.com/connect/token"

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
        self.tenant_id = connection_config.get("tenant_id")
        self.access_token = connection_config.get("access_token")
        self.refresh_token = connection_config.get("refresh_token")
        self._token_manager = None

    async def authenticate(self) -> bool:
        """Authenticate with Xero using OAuth2."""
        if self.access_token:
            self._authenticated = True
            logger.info("Xero authenticated with access token")
            return True

        if self.client_id and self.client_secret:
            from app.connectors.base import TokenManager
            self._token_manager = TokenManager(self.client_id, self.client_secret, self.TOKEN_URL)
            if self.refresh_token:
                self._token_manager._refresh_token = self.refresh_token
            await self._token_manager.get_access_token()
            self._authenticated = True
            logger.info("Xero authenticated with OAuth2")
            return True

        raise ValueError("Xero requires access_token or OAuth2 credentials (client_id, client_secret)")

    async def _get_headers(self) -> Dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
            if self.tenant_id:
                headers["Xero-tenant-id"] = self.tenant_id
        elif self._token_manager:
            token = await self._token_manager.get_access_token()
            headers["Authorization"] = f"Bearer {token}"
            if self.tenant_id:
                headers["Xero-tenant-id"] = self.tenant_id
        return headers

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.BASE_URL, endpoint)
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
                    raise Exception(f"Xero API error: {resp.status} - {error_text}")
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
            "list_contacts": self._list_contacts,
            "list_invoices": self._list_invoices,
            "list_bills": self._list_bills,
            "list_bank_transactions": self._list_bank_transactions,
            "list_bank_accounts": self._list_bank_accounts,
            "list_accounts": self._list_accounts,
            "list_items": self._list_items,
            "list_payments": self._list_payments,
            "list_credit_notes": self._list_credit_notes,
            "list_payments": self._list_payments,
            "list_journals": self._list_journals,
            "list_reports": self._list_reports,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _list_contacts(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "modifiedSince", "contactID", "email", "name"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/Contacts", params=params)
            for contact in data.get("Contacts", []):
                yield {
                    "type": "contact",
                    "id": contact["ContactID"],
                    "data": contact,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("Contacts", [])) < 100:
                break
            params["page"] += 1

    async def _list_invoices(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "modifiedSince", "invoiceID", "contactID", "status"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/Invoices", params=params)
            for invoice in data.get("Invoices", []):
                yield {
                    "type": "invoice",
                    "id": invoice["InvoiceID"],
                    "data": invoice,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("Invoices", [])) < 100:
                break
            params["page"] += 1

    async def _list_bills(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "modifiedSince", "billID", "contactID", "status"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/Bills", params=params)
            for bill in data.get("Bills", []):
                yield {
                    "type": "bill",
                    "id": bill["BillID"],
                    "data": bill,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("Bills", [])) < 100:
                break
            params["page"] += 1

    async def _list_bank_transactions(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "modifiedSince", "bankAccountID", "fromDate", "toDate"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/BankTransactions", params=params)
            for transaction in data.get("BankTransactions", []):
                yield {
                    "type": "bank_transaction",
                    "id": transaction["BankTransactionID"],
                    "data": transaction,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("BankTransactions", [])) < 100:
                break
            params["page"] += 1

    async def _list_bank_accounts(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        data = await self._make_request("GET", "/BankAccounts")
        for account in data.get("BankAccounts", []):
            yield {
                "type": "bank_account",
                "id": account["AccountID"],
                "data": account,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_accounts(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "accountID", "code", "name", "type"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/Accounts", params=params)
            for account in data.get("Accounts", []):
                yield {
                    "type": "account",
                    "id": account["AccountID"],
                    "data": account,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("Accounts", [])) < 100:
                break
            params["page"] += 1

    async def _list_items(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "itemID", "code", "name", "type"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/Items", params=params)
            for item in data.get("Items", []):
                yield {
                    "type": "item",
                    "id": item["ItemID"],
                    "data": item,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("Items", [])) < 100:
                break
            params["page"] += 1

    async def _list_payments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "paymentID", "invoiceID", "billID", "dateFrom", "dateTo"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/Payments", params=params)
            for payment in data.get("Payments", []):
                yield {
                    "type": "payment",
                    "id": payment["PaymentID"],
                    "data": payment,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("Payments", [])) < 100:
                break
            params["page"] += 1

    async def _list_credit_notes(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "modifiedSince", "creditNoteID", "contactID", "status"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/CreditNotes", params=params)
            for credit_note in data.get("CreditNotes", []):
                yield {
                    "type": "credit_note",
                    "id": credit_note["CreditNoteID"],
                    "data": credit_note,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("CreditNotes", [])) < 100:
                break
            params["page"] += 1

    async def _list_payments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "paymentID", "invoiceID", "dateFrom", "dateTo"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/Payments", params=params)
            for payment in data.get("Payments", []):
                yield {
                    "type": "payment",
                    "id": payment["PaymentID"],
                    "data": payment,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("Payments", [])) < 100:
                break
            params["page"] += 1

    async def _list_journals(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"page": 1, "pageSize": 100}
        if filters:
            for key in ["where", "order", "journalID", "dateFrom", "dateTo"]:
                if key in filters:
                    params[key] = filters[key]
        if cursor and cursor.cursor:
            params["page"] = cursor.cursor

        while True:
            data = await self._make_request("GET", "/Journals", params=params)
            for journal in data.get("Journals", []):
                yield {
                    "type": "journal",
                    "id": journal["JournalID"],
                    "data": journal,
                    "synced_at": datetime.utcnow().isoformat(),
                }

            if len(data.get("Journals", [])) < 100:
                break
            params["page"] += 1

    async def _list_reports(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        reports = [
            {"name": "BalanceSheet", "available": True},
            {"name": "ProfitAndLoss", "available": True},
            {"name": "TrialBalance", "available": True},
            {"name": "AgedPayablesDetail", "available": True},
            {"name": "AgedReceivablesDetail", "available": True},
            {"name": "CashFlow", "available": True},
        ]

        for report in reports:
            yield {
                "type": "report",
                "id": report["name"],
                "data": report,
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
            "create_contact": self._create_contact,
            "update_contact": self._update_contact,
            "create_invoice": self._create_invoice,
            "update_invoice": self._update_invoice,
            "create_bill": self._create_bill,
            "update_bill": self._update_bill,
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

    async def _create_contact(self, contact_data: Dict[str, Any]):
        payload = {"Contacts": [contact_data.get("contact", {})]}
        await self._make_request("POST", "/Contacts", json=payload)

    async def _update_contact(self, contact_data: Dict[str, Any]):
        contact_id = contact_data.get("contact_id")
        if not contact_id:
            raise ValueError("contact_id required")
        payload = {"Contacts": [{"ContactID": contact_id, **contact_data.get("contact", {})}]}
        await self._make_request("POST", "/Contacts", json=payload)

    async def _create_invoice(self, invoice_data: Dict[str, Any]):
        payload = {"Invoices": [invoice_data.get("invoice", {})]}
        await self._make_request("POST", "/Invoices", json=payload)

    async def _update_invoice(self, invoice_data: Dict[str, Any]):
        invoice_id = invoice_data.get("invoice_id")
        if not invoice_id:
            raise ValueError("invoice_id required")
        payload = {"Invoices": [{"InvoiceID": invoice_id, **invoice_data.get("invoice", {})}]}
        await self._make_request("POST", "/Invoices", json=payload)

    async def _create_bill(self, bill_data: Dict[str, Any]):
        payload = {"Bills": [bill_data.get("bill", {})]}
        await self._make_request("POST", "/Bills", json=payload)

    async def _update_bill(self, bill_data: Dict[str, Any]):
        bill_id = bill_data.get("bill_id")
        if not bill_id:
            raise ValueError("bill_id required")
        payload = {"Bills": [{"BillID": bill_id, **bill_data.get("bill", {})}]}
        await self._make_request("POST", "/Bills", json=payload)

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/Organisation")
            return "Organisation" in data
        except Exception as e:
            logger.error(f"Xero connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(XeroConnector, XeroConnector.CONFIG)