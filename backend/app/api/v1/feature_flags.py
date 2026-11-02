"""Feature Flags API — Gate 19

REST endpoints for governed feature flag management.

Architecture:
- Feature flags = CONTROL PLANE state (feature availability)
- Authorization = SEPARATE system (actor permissions)
- Governance = SEPARATE system (organizational policy)
- These boundaries MUST NEVER collapse

All mutating endpoints require appropriate permissions.
All operations are tenant-scoped.
All changes are audited.
"""

import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.models.feature_flags import (
    FeatureFlagAuditLog,
    FeatureFlagHistory,
)
from app.services.feature_flags_service import (
    FeatureFlagService,
    FeatureFlagError,
    FeatureFlagNotFoundError,
    FeatureFlagConflictError,
    FeatureFlagValidationError,
    FeatureFlagGovernanceError,
    FeatureFlagTenantIsolationError,
    EvaluationResult,
    FEATURE_FLAG_PERMISSIONS,
    get_feature_flag_service,
)

logger = logging.getLogger("vcos.api.feature_flags")

router = APIRouter(prefix="/feature-flags", tags=["feature-flags"])


# ============================================================
# Request/Response Models
# ============================================================

class FeatureFlagCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    name: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    status: str = Field(default="off", pattern=r"^(off|beta|alpha|enabled|deprecated|archived)$")
    rollout_strategy: str = Field(default="all", pattern=r"^(all|percentage|segment|ring|custom)$")
    rollout_config: Dict[str, Any] = Field(default_factory=dict)
    scope: str = Field(default="tenant", pattern=r"^(global|tenant|user)$")
    depends_on: List[str] = Field(default_factory=list)
    conflicts_with: List[str] = Field(default_factory=list)
    owner_id: Optional[str] = None
    team_id: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class FeatureFlagUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    status: Optional[str] = Field(None, pattern=r"^(off|beta|alpha|enabled|deprecated|archived)$")
    rollout_strategy: Optional[str] = Field(None, pattern=r"^(all|percentage|segment|ring|custom)$")
    rollout_config: Optional[Dict[str, Any]] = None
    scope: Optional[str] = Field(None, pattern=r"^(global|tenant|user)$")
    depends_on: Optional[List[str]] = None
    conflicts_with: Optional[List[str]] = None
    owner_id: Optional[str] = None
    team_id: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None
    governance_context: Optional[Dict[str, Any]] = None
    version: Optional[int] = None


class FeatureFlagResponse(BaseModel):
    id: str
    organization_id: str
    key: str
    name: str
    description: Optional[str]
    status: str
    rollout_strategy: str
    rollout_config: Dict[str, Any]
    scope: str
    depends_on: List[str]
    conflicts_with: List[str]
    owner_id: Optional[str]
    team_id: Optional[str]
    tags: List[str]
    metadata: Dict[str, Any]
    enabled_at: Optional[str]
    deprecated_at: Optional[str]
    deprecated_reason: Optional[str]
    archived_at: Optional[str]
    archived_reason: Optional[str]
    emergency_disabled: bool
    emergency_disabled_at: Optional[str]
    emergency_disabled_by: Optional[str]
    emergency_disabled_reason: Optional[str]
    exposure_count: int
    last_evaluated_at: Optional[str]
    fingerprint: str
    version: int
    governance_context: Dict[str, Any]
    created_at: str
    updated_at: str

    class Config:
        from_attributes = True


class EvaluationRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    user_id: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    actor_roles: List[str] = Field(default_factory=list)
    actor_permissions: List[str] = Field(default_factory=list)


class EvaluationResponse(BaseModel):
    flag_id: str
    flag_key: str
    available: bool  # Renamed from 'enabled' to clarify this is availability
    reason: str
    evaluated_at: str
    context: Dict[str, Any]
    flag_version: int
    flag_status: str
    rollout_strategy: str


class MultiEvaluationRequest(BaseModel):
    keys: List[str] = Field(..., min_length=1, max_length=50)
    user_id: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)
    actor_roles: List[str] = Field(default_factory=list)
    actor_permissions: List[str] = Field(default_factory=list)


