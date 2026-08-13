"""Memory formation worker — Slice 4D.3 change-driven memory automation.

The memory layer is *change-driven*: significant events enqueue a
``memory.formation`` job (one per event, deduplicated by the
``(name, event_id)`` uniqueness constraint). This worker drains those jobs in
bounded FIFO batches using the same atomic CAS claim as the event bus, so any
number of worker processes can run concurrently without double-processing.

Idempotency is enforced twice: jobs are claimed once (CAS), and ``MemoryEvent``
rows make each event's contribution to memory exactly-once even across replays.

An orphan adoption pass (bounded) picks up significant events that never got a
formation job (e.g. emitted while the handler registry was loading, or emitted
by background engines that only publish audit events). The pass is bounded to
the oldest unprocessed events and only enqueues what is not already owned.

Observational-only: the pipeline reads operating tables and writes memory
tables. No operating entity is ever mutated here.

Run standalone: python -m app.workers.memory_formation_worker
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update

from app.db.database import SessionLocal
from app.memory import formation
from app.models.intelligence import BackgroundJob
from app.models.notification import Event as EventRow

logger = logging.getLogger("vcos.workers.memory_formation")

MAX_BATCH = 50
ADOPT_CANDIDATES = 200
STALE_RUNNING_SECONDS = 600


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _claim_batch(
    db, *, limit: int, organization_id: Optional[str] = None
) -> list[BackgroundJob]:
    """Atomic claim of the oldest queued formation jobs (CAS on status).

    Claims are scoped to one organization when an on-demand run supplies an
    ``organization_id`` (tenant-isolated FIFO); the scheduler runs without a
    scope and drains globally.
    """
    conditions = [
        BackgroundJob.name == formation.FORMATION_JOB,
        BackgroundJob.status == "queued",
    ]
    if organization_id:
        conditions.append(BackgroundJob.organization_id == organization_id)
    jobs = (
        await db.execute(
            select(BackgroundJob)
            .where(*conditions)
            .order_by(BackgroundJob.created_at.asc())
            .limit(limit)
        )
    ).scalars().all()
    if not jobs:
        return []
    now = _now()
    await db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.id.in_([job.id for job in jobs]),
            BackgroundJob.status == "queued",
        )
        .values(status="running", started_at=now)
    )
    await db.flush()
    claimed = (
        await db.execute(
            select(BackgroundJob)
            .where(
                BackgroundJob.id.in_([job.id for job in jobs]),
                BackgroundJob.status == "running",
            )
            .order_by(BackgroundJob.created_at.asc(), BackgroundJob.id.asc())
        )
    ).scalars().all()
    return list(claimed)


async def _reclaim_stale_running(db) -> int:
    """Return long-running jobs to the queue so a crashed worker's batch
    is reprocessed (bounded by the formation job family)."""
    deadline = _now() - timedelta(seconds=STALE_RUNNING_SECONDS)
    result = await db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.name == formation.FORMATION_JOB,
            BackgroundJob.status == "running",
            BackgroundJob.started_at < deadline,
        )
        .values(status="queued", started_at=None)
    )
    return result.rowcount or 0


async def _adopt_orphan_events(
    db, *, organization_id: Optional[str] = None
) -> int:
    """Enqueue formation jobs for significant events that have none.

    Bounded: only the oldest unprocessed significant events are considered,
    and events already owned by a job (or already fed a memory) are skipped.
    """
    conditions = [
        EventRow.processed_at.is_(None),
        EventRow.name.in_(formation.SIGNIFICANT_EVENTS),
    ]
    if organization_id:
        conditions.append(EventRow.organization_id == organization_id)
    events = (
        await db.execute(
            select(EventRow)
            .where(*conditions)
            .order_by(EventRow.occurred_at.asc())
            .limit(ADOPT_CANDIDATES)
        )
    ).scalars().all()
    if not events:
        return 0
    owned = set(
        (
            await db.execute(
                select(BackgroundJob.event_id).where(
                    BackgroundJob.name == formation.FORMATION_JOB
                )
            )
        ).scalars().all()
    )
    adopted = 0
    for event in events:
        if event.id in owned:
            continue
        await formation.enqueue_formation(
            db,
            organization_id=event.organization_id,
            event_id=event.id,
            name=event.name,
        )
        owned.add(event.id)
        adopted += 1
    return adopted


async def _process_job(db, job: BackgroundJob) -> None:
    event = None
    if job.event_id:
        event = await db.get(EventRow, job.event_id)
    now = _now()
    if event is None or not event.organization_id:
        # Event vanished (org deleted / row purged) — nothing to form.
        job.status = "done"
        job.finished_at = now
        return
    try:
        trace = await formation.process_event(db, event=event)
        job.status = "done"
        job.finished_at = now
        if trace and not trace.get("skipped"):
            logger.debug("memory formed from event %s: %s", event.name, trace.get("memory_id"))
    except Exception as exc:  # noqa: BLE001 - per-job isolation
        job.attempts += 1
        job.error = f"{type(exc).__name__}: {exc}"[:500]
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.finished_at = now
            logger.warning(
                "memory.formation job %s failed permanently (%s): %s",
                job.id, job.event_id, job.error,
            )
        else:
            job.status = "retry"
            job.next_retry_at = now + timedelta(seconds=30 * job.attempts)


async def run_once(
    db: Optional[object] = None,
    limit: int = MAX_BATCH,
    organization_id: Optional[str] = None,
) -> int:
    """One bounded pass: claim + process formation jobs, adopt orphan events.

    Returns the number of formation jobs processed (not adopted events).
    """
    owns_session = db is None
    session = db if db is not None else SessionLocal()
    processed = 0
    try:
        await _reclaim_stale_running(session)
        batch = await _claim_batch(session, limit=limit, organization_id=organization_id)
        for job in batch:
            await _process_job(session, job)
            processed += 1
        await _adopt_orphan_events(session, organization_id=organization_id)
        await session.commit()
    finally:
        if owns_session:
            await session.close()
    if processed:
        logger.info("memory formation worker processed %s events", processed)
    return processed


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        try:
            await run_once()
        except Exception as exc:  # pragma: no cover
            logger.exception("memory formation worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
