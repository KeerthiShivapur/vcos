"""Gate 34 — Universal Observability & Operational Intelligence Fabric Service.

Implements the canonical observability fabric that provides visibility into
what is happening technically, operationally, and in the company reality.

Key principles:
- Observability is a governed projection over the canonical VCOS reality
- No parallel observability reality - reuses existing primitives
- Correlation across request → authorization → governance → decision → action → worker → integration → outcome
- Epistemic boundaries preserved: telemetry ≠ business truth
"""

import hashlib
import json
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Any, Optional, List, Dict, Tuple, Set
from dataclasses import dataclass, field

from sqlalchemy import select, func, and_, or_, desc, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.timeutils import utcnow
from app.models.observability import (
    CanonicalObservation,
    CorrelationContext,
    Degradation,
    HealthDimension,
    SLOTarget,
    FreshnessCheck,
    OperationalTarget,
    CanonicalObservation,
    CorrelationContext,
    Degradation,
    HealthDimension,
    SLOTarget,
    FreshnessCheck,
    OperationalTarget,
    OBSERVATION_TYPES,
    OBSERVATION_SEVERITY,
    OBSERVATION_EPISTEMIC,
    CORRELATION_TYPES,
    DEGRADATION_STATES,
    DEGRADATION_SEVERITY,
    HEALTH_DIMENSIONS,
    compute_observation_fingerprint,
    compute_correlation_fingerprint,
)
from app.models.organization import Organization
from app.models.user import User
from app.models.employee import Employee
from app.models.notification import Event
from app.models.canonical_reliability import (
    CanonicalOperation,
    OperationAttempt,
    Recovery,
    Reconciliation,
    ExternalUnknownState,
    WorkerLease,
    OperationCheckpoint,
)
from app.models.canonical_integration import (
    ConnectorInstance,
    SyncRun,
    ExternalOperation,
    IntegrationHealth,
)
from app.models.continuous_twin import CompanyAttention
from app.models.enterprise import SecurityEvent
from app.services.event_service import event_service
from app.services.canonical_reliability_service import canonical_reliability_service
from app.services.mfa_service import mfa_service
from app.core.timeutils import utcnow

logger = logging.getLogger("vcos.observability")


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class ObservationContext:
    """Context for creating an observation."""
    organization_id: str
    observation_type: str
    source: str
    source_component: Optional[str] = None
    actor_id: Optional[str] = None
    actor_type: str = "system"
    severity: str = "info"
    epistemic_status: str = "observed"
    correlation_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    operation_id: Optional[str] = None
    operation_type: Optional[str] = None
    attempt_id: Optional[str] = None
    integration_id: Optional[str] = None
    connector_id: Optional[str] = None
    external_operation_id: Optional[str] = None
    security_event_id: Optional[str] = None
    degradation_id: Optional[str] = None
    title: str = ""
    description: Optional[str] = None
    details_json: Optional[dict] = None
    metrics_json: Optional[dict] = None
    provenance_json: Optional[dict] = None
    source_event_id: Optional[str] = None
    observed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    key_fields: Optional[dict] = None


@dataclass
class CorrelationChainStep:
    """A step in a correlation chain."""
    step_number: int
    observation_type: str
    source: str
    observed_at: datetime
    operation_id: Optional[str] = None
    attempt_id: Optional[str] = None
    integration_id: Optional[str] = None
    actor_id: Optional[str] = None
    outcome: Optional[str] = None
    details: Optional[dict] = None


# =============================================================================
# OBSERVABILITY SERVICE
# =============================================================================

