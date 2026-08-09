"""Event bus — durable dispatch of organizational events to handlers.

Reliability model:
- publish() persists an Event row AND enqueues a BackgroundJob
  ("event.dispatch", event_id=...). If the queueing fails the event itself
  is still persisted, so nothing is lost.
- process_pending() runs the event worker's pass: it claims dispatch jobs
  atomically (compare-and-set), runs registered handlers, marks the event
  processed only after every handler succeeded, and marks the job done.
- Handlers run with per-handler isolation: a failing handler is retried on
  its own (the names of already-succeeded handlers are recorded on the job)
  without re-running handlers that already succeeded, so side effects are
  never duplicated.
- Retries use exponential backoff persisted as next_retry_at, so a pass
  never blocks on a slow retry. Jobs stuck in 'running' (crashed workers)
  are reaped and retried. Events persisted without an explicit dispatch job
  (legacy services using EventService.emit) are picked up as orphans, so
  every event eventually flows through the handlers.
- Every dispatch is idempotent: an event with processed_at set is skipped.
"""

import json
import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.intelligence import BackgroundJob, gen_uuid
from app.models.notification import Event as EventRow

logger = logging.getLogger("vcos.events.bus")

DISPATCH_JOB = "event.dispatch"
_BACKOFF_BASE_SECONDS = 60
_BACKOFF_CAP_SECONDS = 3600
_STALE_JOB_AFTER_SECONDS = 900
_MAX_ATTEMPTS_CAP = 10


