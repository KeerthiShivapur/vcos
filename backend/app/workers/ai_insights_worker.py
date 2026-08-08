"""AI insights worker — proactive organizational intelligence.

Scans every organization and persists actionable insights (overload, meeting
load, overdue clusters) into ``ai_insights``. Runs alongside the predictions
worker so the companion always has fresh context.

Run standalone: python -m app.workers.ai_insights_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.ai.insights import insight_engine
from app.db.database import SessionLocal
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.ai_insights")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        orgs = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in orgs:
            try:
                insights = await insight_engine.scan_organization(
                    db, organization_id=organization_id
                )
                await db.commit()
                total += len(insights)
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("insights worker failed for %s: %s", organization_id, exc)
                await db.rollback()
    return total


async def run_forever(interval_seconds: int = 1800) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("ai insights worker persisted %s insights", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("ai insights worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
