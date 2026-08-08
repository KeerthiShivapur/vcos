"""Assessment worker (Phase 10) — assessment lifecycle maintenance.

Every pass:
  1. Auto-finalizes submitted quiz attempts that have been waiting for review
     for more than 3 days using the built-in AI auto-scorer.
  2. Expires assigned attempts that have not been started for 14+ days.

Run standalone: python -m app.workers.assessment_worker
"""

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.learning.assessment_service import assessment_service
from app.models.assessment import AssessmentAttempt
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.assessment")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    now = utcnow()
    review_cutoff = now - timedelta(days=3)
    expire_cutoff = now - timedelta(days=14)

    async def _work(session: AsyncSession) -> int:
        count = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            try:
                awaiting = (
                    await session.execute(
                        select(AssessmentAttempt).where(
                            AssessmentAttempt.organization_id == org_id,
                            AssessmentAttempt.status == "submitted",
                            AssessmentAttempt.submitted_at <= review_cutoff,
                        )
                    )
                ).scalars().all()
                for attempt in awaiting:
                    await assessment_service.evaluate(
                        session, organization_id=org_id, attempt_id=attempt.id,
                        reviewer_kind="ai", reviewer_id=None,
                    )
                    count += 1
                abandoned = (
                    await session.execute(
                        select(AssessmentAttempt).where(
                            AssessmentAttempt.organization_id == org_id,
                            AssessmentAttempt.status == "assigned",
                            AssessmentAttempt.started_at.is_(None),
                            AssessmentAttempt.created_at <= expire_cutoff,
                        )
                    )
                ).scalars().all()
                for attempt in abandoned:
                    attempt.status = "expired"
                    count += 1
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("assessment worker skipped org %s: %s", org_id, exc)
        return count

    if db is None:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("assessment worker processed %s attempts", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("assessment worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
