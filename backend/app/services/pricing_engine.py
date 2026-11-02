"""Versioned Pricing Engine — Stage 5.1 Pay-As-You-Go Billing.

Implements deterministic, decimal-safe pricing with:
- Versioned pricing rules (historical repricing protection)
- Per-unit, tiered, and included-allowance pricing models
- Exact decimal arithmetic (no binary floating-point)
- Deterministic rounding behavior
- Pricing rule audit trail
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, getcontext
from typing import Any, Dict, List, Optional, Tuple, Literal
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.finance import (
    Plan,
    PricingRule,
    PricingRuleVersion,
    Subscription,
    UsageAggregation,
    CommercialAccount,
)
from app.services.audit_service import audit_service

logger = logging.getLogger("vcos.billing.pricing")

# Set decimal context for financial calculations
getcontext().prec = 28
getcontext().rounding = ROUND_HALF_UP


class PricingModel(str, Enum):
    """Supported pricing models."""
    PER_UNIT = "per_unit"           # Fixed price per unit
    TIERED = "tiered"               # Tiered pricing (volume discounts)
    INCLUDED_ALLOWANCE = "included_allowance"  # Included units + overage
    FLAT_FEE = "flat_fee"           # Flat fee regardless of usage
    PERCENTAGE = "percentage"       # Percentage of base amount


class PricingCurrency(str, Enum):
    """Supported currencies."""
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"


@dataclass
class PriceCalculation:
    """Result of a price calculation."""
    metric_code: str
    model: PricingModel
    quantity: Decimal
    unit_price: Decimal
    included_quantity: Decimal
    billable_quantity: Decimal
    subtotal: Decimal
    currency: str
    pricing_rule_version: int
    tier_breakdown: List[Dict[str, Any]]
    rounding_applied: bool


@dataclass
class InvoiceLineItem:
    """Single line item on an invoice."""
    metric_code: str
    description: str
    quantity: Decimal
    unit: str
    unit_price: Decimal
    included_quantity: Decimal
    billable_quantity: Decimal
    total_price: Decimal
    currency: str
    pricing_rule_version: int
    tier_details: Optional[List[Dict[str, Any]]] = None


class PricingEngine:
    """Deterministic pricing engine with versioned rules."""
    
    # Rounding configuration
    ROUNDING_PRECISION = Decimal("0.01")  # Round to cents
    ROUNDING_MODE = ROUND_HALF_UP
    
    def __init__(self):
        pass
    
    # =========================================================================
    # PRICE CALCULATION
    # =========================================================================
    
    async def calculate_price(
        self,
        db: AsyncSession,
        subscription_id: str,
        period: str,
        usage_quantities: Dict[str, Decimal],
        pricing_version: Optional[int] = None,
    ) -> List[PriceCalculation]:
        """
        Calculate prices for all metrics in a billing period.
        
        Args:
            db: Database session
            subscription_id: Subscription to price
            period: Billing period (YYYY-MM)
            usage_quantities: Metric code -> quantity consumed
            pricing_version: Specific pricing rule version (None = latest effective)
            
        Returns:
            List of PriceCalculation for each metric
        """
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            raise ValueError(f"Subscription not found: {subscription_id}")
        
        plan = await db.get(Plan, subscription.plan_id)
        if not plan:
            raise ValueError(f"Plan not found for subscription")
        
        # Get applicable pricing rules
        pricing_rules = await self._get_applicable_pricing_rules(
            db, plan.id, pricing_version
        )
        
        calculations = []
        
        for metric_code, quantity in usage_quantities.items():
            if quantity <= 0:
                continue
                
            rule = pricing_rules.get(metric_code)
            if not rule:
                # No pricing rule - check if it's included in plan
                plan_entitlement = plan.entitlements.get(metric_code)
                if plan_entitlement and plan_entitlement.get("included", False):
                    calculations.append(PriceCalculation(
                        metric_code=metric_code,
                        model=PricingModel.INCLUDED_ALLOWANCE,
                        quantity=quantity,
                        unit_price=Decimal("0"),
                        included_quantity=quantity,
                        billable_quantity=Decimal("0"),
                        subtotal=Decimal("0"),
                        currency=subscription.currency,
                        pricing_rule_version=0,
                        tier_breakdown=[],
                        rounding_applied=False,
                    ))
                continue
            
            calculation = await self._calculate_metric_price(
                rule=rule,
                quantity=quantity,
                plan_entitlements=plan.entitlements,
                currency=subscription.currency,
            )
            calculations.append(calculation)
        
        return calculations
    
    async def _calculate_metric_price(
        self,
        rule: "PricingRule",
        quantity: Decimal,
        plan_entitlements: Dict[str, Any],
        currency: str,
    ) -> PriceCalculation:
        """Calculate price for a single metric using its pricing rule."""
        
        # Get included allowance from plan
        plan_entitlement = plan_entitlements.get(rule.metric_code, {})
        included_quantity = Decimal(str(plan_entitlement.get("included", 0)))
        
        # Calculate billable quantity
        billable_quantity = max(Decimal("0"), quantity - included_quantity)
        
        if rule.model == PricingModel.PER_UNIT:
            return self._calculate_per_unit(rule, quantity, included_quantity, billable_quantity, currency)
        elif rule.model == PricingModel.TIERED:
            return self._calculate_tiered(rule, quantity, included_quantity, billable_quantity, currency)
        elif rule.model == PricingModel.INCLUDED_ALLOWANCE:
            return self._calculate_included_allowance(rule, quantity, included_quantity, billable_quantity, currency)
        elif rule.model == PricingModel.FLAT_FEE:
            return self._calculate_flat_fee(rule, quantity, included_quantity, billable_quantity, currency)
        elif rule.model == PricingModel.PERCENTAGE:
            return self._calculate_percentage(rule, quantity, included_quantity, billable_quantity, currency)
        else:
            raise ValueError(f"Unknown pricing model: {rule.model}")
    
    def _calculate_per_unit(
        self,
        rule: "PricingRule",
        quantity: Decimal,
        included_quantity: Decimal,
        billable_quantity: Decimal,
        currency: str,
    ) -> PriceCalculation:
        """Per-unit pricing: fixed price per billable unit."""
        unit_price = Decimal(str(rule.unit_price_cents)) / Decimal("100")
        subtotal = (billable_quantity * unit_price).quantize(self.ROUNDING_PRECISION, rounding=self.ROUNDING_MODE)
        
        return PriceCalculation(
            metric_code=rule.metric_code,
            model=PricingModel.PER_UNIT,
            quantity=quantity,
            unit_price=unit_price,
            included_quantity=included_quantity,
            billable_quantity=billable_quantity,
            subtotal=subtotal,
            currency=currency,
            pricing_rule_version=rule.version,
            tier_breakdown=[],
            rounding_applied=True,
        )
    
    def _calculate_tiered(
        self,
        rule: "PricingRule",
        quantity: Decimal,
        included_quantity: Decimal,
        billable_quantity: Decimal,
        currency: str,
    ) -> PriceCalculation:
        """Tiered pricing: volume-based price tiers."""
        tiers = rule.tiers or []
        if not tiers:
            raise ValueError("Tiered pricing requires tiers configuration")
        
        # Sort tiers by start_quantity
        sorted_tiers = sorted(tiers, key=lambda t: Decimal(str(t.get("start_quantity", 0))))
        
        remaining = billable_quantity
        subtotal = Decimal("0")
        tier_breakdown = []
        
        for tier in sorted_tiers:
            if remaining <= 0:
                break
            
            tier_start = Decimal(str(tier.get("start_quantity", 0)))
            tier_end = tier.get("end_quantity")
            tier_end = Decimal(str(tier_end)) if tier_end is not None else None
            tier_price_cents = Decimal(str(tier.get("price_cents", 0)))
            tier_unit_price = tier_price_cents / Decimal("100")
            
            # Calculate quantity in this tier
            if tier_end is not None:
                tier_max = tier_end - tier_start
                tier_quantity = min(remaining, max(Decimal("0"), tier_max))
            else:
                tier_quantity = remaining  # Unlimited tier
            
            if tier_quantity > 0:
                tier_subtotal = (tier_quantity * tier_unit_price).quantize(
                    self.ROUNDING_PRECISION, rounding=self.ROUNDING_MODE
                )
                subtotal += tier_subtotal
                remaining -= tier_quantity
                
                tier_breakdown.append({
                    "tier_start": str(tier_start),
                    "tier_end": str(tier_end) if tier_end else "unlimited",
                    "unit_price": str(tier_unit_price),
                    "quantity": str(tier_quantity),
                    "subtotal": str(tier_subtotal),
                })
        
        # Apply rounding to final subtotal
        subtotal = subtotal.quantize(self.ROUNDING_PRECISION, rounding=self.ROUNDING_MODE)
        
        return PriceCalculation(
            metric_code=rule.metric_code,
            model=PricingModel.TIERED,
            quantity=quantity,
            unit_price=Decimal("0"),  # Variable per tier
            included_quantity=included_quantity,
            billable_quantity=billable_quantity,
            subtotal=subtotal,
            currency=currency,
            pricing_rule_version=rule.version,
            tier_breakdown=tier_breakdown,
            rounding_applied=True,
        )
    
    def _calculate_included_allowance(
        self,
        rule: "PricingRule",
        quantity: Decimal,
        included_quantity: Decimal,
        billable_quantity: Decimal,
        currency: str,
    ) -> PriceCalculation:
        """Included allowance: free units up to limit, then per-unit overage."""
        overage_price_cents = Decimal(str(rule.overage_price_cents or 0))
        overage_unit_price = overage_price_cents / Decimal("100")
        
        subtotal = (billable_quantity * overage_unit_price).quantize(
            self.ROUNDING_PRECISION, rounding=self.ROUNDING_MODE
        )
        
        tier_breakdown = []
        if included_quantity > 0:
            tier_breakdown.append({
                "type": "included",
                "quantity": str(included_quantity),
                "unit_price": "0.00",
                "subtotal": "0.00",
            })
        if billable_quantity > 0:
            tier_breakdown.append({
                "type": "overage",
                "quantity": str(billable_quantity),
                "unit_price": str(overage_unit_price),
                "subtotal": str(subtotal),
            })
        
        return PriceCalculation(
            metric_code=rule.metric_code,
            model=PricingModel.INCLUDED_ALLOWANCE,
            quantity=quantity,
            unit_price=overage_unit_price,
            included_quantity=included_quantity,
            billable_quantity=billable_quantity,
            subtotal=subtotal,
            currency=currency,
            pricing_rule_version=rule.version,
            tier_breakdown=tier_breakdown,
            rounding_applied=True,
        )
    
    def _calculate_flat_fee(
        self,
        rule: "PricingRule",
        quantity: Decimal,
        included_quantity: Decimal,
        billable_quantity: Decimal,
        currency: str,
    ) -> PriceCalculation:
        """Flat fee: fixed price regardless of usage."""
        flat_price_cents = Decimal(str(rule.flat_price_cents or 0))
        unit_price = flat_price_cents / Decimal("100")
        subtotal = unit_price.quantize(self.ROUNDING_PRECISION, rounding=self.ROUNDING_MODE)
        
        return PriceCalculation(
            metric_code=rule.metric_code,
            model=PricingModel.FLAT_FEE,
            quantity=quantity,
            unit_price=unit_price,
            included_quantity=quantity,  # All included
            billable_quantity=Decimal("0"),
            subtotal=subtotal,
            currency=currency,
            pricing_rule_version=rule.version,
            tier_breakdown=[{
                "type": "flat_fee",
                "quantity": "1",
                "unit_price": str(unit_price),
                "subtotal": str(subtotal),
            }],
            rounding_applied=True,
        )
    
    def _calculate_percentage(
        self,
        rule: "PricingRule",
        quantity: Decimal,
        included_quantity: Decimal,
        billable_quantity: Decimal,
        currency: str,
    ) -> PriceCalculation:
        """Percentage pricing: percentage of a base amount."""
        # Requires a base_amount in rule config
        base_amount = Decimal(str(rule.base_amount_cents or 0)) / Decimal("100")
        percentage = Decimal(str(rule.percentage or 0)) / Decimal("100")
        
        subtotal = (base_amount * percentage).quantize(
            self.ROUNDING_PRECISION, rounding=self.ROUNDING_MODE
        )
        
        return PriceCalculation(
            metric_code=rule.metric_code,
            model=PricingModel.PERCENTAGE,
            quantity=quantity,
            unit_price=Decimal("0"),
            included_quantity=included_quantity,
            billable_quantity=Decimal("0"),
            subtotal=subtotal,
            currency=currency,
            pricing_rule_version=rule.version,
            tier_breakdown=[{
                "type": "percentage",
                "base_amount": str(base_amount),
                "percentage": str(percentage),
                "subtotal": str(subtotal),
            }],
            rounding_applied=True,
        )
    
    # =========================================================================
    # PRICING RULE MANAGEMENT
    # =========================================================================
    
    async def _get_applicable_pricing_rules(
        self,
        db: AsyncSession,
        plan_id: str,
        pricing_version: Optional[int] = None,
    ) -> Dict[str, "PricingRule"]:
        """Get pricing rules applicable to a plan."""
        query = select(PricingRule).where(
            PricingRule.plan_id == plan_id,
            PricingRule.is_active == True,
        )
        
        if pricing_version:
            query = query.where(PricingRule.version <= pricing_version)
        
        # Get latest version for each metric
        query = query.order_by(PricingRule.metric_code, PricingRule.version.desc())
        
        result = await db.execute(query)
        rules = result.scalars().all()
        
        # Deduplicate by metric_code (keep highest version)
        latest_rules = {}
        for rule in rules:
            if rule.metric_code not in latest_rules:
                latest_rules[rule.metric_code] = rule
        
        return latest_rules
    
    # =========================================================================
    # PRICING RULE CRUD
    # =========================================================================
    
    async def create_pricing_rule(
        self,
        db: AsyncSession,
        *,
        plan_id: str,
        metric_code: str,
        model: PricingModel,
        version: int,
        unit_price_cents: Optional[int] = None,
        overage_price_cents: Optional[int] = None,
        flat_price_cents: Optional[int] = None,
        base_amount_cents: Optional[int] = None,
        percentage: Optional[Decimal] = None,
        tiers: Optional[List[Dict]] = None,
        effective_from: Optional[datetime] = None,
        effective_to: Optional[datetime] = None,
        created_by: Optional[str] = None,
    ) -> "PricingRule":
        """Create a new pricing rule version."""
        # Deactivate existing rules for this metric/plan
        await db.execute(
            PricingRule.__table__.update().where(
                and_(
                    PricingRule.plan_id == plan_id,
                    PricingRule.metric_code == metric_code,
                    PricingRule.is_active == True,
                )
            ).values(is_active=False, effective_to=utcnow())
        )
        
        rule = PricingRule(
            plan_id=plan_id,
            metric_code=metric_code,
            model=model.value,
            version=version,
            unit_price_cents=unit_price_cents,
            overage_price_cents=overage_price_cents,
            flat_price_cents=flat_price_cents,
            base_amount_cents=base_amount_cents,
            percentage=percentage,
            tiers=tiers or [],
            effective_from=effective_from or utcnow(),
            effective_to=effective_to,
            is_active=True,
        )
        
        db.add(rule)
        await db.flush()
        
        # Create version record
        await self._create_version_record(db, rule, created_by=created_by)
        
        await audit_service.log(
            db,
            organization_id="system",
            action="pricing_rule.created",
            actor_id=created_by,
            resource_type="pricing_rule",
            resource_id=rule.id,
            details={"plan_id": plan_id, "metric_code": metric_code, "version": version},
        )
        
        return rule
    
    async def _create_version_record(
        self,
        db: AsyncSession,
        rule: "PricingRule",
        created_by: Optional[str] = None,
    ) -> None:
        """Create pricing rule version audit record."""
        version_record = PricingRuleVersion(
            pricing_rule_id=rule.id,
            plan_id=rule.plan_id,
            metric_code=rule.metric_code,
            model=rule.model,
            version=rule.version,
            unit_price_cents=rule.unit_price_cents,
            overage_price_cents=rule.overage_price_cents,
            flat_price_cents=rule.flat_price_cents,
            base_amount_cents=rule.base_amount_cents,
            percentage=rule.percentage,
            tiers=rule.tiers,
            effective_from=rule.effective_from,
            effective_to=rule.effective_to,
            created_by=created_by,
        )
        db.add(version_record)
        await db.flush()
    
    # =========================================================================
    # INVOICE LINE ITEM GENERATION
    # =========================================================================
    
    async def generate_invoice_lines(
        self,
        db: AsyncSession,
        subscription_id: str,
        period: str,
        usage_quantities: Dict[str, Decimal],
        pricing_version: Optional[int] = None,
    ) -> List[InvoiceLineItem]:
        """Generate invoice line items from usage quantities."""
        calculations = await self.calculate_price(
            db, subscription_id, period, usage_quantities, pricing_version
        )
        
        lines = []
        for calc in calculations:
            if calc.subtotal > 0 or calc.included_quantity > 0:
                lines.append(InvoiceLineItem(
                    metric_code=calc.metric_code,
                    description=self._get_metric_description(calc.metric_code),
                    quantity=calc.quantity,
                    unit=calc.model.value,  # Would map to actual unit
                    unit_price=calc.unit_price,
                    included_quantity=calc.included_quantity,
                    billable_quantity=calc.billable_quantity,
                    total_price=calc.subtotal,
                    currency=calc.currency,
                    pricing_rule_version=calc.pricing_rule_version,
                    tier_details=calc.tier_breakdown if calc.tier_breakdown else None,
                ))
        
        return lines
    
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
    
    # =========================================================================
    # PRICING RULE QUERIES
    # =========================================================================
    
    async def get_pricing_rules(
        self,
        db: AsyncSession,
        plan_id: str,
        metric_code: Optional[str] = None,
    ) -> List["PricingRule"]:
        """Get all pricing rules for a plan."""
        query = select(PricingRule).where(
            PricingRule.plan_id == plan_id,
            PricingRule.is_active == True,
        )
        if metric_code:
            query = query.where(PricingRule.metric_code == metric_code)
        query = query.order_by(PricingRule.metric_code, PricingRule.version.desc())
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def get_pricing_rule_history(
        self,
        db: AsyncSession,
        plan_id: str,
        metric_code: str,
    ) -> List["PricingRuleVersion"]:
        """Get full version history for a pricing rule."""
        result = await db.execute(
            select(PricingRuleVersion).where(
                PricingRuleVersion.plan_id == plan_id,
                PricingRuleVersion.metric_code == metric_code,
            ).order_by(PricingRuleVersion.version.desc())
        )
        return list(result.scalars().all())


# Global instance
pricing_engine = PricingEngine()


# Import datetime
from datetime import datetime