"""Commercial API — Subscription, Billing, Plans, Entitlements, Provisioning, Usage Metering & Payment Reconciliation (Gate 27)."""

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any, Optional, List, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, EmailStr
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
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
from app.services.commercial_service import commercial_service
from app.services.usage_intake_service import usage_intake_service
from app.services.usage_aggregation_service import usage_aggregation_service
from app.services.pricing_engine import pricing_engine
from app.services.invoice_preview_service import invoice_preview_service
from app.services.reconciliation_service import reconciliation_service
from app.services.entitlement_enforcement import entitlement_enforcement_service
from app.services.payment_service import payment_service
from app.services.payment_webhook_service import payment_webhook_router
from app.schemas.usage_metering import (
    UsageEventCreate,
    UsageBatchRequest,
    UsageBatchResponse,
    UsageEventResponse,
    UsageMetricCode,
    UsageEventSource,
)
from app.services.payment_provider import PaymentProviderType

router = APIRouter(prefix="/commercial", tags=["Commercial"])


# =============================================================================
# Request/Response Models
# =============================================================================

class PlanResponse(BaseModel):
    id: str
    key: str
    name: str
    description: Optional[str] = None
    tier: str
    monthly_price_cents: int
    annual_price_cents: int
    currency: str
    intervals: List[str]
    entitlements: dict
    features: dict
    limits: dict
    is_active: bool
    is_public: bool
    trial_days: int


class PlanCreate(BaseModel):
    key: str = Field(..., pattern="^[a-z0-9_-]+$")
    name: str
    tier: str = Field(..., pattern="^(starter|professional|enterprise|custom)$")
    monthly_price_cents: int = Field(..., ge=0)
    annual_price_cents: int = Field(..., ge=0)
    description: Optional[str] = None
    entitlements: Optional[dict] = None
    features: Optional[dict] = None
    limits: Optional[dict] = None
    intervals: Optional[List[str]] = None
    trial_days: int = Field(14, ge=0, le=90)
    is_public: bool = True
    sort_order: int = 0


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    monthly_price_cents: Optional[int] = Field(None, ge=0)
    annual_price_cents: Optional[int] = Field(None, ge=0)
    entitlements: Optional[dict] = None
    features: Optional[dict] = None
    limits: Optional[dict] = None
    intervals: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None
    sort_order: Optional[int] = None
    trial_days: Optional[int] = Field(None, ge=0, le=90)


class EntitlementResponse(BaseModel):
    id: str
    organization_id: str
    key: str
    entitlement_type: str
    value: Optional[str] = None
    numeric_value: Optional[float] = None
    boolean_value: Optional[bool] = None
    source: str
    override_reason: Optional[str] = None
    override_by: Optional[str] = None
    override_expires_at: Optional[datetime] = None
    effective_from: datetime
    effective_to: Optional[datetime] = None


class EntitlementOverrideRequest(BaseModel):
    key: str
    entitlement_type: str = Field(..., pattern="^(limit|boolean|tier)$")
    value: Any
    source: str = "override"
    override_reason: Optional[str] = None
    override_expires_at: Optional[datetime] = None


