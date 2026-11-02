"""Billing Reconciliation Service — Stage 5.1 Pay-As-You-Go Billing.

Implements internal reconciliation between all billing pipeline stages:
- Usage records ↔ Aggregations
- Aggregations ↔ Pricing calculations
- Pricing calculations ↔ Invoice previews
- Invoice previews ↔ Adjustments
- Detects and reports discrepancies with evidence
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum

from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.finance import (
    UsageRecord,
    UsageAggregation,
    SubscriptionInvoice,
    Invoice,
    SubscriptionPayment,
    Subscription,
    Plan,
    PricingRule,
    CommercialAccount,
    Entitlement,
)
from app.services.audit_service import audit_service

logger = logging.getLogger("vcos.billing.reconciliation")


class DiscrepancyType(str, Enum):
    """Types of reconciliation discrepancies."""
    MISSING_USAGE = "missing_usage"
    DUPLICATE_USAGE = "duplicate_usage"
    AGGREGATION_MISMATCH = "aggregation_mismatch"
    PRICING_VERSION_MISMATCH = "pricing_version_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"
    UNEXPLAINED_TOTAL = "unexplained_total"
    ORPHANED_USAGE = "orphaned_usage"
    DUPLICATE_INVOICE_LINE = "duplicate_invoice_line"
    MISSING_INVOICE = "missing_invoice"
    PAYMENT_MISMATCH = "payment_mismatch"
    ENTITLEMENT_DRIFT = "entitlement_drift"
    SUBSCRIPTION_STATE_DRIFT = "subscription_state_drift"


class DiscrepancySeverity(str, Enum):
    """Severity of discrepancy."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class ReconciliationState(str, Enum):
    """Reconciliation run state."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Discrepancy:
    """A single reconciliation discrepancy."""
    discrepancy_type: DiscrepancyType
    severity: DiscrepancySeverity
    organization_id: str
    subscription_id: Optional[str]
    period: str
    metric_code: Optional[str]
    description: str
    expected_value: Optional[Any]
    actual_value: Optional[Any]
    difference: Optional[Any]
    evidence: Dict[str, Any]
    detected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    # Resolution tracking
    resolved: bool = False
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolution_notes: Optional[str] = None


@dataclass
class ReconciliationResult:
    """Result of a reconciliation run."""
    organization_id: str
    period: str
    subscription_id: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime]
    state: ReconciliationState
    discrepancies: List[Discrepancy]
    total_records_checked: int
    summary: Dict[str, int]


class ReconciliationService:
    """Service for billing pipeline reconciliation."""
    
    # Tolerance for floating-point comparisons
    TOLERANCE = Decimal("0.01")  # 1 cent
    
    def __init__(self):
        pass
    
    # =========================================================================
    # FULL RECONCILIATION
    # =========================================================================
    
    async def reconcile_period(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
        subscription_id: Optional[str] = None,
    ) -> ReconciliationResult:
        """
        Run full reconciliation for a billing period.
        
        Checks all pipeline stages for consistency.
        """
        started_at = datetime.now(timezone.utc)
        discrepancies = []
        total_checked = 0
        
        # Get subscriptions to reconcile
        if subscription_id:
            subscriptions = [await db.get(Subscription, subscription_id)]
            subscriptions = [s for s in subscriptions if s]
        else:
            subs_result = await db.execute(
                select(Subscription).where(
                    Subscription.organization_id == organization_id,
                    Subscription.state.in_(["trialing", "active", "past_due", "grace"]),
                )
            )
            subscriptions = list(subs_result.scalars().all())
        
        for subscription in subscriptions:
            sub_discrepancies, checked = await self._reconcile_subscription(
                db, subscription, period
            )
            discrepancies.extend(sub_discrepancies)
            total_checked += checked
        
        # Cross-subscription checks
        cross_discrepancies, cross_checked = await self._reconcile_cross_subscription(
            db, organization_id, period
        )
        discrepancies.extend(cross_discrepancies)
        total_checked += cross_checked
        
        completed_at = datetime.now(timezone.utc)
        state = ReconciliationState.COMPLETED if not any(
            d.severity in (DiscrepancySeverity.ERROR, DiscrepancySeverity.CRITICAL) 
            for d in discrepancies
        ) else ReconciliationState.FAILED
        
        # Summary
        summary = {
            "total_discrepancies": len(discrepancies),
            "critical": sum(1 for d in discrepancies if d.severity == DiscrepancySeverity.CRITICAL),
            "error": sum(1 for d in discrepancies if d.severity == DiscrepancySeverity.ERROR),
            "warning": sum(1 for d in discrepancies if d.severity == DiscrepancySeverity.WARNING),
            "info": sum(1 for d in discrepancies if d.severity == DiscrepancySeverity.INFO),
            "by_type": {},
        }
        
        for d in discrepancies:
            summary["by_type"][d.discrepancy_type.value] = \
                summary["by_type"].get(d.discrepancy_type.value, 0) + 1
        
        result = ReconciliationResult(
            organization_id=organization_id,
            period=period,
            subscription_id=subscription_id,
            started_at=started_at,
            completed_at=completed_at,
            state=ReconciliationState.COMPLETED if not any(
                d.severity in (DiscrepancySeverity.ERROR, DiscrepancySeverity.CRITICAL) 
                for d in discrepancies
            ) else ReconciliationState.FAILED,
            discrepancies=discrepancies,
            total_records_checked=total_checked,
            summary=summary,
        )
        
        # Emit event
        await publish_event(
            db,
            name="billing.reconciliation.completed",
            organization_id=organization_id,
            payload={
                "period": period,
                "subscription_id": subscription_id,
                "state": state.value,
                "discrepancies_found": len(discrepancies),
                "summary": summary,
            },
        )
        
        return result
    
    async def _reconcile_subscription(
        self,
        db: AsyncSession,
        subscription: Subscription,
        period: str,
    ) -> Tuple[List[Discrepancy], int]:
        """Reconcile a single subscription for a period."""
        discrepancies = []
        checked = 0
        
        org_id = subscription.organization_id
        
        # 1. Usage Records ↔ Aggregations
        usage_discrepancies, usage_checked = await self._reconcile_usage_aggregation(
            db, org_id, subscription.id, period
        )
        discrepancies.extend(usage_discrepancies)
        checked += usage_checked
        
        # 2. Aggregations ↔ Pricing
        pricing_discrepancies, pricing_checked = await self._reconcile_aggregation_pricing(
            db, org_id, subscription.id, period
        )
        discrepancies.extend(pricing_discrepancies)
        checked += pricing_checked
        
        # 3. Pricing ↔ Invoice Preview
        invoice_discrepancies, invoice_checked = await self._reconcile_pricing_invoice(
            db, org_id, subscription.id, period
        )
        discrepancies.extend(invoice_discrepancies)
        checked += invoice_checked
        
        # 4. Invoice ↔ Payments
        payment_discrepancies, payment_checked = await self._reconcile_invoice_payments(
            db, org_id, subscription.id, period
        )
        discrepancies.extend(payment_discrepancies)
        checked += payment_checked
        
        # 5. Entitlement consistency
        entitlement_discrepancies, entitlement_checked = await self._reconcile_entitlements(
            db, org_id, subscription.id, period
        )
        discrepancies.extend(entitlement_discrepancies)
        checked += entitlement_checked
        
        # 6. Subscription state consistency
        state_discrepancies, state_checked = await self._reconcile_subscription_state(
            db, org_id, subscription.id, period
        )
        discrepancies.extend(state_discrepancies)
        checked += state_checked
        
        return discrepancies, checked
    
    # =========================================================================
    # STAGE 1: USAGE RECORDS ↔ AGGREGATIONS
    # =========================================================================
    
    async def _reconcile_usage_aggregation(
        self,
        db: AsyncSession,
        organization_id: str,
        subscription_id: str,
        period: str,
    ) -> Tuple[List[Discrepancy], int]:
        """Reconcile raw usage records with aggregations."""
        discrepancies = []
        checked = 0
        
        # Get all metrics for this period
        agg_result = await db.execute(
            select(UsageAggregation).where(
                UsageAggregation.organization_id == organization_id,
                UsageAggregation.period == period,
            )
        )
        aggregations = list(agg_result.scalars().all())
        
        for agg in aggregations:
            checked += 1
            
            # Get raw usage total
            usage_result = await db.execute(
                select(func.coalesce(func.sum(UsageRecord.quantity), Decimal("0"))).where(
                    UsageRecord.organization_id == organization_id,
                    UsageRecord.entitlement_key == agg.metric_code,
                    UsageRecord.period == period,
                )
            )
            raw_total = usage_result.scalar() or Decimal("0")
            
            # Compare
            if abs(agg.total_quantity - raw_total) > self.TOLERANCE:
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.AGGREGATION_MISMATCH,
                    severity=DiscrepancySeverity.ERROR,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=agg.metric_code,
                    description=(
                        f"Aggregation total ({agg.total_quantity}) != "
                        f"raw usage sum ({raw_total})"
                    ),
                    expected_value=str(raw_total),
                    actual_value=str(agg.total_quantity),
                    difference=str(abs(agg.total_quantity - raw_total)),
                    evidence={
                        "aggregation_id": agg.id,
                        "aggregation_version": agg.version,
                        "record_count": agg.record_count,
                    },
                ))
            
            # Check record count
            count_result = await db.execute(
                select(func.count(UsageRecord.id)).where(
                    UsageRecord.organization_id == organization_id,
                    UsageRecord.entitlement_key == agg.metric_code,
                    UsageRecord.period == period,
                )
            )
            raw_count = count_result.scalar() or 0
            
            if agg.record_count != raw_count:
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.AGGREGATION_MISMATCH,
                    severity=DiscrepancySeverity.WARNING,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=agg.metric_code,
                    description=(
                        f"Aggregation record count ({agg.record_count}) != "
                        f"raw record count ({raw_count})"
                    ),
                    expected_value=raw_count,
                    actual_value=agg.record_count,
                    difference=abs(agg.record_count - raw_count),
                    evidence={
                        "aggregation_id": agg.id,
                    },
                ))
        
        # Check for orphaned usage (usage without aggregation)
        usage_metrics = await db.execute(
            select(UsageRecord.entitlement_key).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.period == period,
            ).distinct()
        )
        usage_metric_codes = {row[0] for row in usage_metrics.all()}
        agg_metric_codes = {agg.metric_code for agg in aggregations}
        
        for metric in usage_metric_codes - agg_metric_codes:
            discrepancies.append(Discrepancy(
                discrepancy_type=DiscrepancyType.ORPHANED_USAGE,
                severity=DiscrepancySeverity.WARNING,
                organization_id=organization_id,
                subscription_id=subscription_id,
                period=period,
                metric_code=metric,
                description=f"Usage records exist for {metric} but no aggregation found",
                expected_value=None,
                actual_value=metric,
                evidence={"metric_code": metric},
            ))
        
        return discrepancies, checked
    
    # =========================================================================
    # STAGE 2: AGGREGATIONS ↔ PRICING
    # =========================================================================
    
    async def _reconcile_aggregation_pricing(
        self,
        db: AsyncSession,
        organization_id: str,
        subscription_id: str,
        period: str,
    ) -> Tuple[List[Discrepancy], int]:
        """Reconcile aggregations with pricing calculations."""
        discrepancies = []
        checked = 0
        
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return discrepancies, checked
        
        # Get aggregations
        agg_result = await db.execute(
            select(UsageAggregation).where(
                UsageAggregation.organization_id == organization_id,
                UsageAggregation.period == period,
            )
        )
        aggregations = list(agg_result.scalars().all())
        
        for agg in aggregations:
            checked += 1
            
            # Get pricing rule for this metric
            plan = await db.get(Plan, subscription.plan_id)
            if not plan:
                continue
            
            rule_result = await db.execute(
                select(PricingRule).where(
                    PricingRule.plan_id == plan.id,
                    PricingRule.metric_code == agg.metric_code,
                    PricingRule.is_active == True,
                ).order_by(PricingRule.version.desc())
            )
            rule = rule_result.scalar_one_or_none()
            
            if not rule:
                # No pricing rule - check if metric should be free
                plan_entitlement = plan.entitlements.get(agg.metric_code, {})
                if not plan_entitlement.get("included", False):
                    discrepancies.append(Discrepancy(
                        discrepancy_type=DiscrepancyType.PRICING_VERSION_MISMATCH,
                        severity=DiscrepancySeverity.WARNING,
                        organization_id=organization_id,
                        subscription_id=subscription_id,
                        period=period,
                        metric_code=agg.metric_code,
                        description=f"Metric {agg.metric_code} has usage but no pricing rule",
                        evidence={"aggregation_id": agg.id, "plan_id": plan.id},
                    ))
                continue
            
            # Check pricing version consistency
            # (Would need a pricing_version field on aggregation to fully verify)
            # For now, just verify rule is compatible with aggregation type
            if rule.model == "per_unit" and agg.aggregation_type != "sum":
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.PRICING_VERSION_MISMATCH,
                    severity=DiscrepancySeverity.INFO,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=agg.metric_code,
                    description=f"Pricing model 'per_unit' expects sum aggregation, got {agg.aggregation_type}",
                    evidence={
                        "aggregation_type": agg.aggregation_type,
                        "pricing_model": rule.model,
                    },
                ))
        
        return discrepancies, checked
    
    # =========================================================================
    # STAGE 3: PRICING ↔ INVOICE PREVIEW
    # =========================================================================
    
    async def _reconcile_pricing_invoice(
        self,
        db: AsyncSession,
        organization_id: str,
        subscription_id: str,
        period: str,
    ) -> Tuple[List[Discrepancy], int]:
        """Reconcile pricing calculations with invoice preview/lines."""
        discrepancies = []
        checked = 0
        
        # Get subscription invoices for this period
        inv_result = await db.execute(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.subscription_id == subscription_id,
                SubscriptionInvoice.period_start >= datetime.strptime(period + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc),
                SubscriptionInvoice.period_start < (datetime.strptime(period + "-01", "%Y-%m-%d") + timedelta(days=32)).replace(day=1, tzinfo=timezone.utc),
            )
        )
        sub_invoices = list(inv_result.scalars().all())
        
        if not sub_invoices:
            # No invoice yet - may be expected for trials
            subscription = await db.get(Subscription, subscription_id)
            if subscription and subscription.state == "trialing":
                return discrepancies, checked
            discrepancies.append(Discrepancy(
                discrepancy_type=DiscrepancyType.MISSING_INVOICE,
                severity=DiscrepancySeverity.WARNING,
                organization_id=organization_id,
                subscription_id=subscription_id,
                period=period,
                metric_code=None,
                description=f"No invoice found for period {period}",
                evidence={"subscription_id": subscription_id},
            ))
            return discrepancies, checked
        
        for sub_inv in sub_invoices:
            checked += 1
            
            # Get full invoice
            invoice = await db.get(Invoice, sub_inv.invoice_id)
            if not invoice:
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.MISSING_INVOICE,
                    severity=DiscrepancySeverity.ERROR,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=None,
                    description=f"Invoice {sub_inv.invoice_id} referenced but not found",
                    evidence={"subscription_invoice_id": sub_inv.id},
                ))
                continue
            
            # Verify amounts match
            expected_total = sub_inv.total_cents
            actual_total = int(invoice.amount * 100)
            
            if expected_total != actual_total:
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.UNEXPLAINED_TOTAL,
                    severity=DiscrepancySeverity.ERROR,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=None,
                    description=(
                        f"SubscriptionInvoice total ({expected_total} cents) != "
                        f"Invoice amount ({actual_total} cents)"
                    ),
                    expected_value=expected_total,
                    actual_value=actual_total,
                    difference=abs(expected_total - actual_total),
                    evidence={
                        "subscription_invoice_id": sub_inv.id,
                        "invoice_id": invoice.id,
                    },
                ))
            
            # Verify line items
            for line_item in sub_inv.line_items:
                checked += 1
                metric = line_item.get("metric_code")
                line_total = line_item.get("total_cents", 0)
                
                # Verify line item total = quantity * unit_price
                qty = Decimal(str(line_item.get("quantity", 0)))
                unit_price = Decimal(str(line_item.get("unit_price", 0)))
                expected_line_total = int((qty * unit_price * Decimal("100")).quantize(Decimal("1")))
                
                if line_total != expected_line_total:
                    discrepancies.append(Discrepancy(
                        discrepancy_type=DiscrepancyType.UNEXPLAINED_TOTAL,
                        severity=DiscrepancySeverity.ERROR,
                        organization_id=organization_id,
                        subscription_id=subscription_id,
                        period=period,
                        metric_code=metric,
                        description=f"Line item total mismatch for {metric}",
                        expected_value=expected_line_total,
                        actual_value=line_total,
                        difference=abs(line_total - expected_line_total),
                        evidence={"line_item": line_item},
                    ))
        
        return discrepancies, checked
    
    # =========================================================================
    # STAGE 4: INVOICE ↔ PAYMENTS
    # =========================================================================
    
    async def _reconcile_invoice_payments(
        self,
        db: AsyncSession,
        organization_id: str,
        subscription_id: str,
        period: str,
    ) -> Tuple[List[Discrepancy], int]:
        """Reconcile invoices with payments."""
        discrepancies = []
        checked = 0
        
        sub_inv_result = await db.execute(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.subscription_id == subscription_id,
            )
        )
        sub_invoices = list(sub_inv_result.scalars().all())
        
        for sub_inv in sub_invoices:
            checked += 1
            
            invoice = await db.get(Invoice, sub_inv.invoice_id)
            if not invoice:
                continue
            
            # Get payments for this invoice
            payment_result = await db.execute(
                select(func.coalesce(func.sum(Payment.amount), Decimal("0"))).where(
                    Payment.invoice_id == invoice.id,
                    Payment.status == "completed",
                )
            )
            total_paid = payment_result.scalar() or Decimal("0")
            
            invoice_amount = invoice.amount
            
            if total_paid > invoice_amount + self.TOLERANCE:
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.PAYMENT_MISMATCH,
                    severity=DiscrepancySeverity.ERROR,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=None,
                    description=f"Overpayment: paid {total_paid} > invoice {invoice_amount}",
                    expected_value=str(invoice_amount),
                    actual_value=str(total_paid),
                    difference=str(total_paid - invoice_amount),
                    evidence={
                        "invoice_id": invoice.id,
                        "subscription_invoice_id": sub_inv.id,
                    },
                ))
            elif total_paid < invoice_amount - self.TOLERANCE and invoice.status in ("paid", "partially_paid"):
                # Underpaid but marked paid
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.PAYMENT_MISMATCH,
                    severity=DiscrepancySeverity.WARNING,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=None,
                    description=f"Invoice marked paid but underpaid: {total_paid} < {invoice_amount}",
                    expected_value=str(invoice_amount),
                    actual_value=str(total_paid),
                    difference=str(invoice_amount - total_paid),
                    evidence={
                        "invoice_id": invoice.id,
                        "invoice_status": invoice.status,
                    },
                ))
        
        return discrepancies, checked
    
    # =========================================================================
    # STAGE 5: ENTITLEMENT CONSISTENCY
    # =========================================================================
    
    async def _reconcile_entitlements(
        self,
        db: AsyncSession,
        organization_id: str,
        subscription_id: str,
        period: str,
    ) -> Tuple[List[Discrepancy], int]:
        """Reconcile entitlements with plan and subscription."""
        discrepancies = []
        checked = 0
        
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return discrepancies, checked
        
        plan = await db.get(Plan, subscription.plan_id)
        if not plan:
            return discrepancies, checked
        
        # Get effective entitlements
        from app.services.commercial_service import commercial_service
        effective_entitlements = await commercial_service.resolve_entitlements(db, organization_id)
        
        # Check each plan entitlement is reflected
        for metric_code, plan_entitlement in plan.entitlements.items():
            checked += 1
            
            effective = effective_entitlements.get(metric_code)
            
            if not effective:
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.ENTITLEMENT_DRIFT,
                    severity=DiscrepancySeverity.WARNING,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=metric_code,
                    description=f"Plan entitlement {metric_code} not reflected in effective entitlements",
                    expected_value=plan_entitlement,
                    actual_value=None,
                    evidence={"plan_id": plan.id},
                ))
                continue
            
            # Compare values
            plan_value = plan_entitlement.get("value")
            effective_value = effective.get("value")
            
            if plan_value is not None and effective_value is not None:
                plan_val = Decimal(str(plan_value))
                eff_val = Decimal(str(effective_value))
                
                if plan_val != eff_val:
                    # Check if override explains difference
                    override = await db.execute(
                        select(Entitlement).where(
                            Entitlement.organization_id == organization_id,
                            Entitlement.key == metric_code,
                            Entitlement.source.in_(["override", "addon", "promo"]),
                        )
                    )
                    if not override.scalar_one_or_none():
                        discrepancies.append(Discrepancy(
                            discrepancy_type=DiscrepancyType.ENTITLEMENT_DRIFT,
                            severity=DiscrepancySeverity.WARNING,
                            organization_id=organization_id,
                            subscription_id=subscription_id,
                            period=period,
                            metric_code=metric_code,
                            description=f"Effective entitlement differs from plan without override",
                            expected_value=str(plan_val),
                            actual_value=str(eff_val),
                            difference=str(abs(plan_val - eff_val)),
                            evidence={
                                "plan_entitlement": plan_entitlement,
                                "effective_entitlement": effective,
                            },
                        ))
        
        return discrepancies, checked
    
    # =========================================================================
    # STAGE 6: SUBSCRIPTION STATE CONSISTENCY
    # =========================================================================
    
    async def _reconcile_subscription_state(
        self,
        db: AsyncSession,
        organization_id: str,
        subscription_id: str,
        period: str,
    ) -> Tuple[List[Discrepancy], int]:
        """Reconcile subscription state with billing reality."""
        discrepancies = []
        checked = 0
        
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return discrepancies, checked
        
        checked += 1
        
        # Trial state should not have invoices
        if subscription.state == "trialing":
            inv_result = await db.execute(
                select(SubscriptionInvoice).where(
                    SubscriptionInvoice.subscription_id == subscription_id,
                )
            )
            if inv_result.scalars().first():
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.SUBSCRIPTION_STATE_DRIFT,
                    severity=DiscrepancySeverity.WARNING,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=None,
                    description="Trialing subscription has invoices",
                    evidence={"subscription_state": subscription.state},
                ))
        
        # Active subscription should have current period
        if subscription.state == "active":
            if not subscription.current_period_end:
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.SUBSCRIPTION_STATE_DRIFT,
                    severity=DiscrepancySeverity.ERROR,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=None,
                    description="Active subscription missing current_period_end",
                    evidence={"subscription_id": subscription_id},
                ))
            elif subscription.current_period_end < utcnow():
                discrepancies.append(Discrepancy(
                    discrepancy_type=DiscrepancyType.SUBSCRIPTION_STATE_DRIFT,
                    severity=DiscrepancySeverity.WARNING,
                    organization_id=organization_id,
                    subscription_id=subscription_id,
                    period=period,
                    metric_code=None,
                    description="Active subscription period has ended but not renewed",
                    evidence={
                        "current_period_end": subscription.current_period_end.isoformat(),
                        "now": utcnow().isoformat(),
                    },
                ))
        
        # Past due should have failed payment
        if subscription.state == "past_due":
            # Check for failed payment event
            pass  # Would check SubscriptionEvent for payment_failed
        
        return discrepancies, checked
    
    # =========================================================================
    # CROSS-SUBSCRIPTION CHECKS
    # =========================================================================
    
    async def _reconcile_cross_subscription(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
    ) -> Tuple[List[Discrepancy], int]:
        """Cross-subscription consistency checks."""
        discrepancies = []
        checked = 0
        
        # Get all subscriptions for org
        subs_result = await db.execute(
            select(Subscription).where(
                Subscription.organization_id == organization_id,
            )
        )
        subscriptions = list(subs_result.scalars().all())
        
        if len(subscriptions) <= 1:
            return discrepancies, checked
        
        # Check for duplicate subscriptions
        checked += len(subscriptions)
        
        # Only one active/trialing subscription should exist
        active_subs = [s for s in subscriptions if s.state in ("trialing", "active")]
        if len(active_subs) > 1:
            discrepancies.append(Discrepancy(
                discrepancy_type=DiscrepancyType.SUBSCRIPTION_STATE_DRIFT,
                severity=DiscrepancySeverity.CRITICAL,
                organization_id=organization_id,
                subscription_id=None,
                period=period,
                metric_code=None,
                description=f"Multiple active subscriptions: {[s.id for s in active_subs]}",
                evidence={"active_subscription_ids": [s.id for s in active_subs]},
            ))
        
        # Check for duplicate commercial accounts
        account_result = await db.execute(
            select(CommercialAccount).where(
                CommercialAccount.organization_id == organization_id,
            )
        )
        accounts = list(account_result.scalars().all())
        if len(accounts) > 1:
            discrepancies.append(Discrepancy(
                discrepancy_type=DiscrepancyType.SUBSCRIPTION_STATE_DRIFT,
                severity=DiscrepancySeverity.CRITICAL,
                organization_id=organization_id,
                subscription_id=None,
                period=period,
                metric_code=None,
                description=f"Multiple commercial accounts for organization",
                evidence={"account_ids": [a.id for a in accounts]},
            ))
        
        return discrepancies, checked
    
    # =========================================================================
    # CONNECTOR INSTANCE RECONCILIATION
    # =========================================================================
    
    async def reconcile_connector_instance(
        self,
        db: AsyncSession,
        organization_id: str,
        connector_instance_id: str,
        caller: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """
        Reconcile a specific connector instance.
        
        This method validates that a connector instance's configuration,
        state, and synchronization status are consistent.
        """
        from app.models.canonical_integration import ConnectorInstance, Connector
        
        instance = await db.get(ConnectorInstance, connector_instance_id)
        if not instance or instance.organization_id != organization_id:
            return {"error": "Connector instance not found"}
        
        connector = await db.get(Connector, instance.connector_id)
        
        discrepancies = []
        
        # Check instance state consistency
        if instance.state == "connected" and not instance.credentials:
            discrepancies.append({
                "type": "missing_credentials",
                "severity": "warning",
                "description": "Connected instance has no credentials",
            })
        
        # Check webhook configuration
        if instance.sync_enabled and not instance.webhook_url:
            discrepancies.append({
                "type": "missing_webhook",
                "severity": "info",
                "description": "Sync enabled but no webhook URL configured",
            })
        
        # Check sync status
        if instance.last_sync_at and instance.next_sync_at:
            if instance.next_sync_at < datetime.now(timezone.utc):
                discrepancies.append({
                    "type": "overdue_sync",
                    "severity": "warning",
                    "description": "Next sync time has passed",
                })
        
        return {
            "connector_instance_id": connector_instance_id,
            "connector_name": connector.display_name if connector else "Unknown",
            "instance_state": instance.state,
            "sync_enabled": instance.sync_enabled,
            "last_sync_at": instance.last_sync_at.isoformat() if instance.last_sync_at else None,
            "next_sync_at": instance.next_sync_at.isoformat() if instance.next_sync_at else None,
            "discrepancies_found": len(discrepancies),
            "discrepancies": discrepancies,
            "healthy": len(discrepancies) == 0,
        }
    
    # =========================================================================
    # REPORTING
    # =========================================================================
    
    async def get_reconciliation_report(
        self,
        db: AsyncSession,
        organization_id: str,
        period: str,
    ) -> Dict[str, Any]:
        """Get detailed reconciliation report."""
        result = await self.reconcile_period(db, organization_id, period)
        
        return {
            "period": period,
            "organization_id": organization_id,
            "state": result.state.value,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat() if result.completed_at else None,
            "total_records_checked": result.total_records_checked,
            "summary": result.summary,
            "discrepancies": [
                {
                    "type": d.discrepancy_type.value,
                    "severity": d.severity.value,
                    "subscription_id": d.subscription_id,
                    "period": d.period,
                    "metric_code": d.metric_code,
                    "description": d.description,
                    "expected": str(d.expected_value) if d.expected_value else None,
                    "actual": str(d.actual_value) if d.actual_value else None,
                    "difference": str(d.difference) if d.difference else None,
                    "evidence": d.evidence,
                    "detected_at": d.detected_at.isoformat(),
                }
                for d in result.discrepancies
            ],
        }


# Global instance
reconciliation_service = ReconciliationService()