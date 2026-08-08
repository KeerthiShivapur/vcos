"""Compliance policy worker (Phase 15) — overdue control enforcement.

Flags compliance controls past their due date as warn so the readiness
report reflects an aging posture before formal audits.

Run standalone: python -m app.workers.compliance_policy_worker
"""

import asyncio
import logging

from app.db.database import SessionLocal
from app.enterprise.compliance_service import compliance_service

logger = logging.getLogger("vcos.workers.compliance_policy")


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            flagged = await compliance_service.flag_overdue(session)
            await session.commit()
            return flagged
    flagged = await compliance_service.flag_overdue(db)
    await db.commit()
    return flagged


async def run_forever(interval_seconds: int = 21600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("compliance worker flagged %s overdue controls", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("compliance worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
