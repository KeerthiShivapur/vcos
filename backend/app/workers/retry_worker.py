"""Retry worker (Phase 14) — retries failed workflow steps with attempts left.

Steps configured with max_retries are reset to pending and their executions
put back on the resume path; due workflow approvals are auto-escalated here too.

Run standalone: python -m app.workers.retry_worker
"""

import asyncio
import logging

from app.automation.execution_service import execution_engine
from app.automation.approval_service import workflow_approval_service
from app.db.database import SessionLocal

logger = logging.getLogger("vcos.workers.retry")


async def run_once(db=None) -> int:
    owns_session = db is None
    if owns_session:
        async with SessionLocal() as session:
            total = await _work(session)
            await session.commit()
        return total
    total = await _work(db)
    await db.commit()
    return total


async def _work(session) -> int:
    total = 0
    try:
        reset = await execution_engine.retry_failed_steps(session, limit=100, min_age_minutes=10)
        total += reset
        escalated = await workflow_approval_service.escalate_due(session, hours=48, limit=50)
        total += escalated
        if total:
            logger.info("retry worker: reset=%s escalated=%s", reset, escalated)
    except Exception as exc:  # pragma: no cover
        logger.exception("retry worker pass failed: %s", exc)
    return total


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        await run_once()
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
