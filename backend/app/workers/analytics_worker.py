"""Analytics worker — refreshes derived work metrics.

Maintains the workload snapshot table for org analytics and refreshes project
health/status derived fields (progress from completed tasks). The heavy
aggregations stay on demand; this worker keeps snapshots warm.

Run standalone: python -m app.workers.analytics_worker
"""

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, select

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.employee import Employee
from app.models.organization import Organization
from app.models.task import Task
from app.work.workload_service import workload_service

logger = logging.getLogger("vcos.workers.analytics")


async def run_once() -> int:
    updated = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(
                select(Organization.id).where(Organization.status == "active")
            )
        ).scalars().all()
        for org_id in org_ids:
            try:
                updated += await workload_service.snapshot_week(db, organization_id=org_id)
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("analytics worker skipped org %s: %s", org_id, exc)
        await db.commit()
    return updated


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            updated = await run_once()
            if updated:
                logger.info("analytics worker refreshed %s snapshots", updated)
        except Exception as exc:  # pragma: no cover
            logger.exception("analytics worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
