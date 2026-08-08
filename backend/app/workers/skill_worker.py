"""Skill worker (Phase 10) — keeps the skills graph, gaps and org skill map fresh.

Every pass:
  1. Refreshes today's Organization Skill Map snapshot for every active org.
  2. Re-runs gap detection for active learners so recently acquired skills
     close stale gaps and new role requirements surface as gaps.

Run standalone: python -m app.workers.skill_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.learning.skill_service import skill_service
from app.models.learning_profile import LearningProfile
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.skill")


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
                snapshot = await skill_service.refresh_snapshot(session, organization_id=org_id)
                if snapshot is not None:
                    count += 1
                learners = (
                    await session.execute(
                        select(LearningProfile.employee_id).where(
                            LearningProfile.organization_id == org_id
                        )
                    )
                ).scalars().all()
                for employee_id in learners:
                    gaps = await skill_service.detect_gaps(
                        session, organization_id=org_id, employee_id=employee_id
                    )
                    count += len(gaps)
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("skill worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
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
                logger.info("skill worker touched %s items", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("skill worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
