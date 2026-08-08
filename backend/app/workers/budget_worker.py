"""Budget health worker (Phase 13) — refreshes budget usage and flags overruns.

For every active org, recomputes usage (expenses + purchase orders) for all
budgets and records an overrun metric when a budget exceeds its allocation.

Run standalone: python -m app.workers.budget_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.finance.budget_service import budget_service
from app.models.finance import Budget
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.budget")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            budgets = (
                await session.execute(
                    select(Budget).where(
                        Budget.organization_id == org_id, Budget.status.in_(("active", "frozen"))
                    )
                )
            ).scalars().all()
            for budget in budgets:
                try:
                    await budget_service._refresh_usage(session, budget, organization_id=org_id)
                    count += 1
                except Exception as exc:  # pragma: no cover
                    logger.warning("budget worker skipped budget %s: %s", budget.id, exc)
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
                logger.info("budget worker refreshed %s budgets", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("budget worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
