"""Health Evaluation Service for Production Observability & Alerting (Slice 2E).

Evaluates health across 13 dimensions:
1. infrastructure - Base infrastructure health
2. database - Database connectivity and performance
3. canonical_reality - Canonical company reality integrity
4. temporal_integrity - Temporal consistency and validity
5. provenance - Provenance chain completeness
6. governance - Governance policy compliance
7. concurrency - Concurrency control and stuck operations
8. recovery - Recovery system health
9. integrations - External integration health
10. company_brain - Company Brain service health
11. security - Security posture
12. deployment - Deployment system health
13. longitudinal_integrity - Longitudinal data integrity
"""

import logging
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Callable
from enum import Enum

from sqlalchemy import select, and_, or_, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.observability import HealthDimension, HEALTH_DIMENSIONS
from app.services.canonical_fingerprint import canonical_fingerprint_service
from app.services.release_safety_preflight import release_safety_preflight
from app.services.release_failure_recovery import release_failure_recovery_service
from app.services.release_deployment_orchestrator import release_deployment_orchestrator
from app.services.canonical_reality_integrity_service import canonical_reality_integrity_service
from app.validation.capability_contract import CapabilityDetector

logger = logging.getLogger("vcos.health_evaluation")


# =============================================================================
# HEALTH DIMENSIONS & CONFIGURATION
# =============================================================================

class HealthDimensionName(str, Enum):
    """13 health dimensions for VCOS observability."""
    INFRASTRUCTURE = "infrastructure"
    DATABASE = "database"
    CANONICAL_REALITY = "canonical_reality"
    TEMPORAL_INTEGRITY = "temporal_integrity"
    PROVENANCE = "provenance"
    GOVERNANCE = "governance"
    CONCURRENCY = "concurrency"
    RECOVERY = "recovery"
    INTEGRATIONS = "integrations"
    COMPANY_BRAIN = "company_brain"
    SECURITY = "security"
    DEPLOYMENT = "deployment"
    LONGITUDINAL_INTEGRITY = "longitudinal_integrity"


# All 13 dimensions
ALL_HEALTH_DIMENSIONS = [
    HealthDimensionName.INFRASTRUCTURE,
    HealthDimensionName.DATABASE,
    HealthDimensionName.CANONICAL_REALITY,
    HealthDimensionName.TEMPORAL_INTEGRITY,
    HealthDimensionName.PROVENANCE,
    HealthDimensionName.GOVERNANCE,
    HealthDimensionName.CONCURRENCY,
    HealthDimensionName.RECOVERY,
    HealthDimensionName.INTEGRATIONS,
    HealthDimensionName.COMPANY_BRAIN,
    HealthDimensionName.SECURITY,
    HealthDimensionName.DEPLOYMENT,
    HealthDimensionName.LONGITUDINAL_INTEGRITY,
]


@dataclass
class HealthCheckResult:
    """Result of a single health dimension check."""
    dimension: HealthDimensionName
    status: str  # healthy|degraded|critical|unknown
    current_value: float
    target_value: Optional[float] = None
    threshold_warn: Optional[float] = None
    threshold_critical: Optional[float] = None
    unit: Optional[str] = None
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    window_start: Optional[datetime] = None
    window_end: Optional[datetime] = None


@dataclass
class AggregateHealthReport:
    """Aggregate health report across all dimensions."""
    organization_id: str
    overall_status: str  # healthy|degraded|critical|unknown
    dimension_results: Dict[HealthDimensionName, HealthCheckResult]
    aggregate_fingerprint: str
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


# =============================================================================
# HEALTH EVALUATORS — One per dimension
# =============================================================================

class HealthEvaluator:
    """Base class for health dimension evaluators."""
    
    dimension: HealthDimensionName
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        """Evaluate health for this dimension."""
        raise NotImplementedError


