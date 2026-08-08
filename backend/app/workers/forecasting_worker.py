"""Financial forecasting worker (Phase 13) — generates monthly projections.

For every active org, regenerates cash flow, budget usage, expense, revenue
and project profitability forecasts so the finance dashboard always has a
fresh, explainable projection.

Run standalone: python -m app.workers.forecasting_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.finance.forecasting_service import forecasting_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.forecasting")


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
                result = await forecasting_service.generate(
                    session, organization_id=org_id, kind="all", horizon_months=6)
                count += result["generated"]
            except Exception as exc:  # pragma: no cover
                logger.warning("forecasting worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 43200) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("forecasting worker generated %s forecasts", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("forecasting worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
