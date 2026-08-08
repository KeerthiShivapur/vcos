"""Knowledge indexing worker — keeps the semantic search index fresh.

Entities are indexed on every write by the CRUD pipeline, but this worker
repairs gaps (e.g. rows created before Phase 4, imports) by re-indexing
entities that have no index row yet.

Run standalone: python -m app.workers.indexing_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.knowledge import knowledge_base as kb
from app.models.knowledge import KnowledgeIndex
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.indexing")


async def run_once() -> int:
    indexed = 0
    async with SessionLocal() as db:
        org_ids = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in org_ids:
            for kind, model in kb.KIND_MODELS.items():
                entities = (
                    await db.execute(select(model).where(model.organization_id == organization_id))
                ).scalars().all()
                for entity in entities:
                    row = (
                        await db.execute(
                            select(KnowledgeIndex).where(
                                KnowledgeIndex.organization_id == organization_id,
                                KnowledgeIndex.entity_type == kind,
                                KnowledgeIndex.entity_id == entity.id,
                            )
                        )
                    ).scalar_one_or_none()
                    if row is None:
                        await kb.write_index(
                            db, organization_id=organization_id, entity_type=kind, entity_id=entity.id, entity=entity
                        )
                        indexed += 1
            await db.flush()
        await db.commit()
    return indexed


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            indexed = await run_once()
            if indexed:
                logger.info("indexing worker indexed %s entities", indexed)
        except Exception as exc:  # pragma: no cover
            logger.exception("indexing worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
