"""
Multi-Region & Global Scale API Endpoints.

Provides endpoints for:
- Region management and health
- GeoDNS traffic management
- Anycast IP management
- Edge locations and caching
- Traffic splitting and canary deployments
- Cross-region replication
- Failover orchestration
- Disaster recovery
- Chaos engineering / Game days
- Global load balancing
"""

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.infrastructure.geodns_service import (
    get_geodns_service,
    Endpoint,
    GeoRoute,
    AnycastIP,
    EdgeLocation,
    EdgeCacheRule,
    TrafficPolicy,
    TrafficShift,
    RoutingPolicy,
    RecordType,
    HealthStatus,
)
from app.infrastructure.edge_cdn_service import (
    get_edge_cdn_service,
    CacheRule,
    CachePurgeRequest,
    CacheWarmRequest,
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
    OptimizationRecommendation,
    get_predictive_scaler,
    get_cost_optimizer,
    get_capacity_planner,
    init_predictive_scaler,
    init_cost_optimizer,
    init_capacity_planner,
)
from app.infrastructure.global_traffic_manager import (
    get_global_traffic_manager,
    RegionDeployment,
    RegionRole,
    DeploymentModel,
    ReplicationMode,
    RegionStatus,
    TrafficSplit,
    ReplicationConfig,
    FailoverEvent,
    ChaosExperiment,
    RegionHealth,
)
from app.core.oncall import (
    EscalationLevel,
    OnCallStatus,
)
from app.models.organization import Organization
from app.models.user import User
from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import json
import uuid

router = APIRouter(prefix="/multiregion", tags=["Multi-Region & Global Scale"])


# ==================== Request/Response Models ====================

# Region Management
class RegionDeploymentCreate(BaseModel):
    region_id: str
    name: str
    role: str = "secondary"
    deployment_model: str = "active_active"
    rotation_interval_days: int = 7
    timezone: str = "UTC"
    members: List[str] = []
    escalation_policy_id: Optional[str] = None
    data_center: str = ""
    availability_zone: str = ""


