"""Scheduler worker (Phase 14) — fires due cron workflows.

Each pass runs schedules whose next_run_at has passed, starting workflow
executions with the schedule payload as context.

Run standalone: python -m app.workers.scheduler_worker
"""

import asyncio
import logging

from app.automation.scheduler_service import scheduler_service
from app.db.database import SessionLocal

logger = logging.getLogger("vcos.workers.scheduler")


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            total = await scheduler_service.run_due(session, limit=50)
            await session.commit()
        return total
    total = await scheduler_service.run_due(db, limit=50)
    await db.commit()
    return total


async def run_forever(interval_seconds: int = 60) -> None:
    while True:
        try:
            started = await run_once()
            if started:
                logger.info("scheduler worker fired %s schedules", started)
        except Exception as exc:  # pragma: no cover
            logger.exception("scheduler worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
