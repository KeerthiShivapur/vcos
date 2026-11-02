"""
Predictive Scaling & Cost Optimization for VCOS.

Provides:
- ML-based workload prediction
- Predictive autoscaling policies
- Cost optimization recommendations
- Capacity planning
- Anomaly detection for cost anomalies
- Resource utilization forecasting
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

import numpy as np

from app.core.config import settings
from app.core.timeutils import utcnow

logger = logging.getLogger(__name__)


class ScalingDirection(str, Enum):
    """Scaling directions."""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class ScalingTrigger(str, Enum):
    """Scaling trigger types."""
    METRIC_THRESHOLD = "metric_threshold"
    SCHEDULE = "schedule"
    PREDICTIVE = "predictive"
    MANUAL = "manual"
    ANOMALY = "anomaly"


class ResourceType(str, Enum):
    """Resource types for scaling."""
    CPU = "cpu"
    MEMORY = "memory"
    STORAGE = "storage"
    NETWORK = "network"
    PODS = "pods"
    WORKERS = "workers"
    DATABASE_CONNECTIONS = "db_connections"
    CACHE = "cache"


class CostCategory(str, Enum):
    """Cost categories."""
    COMPUTE = "compute"
    STORAGE = "storage"
    NETWORK = "network"
    DATABASE = "database"
    CACHE = "cache"
    CDN = "cdn"
    MONITORING = "monitoring"
    BACKUP = "backup"
    LICENSING = "licensing"


class OptimizationAction(str, Enum):
    """Cost optimization actions."""
    RIGHTSIZE = "rightsize"
    DOWNGRADE = "downgrade"
    UPGRADE = "upgrade"
    TERMINATE = "terminate"
    SCHEDULE = "schedule"
    RESERVE = "reserve"
    SPOT = "spot"
    SAVINGS_PLAN = "savings_plan"
    AUTO_SCALING = "auto_scaling"


@dataclass
class MetricDataPoint:
    """Single metric data point."""
    timestamp: datetime
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class ScalingMetric:
    """Scaling metric configuration."""
    name: str
    resource_type: ResourceType
    query: str  # PromQL query
    scale_up_threshold: float
    scale_down_threshold: float
    evaluation_window: str = "5m"
    cooldown_period: str = "5m"
    min_replicas: int = 1
    max_replicas: int = 100
    stabilization_window: str = "5m"


@dataclass
class ScalingPolicy:
    """Scaling policy configuration."""
    id: str
    name: str
    resource_type: ResourceType
    namespace: str
    workload: str  # Deployment/StatefulSet name
    metrics: List[ScalingMetric] = field(default_factory=list)
    min_replicas: int = 1
    max_replicas: int = 100
    scale_up_cooldown: str = "5m"
    scale_down_cooldown: str = "5m"
    stabilization_window: str = "5m"
    enabled: bool = True
    predictive_enabled: bool = False
    prediction_horizon: str = "1h"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScalingEvent:
    """Scaling event record."""
    id: str
    policy_id: str
    timestamp: datetime
    direction: ScalingDirection
    trigger: ScalingTrigger
    previous_replicas: int
    new_replicas: int
    trigger_metric: str
    trigger_value: float
    threshold: float
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PredictionResult:
    """Prediction result."""
    metric_name: str
    predicted_values: List[Tuple[datetime, float]]
    confidence_intervals: List[Tuple[float, float]]
    model_name: str
    confidence_score: float
    prediction_horizon: str
    generated_at: datetime


@dataclass
class CostAnomaly:
    """Cost anomaly detection result."""
    id: str
    category: CostCategory
    detected_at: datetime
    expected_cost: float
    actual_cost: float
    deviation_percent: float
    severity: str  # low, medium, high, critical
    affected_resources: List[str]
    description: str
    root_cause_hypothesis: Optional[str] = None
    recommended_actions: List[str] = field(default_factory=list)


@dataclass
class OptimizationRecommendation:
    """Cost optimization recommendation."""
    id: str
    action: OptimizationAction
    category: CostCategory
    resource_id: str
    resource_name: str
    current_cost: float
    estimated_savings: float
    savings_percent: float
    confidence: float
    effort_level: str  # low, medium, high
    risk_level: str  # low, medium, high
    description: str
    implementation_steps: List[str] = field(default_factory=list)
    prerequisites: List[str] = field(default_factory=list)
    risks: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.utcnow)
    status: str = "pending"  # pending, approved, rejected, implemented, dismissed


@dataclass
class CapacityForecast:
    """Capacity forecast result."""
    resource_type: ResourceType
    current_usage: float
    predicted_usage: List[Tuple[datetime, float]]
    capacity_limit: float
    time_to_capacity: Optional[timedelta]
    recommended_action: str
    confidence: float


@dataclass
class CostReport:
    """Cost analysis report."""
    period_start: datetime
    period_end: datetime
    total_cost: float
    cost_by_category: Dict[CostCategory, float]
    cost_by_resource: Dict[str, float]
    cost_trend: List[Tuple[datetime, float]]
    anomalies: List[CostAnomaly]
    recommendations: List[OptimizationRecommendation]
    potential_savings: float
    generated_at: datetime = field(default_factory=datetime.utcnow)


class PredictiveScaler:
    """
    Predictive autoscaling with ML-based forecasting.
    
    Features:
    - Time series forecasting for resource metrics
    - Multi-metric scaling decisions
    - Predictive scaling with configurable horizons
    - Anomaly detection for scaling events
    - Integration with Kubernetes HPA/VPA
    """

    def __init__(self):
        self._policies: Dict[str, ScalingPolicy] = {}
        self._metrics_history: Dict[str, List[MetricDataPoint]] = {}
        self._scaling_events: List[ScalingEvent] = []
        self._predictions: Dict[str, PredictionResult] = {}
        self._models: Dict[str, Any] = {}  # Placeholder for ML models
        self._initialized = False

    async def initialize(self):
        """Initialize predictive scaler."""
        if self._initialized:
            return
        
        # Load policies from database
        await self._load_policies()
        
        # Initialize ML models (placeholder)
        await self._init_models()
        
        # Start background prediction loop
        asyncio.create_task(self._prediction_loop())
        asyncio.create_task(self._evaluation_loop())
        
        self._initialized = True
        logger.info("PredictiveScaler initialized")

    async def _load_policies(self):
        """Load scaling policies from database."""
        # Placeholder - would load from database
        pass

    async def _init_models(self):
        """Initialize ML models for prediction."""
        # In production, load trained models
        # For now, use simple statistical models
        self._models = {
            "arima": "placeholder",
            "prophet": "placeholder",
            "lstm": "placeholder",
            "linear": "linear_regression",
        }

    async def register_policy(self, policy: ScalingPolicy) -> str:
        """Register a new scaling policy."""
        self._policies[policy.id] = policy
        logger.info(f"Registered scaling policy: {policy.id} ({policy.name})")
        return policy.id

    async def get_policy(self, policy_id: str) -> Optional[ScalingPolicy]:
        """Get scaling policy by ID."""
        return self._policies.get(policy_id)

    async def update_policy(self, policy_id: str, updates: Dict[str, Any]) -> Optional[ScalingPolicy]:
        """Update scaling policy."""
        policy = self._policies.get(policy_id)
        if not policy:
            return None
        
        for key, value in updates.items():
            if hasattr(policy, key):
                setattr(policy, key, value)
        
        policy.updated_at = utcnow()
        return policy

    async def delete_policy(self, policy_id: str) -> bool:
        """Delete scaling policy."""
        if policy_id in self._policies:
            del self._policies[policy_id]
            return True
        return False

    async def list_policies(
        self,
        namespace: Optional[str] = None,
        workload: Optional[str] = None,
        enabled_only: bool = True,
    ) -> List[ScalingPolicy]:
        """List scaling policies."""
        policies = list(self._policies.values())
        
        if namespace:
            policies = [p for p in policies if p.namespace == namespace]
        if workload:
            policies = [p for p in policies if p.workload == workload]
        if enabled_only:
            policies = [p for p in policies if p.enabled]
        
        return policies

    # ==================== Metrics Collection ====================

    async def record_metric(
        self,
        metric_name: str,
        value: float,
        timestamp: Optional[datetime] = None,
        labels: Optional[Dict[str, str]] = None,
    ):
        """Record a metric data point."""
        timestamp = timestamp or utcnow()
        labels = labels or {}
        
        key = f"{metric_name}:{json.dumps(labels, sort_keys=True)}"
        
        if key not in self._metrics_history:
            self._metrics_history[key] = []
        
        self._metrics_history[key].append(MetricDataPoint(
            timestamp=timestamp,
            value=value,
            labels=labels,
        ))
        
        # Trim history (keep last 30 days)
        cutoff = utcnow() - timedelta(days=30)
        self._metrics_history[key] = [
            p for p in self._metrics_history[key]
            if p.timestamp >= cutoff
        ]

    async def get_metric_history(
        self,
        metric_name: str,
        labels: Optional[Dict[str, str]] = None,
        hours: int = 24,
    ) -> List[MetricDataPoint]:
        """Get metric history."""
        key = f"{metric_name}:{json.dumps(labels or {}, sort_keys=True)}"
        
        if key not in self._metrics_history:
            return []
        
        cutoff = utcnow() - timedelta(hours=hours)
        return [
            p for p in self._metrics_history[key]
            if p.timestamp >= cutoff
        ]

    # ==================== Prediction Engine ====================

    async def predict_metric(
        self,
        metric_name: str,
        labels: Optional[Dict[str, str]] = None,
        horizon: str = "1h",
        model: str = "linear",
    ) -> PredictionResult:
        """Predict future metric values."""
        history = await self.get_metric_history(metric_name, labels=None, hours=24)
        
        if len(history) < 10:
            raise ValueError(f"Insufficient data for prediction: {len(history)} points")
        
        # Simple linear regression prediction (placeholder for ML models)
        predicted = self._linear_predict(history, horizon)
        
        result = PredictionResult(
            metric_name=metric_name,
            predicted_values=predicted,
            confidence_intervals=self._calculate_confidence_intervals(history, predicted),
            model_name=model,
            confidence_score=0.85,  # Placeholder
            prediction_horizon=horizon,
            generated_at=utcnow(),
        )
        
        self._predictions[metric_name] = result
        return result

    def _linear_predict(
        self,
        history: List[MetricDataPoint],
        horizon: str,
    ) -> List[Tuple[datetime, float]]:
        """Simple linear regression prediction."""
        if len(history) < 2:
            return [(utcnow() + timedelta(hours=1), history[-1].value)] if history else []
        
        # Parse horizon
        horizon_map = {
            "15m": timedelta(minutes=15),
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "12h": timedelta(hours=12),
            "1d": timedelta(days=1),
            "7d": timedelta(days=7),
        }
        
        horizon_delta = horizon_map.get(horizon, timedelta(hours=1))
        steps = int(horizon_delta.total_seconds() / 300)  # 5-minute steps
        
        # Simple linear regression
        x = np.arange(len(history))
        y = np.array([p.value for p in history])
        
        if len(x) > 1:
            slope, intercept = np.polyfit(x, y, 1)
        else:
            slope, intercept = 0, y[0]
        
        predictions = []
        last_time = history[-1].timestamp
        
        for i in range(1, steps + 1):
            next_x = len(history) + i - 1
            pred_value = max(0, slope * next_x + intercept)  # No negative values
            pred_time = history[-1].timestamp + timedelta(minutes=5 * i)
            predictions.append((pred_time, pred_value))
        
        return predictions

    def _calculate_confidence_intervals(
        self,
        history: List[MetricDataPoint],
        predicted: List[Tuple[datetime, float]],
    ) -> List[Tuple[float, float]]:
        """Calculate confidence intervals for predictions."""
        if len(history) < 2:
            return [(p[1] * 0.9, p[1] * 1.1) for p in predicted]
        
        values = np.array([p.value for p in history])
        std = np.std(values)
        
        intervals = []
        for _, pred in predicted:
            margin = 1.96 * std  # 95% confidence
            intervals.append((max(0, pred - margin), pred + margin))
        
        return intervals

    # ==================== Scaling Evaluation ====================

    async def evaluate_scaling(self, policy_id: str) -> List[ScalingEvent]:
        """Evaluate scaling policies and trigger scaling if needed."""
        policy = self._policies.get(policy_id)
        if not policy or not policy.enabled:
            return []
        
        events = []
        
        for metric in policy.metrics:
            history = await self.get_metric_history(
                metric.name,
                labels=metric.labels,
                hours=1,
            )
            
            if not history:
                continue
            
            current_value = history[-1].value
            
            # Check scale up
            if current_value >= metric.scale_up_threshold:
                event = await self._trigger_scale_up(policy, metric, current_value)
                if event:
                    events.append(event)
            
            # Check scale down
            elif current_value <= metric.scale_down_threshold:
                event = await self._trigger_scale_down(policy, metric, current_value)
                if event:
                    events.append(event)
        
        return events

    async def _trigger_scale_up(
        self,
        policy: ScalingPolicy,
        metric: ScalingMetric,
        current_value: float,
    ) -> Optional[ScalingEvent]:
        """Trigger scale up event."""
        # Check cooldown
        recent_scale_up = [
            e for e in self._scaling_events
            if e.policy_id == policy.id and e.direction == ScalingDirection.UP
            and (utcnow() - e.timestamp).total_seconds() < 300  # 5 min cooldown
        ]
        
        if recent_scale_up:
            return None
        
        # Calculate new replica count (simplified)
        current_replicas = 1  # Would get from Kubernetes API
        new_replicas = min(policy.max_replicas, current_replicas + 1)
        
        if new_replicas <= current_replicas:
            return None
        
        event = ScalingEvent(
            id=str(uuid4()),
            policy_id=policy.id,
            timestamp=utcnow(),
            direction=ScalingDirection.UP,
            trigger=ScalingTrigger.METRIC_THRESHOLD,
            previous_replicas=current_replicas,
            new_replicas=new_replicas,
            trigger_metric=metric.name,
            trigger_value=current_value,
            threshold=metric.scale_up_threshold,
        )
        
        self._scaling_events.append(event)
        return event

    async def _trigger_scale_down(
        self,
        policy: ScalingPolicy,
        metric: ScalingMetric,
        current_value: float,
    ) -> Optional[ScalingEvent]:
        """Trigger scale down event."""
        # Check cooldown
        recent_scale_down = [
            e for e in self._scaling_events
            if e.policy_id == metric.name and e.direction == ScalingDirection.DOWN
            and (utcnow() - e.timestamp).total_seconds() < 300  # 5 min cooldown
        ]
        
        if recent_scale_down:
            return None
        
        current_replicas = 1  # Would get from Kubernetes API
        new_replicas = max(policy.min_replicas, current_replicas - 1)
        
        if new_replicas >= current_replicas:
            return None
        
        event = ScalingEvent(
            id=str(uuid4()),
            policy_id=metric.name,  # Using metric name as policy reference
            timestamp=utcnow(),
            direction=ScalingDirection.DOWN,
            trigger=ScalingTrigger.METRIC_THRESHOLD,
            previous_replicas=current_replicas,
            new_replicas=new_replicas,
            trigger_metric=metric.name,
            trigger_value=current_value,
            threshold=metric.scale_down_threshold,
        )
        
        self._scaling_events.append(event)
        return event

    # ==================== Predictive Scaling ====================

    async def evaluate_predictive_scaling(self, policy_id: str) -> List[ScalingEvent]:
        """Evaluate predictive scaling for a policy."""
        policy = self._policies.get(policy_id)
        if not policy or not policy.enabled or not policy.predictive_enabled:
            return []
        
        events = []
        
        for metric in policy.metrics:
            try:
                prediction = await self.predict_metric(
                    metric.name,
                    labels=metric.labels,
                    horizon=policy.prediction_horizon,
                )
                
                # Check if predicted values will cross thresholds
                for pred_time, pred_value in prediction.predicted_values:
                    if pred_value >= metric.scale_up_threshold:
                        event = ScalingEvent(
                            id=str(uuid4()),
                            policy_id=policy.id,
                            timestamp=utcnow(),
                            direction=ScalingDirection.UP,
                            trigger=ScalingTrigger.PREDICTIVE,
                            previous_replicas=1,
                            new_replicas=min(policy.max_replicas, 2),
                            trigger_metric=metric.name,
                            trigger_value=pred_value,
                            threshold=metric.scale_up_threshold,
                            metadata={
                                "prediction_time": prediction.generated_at.isoformat(),
                                "prediction_horizon": policy.prediction_horizon,
                                "confidence": prediction.confidence_score,
                            },
                        )
                        self._scaling_events.append(event)
                        break  # Only trigger once per evaluation
                    
                    elif self._should_scale_down_predictive(metric, prediction):
                        # Similar for scale down
                        pass
                        
            except Exception as e:
                logger.error(f"Predictive scaling failed for {metric.name}: {e}")
        
        return events

    def _should_scale_down_predictive(
        self,
        metric: ScalingMetric,
        prediction: PredictionResult,
    ) -> bool:
        """Check if predictive scale down is warranted."""
        # Check if all predicted values are below scale down threshold
        for _, pred_value in prediction.predicted_values:
            if pred_value > metric.scale_down_threshold:
                return False
        return True

    # ==================== Background Loops ====================

    async def _prediction_loop(self):
        """Background prediction loop."""
        while True:
            try:
                for policy in self._policies.values():
                    if policy.enabled and policy.predictive_enabled:
                        await self.evaluate_predictive_scaling(policy.id)
            except Exception as e:
                logger.error(f"Prediction loop error: {e}")
            
            await asyncio.sleep(300)  # Every 5 minutes

    async def _evaluation_loop(self):
        """Background evaluation loop for threshold-based scaling."""
        while True:
            try:
                for policy in self._policies.values():
                    if policy.enabled:
                        await self.evaluate_scaling(policy.id)
            except Exception as e:
                logger.error(f"Evaluation loop error: {e}")
            
            await asyncio.sleep(60)  # Every minute

    # ==================== Scaling History ====================

    def get_scaling_history(
        self,
        policy_id: Optional[str] = None,
        hours: int = 24,
    ) -> List[ScalingEvent]:
        """Get scaling event history."""
        cutoff = utcnow() - timedelta(hours=hours)
        
        events = [
            e for e in self._scaling_events
            if e.timestamp >= cutoff
        ]
        
        if policy_id:
            events = [e for e in events if e.policy_id == policy_id]
        
        return sorted(events, key=lambda e: e.timestamp, reverse=True)

    def get_scaling_stats(self, policy_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get scaling statistics."""
        events = self.get_scaling_history(policy_id, hours)
        
        scale_up = len([e for e in events if e.direction == ScalingDirection.UP])
        scale_down = len([e for e in events if e.direction == ScalingDirection.DOWN])
        predictive = len([e for e in events if e.trigger == ScalingTrigger.PREDICTIVE])
        
        return {
            "total_events": len(events),
            "scale_up": scale_up,
            "scale_down": scale_down,
            "predictive": predictive,
            "reactive": len(events) - predictive,
            "last_event": events[0].timestamp.isoformat() if events else None,
        }


