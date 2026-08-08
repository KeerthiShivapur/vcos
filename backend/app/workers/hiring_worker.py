"""Hiring worker (Phase 11) — recruitment hygiene.

Every pass:
  1. Withdraws offers that expired without a decision.
  2. Closes jobs that have zero remaining openings.
  3. Counts candidates stuck in the screening stage for a long time.

Run standalone: python -m app.workers.hiring_worker
"""

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.hr import Candidate, Job, Offer
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.hiring")


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
                offers = (
                    await session.execute(
                        select(Offer).where(
                            Offer.organization_id == org_id,
                            Offer.status.in_(["draft", "sent"]),
                            Offer.expires_at.is_not(None),
                            Offer.expires_at < today,
                        )
                    )
                ).scalars().all()
                for offer in offers:
                    offer.status = "withdrawn"
                    offer.notes = f"Auto-withdrawn after expiry {offer.expires_at.isoformat()}"
                    count += 1
                jobs = (
                    await session.execute(
                        select(Job).where(Job.organization_id == org_id, Job.status == "open")
                    )
                ).scalars().all()
                for job in jobs:
                    if job.openings <= 0:
                        job.status = "closed"
                        count += 1
                stale_cutoff = utcnow() - timedelta(days=14)
                stale = (
                    await session.execute(
                        select(Candidate).where(
                            Candidate.organization_id == org_id,
                            Candidate.stage == "screening",
                            Candidate.applied_at.is_not(None),
                            Candidate.applied_at < stale_cutoff,
                        )
                    )
                ).scalars().all()
                count += len(stale)
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("hiring worker skipped org %s: %s", org_id, exc)
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
                logger.info("hiring worker touched %s items", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("hiring worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
