"""Executive health worker — company health, strategic risks, recommendations.

Recomputes the company health score, detects and persists strategic risks,
and refreshes executive recommendations for every organization.

Run standalone: python -m app.workers.exec_health_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.executive.health_engine import health_engine
from app.executive.recommendation_engine import recommendation_engine
from app.executive.risk_engine import risk_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.exec_health")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        orgs = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in orgs:
            try:
                await health_engine.compute_company_health(db, organization_id=organization_id, persist=True)
                risks = await risk_engine.detect_all(db, organization_id=organization_id)
                await risk_engine.persist(db, organization_id=organization_id, risks=risks)
                await recommendation_engine.generate(db, organization_id=organization_id, persist=True)
                await db.commit()
                total += len(risks)
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("exec health worker failed for %s: %s", organization_id, exc)
                await db.rollback()
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("exec health worker processed %s risks", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("exec health worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
