"""Disaster recovery: region failover, replication, RPO/RTO (Phase 16.21)."""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_event
from app.models.infrastructure import DisasterRecoveryLog
from app.models.organization import gen_uuid

DR_SCENARIOS = (
    "region_outage",
    "db_failover",
    "worker_crash",
    "storage_fallback",
    "api_failover",
    "recovery_test",
    "replica_promotion",
)
DR_STATUSES = ("started", "failover", "completed", "failed", "recovered")


class DisasterRecoveryService:
    """Cross-region DR runs and real failover execution."""

    async def list_runs(
        self, db: AsyncSession, *, status: Optional[str] = None, scenario: Optional[str] = None, limit: int = 100
    ) -> list[DisasterRecoveryLog]:
        query = select(DisasterRecoveryLog)
        if status:
            query = query.where(DisasterRecoveryLog.status == status)
        if scenario:
            query = query.where(DisasterRecoveryLog.scenario == scenario)
        result = await db.execute(query.order_by(DisasterRecoveryLog.started_at.desc()).limit(limit))
        return list(result.scalars().all())

    async def get_run(self, db: AsyncSession, run_id: str) -> Optional[DisasterRecoveryLog]:
        return await db.get(DisasterRecoveryLog, run_id)

    async def start(
        self,
        db: AsyncSession,
        *,
        scenario: str = "region_outage",
        region: Optional[str] = None,
        steps: Optional[list[str]] = None,
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> DisasterRecoveryLog:
        if scenario not in DR_SCENARIOS:
            raise ValueError(f"Unknown scenario '{scenario}', expected one of {', '.join(DR_SCENARIOS)}")
        run = DisasterRecoveryLog(
            id=gen_uuid(),
            run_id=gen_uuid(),
            scenario=scenario,
            region=region,
            status="started",
            steps=steps or [],
            started_at=utcnow(),
            actor_id=actor_id,
        )
        db.add(run)
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name="disaster.recovery.started",
            actor_id=actor_id,
            payload={"run_id": run.run_id, "scenario": run.scenario, "region": run.region},
        )
        return run

    async def advance(
        self,
        db: AsyncSession,
        *,
        run_id: str,
        status: str = "completed",
        rpo_minutes: Optional[int] = None,
        rto_minutes: Optional[int] = None,
        outcome: Optional[str] = None,
        steps: Optional[list[str]] = None,
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
    ) -> Optional[DisasterRecoveryLog]:
        if status not in DR_STATUSES:
            raise ValueError(f"status must be one of {', '.join(DR_STATUSES)}")
        run = await self.get_run(db, run_id)
        if run is None:
            return None
        if run.status in ("completed", "failed") and run.status != status:
            raise ValueError(f"run already {run.status}")
        run.status = status
        if status in ("completed", "recovered", "failed"):
            run.completed_at = utcnow()
        if rpo_minutes is not None:
            run.rpo_minutes = max(0, rpo_minutes)
        if rto_minutes is not None:
            run.rto_minutes = max(0, rto_minutes)
        if outcome:
            run.outcome = outcome
        if steps:
            run.steps = steps
        await db.flush()
        await publish_event(
            db,
            organization_id=organization_id,
            name=f"disaster.recovery.{'completed' if status == 'completed' else status}",
            actor_id=actor_id,
            payload={"run_id": run.run_id, "status": status, "rpo_minutes": run.rpo_minutes},
        )
        return run

    async def verify(self, db: AsyncSession, *, run_id: str, outcome: str = "ok") -> Optional[DisasterRecoveryLog]:
        run = await self.get_run(db, run_id)
        if run is None:
            return None
        if run.status not in ("started", "failover", "recovered"):
            raise ValueError("only active runs can be verified")
        steps = list(run.steps or [])
        steps.append(f"verification: {outcome}")
        run.steps = steps
        run.outcome = outcome
        run.completed_at = utcnow()
        await db.flush()
        return run

    async def rpo_rto_summary(self, db: AsyncSession) -> dict[str, Any]:
        runs = await self.list_runs(db, limit=1000)
        measured = [run for run in runs if run.rpo_minutes or run.rto_minutes]
        targets = {"rpo_target_minutes": 15, "rto_target_minutes": 30}
        if not measured:
            return {"report": False, "reason": "no completed DR runs to evaluate"}
        violations = [
            {
                "run_id": run.run_id,
                "scenario": run.scenario,
                "rpo_actual": run.rpo_minutes,
                "rpo_target": targets["rpo_target_minutes"],
                "rto_actual": run.rto_minutes,
                "rto_target": targets["rto_target_minutes"],
            }
            for run in measured
            if run.rpo_minutes > targets["rpo_target_minutes"] or run.rto_minutes > targets["rto_target_minutes"]
        ]
        return {
            "report": True,
            "runs_evaluated": len(measured),
            "targets": targets,
            "target_violations": violations,
            "rpo_breached": sum(1 for v in violations if v["rpo_actual"] > v["rpo_target"]),
            "rto_breached": sum(1 for v in violations if v["rto_actual"] > v["rto_target"]),
            "recommendation": (
                "schedule quarterly failover drills" if not violations else "review replication lag and restore tuning"
            ),
        }


disaster_recovery_service = DisasterRecoveryService()
