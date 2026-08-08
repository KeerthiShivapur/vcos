"""Digital twin worker (Phase 18) — keeps the living organization model warm.

Every pass, for every active organization:
  - refreshes the digital twin,
  - recomputes organizational health,
  - regenerates predictions, recommendations, forecasts and optimizations,
  - assembles the executive morning brief (intelligence.brief event).

Everything is idempotent and derived from the same twin source of truth.

Run standalone: python -m app.workers.twin_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.digital_twin.executive_service import executive_service
from app.digital_twin.forecasting_service import forecasting_service
from app.digital_twin.health_service import health_service
from app.digital_twin.optimization_service import optimization_service
from app.digital_twin.prediction_service import prediction_service
from app.digital_twin.recommendation_service import recommendation_service
from app.digital_twin.twin_service import digital_twin_service
from app.events.publisher import publish_background_event
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.twin")


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
                await digital_twin_service.refresh(session, org_id)
                await health_service.compute(session, org_id)
                await prediction_service.generate(session, org_id)
                await forecasting_service.generate(session, org_id)
                await recommendation_service.generate(session, org_id)
                await optimization_service.generate(session, org_id)
                await executive_service.brief(session, org_id)
                await publish_background_event(
                    session,
                    name="intelligence.brief",
                    organization_id=org_id,
                    payload={"worker": "twin_worker"},
                )
                await session.flush()
                count += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("twin worker skipped org %s: %s", org_id, exc)
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
                logger.info("twin worker refreshed %s organizations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("twin worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
