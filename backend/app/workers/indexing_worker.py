"""Knowledge indexing worker — bounded semantic index repair (Slice 4D.2).

Supersedes the O(N) full-org rescan: the previous implementation iterated
every organization, every kind, every entity — work proportional to total
estate size. Freshness is change-driven through the durable event bus
(handlers call :func:`app.knowledge.semantic_indexer.reindex_entity` on every
create/update/delete), so this worker is only a repair sweep: it re-indexes
the most recently changed entities whose chunk vectors are stale or missing.
Hard SQL caps keep every pass proportional to recent change volume.

For each swept entity it also repairs the legacy single-row
``knowledge_search_index`` entry (the pre-4D.2 lexical index) when missing, so
existing Phase 4 search keeps working after a backfill.

Run standalone: python -m app.workers.indexing_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.knowledge import knowledge_base as kb
from app.knowledge import semantic_indexer
from app.models.knowledge import KnowledgeIndex

logger = logging.getLogger("vcos.workers.indexing")

SWEEP_PER_KIND = 40
MAX_SWEEP = 240


async def _repair_legacy_index(
    db, *, organization_id: str, kind: str, entity: object
) -> None:
    """Bounded repair of the legacy single-row lexical index (one entity)."""
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


async def run_once(max_sweep: int = MAX_SWEEP) -> int:
    """One bounded repair pass: re-index stale vectors for recent entities."""
    reindexed = 0
    async with SessionLocal() as db:
        for kind, model in kb.KIND_MODELS.items():
            entities = (
                await db.execute(
                    select(model).order_by(model.updated_at.desc()).limit(SWEEP_PER_KIND)
                )
            ).scalars().all()
            for entity in entities:
                if reindexed >= max_sweep:
                    break
                fresh = await semantic_indexer.is_fresh(
                    db,
                    organization_id=entity.organization_id,
                    kind=kind,
                    entity_id=entity.id,
                    source_updated_at=getattr(entity, "updated_at", None),
                )
                if fresh:
                    continue
                try:
                    written = await semantic_indexer.reindex_entity(
                        db,
                        organization_id=entity.organization_id,
                        kind=kind,
                        entity_id=entity.id,
                    )
                    await _repair_legacy_index(
                        db, organization_id=entity.organization_id, kind=kind, entity=entity
                    )
                    if written:
                        reindexed += 1
                except Exception:  # noqa: BLE001 - per-row isolation
                    logger.exception("indexing sweep row failed: %s/%s", kind, entity.id)
            if reindexed >= max_sweep:
                break
        await db.commit()
    if reindexed:
        logger.info("indexing worker refreshed %s entities", reindexed)
    return reindexed


async def run_forever(interval_seconds: int = 1800) -> None:
    while True:
        try:
            await run_once()
        except Exception as exc:  # pragma: no cover
            logger.exception("indexing worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
