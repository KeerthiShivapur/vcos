from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.services.company_experience_service import company_experience_service
from app.services.adaptive_experience_engine import adaptive_experience_engine, AdaptiveContext, UserContextRole, GeographicContext
from app.models.company_experience import CompanyExperienceProfile
from app.api.deps import get_current_user, get_current_organization
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/company-experience", tags=["company-experience"])


class CompanyExperienceConfigUpdate(BaseModel):
    experience_profile: Optional[str] = Field(
        default=None, pattern="^(startup|growing|mid_market|large_enterprise|global_enterprise)$"
    )
    employee_count: Optional[int] = Field(default=None, ge=0)
    organizational_depth: Optional[int] = Field(default=None, ge=1)
    organizational_unit_count: Optional[int] = Field(default=None, ge=0)
    legal_entity_count: Optional[int] = Field(default=None, ge=1)
    geographic_footprint_count: Optional[int] = Field(default=None, ge=1)
    governance_complexity: Optional[str] = Field(default=None, pattern="^(simple|standard|complex|delegated|federated)$")
    workflow_complexity: Optional[str] = Field(default=None, pattern="^(simple|conditional|complex)$")
    enabled_modules: Optional[List[str]] = None
    default_dashboard_layout: Optional[str] = None
    navigation_density: Optional[str] = Field(default=None, pattern="^(comfortable|compact|dense)$")
    progressive_disclosure: Optional[bool] = None
    show_advanced_features: Optional[bool] = None
    default_language: Optional[str] = None
    supported_languages: Optional[List[str]] = None
    timezone: Optional[str] = None
    date_format: Optional[str] = None
    number_format: Optional[str] = None
    feature_flags: Optional[dict] = None
    changed_by: Optional[str] = None
    reason: Optional[str] = None
    metadata_json: Optional[dict] = None


class CompanyExperienceConfigOut(BaseModel):
    id: str
    organization_id: str
    experience_profile: str
    employee_count: int
    organizational_depth: int
    organizational_unit_count: int
    legal_entity_count: int
    geographic_footprint_count: int
    governance_complexity: str
    approval_levels: int
    integration_count: int
    workflow_complexity: str
    enabled_modules: List[str]
    default_dashboard_layout: str
    navigation_density: str
    progressive_disclosure: bool
    show_advanced_features: bool
    default_language: str
    supported_languages: List[str]
    timezone: str
    date_format: str
    number_format: str
    feature_flags: dict
    configured_by: Optional[str] = None
    configured_at: Optional[str] = None
    last_profile_change: Optional[str] = None
    previous_profile: Optional[str] = None


@router.get("/config", response_model=CompanyExperienceConfigOut)
async def get_experience_config(
    db: AsyncSession = Depends(get_db),
    # user: User = Depends(require_permission("organization:read")),
    # org: Organization = Depends(get_current_organization),
):
    """Get the company experience configuration."""
    # For now, use a mock organization ID
    org_id = "test-org-id"
    config = await company_experience_service.get_or_create_experience_config(db, org_id)
    
    return CompanyExperienceConfigOut(
        id=config.id,
        organization_id=config.organization_id,
        experience_profile=config.experience_profile.value,
        employee_count=config.employee_count,
        organizational_depth=config.organizational_depth,
        organizational_unit_count=config.organizational_unit_count,
        legal_entity_count=config.legal_entity_count,
        geographic_footprint_count=config.geographic_footprint_count,
        governance_complexity=config.governance_complexity,
        approval_levels=config.approval_levels,
        integration_count=config.integration_count,
        workflow_complexity=config.workflow_complexity,
        enabled_modules=config.enabled_modules,
        default_dashboard_layout=config.default_dashboard_layout,
        navigation_density=config.navigation_density,
        progressive_disclosure=config.progressive_disclosure,
        show_advanced_features=config.show_advanced_features,
        default_language=config.default_language,
        supported_languages=config.supported_languages,
        timezone=config.timezone,
        date_format=config.date_format,
        number_format=config.number_format,
        feature_flags=config.feature_flags,
        configured_by=config.configured_by,
        configured_at=config.configured_at.isoformat() if config.configured_at else None,
        last_profile_change=config.last_profile_change.isoformat() if config.last_profile_change else None,
        previous_profile=config.previous_profile,
    )


