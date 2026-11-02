from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.adaptive_operating_profile_service import adaptive_operating_profile_service
from app.models.adaptive_operating_profile import (
    CapabilityKey,
    IntegrationState,
    CapabilityLifecycleState,
    AdaptationMode,
    OperatingModel,
    GovernanceProfile,
    ScalingProfile,
)

router = APIRouter(prefix="/adaptive-operating-profile", tags=["adaptive-operating-profile"])


class CapabilityKeyRequest(BaseModel):
    capability_key: str = Field(..., description="The capability key to check/enable")


class CapabilityLifecycleUpdate(BaseModel):
    target_state: str = Field(..., description="Target lifecycle state")


class IntegrationStateUpdate(BaseModel):
    state: str
    config: Optional[Dict[str, Any]] = None


class WorkflowConfigCreate(BaseModel):
    workflow_key: str
    workflow_name: str
    workflow_type: str
    complexity: str = "standard"
    stages: List[Dict[str, Any]] = []
    segregation_of_duties: bool = False
    delegation_enabled: bool = True
    timeout_hours: int = 72
    escalation_rules: List[Dict[str, Any]] = []
    failure_handling: Dict[str, Any] = {}
    requires_segregation_of_duties: bool = False
    requires_dual_approval: bool = False


class WorkflowConfigUpdate(BaseModel):
    workflow_name: Optional[str] = None
    complexity: Optional[str] = None
    stages: Optional[List[Dict[str, Any]]] = None
    segregation_of_duties: Optional[bool] = None
    delegation_enabled: Optional[bool] = None
    timeout_hours: Optional[int] = None
    escalation_rules: Optional[List[Dict[str, Any]]] = None
    failure_handling: Optional[Dict[str, Any]] = None
    requires_segregation_of_duties: Optional[bool] = None
    requires_dual_approval: Optional[bool] = None


class ProfileUpdate(BaseModel):
    operating_model: Optional[str] = None
    governance_profile: Optional[str] = None
    scaling_profile: Optional[str] = None
    enabled_capabilities: Optional[List[str]] = None
    disabled_capabilities: Optional[List[str]] = None
    interface_density: Optional[str] = None
    navigation_style: Optional[str] = None
    dashboard_layout: Optional[str] = None
    progressive_disclosure: Optional[bool] = None
    show_advanced_features: Optional[bool] = None
    workflow_complexity: Optional[str] = None
    default_approval_levels: Optional[int] = None
    segregation_of_duties: Optional[bool] = None
    delegation_enabled: Optional[bool] = None
    default_language: Optional[str] = None
    supported_languages: Optional[List[str]] = None
    default_timezone: Optional[str] = None
    date_format: Optional[str] = None
    number_format: Optional[str] = None
    currency: Optional[str] = None
    working_calendar: Optional[str] = None
    integration_configs: Optional[Dict[str, Dict[str, Any]]] = None
    feature_flags: Optional[Dict[str, bool]] = None
    governance_profile: Optional[str] = None
    require_mfa_for_admin: Optional[bool] = None
    session_timeout_minutes: Optional[int] = None
    max_failed_login_attempts: Optional[int] = None
    password_policy: Optional[Dict[str, Any]] = None
    data_retention_days: Optional[int] = None
    sensitive_data_fields: Optional[List[str]] = None
    scaling_profile: Optional[str] = None
    max_concurrent_users: Optional[int] = None
    query_timeout_seconds: Optional[int] = None
    enable_caching: Optional[bool] = None
    cache_ttl_seconds: Optional[int] = None
    ai_companion_enabled: Optional[bool] = None
    company_brain_enabled: Optional[bool] = None
    digital_twin_enabled: Optional[bool] = None
    background_intelligence_enabled: Optional[bool] = None
    auto_approve_low_risk: Optional[bool] = None
    max_auto_approval_amount: Optional[int] = None
    notification_preferences: Optional[Dict[str, Any]] = None
    email_notifications_enabled: Optional[bool] = None
    push_notifications_enabled: Optional[bool] = None
    in_app_notifications_enabled: Optional[bool] = None
    auto_adaptation_enabled: Optional[bool] = None
    adaptation_modes: Optional[List[str]] = None
    auto_transition_enabled: Optional[bool] = None
    transition_cooldown_days: Optional[int] = None
    capability_lifecycle_config: Optional[Dict[str, Any]] = None


