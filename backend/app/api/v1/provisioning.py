"""Company Provisioning API — end-to-end company onboarding."""

from typing import Any, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.db.database import get_db
from app.models.finance import Plan, Provisioning
from app.services.provisioning_service import provisioning_service, ProvisioningState

router = APIRouter(prefix="/provisioning", tags=["provisioning"])


def _latest_step_error(provisioning: Provisioning) -> Optional[str]:
    """Derive the current error from provisioning state (failed step or suspension)."""
    for step in reversed(provisioning.steps or []):
        if step.get("state") == "failed":
            return step.get("error") or f"Step failed: {step.get('step')}"
    return provisioning.suspended_reason


# =============================================================================
# Request/Response Models
# =============================================================================

class ProvisioningStartIn(BaseModel):
    organization_name: str
    domain: str
    admin_email: EmailStr
    admin_name: str
    plan_key: str = "starter"
    billing_interval: str = "monthly"
    custom_domain: bool = False
    idempotency_key: Optional[str] = None


class ProvisioningStartOut(BaseModel):
    provisioning_id: str
    organization_id: str
    state: str
    domain: str
    admin_email: str


class ProvisioningStatusOut(BaseModel):
    provisioning_id: str
    organization_id: str
    state: str
    current_step: Optional[str]
    steps: List[dict]
    validation_passed: bool
    validation_errors: List[str]
    activated_at: Optional[str]
    error: Optional[str]


class StepRetryIn(BaseModel):
    step_name: str


class ProvisioningRetryOut(BaseModel):
    success: bool
    step_name: str
    error: Optional[str] = None


class ProvisioningSuspendIn(BaseModel):
    reason: str


class ProvisioningResumeOut(BaseModel):
    success: bool


class PlanListOut(BaseModel):
    plans: List[dict]


class ProvisioningOut(BaseModel):
    provisioning_id: str
    organization_id: str
    state: str
    domain: str
    admin_email: str
    admin_name: str
    plan_key: str
    billing_interval: str
    custom_domain: bool
    current_step: Optional[str]
    steps: List[dict]
    validation_passed: bool
    validation_errors: List[str]
    activated_at: Optional[str]
    error: Optional[str]


# =============================================================================
# Provisioning Endpoints
# =============================================================================

