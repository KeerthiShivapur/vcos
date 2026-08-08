"""Pattern worker — repeated organizational pattern detection.

Run standalone: python -m app.workers.pattern_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.intelligence.pattern_engine import pattern_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.pattern")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            total += await pattern_engine.scan(db, organization_id=org_id)
            await db.flush()
        await db.commit()
    return total


async def run_forever(interval_seconds: int = 43200) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("pattern worker updated %s patterns", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("pattern worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