@router.patch("/config", response_model=CompanyExperienceConfigOut)
async def update_experience_config(
    payload: CompanyExperienceConfigUpdate,
    db: AsyncSession = Depends(get_db),
    # user: User = Depends(require_permission("organization:update")),
    # org: Organization = Depends(get_current_organization),
):
    """Update company experience configuration."""
    org_id = "test-org-id"
    data = payload.model_dump(exclude_unset=True)
    config = await company_experience_service.update_experience_config(
        db, org_id, data, actor_id="test-user", actor_email="test@example.com"
    )
    
    return CompanyExperienceConfigOut(
        id=config.id,
        organization_id=config.organization_id,
        experience_profile=config.experience_profile.value,
        employee_count=config.employee_count,
        organizational_depth=config.organizational_depth,
        organizational_unit_count=config.organizational_unit_count,
        legal_entity_count=config.legal_entity_count,
        geographic_footprint_count=config.geographic_footprint_count,
        governance_complexity=config.governance_complexity,
        approval_levels=config.approval_levels,
        integration_count=config.integration_count,
        workflow_complexity=config.workflow_complexity,
        enabled_modules=config.enabled_modules,
        default_dashboard_layout=config.default_dashboard_layout,
        navigation_density=config.navigation_density,
        progressive_disclosure=config.progressive_disclosure,
        show_advanced_features=config.show_advanced_features,
        default_language=config.default_language,
        supported_languages=config.supported_languages,
        timezone=config.timezone,
        date_format=config.date_format,
        number_format=config.number_format,
        feature_flags=config.feature_flags,
        configured_by=config.configured_by,
        configured_at=config.configured_at.isoformat() if config.configured_at else None,
        last_profile_change=config.last_profile_change.isoformat() if config.last_profile_change else None,
        previous_profile=config.previous_profile,
    )


@router.get("/profile", response_model=dict)
async def get_experience_profile(
    db: AsyncSession = Depends(get_db),
    # user: User = Depends(require_permission("organization:read")),
    # org: Organization = Depends(get_current_organization),
):
    """Get current and suggested experience profile."""
    org_id = "test-org-id"
    config = await company_experience_service.get_experience_config(db, org_id)
    current_profile = config.experience_profile.value if config and config.experience_profile else "startup"
    
    suggested = await company_experience_service.resolve_profile_for_organization(db, org_id)
    
    return {
        "suggested_profile": suggested.value,
        "current_profile": current_profile,
        "organization_complexity": {
            "employee_count": 50,
            "organizational_depth": 2,
            "organizational_unit_count": 5,
            "legal_entity_count": 1,
            "geographic_footprint_count": 1,
            "governance_complexity": "standard",
            "workflow_complexity": "standard",
        },
        "score_breakdown": {
            "employee_score": 25,
            "depth_score": 10,
            "units_score": 15,
            "entities_score": 5,
            "geo_score": 5,
            "governance_score": 10,
            "workflow_score": 10,
            "total_score": 80,
        },
    }


@router.get("/capabilities")
async def get_profile_capabilities(
    db: AsyncSession = Depends(get_db),
):
    config = await company_experience_service.get_experience_config(db, "test-org-id")
    if config:
        from app.models.company_experience import get_profile_capabilities
        caps = get_profile_capabilities(config.experience_profile)
        return ProfileCapabilitiesOut(**caps)
    return ProfileCapabilitiesOut(
        modules=[],
        navigation_groups=[],
        max_org_depth=1,
        max_departments=3,
        max_teams=2,
        governance_level="simple",
        approval_levels=1,
        modules_enabled_by_default=[],
    )