class EntitlementCheckResponse(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    entitlement: Optional[dict] = None
    current: Optional[float] = None
    required: Optional[float] = None
    limit: Optional[float] = None
    usage: Optional[float] = None
    percentage: Optional[float] = None
    remaining: Optional[float] = None


class CommercialAccountResponse(BaseModel):
    id: str
    organization_id: str
    billing_contact_name: Optional[str] = None
    billing_contact_email: Optional[str] = None
    billing_contact_phone: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_postal_code: Optional[str] = None
    billing_country: Optional[str] = None
    tax_id: Optional[str] = None
    tax_id_type: Optional[str] = None
    tax_exempt: bool
    currency: str
    locale: str
    payment_provider: Optional[str] = None
    status: str
    metadata_json: dict


class CommercialAccountUpdate(BaseModel):
    billing_contact_name: Optional[str] = None
    billing_contact_email: Optional[EmailStr] = None
    billing_contact_phone: Optional[str] = None
    billing_address_line1: Optional[str] = None
    billing_address_line2: Optional[str] = None
    billing_city: Optional[str] = None
    billing_state: Optional[str] = None
    billing_postal_code: Optional[str] = None
    billing_country: Optional[str] = None
    tax_id: Optional[str] = None
    tax_id_type: Optional[str] = None
    tax_exempt: Optional[bool] = None
    tax_exempt_certificate: Optional[str] = None
    currency: Optional[str] = None
    locale: Optional[str] = None
    payment_provider: Optional[str] = None
    payment_method_token: Optional[str] = None
    payment_method_type: Optional[str] = None
    payment_method_details: Optional[dict] = None


class SubscriptionResponse(BaseModel):
    id: str
    organization_id: str
    plan_id: str
    plan_key: Optional[str] = None
    plan_name: Optional[str] = None
    plan_tier: Optional[str] = None
    commercial_account_id: Optional[str] = None
    state: str
    previous_state: Optional[str] = None
    billing_interval: str
    price_cents: int
    currency: str
    trial_started_at: Optional[datetime] = None
    trial_ends_at: Optional[datetime] = None
    current_period_start: datetime
    current_period_end: datetime
    auto_renew: bool
    cancel_at_period_end: bool
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None
    grace_period_ends_at: Optional[datetime] = None
    in_grace_period: bool
    payment_provider: Optional[str] = None
    payment_provider_subscription_id: Optional[str] = None
    payment_method_id: Optional[str] = None
    metadata_json: dict


class SubscriptionCreate(BaseModel):
    plan_key: str
    billing_interval: str = Field("monthly", pattern="^(monthly|annual)$")
    trial_days: Optional[int] = Field(14, ge=0, le=90)
    auto_renew: bool = True
    payment_provider: Optional[str] = None
    payment_method_id: Optional[str] = None


class SubscriptionChangePlan(BaseModel):
    new_plan_key: str
    effective: str = Field("immediate", pattern="^(immediate|next_period)$")


class SubscriptionCancel(BaseModel):
    reason: Optional[str] = None
    immediate: bool = False


class UsageRecordResponse(BaseModel):
    id: str
    organization_id: str
    subscription_id: Optional[str] = None
    entitlement_id: Optional[str] = None
    entitlement_key: str
    period: str
    quantity: float
    unit: str
    event_id: str
    event_source: str
    event_timestamp: datetime
    metadata_json: dict


class UsageRecordRequest(BaseModel):
    entitlement_key: str
    quantity: float = Field(..., ge=0)
    period: Optional[str] = None
    event_id: Optional[str] = None
    event_source: str = "api"
    event_timestamp: Optional[datetime] = None
    metadata_json: Optional[dict] = None


class UsageSummaryResponse(BaseModel):
    organization_id: str
    period: str
    usage: dict


class InvoiceResponse(BaseModel):
    id: str
    organization_id: str
    direction: str
    title: str
    amount: float
    tax_amount: float
    currency: str
    issued_at: Optional[datetime] = None
    due_at: Optional[datetime] = None
    status: str
    paid_at: Optional[datetime] = None
    payment_reference: Optional[str] = None
    attributes: dict


class SubscriptionInvoiceResponse(BaseModel):
    id: str
    subscription_id: str
    invoice_id: str
    period_start: datetime
    period_end: datetime
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    currency: str
    line_items: List[dict]
    status: str


class PaymentResponse(BaseModel):
    id: str
    organization_id: str
    invoice_id: Optional[str] = None
    amount: float
    currency: str
    method: str
    status: str
    paid_at: Optional[datetime] = None
    reference: Optional[str] = None
    external_id: Optional[str] = None


class SubscriptionPaymentResponse(BaseModel):
    id: str
    subscription_id: str
    subscription_invoice_id: Optional[str] = None
    payment_id: str
    amount_cents: int
    currency: str
    status: str


class PaymentRecordRequest(BaseModel):
    subscription_id: str
    subscription_invoice_id: str
    amount_cents: int = Field(..., gt=0)
    currency: str = "USD"
    payment_provider: str
    payment_provider_payment_id: str
    method: str = "card"
    status: str = "completed"
    paid_at: Optional[datetime] = None


class ProvisioningResponse(BaseModel):
    id: str
    organization_id: str
    subscription_id: Optional[str] = None
    commercial_account_id: Optional[str] = None
    state: str
    previous_state: Optional[str] = None
    steps: List[dict]
    current_step: Optional[str] = None
    admin_user_id: Optional[str] = None
    admin_email: Optional[str] = None
    domain: Optional[str] = None
    domain_verified: bool
    domain_verification_token: Optional[str] = None
    domain_verified_at: Optional[datetime] = None
    security_policy_applied: bool
    employees_imported: int
    employees_total: int
    integrations_configured: int
    integrations_total: int
    company_import_completed: bool
    company_import_records: int
    validation_passed: bool
    validation_errors: List[str]
    validated_at: Optional[datetime] = None
    activated_at: Optional[datetime] = None
    activated_by: Optional[str] = None
    suspended_at: Optional[datetime] = None
    suspended_reason: Optional[str] = None
    deactivated_at: Optional[datetime] = None
    deactivated_reason: Optional[str] = None
    metadata_json: dict


class ProvisioningStartRequest(BaseModel):
    plan_key: str
    admin_user_id: Optional[str] = None
    admin_email: Optional[EmailStr] = None
    domain: Optional[str] = None


class ProvisioningStepCompleteRequest(BaseModel):
    success: bool
    output: Optional[dict] = None
    error: Optional[str] = None


class DomainVerificationStartResponse(BaseModel):
    domain: str
    verification_token: str


class DomainVerificationRequest(BaseModel):
    token: str


class SubscriptionEventResponse(BaseModel):
    id: str
    organization_id: str
    subscription_id: str
    event_type: str
    from_state: Optional[str] = None
    to_state: Optional[str] = None
    actor_id: Optional[str] = None
    actor_type: str
    details_json: dict
    amount_cents: Optional[int] = None
    currency: Optional[str] = None
    invoice_id: Optional[str] = None
    occurred_at: datetime


class EntitlementCheckRequest(BaseModel):
    key: str
    required: Any = True


# =============================================================================
# Plans
# =============================================================================

@router.get("/plans", response_model=List[PlanResponse])
async def list_plans(
    tier: Optional[str] = Query(None, pattern="^(starter|professional|enterprise|custom)$"),
    is_active: Optional[bool] = None,
    is_public: Optional[bool] = None,
    user: User = Depends(require_permission("commercial:plans:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List all available plans."""
    plans = await commercial_service.list_plans(db, tier=tier, is_active=is_active, is_public=is_public)
    
    return [
        PlanResponse(
            id=p.id,
            key=p.key,
            name=p.name,
            description=p.description,
            tier=p.tier,
            monthly_price_cents=p.monthly_price_cents,
            annual_price_cents=p.annual_price_cents,
            currency=p.currency,
            intervals=p.intervals,
            entitlements=p.entitlements,
            features=p.features,
            limits=p.limits,
            is_active=p.is_active,
            is_public=p.is_public,
            trial_days=p.trial_days,
        )
        for p in plans
    ]


@router.post("/plans", response_model=PlanResponse, status_code=201)
async def create_plan(
    request: PlanCreate,
    user: User = Depends(require_permission("commercial:plans:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new plan (system admin only)."""
    plan = await commercial_service.create_plan(
        db,
        key=request.key,
        name=request.name,
        tier=request.tier,
        monthly_price_cents=request.monthly_price_cents,
        annual_price_cents=request.annual_price_cents,
        description=request.description,
        entitlements=request.entitlements,
        features=request.features,
        limits=request.limits,
        intervals=request.intervals,
        trial_days=request.trial_days,
        is_public=request.is_public,
        sort_order=request.sort_order,
        metadata_json={},
        created_by=user.id,
    )
    await db.commit()
    
    return PlanResponse(
        id=plan.id,
        key=plan.key,
        name=plan.name,
        description=plan.description,
        tier=plan.tier,
        monthly_price_cents=plan.monthly_price_cents,
        annual_price_cents=plan.annual_price_cents,
        currency=plan.currency,
        intervals=plan.intervals,
        entitlements=plan.entitlements,
        features=plan.features,
        limits=plan.limits,
        is_active=plan.is_active,
        is_public=plan.is_public,
        trial_days=plan.trial_days,
    )


@router.get("/plans/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: str,
    user: User = Depends(require_permission("commercial:plans:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get a plan by ID."""
    plan = await commercial_service.get_plan(db, plan_id)
    if not plan:
        raise HTTPException(404, "Plan not found")
    
    return PlanResponse(
        id=plan.id,
        key=plan.key,
        name=plan.name,
        description=plan.description,
        tier=plan.tier,
        monthly_price_cents=plan.monthly_price_cents,
        annual_price_cents=plan.annual_price_cents,
        currency=plan.currency,
        intervals=plan.intervals,
        entitlements=plan.entitlements,
        features=plan.features,
        limits=plan.limits,
        is_active=plan.is_active,
        is_public=plan.is_public,
        trial_days=plan.trial_days,
    )


@router.patch("/plans/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: str,
    request: PlanUpdate,
    user: User = Depends(require_permission("commercial:plans:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update a plan."""
    update_data = request.model_dump(exclude_unset=True)
    plan = await commercial_service.update_plan(db, plan_id, **update_data)
    await db.commit()
    
    if not plan:
        raise HTTPException(404, "Plan not found")
    
    return PlanResponse(
        id=plan.id,
        key=plan.key,
        name=plan.name,
        description=plan.description,
        tier=plan.tier,
        monthly_price_cents=plan.monthly_price_cents,
        annual_price_cents=plan.annual_price_cents,
        currency=plan.currency,
        intervals=plan.intervals,
        entitlements=plan.entitlements,
        features=plan.features,
        limits=plan.limits,
        is_active=plan.is_active,
        is_public=plan.is_public,
        trial_days=plan.trial_days,
    )


@router.delete("/plans/{plan_id}")
async def deactivate_plan(
    plan_id: str,
    reason: str = Body(..., embed=True),
    user: User = Depends(require_permission("commercial:plans:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Deactivate a plan."""
    plan = await commercial_service.deactivate_plan(db, plan_id, reason, deprecated_by=user.id)
    await db.commit()
    
    if not plan:
        raise HTTPException(404, "Plan not found")
    
    return {"success": True, "message": "Plan deactivated"}


# =============================================================================
# Entitlements
# =============================================================================

@router.get("/entitlements", response_model=dict)
async def get_entitlements(
    user: User = Depends(require_permission("commercial:entitlements:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get all resolved entitlements for the current organization."""
    entitlements = await commercial_service.resolve_entitlements(db, org.id)
    return entitlements


@router.get("/entitlements/{key}", response_model=EntitlementCheckResponse)
async def check_entitlement(
    key: str,
    required: Any = Query(True),
    user: User = Depends(require_permission("commercial:entitlements:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Check a specific entitlement."""
    result = await commercial_service.check_entitlement(db, org.id, key, required)
    return EntitlementCheckResponse(**result)


@router.post("/entitlements/check", response_model=EntitlementCheckResponse)
async def check_entitlement_post(
    request: EntitlementCheckRequest,
    user: User = Depends(require_permission("commercial:entitlements:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Check a specific entitlement (POST for complex required values)."""
    result = await commercial_service.check_entitlement(db, org.id, request.key, request.required)
    return EntitlementCheckResponse(**result)


@router.post("/entitlements/limit-check", response_model=EntitlementCheckResponse)
async def check_limit(
    key: str = Body(..., embed=True),
    current_usage: float = Body(..., embed=True, ge=0),
    user: User = Depends(require_permission("commercial:entitlements:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Check if current usage exceeds entitlement limit."""
    result = await commercial_service.check_limit(db, org.id, key, current_usage)
    return EntitlementCheckResponse(**result)


@router.post("/entitlements/override", response_model=EntitlementResponse)
async def set_entitlement_override(
    request: EntitlementOverrideRequest,
    user: User = Depends(require_permission("commercial:entitlements:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Set or update an entitlement override."""
    override = await commercial_service.set_entitlement_override(
        db,
        organization_id=org.id,
        key=request.key,
        entitlement_type=request.entitlement_type,
        value=request.value,
        source=request.source,
        override_reason=request.override_reason,
        override_by=user.id,
        expires_at=request.override_expires_at,
    )
    await db.commit()
    
    return EntitlementResponse(
        id=override.id,
        organization_id=override.organization_id,
        key=override.key,
        entitlement_type=override.entitlement_type,
        value=override.value,
        numeric_value=override.numeric_value,
        boolean_value=override.boolean_value,
        source=override.source,
        override_reason=override.override_reason,
        override_by=override.override_by,
        override_expires_at=override.override_expires_at,
        effective_from=override.effective_from,
        effective_to=override.effective_to,
    )


@router.delete("/entitlements/override/{key}")
async def remove_entitlement_override(
    key: str,
    user: User = Depends(require_permission("commercial:entitlements:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Remove an entitlement override."""
    success = await commercial_service.remove_entitlement_override(db, org.id, key)
    await db.commit()
    return {"success": success}


# =============================================================================
# Commercial Account
# =============================================================================

@router.get("/account", response_model=CommercialAccountResponse)
async def get_commercial_account(
    user: User = Depends(require_permission("commercial:account:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the organization's commercial account."""
    account = await commercial_service.get_or_create_commercial_account(db, org.id)
    
    return CommercialAccountResponse(
        id=account.id,
        organization_id=account.organization_id,
        billing_contact_name=account.billing_contact_name,
        billing_contact_email=account.billing_contact_email,
        billing_contact_phone=account.billing_contact_phone,
        billing_address_line1=account.billing_address_line1,
        billing_address_line2=account.billing_address_line2,
        billing_city=account.billing_city,
        billing_state=account.billing_state,
        billing_postal_code=account.billing_postal_code,
        billing_country=account.billing_country,
        tax_id=account.tax_id,
        tax_id_type=account.tax_id_type,
        tax_exempt=account.tax_exempt,
        currency=account.currency,
        locale=account.locale,
        payment_provider=account.payment_provider,
        status=account.status,
        metadata_json=account.metadata_json or {},
    )


@router.patch("/account", response_model=CommercialAccountResponse)
async def update_commercial_account(
    update: CommercialAccountUpdate,
    user: User = Depends(require_permission("commercial:account:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update the organization's commercial account."""
    update_data = update.model_dump(exclude_unset=True)
    account = await commercial_service.update_commercial_account(db, org.id, **update_data)
    await db.commit()
    
    if not account:
        raise HTTPException(404, "Commercial account not found")
    
    return CommercialAccountResponse(
        id=account.id,
        organization_id=account.organization_id,
        billing_contact_name=account.billing_contact_name,
        billing_contact_email=account.billing_contact_email,
        billing_contact_phone=account.billing_contact_phone,
        billing_address_line1=account.billing_address_line1,
        billing_address_line2=account.billing_address_line2,
        billing_city=account.billing_city,
        billing_state=account.billing_state,
        billing_postal_code=account.billing_postal_code,
        billing_country=account.billing_country,
        tax_id=account.tax_id,
        tax_id_type=account.tax_id_type,
        tax_exempt=account.tax_exempt,
        currency=account.currency,
        locale=account.locale,
        payment_provider=account.payment_provider,
        status=account.status,
        metadata_json=account.metadata_json or {},
    )


# =============================================================================
# Subscriptions
# =============================================================================

@router.get("/subscription", response_model=Optional[SubscriptionResponse])
async def get_subscription(
    user: User = Depends(require_permission("commercial:subscription:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the organization's active subscription."""
    subscription = await commercial_service.get_subscription(db, org.id)
    if not subscription:
        return None
    
    plan = await commercial_service.get_plan(db, subscription.plan_id) if subscription.plan_id else None
    
    return SubscriptionResponse(
        id=subscription.id,
        organization_id=subscription.organization_id,
        plan_id=subscription.plan_id,
        plan_key=plan.key if plan else None,
        plan_name=plan.name if plan else None,
        plan_tier=plan.tier if plan else None,
        commercial_account_id=subscription.commercial_account_id,
        state=subscription.state,
        previous_state=subscription.previous_state,
        billing_interval=subscription.billing_interval,
        price_cents=subscription.price_cents,
        currency=subscription.currency,
        trial_started_at=subscription.trial_started_at,
        trial_ends_at=subscription.trial_ends_at,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        auto_renew=subscription.auto_renew,
        cancel_at_period_end=subscription.cancel_at_period_end,
        cancelled_at=subscription.cancelled_at,
        cancellation_reason=subscription.cancellation_reason,
        grace_period_ends_at=subscription.grace_period_ends_at,
        in_grace_period=subscription.in_grace_period,
        payment_provider=subscription.payment_provider,
        payment_provider_subscription_id=subscription.payment_provider_subscription_id,
        payment_method_id=subscription.payment_method_id,
        metadata_json=subscription.metadata_json or {},
    )


@router.post("/subscription", response_model=SubscriptionResponse, status_code=201)
async def create_subscription(
    request: SubscriptionCreate,
    user: User = Depends(require_permission("commercial:subscription:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new subscription for the organization."""
    subscription = await commercial_service.create_subscription(
        db,
        organization_id=org.id,
        plan_key=request.plan_key,
        billing_interval=request.billing_interval,
        trial_days=request.trial_days,
        auto_renew=request.auto_renew,
        payment_provider=request.payment_provider,
        payment_method_id=request.payment_method_id,
        created_by=user.id,
    )
    await db.commit()
    
    plan = await commercial_service.get_plan(db, subscription.plan_id)
    
    return SubscriptionResponse(
        id=subscription.id,
        organization_id=subscription.organization_id,
        plan_id=subscription.plan_id,
        plan_key=plan.key if plan else None,
        plan_name=plan.name if plan else None,
        plan_tier=plan.tier if plan else None,
        commercial_account_id=subscription.commercial_account_id,
        state=subscription.state,
        previous_state=subscription.previous_state,
        billing_interval=subscription.billing_interval,
        price_cents=subscription.price_cents,
        currency=subscription.currency,
        trial_started_at=subscription.trial_started_at,
        trial_ends_at=subscription.trial_ends_at,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        auto_renew=subscription.auto_renew,
        cancel_at_period_end=subscription.cancel_at_period_end,
        cancelled_at=subscription.cancelled_at,
        cancellation_reason=subscription.cancellation_reason,
        grace_period_ends_at=subscription.grace_period_ends_at,
        in_grace_period=subscription.in_grace_period,
        payment_provider=subscription.payment_provider,
        payment_provider_subscription_id=subscription.payment_provider_subscription_id,
        payment_method_id=subscription.payment_method_id,
        metadata_json=subscription.metadata_json or {},
    )


@router.post("/subscription/activate", response_model=SubscriptionResponse)
async def activate_subscription(
    user: User = Depends(require_permission("commercial:subscription:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Activate the organization's subscription (end trial)."""
    subscription = await commercial_service.get_subscription(db, org.id)
    if not subscription:
        raise HTTPException(404, "No active subscription found")
    
    subscription = await commercial_service.activate_subscription(db, subscription.id, user.id)
    await db.commit()
    
    if not subscription:
        raise HTTPException(400, "Failed to activate subscription")
    
    plan = await commercial_service.get_plan(db, subscription.plan_id)
    
    return SubscriptionResponse(
        id=subscription.id,
        organization_id=subscription.organization_id,
        plan_id=subscription.plan_id,
        plan_key=plan.key if plan else None,
        plan_name=plan.name if plan else None,
        plan_tier=plan.tier if plan else None,
        commercial_account_id=subscription.commercial_account_id,
        state=subscription.state,
        previous_state=subscription.previous_state,
        billing_interval=subscription.billing_interval,
        price_cents=subscription.price_cents,
        currency=subscription.currency,
        trial_started_at=subscription.trial_started_at,
        trial_ends_at=subscription.trial_ends_at,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        auto_renew=subscription.auto_renew,
        cancel_at_period_end=subscription.cancel_at_period_end,
        cancelled_at=subscription.cancelled_at,
        cancellation_reason=subscription.cancellation_reason,
        grace_period_ends_at=subscription.grace_period_ends_at,
        in_grace_period=subscription.in_grace_period,
        payment_provider=subscription.payment_provider,
        payment_provider_subscription_id=subscription.payment_provider_subscription_id,
        payment_method_id=subscription.payment_method_id,
        metadata_json=subscription.metadata_json or {},
    )


@router.post("/subscription/renew", response_model=SubscriptionResponse)
async def renew_subscription(
    user: User = Depends(require_permission("commercial:subscription:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Renew the subscription for a new period."""
    subscription = await commercial_service.get_subscription(db, org.id)
    if not subscription:
        raise HTTPException(404, "No active subscription found")
    
    subscription = await commercial_service.renew_subscription(db, subscription.id)
    await db.commit()
    
    if not subscription:
        raise HTTPException(400, "Failed to renew subscription")
    
    plan = await commercial_service.get_plan(db, subscription.plan_id)
    
    return SubscriptionResponse(
        id=subscription.id,
        organization_id=subscription.organization_id,
        plan_id=subscription.plan_id,
        plan_key=plan.key if plan else None,
        plan_name=plan.name if plan else None,
        plan_tier=plan.tier if plan else None,
        commercial_account_id=subscription.commercial_account_id,
        state=subscription.state,
        previous_state=subscription.previous_state,
        billing_interval=subscription.billing_interval,
        price_cents=subscription.price_cents,
        currency=subscription.currency,
        trial_started_at=subscription.trial_started_at,
        trial_ends_at=subscription.trial_ends_at,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        auto_renew=subscription.auto_renew,
        cancel_at_period_end=subscription.cancel_at_period_end,
        cancelled_at=subscription.cancelled_at,
        cancellation_reason=subscription.cancellation_reason,
        grace_period_ends_at=subscription.grace_period_ends_at,
        in_grace_period=subscription.in_grace_period,
        payment_provider=subscription.payment_provider,
        payment_provider_subscription_id=subscription.payment_provider_subscription_id,
        payment_method_id=subscription.payment_method_id,
        metadata_json=subscription.metadata_json or {},
    )


@router.post("/subscription/cancel", response_model=SubscriptionResponse)
async def cancel_subscription(
    request: SubscriptionCancel,
    user: User = Depends(require_permission("commercial:subscription:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Cancel the organization's subscription."""
    subscription = await commercial_service.get_subscription(db, org.id)
    if not subscription:
        raise HTTPException(404, "No active subscription found")
    
    subscription = await commercial_service.cancel_subscription(
        db, subscription.id, user.id, request.reason, request.immediate
    )
    await db.commit()
    
    if not subscription:
        raise HTTPException(400, "Failed to cancel subscription")
    
    plan = await commercial_service.get_plan(db, subscription.plan_id)
    
    return SubscriptionResponse(
        id=subscription.id,
        organization_id=subscription.organization_id,
        plan_id=subscription.plan_id,
        plan_key=plan.key if plan else None,
        plan_name=plan.name if plan else None,
        plan_tier=plan.tier if plan else None,
        commercial_account_id=subscription.commercial_account_id,
        state=subscription.state,
        previous_state=subscription.previous_state,
        billing_interval=subscription.billing_interval,
        price_cents=subscription.price_cents,
        currency=subscription.currency,
        trial_started_at=subscription.trial_started_at,
        trial_ends_at=subscription.trial_ends_at,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        auto_renew=subscription.auto_renew,
        cancel_at_period_end=subscription.cancel_at_period_end,
        cancelled_at=subscription.cancelled_at,
        cancellation_reason=subscription.cancellation_reason,
        grace_period_ends_at=subscription.grace_period_ends_at,
        in_grace_period=subscription.in_grace_period,
        payment_provider=subscription.payment_provider,
        payment_provider_subscription_id=subscription.payment_provider_subscription_id,
        payment_method_id=subscription.payment_method_id,
        metadata_json=subscription.metadata_json or {},
    )


@router.post("/subscription/change-plan", response_model=SubscriptionResponse)
async def change_plan(
    request: SubscriptionChangePlan,
    user: User = Depends(require_permission("commercial:subscription:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Change the subscription plan."""
    subscription = await commercial_service.get_subscription(db, org.id)
    if not subscription:
        raise HTTPException(404, "No active subscription found")
    
    subscription = await commercial_service.change_plan(
        db, subscription.id, request.new_plan_key, request.effective, user.id
    )
    await db.commit()
    
    if not subscription:
        raise HTTPException(400, "Failed to change plan")
    
    plan = await commercial_service.get_plan(db, subscription.plan_id)
    
    return SubscriptionResponse(
        id=subscription.id,
        organization_id=subscription.organization_id,
        plan_id=subscription.plan_id,
        plan_key=plan.key if plan else None,
        plan_name=plan.name if plan else None,
        plan_tier=plan.tier if plan else None,
        commercial_account_id=subscription.commercial_account_id,
        state=subscription.state,
        previous_state=subscription.previous_state,
        billing_interval=subscription.billing_interval,
        price_cents=subscription.price_cents,
        currency=subscription.currency,
        trial_started_at=subscription.trial_started_at,
        trial_ends_at=subscription.trial_ends_at,
        current_period_start=subscription.current_period_start,
        current_period_end=subscription.current_period_end,
        auto_renew=subscription.auto_renew,
        cancel_at_period_end=subscription.cancel_at_period_end,
        cancelled_at=subscription.cancelled_at,
        cancellation_reason=subscription.cancellation_reason,
        grace_period_ends_at=subscription.grace_period_ends_at,
        in_grace_period=subscription.in_grace_period,
        payment_provider=subscription.payment_provider,
        payment_provider_subscription_id=subscription.payment_provider_subscription_id,
        payment_method_id=subscription.payment_method_id,
        metadata_json=subscription.metadata_json or {},
    )


# =============================================================================
# Usage Tracking
# =============================================================================

@router.post("/usage", response_model=UsageRecordResponse)
async def record_usage(
    request: UsageRecordRequest,
    user: User = Depends(require_permission("commercial:usage:write")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Record usage against an entitlement (idempotent)."""
    usage = await commercial_service.record_usage(
        db,
        organization_id=org.id,
        entitlement_key=request.entitlement_key,
        quantity=request.quantity,
        period=request.period,
        event_id=request.event_id,
        event_source=request.event_source,
        event_timestamp=request.event_timestamp,
        metadata_json=request.metadata_json,
    )
    await db.commit()
    
    return UsageRecordResponse(
        id=usage.id,
        organization_id=usage.organization_id,
        subscription_id=usage.subscription_id,
        entitlement_id=usage.entitlement_id,
        entitlement_key=usage.entitlement_key,
        period=usage.period,
        quantity=usage.quantity,
        unit=usage.unit,
        event_id=usage.event_id,
        event_source=usage.event_source,
        event_timestamp=usage.event_timestamp,
        metadata_json=usage.metadata_json or {},
    )


@router.get("/usage", response_model=List[UsageRecordResponse])
async def get_usage(
    entitlement_key: Optional[str] = Query(None),
    period: Optional[str] = Query(None),
    user: User = Depends(require_permission("commercial:usage:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get usage records for the organization."""
    usage = await commercial_service.get_usage(db, org.id, entitlement_key=entitlement_key, period=period)
    
    return [
        UsageRecordResponse(
            id=u.id,
            organization_id=u.organization_id,
            subscription_id=u.subscription_id,
            entitlement_id=u.entitlement_id,
            entitlement_key=u.entitlement_key,
            period=u.period,
            quantity=u.quantity,
            unit=u.unit,
            event_id=u.event_id,
            event_source=u.event_source,
            event_timestamp=u.event_timestamp,
            metadata_json=u.metadata_json or {},
        )
        for u in usage
    ]


@router.get("/usage/summary", response_model=UsageSummaryResponse)
async def get_usage_summary(
    period: Optional[str] = Query(None),
    user: User = Depends(require_permission("commercial:usage:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get aggregated usage summary."""
    summary = await commercial_service.get_usage_summary(db, org.id, period=period)
    return UsageSummaryResponse(
        organization_id=org.id,
        period=period or datetime.now(timezone.utc).strftime("%Y-%m"),
        usage=summary,
    )


@router.post("/usage/check", response_model=EntitlementCheckResponse)
async def check_usage_limit(
    key: str = Body(..., embed=True),
    current_usage: float = Body(..., embed=True, ge=0),
    user: User = Depends(require_permission("commercial:usage:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Check if current usage exceeds entitlement limit."""
    result = await commercial_service.check_limit(db, org.id, key, current_usage)
    return EntitlementCheckResponse(**result)


# =============================================================================
# Invoicing & Payments
# =============================================================================

@router.post("/invoices/generate", response_model=SubscriptionInvoiceResponse)
async def generate_invoice(
    period_start: datetime = Body(..., embed=True),
    period_end: datetime = Body(..., embed=True),
    user: User = Depends(require_permission("commercial:billing:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Generate an invoice for the current subscription period."""
    subscription = await commercial_service.get_subscription(db, org.id)
    if not subscription:
        raise HTTPException(404, "No active subscription found")
    
    sub_invoice = await commercial_service.generate_invoice(
        db, subscription.id, period_start, period_end, user.id
    )
    await db.commit()
    
    return SubscriptionInvoiceResponse(
        id=sub_invoice.id,
        subscription_id=sub_invoice.subscription_id,
        invoice_id=sub_invoice.invoice_id,
        period_start=sub_invoice.period_start,
        period_end=sub_invoice.period_end,
        subtotal_cents=sub_invoice.subtotal_cents,
        tax_cents=sub_invoice.tax_cents,
        total_cents=sub_invoice.total_cents,
        currency=sub_invoice.currency,
        line_items=sub_invoice.line_items or [],
        status=sub_invoice.status,
    )


@router.get("/invoices", response_model=List[InvoiceResponse])
async def list_invoices(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("commercial:billing:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List invoices for the organization."""
    query = select(Invoice).where(Invoice.organization_id == org.id)
    if status:
        query = query.where(Invoice.status == status)
    query = query.order_by(Invoice.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    invoices = result.scalars().all()
    
    return [
        InvoiceResponse(
            id=i.id,
            organization_id=i.organization_id,
            direction=i.direction,
            title=i.title,
            amount=i.amount,
            tax_amount=i.tax_amount,
            currency=i.currency,
            issued_at=i.issued_at,
            due_at=i.due_at,
            status=i.status,
            paid_at=i.paid_at,
            payment_reference=i.payment_reference,
            attributes=i.attributes or {},
        )
        for i in invoices
    ]


@router.post("/payments/record", response_model=SubscriptionPaymentResponse)
async def record_payment(
    request: PaymentRecordRequest,
    user: User = Depends(require_permission("commercial:billing:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Record a payment for a subscription invoice."""
    sub_payment = await commercial_service.record_payment(
        db,
        subscription_id=request.subscription_id,
        subscription_invoice_id=request.subscription_invoice_id,
        amount_cents=request.amount_cents,
        currency=request.currency,
        payment_provider=request.payment_provider,
        payment_provider_payment_id=request.payment_provider_payment_id,
        method=request.method,
        status=request.status,
        paid_at=request.paid_at,
    )
    await db.commit()
    
    return SubscriptionPaymentResponse(
        id=sub_payment.id,
        subscription_id=sub_payment.subscription_id,
        subscription_invoice_id=sub_payment.subscription_invoice_id,
        payment_id=sub_payment.payment_id,
        amount_cents=sub_payment.amount_cents,
        currency=sub_payment.currency,
        status=sub_payment.status,
    )


# =============================================================================
# Provisioning
# =============================================================================

@router.post("/provisioning/start", response_model=ProvisioningResponse, status_code=201)
async def start_provisioning(
    request: ProvisioningStartRequest,
    user: User = Depends(require_permission("commercial:provisioning:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Start the provisioning process for a new organization."""
    provisioning = await commercial_service.start_provisioning(
        db,
        organization_id=org.id,
        plan_key=request.plan_key,
        admin_user_id=request.admin_user_id,
        admin_email=request.admin_email,
        domain=request.domain,
    )
    await db.commit()
    
    return ProvisioningResponse(
        id=provisioning.id,
        organization_id=provisioning.organization_id,
        subscription_id=provisioning.subscription_id,
        commercial_account_id=provisioning.commercial_account_id,
        state=provisioning.state,
        previous_state=provisioning.previous_state,
        steps=provisioning.steps,
        current_step=provisioning.current_step,
        admin_user_id=provisioning.admin_user_id,
        admin_email=provisioning.admin_email,
        domain=provisioning.domain,
        domain_verified=provisioning.domain_verified,
        domain_verification_token=provisioning.domain_verification_token,
        domain_verified_at=provisioning.domain_verified_at,
        security_policy_applied=provisioning.security_policy_applied,
        employees_imported=provisioning.employees_imported,
        employees_total=provisioning.employees_total,
        integrations_configured=provisioning.integrations_configured,
        integrations_total=provisioning.integrations_total,
        company_import_completed=provisioning.company_import_completed,
        company_import_records=provisioning.company_import_records,
        validation_passed=provisioning.validation_passed,
        validation_errors=provisioning.validation_errors,
        validated_at=provisioning.validated_at,
        activated_at=provisioning.activated_at,
        activated_by=provisioning.activated_by,
        suspended_at=provisioning.suspended_at,
        suspended_reason=provisioning.suspended_reason,
        deactivated_at=provisioning.deactivated_at,
        deactivated_reason=provisioning.deactivated_reason,
        metadata_json=provisioning.metadata_json or {},
    )


@router.get("/provisioning", response_model=Optional[ProvisioningResponse])
async def get_provisioning(
    user: User = Depends(require_permission("commercial:provisioning:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get the organization's provisioning status."""
    provisioning = await commercial_service.get_provisioning(db, org.id)
    if not provisioning:
        return None
    
    return ProvisioningResponse(
        id=provisioning.id,
        organization_id=provisioning.organization_id,
        subscription_id=provisioning.subscription_id,
        commercial_account_id=provisioning.commercial_account_id,
        state=provisioning.state,
        previous_state=provisioning.previous_state,
        steps=provisioning.steps,
        current_step=provisioning.current_step,
        admin_user_id=provisioning.admin_user_id,
        admin_email=provisioning.admin_email,
        domain=provisioning.domain,
        domain_verified=provisioning.domain_verified,
        domain_verification_token=provisioning.domain_verification_token,
        domain_verified_at=provisioning.domain_verified_at,
        security_policy_applied=provisioning.security_policy_applied,
        employees_imported=provisioning.employees_imported,
        employees_total=provisioning.employees_total,
        integrations_configured=provisioning.integrations_configured,
        integrations_total=provisioning.integrations_total,
        company_import_completed=provisioning.company_import_completed,
        company_import_records=provisioning.company_import_records,
        validation_passed=provisioning.validation_passed,
        validation_errors=provisioning.validation_errors,
        validated_at=provisioning.validated_at,
        activated_at=provisioning.activated_at,
        activated_by=provisioning.activated_by,
        suspended_at=provisioning.suspended_at,
        suspended_reason=provisioning.suspended_reason,
        deactivated_at=provisioning.deactivated_at,
        deactivated_reason=provisioning.deactivated_reason,
        metadata_json=provisioning.metadata_json or {},
    )


@router.post("/provisioning/steps/{step}/complete", response_model=dict)
async def complete_provisioning_step(
    step: str,
    request: ProvisioningStepCompleteRequest,
    user: User = Depends(require_permission("commercial:provisioning:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Complete a provisioning step."""
    provisioning = await commercial_service.get_provisioning(db, org.id)
    if not provisioning:
        raise HTTPException(404, "No provisioning found for organization")
    
    step_obj = await commercial_service.complete_provisioning_step(
        db, provisioning.id, step, request.success, request.output, request.error
    )
    await db.commit()
    
    if not step_obj:
        raise HTTPException(404, f"Step {step} not found")
    
    return {"success": request.success, "step": step, "completed_at": step_obj.completed_at}


@router.post("/provisioning/validate-and-activate", response_model=ProvisioningResponse)
async def validate_and_activate(
    user: User = Depends(require_permission("commercial:provisioning:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Validate provisioning and activate the organization."""
    provisioning = await commercial_service.validate_and_activate(db, org.id, user.id)
    await db.commit()
    
    if not provisioning:
        raise HTTPException(404, "No provisioning found for organization")
    
    return ProvisioningResponse(
        id=provisioning.id,
        organization_id=provisioning.organization_id,
        subscription_id=provisioning.subscription_id,
        commercial_account_id=provisioning.commercial_account_id,
        state=provisioning.state,
        previous_state=provisioning.previous_state,
        steps=provisioning.steps,
        current_step=provisioning.current_step,
        admin_user_id=provisioning.admin_user_id,
        admin_email=provisioning.admin_email,
        domain=provisioning.domain,
        domain_verified=provisioning.domain_verified,
        domain_verification_token=provisioning.domain_verification_token,
        domain_verified_at=provisioning.domain_verified_at,
        security_policy_applied=provisioning.security_policy_applied,
        employees_imported=provisioning.employees_imported,
        employees_total=provisioning.employees_total,
        integrations_configured=provisioning.integrations_configured,
        integrations_total=provisioning.integrations_total,
        company_import_completed=provisioning.company_import_completed,
        company_import_records=provisioning.company_import_records,
        validation_passed=provisioning.validation_passed,
        validation_errors=provisioning.validation_errors,
        validated_at=provisioning.validated_at,
        activated_at=provisioning.activated_at,
        activated_by=provisioning.activated_by,
        suspended_at=provisioning.suspended_at,
        suspended_reason=provisioning.suspended_reason,
        deactivated_at=provisioning.deactivated_at,
        deactivated_reason=provisioning.deactivated_reason,
        metadata_json=provisioning.metadata_json or {},
    )


# =============================================================================
# Domain Verification
# =============================================================================

@router.post("/domain/verify/start", response_model=DomainVerificationStartResponse)
async def start_domain_verification(
    domain: str = Body(..., embed=True),
    user: User = Depends(require_permission("commercial:provisioning:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Start domain verification."""
    provisioning = await commercial_service.start_domain_verification(db, org.id, domain)
    await db.commit()
    
    return DomainVerificationStartResponse(
        domain=provisioning.domain,
        verification_token=provisioning.domain_verification_token or "",
    )


@router.post("/domain/verify", response_model=dict)
async def verify_domain(
    request: DomainVerificationRequest,
    user: User = Depends(require_permission("commercial:provisioning:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Verify domain ownership."""
    success = await commercial_service.verify_domain(db, org.id, request.token)
    await db.commit()
    
    return {"success": success, "verified": success}


# =============================================================================
# Events
# =============================================================================

@router.get("/events", response_model=List[SubscriptionEventResponse])
async def list_subscription_events(
    subscription_id: Optional[str] = Query(None),
    event_type: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    user: User = Depends(require_permission("commercial:events:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List subscription lifecycle events."""
    query = select(SubscriptionEvent).where(SubscriptionEvent.organization_id == org.id)
    
    if subscription_id:
        query = query.where(SubscriptionEvent.subscription_id == subscription_id)
    if event_type:
        query = query.where(SubscriptionEvent.event_type == event_type)
    
    query = query.order_by(SubscriptionEvent.created_at.desc()).limit(limit).offset(offset)
    result = await db.execute(query)
    events = result.scalars().all()
    
    return [
        SubscriptionEventResponse(
            id=e.id,
            organization_id=e.organization_id,
            subscription_id=e.subscription_id,
            event_type=e.event_type,
            from_state=e.from_state,
            to_state=e.to_state,
            actor_id=e.actor_id,
            actor_type=e.actor_type,
            details_json=e.details_json or {},
            amount_cents=e.amount_cents,
            currency=e.currency,
            invoice_id=e.invoice_id,
            occurred_at=e.created_at,
        )
        for e in events
    ]


# =============================================================================
# Usage Metering (Stage 5.1)
# =============================================================================

@router.post("/usage/events", response_model=UsageEventResponse)
async def ingest_usage_event(
    event: UsageEventCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ingest a single usage event with idempotency."""
    from app.schemas.usage_metering import UsageEventCreate
    
    if str(current_user.organization_id) != event.organization_id:
        raise HTTPException(403, "Cannot submit usage events for another organization")
    
    result = await usage_intake_service.ingest_event(db, event, str(current_user.organization_id))
    return result


@router.post("/usage/events/batch", response_model=UsageBatchResponse)
async def ingest_usage_batch(
    batch: UsageBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Ingest a batch of usage events (max 1000)."""
    from app.schemas.usage_metering import UsageBatchRequest, UsageBatchResponse
    
    for event in batch.events:
        if str(current_user.organization_id) != event.organization_id:
            raise HTTPException(403, f"Event {event.event_id} belongs to different organization")
    
    result = await usage_intake_service.ingest_batch(db, batch, str(current_user.organization_id))
    return result


@router.get("/usage/events/{event_id}", response_model=UsageEventResponse)
async def get_event_status(
    event_id: str,
    organization_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get processing status of a usage event."""
    if str(current_user.organization_id) != organization_id:
        raise HTTPException(403, "Cannot access events for another organization")
    
    event_status = await usage_intake_service.get_event_status(db, organization_id, event_id)
    if not event_status:
        raise HTTPException(404, "Event not found")
    return event_status


@router.post("/usage/aggregations/period/{period}")
async def aggregate_period(
    period: str,
    subscription_id: Optional[str] = Query(None),
    metric_codes: Optional[List[str]] = Query(None),
    force: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger aggregation for a billing period."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(403, "Subscription not found")
    
    results = await usage_aggregation_service.aggregate_period(
        db=db,
        organization_id=org_id,
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


@router.get("/usage/aggregations/period/{period}")
async def get_period_aggregations(
    period: str,
    subscription_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get all aggregations for a billing period."""
    org_id = str(current_user.organization_id)
    
    if subscription_id:
        sub = await db.get(Subscription, subscription_id)
        if not sub or str(sub.organization_id) != org_id:
            raise HTTPException(403, "Subscription not found")
    
    aggregations = await usage_aggregation_service.get_aggregations_for_period(db, org_id, period)
    
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
        raise HTTPException(403, "Subscription not found")
    
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
        raise HTTPException(403, "Subscription not found")
    
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
        raise HTTPException(403, "Subscription not found")
    
    current, what_if = await invoice_preview_service.generate_what_if_preview(
        db=db,
        subscription_id=subscription_id,
        period=period,
        what_if_changes=what_if_changes,
        pricing_version=pricing_version,
    )
    
    return {
        "current": {"total_cents": current.total_cents, "line_items": current.line_items},
        "what_if": {"total_cents": what_if.total_cents, "line_items": what_if.line_items},
        "difference_cents": what_if.total_cents - current.total_cents,
    }


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
    
    statuses = await entitlement_enforcement_service.get_all_limit_status(db, org_id, period)
    
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
            raise HTTPException(403, "Subscription not found")
    
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
    
    report = await reconciliation_service.get_reconciliation_report(db, org_id, period)
    return report


# =============================================================================
# Payment Webhooks (Stage 5.2)
# =============================================================================

@router.post("/webhooks/payments/stripe")
async def stripe_payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe payment webhooks."""
    from app.services.payment_webhook_service import payment_webhook_router
    
    payload = await request.json()
    headers = dict(request.headers)
    
    result = await payment_webhook_router.process_webhook(
        db=db,
        provider="stripe",
        payload=payload,
        headers=headers,
    )
    
    if not result.get("success"):
        logger.warning(f"Stripe webhook processing failed: {result.get('error')}")
        # Still return 200 to acknowledge receipt (Stripe will retry on non-2xx)
    
    return {"received": True}


@router.post("/webhooks/payments/{provider}")
async def generic_payment_webhook(
    provider: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Generic payment webhook endpoint for other providers."""
    from app.services.payment_webhook_service import payment_webhook_router
    
    payload = await request.json()
    headers = dict(request.headers)
    
    result = await payment_webhook_router.process_webhook(
        db=db,
        provider=provider,
        payload=payload,
        headers=headers,
    )
    
    if not result.get("success"):
        logger.warning(f"{provider} webhook processing failed: {result.get('error')}")
    
    return {"received": True}


# =============================================================================
# Stripe Subscription Webhooks (handles subscription lifecycle events)
# =============================================================================

@router.post("/webhooks/stripe/subscription")
async def stripe_subscription_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe subscription lifecycle webhooks.
    
    This endpoint handles events like:
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
    
    payload = await request.body()
    signature = request.headers.get("stripe-signature")
    
    if not signature:
        logger.error("Missing stripe-signature header")
        return {"error": "Missing signature"}
    
    try:
        event = stripe.Webhook.construct_event(
            payload.decode(), signature, webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid Stripe payload: {e}")
        return {"error": "Invalid payload"}
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Stripe signature verification failed: {e}")
        return {"error": "Invalid signature"}
    
    event_type = event["type"]
    data = event["data"]["object"]
    
    logger.info(f"Processing Stripe subscription webhook: {event_type}")
    
    # Route to commercial service handler
    result = await commercial_service.handle_stripe_webhook(db, data, signature)
    
    return result


# =============================================================================
# Payment Management (Stage 5.2)
# =============================================================================

@router.post("/payments/initiate", response_model=Dict[str, Any])
async def initiate_payment(
    subscription_id: str = Body(..., embed=True),
    amount_cents: int = Body(..., embed=True, ge=1),
    currency: str = Body("USD", embed=True),
    payment_provider: Optional[str] = Body(None, embed=True),
    payment_method_id: Optional[str] = Body(None, embed=True),
    idempotency_key: Optional[str] = Body(None, embed=True),
    metadata: Optional[Dict[str, Any]] = Body(None, embed=True),
    user: User = Depends(require_permission("commercial:billing:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Initiate a payment with idempotency protection."""
    result = await payment_service.initiate_payment(
        db=db,
        subscription_id=subscription_id,
        amount_cents=amount_cents,
        currency=currency,
        payment_provider=payment_provider,
        payment_method_id=payment_method_id,
        idempotency_key=idempotency_key,
        metadata=metadata,
        initiated_by=user.id,
    )
    
    return {
        "payment_id": result.payment_id,
        "state": result.state,
        "amount_cents": result.amount_cents,
        "currency": result.currency,
        "provider_payment_id": result.provider_payment_id,
        "error": result.error,
    }


@router.post("/payments/{payment_id}/retry", response_model=Dict[str, Any])
async def retry_payment(
    payment_id: str,
    user: User = Depends(require_permission("commercial:billing:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Retry a failed payment."""
    result = await payment_service.retry_failed_payment(db, payment_id, user.id)
    
    return {
        "payment_id": result.payment_id,
        "state": result.state,
        "amount_cents": result.amount_cents,
        "currency": result.currency,
        "provider_payment_id": result.provider_payment_id,
        "error": result.error,
    }


@router.post("/payments/{payment_id}/refund", response_model=Dict[str, Any])
async def process_refund(
    payment_id: str,
    amount_cents: Optional[int] = Body(None, embed=True),
    reason: Optional[str] = Body(None, embed=True),
    idempotency_key: Optional[str] = Body(None, embed=True),
    user: User = Depends(require_permission("commercial:billing:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Process a refund for a payment."""
    result = await payment_service.process_refund(
        db=db,
        payment_id=payment_id,
        amount_cents=amount_cents,
        reason=reason,
        initiated_by=user.id,
        idempotency_key=idempotency_key,
    )
    
    return {
        "refund_id": result.refund_id,
        "provider_refund_id": result.provider_refund_id,
        "state": result.state.value,
        "amount_cents": result.amount_cents,
        "currency": result.currency,
        "failure_reason": result.failure_reason,
    }


@router.post("/subscription/{subscription_id}/dunning")
async def process_dunning(
    subscription_id: str,
    user: User = Depends(require_permission("commercial:billing:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Process dunning for a subscription with failed payment."""
    sub = await db.get(Subscription, subscription_id)
    if not sub or str(sub.organization_id) != str(org.id):
        raise HTTPException(403, "Subscription not found")
    
    result = await payment_service.process_dunning(db, subscription_id)
    return result


@router.post("/subscription/{subscription_id}/suspend")
async def suspend_subscription(
    subscription_id: str,
    reason: str = Body(..., embed=True),
    user: User = Depends(require_permission("commercial:subscription:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Suspend a subscription."""
    sub = await db.get(Subscription, subscription_id)
    if not sub or str(sub.organization_id) != str(org.id):
        raise HTTPException(403, "Subscription not found")
    
    success = await payment_service.suspend_subscription(db, subscription_id, reason)
    return {"success": success}


@router.post("/subscription/{subscription_id}/reactivate")
async def reactivate_subscription(
    subscription_id: str,
    payment_id: Optional[str] = Body(None, embed=True),
    user: User = Depends(require_permission("commercial:subscription:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Reactivate a suspended subscription after verified payment."""
    sub = await db.get(Subscription, subscription_id)
    if not sub or str(sub.organization_id) != str(org.id):
        raise HTTPException(403, "Subscription not found")
    
    success = await payment_service.reactivate_subscription(db, subscription_id, payment_id)
    return {"success": success}


@router.post("/reconciliation/payment/{subscription_id}/{period}")
async def reconcile_payment(
    subscription_id: str,
    period: str,
    user: User = Depends(require_permission("commercial:billing:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Reconcile payment state with provider."""
    sub = await db.get(Subscription, subscription_id)
    if not sub or str(sub.organization_id) != str(org.id):
        raise HTTPException(403, "Subscription not found")
    
    result = await payment_service.reconcile_payment(db, subscription_id, period)
    return result


# =============================================================================
# Exports
# =============================================================================

__all__ = ["router"]