@router.get("/profile")
async def get_profile(
    db: AsyncSession = Depends(get_db),
):
    """Get the adaptive operating profile for the organization."""
    profile = await adaptive_operating_profile_service.get_or_create_profile(db, "test-org-id")
    
    return {
        "id": profile.id,
        "organization_id": profile.organization_id,
        "version": profile.version,
        "profile_name": profile.profile_name,
        "operating_model": profile.operating_model,
        "governance_profile": profile.governance_profile,
        "scaling_profile": profile.scaling_profile,
        "enabled_capabilities": profile.enabled_capabilities,
        "disabled_capabilities": profile.disabled_capabilities,
        "interface_density": profile.interface_density,
        "navigation_style": profile.navigation_style,
        "dashboard_layout": profile.dashboard_layout,
        "progressive_disclosure": profile.progressive_disclosure,
        "show_advanced_features": profile.show_advanced_features,
        "workflow_complexity": profile.workflow_complexity,
        "default_approval_levels": profile.default_approval_levels,
        "segregation_of_duties": profile.segregation_of_duties,
        "delegation_enabled": profile.delegation_enabled,
        "default_language": profile.default_language,
        "supported_languages": profile.supported_languages,
        "default_timezone": profile.default_timezone,
        "date_format": profile.date_format,
        "number_format": profile.number_format,
        "currency": profile.currency,
        "working_calendar": profile.working_calendar,
        "integration_configs": profile.integration_configs,
        "feature_flags": profile.feature_flags,
        "governance_profile": profile.governance_profile,
        "require_mfa_for_admin": profile.require_mfa_for_admin,
        "session_timeout_minutes": profile.session_timeout_minutes,
        "max_failed_login_attempts": profile.max_failed_login_attempts,
        "password_policy": profile.password_policy,
        "data_retention_days": profile.data_retention_days,
        "sensitive_data_fields": profile.sensitive_data_fields,
        "scaling_profile": profile.scaling_profile,
        "max_concurrent_users": profile.max_concurrent_users,
        "query_timeout_seconds": profile.query_timeout_seconds,
        "enable_caching": profile.enable_caching,
        "cache_ttl_seconds": profile.cache_ttl_seconds,
        "ai_companion_enabled": profile.ai_companion_enabled,
        "company_brain_enabled": profile.company_brain_enabled,
        "digital_twin_enabled": profile.digital_twin_enabled,
        "background_intelligence_enabled": profile.background_intelligence_enabled,
        "auto_approve_low_risk": profile.auto_approve_low_risk,
        "max_auto_approval_amount": profile.max_auto_approval_amount,
        "notification_preferences": profile.notification_preferences,
        "email_notifications_enabled": profile.email_notifications_enabled,
        "push_notifications_enabled": profile.push_notifications_enabled,
        "in_app_notifications_enabled": profile.in_app_notifications_enabled,
        "auto_adaptation_enabled": profile.auto_adaptation_enabled,
        "adaptation_modes": profile.adaptation_modes,
        "auto_transition_enabled": profile.auto_transition_enabled,
        "transition_cooldown_days": profile.transition_cooldown_days,
        "capability_lifecycle_config": profile.capability_lifecycle_config,
    }


@router.patch("/profile")
async def update_profile(
    payload: ProfileUpdate,
    db: AsyncSession = Depends(get_db),
):
    data = payload.model_dump(exclude_unset=True)
    if not data:
        raise HTTPException(status_code=400, detail="No fields to update")
    
    profile = await adaptive_operating_profile_service.update_profile(
        db, "test-org-id", data, actor_id="test-user", actor_email="test@example.com"
    )
    
    return {"success": True, "profile_id": profile.id, "version": profile.version}


@router.get("/profile/versions")
async def get_profile_versions(
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
):
    versions = await adaptive_operating_profile_service.get_profile_versions(db, "test-org-id", limit)
    
    return {
        "versions": [
            {
                "version": v.version,
                "effective_from": v.effective_from.isoformat(),
                "effective_until": v.effective_until.isoformat() if v.effective_until else None,
                "changed_by": v.changed_by,
                "changed_by_email": v.changed_by_email,
                "reason": v.change_reason,
                "change_type": v.change_type,
                "affected_capabilities": v.affected_capabilities,
                "affected_workflows": v.affected_workflows,
                "affected_users": v.affected_users,
            }
            for v in versions
        ]
    }


