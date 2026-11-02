"""Usage Metering API — Stage 5.1 Pay-As-You-Go Billing.

REST API endpoints for usage event ingestion, aggregation, pricing, and billing.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.schemas.usage_metering import (
    UsageEventCreate,
    UsageBatchRequest,
    UsageBatchResponse,
    UsageEventResponse,
    UsageMetricCode,
    UsageEventSource,
)
from app.services.usage_intake_service import usage_intake_service
from app.services.usage_aggregation_service import usage_aggregation_service
from app.services.pricing_engine import pricing_engine
from app.services.invoice_preview_service import invoice_preview_service
from app.services.reconciliation_service import reconciliation_service
from app.services.entitlement_enforcement import entitlement_enforcement_service
from app.services.commercial_service import commercial_service

logger = logging.getLogger("vcos.api.usage_metering")

router = APIRouter(prefix="/usage", tags=["Usage Metering"])


# =========================================================================
# USAGE EVENT INGESTION
# =========================================================================

@router.post("/events", response_model=UsageEventResponse)
async def ingest_usage_event(
    event: UsageEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ingest a single usage event.
    
    Validates schema, verifies tenant ownership, enforces idempotency,
    and records the event for billing.
    """
    # Verify user belongs to the organization
    if str(current_user.organization_id) != event.organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot submit usage events for another organization",
        )
    
    result = await usage_intake_service.ingest_event(db, event, str(current_user.organization_id))
    return result


@router.post("/events/batch", response_model=UsageBatchResponse)
async def ingest_usage_batch(
    batch: UsageBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ingest a batch of usage events (max 1000 per batch).
    
    Each event is processed independently with its own transaction savepoint.
    Partial failures don't affect other events in the batch.
    """
    # Verify all events belong to user's organization
    for event in batch.events:
        if str(current_user.organization_id) != event.organization_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Event {event.event_id} belongs to different organization",
            )
    
    result = await usage_intake_service.ingest_batch(db, batch, str(current_user.organization_id))
    return result


@router.get("/events/{event_id}", response_model=UsageEventResponse)
async def get_event_status(
    event_id: str,
    organization_id: str = Query(..., description="Organization ID"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get processing status of a usage event by event_id."""
    if str(current_user.organization_id) != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access events for another organization",
        )
    
    event_status = await usage_intake_service.get_event_status(db, organization_id, event_id)
    if not event_status:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found",
        )
    
    return event_status


