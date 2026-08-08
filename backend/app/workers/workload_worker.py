"""Workload worker — persists weekly workload snapshots for every employee.

Flags overloaded employees (>90% utilization) so the Executive dashboard and
organization load view stay truthful without on-demand computation.

Run standalone: python -m app.workers.workload_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.employee import Employee
from app.work.workload_service import workload_service

logger = logging.getLogger("vcos.workers.workload")


async def run_once() -> int:
    processed = 0
    async with SessionLocal() as db:
        org_ids = set(
            (await db.execute(select(Employee.organization_id))).scalars().all()
        )
        for org_id in org_ids:
            try:
                processed += await workload_service.snapshot_week(db, organization_id=org_id)
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("workload worker skipped org %s: %s", org_id, exc)
        await db.commit()
        return processed


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("workload worker snapshotted %s employees", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("workload worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
