"""Alert Engine for Production Observability & Alerting (Slice 2E).

Provides alert lifecycle management: OBSERVED → EVALUATED → ALERTED → ACKNOWLEDGED → INVESTIGATING → RESOLVED → VERIFIED
"""

import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set
from enum import Enum
from collections import defaultdict

from sqlalchemy import select, and_, or_, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.observability import (
    CanonicalObservation,
    Degradation,
    HealthDimension,
    OBSERVATION_SEVERITY,
    DEGRADATION_STATES,
    DEGRADATION_SEVERITY,
)
from app.validation.capability_contract import CapabilityDetector

logger = logging.getLogger("vcos.alert_engine")


# =============================================================================
# ALERT ENUMS & TYPES
# =============================================================================

class AlertState(str, Enum):
    """Alert lifecycle states."""
    OBSERVED = "observed"
    EVALUATED = "evaluated"
    ALERTED = "alerted"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    VERIFIED = "verified"
    SUPPRESSED = "suppressed"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    DEBUG = "debug"
    INFO = "info"
    NOTICE = "notice"
    WARNING = "warning"
    CRITICAL = "critical"


class AlertCorrelationType(str, Enum):
    """Types of alert correlations."""
    SAME_ROOT_CAUSE = "same_root_cause"
    CASCADING = "cascading"
    RELATED_SYSTEM = "related_system"
    TEMPORAL_PROXIMITY = "temporal_proximity"
    DEPENDENCY = "dependency"


@dataclass
class AlertRule:
    """Alert rule configuration."""
    name: str
    description: str
    dimension: str  # Health dimension to monitor
    condition: str  # e.g., "current_value > threshold_critical"
    severity: AlertSeverity
    governance_scope: str = "company"
    enabled: bool = True
    deduplication_window_seconds: int = 300
    correlation_types: List[AlertCorrelationType] = field(default_factory=list)
    freshness_seconds: int = 60
    runbook_url: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Alert:
    """Alert instance."""
    id: str
    organization_id: str
    rule_name: str
    rule_description: str
    dimension: str
    severity: AlertSeverity
    state: AlertState
    title: str
    description: str
    details: Dict[str, Any]
    fingerprint: str
    correlation_id: Optional[str] = None
    related_alert_ids: List[str] = field(default_factory=list)
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    investigating_by: Optional[str] = None
    investigating_at: Optional[datetime] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    verified_by: Optional[str] = None
    verified_at: Optional[datetime] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AlertCorrelation:
    """Alert correlation record."""
    alert_id: str
    correlated_alert_id: str
    correlation_type: AlertCorrelationType
    confidence: float
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# =============================================================================
# ALERT DEDUPLICATION SERVICE
# =============================================================================

class AlertDeduplicationService:
    """Deduplicates alerts using fingerprint-based caching."""
    
    def __init__(self, window_seconds: int = 300):
        self.window_seconds = window_seconds
        self._fingerprint_cache: Dict[str, datetime] = {}
        self._lock = False  # Simple lock for async safety
    
    def _compute_fingerprint(self, alert: Alert) -> str:
        """Compute deterministic fingerprint for alert deduplication."""
        data = {
            "organization_id": alert.organization_id,
            "rule_name": alert.rule_name,
            "dimension": alert.dimension,
            "severity": alert.severity.value,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:64]
    
    def is_duplicate(self, alert: Alert) -> bool:
        """Check if alert is a duplicate within the deduplication window."""
        fp = self._compute_fingerprint(alert)
        now = utcnow()
        
        if fp in self._fingerprint_cache:
            last_seen = self._fingerprint_cache[fp]
            if (now - last_seen).total_seconds() < self.window_seconds:
                return True
        
        # Update cache
        self._fingerprint_cache[fp] = now
        self._cleanup_cache(now)
        return False
    
    def _cleanup_cache(self, now: datetime) -> None:
        """Remove expired entries from cache."""
        expired = [
            fp for fp, ts in self._fingerprint_cache.items()
            if (now - ts).total_seconds() >= self.window_seconds * 2
        ]
        for fp in expired:
            del self._fingerprint_cache[fp]
    
    def clear_cache(self) -> None:
        """Clear the deduplication cache."""
        self._fingerprint_cache.clear()


# =============================================================================
# ALERT CORRELATION SERVICE
# =============================================================================

