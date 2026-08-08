"""Meeting worker — manages meeting lifecycle state.

Marks scheduled meetings that have started as `in_progress`, auto-completes
meetings past their end time, and generates AI summaries for meetings that
ended without one (the AI gateway is not required; a rule-based summary is
always available as a fallback).

Run standalone: python -m app.workers.meeting_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.meeting import Meeting
from app.work.meeting_service import meeting_service

logger = logging.getLogger("vcos.workers.meeting")


async def run_once() -> int:
    processed = 0
    async with SessionLocal() as db:
        now = utcnow()
        meetings = (
            await db.execute(
                select(Meeting).where(Meeting.status.in_(("scheduled", "in_progress")))
            )
        ).scalars().all()
        for meeting in meetings:
            try:
                if meeting.status == "scheduled" and meeting.start_at and meeting.start_at <= now:
                    if meeting.end_at and meeting.end_at <= now:
                        meeting.status = "completed"
                    else:
                        meeting.status = "in_progress"
                    meeting.updated_at = now
                    processed += 1
                elif meeting.status == "in_progress" and meeting.end_at and meeting.end_at <= now:
                    meeting.status = "completed"
                    meeting.updated_at = now
                    if meeting.ai_summary is None:
                        meeting.ai_summary = meeting_service._build_summary(meeting)
                    processed += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("meeting worker skipped %s: %s", meeting.id, exc)
        await db.commit()
        return processed


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("meeting worker updated %s meetings", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("meeting worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