class CostOptimizer:
    """
    Cost optimization engine.
    
    Features:
    - Cost anomaly detection
    - Rightsizing recommendations
    - Reserved instance / Savings Plan recommendations
    - Spot instance recommendations
    - Idle resource detection
    - Cost anomaly detection
    """

    def __init__(self):
        self._cost_history: List[Dict] = []
        self._anomalies: List[CostAnomaly] = []
        self._recommendations: Dict[str, OptimizationRecommendation] = {}
        self._cost_data: Dict[str, List[Dict]] = {}  # category -> cost data points
        self._initialized = False

    async def initialize(self):
        """Initialize cost optimizer."""
        if self._initialized:
            return
        
        await self._load_cost_data()
        await self._load_recommendations()
        
        # Start background analysis
        asyncio.create_task(self._anomaly_detection_loop())
        asyncio.create_task(self._recommendation_generation_loop())
        asyncio.create_task(self._cost_analysis_loop())
        
        self._initialized = True
        logger.info("CostOptimizer initialized")

    async def _load_recommendations(self):
        """Load saved recommendations from storage."""
        # Placeholder - would load from database
        pass

    async def _load_cost_data(self):
        """Load cost data from billing systems."""
        # Placeholder - would integrate with AWS Cost Explorer, GCP Billing, Azure Cost Management
        pass

    async def record_cost(
        self,
        category: CostCategory,
        resource_id: str,
        resource_name: str,
        cost: float,
        timestamp: Optional[datetime] = None,
        metadata: Optional[Dict] = None,
    ):
        """Record a cost data point."""
        timestamp = timestamp or utcnow()
        
        category_key = category.value
        if category_key not in self._cost_data:
            self._cost_data[category_key] = []
        
        self._cost_data[category_key].append({
            "timestamp": timestamp,
            "resource_id": resource_id,
            "resource_name": resource_name,
            "cost": cost,
            "metadata": metadata or {},
        })
        
        # Trim old data (keep 90 days)
        cutoff = utcnow() - timedelta(days=90)
        self._cost_data[category_key] = [
            d for d in self._cost_data[category_key]
            if d["timestamp"] >= cutoff
        ]

    async def record_cost_batch(self, costs: List[Dict]):
        """Record multiple cost data points."""
        for cost in costs:
            await self.record_cost(
                category=CostCategory(cost["category"]),
                resource_id=cost["resource_id"],
                resource_name=cost["resource_name"],
                cost=cost["cost"],
                timestamp=cost.get("timestamp"),
                metadata=cost.get("metadata"),
            )

    # ==================== Anomaly Detection ====================

    async def detect_anomalies(
        self,
        category: Optional[CostCategory] = None,
        sensitivity: float = 2.0,  # Standard deviations
    ) -> List[CostAnomaly]:
        """Detect cost anomalies using statistical methods."""
        anomalies = []
        
        categories = [category] if category else list(CostCategory)
        
        for cat in categories:
            cat_key = cat.value if isinstance(cat, CostCategory) else cat
            data = self._cost_data.get(cat_key, [])
            
            if len(data) < 7:  # Need at least a week of data
                continue
            
            # Group by resource
            by_resource: Dict[str, List[Dict]] = {}
            for d in data:
                rid = d["resource_id"]
                if rid not in by_resource:
                    by_resource[rid] = []
                by_resource[rid].append(d)
            
            for resource_id, points in by_resource.items():
                if len(points) < 7:
                    continue
                
                # Calculate daily costs
                daily_costs = {}
                for p in points:
                    day = p["timestamp"].date()
                    if day not in daily_costs:
                        daily_costs[day] = 0
                    daily_costs[day] += p["cost"]
                
                if len(daily_costs) < 3:
                    continue
                
                costs = list(daily_costs.values())
                mean_cost = np.mean(costs[:-1])  # Exclude today
                std_cost = np.std(costs[:-1])
                
                if std_cost == 0:
                    continue
                
                today_cost = costs[-1]
                z_score = abs(today_cost - mean_cost) / std_cost
                
                if z_score >= sensitivity:
                    severity = self._calculate_severity(z_score)
                    
                    anomaly = CostAnomaly(
                        id=str(uuid4()),
                        category=CostCategory(cat),
                        detected_at=utcnow(),
                        expected_cost=mean_cost,
                        actual_cost=today_cost,
                        deviation_percent=((today_cost - mean_cost) / mean_cost * 100) if mean_cost > 0 else 0,
                        severity=severity,
                        affected_resources=[points[-1]["resource_id"]],
                        description=f"Cost anomaly detected: {today_cost:.2f} vs expected {mean_cost:.2f} ({z_score:.1f}σ)",
                        recommended_actions=self._get_anomaly_actions(z_score),
                    )
                    
                    anomalies.append(anomaly)
                    self._anomalies.append(anomaly)
        
        return anomalies

    def _calculate_severity(self, z_score: float) -> str:
        if z_score >= 5:
            return "critical"
        elif z_score >= 3:
            return "high"
        elif z_score >= 2.5:
            return "medium"
        return "low"

    def _get_anomaly_actions(self, z_score: float) -> List[str]:
        if z_score >= 5:
            return ["Investigate immediately", "Check for runaway processes", "Review recent deployments"]
        elif z_score >= 3:
            return ["Investigate within 1 hour", "Check for unusual traffic patterns"]
        return ["Monitor closely", "Review next billing cycle"]

    # ==================== Recommendation Generation ====================

    async def generate_recommendations(self) -> List[OptimizationRecommendation]:
        """Generate cost optimization recommendations."""
        recommendations = []
        
        # Rightsizing recommendations
        recommendations.extend(await self._generate_rightsizing_recommendations())
        
        # Idle resource recommendations
        recommendations.extend(await self._generate_idle_recommendations())
        
        # Reserved instance / Savings Plan recommendations
        recommendations.extend(await self._generate_commitment_recommendations())
        
        # Spot instance recommendations
        recommendations.extend(await self._generate_spot_recommendations())
        
        # Store recommendations
        for rec in recommendations:
            self._recommendations[rec.id] = rec
        
        return recommendations

    async def _generate_rightsizing_recommendations(self) -> List[OptimizationRecommendation]:
        """Generate rightsizing recommendations."""
        recommendations = []
        
        # Would analyze CPU/Memory utilization vs allocated
        # For now, return sample recommendations
        
        recommendations.append(OptimizationRecommendation(
            id=str(uuid4()),
            action=OptimizationAction.RIGHTSIZE,
            category=CostCategory.COMPUTE,
            resource_id="i-1234567890abcdef0",
            resource_name="web-server-prod-1",
            current_cost=245.00,
            estimated_savings=73.50,
            savings_percent=30.0,
            confidence=0.85,
            effort_level="low",
            risk_level="low",
            description="CPU utilization averaging 15% over 14 days. Recommend downsizing from c5.xlarge to c5.large.",
            implementation_steps=[
                "Create AMI of current instance",
                "Launch new c5.large instance from AMI",
                "Update target group/load balancer",
                "Validate application health",
                "Terminate old instance",
            ],
            prerequisites=["AMI creation permissions", "Load balancer configuration access"],
            risks=["Brief downtime during swap", "Potential capacity reduction"],
        ))
        
        return [rec for rec in recommendations if rec.savings_percent > 10]

    async def _generate_idle_recommendations(self) -> List[OptimizationRecommendation]:
        """Generate idle resource recommendations."""
        recommendations = []
        
        # Sample idle resources
        recommendations.append(OptimizationRecommendation(
            id=str(uuid4()),
            action=OptimizationAction.TERMINATE,
            category=CostCategory.COMPUTE,
            resource_id="i-0987654321fedcba0",
            resource_name="dev-environment-staging-3",
            current_cost=180.00,
            estimated_savings=180.00,
            savings_percent=100.0,
            confidence=0.95,
            effort_level="low",
            risk_level="low",
            description="Instance idle for 14 days (CPU < 1%, no network traffic). Safe to terminate.",
            implementation_steps=[
                "Verify no critical data on instance",
                "Create snapshot for backup",
                "Terminate instance",
                "Update documentation",
            ],
            prerequisites=["Snapshot permissions", "Team approval for dev env"],
            risks=["Potential data loss if not backed up"],
        ))
        
        return recommendations

    async def _generate_commitment_recommendations(self) -> List[OptimizationRecommendation]:
        """Generate Reserved Instance / Savings Plan recommendations."""
        recommendations = []
        
        # Analyze consistent usage patterns
        recommendations.append(OptimizationRecommendation(
            id=str(uuid4()),
            action=OptimizationAction.RESERVE,
            category=CostCategory.COMPUTE,
            resource_id="ri-recommendation-1",
            resource_name="Production EC2 Fleet",
            current_cost=12500.00,
            estimated_savings=3750.00,
            savings_percent=30.0,
            confidence=0.90,
            effort_level="medium",
            risk_level="low",
            description="Consistent baseline usage of 50 c5.xlarge instances. Recommend 1-year No Upfront Reserved Instances.",
            implementation_steps=[
                "Purchase 50 c5.xlarge 1-year No Upfront RIs",
                "Verify RI application in billing",
                "Monitor RI utilization",
            ],
            prerequisites=["AWS Enterprise Support", "Billing permissions"],
            risks=["Overcommitment if workload decreases"],
        ))
        
        return recommendations

    async def _generate_spot_recommendations(self) -> List[OptimizationRecommendation]:
        """Generate Spot instance recommendations."""
        recommendations = []
        
        recommendations.append(OptimizationRecommendation(
            id=str(uuid4()),
            action=OptimizationAction.SPOT,
            category=CostCategory.COMPUTE,
            resource_id="batch-processing-fleet",
            resource_name="Batch Processing Workers",
            current_cost=8500.00,
            estimated_savings=5950.00,
            savings_percent=70.0,
            confidence=0.80,
            effort_level="high",
            risk_level="medium",
            description="Batch processing workloads can tolerate interruption. Switch to Spot instances with fallback.",
            implementation_steps=[
                "Create Spot Fleet with capacity-optimized allocation",
                "Configure interruption handling",
                "Implement checkpointing in batch jobs",
                "Test with 10% of fleet first",
            ],
            prerequisites=["Checkpointing in batch jobs", "Fleet management setup"],
            risks=["Instance interruption (2-min warning)", "Capacity availability"],
        ))
        
        return recommendations

    # ==================== Anomaly Detection Loop ====================

    async def _anomaly_detection_loop(self):
        """Background anomaly detection loop."""
        while True:
            try:
                anomalies = await self.detect_anomalies(sensitivity=2.5)
                if anomalies:
                    logger.warning(f"Detected {len(anomalies)} cost anomalies")
                    # Would send alerts
            except Exception as e:
                logger.error(f"Anomaly detection error: {e}")
            
            await asyncio.sleep(3600)  # Every hour

    async def _recommendation_generation_loop(self):
        """Background recommendation generation loop."""
        while True:
            try:
                await self.generate_recommendations()
            except Exception as e:
                logger.error(f"Recommendation generation error: {e}")
            
            await asyncio.sleep(86400)  # Daily

    async def _cost_analysis_loop(self):
        """Background cost analysis loop."""
        while True:
            try:
                # Aggregate costs, update dashboards
                await self._aggregate_costs()
            except Exception as e:
                logger.error(f"Cost analysis error: {e}")
            
            await asyncio.sleep(3600)  # Every hour

    async def _aggregate_costs(self):
        """Aggregate costs for reporting."""
        # Would aggregate and store aggregated cost data
        pass

    # ==================== Reporting ====================

    async def generate_cost_report(
        self,
        period_start: datetime,
        period_end: datetime,
    ) -> CostReport:
        """Generate comprehensive cost report."""
        # Aggregate costs by category
        cost_by_category = {}
        cost_by_resource = {}
        cost_trend = []
        
        for cat_key, points in self._cost_data.items():
            cat_cost = sum(p["cost"] for p in points 
                          if period_start <= p["timestamp"] <= period_end)
            cost_by_category[CostCategory(cat_key)] = cat_cost
            
            # By resource
            for p in points:
                if period_start <= p["timestamp"] <= period_end:
                    rid = p["resource_id"]
                    cost_by_resource[rid] = cost_by_resource.get(rid, 0) + p["cost"]
            
            # Trend (daily)
            daily_costs = {}
            for p in points:
                if period_start <= p["timestamp"] <= period_end:
                    day = p["timestamp"].date()
                    daily_costs[day] = daily_costs.get(day, 0) + p["cost"]
            
            cost_trend = [(d, c) for d, c in sorted(daily_costs.items())]
        
        total_cost = sum(cost_by_category.values())
        
        # Get anomalies and recommendations for period
        anomalies = [
            a for a in self._anomalies
            if period_start <= a.detected_at <= period_end
        ]
        
        recommendations = [
            r for r in self._recommendations.values()
            if period_start <= r.created_at <= period_end and r.status == "pending"
        ]
        
        potential_savings = sum(r.estimated_savings for r in recommendations)
        
        return CostReport(
            period_start=period_start,
            period_end=period_end,
            total_cost=total_cost,
            cost_by_category=cost_by_category,
            cost_by_resource=cost_by_resource,
            cost_trend=cost_trend,
            anomalies=anomalies,
            recommendations=recommendations,
            potential_savings=potential_savings,
        )

    async def get_recommendations(
        self,
        status: Optional[str] = None,
        category: Optional[CostCategory] = None,
    ) -> List[OptimizationRecommendation]:
        """Get optimization recommendations."""
        recommendations = list(self._recommendations.values())
        
        if status:
            recommendations = [r for r in recommendations if r.status == status]
        if category:
            recommendations = [r for r in recommendations if r.category == category]
        
        return sorted(recommendations, key=lambda r: r.estimated_savings, reverse=True)

    async def update_recommendation_status(
        self,
        recommendation_id: str,
        status: str,
        notes: str = "",
    ) -> bool:
        """Update recommendation status."""
        rec = self._recommendations.get(recommendation_id)
        if not rec:
            return False
        
        rec.status = status
        if notes:
            rec.implementation_steps.append(f"Note: {notes}")
        return True

    async def get_anomalies(
        self,
        category: Optional[CostCategory] = None,
        severity: Optional[str] = None,
        hours: int = 24,
    ) -> List[CostAnomaly]:
        """Get cost anomalies."""
        cutoff = utcnow() - timedelta(hours=hours)
        
        anomalies = [a for a in self._anomalies if a.detected_at >= cutoff]
        
        if category:
            anomalies = [a for a in anomalies if a.category == category]
        if severity:
            anomalies = [a for a in anomalies if a.severity == severity]
        
        return sorted(anomalies, key=lambda a: a.detected_at, reverse=True)

    def get_stats(self) -> Dict[str, Any]:
        """Get cost optimizer statistics."""
        total_recs = len(self._recommendations)
        pending = sum(1 for r in self._recommendations.values() if r.status == "pending")
        implemented = sum(1 for r in self._recommendations.values() if r.status == "implemented")
        total_savings = sum(r.estimated_savings for r in self._recommendations.values() if r.status == "implemented")
        potential_savings = sum(r.estimated_savings for r in self._recommendations.values() if r.status == "pending")
        
        recent_anomalies = len([
            a for a in self._anomalies 
            if a.detected_at >= utcnow() - timedelta(hours=24)
        ])
        
        total_cost_7d = sum(
            p["cost"] for points in self._cost_data.values()
            for p in points if p["timestamp"] >= utcnow() - timedelta(days=7)
        )
        
        return {
            "total_recommendations": total_recs,
            "pending_recommendations": pending,
            "implemented_recommendations": implemented,
            "implemented_savings": total_savings,
            "potential_savings": potential_savings,
            "anomalies_24h": recent_anomalies,
            "cost_last_7_days": total_cost_7d,
            "categories_tracked": len(self._cost_data),
        }


