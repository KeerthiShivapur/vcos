"""Commercial Service — Subscription, Billing, Entitlements & Provisioning (Gate 27)."""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional, List

from sqlalchemy import select, func, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    ACCESS,
    EMAIL_VERIFY,
    INVITE,
    PASSWORD_RESET,
    REFRESH,
    create_access_token,
    create_email_verification_token,
    create_invite_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.timeutils import utcnow
from app.models.finance import (
    CommercialAccount,
    Plan,
    Entitlement,
    Subscription,
    UsageRecord,
    Invoice,
    Payment,
    SubscriptionInvoice,
    SubscriptionPayment,
    Provisioning,
    ProvisioningStep,
    PaymentProviderConfig,
    SubscriptionEvent,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.services.audit_service import audit_service
from app.services.event_service import event_service
from app.services.notification_service import notification_service
from app.services.email_service import email_service, hash_token

logger = logging.getLogger("vcos.commercial")


class CommercialService:
    """Service for managing commercial subscriptions, billing, entitlements, and provisioning."""

    # ------------------------------------------------------------------ Plan Management

    async def create_plan(
        self,
        db: AsyncSession,
        *,
        key: str,
        name: str,
        tier: str,
        monthly_price_cents: int,
        annual_price_cents: int,
        description: Optional[str] = None,
        entitlements: Optional[dict] = None,
        features: Optional[dict] = None,
        limits: Optional[dict] = None,
        intervals: Optional[List[str]] = None,
        trial_days: int = 14,
        is_public: bool = True,
        sort_order: int = 0,
        metadata_json: Optional[dict] = None,
        created_by: Optional[str] = None,
    ) -> Plan:
        """Create a new commercial plan."""
        
        existing = await db.execute(select(Plan).where(Plan.key == key))
        if existing.scalars().first():
            raise ValueError(f"Plan with key '{key}' already exists")
        
        if tier not in ("starter", "professional", "enterprise", "custom"):
            raise ValueError(f"Invalid tier: {tier}")
        
        plan = Plan(
            key=key,
            name=name,
            description=description,
            tier=tier,
            monthly_price_cents=monthly_price_cents,
            annual_price_cents=annual_price_cents,
            currency="USD",
            intervals=intervals or ["monthly", "annual"],
            entitlements=entitlements or {},
            features=features or {},
            limits=limits or {},
            is_active=True,
            is_public=is_public,
            sort_order=sort_order,
            trial_days=trial_days,
            metadata_json=metadata_json or {},
        )
        
        db.add(plan)
        await db.flush()
        
        await audit_service.log(
            db,
            organization_id="system",
            action="plan.created",
            actor_id=created_by,
            resource_type="plan",
            resource_id=plan.id,
            details={"key": key, "tier": tier},
        )
        
        logger.info(f"Created plan: {key} ({tier})")
        return plan

    async def get_plan(self, db: AsyncSession, plan_id: str) -> Optional[Plan]:
        """Get a plan by ID."""
        return await db.get(Plan, plan_id)

    async def get_plan_by_key(self, db: AsyncSession, key: str) -> Optional[Plan]:
        """Get a plan by key."""
        result = await db.execute(select(Plan).where(Plan.key == key))
        return result.scalar_one_or_none()

    async def ensure_default_plans(self, db: AsyncSession) -> None:
        """Ensure default plans exist with correct entitlements."""
        default_plans = [
            {
                "key": "starter",
                "name": "Starter",
                "description": "Starter plan for small teams",
                "tier": "starter",
                "monthly_price_cents": 0,
                "annual_price_cents": 0,
                "entitlements": {
                    "employees.max": {"type": "limit", "value": 10},
                    "storage.gb": {"type": "limit", "value": 10},
                    "projects.max": {"type": "limit", "value": 5},
                    "teams.max": {"type": "limit", "value": 3},
                    "integrations.max": {"type": "limit", "value": 3},
                },
                "features": {},
                "limits": {},
                "is_active": True,
                "is_public": True,
                "sort_order": 10,
                "trial_days": 14,
            },
            {
                "key": "professional",
                "name": "Professional",
                "description": "Professional plan for growing teams",
                "tier": "professional",
                "monthly_price_cents": 1000,
                "annual_price_cents": 10000,
                "entitlements": {
                    "employees.max": {"type": "limit", "value": 100},
                    "storage.gb": {"type": "limit", "value": 100},
                    "projects.max": {"type": "limit", "value": 50},
                    "teams.max": {"type": "limit", "value": 20},
                    "integrations.max": {"type": "limit", "value": 10},
                },
                "features": {},
                "limits": {},
                "is_active": True,
                "is_public": True,
                "sort_order": 20,
                "trial_days": 14,
            },
            {
                "key": "enterprise",
                "name": "Enterprise",
                "description": "Enterprise plan for large organizations",
                "tier": "enterprise",
                "monthly_price_cents": 9900,
                "annual_price_cents": 99000,
                "entitlements": {
                    "employees.max": {"type": "limit", "value": 1000},
                    "storage.gb": {"type": "limit", "value": 1000},
                    "projects.max": {"type": "limit", "value": 500},
                    "teams.max": {"type": "limit", "value": 100},
                    "integrations.max": {"type": "limit", "value": 50},
                },
                "features": {},
                "limits": {},
                "is_active": True,
                "is_public": True,
                "sort_order": 30,
                "trial_days": 30,
            },
        ]

        for plan_data in default_plans:
            existing = await db.execute(select(Plan).where(Plan.key == plan_data["key"]))
            plan = existing.scalar_one_or_none()
            if plan:
                # Update entitlements if missing keys
                updated = False
                for key, value in plan_data["entitlements"].items():
                    if key not in (plan.entitlements or {}):
                        if plan.entitlements is None:
                            plan.entitlements = {}
                        plan.entitlements[key] = value
                        updated = True
                if updated:
                    await db.flush()
                    logger.info(f"Updated entitlements for plan: {plan_data['key']}")
            else:
                plan = Plan(
                    key=plan_data["key"],
                    name=plan_data["name"],
                    description=plan_data["description"],
                    tier=plan_data["tier"],
                    monthly_price_cents=plan_data["monthly_price_cents"],
                    annual_price_cents=plan_data["annual_price_cents"],
                    currency="USD",
                    intervals=["monthly", "annual"],
                    entitlements=plan_data["entitlements"],
                    features=plan_data["features"],
                    limits=plan_data["limits"],
                    is_active=plan_data["is_active"],
                    is_public=plan_data["is_public"],
                    sort_order=plan_data["sort_order"],
                    trial_days=plan_data["trial_days"],
                    metadata_json={},
                )
                db.add(plan)
                await db.flush()
                logger.info(f"Created default plan: {plan_data['key']}")

        await db.commit()

    async def list_plans(
        self,
        db: AsyncSession,
        *,
        tier: Optional[str] = None,
        is_active: Optional[bool] = None,
        is_public: Optional[bool] = None,
    ) -> List[Plan]:
        """List plans with optional filters."""
        query = select(Plan)
        if tier:
            query = query.where(Plan.tier == tier)
        if is_active is not None:
            query = query.where(Plan.is_active == is_active)
        if is_public is not None:
            query = query.where(Plan.is_public == is_public)
        query = query.order_by(Plan.sort_order, Plan.tier)
        result = await db.execute(query)
        return list(result.scalars().all())

    async def update_plan(
        self,
        db: AsyncSession,
        plan_id: str,
        **fields: Any,
    ) -> Optional[Plan]:
        """Update a plan."""
        plan = await self.get_plan(db, plan_id)
        if not plan:
            return None
        
        for key, value in fields.items():
            if value is not None and hasattr(plan, key):
                setattr(plan, key, value)
        
        plan.updated_at = utcnow()
        await db.flush()
        return plan

    async def deactivate_plan(
        self,
        db: AsyncSession,
        plan_id: str,
        reason: str,
        deprecated_by: Optional[str] = None,
    ) -> Optional[Plan]:
        """Deactivate a plan."""
        plan = await self.get_plan(db, plan_id)
        if not plan:
            return None
        
        plan.is_active = False
        plan.updated_at = utcnow()
        await db.flush()
        
        await audit_service.log(
            db,
            organization_id="system",
            action="plan.deactivated",
            actor_id=deprecated_by,
            resource_type="plan",
            resource_id=plan_id,
            details={"reason": reason},
        )
        
        return plan

    # ------------------------------------------------------------------ Entitlement Resolution

    async def resolve_entitlements(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> dict:
        """Resolve all effective entitlements for an organization."""
        
        # Get active subscription
        sub_result = await db.execute(
            select(Subscription).where(
                Subscription.organization_id == organization_id,
                Subscription.state.in_(["trialing", "active", "past_due", "grace"]),
            ).order_by(Subscription.created_at.desc())
        )
        subscription = sub_result.scalars().first()
        
        if not subscription:
            # No active subscription - return default free tier entitlements
            free_plan = await self.get_plan_by_key(db, "starter")
            if free_plan:
                return self._compute_entitlements_from_plan(free_plan)
            return {}
        
        # Get plan
        plan = await self.get_plan(db, subscription.plan_id)
        if not plan:
            return {}
        
        # Compute base entitlements from plan
        entitlements = self._compute_entitlements_from_plan(plan)
        
        # Apply any overrides from Entitlement table
        entitlement_overrides = await db.execute(
            select(Entitlement).where(
                Entitlement.organization_id == organization_id,
                or_(
                    Entitlement.effective_to.is_(None),
                    Entitlement.effective_to > utcnow(),
                ),
                Entitlement.effective_from <= utcnow(),
            )
        )
        
        for override in entitlement_overrides.scalars().all():
            if override.entitlement_type == "limit":
                entitlements[override.key] = {
                    "type": "limit",
                    "value": override.numeric_value,
                    "source": override.source,
                }
            elif override.entitlement_type == "boolean":
                entitlements[override.key] = {
                    "type": "boolean",
                    "value": override.boolean_value,
                    "source": override.source,
                }
            elif override.entitlement_type == "tier":
                entitlements[override.key] = {
                    "type": "tier",
                    "value": override.value,
                    "source": override.source,
                }
        
        return entitlements

    def _compute_entitlements_from_plan(self, plan: Plan) -> dict:
        """Compute entitlements from a plan definition."""
        entitlements = {}
        
        for key, config in plan.entitlements.items():
            if isinstance(config, dict):
                entitlements[key] = {
                    "type": config.get("type", "limit"),
                    "value": config.get("value"),
                    "source": "plan",
                }
            else:
                # Simple format: {"employees.max": 50}
                entitlements[key] = {
                    "type": "limit",
                    "value": config,
                    "source": "plan",
                }
        
        # Add features as boolean entitlements
        for key, enabled in plan.features.items():
            if isinstance(enabled, bool):
                entitlements[key] = {
                    "type": "boolean",
                    "value": enabled,
                    "source": "plan",
                }
        
        return entitlements

    async def get_entitlement(
        self,
        db: AsyncSession,
        organization_id: str,
        key: str,
    ) -> Optional[dict]:
        """Get a specific resolved entitlement for an organization."""
        entitlements = await self.resolve_entitlements(db, organization_id)
        return entitlements.get(key)

    async def check_entitlement(
        self,
        db: AsyncSession,
        organization_id: str,
        key: str,
        required: Any = True,
    ) -> dict:
        """Check if an organization has an entitlement and if it meets requirements."""
        entitlement = await self.get_entitlement(db, organization_id, key)
        
        if not entitlement:
            return {"allowed": False, "reason": "not_entitled", "entitlement": None}
        
        if entitlement["type"] == "boolean":
            allowed = entitlement["value"] == required
            return {"allowed": allowed, "reason": None if allowed else "feature_disabled", "entitlement": entitlement}
        
        if entitlement["type"] == "limit":
            if isinstance(required, (int, float)):
                allowed = entitlement.get("value", 0) >= required
                return {
                    "allowed": allowed,
                    "reason": None if allowed else "limit_exceeded",
                    "entitlement": entitlement,
                    "current": entitlement.get("value"),
                    "required": required,
                }
        
        return {"allowed": True, "reason": None, "entitlement": entitlement}

    async def check_limit(
        self,
        db: AsyncSession,
        organization_id: str,
        key: str,
        current_usage: float,
    ) -> dict:
        """Check if current usage exceeds the entitlement limit."""
        entitlement = await self.get_entitlement(db, organization_id, key)
        
        if not entitlement or entitlement["type"] != "limit":
            return {"allowed": True, "reason": "no_limit", "limit": None, "usage": current_usage}
        
        limit = entitlement.get("value", 0)
        allowed = current_usage < limit
        percentage = (current_usage / limit * 100) if limit > 0 else 0
        
        return {
            "allowed": allowed,
            "reason": None if allowed else "limit_exceeded",
            "limit": limit,
            "usage": current_usage,
            "percentage": round(percentage, 1),
            "remaining": max(0, limit - current_usage),
        }

    # ------------------------------------------------------------------ Override Entitlements

    async def set_entitlement_override(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        key: str,
        entitlement_type: str,
        value: Any,
        source: str = "override",
        override_reason: Optional[str] = None,
        override_by: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> Entitlement:
        """Set or update an entitlement override."""
        
        # Deactivate existing override for this key
        existing = await db.execute(
            select(Entitlement).where(
                Entitlement.organization_id == organization_id,
                Entitlement.key == key,
            )
        )
        for e in existing.scalars().all():
            e.effective_to = utcnow()
        
        # Create new override
        if entitlement_type == "limit":
            numeric_value = float(value) if value is not None else None
            boolean_value = None
            str_value = str(value) if value is not None else None
        elif entitlement_type == "boolean":
            boolean_value = bool(value)
            numeric_value = 1.0 if value else 0.0
            str_value = str(value).lower()
        else:  # tier
            str_value = str(value)
            numeric_value = None
            boolean_value = None
        
        override = Entitlement(
            organization_id=organization_id,
            key=key,
            entitlement_type=entitlement_type,
            value=str_value,
            numeric_value=numeric_value,
            boolean_value=boolean_value,
            source=source,
            override_reason=override_reason,
            override_by=override_by,
            override_expires_at=expires_at,
            effective_from=utcnow(),
            effective_to=expires_at,
        )
        
        db.add(override)
        await db.flush()
        
        await audit_service.log(
            db,
            organization_id=organization_id,
            action="entitlement.override",
            actor_id=override_by,
            resource_type="entitlement",
            resource_id=override.id,
            details={"key": key, "type": entitlement_type, "value": str(value)},
        )
        
        return override

    async def remove_entitlement_override(
        self,
        db: AsyncSession,
        organization_id: str,
        key: str,
    ) -> bool:
        """Remove an entitlement override."""
        result = await db.execute(
            select(Entitlement).where(
                Entitlement.organization_id == organization_id,
                Entitlement.key == key,
            )
        )
        overrides = result.scalars().all()
        
        for override in overrides:
            override.effective_to = utcnow()
        
        await db.flush()
        return len(overrides) > 0

    # ------------------------------------------------------------------ Commercial Account

    async def get_or_create_commercial_account(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> CommercialAccount:
        """Get or create commercial account for organization."""
        
        result = await db.execute(
            select(CommercialAccount).where(CommercialAccount.organization_id == organization_id)
        )
        account = result.scalar_one_or_none()
        
        if not account:
            account = CommercialAccount(
                organization_id=organization_id,
                currency="USD",
            )
            db.add(account)
            await db.flush()
        
        return account

    async def update_commercial_account(
        self,
        db: AsyncSession,
        organization_id: str,
        **fields: Any,
    ) -> Optional[CommercialAccount]:
        """Update commercial account."""
        account = await self.get_or_create_commercial_account(db, organization_id)
        
        for key, value in fields.items():
            if value is not None and hasattr(account, key):
                setattr(account, key, value)
        
        account.updated_at = utcnow()
        await db.flush()
        return account

    # ------------------------------------------------------------------ Subscription Management

    async def create_subscription(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        plan_key: str,
        billing_interval: str = "monthly",
        trial_days: Optional[int] = None,
        auto_renew: bool = True,
        payment_provider: Optional[str] = None,
        payment_method_id: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> Subscription:
        """Create a new subscription for an organization."""
        
        # Check for existing active subscription
        existing = await db.execute(
            select(Subscription).where(
                Subscription.organization_id == organization_id,
                Subscription.state.in_(["trialing", "active", "past_due", "grace"]),
            )
        )
        if existing.scalars().first():
            raise ValueError("Organization already has an active subscription")
        
        # Get plan
        plan = await self.get_plan_by_key(db, plan_key)
        if not plan:
            raise ValueError(f"Plan not found: {plan_key}")
        
        if not plan.is_active:
            raise ValueError(f"Plan is not active: {plan_key}")
        
        if billing_interval not in plan.intervals:
            raise ValueError(f"Plan does not support {billing_interval} billing")
        
        # Get or create commercial account
        commercial_account = await self.get_or_create_commercial_account(db, organization_id)
        
        # Calculate dates
        now = utcnow()
        trial_days = trial_days or 14
        trial_ends_at = now + timedelta(days=14)
        
        # Determine billing interval
        if billing_interval not in ("monthly", "annual"):
            billing_interval = "monthly"
        
        # Set period
        if billing_interval == "annual":
            period_end = now + timedelta(days=365)
            price_cents = plan.annual_price_cents
        else:
            period_end = now + timedelta(days=30)
            price_cents = plan.monthly_price_cents
        
        subscription = Subscription(
            organization_id=organization_id,
            plan_id=plan.id,
            commercial_account_id=commercial_account.id,
            state="trialing",
            billing_interval="monthly",  # We bill monthly even for annual (can be enhanced)
            price_cents=plan.monthly_price_cents,
            currency=plan.currency,
            trial_started_at=utcnow(),
            trial_ends_at=trial_ends_at,
            current_period_start=utcnow(),
            current_period_end=trial_ends_at,  # Trial period
            auto_renew=True,
            metadata_json={"trial": True},
        )
        
        db.add(subscription)
        await db.flush()
        
        # Create entitlements from plan
        await self._sync_entitlements_from_plan(db, organization_id, subscription.id)
        
        # Log event
        await self._log_subscription_event(
            db,
            organization_id=organization_id,
            subscription_id=subscription.id,
            event_type="created",
            from_state=None,
            to_state="trialing",
            actor_id=created_by,
        )
        
        await audit_service.log(
            db,
            organization_id=organization_id,
            action="subscription.created",
            actor_id=created_by,
            resource_type="subscription",
            resource_id=subscription.id,
            details={"plan_key": plan_key, "trial": True},
        )
        
        await event_service.emit(
            db,
            name="subscription.created",
            actor_id=created_by,
            organization_id=organization_id,
            payload={"subscription_id": subscription.id, "plan_key": plan_key},
        )
        
        logger.info(f"Created subscription for org {organization_id}: {plan_key}")
        return subscription

    async def _sync_entitlements_from_plan(
        self,
        db: AsyncSession,
        organization_id: str,
        subscription_id: str,
    ) -> None:
        """Sync entitlements from plan to organization."""
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return
        
        plan = await self.get_plan(db, subscription.plan_id)
        if not plan:
            return
        
        # Clear existing plan-sourced entitlements
        await db.execute(
            Entitlement.__table__.delete().where(
                Entitlement.organization_id == organization_id,
                Entitlement.source == "plan",
            )
        )
        
        # Create new entitlements from plan
        for key, config in plan.entitlements.items():
            if isinstance(config, dict):
                ent_type = config.get("type", "limit")
                value = config.get("value")
            else:
                ent_type = "limit"
                value = config
            
            if ent_type == "limit":
                numeric_value = float(value) if value is not None else None
                boolean_value = None
                str_value = str(value) if value is not None else None
            elif isinstance(value, bool):
                boolean_value = value
                numeric_value = 1.0 if value else 0.0
                str_value = str(value).lower()
            else:
                str_value = str(value) if value is not None else None
                numeric_value = float(value) if value is not None else None
                boolean_value = None
            
            entitlement = Entitlement(
                organization_id=organization_id,
                key=key,
                entitlement_type=ent_type,
                value=str_value,
                numeric_value=numeric_value,
                boolean_value=boolean_value,
                source="plan",
                effective_from=utcnow(),
            )
            db.add(entitlement)
        
        await db.flush()

    async def get_subscription(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Optional[Subscription]:
        """Get the active subscription for an organization."""
        result = await db.execute(
            select(Subscription).where(
                Subscription.organization_id == organization_id,
                Subscription.state.in_(["trialing", "active", "past_due", "grace"]),
            ).order_by(Subscription.created_at.desc())
        )
        return result.scalars().first()

    async def get_subscription_by_id(
        self,
        db: AsyncSession,
        subscription_id: str,
    ) -> Optional[Subscription]:
        """Get subscription by ID."""
        return await db.get(Subscription, subscription_id)

    async def activate_subscription(
        self,
        db: AsyncSession,
        subscription_id: str,
        activated_by: Optional[str] = None,
    ) -> Optional[Subscription]:
        """Activate a subscription (end trial)."""
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return None
        
        if subscription.state not in ("trialing", "active"):
            raise ValueError(f"Cannot activate subscription in state: {subscription.state}")
        
        subscription.state = "active"
        subscription.current_period_start = utcnow()
        
        if subscription.billing_interval == "annual":
            subscription.current_period_end = utcnow() + timedelta(days=365)
        else:
            subscription.current_period_end = utcnow() + timedelta(days=30)
        
        subscription.trial_ends_at = None
        
        await self._sync_entitlements_from_plan(db, subscription.organization_id, subscription.id)
        
        await self._log_subscription_event(
            db,
            organization_id=subscription.organization_id,
            subscription_id=subscription.id,
            event_type="activated",
            from_state="trialing",
            to_state="active",
            actor_id=activated_by,
        )
        
        await db.flush()
        return subscription

    async def renew_subscription(
        self,
        db: AsyncSession,
        subscription_id: str,
    ) -> Optional[Subscription]:
        """Renew a subscription for a new period."""
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return None
        
        if subscription.state not in ("active", "past_due", "grace"):
            raise ValueError(f"Cannot renew subscription in state: {subscription.state}")
        
        # Calculate new period
        now = utcnow()
        if subscription.billing_interval == "annual":
            subscription.current_period_start = subscription.current_period_end
            subscription.current_period_end = now + timedelta(days=365)
        else:
            subscription.current_period_start = subscription.current_period_end
            subscription.current_period_end = now + timedelta(days=30)
        
        subscription.state = "active"
        subscription.in_grace_period = False
        subscription.grace_period_ends_at = None
        
        await self._sync_entitlements_from_plan(db, subscription.organization_id, subscription.id)
        
        await self._log_subscription_event(
            db,
            organization_id=subscription.organization_id,
            subscription_id=subscription.id,
            event_type="renewed",
            from_state=subscription.state,
            to_state="active",
        )
        
        await db.flush()
        return subscription

    async def cancel_subscription(
        self,
        db: AsyncSession,
        subscription_id: str,
        cancelled_by: Optional[str] = None,
        reason: Optional[str] = None,
        immediate: bool = False,
    ) -> Optional[Subscription]:
        """Cancel a subscription."""
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return None
        
        if subscription.state in ("cancelled", "expired"):
            raise ValueError(f"Subscription already cancelled or expired")
        
        if immediate:
            subscription.state = "cancelled"
            subscription.cancelled_at = utcnow()
            subscription.cancellation_reason = reason
            subscription.auto_renew = False
        else:
            subscription.cancel_at_period_end = True
            subscription.cancellation_reason = reason
        
        await self._log_subscription_event(
            db,
            organization_id=subscription.organization_id,
            subscription_id=subscription.id,
            event_type="cancelled",
            from_state=subscription.state,
            to_state="cancelled" if immediate else "cancel_pending",
            actor_id=cancelled_by,
            details={"reason": reason, "immediate": immediate},
        )
        
        await audit_service.log(
            db,
            organization_id=subscription.organization_id,
            action="subscription.cancelled",
            actor_id=cancelled_by,
            resource_type="subscription",
            resource_id=subscription.id,
            details={"reason": reason, "immediate": immediate},
        )
        
        await db.flush()
        return subscription

    async def change_plan(
        self,
        db: AsyncSession,
        subscription_id: str,
        new_plan_key: str,
        effective: str = "immediate",  # immediate|next_period
        changed_by: Optional[str] = None,
    ) -> Optional[Subscription]:
        """Change subscription plan."""
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return None
        
        new_plan = await self.get_plan_by_key(db, new_plan_key)
        if not new_plan:
            raise ValueError(f"Plan not found: {new_plan_key}")
        
        if not new_plan.is_active:
            raise ValueError(f"Plan is not active: {new_plan_key}")
        
        old_plan = await self.get_plan(db, subscription.plan_id)
        
        if effective == "immediate":
            subscription.plan_id = new_plan.id
            subscription.price_cents = new_plan.monthly_price_cents if subscription.billing_interval == "monthly" else new_plan.annual_price_cents
            await self._sync_entitlements_from_plan(db, subscription.organization_id, subscription.id)
        
        await self._log_subscription_event(
            db,
            organization_id=subscription.organization_id,
            subscription_id=subscription.id,
            event_type="upgraded" if (new_plan.monthly_price_cents > (old_plan.monthly_price_cents if old_plan else 0)) else "downgraded",
            from_state=subscription.state,
            to_state=subscription.state,
            actor_id=changed_by,
            details={"old_plan": old_plan.key if old_plan else None, "new_plan": new_plan_key},
        )
        
        await db.flush()
        return subscription

    # ------------------------------------------------------------------ Usage Tracking

    async def record_usage(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        entitlement_key: str,
        quantity: float,
        period: Optional[str] = None,
        event_id: Optional[str] = None,
        event_source: str = "api",
        event_timestamp: Optional[datetime] = None,
        metadata_json: Optional[dict] = None,
    ) -> UsageRecord:
        """Record usage against an entitlement (idempotent)."""
        
        if not period:
            period = utcnow().strftime("%Y-%m")
        
        if not event_id:
            event_id = f"{organization_id}:{entitlement_key}:{period}:{secrets.token_hex(8)}"
        
        # Check for existing (idempotency)
        existing = await db.execute(
            select(UsageRecord).where(
                UsageRecord.organization_id == organization_id,
                UsageRecord.entitlement_key == entitlement_key,
                UsageRecord.period == period,
                UsageRecord.event_id == event_id,
            )
        )
        if existing.scalars().first():
            return existing.scalars().first()
        
        # Get entitlement
        entitlement_result = await db.execute(
            select(Entitlement).where(
                Entitlement.organization_id == organization_id,
                Entitlement.key == entitlement_key,
            )
        )
        entitlement = entitlement_result.scalar_one_or_none()
        
        subscription = await self.get_subscription(db, organization_id)
        
        usage = UsageRecord(
            organization_id=organization_id,
            subscription_id=subscription.id if subscription else None,
            entitlement_id=entitlement.id if entitlement else None,
            entitlement_key=entitlement_key,
            period=period,
            quantity=quantity,
            event_id=event_id,
            event_source=event_source,
            event_timestamp=event_timestamp or utcnow(),
            metadata_json=metadata_json or {},
        )
        
        db.add(usage)
        await db.flush()
        return usage

    async def get_usage(
        self,
        db: AsyncSession,
        organization_id: str,
        entitlement_key: Optional[str] = None,
        period: Optional[str] = None,
    ) -> List[UsageRecord]:
        """Get usage records for an organization."""
        query = select(UsageRecord).where(UsageRecord.organization_id == organization_id)
        
        if entitlement_key:
            query = query.where(UsageRecord.entitlement_key == entitlement_key)
        
        if period:
            query = query.where(UsageRecord.period == period)
        else:
            # Default to current period
            period = utcnow().strftime("%Y-%m")
            query = query.where(UsageRecord.period == period)
        
        query = query.order_by(UsageRecord.event_timestamp.desc())
        result = await db.execute(query)
        return list(result.scalars().all())

    async def get_usage_summary(
        self,
        db: AsyncSession,
        organization_id: str,
        period: Optional[str] = None,
    ) -> dict:
        """Get aggregated usage summary for an organization."""
        if not period:
            period = utcnow().strftime("%Y-%m")
        
        usage = await self.get_usage(db, organization_id, period=period)
        
        summary = {}
        for u in usage:
            key = u.entitlement_key
            if key not in summary:
                summary[key] = {"quantity": 0, "unit": u.unit, "period": period}
            summary[key]["quantity"] += u.quantity
        
        return summary

    # ------------------------------------------------------------------ Invoicing & Payments

    async def generate_invoice(
        self,
        db: AsyncSession,
        subscription_id: str,
        period_start: datetime,
        period_end: datetime,
        created_by: Optional[str] = None,
    ) -> SubscriptionInvoice:
        """Generate an invoice for a subscription period."""
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            raise ValueError("Subscription not found")
        
        plan = await self.get_plan(db, subscription.plan_id)
        if not plan:
            raise ValueError("Plan not found")
        
        # Check if invoice already exists
        existing = await db.execute(
            select(SubscriptionInvoice).where(
                SubscriptionInvoice.subscription_id == subscription_id,
                SubscriptionInvoice.period_start == period_start,
                SubscriptionInvoice.period_end == period_end,
            )
        )
        if existing.scalars().first():
            raise ValueError("Invoice already exists for this period")
        
        # Calculate amounts
        if subscription.billing_interval == "annual":
            price_cents = plan.annual_price_cents
        else:
            price_cents = plan.monthly_price_cents
        
        # TODO: Add usage-based charges
        
        subtotal_cents = price_cents
        tax_cents = 0  # TODO: Calculate tax
        total_cents = subtotal_cents + tax_cents
        
        # Create invoice
        invoice = Invoice(
            organization_id=subscription.organization_id,
            direction="receivable",
            title=f"VCOS {plan.name} Subscription - {period_start.strftime('%B %Y')}",
            amount=total_cents / 100,
            currency=plan.currency,
            issued_at=utcnow().date(),
            due_at=(utcnow() + timedelta(days=30)).date(),
            status="issued",
            attributes={"subscription_id": subscription_id, "plan_key": plan.key},
        )
        db.add(invoice)
        await db.flush()
        
        # Create subscription invoice link
        sub_invoice = SubscriptionInvoice(
            subscription_id=subscription_id,
            invoice_id=invoice.id,
            period_start=period_start,
            period_end=period_end,
            subtotal_cents=price_cents,
            tax_cents=0,
            total_cents=total_cents,
            currency=plan.currency,
            line_items=[
                {
                    "key": "subscription",
                    "description": f"{plan.name} Subscription ({period_start.strftime('%B %Y')})",
                    "quantity": 1,
                    "unit_price_cents": price_cents,
                    "total_cents": price_cents,
                }
            ],
            status="issued",
        )
        db.add(sub_invoice)
        await db.flush()
        
        # Update subscription status if needed
        if subscription.state == "trialing":
            subscription.state = "active"
        
        await self._log_subscription_event(
            db,
            organization_id=subscription.organization_id,
            subscription_id=subscription_id,
            event_type="invoice_issued",
            from_state=subscription.state,
            to_state=subscription.state,
            details={"invoice_id": invoice.id, "amount_cents": total_cents},
        )
        
        await audit_service.log(
            db,
            organization_id=subscription.organization_id,
            action="invoice.issued",
            actor_id=created_by,
            resource_type="invoice",
            resource_id=invoice.id,
            details={"subscription_id": subscription_id, "amount_cents": total_cents},
        )
        
        await event_service.emit(
            db,
            name="invoice.issued",
            organization_id=subscription.organization_id,
            payload={"invoice_id": invoice.id, "subscription_id": subscription_id},
        )
        
        await db.flush()
        return sub_invoice

    async def record_payment(
        self,
        db: AsyncSession,
        *,
        subscription_id: str,
        subscription_invoice_id: str,
        amount_cents: int,
        currency: str,
        payment_provider: str,
        payment_provider_payment_id: str,
        method: str = "card",
        status: str = "completed",
        paid_at: Optional[datetime] = None,
    ) -> SubscriptionPayment:
        """Record a payment for a subscription invoice."""
        
        # Create payment record
        payment = Payment(
            organization_id=(await db.get(Subscription, subscription_id)).organization_id,
            invoice_id=(await db.get(SubscriptionInvoice, subscription_invoice_id)).invoice_id,
            amount=amount_cents / 100,
            currency=currency,
            method=method,
            status=status,
            paid_at=paid_at or utcnow(),
            reference=payment_provider_payment_id,
        )
        db.add(payment)
        await db.flush()
        
        # Create subscription payment link
        sub_payment = SubscriptionPayment(
            subscription_id=subscription_id,
            subscription_invoice_id=subscription_invoice_id,
            payment_id=payment.id,
            amount_cents=amount_cents,
            currency=currency,
            status=status,
        )
        db.add(sub_payment)
        await db.flush()
        
        # Update invoice status
        invoice = await db.get(Invoice, (await db.get(SubscriptionInvoice, subscription_invoice_id)).invoice_id)
        if invoice:
            # Check if fully paid
            paid_result = await db.execute(
                select(func.sum(Payment.amount)).where(
                    Payment.invoice_id == invoice.id,
                    Payment.status == "completed",
                )
            )
            total_paid = paid_result.scalar() or 0
            if total_paid >= invoice.amount:
                invoice.status = "paid"
                invoice.paid_at = utcnow()
                invoice.payment_reference = payment_provider_payment_id
        
        await self._log_subscription_event(
            db,
            organization_id=(await db.get(Subscription, subscription_id)).organization_id,
            subscription_id=subscription_id,
            event_type="payment_succeeded",
            from_state=None,
            to_state=None,
            details={"payment_id": payment.id, "amount_cents": amount_cents},
        )
        
        await audit_service.log(
            db,
            organization_id=(await db.get(Subscription, subscription_id)).organization_id,
            action="payment.succeeded",
            resource_type="payment",
            resource_id=payment.id,
            details={"subscription_id": subscription_id, "amount_cents": amount_cents},
        )
        
        await event_service.emit(
            db,
            name="payment.succeeded",
            organization_id=(await db.get(Subscription, subscription_id)).organization_id,
            payload={"payment_id": payment.id, "subscription_id": subscription_id},
        )
        
        await db.flush()
        return sub_payment

    async def handle_payment_failed(
        self,
        db: AsyncSession,
        subscription_id: str,
        invoice_id: str,
        error: str,
    ) -> None:
        """Handle a failed payment."""
        subscription = await db.get(Subscription, subscription_id)
        if not subscription:
            return
        
        subscription.state = "past_due"
        subscription.grace_period_ends_at = utcnow() + timedelta(days=14)  # 14-day grace period
        subscription.in_grace_period = True
        
        await self._log_subscription_event(
            db,
            organization_id=subscription.organization_id,
            subscription_id=subscription_id,
            event_type="payment_failed",
            from_state="active",
            to_state="past_due",
            details={"invoice_id": invoice_id, "error": error},
        )
        
        await audit_service.log(
            db,
            organization_id=subscription.organization_id,
            action="payment.failed",
            resource_type="subscription",
            resource_id=subscription_id,
            severity="warning",
            details={"invoice_id": invoice_id, "error": error},
        )
        
        await event_service.emit(
            db,
            name="payment.failed",
            organization_id=subscription.organization_id,
            payload={"subscription_id": subscription_id, "invoice_id": invoice_id, "error": error},
        )
        
        await notification_service.create(
            db,
            organization_id=subscription.organization_id,
            recipient_id=subscription.organization_id,  # Would need admin user
            type="billing",
            title="Payment Failed",
            body=f"Payment for subscription failed: {error}",
            priority="high",
            link=f"/billing/subscriptions/{subscription_id}",
        )
        
        await db.flush()

    # ------------------------------------------------------------------ Provisioning

    async def start_provisioning(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        plan_key: str,
        admin_user_id: Optional[str] = None,
        admin_email: Optional[str] = None,
        domain: Optional[str] = None,
    ) -> Provisioning:
        """Start the provisioning process for a new organization."""
        
        # Check if already provisioning
        existing = await db.execute(
            select(Provisioning).where(Provisioning.organization_id == organization_id)
        )
        if existing.scalars().first():
            raise ValueError("Organization already has a provisioning in progress")
        
        # Create subscription first
        subscription = await self.create_subscription(
            db,
            organization_id=organization_id,
            plan_key=plan_key,
            created_by=admin_user_id,
        )
        
        # Create commercial account
        commercial_account = await self.get_or_create_commercial_account(db, organization_id)
        
        # Create provisioning
        provisioning = Provisioning(
            organization_id=organization_id,
            subscription_id=subscription.id,
            commercial_account_id=commercial_account.id,
            state="provisioning",
            admin_user_id=admin_user_id,
            admin_email=admin_email,
            domain=domain,
            steps=[
                {"step": "commercial_account", "state": "completed", "completed_at": utcnow().isoformat()},
                {"step": "subscription", "state": "completed", "completed_at": utcnow().isoformat()},
                {"step": "admin_user", "state": "pending"},
                {"step": "security", "state": "pending"},
                {"step": "domain", "state": "pending"},
                {"step": "employees", "state": "pending"},
                {"step": "integrations", "state": "pending"},
                {"step": "import", "state": "pending"},
                {"step": "validation", "state": "pending"},
                {"step": "activation", "state": "pending"},
            ],
        )
        
        db.add(provisioning)
        await db.flush()
        
        # Create provisioning steps
        steps = [
            "commercial_account",
            "subscription",
            "admin_user",
            "security",
            "domain",
            "employees",
            "integrations",
            "import",
            "validation",
            "activation",
        ]
        
        for i, step in enumerate(steps):
            step_state = "completed" if i < 2 else "pending"
            step_obj = ProvisioningStep(
                provisioning_id=provisioning.id,
                step=step,
                state=step_state,
                completed_at=utcnow() if step_state == "completed" else None,
            )
            db.add(step_obj)
        
        await db.flush()
        
        logger.info(f"Started provisioning for org {organization_id}")
        return provisioning

    async def get_provisioning(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Optional[Provisioning]:
        """Get provisioning for an organization."""
        result = await db.execute(
            select(Provisioning).where(Provisioning.organization_id == organization_id)
        )
        return result.scalar_one_or_none()

    async def complete_provisioning_step(
        self,
        db: AsyncSession,
        provisioning_id: str,
        step: str,
        success: bool,
        output: Optional[dict] = None,
        error: Optional[str] = None,
    ) -> Optional[ProvisioningStep]:
        """Complete a provisioning step."""
        result = await db.execute(
            select(ProvisioningStep).where(
                ProvisioningStep.provisioning_id == provisioning_id,
                ProvisioningStep.step == step,
            )
        )
        prov_step = result.scalar_one_or_none()
        if not prov_step:
            return None
        
        prov_step.state = "completed" if success else "failed"
        prov_step.completed_at = utcnow()
        prov_step.error = error
        prov_step.output_json = output or {}
        
        # Update provisioning state
        provisioning = await db.get(Provisioning, provisioning_id)
        if provisioning:
            # Update steps list
            for s in provisioning.steps:
                if s["step"] == step:
                    s["state"] = "completed" if success else "failed"
                    if success:
                        s["completed_at"] = utcnow().isoformat()
                    else:
                        s["error"] = error
            
            # Check if all steps completed
            all_completed = all(s["state"] == "completed" for s in provisioning.steps)
            if all_completed:
                provisioning.state = "validation"
                provisioning.current_step = "validation"
        
        await db.flush()
        return prov_step

    async def validate_and_activate(
        self,
        db: AsyncSession,
        organization_id: str,
        validated_by: Optional[str] = None,
    ) -> Optional[Provisioning]:
        """Validate provisioning and activate organization."""
        provisioning = await self.get_provisioning(db, organization_id)
        if not provisioning:
            return None
        
        # Run validation checks
        validation_errors = []
        
        # Check admin user
        if not provisioning.admin_user_id:
            validation_errors.append("No administrator user configured")
        
        # Check domain
        if provisioning.domain and not provisioning.domain_verified:
            validation_errors.append("Domain not verified")
        
        # Check security policy
        if not provisioning.security_policy_applied:
            validation_errors.append("Security policy not applied")
        
        # Check employees
        if provisioning.employees_imported == 0:
            validation_errors.append("No employees imported")
        
        # Check subscription
        subscription = await self.get_subscription(db, organization_id)
        if not subscription or subscription.state not in ("trialing", "active"):
            validation_errors.append("No active subscription")
        
        provisioning.validation_errors = validation_errors
        provisioning.validation_passed = len(validation_errors) == 0
        provisioning.validated_at = utcnow()
        
        if provisioning.validation_passed:
            # Activate
            provisioning.state = "active"
            provisioning.activated_at = utcnow()
            provisioning.activated_by = validated_by
            
            # Activate subscription if in trial
            if subscription and subscription.state == "trialing":
                await self.activate_subscription(db, subscription.id, validated_by)
            
            await audit_service.log(
                db,
                organization_id=organization_id,
                action="provisioning.activated",
                actor_id=validated_by,
                resource_type="provisioning",
                resource_id=provisioning.id,
            )
            
            await event_service.emit(
                db,
                name="provisioning.activated",
                organization_id=organization_id,
                payload={"provisioning_id": provisioning.id},
            )
        else:
            provisioning.state = "validation"
        
        await db.flush()
        return provisioning

    # ------------------------------------------------------------------ Domain Verification

    async def start_domain_verification(
        self,
        db: AsyncSession,
        organization_id: str,
        domain: str,
    ) -> Provisioning:
        """Start domain verification process."""
        provisioning = await self.get_provisioning(db, organization_id)
        if not provisioning:
            raise ValueError("No provisioning found for organization")
        
        token = secrets.token_urlsafe(32)
        provisioning.domain = domain
        provisioning.domain_verification_token = token
        
        await db.flush()
        
        # TODO: Send verification email with token
        # For now, just return the provisioning
        
        return provisioning

    async def verify_domain(
        self,
        db: AsyncSession,
        organization_id: str,
        token: str,
    ) -> bool:
        """Verify domain ownership."""
        provisioning = await self.get_provisioning(db, organization_id)
        if not provisioning or provisioning.domain_verification_token != token:
            return False
        
        provisioning.domain_verified = True
        provisioning.domain_verified_at = utcnow()
        
        await self.complete_provisioning_step(db, provisioning.id, "domain", True)
        
        await db.flush()
        return True

    # ------------------------------------------------------------------ Event Logging

    async def _log_subscription_event(
        self,
        db: AsyncSession,
        organization_id: str,
        subscription_id: str,
        event_type: str,
        from_state: Optional[str] = None,
        to_state: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_type: str = "user",
        details: Optional[dict] = None,
) -> SubscriptionEvent:
        """Log a subscription lifecycle event."""

        event = SubscriptionEvent(
            organization_id=organization_id,
            subscription_id=subscription_id,
            event_type=event_type,
            from_state=from_state,
            to_state=to_state,
            actor_id=actor_id,
            actor_type=actor_type,
            details_json=details or {},
        )

        db.add(event)
        await db.flush()
        return event

    # ------------------------------------------------------------------ Stripe Webhook Handling

    async def handle_stripe_webhook(
        self,
        db: AsyncSession,
        payload: dict,
        signature: str,
    ) -> dict:
        """Handle incoming Stripe webhook events.
        
        Processes subscription lifecycle events:
        - customer.subscription.created
        - customer.subscription.updated
        - customer.subscription.deleted
        - customer.subscription.trial_will_end
        - invoice.payment_succeeded
        - invoice.payment_failed
        - invoice.upcoming
        - payment_method.attached
        - payment_method.detached
        """
        import stripe
        from app.core.config import get_settings
        
        settings = get_settings()
        webhook_secret = settings.stripe_webhook_secret
        
        if not webhook_secret:
            logger.error("Stripe webhook secret not configured")
            return {"error": "Webhook secret not configured"}
        
        try:
            event = stripe.Webhook.construct_event(
                payload, signature, webhook_secret
            )
        except ValueError as e:
            logger.error(f"Invalid Stripe payload: {e}")
            return {"error": "Invalid payload"}
        except stripe.error.SignatureVerificationError as e:
            logger.error(f"Stripe signature verification failed: {e}")
            return {"error": "Invalid signature"}
        
        event_type = event["type"]
        data = event["data"]["object"]
        
        logger.info(f"Processing Stripe webhook: {event_type}")
        
        # Route to appropriate handler
        if event_type == "customer.subscription.created":
            await self._handle_subscription_created(db, data)
        elif event_type == "customer.subscription.updated":
            await self._handle_subscription_updated(db, data)
        elif event_type == "customer.subscription.deleted":
            await self._handle_subscription_deleted(db, data)
        elif event_type == "customer.subscription.trial_will_end":
            await self._handle_trial_will_end(db, data)
        elif event_type == "invoice.payment_succeeded":
            await self._handle_payment_succeeded(db, data)
        elif event_type == "invoice.payment_failed":
            await self._handle_payment_failed(db, data)
        elif event_type == "invoice.upcoming":
            await self._handle_invoice_upcoming(db, data)
        elif event_type == "payment_method.attached":
            await self._handle_payment_method_attached(db, data)
        elif event_type == "payment_method.detached":
            await self._handle_payment_method_detached(db, data)
        else:
            logger.info(f"Unhandled Stripe event type: {event_type}")
        
        return {"received": True, "event_type": event_type}

    async def _handle_subscription_created(self, db: AsyncSession, data: dict):
        """Handle subscription created event."""
        subscription_id = data.get("id")
        customer_id = data.get("customer")
        status = data.get("status")
        plan_id = data.get("plan", {}).get("id") if data.get("plan") else None
        
        logger.info(f"Subscription created: {subscription_id} for customer {customer_id}")
        
        # Find commercial account by Stripe customer ID
        from app.models.finance import CommercialAccount, Subscription
        from sqlalchemy import select
        
        result = await db.execute(
            select(CommercialAccount).where(CommercialAccount.stripe_customer_id == customer_id)
        )
        account = result.scalars().first()
        
        if account:
            # Create or update local subscription
            local_sub = await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
            )
            local_sub = local_sub.scalars().first()
            
            if not local_sub:
                local_sub = Subscription(
                    organization_id=account.organization_id,
                    commercial_account_id=account.id,
                    stripe_subscription_id=subscription_id,
                    stripe_customer_id=customer_id,
                    stripe_price_id=plan_id,
                    state=status,
                    current_period_start=datetime.fromtimestamp(data.get("current_period_start", 0), tz=timezone.utc),
                    current_period_end=datetime.fromtimestamp(data.get("current_period_end", 0), tz=timezone.utc),
                    cancel_at_period_end=data.get("cancel_at_period_end", False),
                )
                db.add(local_sub)
                await db.flush()
                
                await self._log_subscription_event(
                    db, account.organization_id, local_sub.id,
                    "created", None, status, actor_type="stripe_webhook", details=data
                )
            else:
                local_sub.state = status
                local_sub.current_period_start = datetime.fromtimestamp(data.get("current_period_start", 0), tz=timezone.utc)
                local_sub.current_period_end = datetime.fromtimestamp(data.get("current_period_end", 0), tz=timezone.utc)
                local_sub.cancel_at_period_end = data.get("cancel_at_period_end", False)
                
                await self._log_subscription_event(
                    db, account.organization_id, local_sub.id,
                    "updated", None, status, actor_type="stripe_webhook", details=data
                )

    async def _handle_subscription_updated(self, db: AsyncSession, data: dict):
        """Handle subscription updated event."""
        subscription_id = data.get("id")
        status = data.get("status")
        plan_id = data.get("plan", {}).get("id") if data.get("plan") else None
        
        logger.info(f"Subscription updated: {subscription_id} -> {status}")
        
        from app.models.finance import Subscription
        from sqlalchemy import select
        
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
        )
        subscription = result.scalars().first()
        
        if subscription:
            old_state = subscription.state
            subscription.state = status
            subscription.current_period_start = datetime.fromtimestamp(data.get("current_period_start", 0), tz=timezone.utc)
            subscription.current_period_end = datetime.fromtimestamp(data.get("current_period_end", 0), tz=timezone.utc)
            subscription.cancel_at_period_end = data.get("cancel_at_period_end", False)
            if plan_id:
                subscription.stripe_price_id = plan_id
            
            await self._log_subscription_event(
                db, subscription.organization_id, subscription.id,
                "updated", old_state, status, actor_type="stripe_webhook", details=data
            )
            
            # Update entitlements if plan changed
            if plan_id:
                await self._sync_entitlements_from_stripe(db, subscription)

    async def _handle_subscription_deleted(self, db: AsyncSession, data: dict):
        """Handle subscription deleted/cancelled event."""
        subscription_id = data.get("id")
        
        logger.info(f"Subscription deleted: {subscription_id}")
        
        from app.models.finance import Subscription
        from sqlalchemy import select
        
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
        )
        subscription = result.scalars().first()
        
        if subscription:
            old_state = subscription.state
            subscription.state = "canceled"
            subscription.canceled_at = utcnow()
            
            await self._log_subscription_event(
                db, subscription.organization_id, subscription.id,
                "canceled", old_state, "canceled", actor_type="stripe_webhook", details=data
            )

    async def _handle_trial_will_end(self, db: AsyncSession, data: dict):
        """Handle trial ending soon event."""
        subscription_id = data.get("id")
        trial_end = data.get("trial_end")
        
        logger.info(f"Trial ending for subscription: {subscription_id} at {trial_end}")
        
        from app.models.finance import Subscription
        from sqlalchemy import select
        
        result = await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
        )
        subscription = result.scalars().first()
        
        if subscription:
            subscription.trial_end = datetime.fromtimestamp(trial_end, tz=timezone.utc) if trial_end else None
            await self._log_subscription_event(
                db, subscription.organization_id, subscription.id,
                "trial_will_end", None, "trialing", actor_type="stripe_webhook", details=data
            )
            
            # Notify organization admin
            await self._notify_trial_ending(db, subscription)

    async def _handle_payment_succeeded(self, db: AsyncSession, data: dict):
        """Handle successful payment event."""
        subscription_id = data.get("subscription")
        amount = data.get("amount_paid", 0)
        
        logger.info(f"Payment succeeded for subscription: {subscription_id}, amount: {amount}")
        
        if subscription_id:
            from app.models.finance import Subscription
            from sqlalchemy import select
            
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
            )
            subscription = result.scalars().first()
            
            if subscription:
                await self._log_subscription_event(
                    db, subscription.organization_id, subscription.id,
                    "payment_succeeded", None, subscription.state, actor_type="stripe_webhook", details=data
                )

    async def _handle_payment_failed(self, db: AsyncSession, data: dict):
        """Handle failed payment event."""
        subscription_id = data.get("subscription")
        attempt_count = data.get("attempt_count", 1)
        
        logger.warning(f"Payment failed for subscription: {subscription_id}, attempt: {attempt_count}")
        
        if subscription_id:
            from app.models.finance import Subscription
            from sqlalchemy import select
            
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
            )
            subscription = result.scalars().first()
            
            if subscription:
                await self._log_subscription_event(
                    db, subscription.organization_id, subscription.id,
                    "payment_failed", None, subscription.state, actor_type="stripe_webhook", details=data
                )
                
                # If too many failed attempts, mark as past_due
                if attempt_count >= 3:
                    subscription.state = "past_due"
                    await self._log_subscription_event(
                        db, subscription.organization_id, subscription.id,
                        "past_due", "active", "past_due", actor_type="stripe_webhook", details=data
                    )
                    await self._notify_payment_failed(db, subscription)

    async def _handle_invoice_upcoming(self, db: AsyncSession, data: dict):
        """Handle upcoming invoice event (renewal reminder)."""
        subscription_id = data.get("subscription")
        amount_due = data.get("amount_due", 0)
        period_end = data.get("period_end")
        
        logger.info(f"Upcoming invoice for subscription: {subscription_id}, amount: {amount_due}")
        
        if subscription_id:
            from app.models.finance import Subscription
            from sqlalchemy import select
            
            result = await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == subscription_id)
            )
            subscription = result.scalars().first()
            
            if subscription:
                await self._notify_upcoming_renewal(db, subscription, amount_due, period_end)

    async def _handle_payment_method_attached(self, db: AsyncSession, data: dict):
        """Handle payment method attached event."""
        customer_id = data.get("customer")
        payment_method_id = data.get("id")
        
        logger.info(f"Payment method attached: {payment_method_id} to customer {customer_id}")
        
        from app.models.finance import CommercialAccount
        from sqlalchemy import select
        
        result = await db.execute(
            select(CommercialAccount).where(CommercialAccount.stripe_customer_id == customer_id)
        )
        account = result.scalars().first()
        
        if account:
            account.default_payment_method_id = payment_method_id
            await self._log_subscription_event(
                db, account.organization_id, None,
                "payment_method_attached", None, None, actor_type="stripe_webhook", details=data
            )

    async def _handle_payment_method_detached(self, db: AsyncSession, data: dict):
        """Handle payment method detached event."""
        customer_id = data.get("customer")
        payment_method_id = data.get("id")
        
        logger.info(f"Payment method detached: {payment_method_id} from customer {customer_id}")
        
        from app.models.finance import CommercialAccount
        from sqlalchemy import select
        
        result = await db.execute(
            select(CommercialAccount).where(CommercialAccount.stripe_customer_id == customer_id)
        )
        account = result.scalars().first()
        
        if account and account.default_payment_method_id == payment_method_id:
            account.default_payment_method_id = None

    async def _sync_entitlements_from_stripe(self, db: AsyncSession, subscription: 'Subscription'):
        """Sync entitlements based on Stripe price/plan."""
        # This would map Stripe price IDs to local plans and update entitlements
        pass

    async def _notify_trial_ending(self, db: AsyncSession, subscription: 'Subscription'):
        """Notify organization admins that trial is ending."""
        from app.services.notification_service import notification_service
        from app.models.organization import Organization
        from sqlalchemy import select
        
        result = await db.execute(
            select(Organization).where(Organization.id == subscription.organization_id)
        )
        org = result.scalars().first()
        
        if org:
            await notification_service.create_notification(
                db,
                organization_id=org.id,
                user_id=None,  # Broadcast to admins
                type="trial_ending",
                title="Your trial is ending soon",
                body=f"Your trial ends on {subscription.trial_end.strftime('%B %d, %Y') if subscription.trial_end else 'soon'}. Upgrade to continue using VCOS.",
                priority="high",
                link="/settings/billing",
            )

    async def _notify_payment_failed(self, db: AsyncSession, subscription: 'Subscription'):
        """Notify organization admins of failed payment."""
        from app.services.notification_service import notification_service
        from app.models.organization import Organization
        from sqlalchemy import select
        
        result = await db.execute(
            select(Organization).where(Organization.id == subscription.organization_id)
        )
        org = result.scalars().first()
        
        if org:
            await notification_service.create_notification(
                db,
                organization_id=org.id,
                user_id=None,
                type="payment_failed",
                title="Payment failed - Action required",
                body="Your recent payment failed. Please update your payment method to avoid service interruption.",
                priority="urgent",
                link="/settings/billing",
            )

    async def _notify_upcoming_renewal(self, db: AsyncSession, subscription: 'Subscription', amount_due: int, period_end: int):
        """Notify organization admins of upcoming renewal."""
        from app.services.notification_service import notification_service
        from app.models.organization import Organization
        from sqlalchemy import select
        
        result = await db.execute(
            select(Organization).where(Organization.id == subscription.organization_id)
        )
        org = result.scalars().first()
        
        if org:
            period_end_dt = datetime.fromtimestamp(period_end, tz=timezone.utc) if period_end else None
            await notification_service.create_notification(
                db,
                organization_id=org.id,
                user_id=None,
                type="upcoming_renewal",
                title="Upcoming subscription renewal",
                body=f"Your subscription renews on {period_end_dt.strftime('%B %d, %Y') if period_end_dt else 'soon'} for ${amount_due/100:.2f}.",
                priority="normal",
                link="/settings/billing",
            )


commercial_service = CommercialService()