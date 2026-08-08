"""Certification worker (Phase 10) — certificate lifecycle maintenance.

Every pass:
  1. Marks earned certificates past their expiry date as expired.
  2. Counts certificates expiring soon (30 days) for visibility.

Run standalone: python -m app.workers.certification_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.learning.certification_service import certification_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.certification")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            try:
                expired = await certification_service.mark_expired(session, organization_id=org_id)
                expiring = await certification_service.expiring(session, organization_id=org_id, days=30)
                count += expired + len(expiring)
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("certification worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("certification worker processed %s certificates", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("certification worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