class AuthorizationEvaluationRequest(BaseModel):
    key: str = Field(..., min_length=1, max_length=100)
    user_id: str
    required_permission: Optional[str] = None
    context: Dict[str, Any] = Field(default_factory=dict)


class AuthorizationEvaluationResponse(BaseModel):
    allowed: bool
    reason: str
    feature_available: bool
    feature_reason: str
    authorized: bool


class RolloutPercentageRequest(BaseModel):
    percentage: float = Field(..., ge=0, le=100)
    version: Optional[int] = None
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class RolloutSegmentsRequest(BaseModel):
    segments: List[str] = Field(..., min_length=1)
    version: Optional[int] = None
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class RolloutRingsRequest(BaseModel):
    rings: List[str] = Field(..., min_length=1)
    version: Optional[int] = None
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class RolloutCustomRequest(BaseModel):
    custom_rules: List[Dict[str, Any]] = Field(..., min_length=1)
    version: Optional[int] = None
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class DeprecateRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=500)
    version: Optional[int] = None
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class ArchiveRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)
    version: Optional[int] = None
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class EmergencyDisableRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class EmergencyEnableRequest(BaseModel):
    reason: str = Field(..., min_length=1, max_length=1000)
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class PromotionRequest(BaseModel):
    ring: str = Field(default="canary", pattern=r"^(canary|early|broad)$")
    percentage: float = Field(default=10.0, ge=0, le=100)
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class BetaPromotionRequest(BaseModel):
    percentage: float = Field(default=50.0, ge=0, le=100)
    governance_context: Dict[str, Any] = Field(default_factory=dict)


class EvaluationStatsResponse(BaseModel):
    total_evaluations: int
    available_evaluations: int
    unavailable_evaluations: int
    unique_users: int
    availability_rate: float
    period_days: int


class FlagHealthResponse(BaseModel):
    total_flags: int
    by_status: Dict[str, int]
    deprecated_count: int
    stale_enabled_count: int
    emergency_disabled_count: int
    health_score: float


class AuditLogResponse(BaseModel):
    id: str
    organization_id: str
    feature_flag_id: Optional[str]
    actor_id: str
    action: str
    before_state: Optional[Dict[str, Any]]
    after_state: Optional[Dict[str, Any]]
    governance_context: Dict[str, Any]
    reason: Optional[str]
    request_id: Optional[str]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class HistoryResponse(BaseModel):
    id: str
    organization_id: str
    feature_flag_id: str
    key: str
    name: str
    status: str
    rollout_strategy: str
    rollout_config: Dict[str, Any]
    scope: str
    depends_on: List[str]
    conflicts_with: List[str]
    emergency_disabled: bool
    governance_context: Dict[str, Any]
    flag_version: int
    snapshot_version: int
    valid_from: str
    valid_to: Optional[str]
    actor_id: Optional[str]
    action: str
    created_at: str

    class Config:
        from_attributes = True


class TimelineResponse(BaseModel):
    flag_id: str
    flag_key: str
    timeline: List[Dict[str, Any]]


class PrivateAlphaConfigResponse(BaseModel):
    entitled: bool
    flags: List[Dict[str, Any]]


# ============================================================
# Helpers
# ============================================================

def _extract_request_metadata(request: Request) -> Dict[str, Optional[str]]:
    """Extract request metadata for audit logging."""
    return {
        "request_id": request.headers.get("x-request-id"),
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent"),
    }


