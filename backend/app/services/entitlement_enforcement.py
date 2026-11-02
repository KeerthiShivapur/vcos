"""Entitlement Enforcement Service — Stage 5.1 Pay-As-You-Go Billing.

Connects usage tracking with entitlement limits for real-time enforcement:
- Pre-flight limit checks before billable operations
- Real-time usage vs. limit monitoring
- Automatic suspension on limit breach
- Grace period and notification handling
- Tenant-scoped enforcement
"""

import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.finance import (
    Entitlement,
    Subscription,
    UsageRecord,
    UsageAggregation,
    Plan,
)
from app.services.commercial_service import commercial_service
from app.services.audit_service import audit_service
from app.services.notification_service import notification_service

logger = logging.getLogger("vcos.billing.entitlement_enforcement")


class EnforcementAction(str, Enum):
    """Actions taken when limit is reached."""
    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    SUSPEND = "suspend"


class LimitScope(str, Enum):
    """Scope at which limit is enforced."""
    ORGANIZATION = "organization"
    SUBSCRIPTION = "subscription"
    USER = "user"
    WORKSPACE = "workspace"


@dataclass
class EnforcementResult:
    """Result of an entitlement enforcement check."""
    allowed: bool
    action: EnforcementAction
    entitlement_key: str
    current_usage: Decimal
    limit: Decimal
    percentage: float
    remaining: Decimal
    reason: Optional[str] = None
    grace_period_ends_at: Optional[datetime] = None


@dataclass
class LimitStatus:
    """Current status of a limit."""
    entitlement_key: str
    entitlement_type: str
    limit: Decimal
    current_usage: Decimal
    percentage: float
    remaining: Decimal
    is_exceeded: bool
    is_warning: bool
    warning_threshold: float = 0.8  # 80%
    enforcement_action: EnforcementAction = EnforcementAction.ALLOW


