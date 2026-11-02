"""Payment Provider Abstraction — Stage 5.2 Payment + Reconciliation.

Provides a unified interface for payment providers (Stripe, Paddle, etc.)
with provider-specific implementations behind a common interface.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Literal
from enum import Enum

import httpx
import stripe

from app.core.config import get_settings
from app.models.finance import PaymentProviderConfig

logger = logging.getLogger("vcos.billing.payment_provider")


class PaymentProviderType(str, Enum):
    """Supported payment providers."""
    STRIPE = "stripe"
    PADDLE = "paddle"
    BILLING_INTERNAL = "billing_internal"
    MANUAL = "manual"


class PaymentState(str, Enum):
    """Payment lifecycle states."""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    REFUND_PENDING = "refund_pending"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"


class InvoiceState(str, Enum):
    """Invoice lifecycle states."""
    DRAFT = "draft"
    ISSUED = "issued"
    DUE = "due"
    PAID = "paid"
    PARTIALLY_PAID = "partially_paid"
    PAST_DUE = "past_due"
    VOID = "void"
    CANCELLED = "cancelled"


class PaymentMethodType(str, Enum):
    """Payment method types."""
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    ACH = "ach"
    SEPA = "sepa"
    MANUAL = "manual"


@dataclass
class PaymentIntent:
    """Payment intent for initiating a payment."""
    id: str
    amount_cents: int
    currency: str
    customer_id: str
    payment_method_id: Optional[str]
    metadata: Dict[str, Any]
    status: str
    client_secret: Optional[str] = None
    next_action: Optional[Dict[str, Any]] = None


@dataclass
class PaymentResult:
    """Result of a payment operation."""
    payment_id: str
    provider_payment_id: str
    state: PaymentState
    amount_cents: int
    currency: str
    paid_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class RefundResult:
    """Result of a refund operation."""
    refund_id: str
    provider_refund_id: str
    state: PaymentState
    amount_cents: int
    currency: str
    processed_at: Optional[datetime] = None
    failure_reason: Optional[str] = None
    metadata: Dict[str, Any] = None


@dataclass
class InvoiceData:
    """Invoice data for generation."""
    invoice_id: str
    subscription_id: str
    period_start: datetime
    period_end: datetime
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    currency: str
    line_items: List[Dict[str, Any]]
    metadata: Dict[str, Any] = None


class PaymentProvider(ABC):
    """Abstract base class for payment providers."""

    provider_type: PaymentProviderType

    @abstractmethod
    async def initialize(self, config: PaymentProviderConfig) -> bool:
        """Initialize provider with configuration."""
        pass

    @abstractmethod
    async def create_customer(
        self,
        organization_id: str,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a customer in the payment provider."""
        pass

    @abstractmethod
    async def create_payment_intent(
        self,
        customer_id: str,
        amount_cents: int,
        currency: str,
        payment_method_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> PaymentIntent:
        """Create a payment intent for a payment."""
        pass

    @abstractmethod
    async def confirm_payment_intent(
        self,
        payment_intent_id: str,
        payment_method_id: Optional[str] = None,
    ) -> PaymentResult:
        """Confirm a payment intent."""
        pass

    @abstractmethod
    async def retrieve_payment(
        self,
        payment_id: str,
    ) -> PaymentResult:
        """Retrieve payment status from provider."""
        pass

    @abstractmethod
    async def create_refund(
        self,
        payment_id: str,
        amount_cents: Optional[int] = None,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RefundResult:
        """Create a refund for a payment."""
        pass

    @abstractmethod
    async def create_invoice(
        self,
        customer_id: str,
        line_items: List[Dict[str, Any]],
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InvoiceData:
        """Create an invoice in the provider."""
        pass

    @abstractmethod
    async def finalize_invoice(self, invoice_id: str) -> InvoiceData:
        """Finalize a draft invoice."""
        pass

    @abstractmethod
    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify webhook signature from provider."""
        pass

    @abstractmethod
    async def parse_webhook_event(
        self,
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Parse and normalize webhook event from provider."""
        pass

    @abstractmethod
    async def get_customer_payment_methods(
        self,
        customer_id: str,
    ) -> List[Dict[str, Any]]:
        """Get customer's saved payment methods."""
        pass

    @abstractmethod
    async def attach_payment_method(
        self,
        customer_id: str,
        payment_method_id: str,
    ) -> bool:
        """Attach a payment method to a customer."""
        pass

    @abstractmethod
    async def detach_payment_method(self, payment_method_id: str) -> bool:
        """Detach a payment method from a customer."""
        pass

    @abstractmethod
    async def list_subscriptions(
        self,
        customer_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List customer's subscriptions."""
        pass

    @abstractmethod
    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True,
    ) -> bool:
        """Cancel a subscription."""
        pass


class StripeProvider(PaymentProvider):
    """Stripe payment provider implementation."""

    provider_type = PaymentProviderType.STRIPE

    def __init__(self):
        self.client: Optional[stripe.StripeClient] = None
        self.webhook_secret: Optional[str] = None

    async def initialize(self, config: PaymentProviderConfig) -> bool:
        """Initialize Stripe with configuration."""
        try:
            if not config.credentials_encrypted:
                logger.error("Stripe credentials not configured")
                return False

            # Decrypt credentials (simplified - real impl would decrypt)
            import json
            creds = json.loads(config.credentials_encrypted)
            
            self.client = stripe.StripeClient(creds.get("secret_key"))
            self.webhook_secret = config.webhook_secret_encrypted  # Would decrypt in real impl
            
            # Test connection
            await self._test_connection()
            
            logger.info("Stripe provider initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Stripe provider: {e}")
            return False

    async def _test_connection(self) -> bool:
        """Test Stripe connection."""
        try:
            # Simple API call to verify credentials
            await self.client.get("/v1/account")
            return True
        except Exception as e:
            logger.error(f"Stripe connection test failed: {e}")
            return False

    async def create_customer(
        self,
        organization_id: str,
        email: str,
        name: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Create a Stripe customer."""
        try:
            customer = await self.client.post(
                "/v1/customers",
                data={
                    "email": email,
                    "name": name,
                    "metadata": {
                        "vcos_organization_id": organization_id,
                        **(metadata or {}),
                    },
                },
            )
            return customer.id
        except stripe.StripeError as e:
            logger.error(f"Failed to create Stripe customer: {e}")
            raise

    async def create_payment_intent(
        self,
        customer_id: str,
        amount_cents: int,
        currency: str,
        payment_method_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
    ) -> PaymentIntent:
        """Create a Stripe PaymentIntent."""
        try:
            data = {
                "customer": customer_id,
                "amount": amount_cents,
                "currency": currency.lower(),
                "automatic_payment_methods": {"enabled": True},
                "metadata": metadata or {},
            }
            
            if payment_method_id:
                data["payment_method"] = payment_method_id
                data["off_session"] = False
                data["confirm"] = True

            headers = {}
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key

            pi = await self.client.post(
                "/v1/payment_intents",
                data=data,
                headers=headers,
            )
            
            return PaymentIntent(
                id=pi.id,
                amount_cents=pi.amount,
                currency=pi.currency,
                customer_id=pi.customer,
                payment_method_id=pi.payment_method,
                metadata=pi.metadata,
                status=pi.status,
                client_secret=pi.client_secret,
                next_action=pi.next_action,
            )
        except stripe.StripeError as e:
            logger.error(f"Failed to create PaymentIntent: {e}")
            raise

    async def confirm_payment_intent(
        self,
        payment_intent_id: str,
        payment_method_id: Optional[str] = None,
    ) -> PaymentResult:
        """Confirm a PaymentIntent."""
        try:
            data = {}
            if payment_method_id:
                data["payment_method"] = payment_method_id
            
            pi = await self.client.post(
                f"/v1/payment_intents/{payment_intent_id}/confirm",
                data=data,
            )
            
            return self._parse_payment_intent(pi)
        except stripe.StripeError as e:
            logger.error(f"Failed to confirm PaymentIntent: {e}")
            return PaymentResult(
                payment_id=payment_intent_id,
                provider_payment_id=payment_intent_id,
                state=PaymentState.FAILED,
                amount_cents=0,
                currency="usd",
                failure_reason=str(e),
            )

    async def retrieve_payment(self, payment_id: str) -> PaymentResult:
        """Retrieve payment status from Stripe."""
        try:
            # Try as PaymentIntent first
            try:
                pi = await self.client.get(f"/v1/payment_intents/{payment_id}")
                return self._parse_payment_intent(pi)
            except stripe.StripeError:
                pass
            
            # Try as Charge
            try:
                charge = await self.client.get(f"/v1/charges/{payment_id}")
                return self._parse_charge(charge)
            except stripe.StripeError:
                pass
            
            return PaymentResult(
                payment_id=payment_id,
                provider_payment_id=payment_id,
                state=PaymentState.UNKNOWN,
                amount_cents=0,
                currency="usd",
                failure_reason="Payment not found",
            )
        except stripe.StripeError as e:
            logger.error(f"Failed to retrieve payment: {e}")
            return PaymentResult(
                payment_id=payment_id,
                provider_payment_id=payment_id,
                state=PaymentState.FAILED,
                amount_cents=0,
                currency="usd",
                failure_reason=str(e),
            )

    def _parse_payment_intent(self, pi) -> PaymentResult:
        """Parse Stripe PaymentIntent to PaymentResult."""
        state_map = {
            "requires_payment_method": PaymentState.PENDING,
            "requires_confirmation": PaymentState.PROCESSING,
            "requires_action": PaymentState.PROCESSING,
            "processing": PaymentState.PROCESSING,
            "requires_capture": PaymentState.PROCESSING,
            "canceled": PaymentState.FAILED,
            "succeeded": PaymentState.SUCCEEDED,
        }
        
        return PaymentResult(
            payment_id=pi.id,
            provider_payment_id=pi.id,
            state=state_map.get(pi.status, PaymentState.UNKNOWN),
            amount_cents=pi.amount,
            currency=pi.currency,
            paid_at=datetime.fromtimestamp(pi.charges.data[0].created, tz=timezone.utc) if pi.charges.data else None,
            failure_reason=pi.last_payment_error.message if pi.last_payment_error else None,
            metadata=pi.metadata,
        )

    def _parse_charge(self, charge) -> PaymentResult:
        """Parse Stripe Charge to PaymentResult."""
        state_map = {
            "succeeded": PaymentState.SUCCEEDED,
            "pending": PaymentState.PROCESSING,
            "failed": PaymentState.FAILED,
        }
        
        return PaymentResult(
            payment_id=charge.id,
            provider_payment_id=charge.payment_intent or charge.id,
            state=state_map.get(charge.status, PaymentState.UNKNOWN),
            amount_cents=charge.amount,
            currency=charge.currency,
            paid_at=datetime.fromtimestamp(charge.created, tz=timezone.utc) if charge.created else None,
            failure_reason=charge.failure_message,
            metadata=charge.metadata,
        )

    async def create_refund(
        self,
        payment_id: str,
        amount_cents: Optional[int] = None,
        reason: Optional[str] = None,
        idempotency_key: Optional[str] = None,
    ) -> RefundResult:
        """Create a refund in Stripe."""
        try:
            headers = {}
            if idempotency_key:
                headers["Idempotency-Key"] = idempotency_key

            data = {
                "payment_intent": payment_id,
            }
            if amount_cents:
                data["amount"] = amount_cents
            if reason:
                data["reason"] = reason

            refund = await self.client.post(
                "/v1/refunds",
                data=data,
                headers=headers,
            )

            return RefundResult(
                refund_id=refund.id,
                provider_refund_id=refund.id,
                state=PaymentState.SUCCEEDED if refund.status == "succeeded" else PaymentState.REFUND_PENDING,
                amount_cents=refund.amount,
                currency=refund.currency,
                processed_at=datetime.fromtimestamp(refund.created, tz=timezone.utc) if refund.created else None,
                failure_reason=refund.failure_reason,
                metadata=refund.metadata,
            )
        except stripe.StripeError as e:
            logger.error(f"Failed to create refund: {e}")
            return RefundResult(
                refund_id="",
                provider_refund_id="",
                state=PaymentState.FAILED,
                amount_cents=0,
                currency="usd",
                failure_reason=str(e),
            )

    async def create_invoice(
        self,
        customer_id: str,
        line_items: List[Dict[str, Any]],
        currency: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> InvoiceData:
        """Create a Stripe invoice."""
        try:
            invoice = await self.client.post(
                "/v1/invoices",
                data={
                    "customer": customer_id,
                    "currency": currency.lower(),
                    "metadata": metadata or {},
                },
            )

            # Add line items
            for item in line_items:
                await self.client.post(
                    f"/v1/invoiceitems",
                    data={
                        "customer": customer_id,
                        "invoice": invoice.id,
                        "amount": item.get("amount_cents", 0),
                        "currency": currency.lower(),
                        "description": item.get("description", ""),
                        "quantity": item.get("quantity", 1),
                    },
                )

            return InvoiceData(
                invoice_id=invoice.id,
                subscription_id=metadata.get("subscription_id", "") if metadata else "",
                period_start=datetime.now(timezone.utc),
                period_end=datetime.now(timezone.utc),
                subtotal_cents=0,  # Would calculate from line items
                tax_cents=0,
                total_cents=0,
                currency=currency,
                line_items=line_items,
                metadata=metadata or {},
            )
        except stripe.StripeError as e:
            logger.error(f"Failed to create Stripe invoice: {e}")
            raise

    async def finalize_invoice(self, invoice_id: str) -> InvoiceData:
        """Finalize a Stripe invoice."""
        try:
            invoice = await self.client.post(
                f"/v1/invoices/{invoice_id}/finalize",
            )
            return InvoiceData(
                invoice_id=invoice.id,
                subscription_id="",
                period_start=datetime.now(timezone.utc),
                period_end=datetime.now(timezone.utc),
                subtotal_cents=invoice.subtotal,
                tax_cents=invoice.tax or 0,
                total_cents=invoice.total,
                currency=invoice.currency,
                line_items=[],  # Would populate from invoice lines
            )
        except stripe.StripeError as e:
            logger.error(f"Failed to finalize Stripe invoice: {e}")
            raise

    async def verify_webhook_signature(
        self,
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify Stripe webhook signature."""
        try:
            stripe.Webhook.construct_event(payload, signature, secret)
            return True
        except stripe.SignatureVerificationError:
            return False

    async def parse_webhook_event(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Parse and normalize Stripe webhook event."""
        event_type = payload.get("type", "")
        data = payload.get("data", {}).get("object", {})
        
        return {
            "event_type": event_type,
            "event_id": payload.get("id"),
            "data": data,
            "created": datetime.fromtimestamp(payload.get("created", 0), tz=timezone.utc),
        }

    async def get_customer_payment_methods(
        self,
        customer_id: str,
    ) -> List[Dict[str, Any]]:
        """Get customer's saved payment methods."""
        try:
            methods = await self.client.get(
                f"/v1/payment_methods",
                params={"customer": customer_id, "type": "card"},
            )
            return [
                {
                    "id": pm.id,
                    "type": pm.type,
                    "card": {
                        "brand": pm.card.brand,
                        "last4": pm.card.last4,
                        "exp_month": pm.card.exp_month,
                        "exp_year": pm.card.exp_year,
                    } if pm.card else None,
                }
                for pm in methods.data
            ]
        except stripe.StripeError as e:
            logger.error(f"Failed to get payment methods: {e}")
            return []

    async def attach_payment_method(
        self,
        customer_id: str,
        payment_method_id: str,
    ) -> bool:
        """Attach a payment method to a customer."""
        try:
            await self.client.post(
                f"/v1/payment_methods/{payment_method_id}/attach",
                data={"customer": customer_id},
            )
            return True
        except stripe.StripeError as e:
            logger.error(f"Failed to attach payment method: {e}")
            return False

    async def detach_payment_method(self, payment_method_id: str) -> bool:
        """Detach a payment method from a customer."""
        try:
            await self.client.post(
                f"/v1/payment_methods/{payment_method_id}/detach",
            )
            return True
        except stripe.StripeError as e:
            logger.error(f"Failed to detach payment method: {e}")
            return False

    async def list_subscriptions(
        self,
        customer_id: str,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List customer's subscriptions."""
        try:
            params = {"customer": customer_id}
            if status:
                params["status"] = status
            
            subs = await self.client.get("/v1/subscriptions", params=params)
            return [
                {
                    "id": sub.id,
                    "status": sub.status,
                    "current_period_start": sub.current_period_start,
                    "current_period_end": sub.current_period_end,
                    "cancel_at_period_end": sub.cancel_at_period_end,
                    "canceled_at": sub.canceled_at,
                }
                for sub in subs.data
            ]
        except stripe.StripeError as e:
            logger.error(f"Failed to list subscriptions: {e}")
            return []

    async def cancel_subscription(
        self,
        subscription_id: str,
        at_period_end: bool = True,
    ) -> bool:
        """Cancel a Stripe subscription."""
        try:
            if at_period_end:
                await self.client.post(
                    f"/v1/subscriptions/{subscription_id}",
                    data={"cancel_at_period_end": True},
                )
            else:
                await self.client.delete(f"/v1/subscriptions/{subscription_id}")
            return True
        except stripe.StripeError as e:
            logger.error(f"Failed to cancel subscription: {e}")
            return False


class PaymentProviderFactory:
    """Factory for creating payment provider instances."""

    _providers: Dict[PaymentProviderType, type] = {
        PaymentProviderType.STRIPE: StripeProvider,
        # PaymentProviderType.PADDLE: PaddleProvider,  # TODO
        # PaymentProviderType.BILLING_INTERNAL: InternalProvider,  # TODO
    }

    @classmethod
    def register_provider(cls, provider_type: PaymentProviderType, provider_class: type):
        """Register a new payment provider."""
        cls._providers[provider_type] = provider_class

    @classmethod
    def create_provider(cls, provider_type: PaymentProviderType) -> Optional[PaymentProvider]:
        """Create a payment provider instance."""
        provider_class = cls._providers.get(provider_type)
        if not provider_class:
            logger.error(f"Unknown payment provider: {provider_type}")
            return None
        return provider_class()

    @classmethod
    async def create_from_config(cls, config: PaymentProviderConfig) -> Optional[PaymentProvider]:
        """Create and initialize provider from config."""
        provider = cls.create_provider(config.provider)
        if not provider:
            return None
        
        if not await provider.initialize(config):
            return None
        
        return provider


# Global factory instance
payment_provider_factory = PaymentProviderFactory()