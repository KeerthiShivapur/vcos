"""Event worker — dispatches persisted events to their handlers.

The heart of Phase 9: every business action published to the event bus is
processed here, updating expertise, graph, knowledge, learning and
notifications. Failures are retried via BackgroundJob attempts.

Run standalone: python -m app.workers.event_worker
"""

import asyncio
import logging

from app.db.database import SessionLocal
from app.events.event_bus import event_bus

logger = logging.getLogger("vcos.workers.event")


async def run_once(limit: int = 5000) -> int:
    async with SessionLocal() as db:
        return await event_bus.process_pending(db, limit=limit)


async def run_forever(interval_seconds: int = 10) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("event worker dispatched %s events", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("event worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
