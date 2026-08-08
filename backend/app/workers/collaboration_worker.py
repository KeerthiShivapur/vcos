"""Collaboration worker — meeting session lifecycle + live presence (Phase 6).

- sessions live while their meeting is in_progress
- sessions end when the meeting completes (duration recorded)
- participants idle > 10 minutes are marked away (attendance accuracy)

Run standalone: python -m app.workers.collaboration_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.collaboration.participant_service import participant_service
from app.collaboration.session_service import session_service
from app.core.timeutils import ensure_aware, utcnow
from app.db.database import SessionLocal
from app.models.collaboration import MeetingSession
from app.models.meeting import Meeting

logger = logging.getLogger("vcos.workers.collaboration")


async def run_once() -> int:
    processed = 0
    async with SessionLocal() as db:
        sessions = (
            await db.execute(
                select(MeetingSession).where(MeetingSession.status.in_(("scheduled", "live")))
            )
        ).scalars().all()
        for session in sessions:
            try:
                meeting = await db.get(Meeting, session.meeting_id)
                if meeting is None or meeting.organization_id != session.organization_id:
                    continue
                if meeting.status == "in_progress" and session.status == "scheduled":
                    session.status = "live"
                    session.started_at = session.started_at or utcnow()
                    processed += 1
                elif meeting.status == "completed" and session.status in ("scheduled", "live"):
                    now = utcnow()
                    session.status = "ended"
                    session.ended_at = session.ended_at or now
                    if session.started_at:
                        session.duration_seconds = int(
                            (now - ensure_aware(session.started_at)).total_seconds()
                        )
                    processed += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("collaboration worker skipped session %s: %s", session.id, exc)
        expired = await participant_service.expire_idle(db, organization_id=None, idle_minutes=10)
        await db.commit()
        return processed + expired


async def run_forever(interval_seconds: int = 300) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("collaboration worker processed %s items", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("collaboration worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
