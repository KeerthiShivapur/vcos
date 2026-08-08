"""Collaboration intelligence worker — department pair metrics and silos.

Run standalone: python -m app.workers.collab_intel_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.intelligence.collaboration_engine import collaboration_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.collab_intel")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            await collaboration_engine.compute(db, organization_id=org_id)
            total += 1
            await db.flush()
        await db.commit()
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("collaboration worker refreshed %s orgs", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("collaboration worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
