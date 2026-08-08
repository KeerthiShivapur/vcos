"""Presence worker — expires stale presence after heartbeat timeouts.

Phase 2: employees whose last heartbeat is older than the timeout are marked
offline so the directory presence indicators stay truthful.

Run standalone: python -m app.workers.presence_worker
"""

import asyncio
import logging
from datetime import timedelta

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.employee import EmployeePresence

logger = logging.getLogger("vcos.workers.presence")

PRESENCE_TIMEOUT_MINUTES = 10


async def run_once() -> int:
    cutoff = utcnow() - timedelta(minutes=PRESENCE_TIMEOUT_MINUTES)
    async with SessionLocal() as db:
        stale = (
            await db.execute(
                select(EmployeePresence).where(
                    EmployeePresence.is_online.is_(True),
                    EmployeePresence.last_active_at.isnot(None),
                    EmployeePresence.last_active_at < cutoff,
                )
            )
        ).scalars().all()
        for p in stale:
            p.is_online = False
            p.status = "offline"
        await db.commit()
        return len(stale)


async def run_forever(interval_seconds: int = 60) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("presence worker marked %s employees offline", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("presence worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
