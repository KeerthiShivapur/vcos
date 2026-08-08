"""Innovation worker — continuous organizational idea scanning.

For every org, the innovation engine scans community discussions, knowledge
activity, customer conversations and emerging skills to surface new ideas,
experiments and market opportunities.

Run standalone: python -m app.workers.innovation_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.intelligence_network.innovation_engine import innovation_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.innovation")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            result = await innovation_engine.scan(db, org_id)
            await db.commit()
            total += 1
            logger.info("innovation worker: org %s %s signal(s)", org_id, result.get("total", 0))
        return total


async def run_forever(interval_seconds: int = 43200) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("innovation worker scanned %s organizations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("innovation worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
