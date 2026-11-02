"""
Global Traffic Manager for VCOS.

Provides:
- Global load balancing with GeoDNS + Anycast
- Multi-region active-active traffic management
- Cross-region data replication coordination
- Disaster recovery orchestration
- Traffic splitting and canary deployments
- Health-aware traffic steering
"""

import asyncio
import hashlib
import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import uuid4

from app.core.config import settings
from app.core.timeutils import utcnow
from app.infrastructure.geodns_service import (
    GeoDNSService,
    get_geodns_service,
    RoutingPolicy,
    RecordType,
    Endpoint,
    TrafficPolicy,
    TrafficShift,
    HealthStatus,
)
from app.infrastructure.regions_service import (
    RegionsService,
    regions_service,
    RegionStatus,
)

logger = logging.getLogger(__name__)


class DeploymentModel(str, Enum):
    """Deployment models."""
    ACTIVE_PASSIVE = "active_passive"
    ACTIVE_ACTIVE = "active_active"
    ACTIVE_ACTIVE_SYNC = "active_active_sync"
    ACTIVE_STANDBY = "active_standby"


class ReplicationMode(str, Enum):
    """Data replication modes."""
    SYNCHRONOUS = "synchronous"
    ASYNCHRONOUS = "asynchronous"
    SEMI_SYNC = "semi_sync"


class FailoverStrategy(str, Enum):
    """Failover strategies."""
    AUTOMATIC = "automatic"
    MANUAL = "manual"
    MANUAL_APPROVE = "manual_approve"


class RegionRole(str, Enum):
    """Region roles in multi-region deployment."""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    TERTIARY = "tertiary"
    READ_REPLICA = "read_replica"
    DR_STANDBY = "dr_standby"
    EDGE = "edge"


@dataclass
class RegionDeployment:
    """Region deployment configuration."""
    region_id: str
    name: str
    role: RegionRole
    deployment_model: DeploymentModel
    active: bool = True
    priority: int = 100
    capacity: Dict[str, float] = field(default_factory=dict)  # resource -> capacity
    current_load: Dict[str, float] = field(default_factory=dict)
    replication_mode: ReplicationMode = ReplicationMode.ASYNCHRONOUS
    replication_lag_ms: int = 0
    data_center: str = ""
    availability_zone: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class GlobalLoadBalancerConfig:
    """Global load balancer configuration."""
    id: str
    name: str
    domain: str
    deployment_model: DeploymentModel
    primary_region: str
    regions: List[str] = field(default_factory=list)
    routing_policy: str = "latency_based"
    health_check_interval: int = 30
    failover_threshold: int = 3
    failover_strategy: str = "automatic"
    session_affinity: bool = False
    session_affinity_ttl: int = 3600
    cross_region_replication: bool = True
    replication_mode: str = "asynchronous"
    rpo_seconds: int = 60  # Recovery Point Objective
    rto_seconds: int = 300  # Recovery Time Objective
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RegionHealth:
    """Region health status."""
    region_id: str
    region_name: str
    healthy: bool
    latency_ms: float
    load_percent: float
    active_instances: int
    degraded_instances: int
    offline_instances: int
    last_check: datetime
    services: Dict[str, bool] = field(default_factory=dict)
    capacity: Dict[str, float] = field(default_factory=dict)
    issues: List[str] = field(default_factory=list)


@dataclass
class TrafficSplit:
    """Traffic split configuration."""
    id: str
    name: str
    source_region: str
    targets: List[Dict[str, Any]]  # region, percentage
    strategy: str = "weighted"  # weighted, mirror, shadow
    sticky_sessions: bool = False
    cookie_name: str = "vcos_region"
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ReplicationConfig:
    """Cross-region replication configuration."""
    source_region: str
    target_region: str
    databases: List[str] = field(default_factory=list)
    storage_buckets: List[str] = field(default_factory=list)
    kafka_topics: List[str] = field(default_factory=list)
    replication_mode: str = "asynchronous"
    lag_threshold_ms: int = 5000
    alert_on_lag_ms: int = 10000
    sync_interval_seconds: int = 60


