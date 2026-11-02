"""Health Model Service for Production Observability & Alerting (Slice 2E).

Provides multi-dimensional health model with aggregate fingerprint, trend analysis,
and integration with canonical fingerprint service.
"""

import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple
from collections import defaultdict

from sqlalchemy import select, and_, or_, func, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.observability import HealthDimension
from app.services.canonical_fingerprint import canonical_fingerprint_service, TenantFingerprint
from app.validation.capability_contract import CapabilityDetector

logger = logging.getLogger("vcos.health_model")


# =============================================================================
# HEALTH MODEL TYPES
# =============================================================================

@dataclass
class HealthTrendPoint:
    """Single point in health trend."""
    timestamp: datetime
    dimension: str
    status: str
    value: float
    fingerprint: str


@dataclass
class DimensionTrend:
    """Trend analysis for a single dimension."""
    dimension: str
    points: List[HealthTrendPoint]
    trend_direction: str  # improving|stable|degrading|volatile
    trend_score: float  # -1.0 to 1.0
    volatility: float
    last_status: str
    last_value: float
    window_start: datetime
    window_end: datetime


@dataclass
class HealthModelSnapshot:
    """Snapshot of health model at a point in time."""
    organization_id: str
    timestamp: datetime
    overall_status: str
    dimension_statuses: Dict[str, str]  # dimension -> status
    dimension_values: Dict[str, float]  # dimension -> current_value
    aggregate_fingerprint: str
    tenant_fingerprint: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HealthModelReport:
    """Comprehensive health model report."""
    organization_id: str
    generated_at: datetime
    current_snapshot: HealthModelSnapshot
    trends: Dict[str, DimensionTrend]
    trend_summary: Dict[str, Any]
    anomaly_alerts: List[Dict[str, Any]]
    fingerprint: str


# =============================================================================
# HEALTH MODEL SERVICE
# =============================================================================

