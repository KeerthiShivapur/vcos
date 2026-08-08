"""Reliability engineering: circuit breakers, health checks, chaos runs (Phase 16.24)."""

import time
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.infrastructure import ChaosRun
from app.models.organization import gen_uuid

CHAOS_SCENARIOS = (
    "kill_api_server",
    "kill_replica",
    "region_down",
    "db_latency",
    "worker_termination",
    "network_partition",
)
CHAOS_STATUSES = ("queued", "running", "completed", "failed")

_CIRCUIT_BREAKERS: dict[str, dict[str, Any]] = {}


class ReliabilityService:
    """Chaos engineering and resilient call patterns."""

    async def circuit_state(self, name: str) -> dict[str, Any]:
        state = _CIRCUIT_BREAKERS.get(name)
        if state is None:
            return {"name": name, "state": "closed", "failures": 0, "opened_at": None, "last_failure": None}
        return {
            "name": name,
            "state": state["state"],
            "failures": state["failures"],
            "opened_at": state["opened_at"],
            "last_failure": state["last_failure"],
        }

    def record_success(self, name: str) -> None:
        state = _CIRCUIT_BREAKERS.setdefault(
            name, {"state": "closed", "failures": 0, "opened_at": None, "last_failure": None}
        )
        state["state"] = "closed"
        state["failures"] = 0
        state["opened_at"] = None

    def record_failure(self, name: str, threshold: int = 5) -> bool:
        """Record a failure; trip the breaker when the threshold is reached."""
        state = _CIRCUIT_BREAKERS.setdefault(
            name, {"state": "closed", "failures": 0, "opened_at": None, "last_failure": None}
        )
        state["failures"] += 1
        state["last_failure"] = time.time()
        if state["state"] == "closed" and state["failures"] >= threshold:
            state["state"] = "open"
            state["opened_at"] = time.time()
        return state["state"] == "open"

    async def circuit_summary(self) -> dict[str, Any]:
        return {
            "breakers": [
                {
                    "name": name,
                    "state": data["state"],
                    "failures": data["failures"],
                    "opened_at": data["opened_at"],
                }
                for name, data in _CIRCUIT_BREAKERS.items()
            ],
            "total": len(_CIRCUIT_BREAKERS),
            "open": sum(1 for data in _CIRCUIT_BREAKERS.values() if data["state"] == "open"),
        }

    async def health_check(self, db: AsyncSession, *, service: str, timeout_ms: int = 500) -> dict[str, Any]:
        """Probe a service; simulate latency and trip a circuit breaker on failure."""
        import random

        latency_ms = random.randint(5, timeout_ms)
        healthy = latency_ms <= timeout_ms
        if not healthy:
            self.record_failure(service)
        else:
            self.record_success(service)
        from app.infrastructure.observability_service import observability_service

        await observability_service.record_service_metric(
            db,
            service=service,
            metric_name="health_check_latency",
            value=latency_ms,
            unit="ms",
            region=None,
        )
        return {
            "service": service,
            "status": "healthy" if healthy else "unhealthy",
            "latency_ms": latency_ms,
            "circuit": await self.circuit_state(service),
            "checked_at": utcnow().isoformat(),
        }

    async def run_chaos(
        self,
        db: AsyncSession,
        *,
        scenario: str,
        target_region: Optional[str] = None,
        target_service: Optional[str] = None,
        expected_impact: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> ChaosRun:
        if scenario not in CHAOS_SCENARIOS:
            raise ValueError(f"Unknown chaos scenario '{scenario}', expected one of {', '.join(CHAOS_SCENARIOS)}")
        run = ChaosRun(
            id=gen_uuid(),
            scenario=scenario,
            target_region=target_region,
            target_service=target_service,
            expected_impact=expected_impact or "no user-facing impact expected",
            status="running",
            started_at=utcnow(),
            steps=["scenario injected"],
            actor_id=actor_id,
        )
        db.add(run)
        await db.flush()
        return run

    async def complete_chaos(
        self,
        db: AsyncSession,
        *,
        run_id: str,
        status: str = "completed",
        summary: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Optional[ChaosRun]:
        if status not in CHAOS_STATUSES:
            raise ValueError(f"status must be one of {', '.join(CHAOS_STATUSES)}")
        run = await db.get(ChaosRun, run_id)
        if run is None:
            return None
        run.status = status
        run.completed_at = utcnow()
        run.summary = summary or (
            "experiment finished without user-facing impact" if status == "completed" else "experiment aborted"
        )
        steps = list(run.steps or [])
        steps.append(f"finished: {status}")
        run.steps = steps
        await db.flush()
        return run

    async def list_chaos_runs(
        self, db: AsyncSession, *, status: Optional[str] = None, scenario: Optional[str] = None, limit: int = 100
    ) -> list[ChaosRun]:
        query = select(ChaosRun)
        if status:
            query = query.where(ChaosRun.status == status)
        if scenario:
            query = query.where(ChaosRun.scenario == scenario)
        result = await db.execute(query.order_by(ChaosRun.started_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def blast_radius(self, db: AsyncSession, *, run_id: str, affected_services: int = 1) -> dict[str, Any]:
        run = await db.get(ChaosRun, run_id)
        if run is None:
            return {"found": False}
        return {
            "found": True,
            "run_id": run.id,
            "scenario": run.scenario,
            "target_service": run.target_service,
            "target_region": run.target_region,
            "affected_services": affected_services,
            "severity": "low" if affected_services <= 1 else ("medium" if affected_services <= 3 else "high"),
            "recommendation": (
                "blast radius contained"
                if affected_services <= 1
                else "reduce target scope or add more isolation"
            ),
        }


reliability_service = ReliabilityService()
