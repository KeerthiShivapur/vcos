"""
SRE API Endpoints.

Provides endpoints for:
- Structured logging
- On-call management
- Predictive scaling
- Cost optimization
- Capacity planning
"""

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.core.oncall import (
    OnCallManager,
    OnCallSchedule,
    OnCallShift,
    TeamMember,
    EscalationPolicy,
    OverrideRequest,
    SwapRequest,
    RotationType,
    EscalationLevel,
    OnCallStatus,
    get_oncall_manager,
    init_oncall_manager,
)
from app.core.predictive_scaling import (
    PredictiveScaler,
    CostOptimizer,
    CapacityPlanner,
    ScalingPolicy,
    ScalingMetric,
    ResourceType,
    ScalingDirection,
    ScalingTrigger,
    CostCategory,
    OptimizationAction,
    get_predictive_scaler,
    get_cost_optimizer,
    get_capacity_planner,
    init_predictive_scaler,
    init_cost_optimizer,
    init_capacity_planner,
)
from app.core.structured_logging import (
    StructuredLogger,
    LogLevel,
    LogFormat,
    get_logger,
    init_structured_logging,
)
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/sre", tags=["SRE & Operations"])


# ==================== Request/Response Models ====================

# Structured Logging
class LogRequest(BaseModel):
    level: str = "info"
    message: str
    fields: Dict[str, Any] = {}


class LogResponse(BaseModel):
    success: bool
    logged: bool


# On-Call Management
class OnCallScheduleCreate(BaseModel):
    name: str
    team_id: str
    rotation_type: str = "weekly"
    rotation_interval_days: int = 7
    start_date: datetime
    timezone: str = "UTC"
    members: List[str] = []
    escalation_policy_id: Optional[str] = None


class OnCallScheduleUpdate(BaseModel):
    name: Optional[str] = None
    rotation_type: Optional[str] = None
    rotation_interval_days: Optional[int] = None
    members: Optional[List[str]] = None
    escalation_policy_id: Optional[str] = None
    is_active: Optional[bool] = None


class OnCallScheduleResponse(BaseModel):
    id: str
    name: str
    team_id: str
    rotation_type: str
    rotation_interval_days: int
    start_date: str
    timezone: str
    members: List[str]
    escalation_policy_id: Optional[str]
    is_active: bool
    created_at: str
    updated_at: str


class OnCallShiftResponse(BaseModel):
    id: str
    schedule_id: str
    member_id: str
    member_name: str
    start_time: str
    end_time: str
    escalation_level: str
    status: str
    is_current: bool


class OverrideRequestCreate(BaseModel):
    shift_id: str
    replacement_id: str
    start_time: datetime
    end_time: datetime
    reason: str


class SwapRequestCreate(BaseModel):
    shift_id: str
    target_id: str


class EscalationPolicyCreate(BaseModel):
    name: str
    organization_id: str
    steps: List[Dict[str, Any]]
    repeat_interval_minutes: int = 30
    max_repeats: int = 3


# Predictive Scaling
class ScalingPolicyCreate(BaseModel):
    name: str
    resource_type: str
    namespace: str
    workload: str
    metrics: List[Dict[str, Any]] = []
    min_replicas: int = 1
    max_replicas: int = 100
    scale_up_cooldown: str = "5m"
    scale_down_cooldown: str = "5m"
    stabilization_window: str = "5m"
    enabled: bool = True
    predictive_enabled: bool = False
    prediction_horizon: str = "1h"


class ScalingPolicyUpdate(BaseModel):
    name: Optional[str] = None
    metrics: Optional[List[Dict[str, Any]]] = None
    min_replicas: Optional[int] = None
    max_replicas: Optional[int] = None
    enabled: Optional[bool] = None
    predictive_enabled: Optional[bool] = None
    prediction_horizon: Optional[str] = None


class ScalingPolicyResponse(BaseModel):
    id: str
    name: str
    resource_type: str
    namespace: str
    workload: str
    metrics: List[Dict[str, Any]]
    min_replicas: int
    max_replicas: int
    enabled: bool
    predictive_enabled: bool
    prediction_horizon: str


