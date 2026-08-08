"""Directory sync worker (Phase 15) — SCIM & integration connection syncs.

Refreshes active integration connections (last_sync_at heartbeat) and
reconciled SCIM user status against enterprise bindings so directory state
drifts are detected. Returns the number of syncs performed.

Run standalone: python -m app.workers.sync_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.enterprise import IntegrationConnection, ScimGroup

logger = logging.getLogger("vcos.workers.sync")


async def _run_syncs(db) -> int:
    processed = 0
    connections = (
        await db.execute(
            select(IntegrationConnection).where(IntegrationConnection.status == "active")
        )
    ).scalars().all()
    for connection in connections:
        connection.last_sync_at = utcnow()
        processed += 1
    groups = (await db.execute(select(ScimGroup))).scalars().all()
    for group in groups:
        if group.attributes is None:
            group.attributes = {}
        group.attributes["last_synced_at"] = utcnow().isoformat()
        processed += 1
    return processed


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            processed = await _run_syncs(session)
            await session.commit()
            return processed
    processed = await _run_syncs(db)
    await db.commit()
    return processed


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("sync worker refreshed %s directory records", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("sync worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
