"""Executive analytics worker — trend materialization.

Refreshes weekly organization metrics for the trend analysis views.

Run standalone: python -m app.workers.exec_analytics_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.executive.analytics import executive_analytics
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.exec_analytics")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        orgs = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in orgs:
            try:
                result = await executive_analytics.refresh(db, organization_id=organization_id)
                await db.commit()
                total += result["refreshed"]
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("exec analytics worker failed for %s: %s", organization_id, exc)
                await db.rollback()
    return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("exec analytics worker refreshed %s metrics", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("exec analytics worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