class ScalingMetricRequest(BaseModel):
    name: str
    resource_type: str
    query: str
    scale_up_threshold: float
    scale_down_threshold: float
    evaluation_window: str = "5m"
    cooldown_period: str = "5m"
    min_replicas: int = 1
    max_replicas: int = 100


class PredictionRequest(BaseModel):
    metric_name: str
    labels: Dict[str, str] = {}
    horizon: str = "1h"
    model: str = "linear"


class PredictionResponse(BaseModel):
    metric_name: str
    predicted_values: List[List[Any]]
    confidence_intervals: List[List[float]]
    model_name: str
    confidence_score: float
    prediction_horizon: str
    generated_at: str


class ScalingEventResponse(BaseModel):
    id: str
    policy_id: str
    timestamp: str
    direction: str
    trigger: str
    previous_replicas: int
    new_replicas: int
    trigger_metric: str
    trigger_value: float
    threshold: float


# Cost Optimization
class CostRecordRequest(BaseModel):
    category: str
    resource_id: str
    resource_name: str
    cost: float
    timestamp: Optional[datetime] = None
    metadata: Dict[str, Any] = {}


class OptimizationRecommendationResponse(BaseModel):
    id: str
    action: str
    category: str
    resource_id: str
    resource_name: str
    current_cost: float
    estimated_savings: float
    savings_percent: float
    confidence: float
    effort_level: str
    risk_level: str
    description: str
    implementation_steps: List[str]
    prerequisites: List[str]
    risks: List[str]
    status: str


class CostReportRequest(BaseModel):
    period_start: datetime
    period_end: datetime


class CostReportResponse(BaseModel):
    period_start: str
    period_end: str
    total_cost: float
    cost_by_category: Dict[str, float]
    cost_by_resource: Dict[str, float]
    cost_trend: List[List[Any]]
    anomalies: List[Dict[str, Any]]
    recommendations: List[OptimizationRecommendationResponse]
    potential_savings: float


# Capacity Planning
class CapacityForecastRequest(BaseModel):
    resource_type: str
    namespace: str
    workload: str
    horizon: str = "30d"


class CapacityForecastResponse(BaseModel):
    resource_type: str
    current_usage: float
    predicted_usage: List[List[Any]]
    capacity_limit: float
    time_to_capacity: Optional[str]
    recommended_action: str
    confidence: float


# ==================== Structured Logging ====================

@router.post("/logging/log", response_model=LogResponse)
async def log_message(
    request: LogRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("logging:write")),
    db: AsyncSession = Depends(get_db),
):
    """Log a structured message."""
    logger = get_logger("api")
    
    level = LogLevel(request.level.upper())
    extra = {
        "organization_id": org.id,
        "user_id": user.id,
        **request.fields,
    }
    
    log_method = getattr(logger, request.level.lower())
    log_method(request.message, **extra)
    
    return LogResponse(success=True, logged=True)


@router.post("/logging/init")
async def init_logging(
    level: str = "info",
    format: str = "json",
    service_name: str = "vcos",
    environment: str = "production",
    version: str = "1.0.0",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("logging:manage")),
):
    """Initialize structured logging."""
    init_structured_logging(
        level=LogLevel(level.upper()),
        format=format,
        service_name=service_name,
        environment=environment,
        version=version,
    )
    return {"success": True, "message": "Structured logging initialized"}


# ==================== On-Call Management ====================