class EntitlementEnforcementService:
    """Service for enforcing entitlement limits in real-time."""
    
    # Default warning threshold (80%)
    DEFAULT_WARNING_THRESHOLD = 0.8
    
    # Grace period after limit exceeded (24 hours)
    DEFAULT_GRACE_PERIOD = timedelta(hours=24)
    
    def __init__(self):
        pass
    
    # =========================================================================
    # PRE-FLIGHT ENFORCEMENT
    # =========================================================================
    
    async def check_limit_before_operation(
        self,
        db: AsyncSession,
        organization_id: str,
        entitlement_key: str,
        requested_quantity: Decimal = Decimal("1"),
        scope: LimitScope = LimitScope.ORGANIZATION,
        scope_id: Optional[str] = None,
    ) -> EnforcementResult:
        """
        Check entitlement limit before allowing an operation.
        
        This is the primary enforcement point - call before any billable operation.
        """
        # Get entitlement
        entitlement = await commercial_service.get_entitlement(db, organization_id, entitlement_key)
        if not entitlement:
            # No limit configured - allow
            return EnforcementResult(
                allowed=True,
                action=EnforcementAction.ALLOW,
                entitlement_key=entitlement_key,
                current_usage=Decimal("0"),
                limit=Decimal("0"),
                percentage=0.0,
                remaining=Decimal("0"),
                reason="No limit configured",
            )
        
        if entitlement["type"] != "limit":
            # Boolean or tier entitlements don't have quantity limits
            return EnforcementResult(
                allowed=True,
                action=EnforcementAction.ALLOW,
                entitlement_key=entitlement_key,
                current_usage=Decimal("0"),
                limit=Decimal("0"),
                percentage=0.0,
                remaining=Decimal("0"),
                reason=f"Entitlement type '{entitlement['type']}' not subject to quantity limits",
            )
        
        limit = Decimal(str(entitlement.get("value", 0)))
        
        # Get current usage for current period
        current_period = utcnow().strftime("%Y-%m")
        usage_summary = await commercial_service.get_usage_summary(db, organization_id, current_period)
        current_usage = Decimal(str(usage_summary.get(entitlement_key, {}).get("quantity", 0)))
        
        # Calculate projected usage after this operation
        projected_usage = current_usage + requested_quantity
        
        # Check limit
        if projected_usage > limit:
            # Limit would be exceeded
            overage = projected_usage - limit
            percentage = float((projected_usage / limit * 100)) if limit > 0 else 100
            
            # Determine action based on subscription state and grace period
            action = await self._determine_enforcement_action(
                db, organization_id, entitlement_key, current_usage, limit
            )
            
            grace_ends = await self._get_grace_period_end(db, organization_id, entitlement_key)
            
            return EnforcementResult(
                allowed=action == EnforcementAction.ALLOW,
                action=action,
                entitlement_key=entitlement_key,
                current_usage=current_usage,
                limit=limit,
                percentage=percentage,
                remaining=max(Decimal("0"), limit - current_usage),
                reason=f"Limit exceeded: {projected_usage} > {limit}",
                grace_period_ends_at=grace_ends,
            )
        
        # Check warning threshold
        percentage = float((projected_usage / limit * 100)) if limit > 0 else 0
        warning_threshold = 80.0  # 80%
        
        action = EnforcementAction.ALLOW
        if percentage >= warning_threshold * 100:
            action = EnforcementAction.WARN
        
        return EnforcementResult(
            allowed=True,
            action=action,
            entitlement_key=entitlement_key,
            current_usage=current_usage,
            limit=limit,
            percentage=percentage,
            remaining=limit - projected_usage,
            reason="Within limits" if action == EnforcementAction.ALLOW else "Approaching limit",
        )
    
    async def _determine_enforcement_action(
        self,
        db: AsyncSession,
        organization_id: str,
        entitlement_key: str,
        current_usage: Decimal,
        limit: Decimal,
    ) -> EnforcementAction:
        """Determine enforcement action based on context."""
        # Get subscription state
        subscription = await commercial_service.get_subscription(db, organization_id)
        
        if not subscription:
            return EnforcementAction.BLOCK
        
        if subscription.state == "suspended":
            return EnforcementAction.SUSPEND
        
        if subscription.state in ("past_due", "grace"):
            return EnforcementAction.BLOCK
        
        # Check if in grace period for this specific limit
        grace_ends = await self._get_grace_period_end(db, organization_id, entitlement_key)
        if grace_ends and utcnow() < grace_ends:
            return EnforcementAction.WARN  # In grace period, warn but allow
        
        # Check overage percentage
        overage_pct = float((current_usage - limit) / limit * 100) if limit > 0 else 0
        
        if overage_pct > 50:  # 50% over limit
            return EnforcementAction.SUSPEND
        elif overage_pct > 20:  # 20% over limit
            return EnforcementAction.BLOCK
        else:
            return EnforcementAction.BLOCK
    
    async def _get_grace_period_end(
        self,
        db: AsyncSession,
        organization_id: str,
        entitlement_key: str,
    ) -> Optional[datetime]:
        """Get grace period end for a specific limit breach."""
        # Check if there's an active grace period for this limit
        # This would be stored in a limit_breach table or subscription metadata
        # For now, return None (no grace period tracking yet)
        return None
    
    # =========================================================================
    # REAL-TIME LIMIT MONITORING
    # =========================================================================
    
    async def get_all_limit_status(
        self,
        db: AsyncSession,
        organization_id: str,
        period: Optional[str] = None,
    ) -> List[LimitStatus]:
        """Get current status of all limits for an organization."""
        if not period:
            period = utcnow().strftime("%Y-%m")
        
        # Get all limit-type entitlements
        entitlements = await commercial_service.resolve_entitlements(db, organization_id)
        limit_entitlements = {
            k: v for k, v in entitlements.items() 
            if v.get("type") == "limit"
        }
        
        # Get current usage
        usage_summary = await commercial_service.get_usage_summary(db, organization_id, period)
        
        statuses = []
        for key, entitlement in limit_entitlements.items():
            limit = Decimal(str(entitlement.get("value", 0)))
            current_usage = Decimal(str(usage_summary.get(key, {}).get("quantity", 0)))
            
            percentage = float((current_usage / limit * 100)) if limit > 0 else 0
            remaining = max(Decimal("0"), limit - current_usage)
            is_exceeded = current_usage >= limit
            is_warning = percentage >= 80.0
            
            action = EnforcementAction.ALLOW
            if is_exceeded:
                action = EnforcementAction.BLOCK
            elif is_warning:
                action = EnforcementAction.WARN
            
            statuses.append(LimitStatus(
                entitlement_key=key,
                entitlement_type="limit",
                limit=limit,
                current_usage=current_usage,
                percentage=percentage,
                remaining=remaining,
                is_exceeded=is_exceeded,
                is_warning=is_warning,
                enforcement_action=action,
            ))
        
        return statuses
    
    async def check_subscription_limits(
        self,
        db: AsyncSession,
        subscription_id: str,
    ) -> List[LimitStatus]:
        """Check all limits for a specific subscription."""
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return []
        
        return await self.get_all_limit_status(db, subscription.organization_id)
    
    # =========================================================================
    # AUTOMATIC ENFORCEMENT ACTIONS
    # =========================================================================
    
    async def enforce_limits(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> List[Dict[str, Any]]:
        """
        Run automatic enforcement check and take actions.
        
        Called periodically (e.g., hourly) to enforce limits.
        """
        actions_taken = []
        
        statuses = await self.get_all_limit_status(db, organization_id)
        
        for status in statuses:
            if status.enforcement_action == EnforcementAction.SUSPEND:
                # Suspend subscription
                result = await self._suspend_for_limit_breach(db, organization_id, status.entitlement_key)
                actions_taken.append({
                    "action": "suspend",
                    "entitlement_key": status.entitlement_key,
                    "result": result,
                })
            elif status.enforcement_action == EnforcementAction.BLOCK:
                # Block new operations (handled at pre-flight)
                actions_taken.append({
                    "action": "block",
                    "entitlement_key": status.entitlement_key,
                    "reason": "Limit exceeded",
                })
            elif status.enforcement_action == EnforcementAction.WARN:
                # Send warning notification
                await self._send_limit_warning(db, organization_id, status)
                actions_taken.append({
                    "action": "warn",
                    "entitlement_key": status.entitlement_key,
                    "percentage": status.percentage,
                })
        
        return actions_taken
    
    async def _suspend_for_limit_breach(
        self,
        db: AsyncSession,
        organization_id: str,
        entitlement_key: str,
    ) -> Dict[str, Any]:
        """Suspend subscription due to limit breach."""
        subscription = await commercial_service.get_subscription(db, organization_id)
        if not subscription:
            return {"success": False, "reason": "No subscription found"}
        
        # Check if already suspended
        if subscription.state == "suspended":
            return {"success": True, "reason": "Already suspended"}
        
        # Suspend
        await commercial_service.cancel_subscription(
            db, subscription.id, cancelled_by="system",
            reason=f"Limit breached: {entitlement_key}", immediate=True
        )
        
        await publish_event(
            db,
            name="subscription.suspended.limit_breach",
            organization_id=organization_id,
            payload={
                "subscription_id": subscription.id,
                "entitlement_key": entitlement_key,
                "reason": "Limit exceeded",
            },
        )
        
        await audit_service.log(
            db,
            organization_id=organization_id,
            action="subscription.suspended.limit_breach",
            actor_id="system",
            resource_type="subscription",
            resource_id=subscription.id,
            details={"entitlement_key": entitlement_key},
        )
        
        return {"success": True, "subscription_id": subscription.id}
    
    async def _send_limit_warning(
        self,
        db: AsyncSession,
        organization_id: str,
        status: LimitStatus,
    ) -> None:
        """Send warning notification for approaching limit."""
        subscription = await commercial_service.get_subscription(db, organization_id)
        if not subscription:
            return
        
        await notification_service.create(
            db,
            organization_id=organization_id,
            recipient_id=subscription.organization_id,  # Would need admin user
            type="billing",
            title=f"Limit Warning: {status.entitlement_key}",
            body=(
                f"Usage for {status.entitlement_key} is at {status.percentage:.1f}% "
                f"of limit ({status.current_usage}/{status.limit}). "
                f"Approaching limit - consider upgrading your plan."
            ),
            priority="medium",
            link=f"/billing/usage/{status.entitlement_key}",
        )
        
        await publish_event(
            db,
            name="entitlement.limit_warning",
            organization_id=organization_id,
            payload={
                "entitlement_key": status.entitlement_key,
                "percentage": status.percentage,
                "current_usage": str(status.current_usage),
                "limit": str(status.limit),
            },
        )
    
    # =========================================================================
    # GRACE PERIOD MANAGEMENT
    # =========================================================================
    
    async def grant_grace_period(
        self,
        db: AsyncSession,
        organization_id: str,
        entitlement_key: str,
        duration: timedelta,
        granted_by: str,
        reason: str,
    ) -> datetime:
        """Grant a grace period for a limit breach."""
        ends_at = utcnow() + duration
        
        # Store grace period (would need a LimitGracePeriod table)
        # For now, log the grant
        await audit_service.log(
            db,
            organization_id=organization_id,
            action="limit.grace_period.granted",
            actor_id=granted_by,
            resource_type="entitlement",
            resource_id=entitlement_key,
            details={
                "duration_hours": duration.total_seconds() / 3600,
                "reason": reason,
                "ends_at": ends_at.isoformat(),
            },
        )
        
        await publish_event(
            db,
            name="limit.grace_period.granted",
            organization_id=organization_id,
            payload={
                "entitlement_key": entitlement_key,
                "ends_at": ends_at.isoformat(),
                "reason": reason,
            },
        )
        
        return ends_at
    
    async def revoke_grace_period(
        self,
        db: AsyncSession,
        organization_id: str,
        entitlement_key: str,
        revoked_by: str,
    ) -> None:
        """Revoke an active grace period."""
        await audit_service.log(
            db,
            organization_id=organization_id,
            action="limit.grace_period.revoked",
            actor_id=revoked_by,
            resource_type="entitlement",
            resource_id=entitlement_key,
        )
        
        await publish_event(
            db,
            name="limit.grace_period.revoked",
            organization_id=organization_id,
            payload={"entitlement_key": entitlement_key},
        )
    
    # =========================================================================
    # QUERY METHODS
    # =========================================================================
    
    async def get_usage_vs_limit(
        self,
        db: AsyncSession,
        organization_id: str,
        entitlement_key: str,
        period: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get detailed usage vs limit comparison."""
        if not period:
            period = utcnow().strftime("%Y-%m")
        
        entitlement = await commercial_service.get_entitlement(db, organization_id, entitlement_key)
        if not entitlement or entitlement.get("type") != "limit":
            return {"error": "Not a limit-type entitlement"}
        
        limit = Decimal(str(entitlement.get("value", 0)))
        usage_summary = await commercial_service.get_usage_summary(db, organization_id, period)
        current_usage = Decimal(str(usage_summary.get(entitlement_key, {}).get("quantity", 0)))
        
        return {
            "entitlement_key": entitlement_key,
            "period": period,
            "limit": str(limit),
            "current_usage": str(current_usage),
            "percentage": float((current_usage / limit * 100)) if limit > 0 else 0,
            "remaining": str(max(Decimal("0"), limit - current_usage)),
            "is_exceeded": current_usage >= limit,
            "is_warning": current_usage >= limit * Decimal("0.8"),
        }
    
    async def get_limit_history(
        self,
        db: AsyncSession,
        organization_id: str,
        entitlement_key: str,
        months: int = 12,
    ) -> List[Dict[str, Any]]:
        """Get historical limit usage for trend analysis."""
        history = []
        current = utcnow()
        
        for i in range(months):
            period_date = current - timedelta(days=30 * i)
            period = period_date.strftime("%Y-%m")
            
            usage_summary = await commercial_service.get_usage_summary(db, organization_id, period)
            current_usage = Decimal(str(usage_summary.get(entitlement_key, {}).get("quantity", 0)))
            
            entitlement = await commercial_service.get_entitlement(db, organization_id, entitlement_key)
            limit = Decimal(str(entitlement.get("value", 0))) if entitlement else Decimal("0")
            
            history.append({
                "period": period,
                "usage": str(current_usage),
                "limit": str(limit),
                "percentage": float((current_usage / limit * 100)) if limit > 0 else 0,
            })
        
        return list(reversed(history))


# Global instance
entitlement_enforcement_service = EntitlementEnforcementService()