@router.post("/start", response_model=ProvisioningStartOut)
async def start_provisioning(
    body: ProvisioningStartIn,
    db: AsyncSession = Depends(get_db),
    user = Depends(require_permission("provisioning:create")),
) -> dict:
    """Start a new company provisioning.
    
    This is the entry point for company onboarding.
    Creates organization and provisioning record in REQUESTED state.
    Supports idempotency via optional idempotency_key.
    """
    try:
        provisioning = await provisioning_service.start_provisioning(
            db,
            organization_name=body.organization_name,
            domain=body.domain,
            admin_email=body.admin_email,
            admin_name=body.admin_name,
            plan_key=body.plan_key,
            billing_interval=body.billing_interval,
            custom_domain=body.custom_domain,
            idempotency_key=body.idempotency_key,
        )
        
        return {
            "provisioning_id": provisioning.id,
            "organization_id": provisioning.organization_id,
            "state": provisioning.state,
            "domain": provisioning.domain,
            "admin_email": provisioning.admin_email,
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{provisioning_id}/execute", response_model=ProvisioningOut)
async def execute_provisioning(
    provisioning_id: str,
    db: AsyncSession = Depends(get_db),
    user = Depends(require_permission("provisioning:execute")),
) -> Provisioning:
    """Execute the full provisioning lifecycle.
    
    Runs all provisioning steps in order:
    1. identity_initialization
    2. tenant_creation
    3. security_initialization
    4. governance_initialization
    5. commercial_initialization
    6. workspace_initialization
    7. organization_initialization
    8. admin_initialization
    9. integration_ready (optional)
    10. initial_sync (optional)
    11. canonical_validation
    12. company_brain_initialization
    """
    provisioning = await provisioning_service.execute_provisioning(db, provisioning_id)
    
    # Convert to response model
    metadata = provisioning.metadata_json or {}
    return ProvisioningOut(
        provisioning_id=provisioning.id,
        organization_id=provisioning.organization_id,
        state=provisioning.state,
        domain=provisioning.domain or "",
        admin_email=provisioning.admin_email or "",
        admin_name=metadata.get("admin_name", ""),
        plan_key=metadata.get("plan_key", "starter"),
        billing_interval=metadata.get("billing_interval", "monthly"),
        custom_domain=metadata.get("custom_domain", False),
        current_step=provisioning.current_step,
        steps=provisioning.steps or [],
        validation_passed=provisioning.validation_passed,
        validation_errors=provisioning.validation_errors or [],
        activated_at=provisioning.activated_at.isoformat() if provisioning.activated_at else None,
        error=_latest_step_error(provisioning),
    )


@router.get("/{provisioning_id}/status", response_model=ProvisioningStatusOut)
async def get_provisioning_status(
    provisioning_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get provisioning status and progress."""
    provisioning = await provisioning_service.get_provisioning(db, provisioning_id)
    if not provisioning:
        raise HTTPException(status_code=404, detail="Provisioning not found")
    
    return ProvisioningStatusOut(
        provisioning_id=provisioning.id,
        organization_id=provisioning.organization_id,
        state=provisioning.state,
        current_step=provisioning.current_step,
        steps=provisioning.steps or [],
        validation_passed=provisioning.validation_passed,
        validation_errors=provisioning.validation_errors or [],
        activated_at=provisioning.activated_at.isoformat() if provisioning.activated_at else None,
        error=_latest_step_error(provisioning),
    )


@router.post("/{provisioning_id}/retry", response_model=ProvisioningRetryOut)
async def retry_failed_step(
    provisioning_id: str,
    body: StepRetryIn,
    db: AsyncSession = Depends(get_db),
    user = Depends(require_permission("provisioning:execute")),
) -> dict:
    """Retry a failed provisioning step."""
    try:
        success = await provisioning_service.retry_failed_step(
            db, provisioning_id, body.step_name
        )
        return ProvisioningRetryOut(success=success, step_name=body.step_name)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        return ProvisioningRetryOut(success=False, step_name=body.step_name, error=str(e))


@router.post("/{provisioning_id}/suspend", response_model=ProvisioningResumeOut)
async def suspend_provisioning(
    provisioning_id: str,
    body: ProvisioningSuspendIn,
    db: AsyncSession = Depends(get_db),
    user = Depends(require_permission("provisioning:execute")),
) -> dict:
    """Suspend a provisioning."""
    try:
        await provisioning_service.suspend_provisioning(db, provisioning_id, body.reason)
        return ProvisioningResumeOut(success=True)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/{provisioning_id}/resume", response_model=ProvisioningResumeOut)
async def resume_provisioning(
    provisioning_id: str,
    db: AsyncSession = Depends(get_db),
    user = Depends(require_permission("provisioning:execute")),
) -> dict:
    """Resume a suspended provisioning."""
    try:
        success = await provisioning_service.resume_provisioning(db, provisioning_id)
        return ProvisioningResumeOut(success=success)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/plans", response_model=PlanListOut)
async def list_plans(
    db: AsyncSession = Depends(get_db),
) -> dict:
    """List available plans for provisioning."""
    plans = await db.execute(select(Plan).where(Plan.is_active == True, Plan.is_public == True))
    plans_list = []
    for plan in plans.scalars().all():
        plans_list.append({
            "key": plan.key,
            "name": plan.name,
            "description": plan.description,
            "tier": plan.tier,
            "monthly_price_cents": plan.monthly_price_cents,
            "annual_price_cents": plan.annual_price_cents,
            "currency": plan.currency,
            "trial_days": plan.trial_days,
            "entitlements": plan.entitlements,
            "features": plan.features,
            "limits": plan.limits,
            "is_active": plan.is_active,
            "is_public": plan.is_public,
        })
    return {"plans": plans_list}


@router.get("/states", response_model=dict)
async def get_provisioning_states() -> dict:
    """Get all possible provisioning states."""
    return {
        "states": [state.value for state in ProvisioningState],
        "state_order": [state.value for state in [
            ProvisioningState.REQUESTED,
            ProvisioningState.IDENTITY_INITIALIZED,
            ProvisioningState.TENANT_CREATED,
            ProvisioningState.SECURITY_INITIALIZED,
            ProvisioningState.GOVERNANCE_INITIALIZED,
            ProvisioningState.COMMERCIAL_INITIALIZED,
            ProvisioningState.WORKSPACE_INITIALIZED,
            ProvisioningState.ORGANIZATION_INITIALIZED,
            ProvisioningState.ADMIN_INITIALIZED,
            ProvisioningState.INTEGRATION_READY,
            ProvisioningState.INITIAL_SYNC,
            ProvisioningState.CANONICAL_VALIDATION,
            ProvisioningState.COMPANY_BRAIN_INITIALIZATION,
            ProvisioningState.READY,
            ProvisioningState.SUSPENDED,
            ProvisioningState.DEACTIVATED,
        ]]
    }


@router.get("", response_model=dict)
async def list_provisionings(
    db: AsyncSession = Depends(get_db),
    user = Depends(require_permission("provisioning:list")),
    state: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict:
    """List provisionings (platform administration)."""
    query = select(Provisioning)
    count_query = select(func.count(Provisioning.id))
    
    if state:
        query = query.where(Provisioning.state == state)
        count_query = count_query.where(Provisioning.state == state)
    
    total = (await db.execute(count_query)).scalar_one()
    rows = (
        await db.execute(
            query.order_by(Provisioning.created_at.desc()).limit(limit).offset(offset)
        )
    ).scalars().all()
    
    return {
        "total": total,
        "provisionings": [
            {
                "provisioning_id": p.id,
                "organization_id": p.organization_id,
                "state": p.state,
                "domain": p.domain,
                "admin_email": p.admin_email,
                "current_step": p.current_step,
                "validation_passed": p.validation_passed,
                "created_at": p.created_at.isoformat() if p.created_at else None,
                "activated_at": p.activated_at.isoformat() if p.activated_at else None,
            }
            for p in rows
        ],
    }