class AlertCorrelationService:
    """Correlates alerts based on various correlation types."""
    
    def __init__(self):
        self._correlations: Dict[str, List[AlertCorrelation]] = defaultdict(list)
    
    def correlate(self, alert: Alert, existing_alerts: List[Alert]) -> List[AlertCorrelation]:
        """Find correlations between new alert and existing alerts."""
        correlations = []
        
        for existing in existing_alerts:
            if existing.id == alert.id:
                continue
            
            # Skip if already correlated
            if any(c.correlated_alert_id == existing.id for c in self._correlations.get(alert.id, [])):
                continue
            
            correlation = self._compute_correlation(alert, existing)
            if correlation:
                correlations.append(correlation)
                self._correlations[alert.id].append(correlation)
                self._correlations[existing.id].append(AlertCorrelation(
                    alert_id=existing.id,
                    correlated_alert_id=alert.id,
                    correlation_type=correlation.correlation_type,
                    confidence=correlation.confidence,
                ))
        
        return correlations
    
    def _compute_correlation(self, alert1: Alert, alert2: Alert) -> Optional[AlertCorrelation]:
        """Compute correlation between two alerts."""
        # Same organization
        if alert1.organization_id != alert2.organization_id:
            return None
        
        # Same dimension - likely same root cause
        if alert1.dimension == alert2.dimension:
            time_diff = abs((alert1.created_at - alert2.created_at).total_seconds())
            if time_diff < 3600:  # Within 1 hour
                return AlertCorrelation(
                    alert_id=alert1.id,
                    correlated_alert_id=alert2.id,
                    correlation_type=AlertCorrelationType.SAME_ROOT_CAUSE,
                    confidence=0.9 - min(time_diff / 3600, 0.5),
                )
        
        # Related systems (e.g., database + worker_health)
        related_dimensions = {
            ("database", "worker_health"),
            ("availability", "latency"),
            ("error_rate", "queue_delay"),
            ("sync_freshness", "integration_health"),
        }
        
        dim_pair = tuple(sorted([alert1.dimension, alert2.dimension]))
        if dim_pair in related_dimensions:
            time_diff = abs((alert1.created_at - alert2.created_at).total_seconds())
            if time_diff < 1800:  # Within 30 minutes
                return AlertCorrelation(
                    alert_id=alert1.id,
                    correlated_alert_id=alert2.id,
                    correlation_type=AlertCorrelationType.RELATED_SYSTEM,
                    confidence=0.7,
                )
        
        # Temporal proximity
        time_diff = abs((alert1.created_at - alert2.created_at).total_seconds())
        if time_diff < 300:  # Within 5 minutes
            return AlertCorrelation(
                alert_id=alert1.id,
                correlated_alert_id=alert2.id,
                correlation_type=AlertCorrelationType.TEMPORAL_PROXIMITY,
                confidence=0.5,
            )
        
        return None
    
    def get_correlations(self, alert_id: str) -> List[AlertCorrelation]:
        """Get all correlations for an alert."""
        return self._correlations.get(alert_id, [])


# =============================================================================
# ALERT ENGINE
# =============================================================================