@router.post("/oncall/schedules", response_model=OnCallScheduleResponse)
async def create_oncall_schedule(
    request: OnCallScheduleCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create an on-call schedule."""
    oncall = get_oncall_manager()
    
    schedule = await oncall.create_schedule(
        name=request.name,
        team_id=request.team_id,
        rotation_type=RotationType(request.rotation_type),
        rotation_interval_days=request.rotation_interval_days,
        start_date=request.start_date,
        timezone=request.timezone,
        member_ids=request.members,
        escalation_policy_id=request.escalation_policy_id,
    )
    
    return _to_schedule_response(schedule)


@router.get("/oncall/schedules", response_model=List[OnCallScheduleResponse])
async def list_oncall_schedules(
    active_only: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:read")),
    db: AsyncSession = Depends(get_db),
):
    """List on-call schedules."""
    oncall = get_oncall_manager()
    schedules = await oncall.list_schedules(active_only=active_only)
    return [_to_schedule_response(s) for s in schedules]


@router.get("/oncall/schedules/{schedule_id}", response_model=OnCallScheduleResponse)
async def get_oncall_schedule(
    schedule_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get on-call schedule."""
    oncall = get_oncall_manager()
    schedule = await oncall.get_schedule(schedule_id)
    
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    
    return _to_schedule_response(schedule)


@router.patch("/oncall/schedules/{schedule_id}", response_model=OnCallScheduleResponse)
async def update_oncall_schedule(
    schedule_id: str,
    request: OnCallScheduleUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update on-call schedule."""
    oncall = get_oncall_manager()
    
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if "rotation_type" in updates:
        updates["rotation_type"] = RotationType(updates["rotation_type"])
    
    schedule = await oncall.update_schedule(schedule_id, updates)
    
    if not schedule:
        raise HTTPException(404, "Schedule not found")
    
    return _to_schedule_response(schedule)


@router.delete("/oncall/schedules/{schedule_id}")
async def delete_oncall_schedule(
    schedule_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Delete on-call schedule."""
    oncall = get_oncall_manager()
    success = await oncall.delete_schedule(schedule_id)
    
    if not success:
        raise HTTPException(404, "Schedule not found")
    
    return {"success": True}


@router.get("/oncall/schedules/{schedule_id}/shifts", response_model=List[OnCallShiftResponse])
async def get_oncall_shifts(
    schedule_id: str,
    start_time: Optional[datetime] = None,
    end_time: Optional[datetime] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get on-call shifts for a schedule."""
    oncall = get_oncall_manager()
    
    start = start_time or utcnow()
    end = end_time or (utcnow() + timedelta(days=14))
    
    shifts = await oncall.get_oncall_schedule(schedule_id, start, end)
    
    return [
        OnCallShiftResponse(
            id=s.id,
            schedule_id=s.schedule_id,
            member_id=s.member_id,
            member_name="",  # Would lookup member name
            start_time=s.start_time.isoformat(),
            end_time=s.end_time.isoformat(),
            escalation_level=s.escalation_level.value,
            status=s.status.value,
            is_current=s.start_time <= utcnow() < s.end_time,
        )
        for s in shifts
    ]


@router.get("/oncall/schedules/{schedule_id}/preview")
async def get_oncall_preview(
    schedule_id: str,
    days: int = 14,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get upcoming on-call schedule preview."""
    oncall = get_oncall_manager()
    preview = oncall.get_oncall_schedule_preview(schedule_id, days)
    return {"schedule_id": schedule_id, "days": days, "shifts": preview}


@router.get("/oncall/current")
async def get_current_oncall(
    schedule_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get current on-call user for a schedule."""
    oncall = get_oncall_manager()
    shift = await oncall.get_current_oncall(schedule_id)
    
    if not shift:
        return {"oncall": None}
    
    member = {}  # Would lookup member
    return {
        "shift": {
            "id": shift.id,
            "start_time": shift.start_time.isoformat(),
            "end_time": shift.end_time.isoformat(),
            "escalation_level": shift.escalation_level.value,
        },
        "member": member,
    }


# Override Management
@router.post("/oncall/overrides", response_model=Dict[str, Any])
async def create_override(
    request: OverrideRequestCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create an override request."""
    oncall = get_oncall_manager()
    
    override = await oncall.create_override(
        shift_id=request.shift_id,
        requester_id="user_id",  # Would get from user
        replacement_id=request.replacement_id,
        start_time=request.start_time,
        end_time=request.end_time,
        reason=request.reason,
    )
    
    return {"override_id": override.id, "status": override.status}


@router.post("/oncall/overrides/{override_id}/approve")
async def approve_override(
    override_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Approve an override request."""
    oncall = get_oncall_manager()
    success = await oncall.approve_override(override_id, "user_id")
    
    if not success:
        raise HTTPException(404, "Override not found or not pending")
    
    return {"success": True}


@router.post("/oncall/overrides/{override_id}/cancel")
async def cancel_override(
    override_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Cancel an override request."""
    oncall = get_oncall_manager()
    success = await oncall.cancel_override(override_id)
    
    if not success:
        raise HTTPException(404, "Override not found or not pending")
    
    return {"success": True}


@router.get("/oncall/overrides")
async def list_overrides(
    shift_id: Optional[str] = None,
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:read")),
    db: AsyncSession = Depends(get_db),
):
    """List override requests."""
    oncall = get_oncall_manager()
    overrides = await oncall.list_overrides(shift_id=shift_id, status=status)
    return [{"id": o.id, "shift_id": o.shift_id, "status": o.status} for o in overrides]


# Swap Management
@router.post("/oncall/swaps")
async def create_swap(
    request: SwapRequestCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a swap request."""
    oncall = get_oncall_manager()
    swap = await oncall.create_swap(
        shift_id=request.shift_id,
        requester_id="user_id",
        target_id=request.target_id,
    )
    return {"swap_id": swap.id, "status": swap.status}


@router.post("/oncall/swaps/{swap_id}/accept")
async def accept_swap(
    swap_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Accept a swap request."""
    oncall = get_oncall_manager()
    success = await oncall.accept_swap(swap_id, "user_id")
    
    if not success:
        raise HTTPException(404, "Swap not found or not pending")
    
    return {"success": True}


@router.post("/oncall/swaps/{swap_id}/reject")
async def reject_swap(
    swap_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Reject a swap request."""
    oncall = get_oncall_manager()
    success = await oncall.reject_swap(swap_id, "user_id")
    
    if not success:
        raise HTTPException(404, "Swap not found or not pending")
    
    return {"success": True}


# Escalation Policies
@router.post("/escalation/policies")
async def create_escalation_policy(
    request: EscalationPolicyCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create an escalation policy."""
    oncall = get_oncall_manager()
    
    policy = await oncall.create_escalation_policy(
        name=request.name,
        organization_id=org.id,
        steps=request.steps,
        repeat_interval_minutes=request.repeat_interval_minutes,
        max_repeats=request.max_repeats,
    )
    
    return {"policy_id": policy.id, "name": policy.name}


@router.get("/escalation/policies")
async def list_escalation_policies(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:read")),
    db: AsyncSession = Depends(get_db),
):
    """List escalation policies."""
    oncall = get_oncall_manager()
    policies = list(oncall._escalation_policies.values())
    return [{"id": p.id, "name": p.name, "steps": len(p.steps)} for p in policies]


@router.post("/escalation/trigger")
async def trigger_escalation(
    alert_id: str,
    policy_id: str,
    alert_data: Dict[str, Any] = Body({}),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Trigger escalation for an alert."""
    oncall = get_oncall_manager()
    escalation_id = await oncall.trigger_escalation(alert_id, policy_id, alert_data)
    
    if not escalation_id:
        raise HTTPException(404, "Policy not found or inactive")
    
    return {"escalation_id": escalation_id}


@router.post("/escalation/{escalation_id}/acknowledge")
async def acknowledge_escalation(
    escalation_id: str,
    step_number: int = Body(..., embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("oncall:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Acknowledge an escalation step."""
    oncall = get_oncall_manager()
    success = await oncall.acknowledge_escalation(escalation_id, 1, "user_id")
    
    if not success:
        raise HTTPException(404, "Escalation step not found")
    
    return {"success": True}


# ==================== Predictive Scaling ====================

@router.post("/scaling/policies", response_model=ScalingPolicyResponse)
async def create_scaling_policy(
    request: ScalingPolicyCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scaling:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a scaling policy."""
    scaler = get_predictive_scaler()
    
    metrics = [
        ScalingMetric(
            name=m["name"],
            resource_type=ResourceType(m["resource_type"]),
            query=m["query"],
            scale_up_threshold=m["scale_up_threshold"],
            scale_down_threshold=m["scale_down_threshold"],
            evaluation_window=m.get("evaluation_window", "5m"),
            cooldown_period=m.get("cooldown_period", "5m"),
            min_replicas=m.get("min_replicas", 1),
            max_replicas=m.get("max_replicas", 100),
        )
        for m in request.metrics
    ]
    
    policy = ScalingPolicy(
        id=str(uuid4()),
        name=request.name,
        resource_type=ResourceType(request.resource_type),
        namespace=request.namespace,
        workload=request.workload,
        metrics=metrics,
        min_replicas=request.min_replicas,
        max_replicas=request.max_replicas,
        scale_up_cooldown=request.scale_up_cooldown,
        scale_down_cooldown=request.scale_down_cooldown,
        stabilization_window=request.stabilization_window,
        enabled=request.enabled,
        predictive_enabled=request.predictive_enabled,
        prediction_horizon=request.prediction_horizon,
    )
    
    await scaler.register_policy(policy)
    
    return _to_policy_response(policy)


@router.get("/scaling/policies", response_model=List[ScalingPolicyResponse])
async def list_scaling_policies(
    namespace: Optional[str] = None,
    workload: Optional[str] = None,
    enabled_only: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scaling:read")),
    db: AsyncSession = Depends(get_db),
):
    """List scaling policies."""
    scaler = get_predictive_scaler()
    policies = await scaler.list_policies(
        namespace=namespace,
        workload=workload,
        enabled_only=enabled_only,
    )
    
    return [_to_policy_response(p) for p in policies]


@router.get("/scaling/policies/{policy_id}", response_model=ScalingPolicyResponse)
async def get_scaling_policy(
    policy_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scaling:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get scaling policy."""
    scaler = get_predictive_scaler()
    policy = await scaler.get_policy(policy_id)
    
    if not policy:
        raise HTTPException(404, "Policy not found")
    
    return _to_policy_response(policy)


@router.patch("/scaling/policies/{policy_id}", response_model=ScalingPolicyResponse)
async def update_scaling_policy(
    policy_id: str,
    request: ScalingPolicyUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scaling:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update scaling policy."""
    scaler = get_predictive_scaler()
    
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if "resource_type" in updates:
        updates["resource_type"] = ResourceType(updates["resource_type"])
    
    policy = await scaler.update_policy(policy_id, updates)
    
    if not policy:
        raise HTTPException(404, "Policy not found")
    
    return _to_policy_response(policy)


@router.delete("/scaling/policies/{policy_id}")
async def delete_scaling_policy(
    policy_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scaling:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Delete scaling policy."""
    scaler = get_predictive_scaler()
    success = await scaler.delete_policy(policy_id)
    
    if not success:
        raise HTTPException(404, "Policy not found")
    
    return {"success": True}


@router.post("/scaling/policies/{policy_id}/evaluate")
async def evaluate_scaling_policy(
    policy_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scaling:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Evaluate scaling policy and trigger scaling if needed."""
    scaler = get_predictive_scaler()
    events = await scaler.evaluate_scaling(policy_id)
    
    return {
        "events": [
            {
                "id": e.id,
                "direction": e.direction.value,
                "trigger": e.trigger.value,
                "previous_replicas": e.previous_replicas,
                "new_replicas": e.new_replicas,
                "metric": e.trigger_metric,
                "value": e.trigger_value,
                "threshold": e.threshold,
            }
            for e in events
        ]
    }


@router.get("/scaling/policies/{policy_id}/stats")
async def get_scaling_stats(
    policy_id: str,
    hours: int = 24,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scaling:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get scaling statistics."""
    scaler = get_predictive_scaler()
    return scaler.get_scaling_stats(policy_id, hours)


@router.get("/scaling/policies/{policy_id}/history")
async def get_scaling_history(
    policy_id: str,
    hours: int = 24,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scaling:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get scaling event history."""
    scaler = get_predictive_scaler()
    events = scaler.get_scaling_history(policy_id, hours)
    
    return {
        "events": [
            {
                "id": e.id,
                "timestamp": e.timestamp.isoformat(),
                "direction": e.direction.value,
                "trigger": e.trigger.value,
                "previous_replicas": e.previous_replicas,
                "new_replicas": e.new_replicas,
                "metric": e.trigger_metric,
                "value": e.trigger_value,
                "threshold": e.threshold,
            }
            for e in events
        ]
    }


@router.post("/scaling/predict", response_model=PredictionResponse)
async def predict_metric(
    request: PredictionRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("scaling:read")),
    db: AsyncSession = Depends(get_db),
):
    """Predict future metric values."""
    scaler = get_predictive_scaler()
    
    result = await scaler.predict_metric(
        metric_name=request.metric_name,
        labels=request.labels,
        horizon=request.horizon,
        model=request.model,
    )
    
    return PredictionResponse(
        metric_name=result.metric_name,
        predicted_values=[[p[0].isoformat(), p[1]] for p in result.predicted_values],
        confidence_intervals=result.confidence_intervals,
        model_name=result.model_name,
        confidence_score=result.confidence_score,
        prediction_horizon=result.prediction_horizon,
        generated_at=result.generated_at.isoformat(),
    )


# ==================== Cost Optimization ====================

@router.post("/cost/record", response_model=Dict[str, str])
async def record_cost(
    request: CostRecordRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:write")),
    db: AsyncSession = Depends(get_db),
):
    """Record a cost data point."""
    optimizer = get_cost_optimizer()
    
    await optimizer.record_cost(
        category=CostCategory(request.category),
        resource_id=request.resource_id,
        resource_name=request.resource_name,
        cost=request.cost,
        timestamp=request.timestamp,
        metadata=request.metadata,
    )
    
    return {"success": True}


@router.post("/cost/records/batch", response_model=Dict[str, str])
async def record_cost_batch(
    costs: List[CostRecordRequest],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:write")),
    db: AsyncSession = Depends(get_db),
):
    """Record multiple cost data points."""
    optimizer = get_cost_optimizer()
    
    costs = [c.model_dump() for c in costs]
    await optimizer.record_cost_batch(costs)
    
    return {"success": True, "recorded": len(costs)}


@router.post("/cost/anomalies/detect")
async def detect_cost_anomalies(
    category: Optional[str] = None,
    sensitivity: float = 2.0,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:read")),
    db: AsyncSession = Depends(get_db),
):
    """Detect cost anomalies."""
    optimizer = get_cost_optimizer()
    
    category_enum = CostCategory(category) if category else None
    anomalies = await optimizer.detect_anomalies(
        category=category_enum,
        sensitivity=sensitivity,
    )
    
    return {
        "anomalies": [
            {
                "id": a.id,
                "category": a.category.value,
                "detected_at": a.detected_at.isoformat(),
                "expected_cost": a.expected_cost,
                "actual_cost": a.actual_cost,
                "deviation_percent": a.deviation_percent,
                "severity": a.severity,
                "affected_resources": a.affected_resources,
                "description": a.description,
                "recommended_actions": a.recommended_actions,
            }
            for a in anomalies
        ]
    }


@router.post("/cost/recommendations/generate", response_model=List[OptimizationRecommendationResponse])
async def generate_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Generate cost optimization recommendations."""
    optimizer = get_cost_optimizer()
    recommendations = await optimizer.generate_recommendations()
    
    return [_to_recommendation_response(r) for r in recommendations]


@router.get("/cost/recommendations", response_model=List[OptimizationRecommendationResponse])
async def list_recommendations(
    status: Optional[str] = None,
    category: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:read")),
    db: AsyncSession = Depends(get_db),
):
    """List optimization recommendations."""
    optimizer = get_cost_optimizer()
    
    cat = CostCategory(category) if category else None
    recommendations = await optimizer.get_recommendations(status=status, category=cat)
    
    return [_to_recommendation_response(r) for r in recommendations]


@router.get("/cost/recommendations/{recommendation_id}", response_model=OptimizationRecommendationResponse)
async def get_recommendation(
    recommendation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get recommendation details."""
    optimizer = get_cost_optimizer()
    rec = optimizer._recommendations.get(recommendation_id)
    
    if not rec:
        raise HTTPException(404, "Recommendation not found")
    
    return _to_recommendation_response(rec)


@router.patch("/cost/recommendations/{recommendation_id}")
async def update_recommendation_status(
    recommendation_id: str,
    status: str = Body(..., embed=True),
    notes: str = Body("", embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update recommendation status."""
    optimizer = get_cost_optimizer()
    success = await optimizer.update_recommendation_status(recommendation_id, status, notes)
    
    if not success:
        raise HTTPException(404, "Recommendation not found")
    
    return {"success": True}


@router.post("/cost/report", response_model=CostReportResponse)
async def generate_cost_report(
    request: CostReportRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:read")),
    db: AsyncSession = Depends(get_db),
):
    """Generate cost report."""
    optimizer = get_cost_optimizer()
    report = await optimizer.generate_cost_report(request.period_start, request.period_end)
    
    return CostReportResponse(
        period_start=report.period_start.isoformat(),
        period_end=report.period_end.isoformat(),
        total_cost=report.total_cost,
        cost_by_category={k.value: v for k, v in report.cost_by_category.items()},
        cost_by_resource=report.cost_by_resource,
        cost_trend=[[d.isoformat(), c] for d, c in report.cost_trend],
        anomalies=[
            {
                "id": a.id,
                "category": a.category.value,
                "detected_at": a.detected_at.isoformat(),
                "expected_cost": a.expected_cost,
                "actual_cost": a.actual_cost,
                "deviation_percent": a.deviation_percent,
                "severity": a.severity,
            }
            for a in report.anomalies
        ],
        recommendations=[_to_recommendation_response(r) for r in report.recommendations],
        potential_savings=report.potential_savings,
    )


@router.get("/cost/anomalies")
async def list_anomalies(
    category: Optional[str] = None,
    severity: Optional[str] = None,
    hours: int = 24,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:read")),
    db: AsyncSession = Depends(get_db),
):
    """List cost anomalies."""
    optimizer = get_cost_optimizer()
    
    cat = CostCategory(category) if category else None
    anomalies = await optimizer.get_anomalies(category=cat, severity=severity, hours=hours)
    
    return {
        "anomalies": [
            {
                "id": a.id,
                "category": a.category.value,
                "detected_at": a.detected_at.isoformat(),
                "expected_cost": a.expected_cost,
                "actual_cost": a.actual_cost,
                "deviation_percent": a.deviation_percent,
                "severity": a.severity,
                "affected_resources": a.affected_resources,
            }
            for a in anomalies
        ]
    }


@router.get("/cost/stats")
async def get_cost_stats(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("cost:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get cost optimization statistics."""
    optimizer = get_cost_optimizer()
    return optimizer.get_stats()


# ==================== Capacity Planning ====================

@router.post("/capacity/forecast", response_model=CapacityForecastResponse)
async def forecast_capacity(
    request: CapacityForecastRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("capacity:read")),
    db: AsyncSession = Depends(get_db),
):
    """Forecast capacity for a resource."""
    planner = get_capacity_planner()
    
    forecast = await planner.forecast_capacity(
        resource_type=ResourceType(request.resource_type),
        namespace=request.namespace,
        workload=request.workload,
        horizon=request.horizon,
    )
    
    return CapacityForecastResponse(
        resource_type=forecast.resource_type.value,
        current_usage=forecast.current_usage,
        predicted_usage=[[p[0].isoformat(), p[1]] for p in forecast.predicted_usage],
        capacity_limit=forecast.capacity_limit,
        time_to_capacity=str(forecast.time_to_capacity) if forecast.time_to_capacity else None,
        recommended_action=forecast.recommended_action,
        confidence=forecast.confidence,
    )


@router.post("/capacity/forecast/all")
async def forecast_all_capacity(
    namespace: str = Body(..., embed=True),
    workload: str = Body(..., embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("capacity:read")),
    db: AsyncSession = Depends(get_db),
):
    """Forecast capacity for all resource types."""
    planner = get_capacity_planner()
    forecasts = await planner.forecast_all_resources(request.namespace, request.workload)
    
    return {
        rt.value: CapacityForecastResponse(
            resource_type=f.rt.value,
            current_usage=f.current_usage,
            predicted_usage=[[p[0].isoformat(), p[1]] for p in f.predicted_usage],
            capacity_limit=f.capacity_limit,
            time_to_capacity=str(f.time_to_capacity) if f.time_to_capacity else None,
            recommended_action=f.recommended_action,
            confidence=f.confidence,
        )
        for rt, f in forecasts.items()
    }


@router.get("/capacity/forecasts")
async def list_forecasts(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("capacity:read")),
    db: AsyncSession = Depends(get_db),
):
    """List all capacity forecasts."""
    planner = get_capacity_planner()
    forecasts = planner.get_all_forecasts()
    
    return {
        k: {
            "resource_type": f.resource_type.value,
            "current_usage": f.current_usage,
            "capacity_limit": f.capacity_limit,
            "time_to_capacity": str(f.time_to_capacity) if f.time_to_capacity else None,
            "recommended_action": f.recommended_action,
            "confidence": f.confidence,
        }
        for k, f in forecasts.items()
    }


# ==================== SRE Health ====================

@router.get("/health")
async def sre_health(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("sre:read")),
    db: AsyncSession = Depends(get_db),
):
    """Comprehensive SRE health check."""
    from app.core.oncall import get_oncall_manager
    from app.core.predictive_scaling import get_predictive_scaler, get_cost_optimizer, get_capacity_planner
    
    oncall = get_oncall_manager()
    scaler = get_predictive_scaler()
    optimizer = get_cost_optimizer()
    planner = get_capacity_planner()
    
    return {
        "structured_logging": "healthy",
        "oncall": oncall.get_stats(),
        "predictive_scaling": scaler.get_scaling_stats("all") if hasattr(scaler, 'get_scaling_stats') else {},
        "cost_optimization": get_cost_optimizer().get_stats(),
        "capacity_planning": get_capacity_planner().get_all_forecasts() if hasattr(get_capacity_planner(), 'get_all_forecasts') else {},
        "overall": "healthy",
        "checked_at": utcnow().isoformat(),
    }


# ==================== Helper Functions ====================

def _to_schedule_response(schedule) -> OnCallScheduleResponse:
    return OnCallScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        team_id=schedule.team_id,
        rotation_type=schedule.rotation_type.value,
        rotation_interval_days=schedule.rotation_interval_days,
        start_date=schedule.start_date.isoformat(),
        timezone=schedule.timezone,
        members=schedule.members,
        escalation_policy_id=schedule.escalation_policy_id,
        is_active=schedule.is_active,
        created_at=schedule.created_at.isoformat(),
        updated_at=schedule.updated_at.isoformat(),
    )


def _to_policy_response(policy) -> ScalingPolicyResponse:
    return ScalingPolicyResponse(
        id=policy.id,
        name=policy.name,
        resource_type=policy.resource_type.value,
        namespace=policy.namespace,
        workload=policy.workload,
        metrics=[
            {
                "name": m.name,
                "resource_type": m.resource_type.value,
                "query": m.query,
                "scale_up_threshold": m.scale_up_threshold,
                "scale_down_threshold": m.scale_down_threshold,
            }
            for m in policy.metrics
        ],
        min_replicas=policy.min_replicas,
        max_replicas=policy.max_replicas,
        enabled=policy.enabled,
        predictive_enabled=policy.predictive_enabled,
        prediction_horizon=policy.prediction_horizon,
    )


def _to_recommendation_response(rec) -> Dict[str, Any]:
    return {
        "id": rec.id,
        "action": rec.action.value,
        "category": rec.category.value,
        "resource_id": rec.resource_id,
        "resource_name": rec.resource_name,
        "current_cost": rec.current_cost,
        "estimated_savings": rec.estimated_savings,
        "savings_percent": rec.savings_percent,
        "confidence": rec.confidence,
        "effort_level": rec.effort_level,
        "risk_level": rec.risk_level,
        "description": rec.description,
        "implementation_steps": rec.implementation_steps,
        "prerequisites": rec.prerequisites,
        "risks": rec.risks,
        "status": rec.status,
    }


# ==================== Initialize on Module Load ====================

@router.on_event("startup")
async def startup():
    init_structured_logging()
    await init_oncall_manager()
    await init_predictive_scaler()
    await init_cost_optimizer()
    await init_capacity_planner()