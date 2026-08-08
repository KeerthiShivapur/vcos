"""Governance worker — keeps the human-in-the-loop loop healthy.

For every org, escalates AI recommendations that have been awaiting human
review for too long, so nothing important sits unsigned forever.

Run standalone: python -m app.workers.governance_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.kernel.governance_engine import governance_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.governance")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            escalated = await governance_engine.escalate_stale(db, org_id)
            await db.commit()
            total += escalated
            if escalated:
                logger.info("governance worker: org %s escalated %s", org_id, escalated)
        return total


async def run_forever(interval_seconds: int = 21600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("governance worker escalated %s recommendations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("governance worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
