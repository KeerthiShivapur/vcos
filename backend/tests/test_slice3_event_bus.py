"""Slice 3 — event bus hardening tests.

Covers the reliability guarantees added in Slice 3 Step 1:
- per-handler isolation (a failing handler does not block or re-run the
  others, and only the failed handlers are retried)
- exponential retry backoff persisted as next_retry_at (a pass never blocks)
- claim locking: queued jobs flip to 'running' atomically; owned events are
  never re-adopted as orphans; stale 'running' jobs are reaped
- failed events are re-adopted as orphans so nothing is ever lost
- retry_failed caps the retry budget instead of growing without bound
"""

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models.intelligence import BackgroundJob
from app.models.notification import Event as EventRow


def _unique(prefix: str) -> str:
    return f"{prefix}.{uuid4().hex[:8]}"


async def _emit(db, name: str, payload: dict | None = None):
    from app.services.event_service import event_service

    event = await event_service.emit(db, name=name, actor_id=None, organization_id=None, payload=payload or {})
    await db.commit()
    return event


async def _job(db, event_id: str):
    return (await db.execute(select(BackgroundJob))).scalars().one()


# ================================================================ isolation

@pytest.mark.asyncio
async def test_failing_handler_does_not_block_others(db_session_factory):
    from app.events.event_bus import event_bus
    from app.events.subscriber import on

    name = _unique("s3.iso")
    calls: list[str] = []

    @on(name)
    async def h_fail(db, event, payload):
        calls.append("fail")
        raise ValueError("boom-a")

    @on(name)
    async def h_ok(db, event, payload):
        calls.append("ok")

    async with db_session_factory() as db:
        ev = await _emit(db, name)
        processed = await event_bus.process_pending(db, limit=10)
        assert processed == 0  # partial failure => event not fully processed
        assert calls == ["fail", "ok"]  # isolation: ok ran despite fail
        job = await _job(db, ev.id)
        assert job.status == "retry"
        assert job.next_retry_at is not None  # backoff persisted
        assert "boom-a" in job.error
        assert (await db.get(EventRow, ev.id)).processed_at is None


@pytest.mark.asyncio
async def test_retry_backoff_defers_pass_until_due(db_session_factory):
    from app.events.event_bus import event_bus
    from app.events.subscriber import on

    name = _unique("s3.bo")
    calls: list[str] = []

    @on(name)
    async def h_fail(db, event, payload):
        calls.append("fail")
        if calls.count("fail") == 1:
            raise ValueError("boom-b")  # fails only on the first attempt

    @on(name)
    async def h_ok(db, event, payload):
        calls.append("ok")

    async with db_session_factory() as db:
        ev = await _emit(db, name)
        await event_bus.process_pending(db, limit=10)
        assert calls == ["fail", "ok"]
        job = await _job(db, ev.id)
        assert job.status == "retry"

        # a pass before next_retry_at must NOT pick the job up again
        processed = await event_bus.process_pending(db, limit=10)
        assert processed == 0
        assert calls == ["fail", "ok"]

        # make the retry due, then the pass must run ONLY the failed handler
        job.next_retry_at = datetime.now(timezone.utc) - timedelta(seconds=5)
        await db.commit()
        processed = await event_bus.process_pending(db, limit=10)
        assert processed == 1
        assert calls == ["fail", "ok", "fail"]  # ok was not re-run
        assert (await db.get(EventRow, ev.id)).processed_at is not None


@pytest.mark.asyncio
async def test_event_never_lost_failed_job_re_adopted_as_orphan(db_session_factory):
    from app.events.event_bus import event_bus
    from app.events.subscriber import on

    name = _unique("s3.adopt")
    fail_count = 0

    @on(name)
    async def h_flaky(db, event, payload):
        nonlocal fail_count
        fail_count += 1
        if fail_count < 4:
            raise ValueError("flaky")

    async with db_session_factory() as db:
        ev = await _emit(db, name)

        # exhaust the retry budget: pass 1 (attempts 1), pass 2 (2), pass 3 (3)
        for _ in range(3):
            await event_bus.process_pending(db, limit=10)
            jobs = (await db.execute(select(BackgroundJob))).scalars().all()
            jobs[-1].next_retry_at = None  # clear backoff so retry is due now
            await db.commit()
        failed = (await db.execute(select(BackgroundJob))).scalars().all()
        assert all(j.status == "failed" for j in failed)

        # the event is still unprocessed and must be re-adopted as an orphan
        assert (await db.get(EventRow, ev.id)).processed_at is None
        processed = await event_bus.process_pending(db, limit=10)
        assert processed == 1
        assert (await db.get(EventRow, ev.id)).processed_at is not None
        # a fresh dispatch job ran the handler to completion
        jobs = (await db.execute(select(BackgroundJob))).scalars().all()
        assert any(j.status == "done" for j in jobs)


