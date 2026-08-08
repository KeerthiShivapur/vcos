"""Monitoring worker (Phase 15) — metrics retention and health snapshots.

Prunes system metrics and observability logs older than the retention
window so the enterprise console stays bounded and responsive.

Run standalone: python -m app.workers.monitoring_worker
"""

import asyncio
import logging

from app.db.database import SessionLocal
from app.enterprise.monitoring_service import monitoring_service
from app.enterprise.observability_service import observability_service

logger = logging.getLogger("vcos.workers.monitoring")


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            pruned = await monitoring_service.prune(session, older_than_days=30)
            pruned += await observability_service.prune(session, older_than_days=30)
            await session.commit()
            return pruned
    pruned = await monitoring_service.prune(db, older_than_days=30)
    pruned += await observability_service.prune(db, older_than_days=30)
    await db.commit()
    return pruned


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("monitoring worker pruned %s stale records", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("monitoring worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
