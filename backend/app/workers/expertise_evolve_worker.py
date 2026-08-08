"""Expertise evolution worker — continuously evolves expertise from activity.

Applies decay so historical activity fades, then refreshes every employee's
aggregate expertise score. Event handlers already apply activity deltas in
real time; this worker keeps the numbers bounded and current.

Run standalone: python -m app.workers.expertise_evolve_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.intelligence.expertise_engine import expertise_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.expertise_evolve")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            total += await expertise_engine.recompute_all(db, organization_id=org_id)
        await db.commit()
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("expertise evolve worker refreshed %s employees", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("expertise evolve worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
