"""Evolution worker — continuous organizational improvement pass.

Lighter than the orchestration worker: refresh company health, rebuild the
universal graph and regenerate executive intelligence without a full observe
cycle, so the company stays current between orchestration runs.

Run standalone: python -m app.workers.evolution_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.kernel.graph_engine import graph_engine
from app.kernel.health_engine import health_engine
from app.kernel.intelligence_engine import intelligence_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.evolution")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            health = await health_engine.refresh(db, org_id)
            await graph_engine.rebuild(db, org_id)
            await intelligence_engine.generate(db, org_id)
            await db.commit()
            total += 1
            logger.info("evolution worker: org %s health %s", org_id, health["score"])
        return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("evolution worker evolved %s organizations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("evolution worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