@router.get("/events", response_model=List[UsageEventResponse])
async def list_events_by_source(
    organization_id: str = Query(..., description="Organization ID"),
    source_system: Optional[UsageEventSource] = Query(None, description="Filter by source system"),
    period: Optional[str] = Query(None, description="Billing period (YYYY-MM)"),
    limit: int = Query(100, ge=1, le=1000, description="Max results"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List usage events by source system and period."""
    if str(current_user.organization_id) != organization_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access events for another organization",
        )
    
    events = await usage_intake_service.get_events_by_source(
        db, organization_id, source_system, period, limit
    )
    return events


# =========================================================================
# USAGE AGGREGATION
# =========================================================================

@router.post("/aggregations/period/{period}")
async def aggregate_period(
    period: str,
    subscription_id: Optional[str] = Query(None, description="Specific subscription (optional)"),
    metric_codes: Optional[List[str]] = Query(None, description="Specific metrics to aggregate"),
    force: bool = Query(False, description="Force re-aggregation even if up to date"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Trigger aggregation for a billing period.
    
    Idempotent: re-running with same inputs produces same results.
    """
    # Verify subscription access
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != str(current_user.organization_id):
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    results = await usage_aggregation_service.aggregate_period(
        db=db,
        organization_id=str(current_user.organization_id),
        period=period,
        metric_codes=metric_codes,
        force_reaggregate=force,
    )
    
    return {
        "period": period,
        "subscription_id": subscription_id,
        "results": [
            {
                "metric_code": r.metric_code,
                "total_quantity": str(r.total_quantity),
                "record_count": r.record_count,
                "version": r.aggregation_version,
                "state": r.state.value,
                "duration_ms": r.duration_ms,
                "error": r.error,
            }
            for r in results
        ],
    }


@router.get("/aggregations/period/{period}")
async def get_period_aggregations(
    period: str,
    subscription_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all aggregations for a billing period."""
    org_id = str(current_user.organization_id)
    
    # Verify subscription if provided
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    aggregations = await usage_aggregation_service.get_aggregations_for_period(
        db, org_id, period
    )
    
    return {
        "period": period,
        "aggregations": [
            {
                "metric_code": a.metric_code,
                "total_quantity": str(a.total_quantity),
                "record_count": a.record_count,
                "version": a.version,
                "aggregation_type": a.aggregation_type,
                "last_processed_at": a.last_processed_at.isoformat() if a.last_processed_at else None,
            }
            for a in aggregations
        ],
    }


@router.get("/aggregations/history/{metric_code}")
async def get_aggregation_history(
    metric_code: str,
    subscription_id: Optional[str] = Query(None),
    limit: int = Query(24, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregation history for a metric."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    history = await usage_aggregation_service.get_aggregation_history(
        db, org_id, metric_code, limit
    )
    
    return {
        "metric_code": metric_code,
        "history": [
            {
                "period": h.period,
                "total_quantity": str(h.total_quantity),
                "record_count": h.record_count,
                "version": h.version,
                "aggregation_type": h.aggregation_type,
                "last_processed_at": h.last_processed_at.isoformat() if h.last_processed_at else None,
            }
            for h in history
        ],
    }


@router.get("/aggregations/status/{period}")
async def get_aggregation_status(
    period: str,
    subscription_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get aggregation status summary for a period."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    status = await usage_aggregation_service.get_aggregation_status(db, org_id, period)
    return status


@router.post("/aggregations/late-events")
async def process_late_events(
    lookback_days: int = Query(30, ge=1, le=90),
    subscription_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Process late-arriving events for recent periods."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    results = await usage_aggregation_service.process_late_events(
        db, org_id, lookback_days
    )
    
    return {
        "lookback_days": lookback_days,
        "results": [
            {
                "metric_code": r.metric_code,
                "period": r.period,
                "total_quantity": str(r.total_quantity),
                "record_count": r.record_count,
                "version": r.aggregation_version,
                "state": r.state.value,
            }
            for r in results
        ],
    }


# =========================================================================
# PRICING
# =========================================================================

@router.post("/pricing/calculate")
async def calculate_price(
    subscription_id: str,
    period: str,
    usage_quantities: Dict[str, Decimal],
    pricing_version: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calculate prices for given usage quantities."""
    sub = await db.get(Subscription, subscription_id)
    if not sub or str(sub.organization_id) != str(current_user.organization_id):
        raise HTTPException(status_code=403, detail="Subscription not found")
    
    calculations = await pricing_engine.calculate_price(
        db=db,
        subscription_id=subscription_id,
        period=period,
        usage_quantities=usage_quantities,
        pricing_version=pricing_version,
    )
    
    return {
        "subscription_id": subscription_id,
        "period": period,
        "calculations": [
            {
                "metric_code": c.metric_code,
                "model": c.model.value,
                "quantity": str(c.quantity),
                "unit_price": str(c.unit_price),
                "included_quantity": str(c.included_quantity),
                "billable_quantity": str(c.billable_quantity),
                "subtotal": str(c.subtotal),
                "currency": c.currency,
                "pricing_rule_version": c.pricing_rule_version,
                "tier_breakdown": c.tier_breakdown,
            }
            for c in calculations
        ],
    }


@router.get("/pricing/explain")
async def explain_pricing(
    subscription_id: str,
    period: str,
    metric_code: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed pricing explanation for a metric."""
    sub = await db.get(Subscription, subscription_id)
    if not sub or str(sub.organization_id) != str(current_user.organization_id):
        raise HTTPException(status_code=403, detail="Subscription not found")
    
    explanation = await invoice_preview_service.explain_pricing(
        db, subscription_id, period, metric_code
    )
    return explanation


@router.get("/pricing/rules")
async def get_pricing_rules(
    subscription_id: str,
    metric_code: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get pricing rules for a subscription's plan."""
    sub = await db.get(Subscription, subscription_id)
    if not sub or str(sub.organization_id) != str(current_user.organization_id):
        raise HTTPException(status_code=403, detail="Subscription not found")
    
    plan = await db.get(Plan, sub.plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    
    rules = await pricing_engine.get_pricing_rules(db, plan.id, metric_code)
    
    return {
        "plan_id": plan.id,
        "plan_key": plan.key,
        "rules": [
            {
                "metric_code": r.metric_code,
                "model": r.model,
                "version": r.version,
                "unit_price_cents": r.unit_price_cents,
                "overage_price_cents": r.overage_price_cents,
                "flat_price_cents": r.flat_price_cents,
                "base_amount_cents": r.base_amount_cents,
                "percentage": str(r.percentage) if r.percentage else None,
                "tiers": r.tiers,
                "effective_from": r.effective_from.isoformat() if r.effective_from else None,
                "effective_to": r.effective_to.isoformat() if r.effective_to else None,
                "is_active": r.is_active,
            }
            for r in rules
        ],
    }


# =========================================================================
# INVOICE PREVIEW
# =========================================================================

@router.post("/invoices/preview")
async def generate_invoice_preview(
    subscription_id: str,
    period: Optional[str] = None,
    pricing_version: Optional[int] = None,
    what_if_usage: Optional[Dict[str, Decimal]] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate a deterministic invoice preview."""
    sub = await db.get(Subscription, subscription_id)
    if not sub or str(sub.organization_id) != str(current_user.organization_id):
        raise HTTPException(status_code=403, detail="Subscription not found")
    
    preview = await invoice_preview_service.generate_preview(
        db=db,
        subscription_id=subscription_id,
        period=period,
        pricing_version=pricing_version,
        what_if_usage=what_if_usage,
    )
    
    return {
        "preview_id": preview.preview_id,
        "subscription_id": preview.subscription_id,
        "organization_id": preview.organization_id,
        "period": preview.billing_period,
        "subtotal_cents": preview.subtotal_cents,
        "tax_cents": preview.tax_cents,
        "discount_cents": preview.discount_cents,
        "total_cents": preview.total_cents,
        "currency": preview.currency,
        "line_items": preview.line_items,
        "usage_by_metric": preview.usage_by_metric,
        "pricing_version": preview.pricing_version,
        "generated_at": preview.generated_at.isoformat(),
        "expires_at": preview.expires_at.isoformat(),
        "status": preview.status.value,
    }


@router.post("/invoices/preview/what-if")
async def generate_what_if_preview(
    subscription_id: str,
    period: str,
    what_if_changes: Dict[str, Decimal],
    pricing_version: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate comparison preview: current vs. what-if scenario."""
    sub = await db.get(Subscription, subscription_id)
    if not sub or str(sub.organization_id) != str(current_user.organization_id):
        raise HTTPException(status_code=403, detail="Subscription not found")
    
    current, what_if = await invoice_preview_service.generate_what_if_preview(
        db=db,
        subscription_id=subscription_id,
        period=period,
        what_if_changes=what_if_changes,
        pricing_version=pricing_version,
    )
    
    return {
        "current": {
            "total_cents": current.total_cents,
            "line_items": current.line_items,
        },
        "what_if": {
            "total_cents": what_if.total_cents,
            "line_items": what_if.line_items,
        },
        "difference_cents": what_if.total_cents - current.total_cents,
    }


# =========================================================================
# ENTITLEMENT ENFORCEMENT
# =========================================================================

@router.post("/entitlements/check-limit")
async def check_limit_before_operation(
    entitlement_key: str,
    requested_quantity: Decimal = Decimal("1"),
    scope: str = "organization",
    scope_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Check entitlement limit before allowing an operation."""
    result = await entitlement_enforcement_service.check_limit_before_operation(
        db=db,
        organization_id=str(current_user.organization_id),
        entitlement_key=entitlement_key,
        requested_quantity=requested_quantity,
    )
    
    return {
        "allowed": result.allowed,
        "action": result.action.value,
        "entitlement_key": result.entitlement_key,
        "current_usage": str(result.current_usage),
        "limit": str(result.limit),
        "percentage": result.percentage,
        "remaining": str(result.remaining),
        "reason": result.reason,
    }


@router.get("/entitlements/status")
async def get_all_limit_status(
    subscription_id: Optional[str] = Query(None),
    period: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get current status of all limits for an organization."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    statuses = await entitlement_enforcement_service.get_all_limit_status(
        db, org_id, period
    )
    
    return {
        "organization_id": org_id,
        "period": period or datetime.now(timezone.utc).strftime("%Y-%m"),
        "limits": [
            {
                "entitlement_key": s.entitlement_key,
                "limit": str(s.limit),
                "current_usage": str(s.current_usage),
                "percentage": s.percentage,
                "remaining": str(s.remaining),
                "is_exceeded": s.is_exceeded,
                "is_warning": s.is_warning,
                "enforcement_action": s.enforcement_action.value,
            }
            for s in statuses
        ],
    }


@router.post("/entitlements/enforce")
async def enforce_limits(
    subscription_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run automatic enforcement check and take actions."""
    org_id = str(current_user.organization_id)
    
    actions = await entitlement_enforcement_service.enforce_limits(db, org_id)
    
    return {
        "organization_id": org_id,
        "actions_taken": actions,
    }


# =========================================================================
# RECONCILIATION
# =========================================================================

@router.post("/reconciliation/period/{period}")
async def reconcile_period(
    period: str,
    subscription_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run full reconciliation for a billing period."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    result = await reconciliation_service.reconcile_period(
        db=db,
        organization_id=org_id,
        period=period,
        subscription_id=subscription_id,
    )
    
    return {
        "period": period,
        "organization_id": org_id,
        "subscription_id": subscription_id,
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


@router.get("/reconciliation/report/{period}")
async def get_reconciliation_report(
    period: str,
    subscription_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed reconciliation report."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    report = await reconciliation_service.get_reconciliation_report(db, org_id, period)
    return report


# =========================================================================
# USAGE QUERY
# =========================================================================

@router.get("/usage/summary")
async def get_usage_summary(
    subscription_id: Optional[str] = Query(None),
    period: Optional[str] = None,
    entitlement_key: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get usage summary for an organization."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    if not period:
        period = datetime.now(timezone.utc).strftime("%Y-%m")
    
    summary = await commercial_service.get_usage_summary(db, org_id, period)
    
    if entitlement_key:
        return {
            "period": period,
            "entitlement_key": entitlement_key,
            "usage": summary.get(entitlement_key, {}),
        }
    
    return {
        "period": period,
        "summary": summary,
    }


@router.get("/usage/limits/{entitlement_key}")
async def get_usage_vs_limit(
    entitlement_key: str,
    subscription_id: Optional[str] = Query(None),
    period: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get detailed usage vs limit comparison."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(status_code=403, detail="Subscription not found")
    
    if not period:
        period = datetime.now(timezone.utc).strftime("%Y-%m")
    
    result = await entitlement_enforcement_service.get_usage_vs_limit(
        db, org_id, entitlement_key, period
    )
    
    return result


# Import datetime
from datetime import datetime
from app.models.finance import Subscription