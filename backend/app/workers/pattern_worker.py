"""Pattern evaluation worker — Slice 4D.4 change-driven pattern intelligence.

The pattern layer is *change-driven*: significant events enqueue a
``pattern.evaluate`` job (one per event, deduplicated by the ``(name,
event_id)`` uniqueness constraint). This worker drains those jobs in bounded
FIFO batches using the same atomic CAS claim as the memory formation worker,
so any number of worker processes can run concurrently without
double-processing.

Idempotency is enforced twice: jobs are claimed once (CAS), and ``PatternEvent``
rows make each event's contribution exactly-once even across replays.

An orphan adoption pass (bounded) picks up significant events that never got an
evaluation job; a bounded fade/resolve sweep ages patterns that stopped
recurring. No organization-wide rescan exists anywhere in this pipeline.

Observational-only: the pipeline reads operating tables and writes pattern /
intelligence tables. No operating entity is ever mutated here.

Run standalone: python -m app.workers.pattern_worker
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update

from app.db.database import SessionLocal
from app.intelligence import pattern_pipeline
from app.models.intelligence import BackgroundJob
from app.models.notification import Event as EventRow

logger = logging.getLogger("vcos.workers.pattern")

MAX_BATCH = 50
ADOPT_CANDIDATES = 200
STALE_RUNNING_SECONDS = 600
FADE_SWEEP_LIMIT = 50


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _claim_batch(db, *, limit: int) -> list[BackgroundJob]:
    """Atomic claim of the oldest queued evaluation jobs (CAS on status)."""
    jobs = (
        await db.execute(
            select(BackgroundJob)
            .where(
                BackgroundJob.name == pattern_pipeline.EVALUATE_JOB,
                BackgroundJob.status == "queued",
            )
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
    is reprocessed (bounded by the evaluation job family)."""
    deadline = _now() - timedelta(seconds=STALE_RUNNING_SECONDS)
    result = await db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.name == pattern_pipeline.EVALUATE_JOB,
            BackgroundJob.status == "running",
            BackgroundJob.started_at < deadline,
        )
        .values(status="queued", started_at=None)
    )
    return result.rowcount or 0


async def _adopt_orphan_events(db) -> int:
    """Enqueue evaluation jobs for significant events that have none.

    Bounded: only the oldest unprocessed significant events are considered,
    and events already owned by a job (or already evaluated) are skipped.
    """
    events = (
        await db.execute(
            select(EventRow)
            .where(
                EventRow.processed_at.is_(None),
                EventRow.name.in_(pattern_pipeline.PATTERN_EVENTS),
            )
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
                    BackgroundJob.name == pattern_pipeline.EVALUATE_JOB
                )
            )
        ).scalars().all()
    )
    evaluated = set(
        (
            await db.execute(
                select(pattern_pipeline.PatternEvent.event_id).where(
                    pattern_pipeline.PatternEvent.event_id.in_([e.id for e in events])
                )
            )
        ).scalars().all()
    )
    adopted = 0
    for event in events:
        if event.id in owned or event.id in evaluated:
            continue
        await pattern_pipeline.enqueue_evaluation(
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
        # Event vanished (org deleted / row purged) — nothing to evaluate.
        job.status = "done"
        job.finished_at = now
        return
    try:
        trace = await pattern_pipeline.process_event(db, event=event)
        job.status = "done"
        job.finished_at = now
        if trace and trace.get("patterns"):
            logger.debug(
                "pattern evaluation from event %s: %s patterns",
                event.name, len(trace["patterns"]),
            )
    except Exception as exc:  # noqa: BLE001 - per-job isolation
        job.attempts += 1
        job.error = f"{type(exc).__name__}: {exc}"[:500]
        if job.attempts >= job.max_attempts:
            job.status = "failed"
            job.finished_at = now
            logger.warning(
                "pattern.evaluate job %s failed permanently (%s): %s",
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
    """One bounded pass: claim + process evaluation jobs, adopt orphans,
    age stale patterns. Returns the number of evaluation jobs processed."""
    owns_session = db is None
    session = db if db is not None else SessionLocal()
    processed = 0
    try:
        await _reclaim_stale_running(session)
        batch = await _claim_batch(session, limit=limit)
        if organization_id:
            batch = [job for job in batch if job.organization_id == organization_id]
        for job in batch:
            await _process_job(session, job)
            processed += 1
        await _adopt_orphan_events(session)
        await pattern_pipeline.evaluate_fading(
            session, organization_id=organization_id, limit=FADE_SWEEP_LIMIT
        )
        await session.commit()
    finally:
        if owns_session:
            await session.close()
    if processed:
        logger.info("pattern worker processed %s events", processed)
    return processed


async def run_forever(interval_seconds: int = 120) -> None:
    while True:
        try:
            await run_once()
        except Exception as exc:  # pragma: no cover
            logger.exception("pattern worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
