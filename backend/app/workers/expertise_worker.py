"""Expertise worker — keeps expertise scores fresh for every organization.

Phase 2: recomputes per-employee expertise scores from skill rows, and
refreshes each employee's aggregate expertise_score column.

Run standalone: python -m app.workers.expertise_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.organization import Organization
from app.people.expertise_service import expertise_service

logger = logging.getLogger("vcos.workers.expertise")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            processed = await expertise_service.recompute_all(db, organization_id=org_id)
            total += processed
        await db.commit()
        return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("expertise worker refreshed %s employees", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("expertise worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