class InfrastructureHealthEvaluator(HealthEvaluator):
    """Evaluate infrastructure health."""
    
    dimension = HealthDimensionName.INFRASTRUCTURE
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        # Check database connectivity
        try:
            await db.execute(text("SELECT 1"))
            db_healthy = True
        except Exception as e:
            db_healthy = False
            logger.warning(f"Database health check failed: {e}")
        
        # Check if we can query organizations table
        try:
            result = await db.execute(text("SELECT COUNT(*) FROM organizations WHERE id = :org_id"), {"org_id": organization_id})
            org_exists = result.scalar() > 0
        except Exception:
            org_exists = False
        
        status = "healthy" if (db_healthy and org_exists) else "critical"
        current_value = 1.0 if status == "healthy" else 0.0
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.5,
            threshold_critical=0.1,
            unit="boolean",
            evidence=[{"check": "database_connectivity", "result": db_healthy},
                      {"check": "organization_exists", "result": org_exists}],
        )


class DatabaseHealthEvaluator(HealthEvaluator):
    """Evaluate database health."""
    
    dimension = HealthDimensionName.DATABASE
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Connection pool status
        try:
            # Check for long-running queries
            result = await db.execute(text("""
                SELECT COUNT(*) FROM pg_stat_activity 
                WHERE state = 'active' AND now() - query_start > interval '30 seconds'
            """))
            long_queries = result.scalar() or 0
            checks.append({"check": "long_running_queries", "count": long_queries})
        except Exception:
            long_queries = -1
            checks.append({"check": "long_running_queries", "error": "unable to check"})
        
        # Check table sizes for key tables
        key_tables = ["organizations", "users", "employees", "canonical_operations"]
        table_healthy = True
        for table in key_tables:
            try:
                result = await db.execute(text(f"SELECT COUNT(*) FROM {table} WHERE organization_id = :org_id"), {"org_id": organization_id})
                count = result.scalar() or 0
                checks.append({"table": table, "row_count": count})
                if count == 0 and table in ["organizations"]:
                    table_healthy = False
            except Exception as e:
                checks.append({"table": table, "error": str(e)})
                table_healthy = False
        
        # Determine status
        if long_queries > 10 or not table_healthy:
            status = "critical"
        elif long_queries > 5:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.7,
            threshold_critical=0.3,
            unit="score",
            evidence=checks,
        )


class CanonicalRealityHealthEvaluator(HealthEvaluator):
    """Evaluate canonical reality integrity."""
    
    dimension = HealthDimensionName.CANONICAL_REALITY
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        # Run canonical integrity scan
        try:
            findings = await canonical_reality_integrity_service.run_integrity_scan(db, organization_id)
            
            violations = len(findings)
            checks_run = 7  # Number of check types
            checks_passed = checks_run - violations if violations <= checks_run else 0
            
            if checks_run > 0:
                pass_rate = max(0.0, checks_passed / checks_run)
            else:
                pass_rate = 0.0
            
            if violations > 10 or pass_rate < 0.5:
                status = "critical"
            elif violations > 0 or pass_rate < 0.9:
                status = "degraded"
            else:
                status = "healthy"
            
            current_value = pass_rate
            evidence = [{"violations": violations, "checks_run": checks_run, "checks_passed": checks_passed}]
            
        except Exception as e:
            logger.warning(f"Canonical reality scan failed: {e}")
            status = "critical"
            current_value = 0.0
            evidence = [{"error": str(e)}]
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="pass_rate",
            evidence=evidence,
        )


