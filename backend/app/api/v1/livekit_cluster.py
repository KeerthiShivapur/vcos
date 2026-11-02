"""LiveKit Cluster API Endpoints for 500+ Concurrent Participants."""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.core.livekit_cluster import (
    LiveKitClusterManager,
    LiveKitNode,
    RoomAssignment,
    ClusterConfig,
    NodeRole,
    NodeStatus,
    ScalingPolicy,
    get_cluster_manager,
    init_cluster_manager,
)
from app.models.organization import Organization
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/livekit/cluster", tags=["LiveKit Cluster"])


# ==================== Models ====================

class RegisterNodeRequest(BaseModel):
    role: str = "worker"
    host: str
    port: int = 7880
    api_port: int = 7881
    region: str
    zone: str
    capacity: int = 500


class CreateRoomRequest(BaseModel):
    room_name: str
    max_participants: int = 500
    region: Optional[str] = None
    metadata: Dict[str, Any] = {}


class UpdateRoomRequest(BaseModel):
    max_participants: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None


class ClusterConfigRequest(BaseModel):
    cluster_name: str = "vcos-livekit-cluster"
    regions: List[str] = ["us-east-1", "us-west-2", "eu-west-1"]
    min_nodes_per_region: int = 2
    max_nodes_per_region: int = 20
    target_load_factor: float = 0.7
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.3
    scaling_policy: str = "balanced"
    health_check_interval: int = 10
    node_timeout: int = 30
    drain_timeout: int = 300
    enable_auto_scaling: bool = True
    enable_multi_region: bool = True
    redis_url: str = "redis://localhost:6379/5"


class ScaleRegionRequest(BaseModel):
    region: str
    action: str  # "up" or "down"
    node_count: int = 1


# ==================== Cluster Lifecycle ====================

