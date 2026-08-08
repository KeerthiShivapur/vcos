"""Insights worker — generates the autonomous daily briefs.

Every morning: one executive brief per organization plus a personal brief for
each active user. Also runs the duplicate-work and knowledge workers that feed
the brief content when they have not run today.

Run standalone: python -m app.workers.insights_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.intelligence.insights_engine import insights_engine
from app.models.organization import Organization
from app.models.user import User

logger = logging.getLogger("vcos.workers.insights")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            await insights_engine.generate_executive_brief(db, organization_id=org_id)
            total += 1
            user_ids = (
                await db.execute(
                    select(User.id).where(
                        User.organization_id == org_id,
                        User.status == "active",
                    )
                )
            ).scalars().all()
            for user_id in user_ids:
                try:
                    await insights_engine.generate_employee_brief(db, organization_id=org_id, user_id=user_id)
                    total += 1
                except Exception as exc:  # pragma: no cover
                    logger.warning("employee brief failed for %s: %s", user_id, exc)
            await db.flush()
        await db.commit()
    return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("insights worker generated %s briefs", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("insights worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