class TemporalIntegrityHealthEvaluator(HealthEvaluator):
    """Evaluate temporal integrity."""
    
    dimension = HealthDimensionName.TEMPORAL_INTEGRITY
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check for future-dated records that shouldn't be in future
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM company_decisions 
                WHERE organization_id = :org_id 
                AND approved_at > now() + interval '1 hour'
            """), {"org_id": organization_id})
            future_approved = result.scalar() or 0
            checks.append({"check": "future_approved_decisions", "count": future_approved})
        except Exception as e:
            checks.append({"check": "future_approved_decisions", "error": str(e)})
            future_approved = -1
        
        # Check for temporal ordering violations
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM canonical_operations co
                JOIN operation_attempts oa ON co.id = oa.operation_id
                WHERE co.organization_id = :org_id
                AND oa.started_at < co.created_at - interval '1 hour'
            """), {"org_id": organization_id})
            temporal_violations = result.scalar() or 0
            checks.append({"check": "temporal_ordering_violations", "count": temporal_violations})
        except Exception as e:
            checks.append({"check": "temporal_ordering_violations", "error": str(e)})
            temporal_violations = -1
        
        # Check for gaps in company_state_history
        try:
            result = await db.execute(text("""
                SELECT MAX(occurred_at) - MIN(occurred_at) as span,
                       COUNT(*) as count
                FROM company_state_history
                WHERE organization_id = :org_id
                AND occurred_at > now() - interval '7 days'
            """), {"org_id": organization_id})
            row = result.first()
            if row:
                span_hours = row.span.total_seconds() / 3600 if row.span else 0
                checks.append({"check": "state_history_span_hours", "span_hours": span_hours, "count": row.count})
        except Exception as e:
            checks.append({"check": "state_history_span", "error": str(e)})
        
        # Determine status
        critical_issues = 0
        if future_approved > 0:
            critical_issues += future_approved
        if temporal_violations > 0:
            critical_issues += temporal_violations
        
        if critical_issues > 5:
            status = "critical"
        elif critical_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


class ProvenanceHealthEvaluator(HealthEvaluator):
    """Evaluate provenance chain completeness."""
    
    dimension = HealthDimensionName.PROVENANCE
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check for operations without provenance
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM canonical_operations 
                WHERE organization_id = :org_id 
                AND (provenance IS NULL OR provenance = '{}')
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            missing_provenance = result.scalar() or 0
            checks.append({"check": "missing_provenance_24h", "count": missing_provenance})
        except Exception as e:
            checks.append({"check": "missing_provenance_24h", "error": str(e)})
            missing_provenance = -1
        
        # Check for broken provenance chains
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM company_decisions 
                WHERE organization_id = :org_id 
                AND (provenance IS NULL OR provenance = '{}')
                AND state IN ('approved', 'executed')
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            broken_chains = result.scalar() or 0
            checks.append({"check": "broken_provenance_chains", "count": broken_chains})
        except Exception as e:
            checks.append({"check": "broken_provenance_chains", "error": str(e)})
            broken_chains = -1
        
        # Check exact-once fingerprint collisions
        try:
            result = await db.execute(text("""
                SELECT fingerprint, COUNT(*) as cnt 
                FROM canonical_operations 
                WHERE organization_id = :org_id 
                GROUP BY fingerprint 
                HAVING COUNT(*) > 1
            """), {"org_id": organization_id})
            collisions = result.fetchall()
            checks.append({"check": "fingerprint_collisions", "count": len(collisions)})
        except Exception as e:
            checks.append({"check": "fingerprint_collisions", "error": str(e)})
            collisions = []
        
        # Determine status
        total_issues = (missing_provenance if missing_provenance > 0 else 0) + \
                      (broken_chains if broken_chains > 0 else 0) + \
                      len(collisions)
        
        if total_issues > 10:
            status = "critical"
        elif total_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


class GovernanceHealthEvaluator(HealthEvaluator):
    """Evaluate governance policy compliance."""
    
    dimension = HealthDimensionName.GOVERNANCE
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check for decisions without required approvals
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM company_decisions 
                WHERE organization_id = :org_id 
                AND state = 'executed'
                AND approver_label IS NULL OR approver_label = ''
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            unapproved_executions = result.scalar() or 0
            checks.append({"check": "unapproved_executions", "count": unapproved_executions})
        except Exception as e:
            checks.append({"check": "unapproved_executions", "error": str(e)})
            unapproved_executions = -1
        
        # Check for approval workflow violations
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM approval_workflow_instances 
                WHERE organization_id = :org_id 
                AND state = 'expired'
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            expired_workflows = result.scalar() or 0
            checks.append({"check": "expired_approval_workflows", "count": expired_workflows})
        except Exception as e:
            checks.append({"check": "expired_approval_workflows", "error": str(e)})
            expired_workflows = -1
        
        total_issues = (unapproved_executions if unapproved_executions > 0 else 0) + \
                      (expired_workflows if expired_workflows > 0 else 0)
        
        if total_issues > 5:
            status = "critical"
        elif total_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