@router.post("/initialize")
async def initialize_cluster(
    config: Optional[ClusterConfigRequest] = Body(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Initialize the LiveKit cluster manager."""
    if config:
        cluster_config = ClusterConfig(
            cluster_name=config.cluster_name,
            regions=config.regions,
            min_nodes_per_region=config.min_nodes_per_region,
            max_nodes_per_region=config.max_nodes_per_region,
            target_load_factor=config.target_load_factor,
            scale_up_threshold=config.scale_up_threshold,
            scale_down_threshold=config.scale_down_threshold,
            scaling_policy=ScalingPolicy(config.scaling_policy),
            health_check_interval=config.health_check_interval,
            node_timeout=config.node_timeout,
            drain_timeout=config.drain_timeout,
            enable_auto_scaling=config.enable_auto_scaling,
            enable_multi_region=config.enable_multi_region,
            redis_url=config.redis_url,
        )
    else:
        cluster_config = ClusterConfig()

    manager = await init_cluster_manager(cluster_config)
    return {
        "success": True,
        "cluster_name": manager.config.cluster_name,
        "regions": manager.config.regions,
    }


@router.post("/shutdown")
async def shutdown_cluster(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Shutdown the LiveKit cluster manager."""
    manager = get_cluster_manager()
    await manager.close()
    return {"success": True, "message": "Cluster manager shut down"}


@router.get("/status")
async def get_cluster_status(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:read")),
):
    """Get overall cluster status."""
    manager = get_cluster_manager()
    return manager.get_cluster_status()


# ==================== Node Management ====================

@router.post("/nodes")
async def register_node(
    request: RegisterNodeRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Register a new LiveKit node in the cluster."""
    manager = get_cluster_manager()
    
    try:
        role = NodeRole(request.role)
    except ValueError:
        raise HTTPException(400, f"Invalid role: {request.role}")

    node = await manager.register_node(
        role=role,
        host=request.host,
        port=request.port,
        api_port=request.api_port,
        region=request.region,
        zone=request.zone,
        capacity=request.capacity,
    )

    return {
        "success": True,
        "node_id": node.id,
        "node": {
            "id": node.id,
            "role": node.role.value,
            "host": node.host,
            "port": node.port,
            "region": node.region,
            "zone": node.zone,
            "capacity": node.capacity,
        }
    }


@router.delete("/nodes/{node_id}")
async def unregister_node(
    node_id: str,
    drain: bool = Query(True),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Unregister a node from the cluster."""
    manager = get_cluster_manager()
    
    if node_id not in manager.nodes:
        raise HTTPException(404, "Node not found")

    await manager.unregister_node(node_id, drain)
    return {"success": True, "message": f"Node {node_id} unregistered"}


@router.get("/nodes")
async def list_nodes(
    region: Optional[str] = Query(None),
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:read")),
):
    """List all nodes in the cluster."""
    manager = get_cluster_manager()
    
    role_enum = NodeRole(role) if role else None
    status_enum = NodeStatus(status) if status else None
    
    nodes = manager.list_nodes(region=region, role=role_enum, status=status_enum)
    return {"nodes": nodes}


@router.get("/nodes/{node_id}")
async def get_node_status(
    node_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:read")),
):
    """Get detailed status of a specific node."""
    manager = get_cluster_manager()
    
    status = manager.get_node_status(node_id)
    if not status:
        raise HTTPException(404, "Node not found")
    
    return status


@router.post("/nodes/{node_id}/drain")
async def drain_node(
    node_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Drain a node (stop accepting new rooms, migrate existing)."""
    manager = get_cluster_manager()
    
    if node_id not in manager.nodes:
        raise HTTPException(404, "Node not found")

    node = manager.nodes[node_id]
    node.status = NodeStatus.DRAINING
    
    # Reassign all rooms
    for room_name in list(node.rooms):
        await manager._reassign_room(room_name, exclude_node=node_id)
    
    return {"success": True, "message": f"Node {node_id} drained"}


# ==================== Room Management ====================

@router.post("/rooms")
async def create_room(
    request: CreateRoomRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:create")),
):
    """Create a new room in the cluster."""
    manager = get_cluster_manager()
    
    try:
        assignment = await manager.create_room(
            room_name=request.room_name,
            max_participants=request.max_participants,
            region=request.region,
            metadata=request.metadata,
        )
        
        return {
            "success": True,
            "room_name": assignment.room_name,
            "node_id": assignment.node_id,
            "max_participants": assignment.max_participants,
        }
    except RuntimeError as e:
        raise HTTPException(503, str(e))


@router.delete("/rooms/{room_name}")
async def delete_room(
    room_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:delete")),
):
    """Delete a room from the cluster."""
    manager = get_cluster_manager()
    
    success = await manager.delete_room(room_name)
    if not success:
        raise HTTPException(404, "Room not found")
    
    return {"success": True, "message": f"Room {room_name} deleted"}


@router.get("/rooms")
async def list_rooms(
    node_id: Optional[str] = Query(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
):
    """List all rooms in the cluster."""
    manager = get_cluster_manager()
    
    rooms = manager.list_rooms(node_id=node_id)
    return {"rooms": rooms}


@router.get("/rooms/{room_name}")
async def get_room_info(
    room_name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("meetings:read")),
):
    """Get detailed information about a room."""
    manager = get_cluster_manager()
    
    info = manager.get_room_info(room_name)
    if not info:
        raise HTTPException(404, "Room not found")
    
    return info


@router.post("/rooms/{room_name}/migrate")
async def migrate_room(
    room_name: str,
    target_node_id: Optional[str] = Body(None),
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Migrate a room to another node."""
    manager = get_cluster_manager()
    
    assignment = manager.room_assignments.get(room_name)
    if not assignment:
        raise HTTPException(404, "Room not found")
    
    if target_node_id:
        target_node = manager.nodes.get(target_node_id)
        if not target_node or not target_node.is_available:
            raise HTTPException(400, "Target node not available")
    else:
        # Find best node
        target_node = await manager._find_best_node(assignment.max_participants, assignment.node_id)
        if not target_node:
            raise HTTPException(503, "No available nodes for migration")
    
    old_node_id = assignment.node_id
    assignment.node_id = target_node.id
    target_node.rooms.add(room_name)
    
    if old_node_id in manager.nodes:
        manager.nodes[old_node_id].rooms.discard(room_name)
        manager.nodes[old_node_id].current_load = max(0, manager.nodes[old_node_id].current_load - 1)
    
    target_node.current_load += 1
    
    await manager._persist_assignment(assignment)
    
    return {
        "success": True,
        "room_name": room_name,
        "old_node": old_node_id,
        "new_node": target_node.id,
    }


# ==================== Scaling ====================

@router.post("/scale")
async def trigger_scaling(
    request: ScaleRegionRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Manually trigger scaling for a region."""
    manager = get_cluster_manager()
    
    if request.region not in manager.config.regions:
        raise HTTPException(400, f"Invalid region: {request.region}")
    
    if request.action == "up":
        await manager._scale_up_region(request.region)
        return {"success": True, "action": "scale_up", "region": request.region}
    elif request.action == "down":
        await manager._scale_down_region(request.region)
        return {"success": True, "action": "scale_down", "region": request.region}
    else:
        raise HTTPException(400, "Action must be 'up' or 'down'")


@router.get("/scaling/recommendations")
async def get_scaling_recommendations(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:read")),
):
    """Get scaling recommendations based on current load."""
    manager = get_cluster_manager()
    
    recommendations = []
    
    for region in manager.config.regions:
        nodes = [manager.nodes[nid] for nid in manager.region_nodes.get(region, []) if nid in manager.nodes]
        if not nodes:
            continue
        
        healthy = [n for n in nodes if n.status == NodeStatus.HEALTHY]
        if not healthy:
            continue
        
        avg_load = sum(n.load_factor for n in healthy) / len(healthy)
        max_load = max(n.load_factor for n in healthy)
        
        if avg_load > manager.config.scale_up_threshold or max_load > 0.9:
            recommendations.append({
                "region": region,
                "action": "scale_up",
                "reason": f"Average load: {avg_load:.1%}, Max load: {max_load:.1%}",
                "current_nodes": len(nodes),
                "max_nodes": manager.config.max_nodes_per_region,
            })
        elif avg_load < manager.config.scale_down_threshold and len(nodes) > manager.config.min_nodes_per_region:
            recommendations.append({
                "region": region,
                "action": "scale_down",
                "reason": f"Average load: {avg_load:.1%}",
                "current_nodes": len(nodes),
                "min_nodes": manager.config.min_nodes_per_region,
            })
    
    return {"recommendations": recommendations}


# ==================== Health & Metrics ====================

@router.get("/health")
async def cluster_health(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:read")),
):
    """Get cluster health summary."""
    manager = get_cluster_manager()
    
    total_nodes = len(manager.nodes)
    healthy_nodes = sum(1 for n in manager.nodes.values() if n.status == NodeStatus.HEALTHY)
    degraded_nodes = sum(1 for n in manager.nodes.values() if n.status == NodeStatus.DEGRADED)
    unhealthy_nodes = sum(1 for n in manager.nodes.values() if n.status == NodeStatus.UNHEALTHY)
    draining_nodes = sum(1 for n in manager.nodes.values() if n.status == NodeStatus.DRAINING)
    
    total_capacity = sum(n.capacity for n in manager.nodes.values())
    total_load = sum(n.current_load for n in manager.nodes.values())
    
    overall_health = "healthy"
    if unhealthy_nodes > 0:
        overall_health = "critical"
    elif degraded_nodes > 0:
        overall_health = "degraded"
    
    return {
        "overall_health": overall_health,
        "nodes": {
            "total": total_nodes,
            "healthy": healthy_nodes,
            "degraded": degraded_nodes,
            "unhealthy": unhealthy_nodes,
            "draining": draining_nodes,
        },
        "capacity": {
            "total": total_capacity,
            "used": total_load,
            "available": total_capacity - total_load,
            "utilization": total_load / total_capacity if total_capacity > 0 else 0,
        },
        "rooms": len(manager.room_assignments),
    }


@router.get("/metrics")
async def cluster_metrics(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:read")),
):
    """Get detailed cluster metrics."""
    manager = get_cluster_manager()
    
    node_metrics = []
    for node in manager.nodes.values():
        node_metrics.append({
            "node_id": node.id,
            "region": node.region,
            "zone": node.zone,
            "role": node.role.value,
            "status": node.status.value,
            "capacity": node.capacity,
            "current_load": node.current_load,
            "load_factor": node.load_factor,
            "room_count": len(node.rooms),
            "cpu_usage": node.cpu_usage,
            "memory_usage": node.memory_usage,
            "network_in_mbps": node.network_in_mbps,
            "network_out_mbps": node.network_out_mbps,
            "uptime_seconds": time.time() - node.started_at,
        })
    
    import time
    
    return {
        "timestamp": time.time(),
        "nodes": node_metrics,
        "summary": {
            "total_nodes": len(manager.nodes),
            "total_rooms": len(manager.room_assignments),
            "total_capacity": sum(n.capacity for n in manager.nodes.values()),
            "total_load": sum(n.current_load for n in manager.nodes.values()),
        },
    }


# ==================== Configuration ====================

@router.get("/config")
async def get_cluster_config(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:read")),
):
    """Get current cluster configuration."""
    manager = get_cluster_manager()
    
    return {
        "cluster_name": manager.config.cluster_name,
        "regions": manager.config.regions,
        "min_nodes_per_region": manager.config.min_nodes_per_region,
        "max_nodes_per_region": manager.config.max_nodes_per_region,
        "target_load_factor": manager.config.target_load_factor,
        "scale_up_threshold": manager.config.scale_up_threshold,
        "scale_down_threshold": manager.config.scale_down_threshold,
        "scaling_policy": manager.config.scaling_policy.value,
        "health_check_interval": manager.config.health_check_interval,
        "node_timeout": manager.config.node_timeout,
        "drain_timeout": manager.config.drain_timeout,
        "enable_auto_scaling": manager.config.enable_auto_scaling,
        "enable_multi_region": manager.config.enable_multi_region,
        "redis_url": manager.config.redis_url,
    }


@router.patch("/config")
async def update_cluster_config(
    config: ClusterConfigRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Update cluster configuration (runtime)."""
    manager = get_cluster_manager()
    
    manager.config.min_nodes_per_region = config.min_nodes_per_region
    manager.config.max_nodes_per_region = config.max_nodes_per_region
    manager.config.target_load_factor = config.target_load_factor
    manager.config.scale_up_threshold = config.scale_up_threshold
    manager.config.scale_down_threshold = config.scale_down_threshold
    manager.config.scaling_policy = ScalingPolicy(config.scaling_policy)
    manager.config.health_check_interval = config.health_check_interval
    manager.config.node_timeout = config.node_timeout
    manager.config.drain_timeout = config.drain_timeout
    manager.config.enable_auto_scaling = config.enable_auto_scaling
    manager.config.enable_multi_region = config.enable_multi_region
    
    return {"success": True, "message": "Configuration updated"}


# ==================== Multi-Region ====================

@router.get("/regions")
async def list_regions(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:read")),
):
    """List all configured regions with status."""
    manager = get_cluster_manager()
    
    region_status = {}
    for region in manager.config.regions:
        nodes = [manager.nodes[nid] for nid in manager.region_nodes.get(region, []) if nid in manager.nodes]
        healthy = [n for n in nodes if n.status == NodeStatus.HEALTHY]
        
        region_status[region] = {
            "total_nodes": len(nodes),
            "healthy_nodes": len(healthy),
            "total_capacity": sum(n.capacity for n in nodes),
            "current_load": sum(n.current_load for n in nodes),
            "avg_load_factor": sum(n.load_factor for n in healthy) / len(healthy) if healthy else 0,
            "rooms": sum(len(n.rooms) for n in nodes),
        }
    
    return {"regions": region_status}


@router.post("/regions/{region}/nodes")
async def add_node_to_region(
    region: str,
    request: RegisterNodeRequest,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Add a node to a specific region."""
    if region not in manager.config.regions:
        raise HTTPException(400, f"Invalid region: {region}")
    
    request.region = region
    return await register_node(request, org, user)


# ==================== Utility ====================

@router.post("/rebalance")
async def rebalance_cluster(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("admin:write")),
):
    """Trigger cluster rebalancing (migrate rooms for optimal distribution)."""
    manager = get_cluster_manager()
    
    migrated = 0
    
    # Sort nodes by load factor
    healthy_nodes = [n for n in manager.nodes.values() if n.status == NodeStatus.HEALTHY]
    healthy_nodes.sort(key=lambda n: n.load_factor, reverse=True)
    
    # Move rooms from most loaded to least loaded
    for node in healthy_nodes:
        if node.load_factor > manager.config.target_load_factor:
            # Move some rooms
            rooms_to_move = list(node.rooms)[:2]  # Move up to 2 rooms
            for room_name in rooms_to_move:
                target = await manager._find_best_node(500, node.id)
                if target and target != node:
                    await manager._reassign_room(room_name, exclude_node=node.id)
                    migrated += 1
    
    return {"success": True, "migrated_rooms": migrated}


import time