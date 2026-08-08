"""Executive prediction worker — predictive analytics.

Refreshes the organization-level predictions (project completion, hiring
need, turnover, knowledge growth, meeting effectiveness, innovation
momentum) for every organization.

Run standalone: python -m app.workers.exec_prediction_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.executive.forecasting import forecasting_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.exec_prediction")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        orgs = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in orgs:
            try:
                predictions = await forecasting_service.predict_all(
                    db, organization_id=organization_id, persist=True
                )
                await db.commit()
                total += len(predictions)
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("exec prediction worker failed for %s: %s", organization_id, exc)
                await db.rollback()
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("exec prediction worker persisted %s predictions", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("exec prediction worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
