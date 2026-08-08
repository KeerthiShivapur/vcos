"""Graph updates worker — rebuilds structural organization graph edges.

Event handlers add activity edges in real time; this worker rebuilds the
structural layer (reports_to, member_of, works_on, owns, assigned_to) so the
graph stays correct as the org chart changes.

Run standalone: python -m app.workers.graph_updates_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.intelligence.graph_engine import graph_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.graph_updates")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            total += await graph_engine.rebuild_structural(db, organization_id=org_id)
        await db.commit()
    return total


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("graph worker rebuilt %s structural edges", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("graph worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
