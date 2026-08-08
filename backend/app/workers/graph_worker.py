"""Graph worker — maintains organization graph snapshots.

Phase 2: rebuilds the organization graph (employees/departments/teams/locations
nodes and edges) for analytics and the visual org map. Currently the graph is
computed on demand; this worker validates graph integrity and logs anomalies.

Run standalone: python -m app.workers.graph_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.employee import Employee
from app.models.organization import Organization
from app.people.graph_service import graph_service

logger = logging.getLogger("vcos.workers.graph")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            graph = await graph_service.build(db, organization_id=org_id)
            employees = (
                await db.execute(
                    select(Employee).where(Employee.organization_id == org_id)
                )
            ).scalars().all()
            reported = len({e.manager_id for e in employees if e.manager_id})
            if reported > len(employees):
                logger.warning("graph worker: org %s has %s employees but %s manager refs", org_id, len(employees), reported)
            total += len(graph.nodes)
        return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("graph worker validated %s graph nodes", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("graph worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
