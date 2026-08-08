"""Organization worker — refreshes living-org metrics and profile completion.

Phase 2: recomputes profile completion and availability signals for active
employees so the directory always reflects the current state.

Run standalone: python -m app.workers.organization_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.employee import Employee
from app.models.organization import Organization
from app.people.employee_service import employee_service

logger = logging.getLogger("vcos.workers.organization")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            employees = (
                await db.execute(
                    select(Employee).where(Employee.organization_id == org_id)
                )
            ).scalars().all()
            for emp in employees:
                emp.profile_completion = employee_service.compute_profile_completion(emp)
                total += 1
        await db.commit()
        return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("organization worker refreshed %s employees", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("organization worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
