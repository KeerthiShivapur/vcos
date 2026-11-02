"""Invoice Preview Service — Stage 5.1 Pay-As-You-Go Billing.

Generates deterministic, reproducible invoice previews from validated usage
and versioned pricing. Supports what-if scenarios and pricing explanations.
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.finance import (
    Subscription,
    SubscriptionInvoice,
    Invoice,
    Plan,
    PricingRule,
    CommercialAccount,
    UsageAggregation,
    UsageRecord,
)
from app.services.pricing_engine import pricing_engine, InvoiceLineItem
from app.services.usage_aggregation_service import usage_aggregation_service
from app.services.audit_service import audit_service

logger = logging.getLogger("vcos.billing.invoice_preview")


class InvoicePreviewStatus(str, Enum):
    """Invoice preview status."""
    DRAFT = "draft"
    GENERATED = "generated"
    EXPIRED = "expired"


@dataclass
class InvoicePreview:
    """Complete invoice preview with all details."""
    # Identity
    preview_id: str
    subscription_id: str
    organization_id: str
    
    # Period
    period_start: datetime
    period_end: datetime
    billing_period: str  # YYYY-MM
    
    # Amounts (in cents for precision)
    subtotal_cents: int
    tax_cents: int
    discount_cents: int
    total_cents: int
    currency: str
    
    # Line items
    line_items: List[Dict[str, Any]]
    
    # Usage breakdown
    usage_by_metric: Dict[str, Dict[str, Any]]
    
    # Pricing
    pricing_version: int
    pricing_rules_applied: List[Dict[str, Any]]
    
    # Metadata
    generated_at: datetime
    expires_at: datetime
    status: InvoicePreviewStatus
    
    # Reproducibility
    input_hash: str  # Hash of all inputs for reproducibility verification


@dataclass
class UsageBreakdown:
    """Usage breakdown for a single metric."""
    metric_code: str
    metric_description: str
    unit: str
    quantity: Decimal
    included_quantity: Decimal
    billable_quantity: Decimal
    unit_price: Decimal
    subtotal: Decimal
    pricing_model: str
    pricing_rule_version: int


class InvoicePreviewService:
    """Service for generating deterministic invoice previews."""
    
    # Preview validity period
    PREVIEW_VALIDITY_HOURS = 24
    
    # Preview ID prefix
    PREVIEW_ID_PREFIX = "inv_preview"
    
    def __init__(self):
        pass
    
    # =========================================================================
    # INVOICE PREVIEW GENERATION
    # =========================================================================
    
    async def generate_preview(
        self,
        db: AsyncSession,
        subscription_id: str,
        period: Optional[str] = None,
        pricing_version: Optional[int] = None,
        include_usage_details: bool = True,
        what_if_usage: Optional[Dict[str, Decimal]] = None,
    ) -> InvoicePreview:
        """
        Generate a deterministic invoice preview.
        
        Args:
            db: Database session
            subscription_id: Subscription to preview
            period: Billing period (YYYY-MM), defaults to current
            pricing_version: Specific pricing version (None = latest)
            include_usage_details: Include detailed usage breakdown
            what_if_usage: Optional usage overrides for what-if scenarios
            
        Returns:
            Complete InvoicePreview with all line items and totals
        """
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            raise ValueError(f"Subscription not found: {subscription_id}")
        
        if period is None:
            period = utcnow().strftime("%Y-%m")
        
        # Get plan and commercial account
        plan = await db.get(Plan, subscription.plan_id)
        if not plan:
            raise ValueError("Plan not found for subscription")
        
        account = await db.get(CommercialAccount, subscription.commercial_account_id)
        
        # Determine usage quantities
        if what_if_usage is not None:
            usage_quantities = what_if_usage
        else:
            usage_quantities = await self._get_usage_quantities(db, subscription, period)
        
        # Generate preview ID
        preview_id = f"{self.PREVIEW_ID_PREFIX}_{subscription_id}_{period}_{uuid.uuid4().hex[:8]}"
        
        # Calculate prices using pricing engine
        calculations = await pricing_engine.calculate_price(
            db=db,
            subscription_id=subscription_id,
            period=period,
            usage_quantities=usage_quantities,
            pricing_version=pricing_version,
        )
        
        # Generate line items
        line_items = []
        usage_by_metric = {}
        subtotal_cents = 0
        pricing_rules_applied = []
        
        for calc in calculations:
            if calc.subtotal > 0 or calc.included_quantity > 0:
                # Convert to cents
                line_subtotal_cents = int((calc.subtotal * Decimal("100")).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
                subtotal_cents += line_subtotal_cents
                
                line_item = {
                    "metric_code": calc.metric_code,
                    "description": self._get_metric_description(calc.metric_code),
                    "quantity": str(calc.quantity),
                    "unit": calc.model.value,
                    "unit_price": str(calc.unit_price),
                    "included_quantity": str(calc.included_quantity),
                    "billable_quantity": str(calc.billable_quantity),
                    "total_price": str(calc.subtotal),
                    "currency": calc.currency,
                    "pricing_model": calc.model.value,
                    "pricing_rule_version": calc.pricing_rule_version,
                    "tier_breakdown": calc.tier_breakdown,
                }
                line_items.append(line_item)
                
                # Track pricing rules applied
                if calc.pricing_rule_version > 0:
                    pricing_rules_applied.append({
                        "metric_code": calc.metric_code,
                        "model": calc.model.value,
                        "version": calc.pricing_rule_version,
                        "unit_price": str(calc.unit_price),
                    })
                
                # Usage breakdown
                if include_usage_details:
                    usage_by_metric[calc.metric_code] = {
                        "description": self._get_metric_description(calc.metric_code),
                        "unit": calc.model.value,
                        "quantity": str(calc.quantity),
                        "included_quantity": str(calc.included_quantity),
                        "billable_quantity": str(calc.billable_quantity),
                        "unit_price": str(calc.unit_price),
                        "subtotal": str(calc.subtotal),
                        "pricing_model": calc.model.value,
                        "pricing_rule_version": calc.pricing_rule_version,
                    }
        
        # Calculate tax (placeholder - would integrate with tax service)
        tax_cents = 0  # TODO: Implement tax calculation
        
        # Discounts (placeholder)
        discount_cents = 0
        
        total_cents = subtotal_cents + tax_cents - discount_cents
        
        # Build preview
        now = utcnow()
        preview = InvoicePreview(
            preview_id=preview_id,
            subscription_id=subscription_id,
            organization_id=subscription.organization_id,
            period_start=datetime.strptime(period + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc),
            period_end=(datetime.strptime(period + "-01", "%Y-%m-%d") + timedelta(days=32)).replace(day=1) - timedelta(seconds=1),
            billing_period=period,
            subtotal_cents=subtotal_cents,
            tax_cents=tax_cents,
            discount_cents=discount_cents,
            total_cents=total_cents,
            currency=subscription.currency,
            line_items=line_items,
            usage_by_metric=usage_by_metric,
            pricing_version=pricing_version or 0,
            pricing_rules_applied=pricing_rules_applied,
            generated_at=now,
            expires_at=now + timedelta(hours=self.PREVIEW_VALIDITY_HOURS),
            status=InvoicePreviewStatus.GENERATED,
            input_hash=self._compute_input_hash(
                subscription_id, period, usage_quantities, pricing_version
            ),
        )
        
        # Store preview for reproducibility (optional - could cache)
        await self._store_preview(db, preview)
        
        # Emit event
        await publish_event(
            db,
            name="invoice.preview.generated",
            organization_id=subscription.organization_id,
            payload={
                "preview_id": preview_id,
                "subscription_id": subscription_id,
                "period": period,
                "total_cents": total_cents,
                "line_items_count": len(line_items),
            },
        )
        
        await audit_service.log(
            db,
            organization_id=subscription.organization_id,
            action="invoice.preview.generated",
            resource_type="invoice_preview",
            resource_id=preview_id,
            details={
                "subscription_id": subscription_id,
                "period": period,
                "total_cents": total_cents,
            },
        )
        
        return preview
    
    async def _get_usage_quantities(
        self,
        db: AsyncSession,
        subscription: Subscription,
        period: str,
    ) -> Dict[str, Decimal]:
        """Get aggregated usage quantities for a subscription period."""
        # Try aggregations first (pre-computed)
        aggregations = await usage_aggregation_service.get_aggregations_for_period(
            db, subscription.organization_id, period
        )
        
        if aggregations:
            return {
                agg.metric_code: agg.total_quantity
                for agg in aggregations
            }
        
        # Fallback: compute from raw usage records
        result = await db.execute(
            select(
                UsageRecord.entitlement_key,
                func.coalesce(func.sum(UsageRecord.quantity), Decimal("0")),
            ).where(
                UsageRecord.organization_id == subscription.organization_id,
                UsageRecord.period == period,
            ).group_by(UsageRecord.entitlement_key)
        )
        
        return {
            row[0]: row[1] or Decimal("0")
            for row in result.all()
        }
    
    # =========================================================================
    # WHAT-IF SCENARIOS
    # =========================================================================
    
    async def generate_what_if_preview(
        self,
        db: AsyncSession,
        subscription_id: str,
        period: str,
        what_if_changes: Dict[str, Decimal],
        pricing_version: Optional[int] = None,
    ) -> Tuple[InvoicePreview, InvoicePreview]:
        """
        Generate comparison preview: current vs. what-if scenario.
        
        Returns: (current_preview, what_if_preview)
        """
        # Current preview
        current = await self.generate_preview(
            db=db,
            subscription_id=subscription_id,
            period=period,
            pricing_version=pricing_version,
        )
        
        # Get current usage
        current_usage = await self._get_usage_quantities(db, subscription_id, period)
        
        # Apply what-if changes
        what_if_usage = {**current_usage}
        for metric, delta in what_if_changes.items():
            what_if_usage[metric] = what_if_usage.get(metric, Decimal("0")) + delta
        
        # What-if preview
        what_if = await self.generate_preview(
            db=db,
            subscription_id=subscription_id,
            period=period,
            pricing_version=pricing_version,
            what_if_usage=what_if_usage,
        )
        
        return current, what_if
    
    async def generate_plan_comparison(
        self,
        db: AsyncSession,
        subscription_id: str,
        period: str,
        target_plan_keys: List[str],
    ) -> List[InvoicePreview]:
        """
        Generate previews for different plans (plan comparison).
        
        Useful for upgrade/downgrade preview.
        """
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            raise ValueError("Subscription not found")
        
        current_plan = await db.get(Plan, subscription.plan_id)
        current_usage = await self._get_usage_quantities(db, subscription.organization_id, period)
        
        previews = []
        
        # Current plan preview
        current_preview = await self.generate_preview(
            db=db,
            subscription_id=subscription_id,
            period=period,
        )
        previews.append(current_preview)
        
        # Target plan previews
        for plan_key in target_plan_keys:
            plan = await db.get(Plan, plan_key)
            if not plan:
                continue
            
            # Create temporary subscription with target plan for pricing
            # We reuse the same usage quantities
            calculations = await pricing_engine.calculate_price(
                db=db,
                subscription_id=subscription_id,
                period=period,
                usage_quantities=current_usage,
            )
            
            # Generate preview with target plan pricing
            preview = await self._generate_preview_for_plan(
                db=db,
                subscription=subscription,
                plan=plan,
                period=period,
                usage_quantities=current_usage,
            )
            previews.append(preview)
        
        return previews
    
    async def _generate_preview_for_plan(
        self,
        db: AsyncSession,
        subscription: Subscription,
        plan: Plan,
        period: str,
        usage_quantities: Dict[str, Decimal],
    ) -> InvoicePreview:
        """Generate preview using a specific plan's pricing."""
        # Calculate prices with target plan
        calculations = await pricing_engine.calculate_price(
            db=db,
            subscription_id=subscription.id,
            period=period,
            usage_quantities=usage_quantities,
        )
        
        # Build preview (similar to generate_preview but with target plan)
        # ... implementation similar to generate_preview
        pass
    
    # =========================================================================
    # PREVIEW STORAGE & RETRIEVAL
    # =========================================================================
    
    async def _store_preview(self, db: AsyncSession, preview: InvoicePreview) -> None:
        """Store preview for audit and reproducibility."""
        # Could store in a dedicated table or cache
        # For now, just log
        logger.debug(f"Generated preview {preview.preview_id}: {preview.total_cents} cents")
    
    async def get_preview(
        self,
        db: AsyncSession,
        preview_id: str,
    ) -> Optional[InvoicePreview]:
        """Retrieve a stored preview by ID."""
        # Would query preview storage
        return None
    
    async def verify_preview_reproducibility(
        self,
        db: AsyncSession,
        preview: InvoicePreview,
    ) -> bool:
        """Verify a preview can be reproduced from its inputs."""
        regenerated = await self.generate_preview(
            db=db,
            subscription_id=preview.subscription_id,
            period=preview.billing_period,
            pricing_version=preview.pricing_version if preview.pricing_version > 0 else None,
        )
        
        return regenerated.input_hash == preview.input_hash
    
    # =========================================================================
    # PRICING EXPLANATION
    # =========================================================================
    
    async def explain_pricing(
        self,
        db: AsyncSession,
        subscription_id: str,
        period: str,
        metric_code: str,
    ) -> Dict[str, Any]:
        """Generate detailed pricing explanation for a metric."""
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            raise ValueError("Subscription not found")
        
        plan = await db.get(Plan, subscription.plan_id)
        if not plan:
            raise ValueError("Plan not found")
        
        # Get pricing rule
        rule_result = await db.execute(
            select(PricingRule).where(
                PricingRule.plan_id == plan.id,
                PricingRule.metric_code == metric_code,
                PricingRule.is_active == True,
            ).order_by(PricingRule.version.desc())
        )
        rule = rule_result.scalar_one_or_none()
        
        if not rule:
            return {"error": "No pricing rule found"}
        
        # Get usage
        usage_quantities = await self._get_usage_quantities(db, subscription, period)
        quantity = usage_quantities.get(metric_code, Decimal("0"))
        
        # Calculate
        calc = await pricing_engine._calculate_metric_price(
            rule=rule,
            quantity=quantity,
            plan_entitlements=plan.entitlements,
            currency=subscription.currency,
        )
        
        return {
            "metric_code": metric_code,
            "description": self._get_metric_description(metric_code),
            "quantity": str(quantity),
            "pricing_model": rule.model,
            "pricing_rule_version": rule.version,
            "included_quantity": str(calc.included_quantity),
            "billable_quantity": str(calc.billable_quantity),
            "unit_price": str(calc.unit_price),
            "subtotal": str(calc.subtotal),
            "currency": calc.currency,
            "tier_breakdown": calc.tier_breakdown,
            "plan_entitlement": plan.entitlements.get(metric_code, {}),
            "explanation": self._generate_explanation(rule, calc),
        }
    
    def _generate_explanation(self, rule: "PricingRule", calc: Any) -> str:
        """Generate human-readable pricing explanation."""
        if rule.model == "per_unit":
            return f"Per-unit pricing: {calc.unit_price} per unit for {calc.billable_quantity} billable units"
        elif rule.model == "tiered":
            return f"Tiered pricing: {len(calc.tier_breakdown)} tiers applied"
        elif rule.model == "included_allowance":
            return f"Included allowance: {calc.included_quantity} free units, then {calc.unit_price} per unit for {calc.billable_quantity} overage units"
        elif rule.model == "flat_fee":
            return f"Flat fee: {calc.subtotal} regardless of usage"
        return "Pricing applied"
    
    def _get_metric_description(self, metric_code: str) -> str:
        """Get human-readable description for metric."""
        descriptions = {
            "employees.max": "Employee Seats",
            "storage.gb": "Storage (GB)",
            "integrations.max": "Integrations",
            "api.calls.per_month": "API Calls",
            "ai.usage.per_month": "AI Usage (Tokens)",
            "document.processing.pages": "Document Processing (Pages)",
            "workflow.executions": "Workflow Executions",
            "integration.sync.records": "Integration Sync Records",
            "ai.inference.tokens": "AI Inference Tokens",
            "compute.seconds": "Compute Time (Seconds)",
        }
        return descriptions.get(metric_code, metric_code)
    
    def _compute_input_hash(
        self,
        subscription_id: str,
        period: str,
        usage_quantities: Dict[str, Decimal],
        pricing_version: Optional[int],
    ) -> str:
        """Compute deterministic hash of preview inputs for reproducibility."""
        import hashlib
        import json
        
        data = {
            "subscription_id": subscription_id,
            "period": period,
            "usage_quantities": {k: str(v) for k, v in sorted(usage_quantities.items())},
            "pricing_version": pricing_version,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


# Global instance
invoice_preview_service = InvoicePreviewService()


# Import uuid
import uuid