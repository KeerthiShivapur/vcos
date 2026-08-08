"""Finance optimization worker (Phase 13) — records cost-savings signals.

For every active org, produces optimization recommendations as financial
metric rows (budget overrun candidates, high-risk vendors, missing receipts,
duplicate payment candidates) for the finance AI companion and dashboard.

Run standalone: python -m app.workers.optimization_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.finance.risk_service import risk_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.optimization")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            try:
                summary = await risk_service.summarize(session, organization_id=org_id)
                count += summary["total"]
                if count:
                    logger.info("optimization worker: org %s has %s open risks", org_id, summary["total"])
            except Exception as exc:  # pragma: no cover
                logger.warning("optimization worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("optimization worker reviewed %s risk items", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("optimization worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
