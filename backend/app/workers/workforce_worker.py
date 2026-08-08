"""Workforce worker (Phase 11) — workforce snapshots.

Every pass computes today's workforce snapshot (headcount, hires, exits,
attrition, department distribution) for every active organization if one
does not already exist for the day.

Run standalone: python -m app.workers.workforce_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.hr.workforce_service import workforce_service
from app.models.hr import WorkforceSnapshot
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.workforce")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        today = utcnow().date()
        for org_id in org_ids:
            try:
                existing = (
                    await session.execute(
                        select(WorkforceSnapshot).where(
                            WorkforceSnapshot.organization_id == org_id, WorkforceSnapshot.date == today
                        )
                    )
                ).scalar_one_or_none()
                if existing:
                    continue
                snapshot = await workforce_service.compute_snapshot(session, organization_id=org_id)
                if snapshot is not None:
                    count += 1
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("workforce worker skipped org %s: %s", org_id, exc)
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
                logger.info("workforce worker created %s snapshots", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("workforce worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
