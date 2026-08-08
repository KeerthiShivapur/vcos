"""Simulation worker — periodic organizational scenario runs.

For every org, the simulation engine projects the next quarter outlook so
executives always have a fresh what-if baseline without asking.

Run standalone: python -m app.workers.simulation_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.autonomy.simulation_engine import simulation_engine
from app.db.database import SessionLocal
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.simulation")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            run = await simulation_engine.run(
                db, org_id,
                title="Quarterly outlook",
                question="Project the next quarter across all domains",
                created_by="system.worker",
            )
            await db.commit()
            total += 1
            logger.info("simulation worker: org %s run %s", org_id, run.get("id"))
        return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("simulation worker ran %s simulations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("simulation worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
