"""AI predictions worker — keeps risk predictions fresh.

Recomputes delay/burnout/overload/attrition predictions for every
organization so the companion answers and the insights feed always reflect
current state.

Run standalone: python -m app.workers.ai_predictions_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.ai.predictions import prediction_engine
from app.db.database import SessionLocal
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.ai_predictions")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        orgs = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in orgs:
            try:
                counts = await prediction_engine.predict_all(db, organization_id=organization_id)
                await db.commit()
                total += sum(counts.values())
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("predictions worker failed for %s: %s", organization_id, exc)
                await db.rollback()
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("ai predictions worker refreshed %s predictions", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("ai predictions worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
