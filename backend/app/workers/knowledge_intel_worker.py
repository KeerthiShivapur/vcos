"""Knowledge intelligence worker — outdated/duplicate/gap/unused detection.

Run standalone: python -m app.workers.knowledge_intel_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.intelligence.knowledge_engine import knowledge_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.knowledge_intel")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            total += await knowledge_engine.scan(db, organization_id=org_id)
            await db.flush()
        await db.commit()
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("knowledge worker found %s new insights", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("knowledge worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
