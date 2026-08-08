"""Meeting intelligence worker (Phase 6.10) — finalize ended meetings that
missed inline AI processing (summary, action items -> tasks, decisions,
attendance snapshot). Idempotent: ai_meeting_service.finalize skips meetings
that already have an analytics snapshot.
"""

import logging

from sqlalchemy import select

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.collaboration import MeetingAnalytics, MeetingSession
from app.models.meeting import Meeting

logger = logging.getLogger("vcos.workers.meeting_intel")


async def run_once() -> int:
    from app.collaboration.ai_meeting_service import ai_meeting_service
    from app.work.meeting_service import meeting_service

    processed = 0
    async with SessionLocal() as db:
        try:
            sessions = (
                await db.execute(
                    select(MeetingSession).where(
                        MeetingSession.status == "ended",
                        MeetingSession.ended_at.isnot(None),
                    ).order_by(MeetingSession.ended_at.desc()).limit(25)
                )
            ).scalars().all()
            for session in sessions:
                done = (
                    await db.execute(
                        select(MeetingAnalytics.id).where(
                            MeetingAnalytics.organization_id == session.organization_id,
                            MeetingAnalytics.meeting_id == session.meeting_id,
                        )
                    )
                ).scalar_one_or_none()
                if done:
                    continue
                meeting = await meeting_service.get(
                    db, organization_id=session.organization_id, meeting_id=session.meeting_id
                )
                if meeting is None or meeting.status == "cancelled":
                    continue
                await ai_meeting_service.finalize(
                    db,
                    organization_id=session.organization_id,
                    meeting=meeting,
                    session=session,
                )
                await db.commit()
                processed += 1
                logger.info("meeting_intel finalized meeting %s", meeting.id)
        except Exception:  # pragma: no cover - worker isolation
            logger.warning("meeting_intel pass failed", exc_info=True)
            await db.rollback()
    return processed