class CapacityPlanner:
    """
    Capacity planning with predictive forecasting.
    
    Features:
    - Resource utilization forecasting
    - Time-to-capacity predictions
    - Growth trend analysis
    - Capacity recommendations
    """

    def __init__(self, scaler: PredictiveScaler, optimizer: CostOptimizer):
        self.scaler = scaler
        self.optimizer = optimizer
        self._forecasts: Dict[str, CapacityForecast] = {}

    async def forecast_capacity(
        self,
        resource_type: ResourceType,
        namespace: str,
        workload: str,
        horizon: str = "30d",
    ) -> CapacityForecast:
        """Forecast capacity for a resource."""
        # Get current usage metrics
        metric_name = f"{resource_type.value}_usage"
        labels = {"namespace": namespace, "workload": workload}
        
        history = await self.scaler.get_metric_history(
            metric_name=resource_type.value + "_usage",
            labels={"namespace": namespace, "workload": workload},
            hours=720,  # 30 days
        )
        
        if not history:
            raise ValueError(f"No metric data for {resource_type.value} in {namespace}/{workload}")
        
        # Get current usage
        current_usage = history[-1].value if history else 0
        
        # Predict future usage
        prediction = await self.scaler.predict_metric(
            metric_name=resource_type.value + "_usage",
            labels={"namespace": namespace, "workload": workload},
            horizon=horizon,
        )
        
        # Estimate capacity limit (would come from cluster capacity)
        capacity_limit = 100.0  # Percentage
        
        # Calculate time to capacity
        time_to_capacity = None
        for pred_time, pred_value in prediction.predicted_values:
            if pred_value >= capacity_limit * 0.9:  # 90% threshold
                time_to_capacity = pred_time - utcnow()
                break
        
        # Determine recommended action
        if current_usage > 80:
            recommended_action = "Scale up immediately"
        elif current_usage > 70:
            recommended_action = "Plan scale up within 1 week"
        elif current_usage > 50:
            recommended_action = "Monitor, plan for scaling"
        else:
            recommended_action = "No action needed"
        
        forecast = CapacityForecast(
            resource_type=resource_type,
            current_usage=current_usage,
            predicted_usage=prediction.predicted_values,
            capacity_limit=capacity_limit,
            time_to_capacity=time_to_capacity,
            recommended_action=recommended_action,
            confidence=prediction.confidence_score,
        )
        
        self._forecasts[f"{resource_type.value}:{namespace}:{workload}"] = forecast
        return forecast

    async def forecast_all_resources(
        self,
        namespace: str,
        workload: str,
    ) -> Dict[ResourceType, CapacityForecast]:
        """Forecast capacity for all resource types."""
        results = {}
        
        for resource_type in ResourceType:
            try:
                forecast = await self.forecast_capacity(resource_type, namespace, workload)
                results[resource_type] = forecast
            except Exception as e:
                logger.warning(f"Failed to forecast {resource_type}: {e}")
        
        return results

    def get_forecast(self, resource_type: ResourceType, namespace: str, workload: str) -> Optional[CapacityForecast]:
        return self._forecasts.get(f"{resource_type.value}:{namespace}:{workload}")

    def get_all_forecasts(self) -> Dict[str, CapacityForecast]:
        return self._forecasts.copy()


