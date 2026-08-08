"""Knowledge quality worker — re-scores freshness/quality for stale entities.

Freshness decays over time; this worker periodically re-runs the AI quality
scoring (completeness, freshness, popularity, usage, review status) for every
knowledge entity so the analytics always reflect the current state.

Run standalone: python -m app.workers.quality_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.knowledge import knowledge_base as kb
from app.knowledge.ai_service import ai_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.quality")


async def run_once() -> int:
    scored = 0
    async with SessionLocal() as db:
        org_ids = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in org_ids:
            for kind, model in kb.KIND_MODELS.items():
                entities = (
                    await db.execute(select(model).where(model.organization_id == organization_id))
                ).scalars().all()
                for entity in entities:
                    await ai_service._score(
                        db, organization_id=organization_id, entity_type=kind, entity=entity
                    )
                    scored += 1
            await db.flush()
        await db.commit()
    return scored


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            scored = await run_once()
            if scored:
                logger.info("quality worker scored %s entities", scored)
        except Exception as exc:  # pragma: no cover
            logger.exception("quality worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
