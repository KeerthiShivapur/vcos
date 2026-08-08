"""Security worker (Phase 15) — security event hygiene.

Auto-resolves low/medium severity security events that aged out of the
response window, keeping the security center focused on actionable items.

Run standalone: python -m app.workers.security_worker
"""

import asyncio
import logging

from app.db.database import SessionLocal
from app.enterprise.security_service import security_service

logger = logging.getLogger("vcos.workers.security")


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            resolved = await security_service.auto_resolve_stale(session, older_than_days=14)
            await session.commit()
            return resolved
    resolved = await security_service.auto_resolve_stale(db, older_than_days=14)
    await db.commit()
    return resolved


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("security worker auto-resolved %s events", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("security worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
