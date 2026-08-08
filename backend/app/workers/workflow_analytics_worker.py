"""Workflow analytics worker (Phase 14) — materializes execution metrics.

Computes monthly execution/completion/failure/duration metrics per workflow
into WorkflowMetric rows consumed by the analytics dashboard.

Run standalone: python -m app.workers.workflow_analytics_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.automation.analytics_service import workflow_analytics
from app.db.database import SessionLocal
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.workflow_analytics")


async def run_once(db=None) -> int:
    owns_session = db is None

    async def _work(session) -> int:
        total = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            written = await workflow_analytics.materialize(session, organization_id=org_id)
            total += written
        return total

    if owns_session:
        async with SessionLocal() as session:
            total = await _work(session)
            await session.commit()
        return total
    total = await _work(db)
    await db.commit()
    return total


async def run_forever(interval_seconds: int = 43200) -> None:
    while True:
        try:
            written = await run_once()
            if written:
                logger.info("workflow analytics worker wrote %s metrics", written)
        except Exception as exc:  # pragma: no cover
            logger.exception("workflow analytics worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
