"""Recommendation feed worker — regenerates personalized feeds.

For every active employee, regenerate the personalized recommendation feed so
it reflects the latest expertise, knowledge and collaboration signals.

Run standalone: python -m app.workers.recommendation_feed_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.intelligence.recommendation_engine import recommendation_engine
from app.models.employee import Employee
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.recommendation_feed")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            employees = (
                await db.execute(
                    select(Employee).where(
                        Employee.organization_id == org_id,
                        Employee.status == "active",
                        Employee.user_id.isnot(None),
                    )
                )
            ).scalars().all()
            for employee in employees:
                try:
                    await recommendation_engine.generate_for_user(
                        db, organization_id=org_id, user_id=employee.user_id
                    )
                    total += 1
                except Exception as exc:  # pragma: no cover
                    logger.warning("feed failed for %s: %s", employee.id, exc)
            await db.flush()
        await db.commit()
    return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("recommendation feed worker refreshed %s feeds", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("recommendation feed worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