@router.post("/profile/rollback/{version}")
async def rollback_profile(
    version: int,
    db: AsyncSession = Depends(get_db),
):
    profile = await adaptive_operating_profile_service.rollback_to_version(
        db, "test-org-id", version, "test-user", "test@example.com", "Rollback via API"
    )
    return {"success": True, "rolled_back_to_version": version, "new_version": profile.version}


@router.get("/capabilities")
async def get_capability_status(
    db: AsyncSession = Depends(get_db),
):
    status = await adaptive_operating_profile_service.get_capability_status(db, "test-org-id")
    return status


@router.post("/capabilities/{capability_key}/advance")
async def advance_capability_lifecycle(
    capability_key: str,
    target_state: str,
    db: AsyncSession = Depends(get_db),
):
    try:
        target_state_enum = CapabilityLifecycleState(target_state)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid lifecycle state: {target_state}")
    
    record = await adaptive_operating_profile_service.advance_capability_lifecycle(
        db, "test-org-id", capability_key, target_state_enum, "test-user", "test@example.com"
    )
    
    return {
        "capability_key": record.capability_key,
        "previous_state": record.previous_state,
        "current_state": record.current_state,
        "version": record.version,
    }


@router.get("/capabilities/{capability_key}/status")
async def get_capability_record(
    capability_key: str,
    db: AsyncSession = Depends(get_db),
):
    record = await adaptive_operating_profile_service.get_capability_record(db, "test-org-id", capability_key)
    if not record:
        raise HTTPException(status_code=404, detail="Capability not found")
    
    return {
        "capability_key": record.capability_key,
        "current_state": record.current_state,
        "prerequisites_met": record.prerequisites_met,
        "configuration_valid": record.configuration_valid,
        "governance_approved": record.governance_approved,
        "entitlement_verified": record.entitlement_verified,
        "activation_approved": record.activation_approved,
        "health_status": record.health_status,
        "version": record.version,
    }


@router.get("/integrations")
async def get_integration_health(
    db: AsyncSession = Depends(get_db),
):
    health = await adaptive_operating_profile_service.get_integration_health(db, "test-org-id")
    return health