class ConcurrencyHealthEvaluator(HealthEvaluator):
    """Evaluate concurrency control health."""
    
    dimension = HealthDimensionName.CONCURRENCY
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check for stuck operations
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM canonical_operations 
                WHERE organization_id = :org_id 
                AND state IN ('in_progress', 'pending')
                AND updated_at < now() - interval '1 hour'
            """), {"org_id": organization_id})
            stuck_operations = result.scalar() or 0
            checks.append({"check": "stuck_operations", "count": stuck_operations})
        except Exception as e:
            checks.append({"check": "stuck_operations", "error": str(e)})
            stuck_operations = -1
        
        # Check for operation attempt retries
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM operation_attempts 
                WHERE organization_id = :org_id 
                AND attempt_number > 3
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            high_retries = result.scalar() or 0
            checks.append({"check": "high_retry_operations", "count": high_retries})
        except Exception as e:
            checks.append({"check": "high_retry_operations", "error": str(e)})
            high_retries = -1
        
        # Check for lock contention (approximation)
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM pg_locks 
                WHERE NOT granted AND pid IN (
                    SELECT pid FROM pg_stat_activity WHERE state = 'active'
                )
            """))
            lock_waits = result.scalar() or 0
            checks.append({"check": "lock_waits", "count": lock_waits})
        except Exception as e:
            checks.append({"check": "lock_waits", "error": str(e)})
            lock_waits = -1
        
        total_issues = (stuck_operations if stuck_operations > 0 else 0) + \
                      (high_retries if high_retries > 0 else 0) + \
                      (lock_waits if lock_waits > 0 else 0)
        
        if total_issues > 10:
            status = "critical"
        elif total_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


