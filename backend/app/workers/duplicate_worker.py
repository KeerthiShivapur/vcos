"""Duplicate detection worker — flags near-identical knowledge items.

Compares embeddings per kind and marks duplicate_of on KnowledgeQuality rows,
emitting `knowledge.duplicate_detected` events so the AI reports can surface
them for consolidation.

Run standalone: python -m app.workers.duplicate_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.knowledge.ai_service import ai_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.duplicate")


async def run_once() -> int:
    detected = 0
    async with SessionLocal() as db:
        org_ids = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in org_ids:
            detected += await ai_service.scan_duplicates_org(db, organization_id=organization_id)
            await db.flush()
        await db.commit()
    return detected


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            detected = await run_once()
            if detected:
                logger.info("duplicate worker flagged %s pairs", detected)
        except Exception as exc:  # pragma: no cover
            logger.exception("duplicate worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
