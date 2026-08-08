"""Relationship intelligence worker (Phase 12) — org-graph coverage.

Rebuilds customer edges in the organization graph (employee ownership,
touches, meetings, projects, contracts, tickets) so the graph engine and
relationship views always reflect the latest customer activity.

Run standalone: python -m app.workers.relationship_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.customers.relationship_service import relationship_service
from app.db.database import SessionLocal
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.relationship")


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
                result = await relationship_service.build_graph(session, organization_id=org_id)
                count += result.get("edges", 0)
            except Exception as exc:  # pragma: no cover
                logger.warning("relationship worker skipped org %s: %s", org_id, exc)
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
                logger.info("relationship worker upserted %s edge(s)", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("relationship worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
