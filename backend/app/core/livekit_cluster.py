"""
LiveKit Cluster Manager for VCOS Real-time Collaboration.

Provides:
- LiveKit cluster management for 500+ concurrent participants
- Room sharding and load balancing
- Multi-region cluster coordination
- Auto-scaling based on load
- Health monitoring and failover
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)


class NodeRole(str, Enum):
    """LiveKit node roles in cluster."""
    CONTROLLER = "controller"
    WORKER = "worker"
    EDGE = "edge"


class NodeStatus(str, Enum):
    """Node health status."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    DRAINING = "draining"


class ScalingPolicy(str, Enum):
    """Auto-scaling policies."""
    CONSERVATIVE = "conservative"
    BALANCED = "balanced"
    AGGRESSIVE = "aggressive"


@dataclass
class LiveKitNode:
    """LiveKit cluster node."""
    id: str
    role: NodeRole
    host: str
    port: int
    api_port: int
    region: str
    zone: str
    status: NodeStatus = NodeStatus.HEALTHY
    capacity: int = 500  # Max concurrent participants
    current_load: int = 0
    rooms: Set[str] = field(default_factory=set)
    cpu_usage: float = 0.0
    memory_usage: float = 0.0
    network_in_mbps: float = 0.0
    network_out_mbps: float = 0.0
    last_heartbeat: float = field(default_factory=time.time)
    started_at: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def url(self) -> str:
        return f"ws://{self.host}:{self.port}"

    @property
    def api_url(self) -> str:
        return f"http://{self.host}:{self.api_port}"

    @property
    def load_factor(self) -> float:
        return self.current_load / self.capacity if self.capacity > 0 else 1.0

    @property
    def is_available(self) -> bool:
        return self.status == NodeStatus.HEALTHY and self.load_factor < 0.9


@dataclass
class RoomAssignment:
    """Room to node assignment."""
    room_name: str
    node_id: str
    created_at: float = field(default_factory=time.time)
    participant_count: int = 0
    max_participants: int = 500
    is_recording: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClusterConfig:
    """LiveKit cluster configuration."""
    cluster_name: str = "vcos-livekit-cluster"
    regions: List[str] = field(default_factory=lambda: ["us-east-1", "us-west-2", "eu-west-1"])
    min_nodes_per_region: int = 2
    max_nodes_per_region: int = 20
    target_load_factor: float = 0.7
    scale_up_threshold: float = 0.8
    scale_down_threshold: float = 0.3
    scaling_policy: ScalingPolicy = ScalingPolicy.BALANCED
    health_check_interval: int = 10  # seconds
    node_timeout: int = 30  # seconds
    drain_timeout: int = 300  # seconds
    enable_auto_scaling: bool = True
    enable_multi_region: bool = True
    redis_url: Optional[str] = None


