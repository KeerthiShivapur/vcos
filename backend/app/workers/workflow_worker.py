"""Workflow execution worker (Phase 14) — resumes and times out executions.

Crash recovery: executions parked in `waiting` (delay elapsed, parallel join
ready, approval decided) are resumed here; executions stuck in `running` too
long are marked timed_out.

Run standalone: python -m app.workers.workflow_worker
"""

import asyncio
import logging

from app.automation.execution_service import execution_engine
from app.automation.approval_service import workflow_approval_service
from app.db.database import SessionLocal

logger = logging.getLogger("vcos.workers.workflow")


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            total = await _work(session)
            await session.commit()
        return total
    return await _work(db)


async def _work(session) -> int:
    total = 0
    try:
        resumed = await execution_engine.resume_stale(session, limit=100)
        total += resumed
        timed_out = await execution_engine.timeout_stuck(session, hours=72)
        total += timed_out
        escalated = await workflow_approval_service.escalate_due(session, hours=24, limit=50)
        total += escalated
        if total:
            logger.info("workflow worker: resumed=%s timed_out=%s escalated=%s",
                        resumed, timed_out, escalated)
    except Exception as exc:  # pragma: no cover - per-pass isolation
        logger.exception("workflow worker pass failed: %s", exc)
    return total


async def run_forever(interval_seconds: int = 60) -> None:
    while True:
        await run_once()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
