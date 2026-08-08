"""Reasoning worker — periodic company understanding digest.

For every org, the universal reasoning engine answers "what is happening in
the company" and the conclusion is recorded into the company timeline so the
living narrative stays current between evolution cycles.

Run standalone: python -m app.workers.reasoning_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.kernel.memory_engine import memory_engine
from app.kernel.reasoning_engine import reasoning_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.reasoning")


async def run_once() -> int:
    async with SessionLocal() as db:
        org_ids = (
            await db.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        total = 0
        for org_id in org_ids:
            digest = await reasoning_engine.ask(
                db, org_id, "What is happening across the company right now?"
            )
            conclusion = digest.get("conclusion") or digest.get("recommendations") or ""
            await memory_engine.record_timeline(
                db, org_id,
                event_type="organization.updated",
                title="Company understanding digest",
                category="leadership",
                detail=str(conclusion)[:500],
                metadata={"intent": digest.get("intent")},
            )
            await db.commit()
            total += 1
            logger.info("reasoning worker: org %s digested (%s)", org_id, digest.get("intent"))
        return total


async def run_forever(interval_seconds: int = 43200) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("reasoning worker digested %s organizations", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("reasoning worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