@router.post("/integrations/{integration_key}/state")
async def update_integration_state(
    integration_key: str,
    state: str,
    config: Optional[Dict] = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        state_enum = IntegrationState(state)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid integration state: {state}")
    
    config_record = await adaptive_operating_profile_service.update_integration_state(
        db, "test-org-id", integration_key, state_enum, config
    )
    
    return {
        "integration_key": config_record.integration_key,
        "state": config_record.state,
        "health": config_record.health_status,
        "last_sync": config_record.last_sync_at.isoformat() if config_record.last_sync_at else None,
    }


@router.post("/integrations/{integration_key}/sync")
async def record_sync_result(
    integration_key: str,
    success: bool,
    error: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
):
    await adaptive_operating_profile_service.record_sync_result(
        db, "test-org-id", integration_key, success, error
    )
    return {"success": True}


@router.post("/workflows")
async def create_workflow_config(
    payload: WorkflowConfigCreate,
    db: AsyncSession = Depends(get_db),
):
    config = await adaptive_operating_profile_service.create_workflow_config(
        db, "test-org-id", payload.workflow_key, payload.workflow_name,
        payload.workflow_type, payload.complexity, payload.stages, "test-user"
    )
    return {"success": True, "workflow_key": config.workflow_key, "version": config.version}


@router.get("/workflows/{workflow_key}")
async def get_workflow_config(
    workflow_key: str,
    db: AsyncSession = Depends(get_db),
):
    config = await adaptive_operating_profile_service.get_workflow_config(db, "test-org-id", workflow_key)
    if not config:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    return {
        "workflow_key": config.workflow_key,
        "workflow_name": config.workflow_name,
        "workflow_type": config.workflow_type,
        "complexity": config.complexity,
        "stages": config.stages,
        "segregation_of_duties": config.segregation_of_duties,
        "delegation_enabled": config.delegation_enabled,
        "timeout_hours": config.timeout_hours,
        "escalation_rules": config.escalation_rules,
        "failure_handling": config.failure_handling,
        "policy_version": config.policy_version,
        "requires_segregation_of_duties": config.requires_segregation_of_duties,
        "requires_dual_approval": config.requires_dual_approval,
    }


@router.patch("/workflows/{workflow_key}")
async def update_workflow_config(
    workflow_key: str,
    payload: WorkflowConfigUpdate,
    db: AsyncSession = Depends(get_db),
):
    config = await adaptive_operating_profile_service.update_workflow_config(
        db, "test-org-id", workflow_key, payload.model_dump(exclude_unset=True), "test-user"
    )
    return {"success": True, "version": config.version}


@router.post("/recommendations")
async def create_recommendation(
    payload: dict,
    db: AsyncSession = Depends(get_db),
):
    # This is a simplified endpoint for creating recommendations
    rec = await adaptive_operating_profile_service.create_recommendation(
        db=db,
        organization_id="test-org-id",
        recommendation_type=payload.get("recommendation_type", "capability"),
        title=payload.get("title", ""),
        description=payload.get("description", ""),
        rationale=payload.get("rationale", ""),
        evidence=payload.get("evidence", []),
        confidence=payload.get("confidence", 0.8),
        impact_level=payload.get("impact_level", "medium"),
        affected_capabilities=payload.get("affected_capabilities", []),
        affected_workflows=payload.get("affected_workflows", []),
        estimated_effort=payload.get("estimated_effort", "medium"),
        requires_approval=payload.get("requires_approval", True),
        triggered_by="api",
        source_context=payload.get("source_context", {}),
    )
    return {"success": True, "recommendation_id": rec.id}


@router.post("/recommendations/{recommendation_id}/approve")
async def approve_recommendation(
    recommendation_id: str,
    db: AsyncSession = Depends(get_db),
):
    rec = await adaptive_operating_profile_service.approve_recommendation(db, recommendation_id, "test-user")
    return {"success": True, "recommendation_id": rec.id, "status": rec.status}


@router.post("/recommendations/{recommendation_id}/apply")
async def apply_recommendation(
    recommendation_id: str,
    db: AsyncSession = Depends(get_db),
):
    rec = await adaptive_operating_profile_service.apply_recommendation(db, recommendation_id, "test-user")
    return {"success": True, "recommendation_id": rec.id, "status": rec.status}


@router.get("/recommendations")
async def get_recommendations(
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = None,
    limit: int = 50,
):
    recs = await adaptive_operating_profile_service.get_recommendations(db, "test-org-id", status, limit)
    return {
        "recommendations": [
            {
                "id": r.id,
                "type": r.recommendation_type,
                "title": r.title,
                "status": r.status,
                "confidence": r.confidence,
                "impact_level": r.impact_level,
            }
            for r in recs
        ]
    }


@router.post("/recommendations/auto-apply")
async def auto_apply_recommendations(
    db: AsyncSession = Depends(get_db),
):
    applied = await adaptive_operating_profile_service.auto_apply_recommendations(db, "test-org-id", "system")
    return {"applied_count": len(applied), "applied": [r.id for r in applied]}


@router.get("/analytics")
async def get_adaptation_analytics(
    db: AsyncSession = Depends(get_db),
):
    analytics = await adaptive_operating_profile_service.get_adaptation_analytics(db, "test-org-id")
    return analytics


@router.get("/capabilities")
async def get_all_capabilities():
    return {
        "capabilities": [{"key": c.value, "label": c.value.replace("_", " ").title()} for c in CapabilityKey],
        "operating_models": [{"key": m.value, "label": m.value.replace("_", " ").title()} for m in OperatingModel],
        "governance_profiles": [{"key": g.value, "label": g.value.title()} for g in GovernanceProfile],
        "scaling_profiles": [{"key": s.value, "label": s.value.title()} for s in ScalingProfile],
        "integration_states": [{"key": s.value, "label": s.value.replace("_", " ").title()} for s in IntegrationState],
        "lifecycle_states": [{"key": s.value, "label": s.value.replace("_", " ").title()} for s in CapabilityLifecycleState],
        "adaptation_modes": [{"key": a.value, "label": a.value.title()} for a in AdaptationMode],
    }


adaptive_operating_profile_router = router