@router.get("/adaptive")
async def get_adaptive_experience(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Organization = Depends(get_current_organization),
):
    """Get the complete adaptive experience configuration for the current user/context."""
    # Resolve user context role from permissions/roles
    user_role = UserContextRole.EMPLOYEE
    # TODO: Resolve actual role from user's permissions/roles
    # For now, check if user has admin permissions
    # This would be replaced with actual role resolution from permissions
    
    # Build adaptive context from authenticated user
    context = AdaptiveContext(
        organization_id=org.id,
        user_id=user.id,
        user_role=user_role,
        user_permissions=set(),  # TODO: Resolve from permission service
        geographic_context=GeographicContext.GLOBAL,
        device_type="desktop",
    )
    
    # Resolve adaptive experience using the engine
    config = await adaptive_experience_engine.resolve_adaptive_experience(db, context)
    
    return {
        "profile": config.profile.value,
        "navigation_groups": [
            {
                "key": g.key,
                "label": g.label,
                "modules": [
                    {
                        "key": m.key,
                        "label": m.label,
                        "icon": m.icon,
                        "description": m.description,
                        "required_permissions": m.required_permissions,
                        "priority": m.priority,
                        "progressive_disclosure": m.progressive_disclosure,
                        "badge_count": m.badge_count,
                        "badge_label": m.badge_label,
                    }
                    for m in g.modules
                ],
                "profile_requirements": [p.value for p in g.profile_requirements],
                "role_affinity": {k.value: v for k, v in g.role_affinity.items()},
                "priority": g.priority,
                "collapsible": g.collapsible,
                "default_collapsed": g.default_collapsed,
            }
            for g in config.navigation_groups
        ],
        "visible_modules": config.visible_modules,
        "dashboard_layout": config.dashboard_layout,
        "navigation_density": config.navigation_density,
        "progressive_disclosure": config.progressive_disclosure,
        "show_advanced_features": config.show_advanced_features,
        "feature_flags": config.feature_flags,
        "company_brain_insights": config.company_brain_insights,
        "digital_twin_overlay": config.digital_twin_overlay,
        "recommended_actions": config.recommended_actions,
        "context_fingerprint": config.context_fingerprint,
        "resolved_at": config.resolved_at.isoformat(),
    }


@router.get("/transition/preview")
async def preview_profile_transition(
    target_profile: str,
    db: AsyncSession = Depends(get_db),
):
    """Preview what would change if transitioning to a target profile."""
    from app.models.company_experience import CompanyExperienceProfile
    try:
        target = CompanyExperienceProfile(target_profile)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid profile")
    
    # Get current config
    config = await company_experience_service.get_experience_config(db, org.id)
    if not config:
        raise HTTPException(status_code=404, detail="Company experience config not found")
    
    current_profile = config.experience_profile
    current_caps = get_profile_capabilities(current_profile)
    target_caps = get_profile_capabilities(target)
    
    # Calculate differences
    current_modules = set(current_caps.get("modules", []))
    target_modules = set(target_caps.get("modules", []))
    modules_added = list(target_modules - current_modules)
    modules_removed = list(current_modules - target_modules)
    
    current_nav = set(current_caps.get("navigation_groups", []))
    target_nav = set(target_caps.get("navigation_groups", []))
    nav_groups_added = list(target_nav - current_nav)
    nav_groups_removed = list(current_nav - target_nav)
    
    return {
        "current_profile": current_profile.value,
        "target_profile": target_profile,
        "modules_added": modules_added,
        "modules_removed": modules_removed,
        "navigation_groups_added": nav_groups_added,
        "navigation_groups_removed": nav_groups_removed,
        "governance_level_change": {
            "from": current_caps.get("governance_level", "simple"),
            "to": target_caps.get("governance_level", "simple"),
        },
        "approval_levels_change": {
            "from": current_caps.get("approval_levels", 1),
            "to": target_caps.get("approval_levels", 1),
        },
        "new_features": target_caps.get("features", []),
    }


class ProfileTransitionRequest(BaseModel):
    new_profile: str = Field(..., pattern="^(startup|growing|mid_market|large_enterprise|global_enterprise)$")
    reason: Optional[str] = None


@router.post("/transition", response_model=dict)
async def transition_profile(
    request: ProfileTransitionRequest,
    db: AsyncSession = Depends(get_db),
):
    """Transition organization to a new experience profile."""
    from app.models.company_experience import CompanyExperienceProfile
    from app.services.company_experience_service import company_experience_service
    
    try:
        target_profile = CompanyExperienceProfile(request.new_profile)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid profile")
    
    config = await company_experience_service.transition_profile(
        db, "test-org-id", target_profile, "test-user", "test@example.com", request.reason
    )
    
    return {
        "success": True,
        "previous_profile": "startup",
        "new_profile": request.new_profile,
        "reason": request.reason,
    }


@router.get("/module-access/{module_key}")
async def check_module_access(
    module_key: str,
    db: AsyncSession = Depends(get_db),
):
    """Check if a module is accessible for the current organization/user."""
    config = await company_experience_service.get_experience_config(db, "test-org-id")
    if not config:
        return {"accessible": False, "reason": "No configuration found"}
    
    has_access = config.should_show_module(module_key)
    return {"module_key": module_key, "accessible": has_access}


class ProfileCapabilitiesOut(BaseModel):
    modules: List[str]
    navigation_groups: List[str]
    max_org_depth: int
    max_departments: int
    max_teams: int
    governance_level: str
    approval_levels: int
    modules_enabled_by_default: List[str]
    features: Optional[List[str]] = None