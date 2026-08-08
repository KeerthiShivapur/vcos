"""Infrastructure health worker (Phase 16).

Periodically validates cluster topology (heartbeats), records service
health metrics and prunes stale health/service metrics so the
observability tables stay bounded. Returns the number of actions taken.

Run standalone: python -m app.workers.infra_health_worker
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.infrastructure.observability_service import observability_service
from app.models.infrastructure import ClusterStatus, HealthMetric, ServiceMetric

logger = logging.getLogger("vcos.workers.infra_health")

_STALE_THRESHOLD_SECONDS = 3600 * 24 * 7  # prune metric samples older than 7 days
_DEAD_HEARTBEAT_SECONDS = 900  # no heartbeat for 15 minutes => degraded


async def _record_health(db: AsyncSession) -> int:
    """Snapshot cluster health into HealthMetric rows; flag dead nodes."""
    actions = 0
    clusters = (await db.execute(select(ClusterStatus))).scalars().all()
    for cluster in clusters:
        status = cluster.status
        if cluster.last_checked_at and (utcnow() - cluster.last_checked_at).total_seconds() > _DEAD_HEARTBEAT_SECONDS:
            status = "warn"
            cluster.status = "degraded"
        value = 100.0 if status == "healthy" else (60.0 if status == "degraded" else 0.0)
        await observability_service.record_health(
            db,
            region=cluster.region,
            service=f"{cluster.cluster_type}:{cluster.name}",
            status=status,
            metric_name="availability",
            value=value,
            unit="percent",
        )
        actions += 1
    return actions


async def _prune_metrics(db: AsyncSession) -> int:
    """Delete health/service metric samples older than the retention window."""
    cutoff = utcnow() - timedelta(seconds=_STALE_THRESHOLD_SECONDS)
    removed = 0
    for model in (HealthMetric, ServiceMetric):
        result = await db.execute(delete(model).where(model.recorded_at < cutoff))
        removed += int(result.rowcount or 0)
    return removed


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            actions = await _record_health(session) + await _prune_metrics(session)
            await session.commit()
            return actions
    actions = await _record_health(db) + await _prune_metrics(db)
    await db.commit()
    return actions


async def run_forever(interval_seconds: int = 600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("infra health worker actions: %s", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("infra health worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