def _to_response(flag) -> FeatureFlagResponse:
    """Convert FeatureFlag model to response."""
    return FeatureFlagResponse(
        id=flag.id,
        organization_id=flag.organization_id,
        key=flag.key,
        name=flag.name,
        description=flag.description,
        status=flag.status,
        rollout_strategy=flag.rollout_strategy,
        rollout_config=flag.rollout_config or {},
        scope=flag.scope,
        depends_on=flag.depends_on or [],
        conflicts_with=flag.conflicts_with or [],
        owner_id=flag.owner_id,
        team_id=flag.team_id,
        tags=flag.tags or [],
        metadata=flag.metadata_json or {},
        enabled_at=flag.enabled_at.isoformat() if flag.enabled_at else None,
        deprecated_at=flag.deprecated_at.isoformat() if flag.deprecated_at else None,
        deprecated_reason=flag.deprecated_reason,
        archived_at=flag.archived_at.isoformat() if flag.archived_at else None,
        archived_reason=flag.archived_reason,
        emergency_disabled=flag.emergency_disabled,
        emergency_disabled_at=flag.emergency_disabled_at.isoformat() if flag.emergency_disabled_at else None,
        emergency_disabled_by=flag.emergency_disabled_by,
        emergency_disabled_reason=flag.emergency_disabled_reason,
        exposure_count=flag.exposure_count,
        last_evaluated_at=flag.last_evaluated_at.isoformat() if flag.last_evaluated_at else None,
        fingerprint=flag.fingerprint,
        version=flag.version,
        governance_context=flag.governance_context or {},
        created_at=flag.created_at.isoformat(),
        updated_at=flag.updated_at.isoformat(),
    )


def _to_evaluation_response(result: EvaluationResult) -> EvaluationResponse:
    """Convert EvaluationResult to response."""
    return EvaluationResponse(
        flag_id=result.flag_id,
        flag_key=result.flag_key,
        available=result.available,
        reason=result.reason,
        evaluated_at=result.evaluated_at.isoformat(),
        context=result.context,
        flag_version=result.flag_version,
        flag_status=result.flag_status,
        rollout_strategy=result.rollout_strategy,
    )


def _to_audit_response(audit: FeatureFlagAuditLog) -> AuditLogResponse:
    return AuditLogResponse(
        id=audit.id,
        organization_id=audit.organization_id,
        feature_flag_id=audit.feature_flag_id,
        actor_id=audit.actor_id,
        action=audit.action,
        before_state=audit.before_state,
        after_state=audit.after_state,
        governance_context=audit.governance_context or {},
        reason=audit.reason,
        request_id=audit.request_id,
        ip_address=audit.ip_address,
        user_agent=audit.user_agent,
        created_at=audit.created_at.isoformat(),
    )


def _to_history_response(h: FeatureFlagHistory) -> HistoryResponse:
    return HistoryResponse(
        id=h.id,
        organization_id=h.organization_id,
        feature_flag_id=h.feature_flag_id,
        key=h.key,
        name=h.name,
        status=h.status,
        rollout_strategy=h.rollout_strategy,
        rollout_config=h.rollout_config,
        scope=h.scope,
        depends_on=h.depends_on,
        conflicts_with=h.conflicts_with,
        emergency_disabled=h.emergency_disabled,
        governance_context=h.governance_context or {},
        flag_version=h.flag_version,
        snapshot_version=h.snapshot_version,
        valid_from=h.valid_from.isoformat(),
        valid_to=h.valid_to.isoformat() if h.valid_to else None,
        actor_id=h.actor_id,
        action=h.action,
        created_at=h.created_at.isoformat(),
    )


# ============================================================
# Permission Dependency
# ============================================================

async def _require_permission(
    permission_code: str,
    organization_id: str,
    user_id: str,
    session: AsyncSession,
) -> None:
    """Require permission for feature flag operation."""
    from app.models.permission_helpers import user_permission_codes
    
    user_perms = await user_permission_codes(
        session,
        organization_id=organization_id,
        user_id=user_id,
    )
    
    if permission_code not in user_perms:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Missing permission: {permission_code}",
        )


# ============================================================
# CRUD Endpoints
# ============================================================

