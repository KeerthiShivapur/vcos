"""Provisioning Instrumentation — structured timing and observability for onboarding.

Provides structured metrics collection for the provisioning lifecycle
using the existing observability infrastructure.
"""

import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.observability import CanonicalObservation
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class StepTiming:
    """Timing information for a single provisioning step."""
    step_name: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    state: str = "running"
    error: Optional[str] = None
    db_queries: int = 0
    db_rows_affected: int = 0
    transaction_committed: bool = False


@dataclass
class ProvisioningRunMetrics:
    """Complete metrics for a provisioning run."""
    run_id: str
    provisioning_id: str
    organization_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_duration_seconds: Optional[float] = None
    final_state: str = "running"
    steps: Dict[str, StepTiming] = field(default_factory=dict)
    overall_db_queries: int = 0
    overall_db_rows: int = 0
    transaction_rollbacks: int = 0
    lock_wait_seconds: float = 0.0
    failure_reason: Optional[str] = None


# Global metrics registry (in production, use Redis or persistent storage)
_provisioning_run_metrics: Dict[str, ProvisioningRunMetrics] = {}


def get_provisioning_run_metrics(run_id: str) -> Optional[ProvisioningRunMetrics]:
    """Get metrics for a provisioning run."""
    return _provisioning_run_metrics.get(run_id)


def clear_provisioning_run_metrics(run_id: str):
    """Clear metrics for a provisioning run."""
    _provisioning_run_metrics.pop(run_id, None)


def record_run_start(
    run_id: str,
    provisioning_id: str,
    organization_id: str,
) -> ProvisioningRunMetrics:
    """Record the start of a provisioning run."""
    metrics = ProvisioningRunMetrics(
        run_id=run_id,
        provisioning_id=provisioning_id,
        organization_id=organization_id,
        started_at=utcnow(),
    )
    _provisioning_run_metrics[run_id] = metrics
    return metrics


def record_step_start(
    run_id: str,
    step_name: str,
) -> Optional[StepTiming]:
    """Record the start of a provisioning step."""
    if run_id not in _provisioning_run_metrics:
        return None

    metrics = _provisioning_run_metrics[run_id]
    step_timing = StepTiming(
        step_name=step_name,
        started_at=utcnow(),
    )
    metrics.steps[step_name] = step_timing
    return step_timing


def record_step_complete(
    run_id: str,
    step_name: str,
    state: str,
    error: Optional[str] = None,
    db_queries: int = 0,
    db_rows_affected: int = 0,
    transaction_committed: bool = False,
    lock_wait_seconds: float = 0.0,
):
    """Record the completion of a provisioning step."""
    if run_id not in _provisioning_run_metrics:
        return

    metrics = _provisioning_run_metrics[run_id]
    if step_name not in metrics.steps:
        return

    step = metrics.steps[step_name]
    step.completed_at = utcnow()
    step.duration_seconds = (step.completed_at - step.started_at).total_seconds()
    step.state = state
    step.error = error
    step.db_queries = db_queries
    step.db_rows_affected = db_rows_affected
    step.transaction_committed = transaction_committed

    # Update overall metrics
    metrics.overall_db_queries += db_queries
    metrics.overall_db_rows += db_rows_affected
    if not transaction_committed:
        metrics.transaction_rollbacks += 1
    metrics.lock_wait_seconds += lock_wait_seconds
    if state == "failed":
        metrics.failure_reason = error


def record_run_complete(
    run_id: str,
    final_state: str,
    failure_reason: Optional[str] = None,
):
    """Record the completion of a provisioning run."""
    if run_id not in _provisioning_run_metrics:
        return

    metrics = _provisioning_run_metrics[run_id]
    metrics.completed_at = utcnow()
    metrics.total_duration_seconds = (metrics.completed_at - metrics.started_at).total_seconds()
    metrics.final_state = final_state
    metrics.failure_reason = failure_reason


