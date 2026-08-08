"""AI learning worker — folds feedback corrections into durable memory.

Runs the learning service so corrections users gave in past conversations
become semantic memories that ground future answers.

Run standalone: python -m app.workers.ai_learning_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.ai.learning import learning_service
from app.db.database import SessionLocal
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.ai_learning")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        orgs = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in orgs:
            try:
                result = await learning_service.learn(db, organization_id=organization_id)
                await db.commit()
                total += result["corrections_learned"]
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("learning worker failed for %s: %s", organization_id, exc)
                await db.rollback()
    return total


async def run_forever(interval_seconds: int = 43200) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("ai learning worker folded in %s corrections", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("ai learning worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
