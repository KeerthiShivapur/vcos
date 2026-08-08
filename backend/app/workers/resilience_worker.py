"""Resilience worker — periodic enterprise resilience assessment.

For every org, scans for disruption signals (single-point-of-failure roles,
vendor renewals, overdue invoices, pipeline pressure, failing projects) and
keeps response plans current.

Run standalone: python -m app.workers.resilience_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.kernel.resilience_engine import resilience_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.resilience")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            result = await resilience_engine.assess(db, org_id)
            await db.commit()
            total += 1
            logger.info("resilience worker: org %s %s scenario(s)", org_id, result["total"])
        return total


async def run_forever(interval_seconds: int = 21600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("resilience worker assessed %s organizations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("resilience worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
