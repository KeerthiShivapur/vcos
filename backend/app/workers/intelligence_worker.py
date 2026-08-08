"""Intelligence worker — regenerates executive intelligence for every org.

Run standalone: python -m app.workers.intelligence_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.kernel.intelligence_engine import intelligence_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.intelligence")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            snapshot = await intelligence_engine.generate(db, org_id)
            await db.commit()
            total += 1
            logger.info("intelligence worker: org %s snapshot %s", org_id, snapshot["id"])
        return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("intelligence worker refreshed %s organizations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("intelligence worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