def _parse_payload(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


def _retry_delay_seconds(attempts: int) -> int:
    """Exponential backoff for the Nth attempt (1-based), capped at 1 hour."""
    return min(_BACKOFF_BASE_SECONDS * (2 ** (attempts - 1)), _BACKOFF_CAP_SECONDS)


class EventBus:
    """Persistent event dispatcher with retries and full observability."""

    async def publish(
        self,
        db: AsyncSession,
        *,
        name: str,
        organization_id: Optional[str] = None,
        actor_id: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
        enqueue: bool = True,
        flush: bool = True,
    ) -> EventRow:
        """Persist an event and enqueue its dispatch job."""
        from app.services.event_service import event_service

        event = await event_service.emit(
            db, name=name, actor_id=actor_id,
            organization_id=organization_id, payload=payload, flush=flush,
        )
        if enqueue:
            if event.id is None:
                # Caller deferred the flush (flush=False); the dispatch job needs
                # a durable event id, so force the id assignment before serializing.
                await db.flush()
            db.add(
                BackgroundJob(
                    organization_id=organization_id,
                    name=DISPATCH_JOB,
                    status="queued",
                    event_id=event.id,
                    payload_json=json.dumps({"event_id": event.id}),
                )
            )
            if flush:
                await db.flush()
        return event

    async def enqueue(self, db: AsyncSession, *, name: str, organization_id: Optional[str] = None,
                      payload: Optional[dict[str, Any]] = None) -> BackgroundJob:
        job = BackgroundJob(
            organization_id=organization_id, name=name, status="queued",
            payload_json=json.dumps(payload or {}, default=str),
        )
        db.add(job)
        await db.flush()
        return job

    # ------------------------------------------------------------------ processing

    async def process_pending(
        self,
        db: AsyncSession,
        *,
        limit: int = 100,
        event_names: Optional[list[str]] = None,
    ) -> int:
        """One worker pass: dispatch queued events to their handlers.

        Returns the number of events fully processed.

        Concurrency & reliability guarantees:
        - Jobs are claimed atomically (compare-and-set on queued/retry -> running),
          so concurrent workers never dispatch the same event twice.
        - Orphan events (persisted without an explicit dispatch job) are claimed
          by inserting their dispatch job with ON CONFLICT DO NOTHING — the
          (name, event_id) uniqueness makes the first worker the owner.
        - Handlers run with per-handler isolation: a failing handler is retried
          (names of already-succeeded handlers are recorded on the job) without
          re-running handlers that already succeeded.
        - Failed attempts use exponential backoff persisted as next_retry_at, so
          the pass never blocks on a retry.
        - Stale 'running' jobs (crashed workers) are reaped and retried.
        - Events whose dispatch job permanently failed are re-adopted as orphans
          and retried, so nothing is ever lost.
        - Job-backed and orphan events are merged by age, so neither queue
          starves under sustained inflow.
        """
        from app.events.subscriber import get_handlers
        from app.events import handlers  # noqa: F401 - ensure registration

        now = utcnow()

        # Reap jobs stuck in 'running' from crashed workers so their events
        # are retried instead of being lost.
        await db.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.name == DISPATCH_JOB,
                BackgroundJob.status == "running",
                BackgroundJob.started_at.isnot(None),
                BackgroundJob.started_at < now - timedelta(seconds=_STALE_JOB_AFTER_SECONDS),
            )
            .values(status="retry", started_at=None)
            .execution_options(synchronize_session=False)
        )

        jobs = (
            await db.execute(
                select(BackgroundJob)
                .where(
                    BackgroundJob.name == DISPATCH_JOB,
                    BackgroundJob.status.in_(("queued", "retry")),
                    or_(
                        BackgroundJob.next_retry_at.is_(None),
                        BackgroundJob.next_retry_at <= now,
                    ),
                )
                .order_by(BackgroundJob.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        job_event_ids = {
            (job.payload or {}).get("event_id")
            for job in jobs
            if (job.payload or {}).get("event_id")
        }
        owned_event_ids = (
            select(BackgroundJob.event_id).where(
                BackgroundJob.name == DISPATCH_JOB,
                BackgroundJob.event_id.isnot(None),
                BackgroundJob.status.in_(("queued", "retry", "running")),
            )
        )
        orphans = (
            await db.execute(
                select(EventRow)
                .where(
                    EventRow.processed_at.is_(None),
                    EventRow.id.not_in(owned_event_ids),
                    EventRow.id.not_in(list(job_event_ids)) if job_event_ids else True,
                )
                .order_by(EventRow.occurred_at.asc())
                .limit(limit)
            )
        ).scalars().all()

        # Merge job-backed and orphan events by age so neither source
        # starves, then cap the whole pass at `limit` events.
        work: list[tuple[EventRow, Optional[BackgroundJob]]] = []
        for job in jobs:
            event = await db.get(EventRow, (job.payload or {}).get("event_id"))
            if event is None:
                job.status = "failed"
                job.error = "event row missing"
                job.finished_at = now
                continue
            work.append((event, job))
        work.extend((event, None) for event in orphans)
        work.sort(key=lambda item: ensure_aware(item[0].occurred_at))
        work = work[:limit]

        processed = 0
        for event, job in work:
            if event_names and event.name not in event_names:
                continue
            if event.processed_at is not None:
                if job is not None:
                    job.status = "done"
                    job.finished_at = now
                continue

            if job is not None:
                if not await self._claim_job(db, job, event.id, now):
                    continue  # another worker owns it now
            else:
                job = await self._claim_orphan(db, event, now)
                if job is None:
                    continue  # another worker created the dispatch job

            event_payload = _parse_payload(event.payload_json)
            handlers_for = get_handlers(event.name)
            if not handlers_for:
                # nothing subscribes — still let automation (triggers/rules)
                # fire, then mark processed so we never rescan it
                await self._run_automation(db, event, event_payload)
                event.processed_at = now
                job.status = "done"
                job.finished_at = now
                processed += 1
                await db.flush()
                continue

            job_payload = job.payload or {}
            succeeded = set(job_payload.get("succeeded_handlers") or [])
            failures: list[str] = []
            for handler in handlers_for:
                if handler.__name__ in succeeded:
                    continue
                try:
                    await handler(db, event, event_payload)
                    succeeded.add(handler.__name__)
                except Exception as exc:  # noqa: BLE001 - per-handler retry semantics
                    failures.append(f"{handler.__name__}: {exc}")
                    logger.warning("handler %s failed for %s: %s", handler.__name__, event.name, exc)

            await self._run_automation(db, event, event_payload)

            if not failures:
                event.processed_at = now
                job.status = "done"
                job.finished_at = now
                processed += 1
            else:
                job.error = "; ".join(failures)[:2000]
                job.payload_json = json.dumps(
                    {**job_payload, "succeeded_handlers": sorted(succeeded)}, default=str
                )
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    job.finished_at = now
                    # Release ownership of the event so the orphan picker can
                    # re-adopt it with a fresh job — nothing is ever lost.
                    job.event_id = None
                    logger.error("event %s permanently failed after %s attempts: %s",
                                 event.name, job.attempts, job.error)
                else:
                    delay = _retry_delay_seconds(job.attempts)
                    job.status = "retry"
                    job.next_retry_at = now + timedelta(seconds=delay)
                    logger.warning("event %s attempt %s failed, retry in %ss: %s",
                                   event.name, job.attempts, delay, job.error)
            await db.flush()
        await db.commit()
        return processed

    async def _claim_job(
        self, db: AsyncSession, job: BackgroundJob, event_id: str, now: Any
    ) -> bool:
        """Atomically claim a queued/retry dispatch job (compare-and-set).

        Only one concurrent worker can flip the row to 'running'; losers get
        a 0-row update and skip the event, so double dispatch is impossible.
        """
        result = await db.execute(
            update(BackgroundJob)
            .where(
                BackgroundJob.id == job.id,
                BackgroundJob.status.in_(("queued", "retry")),
            )
            .values(
                status="running",
                started_at=now,
                attempts=BackgroundJob.attempts + 1,
                event_id=event_id,
            )
            .execution_options(synchronize_session=False)
        )
        await db.flush()
        if result.rowcount != 1:
            return False
        # Reload the row so the session's "loaded state" matches the DB —
        # otherwise later attribute changes equal to the stale loaded values
        # (e.g. status retry -> running -> retry) would never be flushed.
        await db.refresh(job)
        return True

    async def _claim_orphan(
        self, db: AsyncSession, event: EventRow, now: Any
    ) -> Optional[BackgroundJob]:
        """Claim an orphan event by creating its dispatch job with ON CONFLICT.

        The (name, event_id) unique index makes the first worker the owner;
        a conflicting insert means another worker already claimed it.
        """
        job = BackgroundJob(
            id=gen_uuid(),
            organization_id=event.organization_id,
            name=DISPATCH_JOB,
            status="running",
            attempts=1,
            event_id=event.id,
            payload_json=json.dumps({"event_id": event.id}),
            started_at=now,
        )
        # on_conflict_do_nothing lives on the dialect-specific insert.
        from sqlalchemy.dialects import postgresql, sqlite

        dialect = db.get_bind().dialect.name
        dialect_insert = postgresql.insert if dialect == "postgresql" else sqlite.insert
        result = await db.execute(
            dialect_insert(BackgroundJob)
            .values(
                id=job.id,
                organization_id=job.organization_id,
                name=DISPATCH_JOB,
                status="running",
                attempts=1,
                event_id=event.id,
                payload_json=job.payload_json,
                started_at=now,
            )
            .on_conflict_do_nothing(index_elements=["name", "event_id"])
        )
        await db.flush()
        if result.rowcount != 1:
            return None
        # Reload through the session so subsequent status mutations on the
        # returned job are actually persisted at commit.
        return await db.get(BackgroundJob, job.id)

    async def _run_automation(self, db: AsyncSession, event: EventRow, payload: dict[str, Any]) -> None:
        """Phase 14 hook: fire event-driven workflow triggers and business rules.

        Runs inside the same dispatch transaction as the regular handlers so a
        failed automation attempt is retried with the same job semantics.
        """
        try:
            from app.automation.trigger_service import trigger_engine
            from app.automation.rule_service import rule_engine

            await trigger_engine.on_event(
                db, event.name, event.organization_id, payload, actor_id=event.actor_id,
            )
            await rule_engine.on_event(
                db, event.name, event.organization_id, payload, actor_id=event.actor_id,
            )
        except Exception as exc:  # noqa: BLE001 - automation must never block the bus
            logger.warning("automation hook failed for %s: %s", event.name, exc)

    async def retry_failed(self, db: AsyncSession, *, limit: int = 50) -> int:
        """Reset failed dispatch jobs so they are picked up again."""
        rows = (
            await db.execute(
                select(BackgroundJob)
                .where(BackgroundJob.name == DISPATCH_JOB, BackgroundJob.status == "failed")
                .order_by(BackgroundJob.updated_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        now = utcnow()
        for job in rows:
            if job.attempts >= job.max_attempts:
                # human-recoverable: allow another window, but cap growth so
                # the retry budget cannot balloon without bound
                job.max_attempts = min(job.max_attempts + 2, _MAX_ATTEMPTS_CAP)
            job.status = "retry"
            job.error = None
            job.started_at = None
            job.next_retry_at = None
            job.updated_at = now  # type: ignore[misc]
        await db.commit()
        return len(rows)

    # ------------------------------------------------------------------ observability

    async def stats(self, db: AsyncSession, *, organization_id: Optional[str] = None) -> dict[str, Any]:
        from sqlalchemy import func

        filters = []
        if organization_id:
            filters.append(BackgroundJob.organization_id == organization_id)
        rows = (
            await db.execute(
                select(BackgroundJob.status, func.count(BackgroundJob.id))
                .where(*filters)
                .group_by(BackgroundJob.status)
            )
        ).all()
        stats = {status: count for status, count in rows}
        return {
            "queued": stats.get("queued", 0),
            "running": stats.get("running", 0),
            "done": stats.get("done", 0),
            "retry": stats.get("retry", 0),
            "failed": stats.get("failed", 0),
        }

    async def recent_events(
        self, db: AsyncSession, *, organization_id: Optional[str] = None,
        limit: int = 50, processed: Optional[bool] = None,
    ) -> list[dict[str, Any]]:
        filters = []
        if organization_id:
            filters.append(EventRow.organization_id == organization_id)
        if processed is True:
            filters.append(EventRow.processed_at.isnot(None))
        elif processed is False:
            filters.append(EventRow.processed_at.is_(None))
        rows = (
            await db.execute(
                select(EventRow).where(*filters).order_by(EventRow.occurred_at.desc()).limit(limit)
            )
        ).scalars().all()
        result = []
        for event in rows:
            result.append({
                "id": event.id,
                "name": event.name,
                "organization_id": event.organization_id,
                "actor_id": event.actor_id,
                "payload": _parse_payload(event.payload_json),
                "occurred_at": ensure_aware(event.occurred_at).isoformat() if event.occurred_at else None,
                "processed_at": ensure_aware(event.processed_at).isoformat() if event.processed_at else None,
            })
        return result

    async def recent_jobs(
        self, db: AsyncSession, *, organization_id: Optional[str] = None,
        limit: int = 50, status: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        filters = []
        if organization_id:
            filters.append(BackgroundJob.organization_id == organization_id)
        if status:
            filters.append(BackgroundJob.status == status)
        rows = (
            await db.execute(
                select(BackgroundJob).where(*filters).order_by(BackgroundJob.created_at.desc()).limit(limit)
            )
        ).scalars().all()
        result = []
        for job in rows:
            result.append({
                "id": job.id,
                "name": job.name,
                "organization_id": job.organization_id,
                "status": job.status,
                "attempts": job.attempts,
                "max_attempts": job.max_attempts,
                "event_id": job.event_id,
                "error": job.error,
                "payload": job.payload,
                "created_at": ensure_aware(job.created_at).isoformat() if job.created_at else None,
                "started_at": ensure_aware(job.started_at).isoformat() if job.started_at else None,
                "finished_at": ensure_aware(job.finished_at).isoformat() if job.finished_at else None,
                "next_retry_at": ensure_aware(job.next_retry_at).isoformat() if job.next_retry_at else None,
            })
        return result


event_bus = EventBus()


async def dispatch_event(db: AsyncSession, name: str, organization_id: Optional[str],
                         actor_id: Optional[str], payload: Optional[dict]) -> EventRow:
    """Convenience wrapper used by routers/services to fire a Phase 9 event."""
    return await event_bus.publish(
        db, name=name, organization_id=organization_id,
        actor_id=actor_id, payload=payload,
    )