class AlertEngine(CapabilityDetector):
    """Main alert engine managing alert lifecycle."""
    
    def __init__(self, register_default_rules: bool = True):
        super().__init__()
        self._rules: Dict[str, AlertRule] = {}
        self._alerts: Dict[str, Alert] = {}
        self._deduplication = AlertDeduplicationService()
        self._correlation = AlertCorrelationService()
        self._alert_listeners: List[callable] = []
        
        if register_default_rules:
            for rule in create_release_health_alert_rules():
                self.register_rule(rule)
    
    def register_rule(self, rule: AlertRule) -> None:
        """Register an alert rule."""
        self._rules[rule.name] = rule
        logger.info(f"Registered alert rule: {rule.name}")
    
    def get_rule(self, name: str) -> Optional[AlertRule]:
        """Get alert rule by name."""
        return self._rules.get(name)
    
    def list_rules(self) -> List[AlertRule]:
        """List all registered rules."""
        return list(self._rules.values())
    
    def add_listener(self, listener: callable) -> None:
        """Add alert state change listener."""
        self._alert_listeners.append(listener)
    
    async def evaluate_observation(
        self,
        observation: CanonicalObservation,
        health_dimension: Optional[HealthDimension] = None,
    ) -> List[Alert]:
        """Evaluate an observation against alert rules."""
        alerts = []
        
        for rule in self._rules.values():
            if not rule.enabled:
                continue
            
            # Check if rule applies to this observation
            if not self._rule_applies(rule, observation, health_dimension):
                continue
            
            # Evaluate condition
            if await self._evaluate_condition(rule, observation, health_dimension):
                alert = await self._create_alert(rule, observation, health_dimension)
                if alert and not self._deduplication.is_duplicate(alert):
                    alerts.append(alert)
                    await self._process_alert(alert)
        
        return alerts
    
    def _rule_applies(
        self,
        rule: AlertRule,
        observation: CanonicalObservation,
        health_dimension: Optional[HealthDimension],
    ) -> bool:
        """Check if rule applies to the observation."""
        # Check dimension match
        if health_dimension and rule.dimension != health_dimension.dimension:
            return False
        
        # Check observation type relevance
        relevant_types = {
            "health_check": ["availability", "latency", "error_rate", "queue_delay", "worker_health"],
            "slo_evaluation": ["availability", "latency", "error_rate", "sync_freshness"],
            "freshness_check": ["sync_freshness"],
            "recovery_action": ["recovery_backlog"],
            "reconciliation": ["reconciliation_backlog"],
            "degradation": ["availability", "latency", "error_rate", "worker_health"],
        }
        
        if observation.observation_type in relevant_types:
            if rule.dimension not in relevant_types[observation.observation_type]:
                return False
        
        return True
    
    async def _evaluate_condition(
        self,
        rule: AlertRule,
        observation: CanonicalObservation,
        health_dimension: Optional[HealthDimension],
    ) -> bool:
        """Evaluate alert rule condition."""
        if not health_dimension:
            return False
        
        # Simple condition evaluation
        # In production, use a proper expression evaluator
        condition = rule.condition.lower()
        current = health_dimension.current_value
        warn = health_dimension.threshold_warn
        critical = health_dimension.threshold_critical
        
        if "current_value > threshold_critical" in condition and critical is not None:
            return current > critical
        if "current_value > threshold_warn" in condition and warn is not None:
            return current > warn
        if "slo_compliance <" in condition and health_dimension.slo_compliance is not None:
            target = float(condition.split("<")[-1].strip())
            return health_dimension.slo_compliance < target
        if "status == \"critical\"" in condition:
            return health_dimension.status == "critical"
        if "status == \"degraded\"" in condition:
            return health_dimension.status == "degraded"
        
        return False
    
    async def _create_alert(
        self,
        rule: AlertRule,
        observation: CanonicalObservation,
        health_dimension: Optional[HealthDimension],
    ) -> Optional[Alert]:
        """Create alert from rule evaluation."""
        alert_id = f"alert-{uuid.uuid4().hex[:12]}"
        
        alert = Alert(
            id=alert_id,
            organization_id=observation.organization_id,
            rule_name=rule.name,
            rule_description=rule.description,
            dimension=rule.dimension,
            severity=rule.severity,
            state=AlertState.OBSERVED,
            title=f"{rule.name}: {rule.dimension} {rule.severity.value}",
            description=rule.description,
            details={
                "observation_id": observation.id,
                "observation_type": observation.observation_type,
                "health_dimension_id": health_dimension.id if health_dimension else None,
                "current_value": health_dimension.current_value if health_dimension else None,
                "threshold_warn": health_dimension.threshold_warn if health_dimension else None,
                "threshold_critical": health_dimension.threshold_critical if health_dimension else None,
            },
            fingerprint=alert_id,
            correlation_id=observation.correlation_id,
        )
        
        return alert
    
    async def _process_alert(self, alert: Alert) -> None:
        """Process new alert through lifecycle."""
        # Store alert
        self._alerts[alert.id] = alert
        
        # Correlate with existing alerts
        existing = list(self._alerts.values())
        correlations = self._correlation.correlate(alert, existing)
        alert.related_alert_ids = [c.correlated_alert_id for c in correlations]
        
        # Transition to EVALUATED
        await self._transition_state(alert, AlertState.EVALUATED)
        
        # Transition to ALERTED
        await self._transition_state(alert, AlertState.ALERTED)
        
        # Notify listeners
        for listener in self._alert_listeners:
            try:
                await listener(alert)
            except Exception as e:
                logger.error(f"Alert listener error: {e}")
    
    async def _transition_state(self, alert: Alert, new_state: AlertState) -> None:
        """Transition alert to new state."""
        old_state = alert.state
        alert.state = new_state
        alert.updated_at = utcnow()
        
        logger.info(f"Alert {alert.id} state transition: {old_state} → {new_state}")
        
        # State-specific actions
        if new_state == AlertState.ACKNOWLEDGED:
            pass
        elif new_state == AlertState.INVESTIGATING:
            pass
        elif new_state == AlertState.RESOLVED:
            alert.resolved_at = utcnow()
        elif new_state == AlertState.VERIFIED:
            alert.verified_at = utcnow()
    
    async def acknowledge_alert(self, alert_id: str, acknowledged_by: str) -> bool:
        """Acknowledge an alert."""
        alert = self._alerts.get(alert_id)
        if not alert or alert.state not in [AlertState.ALERTED, AlertState.EVALUATED]:
            return False
        
        alert.acknowledged_by = acknowledged_by
        alert.acknowledged_at = utcnow()
        await self._transition_state(alert, AlertState.ACKNOWLEDGED)
        return True
    
    async def start_investigation(self, alert_id: str, investigating_by: str) -> bool:
        """Start investigating an alert."""
        alert = self._alerts.get(alert_id)
        if not alert or alert.state != AlertState.ACKNOWLEDGED:
            return False
        
        alert.investigating_by = investigating_by
        alert.investigating_at = utcnow()
        await self._transition_state(alert, AlertState.INVESTIGATING)
        return True
    
    async def resolve_alert(self, alert_id: str, resolved_by: str, resolution_note: str = "") -> bool:
        """Resolve an alert."""
        alert = self._alerts.get(alert_id)
        if not alert or alert.state not in [AlertState.ACKNOWLEDGED, AlertState.INVESTIGATING]:
            return False
        
        alert.resolved_by = resolved_by
        alert.details["resolution_note"] = resolution_note
        await self._transition_state(alert, AlertState.RESOLVED)
        return True
    
    async def verify_alert(self, alert_id: str, verified_by: str) -> bool:
        """Verify an alert resolution."""
        alert = self._alerts.get(alert_id)
        if not alert or alert.state != AlertState.RESOLVED:
            return False
        
        alert.verified_by = verified_by
        await self._transition_state(alert, AlertState.VERIFIED)
        return True
    
    async def suppress_alert(self, alert_id: str, reason: str = "") -> bool:
        """Suppress an alert."""
        alert = self._alerts.get(alert_id)
        if not alert:
            return False
        
        alert.details["suppression_reason"] = reason
        await self._transition_state(alert, AlertState.SUPPRESSED)
        return True
    
    def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get alert by ID."""
        return self._alerts.get(alert_id)
    
    def list_alerts(
        self,
        organization_id: Optional[str] = None,
        state: Optional[AlertState] = None,
        severity: Optional[AlertSeverity] = None,
        dimension: Optional[str] = None,
    ) -> List[Alert]:
        """List alerts with optional filters."""
        alerts = list(self._alerts.values())
        
        if organization_id:
            alerts = [a for a in alerts if a.organization_id == organization_id]
        if state:
            alerts = [a for a in alerts if a.state == state]
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if dimension:
            alerts = [a for a in alerts if a.dimension == dimension]
        
        return sorted(alerts, key=lambda a: a.created_at, reverse=True)
    
    def get_correlations(self, alert_id: str) -> List[AlertCorrelation]:
        """Get correlations for an alert."""
        return self._correlation.get_correlations(alert_id)


# =============================================================================
# PREDEFINED ALERT RULES FOR RELEASE HEALTH
# =============================================================================

def create_release_health_alert_rules() -> List[AlertRule]:
    """Create standard alert rules for release health observability."""
    return [
        # Preflight alerts
        AlertRule(
            name="preflight_failure",
            description="Release preflight checks failed",
            dimension="release_preflight",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=600,
            correlation_types=[AlertCorrelationType.SAME_ROOT_CAUSE],
            runbook_url="/runbooks/preflight-failure",
        ),
        AlertRule(
            name="preflight_warning",
            description="Release preflight checks have warnings",
            dimension="release_preflight",
            condition='status == "degraded"',
            severity=AlertSeverity.WARNING,
            governance_scope="company",
            deduplication_window_seconds=600,
        ),
        
        # Migration alerts
        AlertRule(
            name="migration_failure",
            description="Database migration failed during release",
            dimension="migration",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
            correlation_types=[AlertCorrelationType.CASCADING],
            runbook_url="/runbooks/migration-failure",
        ),
        
        # Deployment alerts
        AlertRule(
            name="deployment_failure",
            description="Application deployment failed",
            dimension="deployment",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
            correlation_types=[AlertCorrelationType.CASCADING],
            runbook_url="/runbooks/deployment-failure",
        ),
        AlertRule(
            name="deployment_health_check_failure",
            description="Post-deployment health checks failed",
            dimension="deployment_health",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
        ),
        
        # Fingerprint mismatch alerts
        AlertRule(
            name="fingerprint_mismatch",
            description="Canonical fingerprint mismatch detected",
            dimension="fingerprint_integrity",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=600,
            correlation_types=[AlertCorrelationType.SAME_ROOT_CAUSE],
            runbook_url="/runbooks/fingerprint-mismatch",
        ),
        
        # Canonical reality health alerts
        AlertRule(
            name="canonical_integrity_degraded",
            description="Canonical reality integrity check degraded",
            dimension="canonical_reality",
            condition='status == "degraded"',
            severity=AlertSeverity.WARNING,
            governance_scope="company",
            deduplication_window_seconds=600,
        ),
        AlertRule(
            name="canonical_integrity_critical",
            description="Canonical reality integrity check critical",
            dimension="canonical_reality",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
            correlation_types=[AlertCorrelationType.SAME_ROOT_CAUSE],
        ),
        
        # Infrastructure health alerts
        AlertRule(
            name="database_unhealthy",
            description="Database health check failed",
            dimension="database",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
            correlation_types=[AlertCorrelationType.CASCADING, AlertCorrelationType.DEPENDENCY],
            runbook_url="/runbooks/database-unhealthy",
        ),
        AlertRule(
            name="infrastructure_degraded",
            description="Infrastructure health degraded",
            dimension="infrastructure",
            condition='status == "degraded"',
            severity=AlertSeverity.WARNING,
            governance_scope="company",
            deduplication_window_seconds=600,
        ),
        
        # Temporal integrity alerts
        AlertRule(
            name="temporal_integrity_violation",
            description="Temporal integrity violation detected",
            dimension="temporal_integrity",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
            correlation_types=[AlertCorrelationType.SAME_ROOT_CAUSE],
        ),
        
        # Provenance alerts
        AlertRule(
            name="provenance_chain_broken",
            description="Provenance chain broken",
            dimension="provenance",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=600,
        ),
        
        # Governance alerts
        AlertRule(
            name="governance_policy_violation",
            description="Governance policy violation detected",
            dimension="governance",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
        ),
        
        # Concurrency alerts
        AlertRule(
            name="concurrency_stuck_operations",
            description="Stuck operations detected",
            dimension="concurrency",
            condition='status == "degraded"',
            severity=AlertSeverity.WARNING,
            governance_scope="company",
            deduplication_window_seconds=600,
        ),
        
        # Recovery alerts
        AlertRule(
            name="recovery_backlog_high",
            description="Recovery backlog exceeds threshold",
            dimension="recovery",
            condition="current_value > threshold_warn",
            severity=AlertSeverity.WARNING,
            governance_scope="company",
            deduplication_window_seconds=600,
        ),
        AlertRule(
            name="recovery_failure",
            description="Recovery operation failed",
            dimension="recovery",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
        ),
        
        # Integration alerts
        AlertRule(
            name="integration_sync_failure",
            description="Integration sync failed",
            dimension="integrations",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
            correlation_types=[AlertCorrelationType.CASCADING],
        ),
        AlertRule(
            name="sync_freshness_stale",
            description="Integration sync data is stale",
            dimension="sync_freshness",
            condition="current_value > threshold_critical",
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
        ),
        
        # Company Brain alerts
        AlertRule(
            name="company_brain_unhealthy",
            description="Company Brain health check failed",
            dimension="company_brain",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=300,
        ),
        
        # Security alerts
        AlertRule(
            name="security_event_detected",
            description="Security event detected",
            dimension="security",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=60,
            correlation_types=[AlertCorrelationType.CASCADING],
        ),
        
        # Longitudinal integrity alerts
        AlertRule(
            name="longitudinal_integrity_violation",
            description="Longitudinal integrity violation detected",
            dimension="longitudinal_integrity",
            condition='status == "critical"',
            severity=AlertSeverity.CRITICAL,
            governance_scope="company",
            deduplication_window_seconds=600,
        ),
    ]


# Global alert engine instance
alert_engine = AlertEngine()

# Register default release health rules
for rule in create_release_health_alert_rules():
    alert_engine.register_rule(rule)