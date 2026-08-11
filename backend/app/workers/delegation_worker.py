"""Slice 4C — delegation expiry worker.

Authorization never depends on this sweep: the effective-permission
evaluation already denies expired delegations lazily. The sweep is hygiene —
it marks expired grants and records the governance.delegation.expired event
+ audit row so the lifecycle is visible and delegation rows never linger as
"active".

Run standalone: python -m app.workers.delegation_worker
"""

import asyncio
import logging

from app.db.database import SessionLocal
from app.services.governance_service import governance_service

logger = logging.getLogger("vcos.workers.delegation")


async def run_once(limit: int = 5000) -> int:
    """Sweep overdue delegations; the service emits events + audit rows."""
    async with SessionLocal() as db:
        expired = await governance_service.expire_overdue(db)
        await db.commit()
        if expired:
            logger.info("expired %s delegations", len(expired))
        return len(expired)


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        try:
            await run_once()
        except Exception as exc:  # pragma: no cover
            logger.exception("delegation sweep error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