# ================================================================ claim locking

@pytest.mark.asyncio
async def test_owned_event_is_never_adopted_as_orphan(db_session_factory):
    from app.events.event_bus import event_bus
    from app.events.subscriber import on

    name = _unique("s3.own")
    calls: list[str] = []

    @on(name)
    async def h(db, event, payload):
        calls.append("run")

    async with db_session_factory() as db:
        ev = await _emit(db, name)
        # another worker already owns the event via a queued dispatch job
        db.add(BackgroundJob(name="event.dispatch", status="queued", event_id=ev.id,
                             payload_json=json.dumps({"event_id": ev.id})))
        await db.commit()

        processed = await event_bus.process_pending(db, limit=10)
        assert processed == 1
        assert calls == ["run"]
        jobs = (await db.execute(select(BackgroundJob))).scalars().all()
        assert len(jobs) == 1  # no second job was created for the event


@pytest.mark.asyncio
async def test_claim_is_atomic_queued_that_became_running_is_skipped(db_session_factory):
    from app.events.event_bus import event_bus
    from app.events.subscriber import on

    name = _unique("s3.cas")
    calls: list[str] = []

    @on(name)
    async def h(db, event, payload):
        calls.append("run")

    async with db_session_factory() as db:
        ev = await _emit(db, name)
        job = BackgroundJob(name="event.dispatch", status="running",
                            started_at=datetime.now(timezone.utc),
                            attempts=1, event_id=ev.id,
                            payload_json=json.dumps({"event_id": ev.id}))
        db.add(job)
        await db.commit()

        processed = await event_bus.process_pending(db, limit=10)
        assert processed == 0
        assert calls == []  # never dispatched (already owned as running)
        assert (await db.get(EventRow, ev.id)).processed_at is None


@pytest.mark.asyncio
async def test_stale_running_job_is_reaped_and_retried(db_session_factory):
    from app.events.event_bus import event_bus
    from app.events.subscriber import on

    name = _unique("s3.reap")
    calls: list[str] = []

    @on(name)
    async def h(db, event, payload):
        calls.append("run")

    async with db_session_factory() as db:
        ev = await _emit(db, name)
        db.add(BackgroundJob(name="event.dispatch", status="running",
                             started_at=datetime.now(timezone.utc) - timedelta(hours=2),
                             attempts=1, event_id=ev.id,
                             payload_json=json.dumps({"event_id": ev.id})))
        await db.commit()

        processed = await event_bus.process_pending(db, limit=10)
        assert processed == 1
        assert calls == ["run"]
        assert (await db.get(EventRow, ev.id)).processed_at is not None


# ================================================================ retry_failed

@pytest.mark.asyncio
async def test_retry_failed_resets_and_caps_budget(db_session_factory):
    from app.events.event_bus import event_bus
    from app.events.subscriber import on

    name = _unique("s3.cap")

    @on(name)
    async def h(db, event, payload):
        raise ValueError("always fails")

    async with db_session_factory() as db:
        ev = await _emit(db, name)
        db.add(BackgroundJob(name="event.dispatch", status="failed", attempts=30,
                             max_attempts=30, event_id=ev.id,
                             payload_json=json.dumps({"event_id": ev.id})))
        await db.commit()

        reset = await event_bus.retry_failed(db, limit=10)
        assert reset == 1
        job = await _job(db, ev.id)
        assert job.status == "retry"
        assert job.max_attempts == 10  # capped, never 32
        assert job.next_retry_at is None  # immediately retriable
        assert job.error is None
