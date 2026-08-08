"""Recommendation worker — successors and mentor suggestions.

Phase 2: for each employee with expertise, computes successor candidates and
mentor suggestions and stores a snapshot. This worker is a scheduling shell;
the actual computation lives in the expertise service, so the worker can
scale to run per-org in later phases.

Run standalone: python -m app.workers.recommendation_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.employee import Employee
from app.models.organization import Organization
from app.people.expertise_service import expertise_service

logger = logging.getLogger("vcos.workers.recommendation")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            leaders = (
                await db.execute(
                    select(Employee).where(
                        Employee.organization_id == org_id,
                        Employee.manager_id.is_(None),
                    )
                )
            ).scalars().all()
            for leader in leaders:
                successors = await expertise_service.successors(
                    db, organization_id=org_id, employee_id=leader.id, limit=3
                )
                if successors:
                    leader.ai_summary = (
                        leader.ai_summary
                        or f"Potential successors: {', '.join(s['name'] for s in successors)}"
                    )
                    total += 1
        await db.commit()
        return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("recommendation worker updated %s leaders (as of %s)", processed, utcnow().isoformat())
        except Exception as exc:  # pragma: no cover
            logger.exception("recommendation worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