# ==================== Global Instances ====================

_predictive_scaler: Optional[PredictiveScaler] = None
_cost_optimizer: Optional[CostOptimizer] = None
_capacity_planner: Optional[CapacityPlanner] = None


def get_predictive_scaler() -> PredictiveScaler:
    global _predictive_scaler
    if _predictive_scaler is None:
        _predictive_scaler = PredictiveScaler()
    return _predictive_scaler


async def init_predictive_scaler() -> PredictiveScaler:
    global _predictive_scaler
    _predictive_scaler = PredictiveScaler()
    await _predictive_scaler.initialize()
    return _predictive_scaler


def get_cost_optimizer() -> CostOptimizer:
    global _cost_optimizer
    if _cost_optimizer is None:
        _cost_optimizer = CostOptimizer()
    return _cost_optimizer


async def init_cost_optimizer() -> CostOptimizer:
    global _cost_optimizer
    _cost_optimizer = CostOptimizer()
    await _cost_optimizer.initialize()
    return _cost_optimizer


def get_capacity_planner() -> CapacityPlanner:
    global _capacity_planner
    if _capacity_planner is None:
        _capacity_planner = CapacityPlanner(
            scaler=get_predictive_scaler(),
            optimizer=get_cost_optimizer(),
        )
    return _capacity_planner


async def init_capacity_planner() -> CapacityPlanner:
    global _capacity_planner
    _capacity_planner = CapacityPlanner(
        scaler=await init_predictive_scaler(),
        optimizer=await init_cost_optimizer(),
    )
    return _capacity_planner


async def init_all_sre() -> Dict[str, Any]:
    """Initialize all SRE components."""
    logger.info("Initializing SRE components...")
    
    # Initialize structured logging
    from app.core.structured_logging import init_structured_logging
    init_structured_logging()
    
    # Initialize on-call
    oncall = await init_oncall_manager()
    
    # Initialize predictive scaling
    scaler = await init_predictive_scaler()
    
    # Initialize cost optimizer
    optimizer = await init_cost_optimizer()
    
    # Initialize capacity planner
    planner = await init_capacity_planner()
    
    logger.info("All SRE components initialized")
    
    return {
        "oncall": oncall,
        "scaler": scaler,
        "optimizer": optimizer,
        "planner": planner,
    }