@router.post("", response_model=FeatureFlagResponse, status_code=status.HTTP_201_CREATED)
async def create_feature_flag(
    request: Request,
    payload: FeatureFlagCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Create a new feature flag. Requires feature_flags:create permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.create_flag(
            organization_id=org.id,
            key=payload.key,
            name=payload.name,
            actor_id=user.id,
            description=payload.description,
            status=payload.status,
            rollout_strategy=payload.rollout_strategy,
            rollout_config=payload.rollout_config,
            scope=payload.scope,
            depends_on=payload.depends_on,
            conflicts_with=payload.conflicts_with,
            owner_id=payload.owner_id,
            team_id=payload.team_id,
            tags=payload.tags,
            metadata=payload.metadata,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("", response_model=List[FeatureFlagResponse])
async def list_feature_flags(
    request: Request,
    status: Optional[str] = Query(None, pattern=r"^(off|beta|alpha|enabled|deprecated|archived)$"),
    scope: Optional[str] = Query(None, pattern=r"^(global|tenant|user)$"),
    tags: Optional[List[str]] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """List feature flags with filters. Requires feature_flags:read permission."""
    service = await get_feature_flag_service(session)
    
    try:
        flags = await service.list_flags(
            organization_id=org.id,
            actor_id=user.id,
            status=status,
            scope=scope,
            tags=tags,
            limit=limit,
            offset=offset,
        )
        return [_to_response(f) for f in flags]
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{flag_id}", response_model=FeatureFlagResponse)
async def get_feature_flag(
    request: Request,
    flag_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get a feature flag by ID. Requires feature_flags:read permission."""
    service = await get_feature_flag_service(session)
    
    await _require_permission(FEATURE_FLAG_PERMISSIONS["read"], org.id, user.id, session)
    
    flag = await service.get_flag(org.id, flag_id)
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return _to_response(flag)


@router.get("/by-key/{key}", response_model=FeatureFlagResponse)
async def get_feature_flag_by_key(
    request: Request,
    key: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get a feature flag by key. Requires feature_flags:read permission."""
    service = await get_feature_flag_service(session)
    
    await _require_permission(FEATURE_FLAG_PERMISSIONS["read"], org.id, user.id, session)
    
    flag = await service.get_flag_by_key(org.id, key)
    if not flag:
        raise HTTPException(status_code=404, detail="Feature flag not found")
    return _to_response(flag)


@router.patch("/{flag_id}", response_model=FeatureFlagResponse)
async def update_feature_flag(
    request: Request,
    flag_id: str,
    payload: FeatureFlagUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Update a feature flag. Requires feature_flags:update permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.update_flag(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            name=payload.name,
            description=payload.description,
            status=payload.status,
            rollout_strategy=payload.rollout_strategy,
            rollout_config=payload.rollout_config,
            scope=payload.scope,
            depends_on=payload.depends_on,
            conflicts_with=payload.conflicts_with,
            owner_id=payload.owner_id,
            team_id=payload.team_id,
            tags=payload.tags,
            metadata=payload.metadata,
            version=payload.version,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.delete("/{flag_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_feature_flag(
    request: Request,
    flag_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Delete a feature flag. Requires feature_flags:delete permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        await service.delete_flag(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================
# EVALUATION ENDPOINTS (Feature Availability - NOT Authorization)
# ============================================================

@router.post("/evaluate", response_model=EvaluationResponse)
async def evaluate_feature_flag(
    request: Request,
    payload: EvaluationRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Evaluate a single feature flag for availability.
    
    Returns FEATURE AVAILABILITY only, not authorization.
    Requires feature_flags:evaluate permission.
    """
    service = await get_feature_flag_service(session)
    
    await _require_permission(FEATURE_FLAG_PERMISSIONS["evaluate"], org.id, user.id, session)
    
    result = await service.evaluate_flag(
        organization_id=org.id,
        key=payload.key,
        user_id=payload.user_id or user.id,
        context=payload.context,
        actor_roles=payload.actor_roles,
        actor_permissions=payload.actor_permissions,
    )
    return _to_evaluation_response(result)


@router.post("/evaluate-batch", response_model=Dict[str, EvaluationResponse])
async def evaluate_feature_flags_batch(
    request: Request,
    payload: MultiEvaluationRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Evaluate multiple feature flags for availability.
    
    Returns FEATURE AVAILABILITY only, not authorization.
    Requires feature_flags:evaluate permission.
    """
    service = await get_feature_flag_service(session)
    
    await _require_permission(FEATURE_FLAG_PERMISSIONS["evaluate"], org.id, user.id, session)
    
    results = await service.evaluate_multiple(
        organization_id=org.id,
        keys=payload.keys,
        user_id=payload.user_id or user.id,
        context=payload.context,
        actor_roles=payload.actor_roles,
        actor_permissions=payload.actor_permissions,
    )
    return {k: _to_evaluation_response(v) for k, v in results.items()}


@router.post("/evaluate-with-auth", response_model=AuthorizationEvaluationResponse)
async def evaluate_with_authorization(
    request: Request,
    payload: AuthorizationEvaluationRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Evaluate feature availability AND authorization together.
    
    This is the CORRECT way to check if an actor can use a feature:
    1. Is the feature available? (feature flag)
    2. Is the actor authorized? (permission system)
    
    Requires feature_flags:evaluate permission.
    """
    service = await get_feature_flag_service(session)
    
    await _require_permission(FEATURE_FLAG_PERMISSIONS["evaluate"], org.id, user.id, session)
    
    allowed, reason = await service.evaluate_with_authorization(
        organization_id=org.id,
        key=payload.key,
        user_id=payload.user_id,
        required_permission=payload.required_permission,
        context=payload.context,
    )
    
    # Also get feature availability details
    eval_result = await service.evaluate_flag(
        organization_id=org.id,
        key=payload.key,
        user_id=payload.user_id,
        context=payload.context,
    )
    
    return AuthorizationEvaluationResponse(
        allowed=allowed,
        reason=reason,
        feature_available=eval_result.available,
        feature_reason=eval_result.reason,
        authorized=allowed and eval_result.available,
    )


# ============================================================
# STATUS TRANSITION ENDPOINTS (Governed)
# ============================================================

@router.post("/{flag_id}/enable", response_model=FeatureFlagResponse)
async def enable_feature_flag(
    request: Request,
    flag_id: str,
    version: Optional[int] = None,
    governance_context: Dict[str, Any] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Enable a feature flag. Requires feature_flags:lifecycle permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.enable_flag(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            version=version,
            governance_context=governance_context or {},
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{flag_id}/disable", response_model=FeatureFlagResponse)
async def disable_feature_flag(
    request: Request,
    flag_id: str,
    version: Optional[int] = None,
    governance_context: Dict[str, Any] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Disable a feature flag (set to 'off'). Requires feature_flags:lifecycle permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.disable_flag(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            version=version,
            governance_context=governance_context or {},
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{flag_id}/deprecate", response_model=FeatureFlagResponse)
async def deprecate_feature_flag(
    request: Request,
    flag_id: str,
    payload: DeprecateRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Deprecate a feature flag. Requires feature_flags:lifecycle permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.deprecate_flag(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            reason=payload.reason,
            version=payload.version,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{flag_id}/archive", response_model=FeatureFlagResponse)
async def archive_feature_flag(
    request: Request,
    flag_id: str,
    payload: ArchiveRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Archive a feature flag (terminal state). Requires feature_flags:lifecycle permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.archive_flag(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            reason=payload.reason,
            version=payload.version,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================
# EMERGENCY KILL SWITCH (Governed)
# ============================================================

@router.post("/{flag_id}/emergency-disable", response_model=FeatureFlagResponse)
async def emergency_disable_feature_flag(
    request: Request,
    flag_id: str,
    payload: EmergencyDisableRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Emergency disable a feature flag.
    
    Immediately makes feature unavailable.
    Preserves canonical company reality.
    Creates audit trail.
    Requires feature_flags:emergency permission.
    """
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.emergency_disable(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            reason=payload.reason,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{flag_id}/emergency-enable", response_model=FeatureFlagResponse)
async def emergency_enable_feature_flag(
    request: Request,
    flag_id: str,
    payload: EmergencyEnableRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Re-enable a feature flag after emergency disable.
    
    Requires feature_flags:emergency permission.
    """
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.emergency_enable(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            reason=payload.reason,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================
# ROLLOUT MANAGEMENT ENDPOINTS (Governed)
# ============================================================

@router.post("/{flag_id}/rollout/percentage", response_model=FeatureFlagResponse)
async def set_percentage_rollout(
    request: Request,
    flag_id: str,
    payload: RolloutPercentageRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Set percentage-based rollout. Requires feature_flags:rollout permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.set_percentage_rollout(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            percentage=payload.percentage,
            version=payload.version,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{flag_id}/rollout/segments", response_model=FeatureFlagResponse)
async def set_segment_rollout(
    request: Request,
    flag_id: str,
    payload: RolloutSegmentsRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Set segment-based rollout. Requires feature_flags:rollout permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.set_segment_rollout(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            segments=payload.segments,
            version=payload.version,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{flag_id}/rollout/rings", response_model=FeatureFlagResponse)
async def set_ring_rollout(
    request: Request,
    flag_id: str,
    payload: RolloutRingsRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Set ring-based rollout (canary, early, broad). Requires feature_flags:rollout permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.set_ring_rollout(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            rings=payload.rings,
            version=payload.version,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{flag_id}/rollout/custom", response_model=FeatureFlagResponse)
async def set_custom_rollout(
    request: Request,
    flag_id: str,
    payload: RolloutCustomRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Set custom rollout rules. Requires feature_flags:rollout permission."""
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.set_custom_rollout(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            custom_rules=payload.custom_rules,
            version=payload.version,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================
# PRIVATE ALPHA ROLLOUT
# ============================================================

@router.get("/private-alpha/config", response_model=PrivateAlphaConfigResponse)
async def get_private_alpha_config(
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get private alpha rollout configuration for organization."""
    service = await get_feature_flag_service(session)
    
    await _require_permission(FEATURE_FLAG_PERMISSIONS["read"], org.id, user.id, session)
    
    config = await service.get_private_alpha_config(org.id)
    return PrivateAlphaConfigResponse(**config)


@router.post("/{flag_id}/promote-to-alpha", response_model=FeatureFlagResponse)
async def promote_to_alpha(
    request: Request,
    flag_id: str,
    payload: PromotionRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Promote a feature flag to private alpha rollout.
    
    Requires feature_flags:lifecycle and feature_flags:rollout permissions.
    """
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.promote_to_alpha(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            ring=payload.ring,
            percentage=payload.percentage,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{flag_id}/promote-alpha-to-beta", response_model=FeatureFlagResponse)
async def promote_alpha_to_beta(
    request: Request,
    flag_id: str,
    payload: BetaPromotionRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Promote from alpha to beta with broader rollout.
    
    Requires feature_flags:lifecycle and feature_flags:rollout permissions.
    """
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.promote_alpha_to_beta(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            percentage=payload.percentage,
            governance_context=payload.governance_context,
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.post("/{flag_id}/promote-beta-to-enabled", response_model=FeatureFlagResponse)
async def promote_beta_to_enabled(
    request: Request,
    flag_id: str,
    governance_context: Dict[str, Any] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Promote from beta to fully enabled.
    
    Requires feature_flags:lifecycle permission.
    """
    service = await get_feature_flag_service(session)
    meta = _extract_request_metadata(request)
    
    try:
        flag = await service.promote_beta_to_enabled(
            organization_id=org.id,
            flag_id=flag_id,
            actor_id=user.id,
            governance_context=governance_context or {},
            request_id=meta["request_id"],
            ip_address=meta["ip_address"],
            user_agent=meta["user_agent"],
        )
        return _to_response(flag)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================
# ANALYTICS ENDPOINTS
# ============================================================

@router.get("/{flag_id}/stats", response_model=EvaluationStatsResponse)
async def get_flag_stats(
    request: Request,
    flag_id: str,
    days: int = Query(30, ge=1, le=365),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get evaluation statistics for a flag. Requires feature_flags:analytics permission."""
    service = await get_feature_flag_service(session)
    
    try:
        stats = await service.get_evaluation_stats(
            organization_id=org.id,
            actor_id=user.id,
            flag_id=flag_id,
            days=days,
        )
        return EvaluationStatsResponse(**stats)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/health/overview", response_model=FlagHealthResponse)
async def get_flags_health(
    request: Request,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get overall feature flag health for organization. Requires feature_flags:analytics permission."""
    service = await get_feature_flag_service(session)
    
    try:
        health = await service.get_flag_health(org.id, user.id)
        return FlagHealthResponse(**health)
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================
# AUDIT & HISTORY ENDPOINTS
# ============================================================

@router.get("/{flag_id}/audit", response_model=List[AuditLogResponse])
async def get_flag_audit_log(
    request: Request,
    flag_id: str,
    action: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get audit log for a feature flag. Requires feature_flags:audit permission."""
    service = await get_feature_flag_service(session)
    
    try:
        audit_logs = await service.get_audit_log(
            organization_id=org.id,
            actor_id=user.id,
            flag_id=flag_id,
            action=action,
            limit=limit,
            offset=offset,
        )
        return [_to_audit_response(a) for a in audit_logs]
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{flag_id}/history", response_model=List[HistoryResponse])
async def get_flag_history(
    request: Request,
    flag_id: str,
    limit: int = Query(100, ge=1, le=1000),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get historical configuration for a flag (longitudinal queries).
    
    Requires feature_flags:analytics permission.
    """
    service = await get_feature_flag_service(session)
    
    try:
        history = await service.get_history(
            organization_id=org.id,
            actor_id=user.id,
            flag_id=flag_id,
            limit=limit,
        )
        return [_to_history_response(h) for h in history]
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{flag_id}/configuration-at", response_model=HistoryResponse)
async def get_flag_configuration_at(
    request: Request,
    flag_id: str,
    at: str = Query(..., description="ISO 8601 timestamp"),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get flag configuration at a specific point in time.
    
    Enables longitudinal queries: "What was the configuration three months ago?"
    Requires feature_flags:analytics permission.
    """
    service = await get_feature_flag_service(session)
    
    try:
        at_dt = datetime.fromisoformat(at.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid timestamp format. Use ISO 8601.")
    
    try:
        config = await service.get_configuration_at(
            organization_id=org.id,
            actor_id=user.id,
            flag_id=flag_id,
            at=at_dt,
        )
        if not config:
            raise HTTPException(status_code=404, detail="No configuration found at that time")
        return _to_history_response(config)
    except FeatureFlagNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


@router.get("/{flag_id}/timeline", response_model=TimelineResponse)
async def get_flag_timeline(
    request: Request,
    flag_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get complete timeline of flag changes for longitudinal analysis.
    
    Requires feature_flags:audit permission.
    """
    service = await get_feature_flag_service(session)
    
    try:
        flag = await service.get_flag(org.id, flag_id)
        if not flag:
            raise HTTPException(status_code=404, detail="Feature flag not found")
        
        timeline = await service.get_flag_timeline(
            organization_id=org.id,
            actor_id=user.id,
            flag_id=flag_id,
        )
        return TimelineResponse(flag_id=flag.id, flag_key=flag.key, timeline=timeline)
    except FeatureFlagGovernanceError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except FeatureFlagTenantIsolationError as e:
        raise HTTPException(status_code=403, detail=str(e))


# ============================================================
# ENTITLEMENT INTEGRATION
# ============================================================

@router.get("/{key}/entitlement", response_model=Dict[str, Any])
async def get_feature_entitlement(
    request: Request,
    key: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
):
    """Get entitlement status for a feature.
    
    Distinguishes:
    - Entitlement: commercial right to access capability
    - Feature Flag: operational rollout availability
    - Authorization: actor permission
    
    Requires feature_flags:read permission.
    """
    service = await get_feature_flag_service(session)
    
    await _require_permission(FEATURE_FLAG_PERMISSIONS["read"], org.id, user.id, session)
    
    entitlement = await service.get_feature_entitlement(org.id, key)
    return entitlement


# Need to import datetime
from datetime import datetime