class LiveKitClusterManager:
    """
    Manages LiveKit cluster for 500+ concurrent participants.
    
    Features:
    - Room sharding across nodes
    - Load-based room placement
    - Multi-region support
    - Auto-scaling
    - Health monitoring
    - Graceful node draining
    """

    def __init__(self, config: ClusterConfig):
        self.config = config
        self.nodes: Dict[str, LiveKitNode] = {}
        self.room_assignments: Dict[str, RoomAssignment] = {}
        self.region_nodes: Dict[str, List[str]] = defaultdict(list)
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._scaling_task: Optional[asyncio.Task] = None
        self._redis = None
        self._http_session: Optional[aiohttp.ClientSession] = None
        self._node_id_counter = 0

    async def initialize(self):
        """Initialize cluster manager."""
        # Initialize Redis for distributed state
        try:
            import redis.asyncio as redis
            self._redis = redis.from_url(
                self.config.redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
            await self._redis.ping()
            logger.info("Redis connection established for cluster state")
        except Exception as e:
            logger.warning(f"Redis not available, using in-memory state: {e}")

        # Initialize HTTP session
        self._http_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=10),
            connector=aiohttp.TCPConnector(limit=50),
        )

        # Start background tasks
        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())
        self._scaling_task = asyncio.create_task(self._scaling_loop())

        # Register this instance as a controller node
        await self._register_controller()

        logger.info(f"LiveKit Cluster Manager initialized: {self.config.cluster_name}")

    async def close(self):
        """Shutdown cluster manager."""
        self._running = False

        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass

        if self._scaling_task:
            self._scaling_task.cancel()
            try:
                await self._scaling_task
            except asyncio.CancelledError:
                pass

        if self._http_session:
            await self._http_session.close()

        if self._redis:
            await self._redis.close()

        logger.info("LiveKit Cluster Manager closed")

    async def _register_controller(self):
        """Register this instance as controller."""
        controller_id = f"controller-{uuid.uuid4().hex[:8]}"
        # In production, this would register with service discovery
        logger.info(f"Registered as controller: {controller_id}")

    # ==================== Node Management ====================

    async def register_node(
        self,
        role: NodeRole,
        host: str,
        port: int,
        api_port: int,
        region: str,
        zone: str,
        capacity: int = 500,
    ) -> LiveKitNode:
        """Register a new LiveKit node in the cluster."""
        self._node_id_counter += 1
        node_id = f"{role.value}-{region}-{zone}-{self._node_id_counter}"

        node = LiveKitNode(
            id=node_id,
            role=role,
            host=host,
            port=port,
            api_port=api_port,
            region=region,
            zone=zone,
            capacity=capacity,
        )

        self.nodes[node_id] = node
        self.region_nodes[region].append(node_id)

        # Persist to Redis
        await self._persist_node(node)

        logger.info(f"Registered node: {node_id} ({role.value}) in {region}/{zone}")
        return node

    async def unregister_node(self, node_id: str, drain: bool = True):
        """Unregister a node from the cluster."""
        node = self.nodes.get(node_id)
        if not node:
            return

        if drain:
            node.status = NodeStatus.DRAINING
            # Wait for rooms to drain
            await self._drain_node(node_id, self.config.drain_timeout)

        # Reassign rooms
        for room_name in list(node.rooms):
            await self._reassign_room(room_name, exclude_node=node_id)

        # Remove from region list
        if node_id in self.region_nodes.get(node.region, []):
            self.region_nodes[node.region].remove(node_id)

        # Remove from Redis
        await self._remove_node(node_id)

        del self.nodes[node_id]
        logger.info(f"Unregistered node: {node_id}")

    async def _drain_node(self, node_id: str, timeout: int):
        """Wait for node to drain (no active rooms)."""
        start = time.time()
        node = self.nodes.get(node_id)
        if not node:
            return

        while node.rooms and (time.time() - start) < timeout:
            await asyncio.sleep(5)
            node = self.nodes.get(node_id)
            if not node:
                return

        if node.rooms:
            logger.warning(f"Node {node_id} drain timeout, {len(node.rooms)} rooms still active")

    async def _reassign_room(self, room_name: str, exclude_node: Optional[str] = None):
        """Reassign room to another node."""
        assignment = self.room_assignments.get(room_name)
        if not assignment:
            return

        # Find best available node
        new_node = await self._find_best_node(assignment.max_participants, exclude_node)
        if not new_node:
            logger.error(f"No available node for room {room_name}")
            return

        # Migrate room (in production, use LiveKit's room migration)
        old_node_id = assignment.node_id
        assignment.node_id = new_node.id
        new_node.rooms.add(room_name)

        if old_node_id in self.nodes:
            self.nodes[old_node_id].rooms.discard(room_name)

        await self._persist_assignment(assignment)
        logger.info(f"Reassigned room {room_name} from {old_node_id} to {new_node.id}")

    # ==================== Room Management ====================

    async def create_room(
        self,
        room_name: str,
        max_participants: int = 500,
        region: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RoomAssignment:
        """Create a new room and assign to optimal node."""
        # Select region
        if not region:
            region = await self._select_optimal_region()

        # Find best node in region
        node = await self._find_best_node_in_region(region, max_participants)
        if not node:
            # Try other regions
            for r in self.config.regions:
                if r != region:
                    node = await self._find_best_node_in_region(r, max_participants)
                    if node:
                        region = r
                        break

        if not node:
            raise RuntimeError("No available nodes for room creation")

        # Create room via LiveKit API
        await self._create_room_on_node(node, room_name, max_participants, metadata)

        # Create assignment
        assignment = RoomAssignment(
            room_name=room_name,
            node_id=node.id,
            max_participants=max_participants,
            metadata=metadata or {},
        )

        self.room_assignments[room_name] = assignment
        node.rooms.add(room_name)
        node.current_load += 1

        await self._persist_assignment(assignment)

        logger.info(f"Created room: {room_name} on node {node.id} ({region})")
        return assignment

    async def _find_best_node_in_region(
        self,
        region: str,
        required_capacity: int,
    ) -> Optional[LiveKitNode]:
        """Find best available node in a specific region."""
        candidates = [
            self.nodes[nid]
            for nid in self.region_nodes.get(region, [])
            if self.nodes[nid].is_available and self.nodes[nid].capacity >= required_capacity
        ]

        if not candidates:
            return None

        # Sort by load factor (least loaded first)
        candidates.sort(key=lambda n: n.load_factor)
        return candidates[0]

    async def _find_best_node(
        self,
        required_capacity: int,
        exclude_node: Optional[str] = None,
    ) -> Optional[LiveKitNode]:
        """Find best available node across all regions."""
        candidates = [
            n for n in self.nodes.values()
            if n.is_available and n.capacity >= required_capacity and n.id != exclude_node
        ]

        if not candidates:
            return None

        candidates.sort(key=lambda n: n.load_factor)
        return candidates[0]

    async def _select_optimal_region(self) -> str:
        """Select optimal region based on load and latency."""
        # In production, consider user location, latency, etc.
        region_loads = {}
        for region in self.config.regions:
            nodes = [self.nodes[nid] for nid in self.region_nodes.get(region, []) if nid in self.nodes]
            if nodes:
                avg_load = sum(n.load_factor for n in nodes) / len(nodes)
                region_loads[region] = avg_load

        if region_loads:
            return min(region_loads, key=region_loads.get)
        return self.config.regions[0]

    async def delete_room(self, room_name: str) -> bool:
        """Delete a room and free up capacity."""
        assignment = self.room_assignments.get(room_name)
        if not assignment:
            return False

        node = self.nodes.get(assignment.node_id)
        if node:
            # Delete room via LiveKit API
            await self._delete_room_on_node(node, room_name)
            node.rooms.discard(room_name)
            node.current_load = max(0, node.current_load - 1)

        del self.room_assignments[room_name]
        await self._remove_assignment(room_name)

        logger.info(f"Deleted room: {room_name}")
        return True

    async def get_room_node(self, room_name: str) -> Optional[LiveKitNode]:
        """Get the node hosting a room."""
        assignment = self.room_assignments.get(room_name)
        if assignment:
            return self.nodes.get(assignment.node_id)
        return None

    # ==================== LiveKit API Operations ====================

    async def _create_room_on_node(
        self,
        node: LiveKitNode,
        room_name: str,
        max_participants: int,
        metadata: Optional[Dict[str, Any]],
    ):
        """Create room on specific LiveKit node."""
        if not self._http_session:
            return

        url = f"{node.api_url}/twirp/livekit.RoomService/CreateRoom"
        payload = {
            "name": room_name,
            "empty_timeout": 300,
            "max_participants": max_participants,
        }
        if metadata:
            payload["metadata"] = str(metadata)

        try:
            async with self._http_session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Failed to create room on {node.id}: {text}")
        except Exception as e:
            logger.error(f"Error creating room on {node.id}: {e}")

    async def _delete_room_on_node(self, node: LiveKitNode, room_name: str):
        """Delete room on specific LiveKit node."""
        if not self._http_session:
            return

        url = f"{node.api_url}/twirp/livekit.RoomService/DeleteRoom"
        payload = {"room": room_name}

        try:
            async with self._http_session.post(url, json=payload) as resp:
                if resp.status != 200:
                    text = await resp.text()
                    logger.error(f"Failed to delete room on {node.id}: {text}")
        except Exception as e:
            logger.error(f"Error deleting room on {node.id}: {e}")

    # ==================== Scaling ====================

    async def _scaling_loop(self):
        """Auto-scaling loop."""
        while self._running:
            try:
                if self.config.enable_auto_scaling:
                    await self._evaluate_scaling()
            except Exception as e:
                logger.error(f"Scaling loop error: {e}")

            await asyncio.sleep(60)  # Check every minute

    async def _evaluate_scaling(self):
        """Evaluate if scaling is needed."""
        for region in self.config.regions:
            await self._evaluate_region_scaling(region)

    async def _evaluate_region_scaling(self, region: str):
        """Evaluate scaling for a specific region."""
        nodes = [self.nodes[nid] for nid in self.region_nodes.get(region, []) if nid in self.nodes]
        if not nodes:
            return

        healthy_nodes = [n for n in nodes if n.status == NodeStatus.HEALTHY]
        if not healthy_nodes:
            return

        avg_load = sum(n.load_factor for n in healthy_nodes) / len(healthy_nodes)
        max_load = max(n.load_factor for n in healthy_nodes)

        # Scale up
        if (avg_load > self.config.scale_up_threshold or max_load > 0.9) and len(nodes) < self.config.max_nodes_per_region:
            await self._scale_up_region(region)

        # Scale down
        elif avg_load < self.config.scale_down_threshold and len(nodes) > self.config.min_nodes_per_region:
            await self._scale_down_region(region)

    async def _scale_up_region(self, region: str):
        """Add a new node to region."""
        # In production, this would trigger infrastructure provisioning (K8s, ASG, etc.)
        logger.info(f"Scaling up region {region} - would provision new node")
        # Example: trigger Kubernetes HPA, AWS ASG, etc.

    async def _scale_down_region(self, region: str):
        """Remove a node from region."""
        # Find least loaded drainable node
        nodes = [self.nodes[nid] for nid in self.region_nodes.get(region, []) if nid in self.nodes]
        drainable = [n for n in nodes if not n.rooms and n.status == NodeStatus.HEALTHY]

        if drainable:
            # Sort by uptime (oldest first for scaling down)
            drainable.sort(key=lambda n: n.started_at)
            node_to_remove = drainable[0]
            logger.info(f"Scaling down region {region} - would remove node {node_to_remove.id}")
            # In production: await self.unregister_node(node_to_remove.id)

    # ==================== Health Monitoring ====================

    async def _monitor_loop(self):
        """Health monitoring loop."""
        while self._running:
            try:
                await self._check_node_health()
                await self._collect_metrics()
            except Exception as e:
                logger.error(f"Monitor loop error: {e}")

            await asyncio.sleep(self.config.health_check_interval)

    async def _check_node_health(self):
        """Check health of all nodes."""
        for node in list(self.nodes.values()):
            try:
                healthy = await self._check_node(node)
                if healthy:
                    if node.status != NodeStatus.HEALTHY:
                        node.status = NodeStatus.HEALTHY
                        logger.info(f"Node {node.id} recovered")
                else:
                    if node.status == NodeStatus.HEALTHY:
                        node.status = NodeStatus.DEGRADED
                        logger.warning(f"Node {node.id} degraded")
                    elif node.status == NodeStatus.DEGRADED:
                        # Check if timeout exceeded
                        if time.time() - node.last_heartbeat > self.config.node_timeout:
                            node.status = NodeStatus.UNHEALTHY
                            logger.error(f"Node {node.id} unhealthy - initiating failover")
                            await self._failover_node(node.id)
            except Exception as e:
                logger.error(f"Health check failed for {node.id}: {e}")

    async def _check_node(self, node: LiveKitNode) -> bool:
        """Check single node health."""
        if not self._http_session:
            return False

        try:
            async with self._http_session.get(
                f"{node.api_url}/twirp/livekit.RoomService/ListRooms",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    node.last_heartbeat = time.time()
                    return True
        except Exception:
            pass

        return False

    async def _collect_metrics(self):
        """Collect metrics from all nodes."""
        for node in self.nodes.values():
            try:
                await self._collect_node_metrics(node)
            except Exception as e:
                logger.error(f"Metrics collection failed for {node.id}: {e}")

    async def _collect_node_metrics(self, node: LiveKitNode):
        """Collect metrics from a single node."""
        if not self._http_session:
            return

        try:
            # Get room stats
            async with self._http_session.get(
                f"{node.api_url}/twirp/livekit.RoomService/ListRooms",
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    rooms = data.get("rooms", [])
                    node.current_load = sum(r.get("num_participants", 0) for r in rooms)
                    node.rooms = {r["name"] for r in rooms}

            # Get node stats (if available)
            # In production, would query Prometheus or node exporter
        except Exception as e:
            logger.debug(f"Metrics collection partial for {node.id}: {e}")

    async def _failover_node(self, node_id: str):
        """Failover rooms from unhealthy node."""
        node = self.nodes.get(node_id)
        if not node:
            return

        logger.warning(f"Initiating failover for node {node_id} with {len(node.rooms)} rooms")

        for room_name in list(node.rooms):
            await self._reassign_room(room_name, exclude_node=node_id)

        # Mark node for removal
        node.status = NodeStatus.UNHEALTHY

    # ==================== State Persistence ====================

    async def _persist_node(self, node: LiveKitNode):
        """Persist node to Redis."""
        if not self._redis:
            return

        import json
        key = f"livekit:cluster:nodes:{node.id}"
        data = {
            "id": node.id,
            "role": node.role.value,
            "host": node.host,
            "port": node.port,
            "api_port": node.api_port,
            "region": node.region,
            "zone": node.zone,
            "status": node.status.value,
            "capacity": node.capacity,
            "current_load": node.current_load,
            "rooms": list(node.rooms),
            "cpu_usage": node.cpu_usage,
            "memory_usage": node.memory_usage,
            "last_heartbeat": node.last_heartbeat,
            "started_at": node.started_at,
            "metadata": node.metadata,
        }
        await self._redis.setex(key, 300, json.dumps(data))  # 5 min TTL

        # Add to region set
        await self._redis.sadd(f"livekit:cluster:regions:{node.region}", node.id)

    async def _remove_node(self, node_id: str):
        """Remove node from Redis."""
        if not self._redis:
            return

        node = self.nodes.get(node_id)
        if node:
            await self._redis.delete(f"livekit:cluster:nodes:{node_id}")
            await self._redis.srem(f"livekit:cluster:regions:{node.region}", node_id)

    async def _persist_assignment(self, assignment: RoomAssignment):
        """Persist room assignment to Redis."""
        if not self._redis:
            return

        import json
        key = f"livekit:cluster:rooms:{assignment.room_name}"
        data = {
            "room_name": assignment.room_name,
            "node_id": assignment.node_id,
            "created_at": assignment.created_at,
            "participant_count": assignment.participant_count,
            "max_participants": assignment.max_participants,
            "is_recording": assignment.is_recording,
            "metadata": assignment.metadata,
        }
        await self._redis.set(key, json.dumps(data))

    async def _remove_assignment(self, room_name: str):
        """Remove room assignment from Redis."""
        if not self._redis:
            return

        await self._redis.delete(f"livekit:cluster:rooms:{room_name}")

    # ==================== Query Methods ====================

    def get_cluster_status(self) -> Dict[str, Any]:
        """Get overall cluster status."""
        total_capacity = sum(n.capacity for n in self.nodes.values())
        total_load = sum(n.current_load for n in self.nodes.values())
        healthy_nodes = sum(1 for n in self.nodes.values() if n.status == NodeStatus.HEALTHY)

        region_stats = {}
        for region in self.config.regions:
            nodes = [self.nodes[nid] for nid in self.region_nodes.get(region, []) if nid in self.nodes]
            region_stats[region] = {
                "nodes": len(nodes),
                "healthy": sum(1 for n in nodes if n.status == NodeStatus.HEALTHY),
                "total_capacity": sum(n.capacity for n in nodes),
                "current_load": sum(n.current_load for n in nodes),
                "avg_load_factor": sum(n.load_factor for n in nodes) / len(nodes) if nodes else 0,
            }

        return {
            "cluster_name": self.config.cluster_name,
            "total_nodes": len(self.nodes),
            "healthy_nodes": healthy_nodes,
            "total_capacity": total_capacity,
            "current_load": total_load,
            "overall_load_factor": total_load / total_capacity if total_capacity > 0 else 0,
            "total_rooms": len(self.room_assignments),
            "regions": region_stats,
        }

    def get_node_status(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Get status of a specific node."""
        node = self.nodes.get(node_id)
        if not node:
            return None

        return {
            "id": node.id,
            "role": node.role.value,
            "host": node.host,
            "port": node.port,
            "region": node.region,
            "zone": node.zone,
            "status": node.status.value,
            "capacity": node.capacity,
            "current_load": node.current_load,
            "load_factor": node.load_factor,
            "rooms": list(node.rooms),
            "room_count": len(node.rooms),
            "cpu_usage": node.cpu_usage,
            "memory_usage": node.memory_usage,
            "uptime_seconds": time.time() - node.started_at,
            "last_heartbeat": node.last_heartbeat,
        }

    def list_nodes(
        self,
        region: Optional[str] = None,
        role: Optional[NodeRole] = None,
        status: Optional[NodeStatus] = None,
    ) -> List[Dict[str, Any]]:
        """List nodes with optional filters."""
        nodes = list(self.nodes.values())

        if region:
            nodes = [n for n in nodes if n.region == region]
        if role:
            nodes = [n for n in nodes if n.role == role]
        if status:
            nodes = [n for n in nodes if n.status == status]

        return [
            {
                "id": n.id,
                "role": n.role.value,
                "region": n.region,
                "zone": n.zone,
                "status": n.status.value,
                "load_factor": n.load_factor,
                "room_count": len(n.rooms),
            }
            for n in nodes
        ]

    def list_rooms(self, node_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List rooms with optional node filter."""
        rooms = []
        for assignment in self.room_assignments.values():
            if node_id and assignment.node_id != node_id:
                continue
            rooms.append({
                "room_name": assignment.room_name,
                "node_id": assignment.node_id,
                "participant_count": assignment.participant_count,
                "max_participants": assignment.max_participants,
                "is_recording": assignment.is_recording,
                "created_at": assignment.created_at,
            })
        return rooms

    def get_room_info(self, room_name: str) -> Optional[Dict[str, Any]]:
        """Get detailed room information."""
        assignment = self.room_assignments.get(room_name)
        if not assignment:
            return None

        node = self.nodes.get(assignment.node_id)
        return {
            "room_name": assignment.room_name,
            "node_id": assignment.node_id,
            "node_url": node.url if node else None,
            "node_region": node.region if node else None,
            "participant_count": assignment.participant_count,
            "max_participants": assignment.max_participants,
            "is_recording": assignment.is_recording,
            "created_at": assignment.created_at,
            "metadata": assignment.metadata,
        }


# Global cluster manager instance
_cluster_manager: Optional[LiveKitClusterManager] = None


def get_cluster_manager() -> LiveKitClusterManager:
    """Get or create cluster manager singleton."""
    global _cluster_manager
    if _cluster_manager is None:
        _cluster_manager = LiveKitClusterManager(ClusterConfig())
    return _cluster_manager


async def init_cluster_manager(config: Optional[ClusterConfig] = None) -> LiveKitClusterManager:
    """Initialize cluster manager with custom config."""
    global _cluster_manager
    _cluster_manager = LiveKitClusterManager(config or ClusterConfig())
    await _cluster_manager.initialize()
    return _cluster_manager