"""Company Onboarding API — company-level onboarding flow."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.workspace import Workspace
from app.services.onboarding_service import onboarding_service
from app.services.provisioning_service import provisioning_service
from app.models.finance import Provisioning

router = APIRouter(prefix="/onboarding", tags=["Company Onboarding"])


@router.get("/status")
async def get_onboarding_status(
    user: User = Depends(require_permission("organization:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get company onboarding status for the current organization."""
    # Get admin's workspace to check onboarding completion
    admin_workspace = await db.execute(
        select(Workspace).where(
            Workspace.user_id == user.id,
            Workspace.organization_id == org.id,
        )
    )
    admin_workspace = admin_workspace.scalar_one_or_none()

    # Get onboarding progress from service
    progress = await onboarding_service.get_onboarding_progress(db, org.id)

    return {
        "organization_id": org.id,
        "onboarding_completed": admin_workspace.onboarding_completed if admin_workspace else False,
        "provisioning_state": progress.get("provisioning_state"),
        "provisioning_progress": progress.get("provisioning_progress", 0),
        "current_phase": progress.get("current_phase"),
        "completed_steps": progress.get("completed_steps", []),
        "failed_steps": progress.get("failed_steps", []),
        "errors": progress.get("errors", []),
        "started_at": progress.get("started_at"),
        "completed_at": progress.get("completed_at"),
    }


@router.post("/complete")
async def complete_company_onboarding(
    user: User = Depends(require_permission("organization:update")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Mark company onboarding as complete."""
    # Complete onboarding via service
    await onboarding_service.complete_onboarding(db, org.id)

    # Mark admin's workspace as onboarded
    admin_workspace = await db.execute(
        select(Workspace).where(
            Workspace.user_id == user.id,
            Workspace.organization_id == org.id,
        )
    )
    admin_workspace = admin_workspace.scalar_one_or_none()
    if admin_workspace:
        admin_workspace.onboarding_completed = True
        from app.core.timeutils import utcnow
        admin_workspace.onboarded_at = utcnow().isoformat()

    await db.commit()

    return {"success": True, "message": "Company onboarding completed"}


@router.post("/provisioning/start")
async def start_provisioning(
    user: User = Depends(require_permission("organization:update")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Start provisioning for the current organization."""
    from app.services.provisioning_service import provisioning_service
    from app.models.finance import Provisioning

    # Check if provisioning already exists
    existing = await db.execute(
        select(Provisioning).where(Provisioning.organization_id == org.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Provisioning already exists for this organization")

    # Start provisioning using the core provisioning service
    # Use org details for provisioning
    prov = await provisioning_service.start_provisioning(
        db,
        organization_name=org.name,
        domain=org.slug,
        admin_email=user.email,
        admin_name=user.full_name,
        plan_key="starter",
        billing_interval="monthly",
        organization_id=org.id,
    )

    # Execute provisioning in background
    try:
        await provisioning_service.execute_provisioning(db, prov.id, caller=user)
    except Exception as e:
        # Provisioning failed, but record exists for retry
        raise HTTPException(status_code=500, detail=f"Provisioning failed: {str(e)}")

    return {"success": True, "provisioning_id": prov.id, "message": "Provisioning started"}


@router.get("/provisioning/{provisioning_id}/retry/{step_name}")
async def retry_provisioning_step(
    provisioning_id: str,
    step_name: str,
    user: User = Depends(require_permission("organization:update")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Retry a failed provisioning step."""
    from app.services.provisioning_service import provisioning_service

    success = await provisioning_service.retry_failed_step(
        db, provisioning_id, step_name, caller=user
    )

    if not success:
        raise HTTPException(status_code=500, detail="Step retry failed")

    return {"success": True, "message": f"Step {step_name} retried successfully"}


@router.get("/provisioning/{provisioning_id}/progress")
async def get_provisioning_progress(
    provisioning_id: str,
    user: User = Depends(require_permission("organization:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Get provisioning progress for the current organization."""
    prov = await db.get(Provisioning, provisioning_id)
    if not prov:
        raise HTTPException(status_code=404, detail="Provisioning not found")
    
    if prov.organization_id != org.id:
        raise HTTPException(status_code=403, detail="Access denied")
    
    from app.services.provisioning_service import STEP_DEFINITIONS, PROVISIONING_STATE_ORDER, ProvisioningState
    
    steps = prov.steps or []
    step_map = {s.get("step"): s for s in steps}
    
    # Build step progress with definitions
    step_progress = []
    completed_count = 0
    failed_count = 0
    running_count = 0
    
    for step_def in STEP_DEFINITIONS:
        step_name = step_def["step"]
        step_data = step_map.get(step_name, {})
        step_state = step_data.get("state", "not_started")
        
        if step_state == "completed":
            completed_count += 1
        elif step_state == "failed":
            failed_count += 1
        elif step_state == "running":
            running_count += 1
        
        step_progress.append({
            "step": step_name,
            "state": step_state,
            "name": step_def["name"],
            "description": step_def["description"],
            "required": step_def["required"],
            "recoverable": step_def["recoverable"],
            "started_at": step_data.get("started_at"),
            "completed_at": step_data.get("completed_at"),
            "error": step_data.get("error"),
        })
    
    # Calculate progress percentage
    total_steps = len(STEP_DEFINITIONS)
    provisioning_progress = int((completed_count / total_steps) * 100) if total_steps > 0 else 0
    
    # Determine current phase from provisioning state
    current_phase = prov.state
    if prov.state in [s.value for s in ProvisioningState]:
        state_index = next((i for i, s in enumerate(PROVISIONING_STATE_ORDER) if s.value == prov.state), 0)
        if state_index < len(PROVISIONING_STATE_ORDER) - 1:
            current_phase = PROVISIONING_STATE_ORDER[state_index].value.replace("_", " ").title()
    
    # Get current step
    current_step = prov.current_step
    if current_step:
        current_step_def = next((s for s in STEP_DEFINITIONS if s["step"] == current_step), None)
        current_step_name = current_step_def["name"] if current_step_def else current_step
    else:
        current_step_name = "Initializing..."
    
    return {
        "provisioning_id": prov.id,
        "state": prov.state,
        "current_step": current_step,
        "current_step_name": current_step_name,
        "steps": step_progress,
        "current_phase": current_phase,
        "provisioning_progress": provisioning_progress,
        "error": prov.metadata_json.get("error") if prov.metadata_json else None,
        "completed_count": completed_count,
        "failed_count": failed_count,
        "running_count": running_count,
        "total_steps": total_steps,
    }