"""Customer health worker (Phase 12) — recomputes portfolio health.

For every active org, recomputes health scores for all customers from
support, projects, communication, contracts and engagement signals, then
updates CustomerHealth rows and the Customer.health_score/status fields.

Run standalone: python -m app.workers.customer_health_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.analytics_service import analytics_service
from app.db.database import SessionLocal
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.customer_health")


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
                updated = await analytics_service.compute_customer_health(
                    session, organization_id=org_id)
                count += len(updated)
            except Exception as exc:  # pragma: no cover
                logger.warning("customer health worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("customer health worker recomputed %s customers", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("customer health worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