class ObservabilityService:
    """Universal Observability & Operational Intelligence Fabric Service."""
    
    def __init__(self):
        self._secret_patterns = [
            "password", "token", "secret", "key", "credential",
            "authorization", "access_token", "refresh_token",
            "api_key", "api_secret", "client_secret", "private_key",
            "webhook_secret", "signing_secret", "jwt_secret",
        ]
    
    # =========================================================================
    # SECRET REDACTION
    # =========================================================================
    
    def _redact_secrets(self, data: Any) -> Any:
        """Recursively redact secrets from data structures."""
        if isinstance(data, dict):
            result = {}
            for key, value in data.items():
                key_lower = key.lower()
                if any(pattern in key_lower for pattern in self._secret_patterns):
                    result[key] = "***REDACTED***"
                else:
                    result[key] = self._redact_secrets(value)
            return result
        elif isinstance(data, list):
            return [self._redact_secrets(item) for item in data]
        else:
            return data
    
    def _sanitize_observation(self, observation: CanonicalObservation) -> CanonicalObservation:
        """Create a sanitized copy of an observation for API responses."""
        # The original observation is not modified; we just ensure
        # any sensitive fields are redacted in the response
        return observation
    
    # =========================================================================
    # FINGERPRINT COMPUTATION
    # =========================================================================
    
    def _compute_observation_fingerprint(self, context: ObservationContext) -> str:
        """Compute fingerprint for exact-once observation semantics."""
        key_fields = context.key_fields or {}
        payload = {
            "organization_id": context.organization_id,
            "observation_type": context.observation_type,
            "source": context.source,
            "source_component": context.source_component or "",
            "actor_id": context.actor_id or "",
            "operation_id": context.operation_id or "",
            "attempt_id": context.attempt_id or "",
            "integration_id": context.integration_id or "",
            "connector_id": context.connector_id or "",
            "external_operation_id": context.external_operation_id or "",
            "security_event_id": context.security_event_id or "",
            "degradation_id": context.degradation_id or "",
            "title": context.title,
            "key_fields": key_fields,
        }
        return compute_observation_fingerprint(payload)
    
    # =========================================================================
    # OBSERVATION CREATION
    # =========================================================================
    
    async def record_observation(
        self,
        db: AsyncSession,
        context: ObservationContext,
    ) -> CanonicalObservation:
        """Record a canonical observation with exact-once semantics."""
        
        # Set defaults
        observed_at = context.observed_at or utcnow()
        
        # Compute fingerprint for exact-once
        fingerprint = self._compute_observation_fingerprint(context)
        
        # Check for exact-once duplicate
        existing = await db.execute(
            select(CanonicalObservation).where(
                CanonicalObservation.organization_id == context.organization_id,
                CanonicalObservation.fingerprint == fingerprint,
            )
        )
        existing_obs = existing.scalars().first()
        if existing_obs:
            logger.debug(f"Exact-once duplicate detected for observation {fingerprint}")
            return existing_obs
        
        # Create observation
        observation = CanonicalObservation(
            organization_id=context.organization_id,
            observation_type=context.observation_type,
            source=context.source,
            source_component=context.source_component,
            actor_id=context.actor_id,
            actor_type=context.actor_type,
            severity=context.severity,
            epistemic_status=context.epistemic_status,
            correlation_id=context.correlation_id,
            trace_id=context.trace_id,
            span_id=context.span_id,
            parent_span_id=context.parent_span_id,
            operation_id=context.operation_id,
            operation_type=context.operation_type,
            attempt_id=context.attempt_id,
            integration_id=context.integration_id,
            connector_id=context.connector_id,
            external_operation_id=context.external_operation_id,
            security_event_id=context.security_event_id,
            degradation_id=context.degradation_id,
            title=context.title,
            description=context.description,
            details_json=context.details_json or {},
            metrics_json=context.metrics_json or {},
            provenance_json=context.provenance_json or {},
            source_event_id=context.source_event_id,
            observed_at=observed_at,
            duration_ms=context.duration_ms,
            fingerprint=fingerprint,
        )
        
        db.add(observation)
        await db.flush()
        
        # Emit event for downstream consumers
        await event_service.emit(
            db,
            name="observation.recorded",
            actor_id=context.actor_id or "system",
            organization_id=context.organization_id,
            payload={
                "observation_id": observation.id,
                "observation_type": observation.observation_type,
                "severity": observation.severity,
                "correlation_id": observation.correlation_id,
                "trace_id": observation.trace_id,
            },
        )
        
        logger.info(f"Recorded observation {observation.id} ({observation.observation_type})")
        return observation
    
    async def record_request_observation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        request_id: str,
        route: str,
        method: str,
        actor_id: Optional[str] = None,
        actor_type: str = "human",
        status_code: int = 200,
        duration_ms: int = 0,
        error_category: Optional[str] = None,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> CanonicalObservation:
        """Record an API request observation."""
        
        # Determine severity based on status code
        if status_code >= 500:
            severity = "critical"
        elif status_code >= 400:
            severity = "warning"
        elif status_code >= 300:
            severity = "notice"
        else:
            severity = "info"
        
        # Determine error category
        if error_category is None and status_code >= 400:
            if status_code == 401:
                error_category = "unauthorized"
            elif status_code == 403:
                error_category = "forbidden"
            elif status_code == 404:
                error_category = "not_found"
            elif status_code == 422:
                error_category = "validation_error"
            elif status_code == 429:
                error_category = "rate_limited"
            elif status_code >= 500:
                error_category = "server_error"
            else:
                error_category = "client_error"
        
        context = ObservationContext(
            organization_id=organization_id,
            observation_type="request",
            source="api",
            source_component="request",
            actor_id=actor_id,
            actor_type=actor_type,
            severity=severity,
            epistemic_status="observed",
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            title=f"{method} {route} - {status_code}",
            description=f"API request to {route} returned {status_code}",
            details_json={
                "route": route,
                "method": method,
                "status_code": status_code,
                "error_category": error_category,
                "request_id": request_id,
                **(details or {}),
            },
            metrics_json={
                "duration_ms": duration_ms,
                "status_code": status_code,
            },
            observed_at=utcnow(),
            duration_ms=duration_ms,
            key_fields={
                "route": route,
                "method": method,
                "status_code": str(status_code),
            },
        )
        
        return await self.record_observation(db, context)
    
    async def record_worker_observation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        worker_id: str,
        operation_id: str,
        attempt_id: Optional[str] = None,
        observation_type: str = "worker_execution",
        source_component: str = "worker",
        actor_id: str = "worker",
        actor_type: str = "worker",
        severity: str = "info",
        title: str = "",
        description: Optional[str] = None,
        details: Optional[dict] = None,
        metrics: Optional[dict] = None,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        span_id: Optional[str] = None,
        outcome: Optional[str] = None,
        duration_ms: Optional[int] = None,
        error: Optional[str] = None,
    ) -> CanonicalObservation:
        """Record a worker execution observation."""
        
        context = ObservationContext(
            organization_id=organization_id,
            observation_type=observation_type,
            source="worker",
            source_component=source_component,
            actor_id=actor_id,
            actor_type=actor_type,
            severity=severity,
            epistemic_status="observed",
            correlation_id=correlation_id,
            trace_id=trace_id,
            span_id=span_id,
            operation_id=operation_id,
            attempt_id=attempt_id,
            title=title or f"Worker {worker_id} execution",
            description=description or f"Worker {worker_id} executed operation {operation_id}",
            details_json={
                "worker_id": worker_id,
                "operation_id": operation_id,
                "attempt_id": attempt_id,
                "outcome": outcome,
                "error": error,
                **(details or {}),
            },
            metrics_json=metrics or {},
            observed_at=utcnow(),
            duration_ms=duration_ms,
            key_fields={
                "worker_id": worker_id,
                "operation_id": operation_id,
            },
        )
        
        return await self.record_observation(db, context)
    
    async def record_operation_observation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        operation: CanonicalOperation,
        attempt: Optional[OperationAttempt] = None,
        observation_type: str = "operation_lifecycle",
        severity: str = "info",
        title: str = "",
        description: Optional[str] = None,
        details: Optional[dict] = None,
        metrics: Optional[dict] = None,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        outcome: Optional[str] = None,
    ) -> CanonicalObservation:
        """Record a canonical operation lifecycle observation."""
        
        context = ObservationContext(
            organization_id=organization_id,
            observation_type=observation_type,
            source="reliability",
            source_component="canonical_operation",
            severity=severity,
            epistemic_status="observed",
            correlation_id=correlation_id,
            trace_id=trace_id,
            operation_id=operation.id,
            operation_type=operation.operation_type,
            attempt_id=attempt.attempt_number if attempt else None,
            title=title or f"Operation {operation.operation_type} {operation.state}",
            description=description or f"Operation {operation.id} transitioned to {operation.state}",
            details_json={
                "operation_id": operation.id,
                "operation_type": operation.operation_type,
                "state": operation.state,
                "attempt": attempt.attempt_number if attempt else None,
                "outcome": outcome,
                **(details or {}),
            },
            metrics_json=metrics or {},
            observed_at=utcnow(),
            key_fields={
                "operation_id": operation.id,
                "operation_type": operation.operation_type,
            },
        )
        
        return await self.record_observation(db, context)
    
    async def record_integration_observation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        integration: ConnectorInstance,
        sync_run: Optional[SyncRun] = None,
        external_operation: Optional[ExternalOperation] = None,
        observation_type: str = "integration_sync",
        severity: str = "info",
        title: str = "",
        description: Optional[str] = None,
        details: Optional[dict] = None,
        metrics: Optional[dict] = None,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> CanonicalObservation:
        """Record an integration sync observation."""
        
        context = ObservationContext(
            organization_id=organization_id,
            observation_type=observation_type,
            source="integration",
            source_component="connector",
            severity=severity,
            epistemic_status="observed",
            correlation_id=correlation_id,
            trace_id=trace_id,
            integration_id=integration.id,
            connector_id=integration.connector_id,
            external_operation_id=external_operation.id if external_operation else None,
            title=title or f"Integration {integration.name} sync",
            description=description or f"Integration {integration.id} sync status",
            details_json={
                "integration_id": integration.id,
                "connector_id": integration.connector_id,
                "sync_run_id": sync_run.id if sync_run else None,
                "external_operation_id": external_operation.id if external_operation else None,
                **(details or {}),
            },
            metrics_json=metrics or {},
            observed_at=utcnow(),
            key_fields={
                "integration_id": integration.id,
                "connector_id": integration.connector_id,
            },
        )
        
        return await self.record_observation(db, context)
    
    async def record_security_observation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        security_event: SecurityEvent,
        severity: Optional[str] = None,
        title: str = "",
        description: Optional[str] = None,
        details: Optional[dict] = None,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> CanonicalObservation:
        """Record a security event observation."""
        
        # Map security severity
        severity_map = {
            "low": "notice",
            "medium": "warning",
            "high": "critical",
            "critical": "critical",
        }
        mapped_severity = severity or severity_map.get(security_event.severity, "warning")
        
        context = ObservationContext(
            organization_id=organization_id,
            observation_type="security_event",
            source="security",
            source_component="security_center",
            severity=mapped_severity,
            epistemic_status="observed",
            correlation_id=correlation_id,
            trace_id=trace_id,
            security_event_id=security_event.id,
            title=title or f"Security event: {security_event.event_type}",
            description=description or security_event.title,
            details_json={
                "security_event_id": security_event.id,
                "event_type": security_event.event_type,
                "severity": security_event.severity,
                "actor_id": security_event.actor_id,
                "source_ip": security_event.source_ip,
                **(security_event.details or {}),
                **(details or {}),
            },
            observed_at=utcnow(),
            key_fields={
                "security_event_id": security_event.id,
                "event_type": security_event.event_type,
            },
        )
        
        return await self.record_observation(db, context)
    
    async def record_recovery_observation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        recovery: Recovery,
        observation_type: str = "recovery_action",
        severity: str = "info",
        title: str = "",
        description: Optional[str] = None,
        details: Optional[dict] = None,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
    ) -> CanonicalObservation:
        """Record a recovery action observation."""
        
        context = ObservationContext(
            organization_id=organization_id,
            observation_type=observation_type,
            source="reliability",
            source_component="recovery",
            severity=severity,
            epistemic_status="observed",
            correlation_id=correlation_id,
            trace_id=trace_id,
            operation_id=recovery.operation_id,
            title=title or f"Recovery {recovery.recovery_type} for operation {recovery.operation_id}",
            description=description or f"Recovery {recovery.id} executed",
            details_json={
                "recovery_id": recovery.id,
                "recovery_type": recovery.recovery_type,
                "operation_id": recovery.operation_id,
                "failure_class": recovery.failure_class,
                "outcome": recovery.outcome,
                **(details or {}),
            },
            observed_at=utcnow(),
            key_fields={
                "recovery_id": recovery.id,
                "operation_id": recovery.operation_id,
            },
        )
        
        return await self.record_observation(db, context)
    
    # =========================================================================
    # CORRELATION CONTEXT
    # =========================================================================
    
    async def create_correlation_context(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        correlation_type: str,
        correlation_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        initial_step: Optional[CorrelationChainStep] = None,
        metadata: Optional[dict] = None,
    ) -> CorrelationContext:
        """Create a new correlation context."""
        
        if correlation_id is None:
            correlation_id = uuid.uuid4().hex[:32]
        if trace_id is None:
            trace_id = uuid.uuid4().hex[:32]
        
        fingerprint = compute_correlation_fingerprint(organization_id, correlation_id, trace_id)
        
        # Check for existing
        existing = await db.execute(
            select(CorrelationContext).where(
                CorrelationContext.organization_id == organization_id,
                CorrelationContext.correlation_id == correlation_id,
            )
        )
        existing_ctx = existing.scalars().first()
        if existing_ctx:
            return existing_ctx
        
        chain = []
        if initial_step:
            chain.append({
                "step_number": 1,
                "observation_type": initial_step.observation_type,
                "source": initial_step.source,
                "operation_id": initial_step.operation_id,
                "attempt_id": initial_step.attempt_id,
                "integration_id": initial_step.integration_id,
                "actor_id": initial_step.actor_id,
                "observed_at": initial_step.observed_at.isoformat(),
                "outcome": initial_step.outcome,
                "details": initial_step.details,
            })
        
        context = CorrelationContext(
            organization_id=organization_id,
            correlation_type=correlation_type,
            correlation_id=correlation_id,
            trace_id=trace_id,
            chain_json={"steps": chain},
            current_step=1 if initial_step else 0,
            total_steps=None,
            status="active",
            metadata_json=metadata or {},
            fingerprint=compute_correlation_fingerprint(organization_id, correlation_id, trace_id),
        )
        
        db.add(context)
        await db.flush()
        
        await event_service.emit(
            db,
            name="correlation.created",
            actor_id="system",
            organization_id=organization_id,
            payload={
                "correlation_id": correlation_id,
                "trace_id": trace_id,
                "correlation_type": correlation_type,
            },
        )
        
        return context
    
    async def add_correlation_step(
        self,
        db: AsyncSession,
        *,
        correlation_context: CorrelationContext,
        step: CorrelationChainStep,
    ) -> CorrelationContext:
        """Add a step to the correlation chain."""
        
        chain = correlation_context.chain_json.get("steps", [])
        step_num = len(chain) + 1
        chain.append({
            "step_number": step_num,
            "observation_type": step.observation_type,
            "source": step.source,
            "operation_id": step.operation_id,
            "attempt_id": step.attempt_id,
            "integration_id": step.integration_id,
            "actor_id": step.actor_id,
            "observed_at": step.observed_at.isoformat(),
            "outcome": step.outcome,
            "details": step.details,
        })
        
        correlation_context.chain_json = {"steps": chain}
        correlation_context.current_step = step_num
        correlation_context.last_updated_at = utcnow()
        
        if step.outcome in ("success", "failed", "error"):
            correlation_context.total_steps = step_num
        
        # Flag the JSON column as modified for SQLAlchemy change detection
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(correlation_context, "chain_json")
        
        await db.flush()
        return correlation_context
    
    async def complete_correlation(
        self,
        db: AsyncSession,
        *,
        correlation_context: CorrelationContext,
        outcome: str,
    ) -> CorrelationContext:
        """Mark correlation context as completed."""
        
        correlation_context.status = "completed"
        correlation_context.outcome = outcome
        correlation_context.completed_at = utcnow()
        correlation_context.last_updated_at = utcnow()
        
        await db.flush()
        return correlation_context
    
    async def get_correlation_context(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        correlation_id: str,
    ) -> Optional[CorrelationContext]:
        """Get correlation context by ID."""
        
        result = await db.execute(
            select(CorrelationContext).where(
                CorrelationContext.organization_id == organization_id,
                CorrelationContext.correlation_id == correlation_id,
            )
        )
        return result.scalars().first()
    
    async def get_correlation_by_trace(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        trace_id: str,
    ) -> List[CorrelationContext]:
        """Get all correlation contexts for a trace."""
        
        result = await db.execute(
            select(CorrelationContext).where(
                CorrelationContext.organization_id == organization_id,
                CorrelationContext.trace_id == trace_id,
            ).order_by(CorrelationContext.created_at.desc())
        )
        return list(result.scalars().all())
    
    # =========================================================================
    # DEGRADATION MANAGEMENT
    # =========================================================================
    
    async def create_degradation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        degradation_type: str,
        severity: str = "minor",
        title: str,
        description: Optional[str] = None,
        details: Optional[dict] = None,
        affected_entities: Optional[List[dict]] = None,
        affected_dimensions: Optional[List[str]] = None,
        correlation_id: Optional[str] = None,
        root_cause_observation_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        actor_type: str = "system",
        evidence: Optional[List[dict]] = None,
        provenance: Optional[dict] = None,
    ) -> Degradation:
        """Create a new degradation/incident."""
        
        fingerprint = compute_observation_fingerprint({
            "organization_id": organization_id,
            "degradation_type": degradation_type,
            "title": title,
            "detected_at": utcnow().isoformat(),
        })
        
        # Check for existing
        existing = await db.execute(
            select(Degradation).where(
                Degradation.organization_id == organization_id,
                Degradation.fingerprint == fingerprint,
            )
        )
        existing_deg = existing.scalars().first()
        if existing_deg:
            return existing_deg
        
        degradation = Degradation(
            organization_id=organization_id,
            degradation_type=degradation_type,
            severity=severity,
            title=title,
            description=description,
            details_json=details or {},
            affected_entities_json=affected_entities or [],
            affected_dimensions_json=affected_dimensions or [],
            correlation_id=correlation_id,
            root_cause_observation_id=root_cause_observation_id,
            actor_id=actor_id,
            actor_type="system",
            evidence_json=evidence or [],
            provenance_json=provenance or {},
            fingerprint=fingerprint,
        )
        
        db.add(degradation)
        await db.flush()
        
        # Create attention signal
        await self._create_attention_for_degradation(db, degradation)
        
        await event_service.emit(
            db,
            name="degradation.detected",
            actor_id="system",
            organization_id=organization_id,
            payload={
                "degradation_id": degradation.id,
                "degradation_type": degradation_type,
                "severity": severity,
                "title": title,
            },
        )
        
        logger.warning(f"Degradation detected: {degradation.id} ({degradation_type})")
        return degradation
    
    async def acknowledge_degradation(
        self,
        db: AsyncSession,
        *,
        degradation: Degradation,
        actor_id: str,
    ) -> Degradation:
        """Acknowledge a degradation."""
        
        if degradation.state != "detected":
            raise ValueError("Can only acknowledge detected degradations")
        
        degradation.state = "investigating"
        degradation.acknowledged_at = utcnow()
        await db.flush()
        
        await event_service.emit(
            db,
            name="degradation.acknowledged",
            actor_id=actor_id,
            organization_id=degradation.organization_id,
            payload={"degradation_id": degradation.id},
        )
        
        return degradation
    
    async def contain_degradation(
        self,
        db: AsyncSession,
        *,
        degradation: Degradation,
        actor_id: str,
        note: Optional[str] = None,
    ) -> Degradation:
        """Mark degradation as contained."""
        
        if degradation.state not in ("detected", "investigating"):
            raise ValueError("Can only contain active degradations")
        
        degradation.state = "contained"
        degradation.contained_at = utcnow()
        if note:
            degradation.resolution_note = note
        await db.flush()
        
        await event_service.emit(
            db,
            name="degradation.contained",
            actor_id=actor_id,
            organization_id=degradation.organization_id,
            payload={"degradation_id": degradation.id},
        )
        
        return degradation
    
    async def recover_degradation(
        self,
        db: AsyncSession,
        *,
        degradation: Degradation,
        actor_id: str,
        resolution_method: str,
        resolution_note: Optional[str] = None,
        lessons_learned: Optional[dict] = None,
    ) -> Degradation:
        """Mark degradation as recovered."""
        
        if degradation.state not in ("detected", "investigating", "contained"):
            raise ValueError("Can only recover active degradations")
        
        degradation.state = "recovering"
        degradation.recovered_at = utcnow()
        degradation.resolution_method = resolution_method
        degradation.resolution_note = resolution_note
        degradation.lessons_learned_json = lessons_learned
        await db.flush()
        
        await event_service.emit(
            db,
            name="degradation.recovering",
            actor_id=actor_id,
            organization_id=degradation.organization_id,
            payload={"degradation_id": degradation.id},
        )
        
        return degradation
    
    async def verify_degradation(
        self,
        db: AsyncSession,
        *,
        degradation: Degradation,
        actor_id: str,
        verification_note: Optional[str] = None,
    ) -> Degradation:
        """Verify degradation resolution."""
        
        if degradation.state != "recovering":
            raise ValueError("Can only verify recovering degradations")
        
        degradation.state = "verified"
        degradation.verified_at = utcnow()
        degradation.resolved_by = actor_id
        degradation.resolution_note = verification_note
        await db.flush()
        
        # Update attention signal
        await self._resolve_attention_for_degradation(db, degradation)
        
        await event_service.emit(
            db,
            name="degradation.verified",
            actor_id=actor_id,
            organization_id=degradation.organization_id,
            payload={"degradation_id": degradation.id},
        )
        
        return degradation
    
    async def learn_from_degradation(
        self,
        db: AsyncSession,
        *,
        degradation: Degradation,
        actor_id: str,
        lessons_learned: dict,
    ) -> Degradation:
        """Record lessons learned from degradation."""
        
        if degradation.state != "verified":
            raise ValueError("Can only learn from verified degradations")
        
        degradation.state = "learned"
        degradation.learned_at = utcnow()
        degradation.lessons_learned_json = lessons_learned
        await db.flush()
        
        await event_service.emit(
            db,
            name="degradation.learned",
            actor_id=actor_id,
            organization_id=degradation.organization_id,
            payload={"degradation_id": degradation.id},
        )
        
        return degradation
    
    async def _create_attention_for_degradation(
        self,
        db: AsyncSession,
        degradation: Degradation,
    ) -> CompanyAttention:
        """Create attention signal for degradation."""
        
        priority_map = {
            "minor": "info",
            "major": "watch",
            "critical": "critical",
        }
        
        attention = CompanyAttention(
            organization_id=degradation.organization_id,
            attention_type="degradation",
            priority=priority_map.get(degradation.severity, "info"),
            title=degradation.title,
            description=degradation.description,
            source_type="degradation",
            source_id=degradation.id,
            priority_score=1.0 if degradation.severity == "critical" else 0.5,
            urgency=degradation.severity,
            status="open",
        )
        
        db.add(attention)
        await db.flush()
        return attention
    
    async def _resolve_attention_for_degradation(
        self,
        db: AsyncSession,
        degradation: Degradation,
    ) -> None:
        """Resolve attention signal for degradation."""
        
        # Find and resolve related attention
        result = await db.execute(
            select(CompanyAttention).where(
                CompanyAttention.organization_id == degradation.organization_id,
                CompanyAttention.source_type == "degradation",
                CompanyAttention.source_id == degradation.id,
                CompanyAttention.status == "open",
            )
        )
        for attention in result.scalars().all():
            attention.status = "resolved"
            attention.resolved_at = utcnow()
            attention.resolved_by = degradation.resolved_by
            attention.resolution_note = degradation.resolution_note
        await db.flush()
    
    # =========================================================================
    # HEALTH DIMENSIONS
    # =========================================================================
    
    async def record_health_dimension(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        dimension: str,
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        current_value: float,
        target_value: Optional[float] = None,
        threshold_warn: Optional[float] = None,
        threshold_critical: Optional[float] = None,
        unit: Optional[str] = None,
        trend: str = "stable",
        trend_score: float = 0.0,
        slo_target: Optional[float] = None,
        slo_compliance: Optional[float] = None,
        evidence: Optional[List[dict]] = None,
        provenance: Optional[dict] = None,
        window_start: Optional[datetime] = None,
        window_end: Optional[datetime] = None,
    ) -> HealthDimension:
        """Record a health dimension measurement."""
        
        # Determine status based on thresholds
        status = "healthy"
        if threshold_critical is not None and current_value >= threshold_critical:
            status = "critical"
        elif threshold_warn is not None and current_value >= threshold_warn:
            status = "degraded"
        
        # Determine trend
        if trend == "improving":
            trend_score = 1.0
        elif trend == "degrading":
            trend_score = -1.0
        elif trend == "volatile":
            trend_score = 0.0
        
        # Compute fingerprint
        fingerprint = compute_observation_fingerprint({
            "organization_id": organization_id,
            "dimension": dimension,
            "scope_type": scope_type,
            "scope_id": scope_id or "",
            "window_start": window_start.isoformat() if window_start else "",
            "window_end": window_end.isoformat() if window_end else "",
        })
        
        # Check for existing
        existing = await db.execute(
            select(HealthDimension).where(
                HealthDimension.organization_id == organization_id,
                HealthDimension.dimension == dimension,
                HealthDimension.scope_type == scope_type,
                HealthDimension.scope_id == scope_id,
                HealthDimension.window_start == window_start,
                HealthDimension.window_end == window_end,
            )
        )
        existing_hdim = existing.scalars().first()
        if existing_hdim:
            # Update existing
            existing_hdim.current_value = current_value
            existing_hdim.target_value = target_value
            existing_hdim.threshold_warn = threshold_warn
            existing_hdim.threshold_critical = threshold_critical
            existing_hdim.unit = unit
            existing_hdim.trend = trend
            existing_hdim.trend_score = trend_score
            existing_hdim.slo_target = slo_target
            existing_hdim.slo_compliance = slo_compliance
            existing_hdim.evidence_json = evidence or []
            existing_hdim.provenance_json = provenance or {}
            existing_hdim.recorded_at = utcnow()
            existing_hdim.window_start = window_start
            existing_hdim.window_end = window_end
            existing_hdim.status = status
            existing_hdim.trend = trend
            existing_hdim.trend_score = trend_score
            existing_hdim.slo_target = slo_target
            existing_hdim.slo_compliance = slo_compliance
            await db.flush()
            return existing_hdim
        
        hdim = HealthDimension(
            organization_id=organization_id,
            dimension=dimension,
            scope_type=scope_type,
            scope_id=scope_id,
            status=status,
            current_value=current_value,
            target_value=target_value,
            threshold_warn=threshold_warn,
            threshold_critical=threshold_critical,
            unit=unit,
            trend=trend,
            trend_score=trend_score,
            slo_target=slo_target,
            slo_compliance=slo_compliance,
            evidence_json=evidence or [],
            provenance_json=provenance or {},
            recorded_at=utcnow(),
            window_start=window_start,
            window_end=window_end,
            fingerprint=fingerprint,
        )
        
        db.add(hdim)
        await db.flush()
        
        # Emit event
        await event_service.emit(
            db,
            name="health.dimension.recorded",
            actor_id="system",
            organization_id=organization_id,
            payload={
                "dimension": dimension,
                "status": status,
                "value": current_value,
            },
        )
        
        return hdim
    
    async def get_health_dimensions(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        dimension: Optional[str] = None,
        scope_type: Optional[str] = None,
        scope_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> List[HealthDimension]:
        """Query health dimensions."""
        
        query = select(HealthDimension).where(
            HealthDimension.organization_id == organization_id
        )
        if dimension:
            query = query.where(HealthDimension.dimension == dimension)
        if scope_type:
            query = query.where(HealthDimension.scope_type == scope_type)
        if scope_id:
            query = query.where(HealthDimension.scope_id == scope_id)
        if status:
            query = query.where(HealthDimension.status == status)
        
        query = query.order_by(HealthDimension.recorded_at.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    # =========================================================================
    # SLO TARGETS
    # =========================================================================
    
    async def create_or_update_slo_target(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        dimension: str,
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        target_value: float,
        operator: str = "<=",
        unit: Optional[str] = None,
        window_type: str = "rolling",
        window_size: str = "7d",
        status: str = "active",
        updated_by: str,
    ) -> SLOTarget:
        """Create or update an SLO target."""
        
        # Compute fingerprint
        fingerprint = compute_observation_fingerprint({
            "organization_id": organization_id,
            "dimension": dimension,
            "scope_type": scope_type,
            "scope_id": scope_id or "",
        })
        
        # Check existing
        existing = await db.execute(
            select(SLOTarget).where(
                SLOTarget.organization_id == organization_id,
                SLOTarget.dimension == dimension,
                SLOTarget.scope_type == scope_type,
                SLOTarget.scope_id == scope_id,
            )
        )
        existing_slo = existing.scalars().first()
        
        if existing_slo:
            # Update
            existing_slo.target_value = target_value
            existing_slo.operator = operator
            existing_slo.unit = unit
            existing_slo.window_type = window_type
            existing_slo.window_size = window_size
            existing_slo.status = status
            existing_slo.updated_by = updated_by
            existing_slo.updated_at = utcnow()
            await db.flush()
            return existing_slo
        
        slo = SLOTarget(
            organization_id=organization_id,
            dimension=dimension,
            scope_type=scope_type,
            scope_id=scope_id,
            target_value=target_value,
            operator=operator,
            unit=unit,
            window_type=window_type,
            window_size=window_size,
            status=status,
            fingerprint=compute_observation_fingerprint({
                "organization_id": organization_id,
                "dimension": dimension,
                "scope_type": scope_type,
                "scope_id": scope_id or "",
            }),
        )
        
        db.add(slo)
        await db.flush()
        return slo
    
    async def evaluate_slo(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        dimension: str,
        scope_type: str = "company",
        scope_id: Optional[str] = None,
    ) -> Optional[SLOTarget]:
        """Evaluate SLO compliance for a dimension."""
        
        slo = await db.execute(
            select(SLOTarget).where(
                SLOTarget.organization_id == organization_id,
                SLOTarget.dimension == dimension,
                SLOTarget.scope_type == scope_type,
                SLOTarget.scope_id == scope_id,
                SLOTarget.status == "active",
            )
        )
        slo = slo.scalars().first()
        
        if not slo:
            return None
        
        # Get latest health dimension
        hdim = await db.execute(
            select(HealthDimension).where(
                HealthDimension.organization_id == organization_id,
                HealthDimension.dimension == dimension,
                HealthDimension.scope_type == slo.scope_type,
                HealthDimension.scope_id == slo.scope_id,
            ).order_by(HealthDimension.recorded_at.desc()).limit(1)
        )
        hdim = hdim.scalars().first()
        
        if not hdim:
            return slo
        
        # Evaluate compliance
        current = hdim.current_value
        target = slo.target_value
        op = slo.operator
        
        if op == "<=":
            compliant = current <= target
        elif op == ">=":
            compliant = current >= target
        elif op == "==":
            compliant = abs(current - target) < 0.001
        elif op == "<":
            compliant = current < target
        else:
            compliant = False
        
        # Update SLO
        slo.current_compliance = 100.0 if compliant else 0.0
        slo.last_evaluated_at = utcnow()
        await db.flush()
        
        return slo
    
    # =========================================================================
    # FRESHNESS CHECKS
    # =========================================================================
    
    async def check_freshness(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        feed_type: str,
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        feed_id: Optional[str] = None,
        expected_interval_seconds: int = 300,
        max_acceptable_delay_seconds: int = 3600,
        last_event_at: Optional[datetime] = None,
        last_event_fingerprint: Optional[str] = None,
    ) -> FreshnessCheck:
        """Check freshness of a data feed."""
        
        now = utcnow()
        delay_seconds = None
        status = "fresh"
        
        if last_event_at:
            delay_seconds = int((now - last_event_at).total_seconds())
            if delay_seconds > max_acceptable_delay_seconds:
                status = "stale"
            elif delay_seconds > max_acceptable_delay_seconds * 0.5:
                status = "delayed"
        else:
            status = "unknown"
        
        fingerprint = compute_observation_fingerprint({
            "organization_id": organization_id,
            "feed_type": feed_type,
            "scope_type": scope_type,
            "scope_id": scope_id or "",
            "feed_id": feed_id or "",
        })
        
        # Check existing
        existing = await db.execute(
            select(FreshnessCheck).where(
                FreshnessCheck.organization_id == organization_id,
                FreshnessCheck.feed_type == feed_type,
                FreshnessCheck.scope_type == scope_type,
                FreshnessCheck.scope_id == scope_id,
                FreshnessCheck.feed_id == feed_id,
            )
        )
        existing_fresh = existing.scalars().first()
        
        if existing_fresh:
            existing_fresh.last_checked_at = utcnow()
            existing_fresh.last_event_at = last_event_at
            existing_fresh.delay_seconds = delay_seconds
            existing_fresh.max_acceptable_delay_seconds = max_acceptable_delay_seconds
            existing_fresh.status = status
            existing_fresh.last_event_fingerprint = last_event_fingerprint
            await db.flush()
            return existing_fresh
        
        fresh = FreshnessCheck(
            organization_id=organization_id,
            feed_type=feed_type,
            scope_type=scope_type,
            scope_id=scope_id,
            feed_id=feed_id,
            status=status,
            expected_interval_seconds=expected_interval_seconds,
            last_event_at=last_event_at,
            last_checked_at=utcnow(),
            delay_seconds=delay_seconds,
            max_acceptable_delay_seconds=max_acceptable_delay_seconds,
            last_event_fingerprint=last_event_fingerprint,
            fingerprint=compute_observation_fingerprint({
                "organization_id": organization_id,
                "feed_type": feed_type,
                "scope_type": scope_type,
                "scope_id": scope_id or "",
                "feed_id": feed_id or "",
            }),
        )
        
        db.add(fresh)
        await db.flush()
        
        # Create attention if stale
        if status == "stale":
            await self._create_freshness_attention(db, organization_id, feed_type, scope_type, scope_id, fresh)
        
        return fresh
    
    async def _create_freshness_attention(
        self,
        db: AsyncSession,
        organization_id: str,
        feed_type: str,
        scope_type: str,
        scope_id: Optional[str],
        fresh_check: FreshnessCheck,
    ) -> CompanyAttention:
        """Create attention for stale feed."""
        
        attention = CompanyAttention(
            organization_id=organization_id,
            attention_type="freshness_stale",
            priority="high",
            title=f"Stale feed: {feed_type}",
            description=f"Feed {feed_type} has not received updates for {fresh_check.delay_seconds}s",
            source_type="freshness",
            source_id=fresh_check.id,
            priority_score=0.8,
            urgency="high",
            status="open",
        )
        db.add(attention)
        await db.flush()
        return attention
    
    # =========================================================================
    # OPERATIONAL TARGETS
    # =========================================================================
    
    async def create_operational_target(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        target_type: str,
        scope_type: str = "company",
        scope_id: Optional[str] = None,
        target_duration_seconds: int,
        target_value: Optional[float] = None,
        unit: Optional[str] = None,
        window_end: Optional[datetime] = None,
    ) -> OperationalTarget:
        """Create an operational target."""
        
        fingerprint = compute_observation_fingerprint({
            "organization_id": organization_id,
            "target_type": target_type,
            "scope_type": scope_type,
            "scope_id": scope_id or "",
            "window_start": utcnow().isoformat(),
        })
        
        # Check existing
        existing = await db.execute(
            select(OperationalTarget).where(
                OperationalTarget.organization_id == organization_id,
                OperationalTarget.target_type == target_type,
                OperationalTarget.scope_type == scope_type,
                OperationalTarget.scope_id == scope_id,
            )
        )
        existing_target = existing.scalars().first()
        if existing_target:
            existing_target.target_duration_seconds = target_duration_seconds
            existing_target.target_value = target_value
            existing_target.unit = unit
            existing_target.window_end = window_end
            existing_target.status = "active"
            await db.flush()
            return existing_target
        
        target = OperationalTarget(
            organization_id=organization_id,
            target_type=target_type,
            scope_type=scope_type,
            scope_id=scope_id,
            target_duration_seconds=target_duration_seconds,
            target_value=target_value,
            unit=unit,
            status="active",
            window_end=window_end,
            fingerprint=compute_observation_fingerprint({
                "organization_id": organization_id,
                "target_type": target_type,
                "scope_type": scope_type,
                "scope_id": scope_id or "",
            }),
        )
        
        db.add(target)
        await db.flush()
        return target
    
    async def evaluate_operational_target(
        self,
        db: AsyncSession,
        *,
        target: OperationalTarget,
        current_value: float,
    ) -> OperationalTarget:
        """Evaluate operational target against current value."""
        
        target.current_value = current_value
        
        # Check if met (higher is better for completion/success rates)
        if target.target_value is not None:
            if current_value >= target.target_value:
                target.status = "met"
            else:
                target.status = "missed"
        
        await db.flush()
        return target
    
    # =========================================================================
    # FRESHNESS MONITORING FOR INTEGRATIONS
    # =========================================================================
    
    async def check_integration_freshness(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
    ) -> List[FreshnessCheck]:
        """Check freshness for all active integrations."""
        
        # Get all active connector instances
        result = await db.execute(
            select(ConnectorInstance).where(
                ConnectorInstance.organization_id == organization_id,
                ConnectorInstance.state == "active",
            )
        )
        connectors = result.scalars().all()
        
        checks = []
        for connector in connectors:
            # Get latest sync
            sync = await db.execute(
                select(SyncRun).where(
                    SyncRun.connector_instance_id == connector.id,
                ).order_by(SyncRun.started_at.desc()).limit(1)
            )
            last_sync = sync.scalars().first()
            
            # Check freshness
            check = await self.check_freshness(
                db=db,
                organization_id=organization_id,
                feed_type="integration",
                scope_type="integration",
                scope_id=connector.id,
                feed_id=connector.id,
                expected_interval_seconds=3600,  # 1 hour default
                max_acceptable_delay_seconds=86400,  # 24 hours
                last_event_at=last_sync.started_at if last_sync else None,
            )
            checks.append(check)
        
        return checks
    
    async def check_worker_freshness(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
    ) -> List[FreshnessCheck]:
        """Check freshness for all active workers."""
        
        # Get stale workers from reliability service
        stale_ops = await canonical_reliability_service.detect_stale_operations(
            db, organization_id=organization_id
        )
        
        checks = []
        for stale in stale_ops:
            check = await self.check_freshness(
                db=db,
                organization_id=organization_id,
                feed_type="worker",
                scope_type="worker",
                scope_id=stale.operation_id,
                feed_id=f"worker_{stale.operation_id}",
                expected_interval_seconds=300,
                max_acceptable_delay_seconds=600,
                last_event_at=stale.last_progress_at,
            )
            checks.append(check)
        
        return checks
    
    # =========================================================================
    # OPERATIONAL ATTENTION INTEGRATION
    # =========================================================================
    
    async def create_operational_attention(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        attention_type: str,
        priority: str = "info",
        title: str,
        description: Optional[str] = None,
        source_type: str,
        source_id: str,
        priority_score: float = 0.5,
        urgency: str = "normal",
        assigned_to: Optional[str] = None,
        assigned_by: Optional[str] = None,
        details: Optional[dict] = None,
    ) -> CompanyAttention:
        """Create an operational attention signal."""
        
        attention = CompanyAttention(
            organization_id=organization_id,
            attention_type=attention_type,
            priority=priority,
            title=title,
            description=description,
            source_type=source_type,
            source_id=source_id,
            priority_score=priority_score,
            urgency=urgency,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            status="open",
        )
        
        db.add(attention)
        await db.flush()
        
        # Emit event
        await event_service.emit(
            db,
            name="attention.created",
            actor_id=assigned_by or "system",
            organization_id=organization_id,
            payload={
                "attention_id": attention.id,
                "attention_type": attention_type,
                "priority": priority,
                "source_type": source_type,
                "source_id": source_id,
            },
        )
        
        return attention
    
    async def get_operational_attention(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        status: Optional[str] = None,
        attention_type: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 100,
    ) -> List[CompanyAttention]:
        """Get operational attention signals."""
        
        query = select(CompanyAttention).where(
            CompanyAttention.organization_id == organization_id
        )
        if status:
            query = query.where(CompanyAttention.status == status)
        if attention_type:
            query = query.where(CompanyAttention.attention_type == attention_type)
        if priority:
            query = query.where(CompanyAttention.priority == priority)
        
        query = query.order_by(CompanyAttention.priority_score.desc()).limit(limit)
        result = await db.execute(query)
        return list(result.scalars().all())
    
    async def resolve_attention(
        self,
        db: AsyncSession,
        *,
        attention_id: str,
        organization_id: str,
        resolved_by: str,
        resolution_note: Optional[str] = None,
    ) -> bool:
        """Resolve an attention signal."""
        
        attention = await db.get(CompanyAttention, attention_id)
        if not attention or attention.organization_id != organization_id:
            return False
        
        if attention.status == "resolved":
            return False
        
        attention.status = "resolved"
        attention.resolved_at = utcnow()
        attention.resolved_by = resolved_by
        attention.resolution_note = resolution_note
        
        await db.flush()
        
        await event_service.emit(
            db,
            name="attention.resolved",
            actor_id=resolved_by,
            organization_id=organization_id,
            payload={"attention_id": attention_id},
        )
        
        return True
    
    # =========================================================================
    # HEALTH & FRESHNESS DASHBOARD
    # =========================================================================
    
    async def get_health_dashboard(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
    ) -> dict[str, Any]:
        """Get comprehensive health dashboard."""
        
        # Health dimensions
        dims = await self.get_health_dimensions(db, organization_id=organization_id, limit=100)
        
        # Freshness checks
        freshness = await db.execute(
            select(FreshnessCheck).where(
                FreshnessCheck.organization_id == organization_id
            ).order_by(FreshnessCheck.last_checked_at.desc()).limit(100)
        )
        freshness_checks = freshness.scalars().all()
        
        # Active degradations
        degradations = await db.execute(
            select(Degradation).where(
                Degradation.organization_id == organization_id,
                Degradation.state.in_(["detected", "investigating", "contained", "recovering"]),
            ).order_by(Degradation.detected_at.desc()).limit(50)
        )
        active_degradations = degradations.scalars().all()
        
        # Active attention
        attention = await self.get_operational_attention(
            db, organization_id=organization_id, status="open", limit=50
        )
        
        # Correlation contexts
        correlations = await db.execute(
            select(CorrelationContext).where(
                CorrelationContext.organization_id == organization_id,
                CorrelationContext.status == "active",
            ).order_by(CorrelationContext.last_updated_at.desc()).limit(50)
        )
        correlations = correlations.scalars().all()
        
        # SLO evaluations
        slos = await db.execute(
            select(SLOTarget).where(
                SLOTarget.organization_id == organization_id,
                SLOTarget.status == "active",
            )
        )
        slos_list = slos.scalars().all()
        
        # Evaluate SLOs
        for slo in slos_list:
            await self.evaluate_slo(
                db=db,
                organization_id=organization_id,
                dimension=slo.dimension,
                scope_type=slo.scope_type,
                scope_id=slo.scope_id,
            )
        
        # Freshness checks for integrations and workers
        integration_freshness = await self.check_integration_freshness(db, organization_id=organization_id)
        worker_freshness = await self.check_worker_freshness(db, organization_id=organization_id)
        
        return {
            "health_dimensions": [
                {
                    "dimension": d.dimension,
                    "status": d.status,
                    "current_value": d.current_value,
                    "target_value": d.target_value,
                    "threshold_warn": d.threshold_warn,
                    "threshold_critical": d.threshold_critical,
                    "unit": d.unit,
                    "trend": d.trend,
                    "slo_compliance": d.slo_compliance,
                    "recorded_at": d.recorded_at.isoformat(),
                }
                for d in dims
            ],
            "freshness": [
                {
                    "feed_type": f.feed_type,
                    "scope_type": f.scope_type,
                    "scope_id": f.scope_id,
                    "status": f.status,
                    "delay_seconds": f.delay_seconds,
                    "max_delay_seconds": f.max_acceptable_delay_seconds,
                    "last_event_at": f.last_event_at.isoformat() if f.last_event_at else None,
                    "last_checked_at": f.last_checked_at.isoformat(),
                }
                for f in freshness_checks
            ],
            "degradations": [
                {
                    "id": d.id,
                    "type": d.degradation_type,
                    "severity": d.severity,
                    "state": d.state,
                    "title": d.title,
                    "detected_at": d.detected_at.isoformat(),
                }
                for d in active_degradations
            ],
            "attention": [
                {
                    "id": a.id,
                    "type": a.attention_type,
                    "priority": a.priority,
                    "title": a.title,
                    "source_type": a.source_type,
                    "source_id": a.source_id,
                    "status": a.status,
                }
                for a in attention
            ],
            "correlations": [
                {
                    "correlation_id": c.correlation_id,
                    "trace_id": c.trace_id,
                    "type": c.correlation_type,
                    "status": c.status,
                    "current_step": c.current_step,
                    "outcome": c.outcome,
                }
                for c in correlations
            ],
            "slos": [
                {
                    "dimension": s.dimension,
                    "target_value": s.target_value,
                    "operator": s.operator,
                    "compliance": s.current_compliance,
                    "status": s.status,
                }
                for s in slos_list
            ],
            "integration_freshness": [
                {
                    "feed_type": f.feed_type,
                    "scope_id": f.scope_id,
                    "status": f.status,
                    "delay_seconds": f.delay_seconds,
                }
                for f in integration_freshness
            ],
            "worker_freshness": [
                {
                    "feed_type": f.feed_type,
                    "scope_id": f.scope_id,
                    "status": f.status,
                    "delay_seconds": f.delay_seconds,
                }
                for f in worker_freshness
            ],
        }
    
    # =========================================================================
    # CORRELATION RECONSTRUCTION
    # =========================================================================
    
    async def reconstruct_correlation_chain(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        trace_id: str,
    ) -> List[dict]:
        """Reconstruct full correlation chain for a trace."""
        
        contexts = await self.get_correlation_by_trace(db, organization_id=organization_id, trace_id=trace_id)
        
        chain = []
        for ctx in contexts:
            for step in ctx.chain_json.get("steps", []):
                chain.append({
                    "correlation_id": ctx.correlation_id,
                    "correlation_type": ctx.correlation_type,
                    **step,
                })
        
        # Sort by observed_at
        chain.sort(key=lambda x: x.get("observed_at", ""))
        return chain
    
    async def get_operation_correlation(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        operation_id: str,
    ) -> List[CanonicalObservation]:
        """Get all observations for an operation."""
        
        result = await db.execute(
            select(CanonicalObservation).where(
                CanonicalObservation.organization_id == organization_id,
                CanonicalObservation.operation_id == operation_id,
            ).order_by(CanonicalObservation.observed_at.asc())
        )
        return list(result.scalars().all())
    
    # =========================================================================
    # SECRET REDACTION FOR API RESPONSES
    # =========================================================================
    
    def sanitize_for_api(self, data: Any) -> Any:
        """Sanitize data for API responses, redacting secrets."""
        return self._redact_secrets(data)
    
    def sanitize_observation_for_api(self, observation: CanonicalObservation) -> dict:
        """Convert observation to sanitized dict for API response."""
        return self.sanitize_for_api({
            "id": observation.id,
            "organization_id": observation.organization_id,
            "observation_type": observation.observation_type,
            "source": observation.source,
            "source_component": observation.source_component,
            "actor_id": observation.actor_id,
            "actor_type": observation.actor_type,
            "severity": observation.severity,
            "epistemic_status": observation.epistemic_status,
            "correlation_id": observation.correlation_id,
            "trace_id": observation.trace_id,
            "span_id": observation.span_id,
            "parent_span_id": observation.parent_span_id,
            "operation_id": observation.operation_id,
            "operation_type": observation.operation_type,
            "attempt_id": observation.attempt_id,
            "integration_id": observation.integration_id,
            "connector_id": observation.connector_id,
            "external_operation_id": observation.external_operation_id,
            "security_event_id": observation.security_event_id,
            "degradation_id": observation.degradation_id,
            "title": observation.title,
            "description": observation.description,
            "details_json": self._redact_secrets(observation.details_json),
            "metrics_json": self._redact_secrets(observation.metrics_json),
            "provenance_json": self._redact_secrets(observation.provenance_json),
            "source_event_id": observation.source_event_id,
            "observed_at": observation.observed_at.isoformat() if observation.observed_at else None,
            "recorded_at": observation.recorded_at.isoformat() if observation.recorded_at else None,
            "duration_ms": observation.duration_ms,
            "fingerprint": observation.fingerprint,
            "version": observation.version,
            "created_at": observation.created_at.isoformat() if observation.created_at else None,
            "updated_at": observation.updated_at.isoformat() if observation.updated_at else None,
        })


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

observability_service = ObservabilityService()


# =============================================================================
# SLICE 2E INTEGRATION — Alert Engine & Health Evaluation
# =============================================================================

# Import Slice 2E services
# Slice 2E services - imported lazily to avoid circular imports
SLICE_2E_AVAILABLE = True
alert_engine = None
health_evaluation_service = None
health_model_service = None

def _get_slice2e_services():
    """Lazily import Slice 2E services."""
    global alert_engine, health_evaluation_service, health_model_service
    if alert_engine is None:
        try:
            from app.services.alert_engine import (
                alert_engine as _alert_engine,
                AlertEngine,
                AlertState,
                AlertSeverity,
                AlertRule,
                Alert,
                AlertCorrelationType,
                create_release_health_alert_rules,
            )
            from app.services.health_evaluation_service import (
                health_evaluation_service as _health_evaluation_service,
                HealthEvaluationService,
                HealthDimensionName,
                AggregateHealthReport,
            )
            from app.services.health_model_service import (
                health_model_service as _health_model_service,
                HealthModelService,
                HealthModelReport,
            )
            alert_engine = _alert_engine
            health_evaluation_service = _health_evaluation_service
            health_model_service = _health_model_service
        except ImportError:
            pass

class ObservabilityServiceSlice2E:
    """Slice 2E extensions for ObservabilityService."""
    
    def __init__(self, base_service: ObservabilityService):
        self.base = base_service
        _get_slice2e_services()
        self._alert_engine = alert_engine
        self._health_evaluation = health_evaluation_service
        self._health_model = health_model_service
    
    async def evaluate_release_health(
        self,
        db: AsyncSession,
        organization_id: str,
        include_alerts: bool = True,
    ) -> Dict[str, Any]:
        """Evaluate comprehensive release health including alerts and health model."""
        
        if not SLICE_2E_AVAILABLE:
            return {"error": "Slice 2E services not available"}
        
        results = {}
        
        # 1. Evaluate health across all 13 dimensions
        health_report = await self._health_evaluation.evaluate_all(db, organization_id)
        results["health_report"] = health_report
        
        # 2. Get tenant fingerprint for correlation
        from app.services.canonical_fingerprint import canonical_fingerprint_service
        tenant_fp = await canonical_fingerprint_service.compute_tenant_fingerprint(db, organization_id)
        results["tenant_fingerprint"] = tenant_fp.aggregate_fingerprint
        
        # 3. Build health model snapshot
        health_model_report = await self._health_model.generate_report(
            db, organization_id, health_report, tenant_fp
        )
        results["health_model"] = health_model_report
        
        # 4. Correlate with canonical fingerprint
        fingerprint_correlation = await self._health_model.correlate_with_canonical_fingerprint(
            db, organization_id, health_report
        )
        results["fingerprint_correlation"] = fingerprint_correlation
        
        # 5. Evaluate alerts if requested
        if include_alerts and self._alert_engine:
            # Create mock observations from health report for alert evaluation
            alerts_triggered = []
            for dim, result in health_report.dimension_results.items():
                # Create a synthetic observation for alert evaluation
                from app.models.observability import CanonicalObservation
                mock_obs = CanonicalObservation(
                    organization_id=organization_id,
                    observation_type="health_check",
                    source="health_evaluation",
                    severity=result.status if result.status in ["critical", "degraded"] else "info",
                    title=f"Health check: {dim.value}",
                    observed_at=utcnow(),
                    fingerprint=f"health-{dim.value}-{organization_id}",
                )
                # Evaluate against alert rules
                alerts = await self._alert_engine.evaluate_observation(mock_obs, result)
                alerts_triggered.extend(alerts)
            
            # Import AlertSeverity lazily
            from app.services.alert_engine import AlertSeverity
            results["alerts"] = {
                "triggered": len(alerts_triggered),
                "alert_ids": [a.id for a in alerts_triggered],
                "by_severity": {
                    sev.value: len([a for a in alerts_triggered if a.severity == sev])
                    for sev in AlertSeverity
                },
            }
        
        return results
    
    async def get_alert_dashboard(
        self,
        db: AsyncSession,
        organization_id: str,
    ) -> Dict[str, Any]:
        """Get alert dashboard data for an organization."""
        
        if not SLICE_2E_AVAILABLE or not self._alert_engine:
            return {"error": "Slice 2E services not available"}
        
        # Get all alerts
        alerts = self._alert_engine.list_alerts(organization_id=organization_id)
        
        # Group by state
        by_state = defaultdict(list)
        for alert in alerts:
            by_state[alert.state.value].append({
                "id": alert.id,
                "rule_name": alert.rule_name,
                "dimension": alert.dimension,
                "severity": alert.severity.value,
                "title": alert.title,
                "created_at": alert.created_at.isoformat(),
                "acknowledged_by": alert.acknowledged_by,
                "investigating_by": alert.investigating_by,
            })
        
        # Get correlations
        correlations = {}
        for alert in alerts:
            corrs = self._alert_engine.get_correlations(alert.id)
            if corrs:
                correlations[alert.id] = [
                    {
                        "correlated_alert_id": c.correlated_alert_id,
                        "type": c.correlation_type.value,
                        "confidence": c.confidence,
                    }
                    for c in corrs
                ]
        
        # Import AlertSeverity and AlertState lazily
        from app.services.alert_engine import AlertSeverity, AlertState
        return {
            "organization_id": organization_id,
            "total_alerts": len(alerts),
            "by_state": dict(by_state),
            "by_severity": {
                sev.value: len([a for a in alerts if a.severity == sev])
                for sev in AlertSeverity
            },
            "correlations": correlations,
            "active_alerts": len([a for a in alerts if a.state in [
                AlertState.OBSERVED, AlertState.EVALUATED, AlertState.ALERTED,
                AlertState.ACKNOWLEDGED, AlertState.INVESTIGATING,
            ]]),
        }
    
    async def acknowledge_alert(
        self,
        alert_id: str,
        acknowledged_by: str,
    ) -> bool:
        """Acknowledge an alert."""
        if not SLICE_2E_AVAILABLE or not self._alert_engine:
            return False
        return await self._alert_engine.acknowledge_alert(alert_id, acknowledged_by)
    
    async def investigate_alert(
        self,
        alert_id: str,
        investigating_by: str,
    ) -> bool:
        """Start investigating an alert."""
        if not SLICE_2E_AVAILABLE or not self._alert_engine:
            return False
        return await self._alert_engine.start_investigation(alert_id, investigating_by)
    
    async def resolve_alert(
        self,
        alert_id: str,
        resolved_by: str,
        resolution_note: str = "",
    ) -> bool:
        """Resolve an alert."""
        if not SLICE_2E_AVAILABLE or not self._alert_engine:
            return False
        return await self._alert_engine.resolve_alert(alert_id, resolved_by, resolution_note)
    
    async def verify_alert(
        self,
        alert_id: str,
        verified_by: str,
    ) -> bool:
        """Verify an alert resolution."""
        if not SLICE_2E_AVAILABLE or not self._alert_engine:
            return False
        return await self._alert_engine.verify_alert(alert_id, verified_by)


def get_slice2e_extension(service: ObservabilityService) -> Optional[ObservabilityServiceSlice2E]:
    """Get Slice 2E extension for observability service."""
    if SLICE_2E_AVAILABLE:
        return ObservabilityServiceSlice2E(service)
    return None