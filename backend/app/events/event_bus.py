"""Event bus — durable dispatch of organizational events to handlers.

Reliability model:
- publish() persists an Event row AND enqueues a BackgroundJob
  ("event.dispatch", payload={"event_id": ...}). If the queueing fails the
  event itself is still persisted, so nothing is lost.
- process_pending() runs the event worker's pass: for each queued job it
  loads the event, runs registered handlers (marking the event processed
  BEFORE dispatch so a crashing worker never double-processes), then marks
  the job done. Failures are retried up to max_attempts with exponential
  backoff tracked in the job row.
- Every dispatch is idempotent: an event with processed_at set is skipped.
"""

import asyncio
import json
import logging
from datetime import timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.models.intelligence import BackgroundJob
from app.models.notification import Event as EventRow

logger = logging.getLogger("vcos.events.bus")

DISPATCH_JOB = "event.dispatch"
_BACKOFF_BASE_SECONDS = 60


def _parse_payload(raw: Optional[str]) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, TypeError):
        return {}


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

        Returns the number of events processed. Skips events whose handlers
        were already applied (processed_at guard). Retries failed jobs.

        Events persisted without an explicit dispatch job (legacy services
        using EventService.emit) are picked up as orphans, so every event
        eventually flows through the handlers.
        """
        from app.events.subscriber import get_handlers
        from app.events import handlers  # noqa: F401 - ensure registration

        now = utcnow()
        jobs = (
            await db.execute(
                select(BackgroundJob)
                .where(BackgroundJob.name == DISPATCH_JOB, BackgroundJob.status.in_(("queued", "retry")))
                .order_by(BackgroundJob.created_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        job_event_ids = {
            (job.payload or {}).get("event_id")
            for job in jobs
            if (job.payload or {}).get("event_id")
        }
        orphans = (
            await db.execute(
                select(EventRow)
                .where(
                    EventRow.processed_at.is_(None),
                    EventRow.id.not_in(list(job_event_ids)) if job_event_ids else True,
                )
                .order_by(EventRow.occurred_at.asc())
                .limit(limit)
            )
        ).scalars().all()
        processed = 0
        for job, orphan_event in [(j, None) for j in jobs] + [(None, e) for e in orphans]:
            if job is not None:
                payload = job.payload or {}
                event = await db.get(EventRow, payload.get("event_id"))
                if event is None:
                    job.status = "failed"
                    job.error = "event row missing"
                    job.finished_at = now
                    await db.flush()
                    continue
            else:
                event = orphan_event
                job = None
            if event_names and event.name not in event_names:
                continue
            if event.processed_at is not None:
                if job is not None:
                    job.status = "done"
                    job.finished_at = now
                continue
            handlers_for = get_handlers(event.name)
            event_payload = _parse_payload(event.payload_json)
            if not handlers_for:
                # nothing subscribes — still let automation (triggers/rules) fire,
                # then mark processed so we never rescan it
                try:
                    await self._run_automation(db, event, event_payload)
                except Exception as exc:  # pragma: no cover - defensive
                    logger.warning("automation hook failed for %s: %s", event.name, exc)
                event.processed_at = now
                if job is not None:
                    job.status = "done"
                    job.finished_at = now
                processed += 1
                continue

            if job is None:
                # orphan pickup — create bookkeeping so failures are retried
                job = BackgroundJob(
                    organization_id=event.organization_id,
                    name=DISPATCH_JOB,
                    status="running",
                    attempts=1,
                    payload_json=json.dumps({"event_id": event.id}),
                    started_at=now,
                )
                db.add(job)
                await db.flush()
            else:
                job.status = "running"
                job.started_at = now
                job.attempts += 1
            try:
                for handler in handlers_for:
                    await handler(db, event, event_payload)
                await self._run_automation(db, event, event_payload)
                event.processed_at = now
                job.status = "done"
                job.finished_at = now
                processed += 1
            except Exception as exc:  # noqa: BLE001 - retry semantics
                job.error = str(exc)[:2000]
                if job.attempts >= job.max_attempts:
                    job.status = "failed"
                    job.finished_at = now
                    logger.error("event %s permanently failed after %s attempts: %s",
                                 event.name, job.attempts, exc)
                else:
                    job.status = "retry"
                    await db.flush()
                    await asyncio.sleep(min(2 ** job.attempts, 30) * 0.01)
                    logger.warning("event %s attempt %s failed, will retry: %s",
                                   event.name, job.attempts, exc)
            await db.flush()
        await db.commit()
        return processed

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
                job.max_attempts += 2  # human-recoverable: allow another window
            job.status = "retry"
            job.error = None
            job.started_at = None
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
                "error": job.error,
                "payload": job.payload,
                "created_at": ensure_aware(job.created_at).isoformat() if job.created_at else None,
                "started_at": ensure_aware(job.started_at).isoformat() if job.started_at else None,
                "finished_at": ensure_aware(job.finished_at).isoformat() if job.finished_at else None,
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