def record_provisioning_complete(
    provisioning_id: str,
    final_state: str,
    failure_reason: Optional[str] = None,
):
    """Record the completion of a provisioning (for backward compatibility)."""
    # This is a compatibility function for the existing provisioning service
    # The actual run tracking is done via record_run_complete with run_id
    pass


# =============================================================================
# OBSERVABILITY INTEGRATION
# =============================================================================

import hashlib

async def emit_provisioning_observation(
    db: AsyncSession,
    organization_id: str,
    run_id: str,
    step_name: str,
    state: str,
    duration_seconds: Optional[float] = None,
    error: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Emit a canonical observation for provisioning step."""
    try:
        # Generate fingerprint for exact-once
        fp_content = f"{organization_id}|{run_id}|{step_name}|{state}|{duration_seconds}|{error}"
        fingerprint = hashlib.sha256(fp_content.encode()).hexdigest()[:64]
        
        observation = CanonicalObservation(
            organization_id=organization_id,
            observation_type="operation_lifecycle",
            title=f"Provisioning step {step_name} {state}",
            description=f"Step {step_name} completed with state {state}",
            source="provisioning_service",
            source_component="provisioning_step",
            severity="info" if state == "completed" else "warning" if state == "failed" else "notice",
            epistemic_status="observed",
            recorded_at=utcnow(),
            observed_at=utcnow(),
            fingerprint=fingerprint,
            details_json={
                "run_id": run_id,
                "step_name": step_name,
                "state": state,
                "duration_seconds": duration_seconds,
                "error": error,
                **(metadata or {}),
            },
        )
        db.add(observation)
        await db.flush()
    except Exception:
        # Don't let observability failures break provisioning
        pass


async def emit_provisioning_run_observation(
    db: AsyncSession,
    organization_id: str,
    run_id: str,
    final_state: str,
    total_duration_seconds: Optional[float] = None,
    steps_completed: int = 0,
    steps_failed: int = 0,
):
    """Emit a canonical observation for the complete provisioning run."""
    try:
        # Generate fingerprint for exact-once
        fp_content = f"{organization_id}|{run_id}|{final_state}|{total_duration_seconds}"
        fingerprint = hashlib.sha256(fp_content.encode()).hexdigest()[:64]
        
        observation = CanonicalObservation(
            organization_id=organization_id,
            observation_type="operation_lifecycle",
            title=f"Provisioning run {final_state}",
            description=f"Full provisioning run completed with state {final_state}",
            source="provisioning_service",
            source_component="provisioning_run",
            severity="info" if final_state == "ready" else "critical",
            epistemic_status="observed",
            recorded_at=utcnow(),
            observed_at=utcnow(),
            fingerprint=fingerprint,
            details_json={
                "run_id": run_id,
                "final_state": final_state,
                "total_duration_seconds": total_duration_seconds,
                "steps_completed": steps_completed,
                "steps_failed": steps_failed,
            },
        )
        db.add(observation)
        await db.flush()
    except Exception:
        pass


# =============================================================================
# CONTEXT MANAGER FOR STEP TIMING
# =============================================================================

@asynccontextmanager
async def timed_provisioning_step(
    db: AsyncSession,
    run_id: str,
    step_name: str,
    organization_id: str,
):
    """Context manager for timing a provisioning step with automatic metrics."""
    step_timing = record_step_start(run_id, step_name)
    if not step_timing:
        yield None
        return

    error = None
    state = "completed"
    db_queries = 0
    db_rows = 0
    transaction_committed = False
    lock_wait = 0.0

    try:
        yield step_timing
    except Exception as e:
        error = str(e)
        state = "failed"
        raise
    finally:
        record_step_complete(
            run_id=run_id,
            step_name=step_name,
            state=state,
            error=error,
            db_queries=db_queries,
            db_rows_affected=db_rows,
            transaction_committed=transaction_committed,
            lock_wait_seconds=lock_wait,
        )

        # Emit observation
        duration = step_timing.duration_seconds
        await emit_provisioning_observation(
            db,
            organization_id=organization_id,
            run_id=run_id,
            step_name=step_name,
            state=state,
            duration_seconds=duration,
            error=error,
        )


# =============================================================================
# BASELINE MEASUREMENT UTILITIES
# =============================================================================

class OnboardingBaseline:
    """Utility for measuring onboarding baseline performance."""

    def __init__(self):
        self.measurements: List[Dict[str, Any]] = []

    async def measure_onboarding(
        self,
        db: AsyncSession,
        organization_name: str,
        domain: str,
        admin_email: str,
        admin_name: str,
        plan_key: str = "starter",
        iterations: int = 5,
    ) -> Dict[str, Any]:
        """Measure onboarding performance over multiple iterations."""
        from app.services.provisioning_service import provisioning_service

        results = []

        for i in range(iterations):
            # Create unique domain for each iteration
            iter_domain = f"{domain}-iter{i}"
            iter_name = f"{organization_name} Iter {i}"

            run_id = f"baseline-{uuid.uuid4().hex[:8]}"

            # Start provisioning
            provisioning = await provisioning_service.start_provisioning(
                db,
                organization_name=iter_name,
                domain=iter_domain,
                admin_email=f"admin{i}@{iter_domain}",
                admin_name=admin_name,
                plan_key=plan_key,
            )

            run_start = time.perf_counter()

            try:
                # Execute full provisioning
                await provisioning_service.execute_provisioning(
                    db,
                    provisioning_id=provisioning.id,
                )

                run_duration = time.perf_counter() - run_start

                # Get final state
                final_provisioning = await provisioning_service.get_provisioning(db, provisioning.id)

                results.append({
                    "iteration": i,
                    "run_id": run_id,
                    "provisioning_id": provisioning.id,
                    "duration_seconds": run_duration,
                    "final_state": final_provisioning.state,
                    "steps_completed": len([s for s in (final_provisioning.steps or []) if s.get("state") == "completed"]),
                    "steps_failed": len([s for s in (final_provisioning.steps or []) if s.get("state") == "failed"]),
                    "success": final_provisioning.state == "ready",
                })

            except Exception as e:
                run_duration = time.perf_counter() - run_start
                results.append({
                    "iteration": i,
                    "run_id": run_id,
                    "provisioning_id": provisioning.id,
                    "duration_seconds": run_duration,
                    "final_state": "failed",
                    "error": str(e),
                    "success": False,
                })

        # Calculate statistics
        successful = [r for r in results if r.get("success")]
        durations = [r["duration_seconds"] for r in successful]

        return {
            "iterations": iterations,
            "successful_runs": len(successful),
            "failed_runs": len(results) - len(successful),
            "median_duration_seconds": sorted(durations)[len(durations) // 2] if durations else None,
            "p95_duration_seconds": sorted(durations)[int(len(durations) * 0.95)] if durations else None,
            "min_duration_seconds": min(durations) if durations else None,
            "max_duration_seconds": max(durations) if durations else None,
            "avg_duration_seconds": sum(durations) / len(durations) if durations else None,
            "detailed_results": results,
        }


# =============================================================================
# DATABASE QUERY COUNTER (for development/measurement)
# =============================================================================

class QueryCounter:
    """Simple query counter for measuring database queries during provisioning."""

    def __init__(self):
        self.count = 0
        self.enabled = False

    def __enter__(self):
        self.count = 0
        self.enabled = True
        return self

    def __exit__(self, *args):
        self.enabled = False

    def increment(self):
        if self.enabled:
            self.count += 1


# Global query counter
_query_counter = QueryCounter()


def get_query_counter() -> QueryCounter:
    return _query_counter


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "StepTiming",
    "ProvisioningRunMetrics",
    "record_run_start",
    "record_step_start",
    "record_step_complete",
    "record_run_complete",
    "record_provisioning_complete",
    "get_provisioning_run_metrics",
    "clear_provisioning_run_metrics",
    "emit_provisioning_observation",
    "emit_provisioning_run_observation",
    "timed_provisioning_step",
    "OnboardingBaseline",
    "QueryCounter",
    "get_query_counter",
]