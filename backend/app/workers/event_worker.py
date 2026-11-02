"""Event worker — dispatches persisted events to their handlers.

The heart of Phase 9: every business action published to the event bus is
processed here, updating expertise, graph, knowledge, learning and
notifications. Failures are retried via BackgroundJob attempts.

Run standalone: python -m app.workers.event_worker

Tenant isolation: processes events per-organization so institutional
intelligence never leaks across organizations.
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.events.event_bus import DISPATCH_JOB, event_bus
from app.models.intelligence import BackgroundJob
from app.models.notification import Event as EventRow
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.event")


async def _get_orgs_with_pending_events(db, limit: int = 100) -> list[str]:
    """Get organizations that have pending or retry dispatch jobs.

    Also includes organizations whose only pending work is orphan events
    (persisted via EventService.emit without a dispatch job): the bus claims
    those as orphans during processing, but org discovery has to include them
    or they would never be dispatched by the scheduled worker.
    """
    org_ids = (
        await db.execute(
            select(BackgroundJob.organization_id)
            .where(
                BackgroundJob.name == DISPATCH_JOB,
                BackgroundJob.status.in_(("queued", "retry")),
                BackgroundJob.organization_id.isnot(None),
            )
            .distinct()
            .limit(limit)
        )
    ).scalars().all()
    owned_event_ids = select(BackgroundJob.event_id).where(
        BackgroundJob.name == DISPATCH_JOB,
        BackgroundJob.event_id.isnot(None),
        BackgroundJob.status.in_(("queued", "retry", "running")),
    )
    orphan_org_ids = (
        await db.execute(
            select(EventRow.organization_id)
            .where(
                EventRow.processed_at.is_(None),
                EventRow.organization_id.isnot(None),
                EventRow.id.not_in(owned_event_ids),
            )
            .distinct()
            .limit(limit)
        )
    ).scalars().all()
    return list(dict.fromkeys([*org_ids, *orphan_org_ids]))


async def run_once(limit: int = 5000) -> int:
    """Process pending events for all organizations with pending work."""
    async with SessionLocal() as db:
        org_ids = await _get_orgs_with_pending_events(db)
        total = 0
        for org_id in org_ids:
            try:
                processed = await event_bus.process_pending(
                    db, limit=limit, organization_id=org_id
                )
                if processed:
                    logger.info("event worker dispatched %s events for org %s", processed, org_id)
                total += processed
            except Exception as exc:
                logger.exception("event worker error for org %s: %s", org_id, exc)
        return total


async def run_forever(interval_seconds: int = 10) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("event worker dispatched %s events total", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("event worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())