"""
Stripe Connector for VCOS.

Provides integration with Stripe for payments, customers, subscriptions, and financial data.
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


class StripeConnector(BaseConnector):
    """Stripe Connector Implementation."""

    CONFIG = ConnectorConfig(
        name="stripe",
        display_name="Stripe",
        description="Payment processing and financial platform",
        category="finance",
        auth_type=AuthType.API_KEY,
        config_schema={
            "type": "object",
            "properties": {
                "secret_key": {"type": "string", "description": "Stripe Secret Key (sk_live_... or sk_test_...)"},
                "publishable_key": {"type": "string", "description": "Stripe Publishable Key (pk_live_... or pk_test_...)"},
                "webhook_secret": {"type": "string", "description": "Stripe Webhook Signing Secret"},
                "api_version": {"type": "string", "default": "2023-10-16", "description": "Stripe API Version"},
            },
            "required": ["secret_key"],
        },
        required_scopes=[],
        supported_operations=[
            "list_customers",
            "get_customer",
            "create_customer",
            "update_customer",
            "delete_customer",
            "list_payment_methods",
            "attach_payment_method",
            "detach_payment_method",
            "list_charges",
            "get_charge",
            "create_charge",
            "refund_charge",
            "list_payments",
            "get_payment_intent",
            "create_payment_intent",
            "confirm_payment_intent",
            "list_subscriptions",
            "get_subscription",
            "create_subscription",
            "update_subscription",
            "cancel_subscription",
            "list_products",
            "get_product",
            "create_product",
            "update_product",
            "list_prices",
            "get_price",
            "create_price",
            "list_invoices",
            "get_invoice",
            "create_invoice",
            "finalize_invoice",
            "send_invoice",
            "list_invoice_items",
            "create_invoice_item",
            "list_refunds",
            "get_refund",
            "create_refund",
            "list_disputes",
            "get_dispute",
            "update_dispute",
            "list_events",
            "get_event",
            "list_balance_transactions",
            "list_payouts",
            "create_payout",
            "list_webhook_endpoints",
            "create_webhook_endpoint",
            "delete_webhook_endpoint",
        ],
        webhook_events=[
            "customer.created",
            "customer.updated",
            "customer.deleted",
            "payment_method.attached",
            "payment_method.detached",
            "charge.succeeded",
            "charge.failed",
            "charge.refunded",
            "payment_intent.created",
            "payment_intent.succeeded",
            "payment_intent.payment_failed",
            "invoice.created",
            "invoice.finalized",
            "invoice.paid",
            "invoice.payment_failed",
            "invoice.upcoming",
            "subscription.created",
            "subscription.updated",
            "subscription.deleted",
            "subscription.trial_will_end",
            "product.created",
            "product.updated",
            "product.deleted",
            "price.created",
            "price.updated",
            "price.deleted",
            "refund.created",
            "refund.updated",
            "dispute.created",
            "dispute.updated",
            "dispute.closed",
            "payout.created",
            "payout.paid",
            "payout.failed",
        ],
        rate_limits=RateLimitConfig(
            requests_per_second=25,
            requests_per_minute=100,
            burst=50,
        ),
        logo_url="https://cdn.jsdelivr.net/npm/simple-icons@v9/icons/stripe.svg",
        documentation_url="https://stripe.com/docs/api",
    )

    BASE_URL = "https://api.stripe.com/v1"

    def __init__(
        self,
        config: ConnectorConfig,
        connection_config: Dict[str, Any],
        organization_id: str,
        connection_id: str,
    ):
        super().__init__(config, connection_config, organization_id, connection_id)
        self.secret_key = connection_config.get("secret_key")
        self.publishable_key = connection_config.get("publishable_key")
        self.webhook_secret = connection_config.get("webhook_secret")
        self.api_version = connection_config.get("api_version", "2023-10-16")

    async def authenticate(self) -> bool:
        """Authenticate with Stripe using secret key."""
        if not self.secret_key:
            raise ValueError("Stripe requires secret_key")

        self._authenticated = True
        logger.info("Stripe authenticated with secret key")
        return True

    async def _get_headers(self) -> Dict[str, str]:
        return {
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {self.secret_key}",
            "Stripe-Version": self.api_version,
        }

    async def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make Stripe API request with error handling."""
        if not self._authenticated:
            await self.authenticate()

        url = urljoin(self.BASE_URL, endpoint)
        headers = await self._get_headers()

        await self.rate_limiter.acquire()

        # Stripe uses form data for POST/PUT/DELETE
        if method in ("POST", "PUT", "DELETE") and "json" in kwargs:
            data = kwargs.pop("json")
            kwargs["data"] = data

        async def _request():
            async with self.session.request(method, url, headers=headers, **kwargs) as resp:
                response_data = await resp.json()
                if resp.status >= 400:
                    error = response_data.get("error", {})
                    raise Exception(f"Stripe API error: {error.get('message', 'Unknown error')} (type: {error.get('type')}, code: {error.get('code')})")
                return response_data

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
            "list_payment_methods": self._list_payment_methods,
            "list_charges": self._list_charges,
            "list_payments": self._list_payments,
            "list_subscriptions": self._list_subscriptions,
            "list_products": self._list_products,
            "list_prices": self._list_prices,
            "list_invoices": self._list_invoices,
            "list_invoice_items": self._list_invoice_items,
            "list_refunds": self._list_refunds,
            "list_disputes": self._list_disputes,
            "list_events": self._list_events,
            "list_balance_transactions": self._list_balance_transactions,
            "list_payouts": self._list_payouts,
            "list_webhook_endpoints": self._list_webhook_endpoints,
        }

        handler = handlers.get(operation)
        if not handler:
            raise ValueError(f"Unsupported operation: {operation}")

        async for item in handler(cursor, filters):
            yield item

    async def _paginate_list(self, endpoint: str, params: Dict[str, Any], cursor: Optional[SyncCursor], filters: Optional[Dict[str, Any]]):
        """Helper for paginated list endpoints."""
        if cursor and cursor.cursor:
            params["starting_after"] = cursor.cursor

        if filters:
            for key in ["created", "limit", "status", "customer", "subscription"]:
                if key in filters:
                    params[key] = filters[key]

        while True:
            data = await self._make_request("GET", endpoint, params=params)
            for item in data.get("data", []):
                yield item

            if data.get("has_more") and data.get("data"):
                params["starting_after"] = data["data"][-1]["id"]
            else:
                break

    async def _list_customers(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for customer in self._paginate_list("/customers", params, cursor, filters):
            yield {
                "type": "customer",
                "id": customer["id"],
                "data": customer,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_payment_methods(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100, "type": "card"}
        customer = filters.get("customer") if filters else None
        if customer:
            params["customer"] = customer

        async for pm in self._paginate_list("/payment_methods", params, cursor, filters):
            yield {
                "type": "payment_method",
                "id": pm["id"],
                "data": pm,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_charges(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for charge in self._paginate_list("/charges", params, cursor, filters):
            yield {
                "type": "charge",
                "id": charge["id"],
                "data": charge,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_payments(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for payment in self._paginate_list("/payment_intents", params, cursor, filters):
            yield {
                "type": "payment_intent",
                "id": payment["id"],
                "data": payment,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_subscriptions(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for sub in self._paginate_list("/subscriptions", params, cursor, filters):
            yield {
                "type": "subscription",
                "id": sub["id"],
                "data": sub,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_products(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for product in self._paginate_list("/products", params, cursor, filters):
            yield {
                "type": "product",
                "id": product["id"],
                "data": product,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_prices(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]], None,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for price in self._paginate_list("/prices", params, cursor, filters):
            yield {
                "type": "price",
                "id": price["id"],
                "data": price,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_invoices(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for invoice in self._paginate_list("/invoices", params, cursor, filters):
            yield {
                "type": "invoice",
                "id": invoice["id"],
                "data": invoice,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_invoice_items(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for item in self._paginate_list("/invoiceitems", params, cursor, filters):
            yield {
                "type": "invoice_item",
                "id": item["id"],
                "data": item,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_refunds(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for refund in self._paginate_list("/refunds", params, cursor, filters):
            yield {
                "type": "refund",
                "id": refund["id"],
                "data": refund,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_disputes(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for dispute in self._paginate_list("/disputes", params, cursor, filters):
            yield {
                "type": "dispute",
                "id": dispute["id"],
                "data": dispute,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_events(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for event in self._paginate_list("/events", params, cursor, filters):
            yield {
                "type": "event",
                "id": event["id"],
                "data": event,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_balance_transactions(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for txn in self._paginate_list("/balance_transactions", params, cursor, filters):
            yield {
                "type": "balance_transaction",
                "id": txn["id"],
                "data": txn,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_payouts(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for payout in self._paginate_list("/payouts", params, cursor, filters):
            yield {
                "type": "payout",
                "id": payout["id"],
                "data": payout,
                "synced_at": datetime.utcnow().isoformat(),
            }

    async def _list_webhook_endpoints(
        self,
        cursor: Optional[SyncCursor],
        filters: Optional[Dict[str, Any]],
    ) -> AsyncGenerator[Dict[str, Any], None]:
        params = {"limit": 100}
        async for endpoint in self._paginate_list("/webhook_endpoints", params, cursor, filters):
            yield {
                "type": "webhook_endpoint",
                "id": endpoint["id"],
                "data": endpoint,
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
            "create_customer": self._create_customer,
            "update_customer": self._update_customer,
            "delete_customer": self._delete_customer,
            "attach_payment_method": self._attach_payment_method,
            "detach_payment_method": self._detach_payment_method,
            "create_charge": self._create_charge,
            "refund_charge": self._refund_charge,
            "create_payment_intent": self._create_payment_intent,
            "confirm_payment_intent": self._confirm_payment_intent,
            "create_subscription": self._create_subscription,
            "update_subscription": self._update_subscription,
            "cancel_subscription": self._cancel_subscription,
            "create_product": self._create_product,
            "update_product": self._update_product,
            "create_price": self._create_price,
            "create_invoice": self._create_invoice,
            "finalize_invoice": self._finalize_invoice,
            "send_invoice": self._send_invoice,
            "create_invoice_item": self._create_invoice_item,
            "create_refund": self._create_refund,
            "update_dispute": self._update_dispute,
            "create_webhook_endpoint": self._create_webhook_endpoint,
            "delete_webhook_endpoint": self._delete_webhook_endpoint,
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

    async def _create_customer(self, customer_data: Dict[str, Any]):
        payload = customer_data.get("customer", {})
        await self._make_request("POST", "/customers", data=payload)

    async def _update_customer(self, customer_data: Dict[str, Any]):
        customer_id = customer_data.get("customer_id")
        if not customer_id:
            raise ValueError("customer_id required")
        payload = customer_data.get("customer", {})
        await self._make_request("POST", f"/customers/{customer_id}", data=payload)

    async def _delete_customer(self, customer_data: Dict[str, Any]):
        customer_id = customer_data.get("customer_id")
        if not customer_id:
            raise ValueError("customer_id required")
        await self._make_request("DELETE", f"/customers/{customer_id}")

    async def _attach_payment_method(self, pm_data: Dict[str, Any]):
        payload = {
            "payment_method": pm_data.get("payment_method_id"),
            "customer": pm_data.get("customer_id"),
        }
        await self._make_request("POST", f"/payment_methods/{pm_data.get('payment_method_id')}/attach", data=payload)

    async def _detach_payment_method(self, pm_data: Dict[str, Any]):
        payment_method_id = pm_data.get("payment_method_id")
        if not payment_method_id:
            raise ValueError("payment_method_id required")
        await self._make_request("POST", f"/payment_methods/{payment_method_id}/detach")

    async def _create_charge(self, charge_data: Dict[str, Any]):
        payload = charge_data.get("charge", {})
        await self._make_request("POST", "/charges", data=payload)

    async def _refund_charge(self, charge_data: Dict[str, Any]):
        charge_id = charge_data.get("charge_id")
        if not charge_id:
            raise ValueError("charge_id required")
        payload = {
            "amount": charge_data.get("amount"),
            "reason": charge_data.get("reason", "requested_by_customer"),
        }
        await self._make_request("POST", f"/charges/{charge_id}/refunds", data=payload)

    async def _create_payment_intent(self, pi_data: Dict[str, Any]):
        payload = pi_data.get("payment_intent", {})
        await self._make_request("POST", "/payment_intents", data=payload)

    async def _confirm_payment_intent(self, pi_data: Dict[str, Any]):
        payment_intent_id = pi_data.get("payment_intent_id")
        if not payment_intent_id:
            raise ValueError("payment_intent_id required")
        payload = {
            "payment_method": pi_data.get("payment_method_id"),
            "return_url": pi_data.get("return_url"),
        }
        await self._make_request("POST", f"/payment_intents/{payment_intent_id}/confirm", data=payload)

    async def _create_subscription(self, sub_data: Dict[str, Any]):
        payload = sub_data.get("subscription", {})
        await self._make_request("POST", "/subscriptions", data=payload)

    async def _update_subscription(self, sub_data: Dict[str, Any]):
        subscription_id = sub_data.get("subscription_id")
        if not subscription_id:
            raise ValueError("subscription_id required")
        payload = sub_data.get("subscription", {})
        await self._make_request("POST", f"/subscriptions/{subscription_id}", data=payload)

    async def _cancel_subscription(self, sub_data: Dict[str, Any]):
        subscription_id = sub_data.get("subscription_id")
        if not subscription_id:
            raise ValueError("subscription_id required")
        payload = {
            "invoice_now": sub_data.get("invoice_now", False),
            "prorate": sub_data.get("prorate", True),
        }
        await self._make_request("DELETE", f"/subscriptions/{subscription_id}", data=payload)

    async def _create_product(self, product_data: Dict[str, Any]):
        payload = product_data.get("product", {})
        await self._make_request("POST", "/products", data=payload)

    async def _update_product(self, product_data: Dict[str, Any]):
        product_id = product_data.get("product_id")
        if not product_id:
            raise ValueError("product_id required")
        payload = product_data.get("product", {})
        await self._make_request("POST", f"/products/{product_id}", data=payload)

    async def _create_price(self, price_data: Dict[str, Any]):
        payload = price_data.get("price", {})
        await self._make_request("POST", "/prices", data=payload)

    async def _create_invoice(self, invoice_data: Dict[str, Any]):
        payload = invoice_data.get("invoice", {})
        await self._make_request("POST", "/invoices", data=payload)

    async def _finalize_invoice(self, invoice_data: Dict[str, Any]):
        invoice_id = invoice_data.get("invoice_id")
        if not invoice_id:
            raise ValueError("invoice_id required")
        await self._make_request("POST", f"/invoices/{invoice_id}/finalize")

    async def _send_invoice(self, invoice_data: Dict[str, Any]):
        invoice_id = invoice_data.get("invoice_id")
        if not invoice_id:
            raise ValueError("invoice_id required")
        await self._make_request("POST", f"/invoices/{invoice_id}/send")

    async def _create_invoice_item(self, item_data: Dict[str, Any]):
        payload = item_data.get("invoice_item", {})
        await self._make_request("POST", "/invoiceitems", data=payload)

    async def _create_refund(self, refund_data: Dict[str, Any]):
        payload = refund_data.get("refund", {})
        await self._make_request("POST", "/refunds", data=payload)

    async def _update_dispute(self, dispute_data: Dict[str, Any]):
        dispute_id = dispute_data.get("dispute_id")
        if not dispute_id:
            raise ValueError("dispute_id required")
        payload = dispute_data.get("dispute", {})
        await self._make_request("POST", f"/disputes/{dispute_id}", data=payload)

    async def _create_webhook_endpoint(self, endpoint_data: Dict[str, Any]):
        payload = endpoint_data.get("webhook_endpoint", {})
        await self._make_request("POST", "/webhook_endpoints", data=payload)

    async def _delete_webhook_endpoint(self, endpoint_data: Dict[str, Any]):
        endpoint_id = endpoint_data.get("endpoint_id")
        if not endpoint_id:
            raise ValueError("endpoint_id required")
        await self._make_request("DELETE", f"/webhook_endpoints/{endpoint_id}")

    async def test_connection(self) -> bool:
        try:
            data = await self._make_request("GET", "/account")
            return "id" in data
        except Exception as e:
            logger.error(f"Stripe connection test failed: {e}")
            return False


from app.connectors.base import connector_registry
connector_registry.register(StripeConnector, StripeConnector.CONFIG)