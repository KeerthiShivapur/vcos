"""Integration worker (Phase 14) — drains queued automation integration syncs.

Each sync job delivers the payload to the integration platform (webhook,
Slack/Teams, email, Zapier/Sheets/Notion) and records the result on the
integration row.

Run standalone: python -m app.workers.integration_worker
"""

import asyncio
import logging

from app.automation.integration_service import automation_integration_service
from app.db.database import SessionLocal

logger = logging.getLogger("vcos.workers.integration")


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            return await automation_integration_service.process_syncs(session, limit=50)
    return await automation_integration_service.process_syncs(db, limit=50)


async def run_forever(interval_seconds: int = 60) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("integration worker synced %s integrations", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("integration worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