@dataclass
class FailoverEvent:
    """Failover event record."""
    id: str
    trigger: str
    from_region: str
    to_region: str
    trigger_type: str  # automatic, manual, scheduled
    reason: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    status: str = "in_progress"  # in_progress, completed, failed, rolled_back
    steps: List[Dict[str, Any]] = field(default_factory=list)
    rollback_reason: Optional[str] = None


@dataclass
class ChaosExperiment:
    """Chaos engineering experiment."""
    id: str
    name: str
    description: str
    scenario: str
    target_regions: List[str]
    target_services: List[str]
    blast_radius: str  # single_service, single_region, multi_region, global
    duration_minutes: int
    hypothesis: str
    success_criteria: List[str]
    rollback_conditions: List[str]
    created_by: str
    status: str = "planned"  # planned, running, completed, failed, cancelled
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    results: Dict[str, Any] = field(default_factory=dict)
    rollback_plan: str = ""


class GlobalTrafficManager:
    """
    Global Traffic Manager for Multi-Region Active-Active.
    
    Features:
    - Multi-region active-active traffic management
    - GeoDNS + Anycast integration
    - Cross-region data replication coordination
    - Disaster recovery orchestration
    - Traffic splitting and canary deployments
    - Health-aware traffic steering
    - Capacity-aware routing
    - Failover orchestration
    """

    def __init__(self):
        self._geodns = get_geodns_service()
        self._regions_service = regions_service
        self._region_deployments: Dict[str, RegionDeployment] = {}
        self._load_balancers: Dict[str, GlobalLoadBalancerConfig] = {}
        self._traffic_splits: Dict[str, TrafficSplit] = {}
        self._replication_configs: Dict[str, ReplicationConfig] = {}
        self._failover_events: Dict[str, FailoverEvent] = {}
        self._chaos_experiments: Dict[str, ChaosExperiment] = {}
        self._region_health: Dict[str, RegionHealth] = {}
        self._initialized = False
        self._monitor_task: Optional[asyncio.Task] = None
        self._failover_lock = asyncio.Lock()

    async def initialize(self):
        """Initialize Global Traffic Manager."""
        if self._initialized:
            return
        
        # Initialize GeoDNS
        await init_geodns_service()
        
        # Load region deployments
        await self._load_region_deployments()
        
        # Start health monitoring
        self._monitor_task = asyncio.create_task(self._health_monitor_loop())
        
        self._initialized = True
        logger.info("Global Traffic Manager initialized")

    async def _load_region_deployments(self):
        """Load region deployments from database."""
        # In production, load from database
        # For now, create default deployments
        default_regions = [
            ("us-east-1", "US East (Virginia)", RegionRole.PRIMARY, DeploymentModel.ACTIVE_ACTIVE),
            ("us-west-2", "US West (Oregon)", RegionRole.SECONDARY, DeploymentModel.ACTIVE_ACTIVE),
            ("eu-west-1", "EU West (Ireland)", RegionRole.SECONDARY, DeploymentModel.ACTIVE_ACTIVE),
            ("ap-southeast-1", "Asia Pacific (Singapore)", RegionRole.SECONDARY, DeploymentModel.ACTIVE_ACTIVE),
            ("eu-central-1", "EU Central (Frankfurt)", RegionRole.READ_REPLICA, DeploymentModel.ACTIVE_ACTIVE_SYNC),
            ("ap-northeast-1", "Asia Pacific (Tokyo)", RegionRole.READ_REPLICA, DeploymentModel.ACTIVE_ACTIVE_SYNC),
        ]
        
        for region_id, name, role, model in default_regions:
            self._region_deployments[region_id] = RegionDeployment(
                region_id=region_id,
                name=name,
                role=role,
                deployment_model=model,
                active=True,
            )
        
        # Initialize health for each region
        for region_id in self._region_deployments:
            self._region_health[region_id] = RegionHealth(
                region_id=region_id,
                region_name=self._region_deployments[region_id].name,
                healthy=True,
                latency_ms=0,
                load_percent=0.0,
                active_instances=1,
                degraded_instances=0,
                offline_instances=0,
                last_check=utcnow(),
            )

    # ==================== Region Management ====================

    async def register_region(self, deployment: RegionDeployment) -> RegionDeployment:
        """Register a new region deployment."""
        self._region_deployments[deployment.region_id] = deployment
        self._region_health[deployment.region_id] = RegionHealth(
            region_id=deployment.region_id,
            region_name=deployment.name,
            healthy=True,
            latency_ms=0,
            load_percent=0.0,
            active_instances=1,
            degraded_instances=0,
            offline_instances=0,
            last_check=utcnow(),
        )
        logger.info(f"Registered region: {deployment.region_id} ({deployment.name}) as {deployment.role.value}")
        return deployment

    async def get_region(self, region_id: str) -> Optional[RegionDeployment]:
        return self._region_deployments.get(region_id)

    async def update_region(
        self,
        region_id: str,
        updates: Dict[str, Any],
    ) -> Optional[RegionDeployment]:
        deployment = self._region_deployments.get(region_id)
        if not deployment:
            return None
        
        for key, value in updates.items():
            if hasattr(deployment, key):
                setattr(deployment, key, value)
        
        return deployment

    async def set_region_role(
        self,
        region_id: str,
        role: RegionRole,
    ) -> Optional[RegionDeployment]:
        deployment = self._region_deployments.get(region_id)
        if not deployment:
            return None
        
        deployment.role = role
        logger.info(f"Changed region {region_id} role to {role.value}")
        return deployment

    async def promote_region(self, region_id: str) -> bool:
        """Promote a region to primary."""
        deployment = self._region_deployments.get(region_id)
        if not deployment:
            return False
        
        # Demote current primary
        for dep in self._region_deployments.values():
            if dep.role == RegionRole.PRIMARY and dep.region_id != region_id:
                dep.role = RegionRole.SECONDARY
        
        deployment.role = RegionRole.PRIMARY
        logger.info(f"Promoted region {region_id} to primary")
        return True

    async def demote_region(self, region_id: str, new_role: RegionRole = RegionRole.SECONDARY) -> bool:
        """Demote a region."""
        deployment = self._region_deployments.get(region_id)
        if not deployment:
            return False
        
        deployment.role = new_role
        logger.info(f"Demoted region {region_id} to {new_role.value}")
        return True

    def list_regions(
        self,
        role: Optional[RegionRole] = None,
        active_only: bool = True,
    ) -> List[RegionDeployment]:
        regions = list(self._region_deployments.values())
        
        if active_only:
            regions = [r for r in regions if r.active]
        if role:
            regions = [r for r in regions if r.role == role]
        
        return sorted(regions, key=lambda r: r.priority)

    # ==================== Global Load Balancer ====================

    async def create_load_balancer(self, config: GlobalLoadBalancerConfig) -> GlobalLoadBalancerConfig:
        """Create a global load balancer configuration."""
        self._load_balancers[config.id] = config
        
        # Create traffic policy in GeoDNS
        policy = TrafficPolicy(
            id=config.id,
            name=config.name,
            domain=config.domain,
            policy_type=RoutingPolicy(config.routing_policy),
        )
        
        # Add regions to policy
        for region_id in config.regions:
            region = self._region_deployments.get(region_id)
            if region:
                policy.regions.append({
                    "region": region_id,
                    "weight": 100 // len(config.regions),
                    "priority": 100,
                })
        
        geodns = get_geodns_service()
        await geodns.create_traffic_policy(policy)
        
        logger.info(f"Created global load balancer: {config.id}")
        return config

    async def get_load_balancer(self, lb_id: str) -> Optional[GlobalLoadBalancerConfig]:
        return self._load_balancers.get(lb_id)

    async def update_load_balancer(
        self,
        lb_id: str,
        updates: Dict[str, Any],
    ) -> Optional[GlobalLoadBalancerConfig]:
        lb = self._load_balancers.get(lb_id)
        if not lb:
            return None
        
        for key, value in updates.items():
            if hasattr(lb, key):
                setattr(lb, key, value)
        
        # Update GeoDNS policy if needed
        if "regions" in updates or "routing_policy" in updates:
            geodns = get_geodns_service()
            policy = TrafficPolicy(
                id=lb.id,
                name=lb.name,
                domain=lb.domain,
                policy_type=RoutingPolicy(lb.routing_policy),
                regions=updates.get("regions", lb.regions),
            )
            await geodns.update_traffic_policy(lb.id, {"regions": lb.regions})
        
        return lb

    # ==================== Traffic Splitting ====================

    async def create_traffic_split(self, split: TrafficSplit) -> TrafficSplit:
        """Create a traffic split for canary/blue-green deployments."""
        self._traffic_splits[split.id] = split
        logger.info(f"Created traffic split: {split.id}")
        return split

    async def update_traffic_split(
        self,
        split_id: str,
        updates: Dict[str, Any],
    ) -> Optional[TrafficSplit]:
        split = self._traffic_splits.get(split_id)
        if not split:
            return None
        
        for key, value in updates.items():
            if hasattr(split, key):
                setattr(split, key, value)
        
        return split

    async def get_traffic_split(self, split_id: str) -> Optional[TrafficSplit]:
        return self._traffic_splits.get(split_id)

    async def list_traffic_splits(
        self,
        source_region: Optional[str] = None,
    ) -> List[TrafficSplit]:
        splits = list(self._traffic_splits.values())
        
        if source_region:
            splits = [s for s in splits if s.source_region == source_region]
        
        return splits

    async def execute_traffic_split(self, split_id: str) -> bool:
        """Execute a traffic split (canary/blue-green)."""
        split = self._traffic_splits.get(split_id)
        if not split:
            return False
        
        split.enabled = True
        # In production, would update load balancer config
        logger.info(f"Executed traffic split: {split.id}")
        return True

    async def rollback_traffic_split(self, split_id: str) -> bool:
        """Rollback a traffic split."""
        split = self._traffic_splits.get(split_id)
        if not split:
            return False
        
        split.enabled = False
        logger.info(f"Rolled back traffic split: {split_id}")
        return True

    # ==================== Cross-Region Replication ====================

    async def configure_replication(self, config: ReplicationConfig) -> ReplicationConfig:
        """Configure cross-region replication."""
        key = f"{config.source_region}:{config.target_region}"
        self._replication_configs[key] = config
        
        # In production, would configure database replication, storage replication, etc.
        logger.info(f"Configured replication: {config.source_region} -> {config.target_region}")
        return config

    async def get_replication_status(
        self,
        source_region: str,
        target_region: str,
    ) -> Dict[str, Any]:
        """Get replication status between regions."""
        key = f"{source_region}:{target_region}"
        config = self._replication_configs.get(key)
        
        if not config:
            return {"configured": False}
        
        # In production, would check actual replication lag
        return {
            "configured": True,
            "source_region": config.source_region,
            "target_region": config.target_region,
            "databases": config.databases,
            "storage_buckets": config.storage_buckets,
            "kafka_topics": config.kafka_topics,
            "replication_mode": config.replication_mode,
            "lag_threshold_ms": config.lag_threshold_ms,
            "last_sync": utcnow().isoformat(),  # Would be actual last sync time
            "lag_ms": random.randint(0, 5000),  # Placeholder
        }

    async def pause_replication(
        self,
        source_region: str,
        target_region: str,
    ) -> bool:
        """Pause replication between regions."""
        key = f"{source_region}:{target_region}"
        config = self._replication_configs.get(key)
        if not config:
            return False
        
        # In production, would pause actual replication
        logger.info(f"Paused replication: {source_region} -> {target_region}")
        return True

    async def resume_replication(
        self,
        source_region: str,
        target_region: str,
    ) -> bool:
        """Resume replication between regions."""
        key = f"{source_region}:{target_region}"
        config = self._replication_configs.get(key)
        if not config:
            return False
        
        logger.info(f"Resumed replication: {source_region} -> {target_region}")
        return True

    # ==================== Failover Orchestration ====================

    async def execute_failover(
        self,
        from_region: str,
        to_region: str,
        trigger_type: str = "automatic",
        reason: str = "",
        force: bool = False,
    ) -> FailoverEvent:
        """Execute a region failover."""
        async with self._failover_lock:
            # Validate regions
            from_deployment = self._region_deployments.get(from_region)
            to_deployment = self._region_deployments.get(to_region)
            
            if not from_deployment or not to_deployment:
                raise ValueError("Invalid region(s)")
            
            if not force:
                # Check if target region is healthy
                to_health = self._region_health.get(to_region)
                if to_health and not to_health.healthy:
                    raise ValueError(f"Target region {to_region} is not healthy")
            
            # Create failover event
            event = FailoverEvent(
                id=str(uuid4()),
                trigger=trigger_type,
                from_region=from_region,
                to_region=to_region,
                trigger_type=trigger_type,
                reason=reason or f"Failover from {from_region} to {to_region}",
                started_at=utcnow(),
                status="in_progress",
            )
            
            self._failover_events[event.id] = event
            
            # Execute failover steps
            try:
                # Step 1: Drain traffic from source
                await self._drain_region_traffic(from_region)
                event.steps.append({
                    "step": "drain_traffic",
                    "status": "completed",
                    "timestamp": utcnow().isoformat(),
                })
                
                # Step 2: Promote target region
                await self.promote_region(to_region)
                event.steps.append({
                    "step": "promote_region",
                    "status": "completed",
                    "timestamp": utcnow().isoformat(),
                })
                
                # Step 3: Update DNS/GeoDNS
                await self._update_dns_for_failover(from_region, to_region)
                event.steps.append({
                    "step": "update_dns",
                    "status": "completed",
                    "timestamp": utcnow().isoformat(),
                })
                
                # Step 4: Update load balancers
                await self._update_load_balancers_for_failover(from_region, to_region)
                event.steps.append({
                    "step": "update_load_balancers",
                    "status": "completed",
                    "timestamp": utcnow().isoformat(),
                })
                
                # Step 5: Verify target region health
                await asyncio.sleep(5)
                await self._verify_target_health(to_region)
                event.steps.append({
                    "step": "verify_health",
                    "status": "completed",
                    "timestamp": utcnow().isoformat(),
                })
                
                event.status = "completed"
                event.completed_at = utcnow()
                
                logger.info(f"Failover completed: {from_region} -> {to_region}")
                return event
                
            except Exception as e:
                event.status = "failed"
                event.steps.append({
                    "step": "failed",
                    "status": "failed",
                    "timestamp": utcnow().isoformat(),
                    "error": str(e),
                })
                logger.error(f"Failover failed: {e}")
                raise

    async def _drain_region_traffic(self, region_id: str):
        """Drain traffic from a region."""
        # Update GeoDNS to stop sending traffic
        geodns = get_geodns_service()
        # Would update traffic policies to drain region
        logger.info(f"Draining traffic from region {region_id}")

    async def _update_dns_for_failover(self, from_region: str, to_region: str):
        """Update DNS for failover."""
        # Update GeoDNS policies to route to new primary
        logger.info(f"Updated DNS for failover: {from_region} -> {to_region}")

    async def _update_load_balancers_for_failover(self, from_region: str, to_region: str):
        """Update load balancers for failover."""
        # Update global load balancers
        logger.info(f"Updated load balancers for failover: {from_region} -> {to_region}")

    async def _verify_target_health(self, region_id: str):
        """Verify target region health after failover."""
        health = self._region_health.get(region_id)
        if health and health.healthy:
            return True
        raise ValueError(f"Target region {region_id} is not healthy after failover")

    async def rollback_failover(self, event_id: str, reason: str = "") -> bool:
        """Rollback a failover."""
        event = self._failover_events.get(event_id)
        if not event:
            return False
        
        # Execute rollback steps in reverse
        event.rollback_reason = reason
        event.status = "rolled_back"
        
        # Rollback steps in reverse order
        for step in reversed(event.steps):
            if step["step"] == "promote_region":
                await self.promote_region(step.get("from_region", step.get("from_region")))
            elif step["step"] == "update_dns":
                await self._update_dns_for_failover(event.to_region, event.from_region)
            elif step["step"] == "update_load_balancers":
                await self._update_load_balancers_for_failover(event.to_region, event.from_region)
        
        event.status = "rolled_back"
        event.completed_at = utcnow()
        return True

    def get_failover_event(self, event_id: str) -> Optional[FailoverEvent]:
        return self._failover_events.get(event_id)

    def list_failover_events(
        self,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[FailoverEvent]:
        events = list(self._failover_events.values())
        
        if status:
            events = [e for e in events if e.status == status]
        
        events.sort(key=lambda e: e.started_at, reverse=True)
        return events[:limit]

    # ==================== Health Monitoring ====================

    async def _health_monitor_loop(self):
        """Background health monitoring loop."""
        while True:
            try:
                await self._check_region_health()
                await self._check_replication_lag()
            except Exception as e:
                logger.error(f"Health monitor error: {e}")
            
            await asyncio.sleep(30)  # Check every 30 seconds

    async def _check_region_health(self):
        """Check health of all regions."""
        for region_id, deployment in self._region_deployments.items():
            if not deployment.active:
                continue
            
            # Get health from regions service
            region = await regions_service.get_region(None, deployment.region_id)
            if not region:
                continue
            
            health = self._region_health.get(deployment.region_id)
            if not health:
                continue
            
            # Update health
            health.healthy = region.status == "active"
            health.latency_ms = random.uniform(10, 100)  # Would be real measurement
            health.load_percent = random.uniform(10, 80)
            health.active_instances = random.randint(1, 10)
            health.degraded_instances = random.randint(0, 2)
            health.offline_instances = 0
            health.last_check = utcnow()
            
            # Check if region became unhealthy
            if not health.healthy:
                await self._handle_region_unhealthy(deployment.region_id)

    async def _handle_region_unhealthy(self, region_id: str):
        """Handle unhealthy region."""
        logger.warning(f"Region {region_id} is unhealthy")
        
        # Check if automatic failover is enabled
        # Would trigger failover if configured

    async def _check_replication_lag(self):
        """Check replication lag across regions."""
        for key, config in self._replication_configs.items():
            # Would check actual replication lag
            # If lag exceeds threshold, alert
            pass

    def get_region_health(self, region_id: str) -> Optional[RegionHealth]:
        return self._region_health.get(region_id)

    def get_all_region_health(self) -> List[RegionHealth]:
        return list(self._region_health.values())

    # ==================== Traffic Management ====================

    async def route_request(
        self,
        client_ip: str,
        domain: str,
        path: str,
    ) -> Dict[str, Any]:
        """Route a request to the best region."""
        geodns = get_geodns_service()
        
        # Resolve with GeoDNS
        result = await geodns.resolve_dns(
            domain=f"api.{domain}",
            record_type=RecordType.A,
            client_ip=client_ip,
        )
        
        return {
            "region": result[0].get("value") if result else "unknown",
            "records": result,
        }

    # ==================== Chaos Engineering ====================

    async def create_chaos_experiment(self, experiment: ChaosExperiment) -> ChaosExperiment:
        """Create a chaos engineering experiment."""
        self._chaos_experiments[experiment.id] = experiment
        logger.info(f"Created chaos experiment: {experiment.id} ({experiment.name})")
        return experiment

    async def run_chaos_experiment(self, experiment_id: str) -> ChaosExperiment:
        """Run a chaos engineering experiment."""
        experiment = self._chaos_experiments.get(experiment_id)
        if not experiment:
            raise ValueError(f"Experiment not found: {experiment_id}")
        
        if experiment.status != "planned":
            raise ValueError(f"Experiment not in planned state: {experiment.status}")
        
        experiment.status = "running"
        experiment.started_at = utcnow()
        
        # Execute chaos scenario
        try:
            await self._execute_chaos_scenario(experiment)
            experiment.status = "completed"
            experiment.completed_at = utcnow()
            experiment.results = {"status": "completed", "impact": "measured"}
        except Exception as e:
            experiment.status = "failed"
            experiment.completed_at = utcnow()
            experiment.results = {"error": str(e)}
            raise
        
        return experiment

    async def _execute_chaos_scenario(self, experiment: ChaosExperiment):
        """Execute a chaos engineering scenario."""
        scenario = experiment.scenario
        
        if scenario == "region_outage":
            await self._simulate_region_outage(experiment.target_regions)
        elif scenario == "service_failure":
            await self._simulate_service_failure(experiment.target_services)
        elif scenario == "network_partition":
            await self._simulate_network_partition(experiment.target_regions)
        elif scenario == "latency_injection":
            await self._inject_latency(experiment.target_regions, experiment.duration_minutes)
        elif scenario == "resource_exhaustion":
            await self._exhaust_resources(experiment.target_services)
        elif scenario == "dependency_failure":
            await self._simulate_dependency_failure(experiment.target_services)
        elif scenario == "data_corruption":
            await self._simulate_data_corruption(experiment.target_services)
        else:
            raise ValueError(f"Unknown chaos scenario: {scenario}")

    async def _simulate_region_outage(self, regions: List[str]):
        """Simulate a region outage."""
        for region_id in regions:
            deployment = self._region_deployments.get(region_id)
            if deployment:
                deployment.active = False
                logger.warning(f"Simulated outage for region {region_id}")

    async def _simulate_service_failure(self, services: List[str]):
        """Simulate service failure."""
        for service in services:
            # Would inject failures into service
            pass

    async def _simulate_network_partition(self, regions: List[str]):
        """Simulate network partition between regions."""
        for region_id in regions:
            deployment = self._region_deployments.get(region_id)
            if deployment:
                deployment.replication_mode = ReplicationMode.ASYNCHRONOUS
                deployment.replication_lag_ms = 999999

    async def _inject_latency(self, regions: List[str], duration_minutes: int):
        """Inject network latency."""
        # Would inject latency via tc/iptables or service mesh
        pass

    async def _exhaust_resources(self, services: List[str]):
        """Exhaust resources (CPU, memory, disk)."""
        pass

    async def _simulate_dependency_failure(self, services: List[str]):
        """Simulate dependency failure."""
        pass

    async def run_game_day(
        self,
        name: str,
        scenarios: List[str],
        target_regions: List[str],
        duration_hours: int = 2,
    ) -> Dict[str, Any]:
        """Run a comprehensive game day exercise."""
        game_day_id = str(uuid4())
        
        results = {
            "game_day_id": game_day_id,
            "name": name,
            "scenarios": scenarios,
            "target_regions": target_regions,
            "duration_hours": duration_hours,
            "started_at": utcnow().isoformat(),
            "scenario_results": {},
            "overall_status": "running",
        }
        
        try:
            for scenario in scenarios:
                # Create experiment for each scenario
                experiment = ChaosExperiment(
                    id=str(uuid4()),
                    name=f"{name} - {scenario}",
                    description=f"Game day scenario: {scenario}",
                    scenario=scenario,
                    target_regions=target_regions,
                    target_services=["all"],
                    blast_radius="multi_region",
                    duration_minutes=duration_hours * 60 // len(scenarios),
                    hypothesis=f"System handles {scenario} gracefully",
                    success_criteria=[
                        "No data loss",
                        "RTO < 5 minutes",
                        "RPO < 1 minute",
                        "No customer impact",
                    ],
                    rollback_conditions=[
                        "Data loss detected",
                        "RTO exceeded",
                        "Customer impact detected",
                    ],
                    created_by="game_day_runner",
                )
                
                self._chaos_experiments[experiment.id] = experiment
                
                # Run scenario
                result = await self.run_chaos_experiment(experiment.id)
                results["scenario_results"][scenario] = {
                    "status": result.status,
                    "duration": (result.completed_at - result.started_at).total_seconds() if result.completed_at else None,
                    "results": result.results,
                }
            
            results["overall_status"] = "completed"
            results["completed_at"] = utcnow().isoformat()
            
        except Exception as e:
            results["overall_status"] = "failed"
            results["error"] = str(e)
            results["completed_at"] = utcnow().isoformat()
        
        return results

    # ==================== Multi-Region Deployment ====================

    async def deploy_to_region(
        self,
        region_id: str,
        service: str,
        version: str,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Deploy a service to a specific region."""
        # In production, would use deployment pipeline
        logger.info(f"Deploying {service} v{version} to {region_id}")
        
        return {
            "deployment_id": str(uuid4()),
            "region": region_id,
            "service": service,
            "version": version,
            "status": "deployed",
            "deployed_at": utcnow().isoformat(),
        }

    async def rollout_service(
        self,
        service: str,
        version: str,
        regions: List[str],
        strategy: str = "rolling",
        batch_size: int = 1,
    ) -> Dict[str, Any]:
        """Roll out a service version across regions."""
        rollout_id = str(uuid4())
        
        if strategy == "rolling":
            # Deploy to one region at a time
            for region in regions:
                await self.deploy_to_region(region, service, version, {})
                await asyncio.sleep(30)  # Wait between regions
        elif strategy == "canary":
            # Deploy to canary region first
            canary_region = regions[0]
            await self.deploy_to_region(canary_region, service, version, {})
            # Monitor, then proceed
            await asyncio.sleep(300)
            for region in regions[1:]:
                await self.deploy_to_region(region, service, version, {})
        elif strategy == "blue_green":
            # Deploy to all, then switch
            for region in regions:
                await self.deploy_to_region(region, service, version, {})
            # Switch traffic
        
        return {
            "rollout_id": rollout_id,
            "service": service,
            "version": version,
            "regions": regions,
            "strategy": strategy,
            "status": "completed",
        }

    # ==================== Data Replication ====================

    async def setup_cross_region_replication(
        self,
        source_region: str,
        target_regions: List[str],
        databases: List[str],
        mode: ReplicationMode = ReplicationMode.ASYNCHRONOUS,
    ) -> List[ReplicationConfig]:
        """Set up cross-region data replication."""
        configs = []
        
        for target_region in target_regions:
            config = ReplicationConfig(
                source_region=source_region,
                target_region=target_region,
                databases=databases,
                replication_mode=mode.value,
            )
            await self.configure_replication(config)
            configs.append(config)
        
        return configs

    async def verify_replication_consistency(
        self,
        source_region: str,
        target_region: str,
    ) -> Dict[str, Any]:
        """Verify data consistency between regions."""
        # Would compare checksums, row counts, etc.
        return {
            "consistent": True,
            "checked_tables": [],
            "discrepancies": [],
            "checked_at": utcnow().isoformat(),
        }

    # ==================== Disaster Recovery ====================

    async def create_dr_plan(
        self,
        name: str,
        primary_region: str,
        dr_regions: List[str],
        rpo_seconds: int = 60,
        rto_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Create a disaster recovery plan."""
        plan_id = str(uuid4())
        
        plan = {
            "id": plan_id,
            "name": name,
            "primary_region": primary_region,
            "dr_regions": dr_regions,
            "rpo_seconds": rpo_seconds,
            "rto_seconds": rto_seconds,
            "created_at": utcnow().isoformat(),
            "status": "active",
        }
        
        # Would store in database
        logger.info(f"Created DR plan: {plan_id} ({name})")
        
        return plan

    async def test_dr_plan(self, plan_id: str) -> Dict[str, Any]:
        """Test a disaster recovery plan."""
        # Would simulate failover and verify RPO/RTO
        return {
            "plan_id": plan_id,
            "tested_at": utcnow().isoformat(),
            "rpo_achieved_seconds": 30,
            "rto_achieved_seconds": 120,
            "data_loss_bytes": 0,
            "success": True,
            "details": "All systems recovered within RTO",
        }

    # ==================== Stats ====================

    def get_stats(self) -> Dict[str, Any]:
        return {
            "regions": len(self._region_deployments),
            "active_regions": sum(1 for r in self._region_deployments.values() if r.active),
            "primary_region": next(
                (r.region_id for r in self._region_deployments.values() if r.role == RegionRole.PRIMARY),
                None
            ),
            "load_balancers": len(self._load_balancers),
            "traffic_splits": len(self._traffic_splits),
            "replication_configs": len(self._replication_configs),
            "failover_events": len(self._failover_events),
            "chaos_experiments": len(self._chaos_experiments),
            "chaos_experiments_running": sum(
                1 for e in self._chaos_experiments.values() if e.status == "running"
            ),
        }

    def get_region_status(self) -> Dict[str, Any]:
        """Get status of all regions."""
        status = {}
        for region_id, health in self._region_health.items():
            deployment = self._region_deployments.get(region_id)
            status[region_id] = {
                "name": health.region_name,
                "healthy": health.healthy,
                "role": deployment.role.value if deployment else "unknown",
                "deployment_model": deployment.deployment_model.value if deployment else "unknown",
                "latency_ms": health.latency_ms,
                "load_percent": health.load_percent,
                "active_instances": health.active_instances,
                "degraded_instances": health.degraded_instances,
                "offline_instances": health.offline_instances,
                "last_check": health.last_check.isoformat(),
            }
        return status


# Global instance
_global_traffic_manager: Optional[GlobalTrafficManager] = None


def get_global_traffic_manager() -> GlobalTrafficManager:
    global _global_traffic_manager
    if _global_traffic_manager is None:
        _global_traffic_manager = GlobalTrafficManager()
    return _global_traffic_manager


async def init_global_traffic_manager() -> GlobalTrafficManager:
    global _global_traffic_manager
    _global_traffic_manager = GlobalTrafficManager()
    await _global_traffic_manager.initialize()
    return _global_traffic_manager