class RegionDeploymentUpdate(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    deployment_model: Optional[str] = None
    rotation_interval_days: Optional[int] = None
    members: Optional[List[str]] = None
    escalation_policy_id: Optional[str] = None
    is_active: Optional[bool] = None


class RegionDeploymentResponse(BaseModel):
    region_id: str
    name: str
    role: str
    deployment_model: str
    active: bool
    priority: int
    created_at: str
    updated_at: str
    health: Dict[str, Any]


# GeoDNS / Traffic Management
class EndpointCreate(BaseModel):
    region: str
    ip: str
    port: int = 443
    protocol: str = "https"
    weight: int = 100
    priority: int = 100
    health_check: str = "/health"
    health_check_type: str = "http"
    health_check_interval: int = 30
    healthy_threshold: int = 2
    unhealthy_threshold: int = 3


class EndpointResponse(BaseModel):
    id: str
    region: str
    ip: str
    port: int
    protocol: str
    weight: int
    priority: int
    healthy: bool
    healthy_threshold: int
    unhealthy_threshold: int


class GeoRouteCreate(BaseModel):
    name: str
    priority: int = 100
    conditions: Dict[str, Any] = {}
    target_region: str
    weight: int = 100


class GeoRouteResponse(BaseModel):
    id: str
    name: str
    priority: int
    conditions: Dict[str, Any]
    target_region: str
    weight: int
    enabled: bool


class AnycastIPCreate(BaseModel):
    ip: str
    ipv6: Optional[str] = None
    scope: str = "global"
    regions: List[str] = []
    communities: List[str] = []
    asn: Optional[int] = None
    prefix_length: int = 32
    health_check: Optional[str] = None


class AnycastIPResponse(BaseModel):
    id: str
    ip: str
    ipv6: Optional[str]
    scope: str
    regions: List[str]
    communities: List[str]
    asn: Optional[int]
    prefix_length: int
    announce: bool
    health_check: Optional[str]


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


class EdgeLocationCreate(BaseModel):
    code: str
    name: str
    city: str
    country: str
    continent: str
    latitude: float
    longitude: float
    provider: str = "custom"
    capacity: int = 10000
    cache_storage_gb: int = 1000
    services: List[str] = []


class EdgeLocationResponse(BaseModel):
    id: str
    code: str
    name: str
    city: str
    country: str
    continent: str
    provider: str
    capacity: int
    current_load: int
    services: List[str]
    status: str


class EdgeCacheRuleCreate(BaseModel):
    pattern: str
    ttl_seconds: int = 3600
    stale_while_revalidate: int = 86400
    stale_if_error: int = 86400
    vary_headers: List[str] = []
    vary_by_cookie: Optional[str] = None
    vary_by_header: Optional[str] = None
    vary_by_region: bool = False
    bypass_cookies: List[str] = []
    bypass_query_params: List[str] = []
    cache_methods: List[str] = ["GET", "HEAD"]
    cache_status_codes: List[int] = [200, 301, 302, 304]
    compress: bool = True
    priority: int = 100
    tags: List[str] = []


class TrafficPolicyCreate(BaseModel):
    name: str
    domain: str
    policy_type: str = "latency_based"
    default_region: Optional[str] = None
    regions: List[Dict[str, Any]] = []
    geo_routes: List[str] = []
    health_check_enabled: bool = True
    health_check_interval: int = 30
    failover_enabled: bool = True
    failover_threshold: int = 3
    traffic_shift_enabled: bool = False
    canary_percentage: float = 0.0
    shadow_enabled: bool = False
    shadow_target: Optional[str] = None


class TrafficPolicyResponse(BaseModel):
    id: str
    name: str
    domain: str
    policy_type: str
    default_region: Optional[str]
    regions: List[Dict[str, Any]]
    geo_routes: List[str]
    health_check_enabled: bool
    health_check_interval: int
    failover_enabled: bool
    failover_threshold: int
    traffic_shift_enabled: bool
    canary_percentage: float
    shadow_enabled: bool
    shadow_target: Optional[str]
    created_at: str
    updated_at: str


class TrafficShiftCreate(BaseModel):
    policy_id: str
    from_region: str
    to_region: str
    percentage: float
    duration_minutes: int = 60


class TrafficShiftResponse(BaseModel):
    id: str
    policy_id: str
    from_region: str
    to_region: str
    percentage: float
    start_time: str
    end_time: Optional[str]
    ramp_up_minutes: int
    status: str
    progress: float


class TrafficSplitCreate(BaseModel):
    name: str
    source_region: str
    targets: List[Dict[str, Any]] = []
    strategy: str = "weighted"
    sticky_sessions: bool = False
    cookie_name: str = "vcos_region"


class TrafficSplitResponse(BaseModel):
    id: str
    name: str
    source_region: str
    targets: List[Dict[str, Any]]
    strategy: str
    sticky_sessions: bool
    cookie_name: str
    enabled: bool
    created_at: str


# Replication
class ReplicationConfigCreate(BaseModel):
    source_region: str
    target_region: str
    databases: List[str] = []
    storage_buckets: List[str] = []
    kafka_topics: List[str] = []
    replication_mode: str = "asynchronous"
    lag_threshold_ms: int = 5000
    alert_on_lag_ms: int = 10000
    sync_interval_seconds: int = 60


class ReplicationConfigResponse(BaseModel):
    source_region: str
    target_region: str
    databases: List[str]
    storage_buckets: List[str]
    kafka_topics: List[str]
    replication_mode: str
    lag_threshold_ms: int
    alert_on_lag_ms: int
    sync_interval_seconds: int


# Failover
class FailoverExecuteRequest(BaseModel):
    from_region: str
    to_region: str
    trigger_type: str = "automatic"
    reason: str = ""
    force: bool = False


class FailoverEventResponse(BaseModel):
    id: str
    trigger: str
    from_region: str
    to_region: str
    trigger_type: str
    reason: str
    started_at: str
    completed_at: Optional[str]
    status: str
    steps: List[Dict[str, Any]]
    rollback_reason: Optional[str]


# Chaos Engineering
class ChaosExperimentCreate(BaseModel):
    name: str
    description: str
    scenario: str
    target_regions: List[str]
    target_services: List[str]
    blast_radius: str = "multi_region"
    duration_minutes: int = 60
    hypothesis: str
    success_criteria: List[str] = []
    rollback_conditions: List[str] = []


class ChaosExperimentResponse(BaseModel):
    id: str
    name: str
    description: str
    scenario: str
    target_regions: List[str]
    target_services: List[str]
    blast_radius: str
    duration_minutes: int
    hypothesis: str
    success_criteria: List[str]
    rollback_conditions: List[str]
    status: str
    created_by: str
    created_at: str
    started_at: Optional[str]
    completed_at: Optional[str]
    results: Dict[str, Any]


class GameDayRequest(BaseModel):
    name: str
    scenarios: List[str]
    target_regions: List[str]
    duration_hours: int = 2


class GameDayResponse(BaseModel):
    game_day_id: str
    name: str
    scenarios: List[str]
    target_regions: List[str]
    duration_hours: int
    started_at: str
    scenario_results: Dict[str, Any]
    overall_status: str


# ==================== Region Management ====================

@router.post("/regions", response_model=RegionDeploymentResponse)
async def create_region(
    request: RegionDeploymentCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a region deployment."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, RegionDeployment, RegionRole, DeploymentModel
    
    manager = get_global_traffic_manager()
    
    deployment = RegionDeployment(
        region_id=request.region_id,
        name=request.name,
        role=RegionRole(request.role),
        deployment_model=DeploymentModel(request.deployment_model),
        members=request.members,
        data_center=request.data_center,
        availability_zone=request.availability_zone,
    )
    
    await manager.register_region(deployment)
    
    return RegionDeploymentResponse(
        region_id=deployment.region_id,
        name=deployment.name,
        role=deployment.role.value,
        deployment_model=deployment.deployment_model.value,
        active=deployment.active,
        priority=deployment.priority,
        created_at=deployment.created_at.isoformat(),
        updated_at=deployment.updated_at.isoformat(),
        health=manager.get_region_status().get(deployment.region_id, {}),
    )


@router.get("/regions", response_model=List[RegionDeploymentResponse])
async def list_regions(
    role: Optional[str] = None,
    active_only: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:read")),
    db: AsyncSession = Depends(get_db),
):
    """List region deployments."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, RegionRole
    
    manager = get_global_traffic_manager()
    
    role_enum = RegionRole(role) if role else None
    regions = manager.list_regions(role=role_enum, active_only=active_only)
    
    return [
        RegionDeploymentResponse(
            region_id=r.region_id,
            name=r.name,
            role=r.role.value,
            deployment_model=r.deployment_model.value,
            active=r.active,
            priority=r.priority,
            created_at=r.created_at.isoformat(),
            updated_at=r.updated_at.isoformat(),
            health=manager.get_region_status().get(r.region_id, {}),
        )
        for r in regions
    ]


@router.get("/regions/{region_id}", response_model=RegionDeploymentResponse)
async def get_region(
    region_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get region deployment."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    region = await manager.get_region(region_id)
    
    if not region:
        raise HTTPException(404, "Region not found")
    
    return RegionDeploymentResponse(
        region_id=region.region_id,
        name=region.name,
        role=region.role.value,
        deployment_model=region.deployment_model.value,
        active=region.active,
        priority=region.priority,
        created_at=region.created_at.isoformat(),
        updated_at=region.updated_at.isoformat(),
        health=manager.get_region_status().get(region.region_id, {}),
    )


@router.patch("/regions/{region_id}", response_model=RegionDeploymentResponse)
async def update_region(
    region_id: str,
    request: RegionDeploymentUpdate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Update region deployment."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, RegionRole, DeploymentModel
    
    manager = get_global_traffic_manager()
    
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    if "role" in updates:
        updates["role"] = RegionRole(updates["role"])
    if "deployment_model" in updates:
        updates["deployment_model"] = DeploymentModel(updates["deployment_model"])
    
    region = await manager.update_region(region_id, updates)
    
    if not region:
        raise HTTPException(404, "Region not found")
    
    return RegionDeploymentResponse(
        region_id=region.region_id,
        name=region.name,
        role=region.role.value,
        deployment_model=region.deployment_model.value,
        active=region.active,
        priority=region.priority,
        created_at=region.created_at.isoformat(),
        updated_at=region.updated_at.isoformat(),
        health=manager.get_region_status().get(region.region_id, {}),
    )


@router.post("/regions/{region_id}/promote")
async def promote_region(
    region_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Promote a region to primary."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    success = await manager.promote_region(region_id)
    
    if not success:
        raise HTTPException(404, "Region not found")
    
    return {"success": True, "message": f"Region {region_id} promoted to primary"}


@router.post("/regions/{region_id}/demote")
async def demote_region(
    region_id: str,
    new_role: str = "secondary",
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Demote a region."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, RegionRole
    
    manager = get_global_traffic_manager()
    success = await manager.demote_region(region_id, new_role=RegionRole(new_role))
    
    if not success:
        raise HTTPException(404, "Region not found")
    
    return {"success": True, "message": f"Region demoted to {new_role}"}


@router.get("/regions/health", response_model=Dict[str, Any])
async def get_regions_health(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get health status of all regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    return manager.get_region_status()


# ==================== GeoDNS / Traffic Management ====================

@router.post("/geodns/endpoints", response_model=EndpointResponse)
async def create_endpoint(
    request: EndpointCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Register a service endpoint."""
    from app.infrastructure.geodns_service import get_geodns_service, Endpoint, HealthCheckType
    
    geodns = get_geodns_service()
    
    endpoint = Endpoint(
        id=str(uuid4()),
        region=request.region,
        ip=request.ip,
        port=request.port,
        protocol=request.protocol,
        weight=request.weight,
        priority=request.priority,
        health_check=request.health_check,
        health_check_type=HealthCheckType(request.health_check_type),
        health_check_interval=request.health_check_interval,
        healthy_threshold=request.healthy_threshold,
        unhealthy_threshold=request.unhealthy_threshold,
    )
    
    await geodns.register_endpoint(endpoint)
    
    return EndpointResponse(
        id=endpoint.id,
        region=endpoint.region,
        ip=endpoint.ip,
        port=endpoint.port,
        protocol=endpoint.protocol,
        weight=endpoint.weight,
        priority=endpoint.priority,
        healthy=endpoint.healthy,
        healthy_threshold=endpoint.healthy_threshold,
        unhealthy_threshold=endpoint.unhealthy_threshold,
    )


@router.get("/geodns/endpoints", response_model=List[EndpointResponse])
async def list_endpoints(
    region: Optional[str] = None,
    healthy_only: bool = False,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:read")),
):
    """List endpoints."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    endpoints = await geodns.list_endpoints(region=region, healthy_only=healthy_only)
    
    return [
        EndpointResponse(
            id=e.id,
            region=e.region,
            ip=e.ip,
            port=e.port,
            protocol=e.protocol,
            weight=e.weight,
            priority=e.priority,
            healthy=e.healthy,
            healthy_threshold=e.healthy_threshold,
            unhealthy_threshold=e.unhealthy_threshold,
        )
        for e in endpoints
    ]


@router.get("/geodns/endpoints/{endpoint_id}", response_model=EndpointResponse)
async def get_endpoint(
    endpoint_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:read")),
):
    """Get endpoint details."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    endpoint = await geodns.get_endpoint(endpoint_id)
    
    if not endpoint:
        raise HTTPException(404, "Endpoint not found")
    
    return EndpointResponse(
        id=endpoint.id,
        region=endpoint.region,
        ip=endpoint.ip,
        port=endpoint.port,
        protocol=endpoint.protocol,
        weight=endpoint.weight,
        priority=endpoint.priority,
        healthy=endpoint.healthy,
        healthy_threshold=endpoint.healthy_threshold,
        unhealthy_threshold=endpoint.unhealthy_threshold,
    )


@router.patch("/geodns/endpoints/{endpoint_id}", response_model=EndpointResponse)
async def update_endpoint(
    endpoint_id: str,
    updates: Dict[str, Any] = Body(...),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Update an endpoint."""
    from app.infrastructure.geodns_service import get_geodns_service, Endpoint
    
    geodns = get_geodns_service()
    endpoint = await geodns.update_endpoint(endpoint_id, updates)
    
    if not endpoint:
        raise HTTPException(404, "Endpoint not found")
    
    return EndpointResponse(
        id=endpoint.id,
        region=endpoint.region,
        ip=endpoint.ip,
        port=endpoint.port,
        protocol=endpoint.protocol,
        weight=endpoint.weight,
        priority=endpoint.priority,
        healthy=endpoint.healthy,
        healthy_threshold=endpoint.healthy_threshold,
        unhealthy_threshold=endpoint.unhealthy_threshold,
    )


@router.delete("/geodns/endpoints/{endpoint_id}")
async def delete_endpoint(
    endpoint_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Delete an endpoint."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    success = await geodns.remove_endpoint(endpoint_id)
    
    if not success:
        raise HTTPException(404, "Endpoint not found")
    
    return {"success": True}


# Geo Routes
@router.post("/geodns/routes", response_model=GeoRouteResponse)
async def create_geo_route(
    request: GeoRouteCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Create a geo-routing rule."""
    from app.infrastructure.geodns_service import get_geodns_service, GeoRoute
    
    geodns = get_geodns_service()
    route = GeoRoute(
        id=str(uuid4()),
        name=request.name,
        priority=request.priority,
        conditions=request.conditions,
        target_region=request.target_region,
        weight=request.weight,
    )
    
    await geodns.create_geo_route(route)
    
    return GeoRouteResponse(
        id=route.id,
        name=route.name,
        priority=route.priority,
        conditions=route.conditions,
        target_region=route.target_region,
        weight=route.weight,
        enabled=route.enabled,
    )


@router.get("/geodns/routes", response_model=List[GeoRouteResponse])
async def list_geo_routes(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:read")),
):
    """List geo-routing rules."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    routes = list(geodns._geo_routes.values())
    
    return [
        GeoRouteResponse(
            id=r.id,
            name=r.name,
            priority=r.priority,
            conditions=r.conditions,
            target_region=r.target_region,
            weight=r.weight,
            enabled=r.enabled,
        )
        for r in routes
    ]


@router.delete("/geodns/routes/{route_id}")
async def delete_geo_route(
    route_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Delete a geo-routing rule."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    success = await geodns.delete_geo_route(route_id)
    
    if not success:
        raise HTTPException(404, "Geo route not found")
    
    return {"success": True}


# Anycast IPs
@router.post("/geodns/anycast", response_model=AnycastIPResponse)
async def register_anycast_ip(
    request: AnycastIPCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Register an Anycast IP."""
    from app.infrastructure.geodns_service import get_geodns_service, AnycastIP, AnycastScope
    
    geodns = get_geodns_service()
    
    anycast = AnycastIP(
        id=str(uuid4()),
        ip=request.ip,
        ipv6=request.ipv6,
        scope=AnycastScope(request.scope),
        regions=request.regions,
        communities=request.communities,
        asn=request.asn,
        prefix_length=request.prefix_length,
        health_check=request.health_check,
    )
    
    await geodns.register_anycast_ip(anycast)
    
    return AnycastIPResponse(
        id=anycast.id,
        ip=anycast.ip,
        ipv6=anycast.ipv6,
        scope=anycast.scope.value,
        regions=anycast.regions,
        communities=anycast.communities,
        asn=anycast.asn,
        prefix_length=anycast.prefix_length,
        announce=anycast.announce,
        health_check=anycast.health_check,
    )


@router.post("/geodns/anycast/{anycast_id}/announce")
async def announce_anycast(
    anycast_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Announce Anycast IP via BGP."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    success = await geodns.announce_anycast(anycast_id)
    
    if not success:
        raise HTTPException(404, "Anycast IP not found")
    
    return {"success": True, "message": "Anycast IP announced"}


@router.post("/geodns/anycast/{anycast_id}/withdraw")
async def withdraw_anycast(
    anycast_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Withdraw Anycast IP from BGP."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    success = await geodns.withdraw_anycast(anycast_id)
    
    if not success:
        raise HTTPException(404, "Anycast IP not found")
    
    return {"success": True, "message": "Anycast IP withdrawn"}


@router.get("/geodns/anycast/{anycast_id}/status")
async def get_anycast_status(
    anycast_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:read")),
):
    """Get Anycast IP status."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    status = await geodns.get_anycast_status(anycast_id)
    
    if not status:
        raise HTTPException(404, "Anycast IP not found")
    
    return status


# Edge Locations
@router.post("/edge/locations", response_model=EdgeLocationResponse)
async def register_edge_location(
    request: EdgeLocationCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("edge:manage")),
):
    """Register an edge PoP location."""
    from app.infrastructure.geodns_service import get_geodns_service, EdgeLocation
    
    geodns = get_geodns_service()
    
    edge = EdgeLocation(
        id=str(uuid4()),
        code=request.code,
        name=request.name,
        city=request.city,
        country=request.country,
        continent=request.continent,
        latitude=request.latitude,
        longitude=request.longitude,
        provider=request.provider,
        capacity=request.capacity,
        cache_storage_gb=request.cache_storage_gb,
        services=request.services,
    )
    
    await geodns.register_edge_location(edge)
    
    return EdgeLocationResponse(
        id=edge.id,
        code=edge.code,
        name=edge.name,
        city=edge.city,
        country=edge.country,
        continent=edge.continent,
        provider=edge.provider,
        capacity=edge.capacity,
        current_load=edge.current_load,
        services=edge.services,
        status=edge.status,
    )


@router.get("/edge/locations", response_model=List[EdgeLocationResponse])
async def list_edge_locations(
    continent: Optional[str] = None,
    country: Optional[str] = None,
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("edge:read")),
):
    """List edge locations."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    locations = await geodns.list_edge_locations(
        continent=continent,
        country=country,
        status=status,
    )
    
    return [
        EdgeLocationResponse(
            id=e.id,
            code=e.code,
            name=e.name,
            city=e.city,
            country=e.country,
            continent=e.continent,
            provider=e.provider,
            capacity=e.capacity,
            current_load=e.current_load,
            services=e.services,
            status=e.status,
        )
        for e in locations
    ]


@router.get("/edge/nearest")
async def get_nearest_edge(
    latitude: float = Query(...),
    longitude: float = Query(...),
    service: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("edge:read")),
):
    """Find nearest edge location."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    edge = await geodns.get_nearest_edge(latitude, longitude, service)
    
    if not edge:
        raise HTTPException(404, "No edge location found")
    
    return EdgeLocationResponse(
        id=edge.id,
        code=edge.code,
        name=edge.name,
        city=edge.city,
        country=edge.country,
        continent=edge.continent,
        provider=edge.provider,
        capacity=edge.capacity,
        current_load=edge.current_load,
        services=edge.services,
        status=edge.status,
    )


# Edge Cache Rules
@router.post("/edge/cache/rules", response_model=Dict[str, str])
async def create_cache_rule(
    request: EdgeCacheRuleCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("edge:manage")),
):
    """Create edge cache rule."""
    from app.infrastructure.edge_cdn_service import get_edge_cdn_service, CacheRule
    from app.infrastructure.edge_cdn_service import CacheRule as EdgeCacheRuleModel
    
    edge_cdn = get_edge_cdn_service()
    
    rule = EdgeCacheRuleModel(
        id=str(uuid4()),
        pattern=request.pattern,
        ttl_seconds=request.ttl_seconds,
        stale_while_revalidate=request.stale_while_revalidate,
        stale_if_error=request.stale_if_error,
        vary_headers=request.vary_headers,
        vary_by_cookie=request.vary_by_cookie,
        vary_by_header=request.vary_by_header,
        vary_by_region=request.vary_by_region,
        bypass_cookies=request.bypass_cookies,
        bypass_query_params=request.bypass_query_params,
        cache_methods=request.cache_methods,
        cache_status_codes=request.cache_status_codes,
        compress=request.compress,
        priority=request.priority,
        tags=request.tags,
    )
    
    edge_cdn.add_cache_rule(rule)
    
    return {"rule_id": rule.id, "message": "Cache rule created"}


@router.get("/edge/cache/rules")
async def list_cache_rules(
    enabled_only: bool = True,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("edge:read")),
):
    """List edge cache rules."""
    from app.infrastructure.edge_cdn_service import get_edge_cdn_service
    
    edge_cdn = get_edge_cdn_service()
    rules = edge_cdn.list_cache_rules(enabled_only=enabled_only)
    
    return {
        "rules": [
            {
                "id": r.id,
                "pattern": r.pattern,
                "ttl_seconds": r.ttl_seconds,
                "stale_while_revalidate": r.stale_while_revalidate,
                "stale_if_error": r.stale_if_error,
                "vary_headers": r.vary_headers,
                "vary_by_cookie": r.vary_by_cookie,
                "vary_by_header": r.vary_by_header,
                "vary_by_region": r.vary_by_region,
                "enabled": r.enabled,
                "priority": r.priority,
                "tags": r.tags,
            }
            for r in rules
        ]
    }


@router.post("/edge/cache/warm", response_model=Dict[str, Any])
async def warm_cache(
    urls: List[str] = Body(..., embed=True),
    regions: List[str] = Body([], embed=True),
    headers: Dict[str, str] = Body({}, embed=True),
    priority: int = Body(5, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("edge:manage")),
):
    """Warm cache for specific URLs."""
    from app.infrastructure.edge_cdn_service import get_edge_cdn_service
    
    edge_cdn = get_edge_cdn_service()
    request = await edge_cdn.warm_cache(
        urls=urls,
        regions=regions,
        headers=headers,
        priority=priority,
    )
    
    return {
        "request_id": request.id,
        "status": request.status,
        "urls": urls,
        "regions": regions,
    }


@router.post("/edge/cache/purge")
async def purge_cache(
    patterns: List[str] = Body(..., embed=True),
    regions: List[str] = Body([], embed=True),
    tiers: List[str] = Body(["edge", "regional", "origin_shield", "origin"], embed=True),
    tags: List[str] = Body([], embed=True),
    force: bool = Body(False, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("edge:manage")),
):
    """Purge cache entries."""
    from app.infrastructure.edge_cdn_service import get_edge_cdn_service, CachePurgeRequest
    
    edge_cdn = get_edge_cdn_service()
    
    request = CachePurgeRequest(
        id=str(uuid4()),
        patterns=patterns,
        regions=regions,
        tiers=tiers,
        tags=tags,
        force=force,
    )
    
    result = await edge_cdn.purge(
        patterns=request.patterns,
        regions=request.regions,
        tiers=request.tiers,
        tags=request.tags,
        force=request.force,
    )
    
    return {
        "purge_id": result.id,
        "status": result.status,
        "purged_keys": result.purged_keys,
    }


@router.get("/edge/cache/purge/{purge_id}")
async def get_purge_status(
    purge_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("edge:read")),
):
    """Get purge request status."""
    from app.infrastructure.edge_cdn_service import get_edge_cdn_service
    
    edge_cdn = get_edge_cdn_service()
    request = edge_cdn.get_purge_status(purge_id)
    
    if not request:
        raise HTTPException(404, "Purge request not found")
    
    return {
        "id": request.id,
        "patterns": request.patterns,
        "regions": request.regions,
        "tiers": request.tiers,
        "status": request.status,
        "purged_keys": request.purged_keys,
        "error": request.error,
        "created_at": request.created_at.isoformat(),
        "completed_at": request.completed_at.isoformat() if request.completed_at else None,
    }


# Traffic Policies
@router.post("/geodns/policies", response_model=TrafficPolicyResponse)
async def create_traffic_policy(
    request: TrafficPolicyCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Create a traffic management policy."""
    from app.infrastructure.geodns_service import get_geodns_service, TrafficPolicy, RoutingPolicy
    
    geodns = get_geodns_service()
    
    policy = TrafficPolicy(
        id=str(uuid4()),
        name=request.name,
        domain=request.domain,
        policy_type=RoutingPolicy(request.policy_type),
        default_region=request.default_region,
        regions=request.regions,
        geo_routes=request.geo_routes,
        health_check_enabled=request.health_check_enabled,
        health_check_interval=request.health_check_interval,
        failover_enabled=request.failover_enabled,
        failover_threshold=request.failover_threshold,
        traffic_shift_enabled=request.traffic_shift_enabled,
        canary_percentage=request.canary_percentage,
        shadow_enabled=request.shadow_enabled,
        shadow_target=request.shadow_target,
    )
    
    await geodns.create_traffic_policy(policy)
    
    return TrafficPolicyResponse(
        id=policy.id,
        name=policy.name,
        domain=policy.domain,
        policy_type=policy.policy_type.value,
        default_region=policy.default_region,
        regions=policy.regions,
        geo_routes=policy.geo_routes,
        health_check_enabled=policy.health_check_enabled,
        health_check_interval=policy.health_check_interval,
        failover_enabled=policy.failover_enabled,
        failover_threshold=policy.failover_threshold,
        traffic_shift_enabled=policy.traffic_shift_enabled,
        canary_percentage=policy.canary_percentage,
        shadow_enabled=policy.shadow_enabled,
        shadow_target=policy.shadow_target,
        created_at=policy.created_at.isoformat(),
        updated_at=policy.updated_at.isoformat(),
    )


@router.get("/geodns/policies", response_model=List[TrafficPolicyResponse])
async def list_traffic_policies(
    domain: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:read")),
):
    """List traffic policies."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    policies = await geodns.list_traffic_policies(domain=domain)
    
    return [
        TrafficPolicyResponse(
            id=p.id,
            name=p.name,
            domain=p.domain,
            policy_type=p.policy_type.value,
            default_region=p.default_region,
            regions=p.regions,
            geo_routes=p.geo_routes,
            health_check_enabled=p.health_check_enabled,
            health_check_interval=p.health_check_interval,
            failover_enabled=p.failover_enabled,
            failover_threshold=p.failover_threshold,
            traffic_shift_enabled=p.traffic_shift_enabled,
            canary_percentage=p.canary_percentage,
            shadow_enabled=p.shadow_enabled,
            shadow_target=p.shadow_target,
            created_at=p.created_at.isoformat(),
            updated_at=p.updated_at.isoformat(),
        )
        for p in policies
    ]


@router.post("/geodns/policies/{policy_id}/shift", response_model=TrafficShiftResponse)
async def create_traffic_shift(
    policy_id: str,
    request: TrafficShiftCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Create and start a traffic shift."""
    from app.infrastructure.geodns_service import get_geodns_service, TrafficShift
    
    geodns = get_geodns_service()
    
    shift = TrafficShift(
        id=str(uuid4()),
        policy_id=policy_id,
        from_region=request.from_region,
        to_region=request.to_region,
        percentage=request.percentage,
        start_time=utcnow(),
        end_time=utcnow() + timedelta(minutes=request.duration_minutes),
        ramp_up_minutes=request.duration_minutes,
    )
    
    await geodns.create_traffic_shift(shift)
    await geodns.start_traffic_shift(shift.id)
    
    return TrafficShiftResponse(
        id=shift.id,
        policy_id=shift.policy_id,
        from_region=shift.from_region,
        to_region=shift.to_region,
        percentage=shift.percentage,
        start_time=shift.start_time.isoformat(),
        end_time=shift.end_time.isoformat() if shift.end_time else None,
        ramp_up_minutes=shift.ramp_up_minutes,
        status=shift.status,
        progress=shift.progress,
    )


@router.get("/geodns/policies/{policy_id}/shifts")
async def list_traffic_shifts(
    policy_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:read")),
):
    """List traffic shifts for a policy."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    shifts = [
        s for s in geodns._traffic_shifts.values()
        if s.policy_id == policy_id
    ]
    
    return [
        {
            "id": s.id,
            "from_region": s.from_region,
            "to_region": s.to_region,
            "percentage": s.percentage,
            "status": s.status,
            "progress": s.progress,
            "start_time": s.start_time.isoformat(),
            "end_time": s.end_time.isoformat() if s.end_time else None,
        }
        for s in shifts
    ]


@router.patch("/geodns/shifts/{shift_id}")
async def update_traffic_shift(
    shift_id: str,
    percentage: Optional[float] = None,
    status: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Update traffic shift progress."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    success = await geodns.update_traffic_shift(
        shift_id,
        percentage=percentage,
        status=status,
    )
    
    if not success:
        raise HTTPException(404, "Traffic shift not found")
    
    return {"success": True}


@router.post("/geodns/shifts/{shift_id}/rollback")
async def rollback_traffic_shift(
    shift_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("geodns:manage")),
):
    """Rollback a traffic shift."""
    from app.infrastructure.geodns_service import get_geodns_service
    
    geodns = get_geodns_service()
    success = await geodns.rollback_traffic_shift(shift_id)
    
    if not success:
        raise HTTPException(404, "Traffic shift not found")
    
    return {"success": True}


# Traffic Splits
@router.post("/traffic/splits", response_model=TrafficSplitResponse)
async def create_traffic_split(
    request: TrafficSplitCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a traffic split."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, TrafficSplit
    
    manager = get_global_traffic_manager()
    
    split = TrafficSplit(
        id=str(uuid4()),
        name=request.name,
        source_region=request.source_region,
        targets=request.targets,
        strategy=request.strategy,
        sticky_sessions=request.sticky_sessions,
        cookie_name=request.cookie_name,
    )
    
    await manager.create_traffic_split(split)
    
    return TrafficSplitResponse(
        id=split.id,
        name=split.name,
        source_region=split.source_region,
        targets=split.targets,
        strategy=split.strategy,
        sticky_sessions=split.sticky_sessions,
        cookie_name=split.cookie_name,
        enabled=split.enabled,
        created_at=split.created_at.isoformat(),
    )


@router.get("/traffic/splits", response_model=List[TrafficSplitResponse])
async def list_traffic_splits(
    source_region: Optional[str] = None,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:read")),
    db: AsyncSession = Depends(get_db),
):
    """List traffic splits."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    splits = await manager.list_traffic_splits(source_region=source_region)
    
    return [
        TrafficSplitResponse(
            id=s.id,
            name=s.name,
            source_region=s.source_region,
            targets=s.targets,
            strategy=s.strategy,
            sticky_sessions=s.sticky_sessions,
            cookie_name=s.cookie_name,
            enabled=s.enabled,
            created_at=s.created_at.isoformat(),
        )
        for s in splits
    ]


@router.post("/traffic/splits/{split_id}/execute")
async def execute_traffic_split(
    split_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Execute a traffic split."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    success = await manager.execute_traffic_split(split_id)
    
    if not success:
        raise HTTPException(404, "Traffic split not found")
    
    return {"success": True, "message": "Traffic split executed"}


@router.post("/traffic/splits/{split_id}/rollback")
async def rollback_traffic_split(
    split_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Rollback a traffic split."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    success = await manager.rollback_traffic_split(split_id)
    
    if not success:
        raise HTTPException(404, "Traffic split not found")
    
    return {"success": True, "message": "Traffic split rolled back"}


# Replication
@router.post("/replication", response_model=ReplicationConfigResponse)
async def configure_replication(
    request: ReplicationConfigCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Configure cross-region replication."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, ReplicationConfig, ReplicationMode
    
    manager = get_global_traffic_manager()
    
    config = ReplicationConfig(
        source_region=request.source_region,
        target_region=request.target_region,
        databases=request.databases,
        storage_buckets=request.storage_buckets,
        kafka_topics=request.kafka_topics,
        replication_mode=ReplicationMode(request.replication_mode),
        lag_threshold_ms=request.lag_threshold_ms,
        alert_on_lag_ms=request.alert_on_lag_ms,
        sync_interval_seconds=request.sync_interval_seconds,
    )
    
    await manager.configure_replication(config)
    
    return ReplicationConfigResponse(
        source_region=config.source_region,
        target_region=config.target_region,
        databases=config.databases,
        storage_buckets=config.storage_buckets,
        kafka_topics=config.kafka_topics,
        replication_mode=config.replication_mode.value,
        lag_threshold_ms=config.lag_threshold_ms,
        alert_on_lag_ms=config.alert_on_lag_ms,
        sync_interval_seconds=config.sync_interval_seconds,
    )


@router.get("/replication/{source_region}/{target_region}")
async def get_replication_status(
    source_region: str,
    target_region: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:read")),
    db: AsyncSession = Depends(get_db),
):
    """Get replication status between regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    status = await manager.get_replication_status(source_region, target_region)
    return status


@router.post("/replication/{source_region}/{target_region}/pause")
async def pause_replication(
    source_region: str,
    target_region: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Pause replication between regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    success = await manager.pause_replication(source_region, target_region)
    
    if not success:
        raise HTTPException(404, "Replication config not found")
    
    return {"success": True}


@router.post("/replication/{source_region}/{target_region}/resume")
async def resume_replication(
    source_region: str,
    target_region: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Resume replication between regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    success = await manager.resume_replication(source_region, target_region)
    
    if not success:
        raise HTTPException(404, "Replication config not found")
    
    return {"success": True}


@router.post("/replication/{source_region}/{target_region}/verify")
async def verify_replication_consistency(
    source_region: str,
    target_region: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:read")),
    db: AsyncSession = Depends(get_db),
):
    """Verify data consistency between regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    return await manager.verify_replication_consistency(source_region, target_region)


# Failover
@router.post("/failover", response_model=FailoverEventResponse)
async def execute_failover(
    request: FailoverExecuteRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Execute a region failover."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, FailoverStrategy
    
    manager = get_global_traffic_manager()
    
    event = await manager.execute_failover(
        from_region=request.from_region,
        to_region=request.to_region,
        trigger_type=FailoverStrategy(request.trigger_type),
        reason=request.reason,
        force=request.force,
    )
    
    if not event:
        raise HTTPException(400, "Failover failed")
    
    return FailoverEventResponse(
        id=event.id,
        trigger=event.trigger,
        from_region=event.from_region,
        to_region=event.to_region,
        trigger_type=event.trigger_type.value,
        reason=event.reason,
        started_at=event.started_at.isoformat(),
        completed_at=event.completed_at.isoformat() if event.completed_at else None,
        status=event.status.value,
        steps=event.steps,
        rollback_reason=event.rollback_reason,
    )


@router.get("/failover/events", response_model=List[FailoverEventResponse])
async def list_failover_events(
    status: Optional[str] = None,
    limit: int = 50,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:read")),
    db: AsyncSession = Depends(get_db),
):
    """List failover events."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, FailoverStatus
    
    manager = get_global_traffic_manager()
    
    status_enum = FailoverStatus(status) if status else None
    events = manager.list_failover_events(status=status_enum, limit=limit)
    
    return [
        FailoverEventResponse(
            id=e.id,
            trigger=e.trigger,
            from_region=e.from_region,
            to_region=e.to_region,
            trigger_type=e.trigger_type.value,
            reason=e.reason,
            started_at=e.started_at.isoformat(),
            completed_at=e.completed_at.isoformat() if e.completed_at else None,
            status=e.status.value,
            steps=e.steps,
            rollback_reason=e.rollback_reason,
        )
        for e in events
    ]


@router.post("/failover/{event_id}/rollback")
async def rollback_failover(
    event_id: str,
    reason: str = Body("", embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Rollback a failover."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    success = await manager.rollback_failover(event_id, reason)
    
    if not success:
        raise HTTPException(404, "Failover event not found")
    
    return {"success": True, "message": "Failover rolled back"}


# Chaos Engineering
@router.post("/chaos/experiments", response_model=ChaosExperimentResponse)
async def create_chaos_experiment(
    request: ChaosExperimentCreate,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("chaos:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a chaos engineering experiment."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, ChaosExperiment
    
    manager = get_global_traffic_manager()
    
    experiment = ChaosExperiment(
        id=str(uuid4()),
        name=request.name,
        description=request.description,
        scenario=request.scenario,
        target_regions=request.target_regions,
        target_services=request.target_services,
        blast_radius=request.blast_radius,
        duration_minutes=request.duration_minutes,
        hypothesis=request.hypothesis,
        success_criteria=request.success_criteria,
        rollback_conditions=request.rollback_conditions,
        created_by=user.id,
    )
    
    await manager.create_chaos_experiment(experiment)
    
    return ChaosExperimentResponse(
        id=experiment.id,
        name=experiment.name,
        description=experiment.description,
        scenario=experiment.scenario,
        target_regions=experiment.target_regions,
        target_services=experiment.target_services,
        blast_radius=experiment.blast_radius,
        duration_minutes=experiment.duration_minutes,
        hypothesis=experiment.hypothesis,
        success_criteria=experiment.success_criteria,
        rollback_conditions=experiment.rollback_conditions,
        status=experiment.status,
        created_by=experiment.created_by,
        created_at=experiment.created_at.isoformat(),
        started_at=experiment.started_at.isoformat() if experiment.started_at else None,
        completed_at=experiment.completed_at.isoformat() if experiment.completed_at else None,
        results=experiment.results,
    )


@router.post("/chaos/experiments/{experiment_id}/run", response_model=ChaosExperimentResponse)
async def run_chaos_experiment(
    experiment_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("chaos:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Run a chaos experiment."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    experiment = await manager.run_chaos_experiment(experiment_id)
    
    return ChaosExperimentResponse(
        id=experiment.id,
        name=experiment.name,
        description=experiment.description,
        scenario=experiment.scenario,
        target_regions=experiment.target_regions,
        target_services=experiment.target_services,
        blast_radius=experiment.blast_radius,
        duration_minutes=experiment.duration_minutes,
        hypothesis=experiment.hypothesis,
        success_criteria=experiment.success_criteria,
        rollback_conditions=experiment.rollback_conditions,
        status=experiment.status,
        created_by=experiment.created_by,
        created_at=experiment.created_at.isoformat(),
        started_at=experiment.started_at.isoformat() if experiment.started_at else None,
        completed_at=experiment.completed_at.isoformat() if experiment.completed_at else None,
        results=experiment.results,
    )


@router.post("/chaos/game-day", response_model=GameDayResponse)
async def run_game_day(
    request: GameDayRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("chaos:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Run a comprehensive game day exercise."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    results = await manager.run_game_day(
        name=request.name,
        scenarios=request.scenarios,
        target_regions=request.target_regions,
        duration_hours=request.duration_hours,
    )
    
    return GameDayResponse(
        game_day_id=results["game_day_id"],
        name=results["name"],
        scenarios=results["scenarios"],
        target_regions=results["target_regions"],
        duration_hours=results["duration_hours"],
        started_at=results["started_at"],
        scenario_results=results["scenario_results"],
        overall_status=results["overall_status"],
    )


# ==================== Deployment ====================

@router.post("/deploy/region")
async def deploy_to_region(
    region_id: str = Body(..., embed=True),
    service: str = Body(..., embed=True),
    version: str = Body(..., embed=True),
    config: Dict[str, Any] = Body({}, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Deploy a service to a specific region."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    result = await manager.deploy_to_region(region_id, service, version, config)
    
    return result


@router.post("/deploy/rollout")
async def rollout_service(
    service: str = Body(..., embed=True),
    version: str = Body(..., embed=True),
    regions: List[str] = Body(..., embed=True),
    strategy: str = Body("rolling", embed=True),
    batch_size: int = Body(1, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Roll out a service version across regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    result = await manager.rollout_service(service, version, regions, strategy, batch_size)
    
    return result


# Cross-region Replication
@router.post("/replication/setup")
async def setup_cross_region_replication(
    source_region: str = Body(..., embed=True),
    target_regions: List[str] = Body(..., embed=True),
    databases: List[str] = Body([], embed=True),
    mode: str = Body("asynchronous", embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Set up cross-region data replication."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, ReplicationMode
    
    manager = get_global_traffic_manager()
    configs = await manager.setup_cross_region_replication(
        source_region=source_region,
        target_regions=target_regions,
        databases=databases,
        mode=ReplicationMode(mode),
    )
    
    return {"configured": len(configs), "configs": [
        {"source": c.source_region, "target": c.target_region} for c in configs
    ]}


@router.get("/replication/{source_region}/{target_region}/verify")
async def verify_replication_consistency(
    source_region: str,
    target_region: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:read")),
    db: AsyncSession = Depends(get_db),
):
    """Verify data consistency between regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    return await manager.verify_replication_consistency(source_region, target_region)


# Disaster Recovery
@router.post("/dr/plans")
async def create_dr_plan(
    name: str = Body(..., embed=True),
    primary_region: str = Body(..., embed=True),
    dr_regions: List[str] = Body(..., embed=True),
    rpo_seconds: int = Body(60, embed=True),
    rto_seconds: int = Body(300, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a disaster recovery plan."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    plan = await manager.create_dr_plan(
        name=name,
        primary_region=primary_region,
        dr_regions=dr_regions,
        rpo_seconds=rpo_seconds,
        rto_seconds=rto_seconds,
    )
    
    return plan


@router.post("/dr/plans/{plan_id}/test")
async def test_dr_plan(
    plan_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Test a disaster recovery plan."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    return await manager.test_dr_plan(plan_id)


# Deployment
@router.post("/deploy/region")
async def deploy_to_region(
    region_id: str = Body(..., embed=True),
    service: str = Body(..., embed=True),
    version: str = Body(..., embed=True),
    config: Dict[str, Any] = Body({}, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Deploy a service to a specific region."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    result = await manager.deploy_to_region(region_id, service, version, config)
    
    return result


@router.post("/deploy/rollout")
async def rollout_service(
    service: str = Body(..., embed=True),
    version: str = Body(..., embed=True),
    regions: List[str] = Body(..., embed=True),
    strategy: str = Body("rolling", embed=True),
    batch_size: int = Body(1, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Roll out a service version across regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    result = await manager.rollout_service(service, version, regions, strategy, batch_size)
    
    return result


# Cross-region Replication
@router.post("/replication/setup")
async def setup_cross_region_replication(
    source_region: str = Body(..., embed=True),
    target_regions: List[str] = Body(..., embed=True),
    databases: List[str] = Body([], embed=True),
    mode: str = Body("asynchronous", embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Set up cross-region data replication."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager, ReplicationMode
    
    manager = get_global_traffic_manager()
    configs = await manager.setup_cross_region_replication(
        source_region=source_region,
        target_regions=target_regions,
        databases=databases,
        mode=ReplicationMode(mode),
    )
    
    return {"configured": len(configs), "configs": [
        {"source": c.source_region, "target": c.target_region} for c in configs
    ]}


@router.get("/replication/{source_region}/{target_region}/verify")
async def verify_replication_consistency(
    source_region: str,
    target_region: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:read")),
    db: AsyncSession = Depends(get_db),
):
    """Verify data consistency between regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    return await manager.verify_replication_consistency(source_region, target_region)


# Disaster Recovery
@router.post("/dr/plans")
async def create_dr_plan(
    name: str = Body(..., embed=True),
    primary_region: str = Body(..., embed=True),
    dr_regions: List[str] = Body(..., embed=True),
    rpo_seconds: int = Body(60, embed=True),
    rto_seconds: int = Body(300, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Create a disaster recovery plan."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    plan = await manager.create_dr_plan(
        name=name,
        primary_region=primary_region,
        dr_regions=dr_regions,
        rpo_seconds=rpo_seconds,
        rto_seconds=rto_seconds,
    )
    
    return plan


@router.post("/dr/plans/{plan_id}/test")
async def test_dr_plan(
    plan_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Test a disaster recovery plan."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    return await manager.test_dr_plan(plan_id)


# Deployment
@router.post("/deploy/region")
async def deploy_to_region(
    region_id: str = Body(..., embed=True),
    service: str = Body(..., embed=True),
    version: str = Body(..., embed=True),
    config: Dict[str, Any] = Body({}, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Deploy a service to a specific region."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    result = await manager.deploy_to_region(region_id, service, version, config)
    
    return result


@router.post("/deploy/rollout")
async def rollout_service(
    service: str = Body(..., embed=True),
    version: str = Body(..., embed=True),
    regions: List[str] = Body(..., embed=True),
    strategy: str = Body("rolling", embed=True),
    batch_size: int = Body(1, embed=True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("multiregion:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Roll out a service version across regions."""
    from app.infrastructure.global_traffic_manager import get_global_traffic_manager
    
    manager = get_global_traffic_manager()
    result = await manager.rollout_service(service, version, regions, strategy, batch_size)
    
    return result


# ==================== Helper Functions ====================

import uuid
import time
import fnmatch

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