class HealthModelService(CapabilityDetector):
    """Service for building and analyzing multi-dimensional health models."""
    
    def __init__(self, history_window_days: int = 30):
        super().__init__()
        self.history_window_days = history_window_days
        self._snapshots: Dict[str, List[HealthModelSnapshot]] = defaultdict(list)
        self._max_snapshots_per_org = 1000
    
    async def build_health_model(
        self,
        db: AsyncSession,
        organization_id: str,
        health_report: "AggregateHealthReport",
        tenant_fingerprint: Optional[TenantFingerprint] = None,
    ) -> HealthModelSnapshot:
        """Build health model snapshot from evaluation report."""
        
        # Extract dimension statuses and values
        dimension_statuses = {}
        dimension_values = {}
        
        for dim, result in health_report.dimension_results.items():
            dimension_statuses[dim.value] = result.status
            dimension_values[dim.value] = result.current_value
        
        # Get tenant fingerprint if available
        tenant_fp = None
        if tenant_fingerprint:
            tenant_fp = tenant_fingerprint.aggregate_fingerprint
        
        snapshot = HealthModelSnapshot(
            organization_id=organization_id,
            timestamp=utcnow(),
            overall_status=health_report.overall_status,
            dimension_statuses=dimension_statuses,
            dimension_values=dimension_values,
            aggregate_fingerprint=health_report.aggregate_fingerprint,
            tenant_fingerprint=tenant_fp,
            metadata={
                "evaluation_timestamp": health_report.checked_at.isoformat(),
            },
        )
        
        # Store snapshot
        self._store_snapshot(organization_id, snapshot)
        
        return snapshot
    
    def _store_snapshot(self, organization_id: str, snapshot: HealthModelSnapshot) -> None:
        """Store snapshot in memory (in production, persist to database)."""
        snapshots = self._snapshots[organization_id]
        snapshots.append(snapshot)
        
        # Trim old snapshots
        if len(snapshots) > self._max_snapshots_per_org:
            snapshots[:] = snapshots[-self._max_snapshots_per_org:]
    
    async def get_health_trends(
        self,
        db: AsyncSession,
        organization_id: str,
        window_days: Optional[int] = None,
    ) -> Dict[str, DimensionTrend]:
        """Analyze health trends across all dimensions."""
        window = window_days or self.history_window_days
        cutoff = utcnow() - timedelta(days=window)
        
        # Query historical health dimensions from database
        result = await db.execute(
            select(HealthDimension)
            .where(
                and_(
                    HealthDimension.organization_id == organization_id,
                    HealthDimension.recorded_at >= cutoff,
                )
            )
            .order_by(HealthDimension.recorded_at)
        )
        historical = result.scalars().all()
        
        # Group by dimension
        by_dimension = defaultdict(list)
        for hd in historical:
            by_dimension[hd.dimension].append(hd)
        
        trends = {}
        for dimension, points in by_dimension.items():
            if len(points) < 2:
                continue
            
            trend_points = [
                HealthTrendPoint(
                    timestamp=p.recorded_at,
                    dimension=p.dimension,
                    status=p.status,
                    value=p.current_value,
                    fingerprint=p.fingerprint,
                )
                for p in points
            ]
            
            trend = self._analyze_trend(dimension, trend_points)
            trends[dimension] = trend
        
        return trends
    
    def _analyze_trend(self, dimension: str, points: List[HealthTrendPoint]) -> DimensionTrend:
        """Analyze trend for a single dimension."""
        if len(points) < 2:
            return DimensionTrend(
                dimension=dimension,
                points=points,
                trend_direction="stable",
                trend_score=0.0,
                volatility=0.0,
                last_status=points[-1].status if points else "unknown",
                last_value=points[-1].value if points else 0.0,
                window_start=points[0].timestamp if points else utcnow(),
                window_end=points[-1].timestamp if points else utcnow(),
            )
        
        # Calculate trend score using linear regression on values
        values = [p.value for p in points]
        n = len(values)
        x = list(range(n))
        
        # Simple linear regression
        x_mean = sum(x) / n
        y_mean = sum(values) / n
        
        numerator = sum((x[i] - x_mean) * (values[i] - y_mean) for i in range(n))
        denominator = sum((x[i] - x_mean) ** 2 for i in range(n))
        
        if denominator > 0:
            slope = numerator / denominator
        else:
            slope = 0.0
        
        # Normalize slope to -1..1 range
        max_value = max(values) if values else 1.0
        min_value = min(values) if values else 0.0
        value_range = max_value - min_value if max_value != min_value else 1.0
        trend_score = max(-1.0, min(1.0, slope * n / value_range))
        
        # Determine direction
        if trend_score > 0.1:
            trend_direction = "improving"
        elif trend_score < -0.1:
            trend_direction = "degrading"
        else:
            # Check volatility
            volatility = self._calculate_volatility(values)
            if volatility > 0.3:
                trend_direction = "volatile"
            else:
                trend_direction = "stable"
        
        # Calculate volatility (coefficient of variation)
        volatility = self._calculate_volatility(values)
        
        return DimensionTrend(
            dimension=dimension,
            points=points,
            trend_direction=trend_direction,
            trend_score=trend_score,
            volatility=volatility,
            last_status=points[-1].status,
            last_value=points[-1].value,
            window_start=points[0].timestamp,
            window_end=points[-1].timestamp,
        )
    
    def _calculate_volatility(self, values: List[float]) -> float:
        """Calculate coefficient of variation."""
        if len(values) < 2:
            return 0.0
        
        mean = sum(values) / len(values)
        if mean == 0:
            return 0.0
        
        variance = sum((v - mean) ** 2 for v in values) / len(values)
        std_dev = variance ** 0.5
        return std_dev / mean
    
    async def detect_anomalies(
        self,
        db: AsyncSession,
        organization_id: str,
        current_snapshot: HealthModelSnapshot,
        trends: Dict[str, DimensionTrend],
    ) -> List[Dict[str, Any]]:
        """Detect anomalies in health model."""
        anomalies = []
        
        # Check for sudden status changes
        for dimension, trend in trends.items():
            if len(trend.points) < 2:
                continue
            
            # Check for status degradation
            recent_statuses = [p.status for p in trend.points[-5:]]
            if "critical" in recent_statuses and "healthy" in recent_statuses[-3:-1]:
                anomalies.append({
                    "type": "sudden_degradation",
                    "dimension": dimension,
                    "severity": "high",
                    "message": f"{dimension} suddenly degraded from healthy to critical",
                    "details": {
                        "recent_statuses": recent_statuses,
                        "trend_score": trend.trend_score,
                    },
                })
            
            # Check for high volatility
            if trend.volatility > 0.5:
                anomalies.append({
                    "type": "high_volatility",
                    "dimension": dimension,
                    "severity": "medium",
                    "message": f"{dimension} showing high volatility (cv={trend.volatility:.2f})",
                    "details": {
                        "volatility": trend.volatility,
                        "trend_direction": trend.trend_direction,
                    },
                })
            
            # Check for sustained degradation
            if trend.trend_score < -0.5 and trend.trend_direction == "degrading":
                anomalies.append({
                    "type": "sustained_degradation",
                    "dimension": dimension,
                    "severity": "high",
                    "message": f"{dimension} showing sustained degradation trend",
                    "details": {
                        "trend_score": trend.trend_score,
                        "trend_direction": trend.trend_direction,
                    },
                })
        
        # Check for fingerprint divergence from tenant fingerprint
        if current_snapshot.tenant_fingerprint and current_snapshot.aggregate_fingerprint:
            if current_snapshot.tenant_fingerprint != current_snapshot.aggregate_fingerprint:
                anomalies.append({
                    "type": "fingerprint_divergence",
                    "dimension": "canonical_reality",
                    "severity": "critical",
                    "message": "Health model fingerprint diverges from tenant canonical fingerprint",
                    "details": {
                        "tenant_fingerprint": current_snapshot.tenant_fingerprint[:16],
                        "health_fingerprint": current_snapshot.aggregate_fingerprint[:16],
                    },
                })
        
        return anomalies
    
    async def generate_report(
        self,
        db: AsyncSession,
        organization_id: str,
        health_report: "AggregateHealthReport",
        tenant_fingerprint: Optional[TenantFingerprint] = None,
    ) -> HealthModelReport:
        """Generate comprehensive health model report."""
        
        # Build current snapshot
        snapshot = await self.build_health_model(db, organization_id, health_report, tenant_fingerprint)
        
        # Get trends
        trends = await self.get_health_trends(db, organization_id)
        
        # Detect anomalies
        anomalies = await self.detect_anomalies(db, organization_id, snapshot, trends)
        
        # Generate trend summary
        trend_summary = {
            "total_dimensions": len(trends),
            "improving": sum(1 for t in trends.values() if t.trend_direction == "improving"),
            "degrading": sum(1 for t in trends.values() if t.trend_direction == "degrading"),
            "stable": sum(1 for t in trends.values() if t.trend_direction == "stable"),
            "volatile": sum(1 for t in trends.values() if t.trend_direction == "volatile"),
            "anomalies_detected": len(anomalies),
        }
        
        # Compute report fingerprint
        report_data = {
            "organization_id": organization_id,
            "snapshot_fingerprint": snapshot.aggregate_fingerprint,
            "trends": {
                dim: {
                    "direction": t.trend_direction,
                    "score": t.trend_score,
                    "volatility": t.volatility,
                }
                for dim, t in trends.items()
            },
            "anomalies": len(anomalies),
        }
        canonical = json.dumps(report_data, sort_keys=True, separators=(",", ":"))
        fingerprint = hashlib.sha256(canonical.encode()).hexdigest()[:64]
        
        return HealthModelReport(
            organization_id=organization_id,
            generated_at=utcnow(),
            current_snapshot=snapshot,
            trends=trends,
            trend_summary=trend_summary,
            anomaly_alerts=anomalies,
            fingerprint=fingerprint,
        )
    
    async def compare_snapshots(
        self,
        organization_id: str,
        snapshot1: HealthModelSnapshot,
        snapshot2: HealthModelSnapshot,
    ) -> Dict[str, Any]:
        """Compare two health model snapshots."""
        changes = {
            "overall_status_changed": snapshot1.overall_status != snapshot2.overall_status,
            "overall_status_from": snapshot1.overall_status,
            "overall_status_to": snapshot2.overall_status,
            "dimension_changes": {},
            "fingerprint_match": snapshot1.aggregate_fingerprint == snapshot2.aggregate_fingerprint,
        }
        
        all_dims = set(snapshot1.dimension_statuses.keys()) | set(snapshot2.dimension_statuses.keys())
        
        for dim in all_dims:
            status1 = snapshot1.dimension_statuses.get(dim)
            status2 = snapshot2.dimension_statuses.get(dim)
            value1 = snapshot1.dimension_values.get(dim)
            value2 = snapshot2.dimension_values.get(dim)
            
            if status1 != status2 or value1 != value2:
                changes["dimension_changes"][dim] = {
                    "status_from": status1,
                    "status_to": status2,
                    "value_from": value1,
                    "value_to": value2,
                    "value_delta": (value2 or 0) - (value1 or 0) if value1 is not None and value2 is not None else None,
                }
        
        return changes
    
    def get_snapshot_history(
        self,
        organization_id: str,
        limit: int = 100,
    ) -> List[HealthModelSnapshot]:
        """Get recent snapshot history for an organization."""
        snapshots = self._snapshots.get(organization_id, [])
        return snapshots[-limit:]
    
    async def correlate_with_canonical_fingerprint(
        self,
        db: AsyncSession,
        organization_id: str,
        health_report: "AggregateHealthReport",
    ) -> Dict[str, Any]:
        """Correlate health model with canonical fingerprint."""
        
        # Get tenant fingerprint
        tenant_fp = await canonical_fingerprint_service.compute_tenant_fingerprint(
            db, organization_id
        )
        
        # Compare fingerprints
        fingerprint_match = health_report.aggregate_fingerprint == tenant_fp.aggregate_fingerprint
        
        # Check component-level differences
        component_diffs = {}
        # HealthCheckResult has 'dimension' attribute, not 'component_name'
        health_components = {r.dimension.value: r.current_value for r in health_report.dimension_results.values()}
        tenant_components = {c.component_name: c.fingerprint for c in tenant_fp.components}
        
        all_components = set(health_components.keys()) | set(tenant_components.keys())
        for comp in all_components:
            h_val = health_components.get(comp)
            t_fp = tenant_components.get(comp)
            if h_val is not None or t_fp is not None:
                component_diffs[comp] = {
                    "health_value": h_val,
                    "tenant_fingerprint": t_fp,
                    "match": h_val is not None and t_fp is not None,
                }
        
        return {
            "fingerprint_match": fingerprint_match,
            "health_aggregate_fingerprint": health_report.aggregate_fingerprint,
            "tenant_aggregate_fingerprint": tenant_fp.aggregate_fingerprint,
            "component_differences": component_diffs,
            "divergence_detected": not fingerprint_match or len(component_diffs) > 0,
        }


# Global instance
health_model_service = HealthModelService()