class RecoveryHealthEvaluator(HealthEvaluator):
    """Evaluate recovery system health."""
    
    dimension = HealthDimensionName.RECOVERY
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check recovery backlog
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM restore_operations 
                WHERE organization_id = :org_id 
                AND state IN ('pending', 'in_progress')
            """), {"org_id": organization_id})
            pending_restores = result.scalar() or 0
            checks.append({"check": "pending_restores", "count": pending_restores})
        except Exception as e:
            checks.append({"check": "pending_restores", "error": str(e)})
            pending_restores = -1
        
        # Check failed recoveries
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM restore_operations 
                WHERE organization_id = :org_id 
                AND state = 'failed'
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            failed_restores = result.scalar() or 0
            checks.append({"check": "failed_restores_24h", "count": failed_restores})
        except Exception as e:
            checks.append({"check": "failed_restores_24h", "error": str(e)})
            failed_restores = -1
        
        # Check backup verification failures
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM backup_verification_results 
                WHERE organization_id = :org_id 
                AND verified = false
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            failed_verifications = result.scalar() or 0
            checks.append({"check": "failed_backup_verifications_24h", "count": failed_verifications})
        except Exception as e:
            checks.append({"check": "failed_backup_verifications_24h", "error": str(e)})
            failed_verifications = -1
        
        total_issues = (pending_restores if pending_restores > 10 else 0) + \
                      (failed_restores if failed_restores > 0 else 0) + \
                      (failed_verifications if failed_verifications > 0 else 0)
        
        if total_issues > 5:
            status = "critical"
        elif total_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


class IntegrationsHealthEvaluator(HealthEvaluator):
    """Evaluate external integrations health."""
    
    dimension = HealthDimensionName.INTEGRATIONS
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check connector instance states
        try:
            result = await db.execute(text("""
                SELECT state, COUNT(*) as cnt 
                FROM connector_instances 
                WHERE organization_id = :org_id 
                GROUP BY state
            """), {"org_id": organization_id})
            states = {row.state: row.cnt for row in result.fetchall()}
            checks.append({"check": "connector_states", "states": states})
            
            error_count = states.get("error", 0) + states.get("failed", 0)
            degraded_count = states.get("degraded", 0)
        except Exception as e:
            checks.append({"check": "connector_states", "error": str(e)})
            error_count = -1
            degraded_count = -1
        
        # Check sync run failures
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM sync_runs 
                WHERE organization_id = :org_id 
                AND status = 'failed'
                AND started_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            failed_syncs = result.scalar() or 0
            checks.append({"check": "failed_syncs_24h", "count": failed_syncs})
        except Exception as e:
            checks.append({"check": "failed_syncs_24h", "error": str(e)})
            failed_syncs = -1
        
        # Check external operation failures
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM external_operations 
                WHERE organization_id = :org_id 
                AND state = 'failed'
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            failed_external = result.scalar() or 0
            checks.append({"check": "failed_external_operations_24h", "count": failed_external})
        except Exception as e:
            checks.append({"check": "failed_external_operations_24h", "error": str(e)})
            failed_external = -1
        
        total_issues = (error_count if error_count > 0 else 0) + \
                      (degraded_count if degraded_count > 5 else 0) + \
                      (failed_syncs if failed_syncs > 0 else 0) + \
                      (failed_external if failed_external > 0 else 0)
        
        if total_issues > 10:
            status = "critical"
        elif total_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


class CompanyBrainHealthEvaluator(HealthEvaluator):
    """Evaluate Company Brain service health."""
    
    dimension = HealthDimensionName.COMPANY_BRAIN
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check company attention items
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM company_attention 
                WHERE organization_id = :org_id 
                AND state IN ('open', 'investigating')
            """), {"org_id": organization_id})
            open_attention = result.scalar() or 0
            checks.append({"check": "open_attention_items", "count": open_attention})
        except Exception as e:
            checks.append({"check": "open_attention_items", "error": str(e)})
            open_attention = -1
        
        # Check organizational learning evidence
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM learning_evidence 
                WHERE organization_id = :org_id 
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            recent_learning = result.scalar() or 0
            checks.append({"check": "recent_learning_evidence", "count": recent_learning})
        except Exception as e:
            checks.append({"check": "recent_learning_evidence", "error": str(e)})
            recent_learning = -1
        
        # Check canonical observations
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM canonical_observations 
                WHERE organization_id = :org_id 
                AND severity IN ('warning', 'critical')
                AND recorded_at > now() - interval '1 hour'
            """), {"org_id": organization_id})
            critical_observations = result.scalar() or 0
            checks.append({"check": "critical_observations_1h", "count": critical_observations})
        except Exception as e:
            checks.append({"check": "critical_observations_1h", "error": str(e)})
            critical_observations = -1
        
        total_issues = (open_attention if open_attention > 10 else 0) + \
                      (critical_observations if critical_observations > 0 else 0)
        
        # Learning evidence is positive
        if recent_learning > 0:
            total_issues = max(0, total_issues - 1)
        
        if total_issues > 10:
            status = "critical"
        elif total_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


class SecurityHealthEvaluator(HealthEvaluator):
    """Evaluate security posture."""
    
    dimension = HealthDimensionName.SECURITY
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check for security events
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM canonical_observations 
                WHERE organization_id = :org_id 
                AND observation_type = 'security_event'
                AND severity IN ('warning', 'critical')
                AND recorded_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            security_events = result.scalar() or 0
            checks.append({"check": "security_events_24h", "count": security_events})
        except Exception as e:
            checks.append({"check": "security_events_24h", "error": str(e)})
            security_events = -1
        
        # Check for failed authentication attempts (if tracked)
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM canonical_observations 
                WHERE organization_id = :org_id 
                AND details_json->>'auth_failed' = 'true'
                AND recorded_at > now() - interval '1 hour'
            """), {"org_id": organization_id})
            auth_failures = result.scalar() or 0
            checks.append({"check": "auth_failures_1h", "count": auth_failures})
        except Exception as e:
            checks.append({"check": "auth_failures_1h", "error": str(e)})
            auth_failures = -1
        
        # Check for privilege escalation attempts
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM company_authorizations 
                WHERE organization_id = :org_id 
                AND authorization_type = 'full'
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            full_authorizations = result.scalar() or 0
            checks.append({"check": "full_authorizations_24h", "count": full_authorizations})
        except Exception as e:
            checks.append({"check": "full_authorizations_24h", "error": str(e)})
            full_authorizations = -1
        
        total_issues = (security_events if security_events > 0 else 0) + \
                      (auth_failures if auth_failures > 10 else 0)
        
        if total_issues > 5:
            status = "critical"
        elif total_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


