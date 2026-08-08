"""Performance worker (Phase 11) — keeps performance hygiene.

Every pass:
  1. Moves cycles past their end date from open → reviewing.
  2. Counts overdue goals (past due date, not completed) and draft reviews
     in open cycles so HR sees the backlog.

Run standalone: python -m app.workers.performance_worker
"""

import asyncio
import logging
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.hr import PerformanceCycle, PerformanceGoal, PerformanceReview
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.performance")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        today = utcnow().date()
        for org_id in org_ids:
            try:
                cycles = (
                    await session.execute(
                        select(PerformanceCycle).where(PerformanceCycle.organization_id == org_id)
                    )
                ).scalars().all()
                for cycle in cycles:
                    period = cycle.period or {}
                    end = period.get("end")
                    if cycle.status == "open" and end and date.fromisoformat(end) < today:
                        cycle.status = "reviewing"
                        count += 1
                goals = (
                    await session.execute(
                        select(PerformanceGoal).where(
                            PerformanceGoal.organization_id == org_id,
                            PerformanceGoal.due_date.is_not(None),
                            PerformanceGoal.due_date < today,
                            PerformanceGoal.status != "completed",
                        )
                    )
                ).scalars().all()
                overdue = len(goals)
                reviews = (
                    await session.execute(
                        select(PerformanceReview).where(
                            PerformanceReview.organization_id == org_id,
                            PerformanceReview.status == "draft",
                        )
                    )
                ).scalars().all()
                count += overdue + len(reviews)
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("performance worker skipped org %s: %s", org_id, exc)
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
                logger.info("performance worker touched %s items", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("performance worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