class DeploymentHealthEvaluator(HealthEvaluator):
    """Evaluate deployment system health."""
    
    dimension = HealthDimensionName.DEPLOYMENT
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check recent deployment failures
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM canonical_observations 
                WHERE organization_id = :org_id 
                AND observation_type IN ('deployment', 'operation_lifecycle')
                AND severity = 'critical'
                AND recorded_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            deployment_failures = result.scalar() or 0
            checks.append({"check": "deployment_failures_24h", "count": deployment_failures})
        except Exception as e:
            checks.append({"check": "deployment_failures_24h", "error": str(e)})
            deployment_failures = -1
        
        # Check for rollback operations
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM restore_operations 
                WHERE organization_id = :org_id 
                AND metadata_json->>'reason' = 'deployment_rollback'
                AND created_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            rollbacks = result.scalar() or 0
            checks.append({"check": "deployment_rollbacks_24h", "count": rollbacks})
        except Exception as e:
            checks.append({"check": "deployment_rollbacks_24h", "error": str(e)})
            rollbacks = -1
        
        # Check health check failures post-deployment
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM canonical_observations 
                WHERE organization_id = :org_id 
                AND observation_type = 'health_check'
                AND severity IN ('warning', 'critical')
                AND recorded_at > now() - interval '24 hours'
            """), {"org_id": organization_id})
            health_check_failures = result.scalar() or 0
            checks.append({"check": "post_deployment_health_failures_24h", "count": health_check_failures})
        except Exception as e:
            checks.append({"check": "post_deployment_health_failures_24h", "error": str(e)})
            health_check_failures = -1
        
        total_issues = (deployment_failures if deployment_failures > 0 else 0) + \
                      (rollbacks if rollbacks > 0 else 0) + \
                      (health_check_failures if health_check_failures > 5 else 0)
        
        if total_issues > 3:
            status = "critical"
        elif total_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


class LongitudinalIntegrityHealthEvaluator(HealthEvaluator):
    """Evaluate longitudinal data integrity."""
    
    dimension = HealthDimensionName.LONGITUDINAL_INTEGRITY
    
    async def evaluate(self, db: AsyncSession, organization_id: str) -> HealthCheckResult:
        checks = []
        
        # Check for gaps in company_state_history
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM company_state_history csh1
                WHERE organization_id = :org_id
                AND NOT EXISTS (
                    SELECT 1 FROM company_state_history csh2
                    WHERE csh2.organization_id = csh1.organization_id
                    AND csh2.occurred_at = csh1.occurred_at + interval '1 hour'
                )
                AND csh1.occurred_at > now() - interval '7 days'
            """), {"org_id": organization_id})
            temporal_gaps = result.scalar() or 0
            checks.append({"check": "temporal_gaps_7d", "count": temporal_gaps})
        except Exception as e:
            checks.append({"check": "temporal_gaps_7d", "error": str(e)})
            temporal_gaps = -1
        
        # Check for supersession chain integrity
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM company_decisions 
                WHERE organization_id = :org_id 
                AND superseded_at IS NOT NULL
                AND superseded_by IS NULL
            """), {"org_id": organization_id})
            broken_supersession = result.scalar() or 0
            checks.append({"check": "broken_supersession_chains", "count": broken_supersession})
        except Exception as e:
            checks.append({"check": "broken_supersession_chains", "error": str(e)})
            broken_supersession = -1
        
        # Check for learning evidence without organizational learning
        try:
            result = await db.execute(text("""
                SELECT COUNT(*) FROM learning_evidence le
                WHERE organization_id = :org_id
                AND NOT EXISTS (
                    SELECT 1 FROM organizational_learning ol
                    WHERE ol.id = le.learning_id
                )
            """), {"org_id": organization_id})
            orphan_evidence = result.scalar() or 0
            checks.append({"check": "orphan_learning_evidence", "count": orphan_evidence})
        except Exception as e:
            checks.append({"check": "orphan_learning_evidence", "error": str(e)})
            orphan_evidence = -1
        
        total_issues = (temporal_gaps if temporal_gaps > 0 else 0) + \
                      (broken_supersession if broken_supersession > 0 else 0) + \
                      (orphan_evidence if orphan_evidence > 0 else 0)
        
        if total_issues > 5:
            status = "critical"
        elif total_issues > 0:
            status = "degraded"
        else:
            status = "healthy"
        
        current_value = 1.0 if status == "healthy" else (0.5 if status == "degraded" else 0.0)
        
        return HealthCheckResult(
            dimension=self.dimension,
            status=status,
            current_value=current_value,
            target_value=1.0,
            threshold_warn=0.9,
            threshold_critical=0.5,
            unit="score",
            evidence=checks,
        )


# =============================================================================
# HEALTH EVALUATION SERVICE
# =============================================================================

class HealthEvaluationService(CapabilityDetector):
    """Service for evaluating health across all 13 dimensions."""
    
    def __init__(self):
        super().__init__()
        self._evaluators: Dict[HealthDimensionName, HealthEvaluator] = {
            HealthDimensionName.INFRASTRUCTURE: InfrastructureHealthEvaluator(),
            HealthDimensionName.DATABASE: DatabaseHealthEvaluator(),
            HealthDimensionName.CANONICAL_REALITY: CanonicalRealityHealthEvaluator(),
            HealthDimensionName.TEMPORAL_INTEGRITY: TemporalIntegrityHealthEvaluator(),
            HealthDimensionName.PROVENANCE: ProvenanceHealthEvaluator(),
            HealthDimensionName.GOVERNANCE: GovernanceHealthEvaluator(),
            HealthDimensionName.CONCURRENCY: ConcurrencyHealthEvaluator(),
            HealthDimensionName.RECOVERY: RecoveryHealthEvaluator(),
            HealthDimensionName.INTEGRATIONS: IntegrationsHealthEvaluator(),
            HealthDimensionName.COMPANY_BRAIN: CompanyBrainHealthEvaluator(),
            HealthDimensionName.SECURITY: SecurityHealthEvaluator(),
            HealthDimensionName.DEPLOYMENT: DeploymentHealthEvaluator(),
            HealthDimensionName.LONGITUDINAL_INTEGRITY: LongitudinalIntegrityHealthEvaluator(),
        }
    
    def get_evaluator(self, dimension: HealthDimensionName) -> Optional[HealthEvaluator]:
        """Get evaluator for a dimension."""
        return self._evaluators.get(dimension)
    
    def list_dimensions(self) -> List[HealthDimensionName]:
        """List all supported dimensions."""
        return ALL_HEALTH_DIMENSIONS
    
    async def evaluate_dimension(
        self,
        db: AsyncSession,
        organization_id: str,
        dimension: HealthDimensionName,
    ) -> HealthCheckResult:
        """Evaluate a single health dimension with transaction isolation."""
        evaluator = self._evaluators.get(dimension)
        if not evaluator:
            return HealthCheckResult(
                dimension=dimension,
                status="unknown",
                current_value=0.0,
                evidence=[{"error": f"No evaluator for dimension {dimension.value}"}],
            )
        
        # Use savepoint for transaction isolation
        # This ensures one evaluator's failure doesn't poison the session for others
        try:
            # Create a savepoint for this evaluator
            await db.execute(text("SAVEPOINT health_eval"))
            result = await evaluator.evaluate(db, organization_id)
            await db.execute(text("RELEASE SAVEPOINT health_eval"))
            return result
        except Exception as e:
            # Rollback to savepoint on failure
            try:
                await db.execute(text("ROLLBACK TO SAVEPOINT health_eval"))
            except Exception:
                pass
            logger.error(f"Health evaluation failed for {dimension.value}: {e}")
            return HealthCheckResult(
                dimension=dimension,
                status="unknown",  # Use "unknown" for evaluator failure, not "critical"
                current_value=0.0,
                evidence=[{"error": str(e), "evaluator_failure": True}],
            )
    
    async def evaluate_all(
        self,
        db: AsyncSession,
        organization_id: str,
        dimensions: Optional[List[HealthDimensionName]] = None,
    ) -> AggregateHealthReport:
        """Evaluate all health dimensions for an organization."""
        dims = dimensions or ALL_HEALTH_DIMENSIONS
        
        results = {}
        for dim in dims:
            result = await self.evaluate_dimension(db, organization_id, dim)
            results[dim] = result
        
        # Compute overall status
        statuses = [r.status for r in results.values()]
        if "critical" in statuses:
            overall_status = "critical"
        elif "degraded" in statuses:
            overall_status = "degraded"
        elif "unknown" in statuses:
            overall_status = "unknown"
        else:
            overall_status = "healthy"
        
        # Compute aggregate fingerprint
        fingerprint_data = {
            "organization_id": organization_id,
            "dimensions": {
                dim.value: {
                    "status": result.status,
                    "current_value": result.current_value,
                }
                for dim, result in results.items()
            },
        }
        import hashlib, json
        canonical = json.dumps(fingerprint_data, sort_keys=True, separators=(",", ":"))
        aggregate_fingerprint = hashlib.sha256(canonical.encode()).hexdigest()[:64]
        
        return AggregateHealthReport(
            organization_id=organization_id,
            overall_status=overall_status,
            dimension_results=results,
            aggregate_fingerprint=aggregate_fingerprint,
        )
    
    async def store_health_dimensions(
        self,
        db: AsyncSession,
        report: AggregateHealthReport,
    ) -> List[HealthDimension]:
        """Store health dimension results in database."""
        stored = []
        
        for dimension, result in report.dimension_results.items():
            hd = HealthDimension(
                organization_id=report.organization_id,
                dimension=dimension.value,
                scope_type="company",
                scope_id=None,
                status=result.status,
                current_value=result.current_value,
                target_value=result.target_value,
                threshold_warn=result.threshold_warn,
                threshold_critical=result.threshold_critical,
                unit=result.unit,
                evidence_json=result.evidence,
                provenance_json={"evaluation_id": report.aggregate_fingerprint},
                recorded_at=result.checked_at,
                window_start=result.window_start,
                window_end=result.window_end,
                fingerprint=self._compute_fingerprint(report.organization_id, dimension.value, result),
            )
            db.add(hd)
            stored.append(hd)
        
        await db.commit()
        return stored
    
    def _compute_fingerprint(self, org_id: str, dimension: str, result: HealthCheckResult) -> str:
        import hashlib, json
        data = {
            "organization_id": org_id,
            "dimension": dimension,
            "status": result.status,
            "current_value": result.current_value,
            "checked_at": result.checked_at.isoformat(),
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:160]


# Global instance
health_evaluation_service = HealthEvaluationService()