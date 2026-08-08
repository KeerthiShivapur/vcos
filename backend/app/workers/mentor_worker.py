"""Mentor worker (Phase 10) — mentorship program health.

Every pass flags active mentorships that have stalled (no sessions recorded
for 14+ days) so managers and the program can nudge them back on track.

Run standalone: python -m app.workers.mentor_worker
"""

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.events.event_bus import EventBus
from app.models.mentorship import Mentorship, MentorshipSession
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.mentor")

_event_bus = EventBus()


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    cutoff = utcnow() - timedelta(days=14)

    async def _work(session: AsyncSession) -> int:
        count = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            active = (
                await session.execute(
                    select(Mentorship).where(
                        Mentorship.organization_id == org_id,
                        Mentorship.status == "active",
                        Mentorship.progress < 100.0,
                    )
                )
            ).scalars().all()
            for mentorship in active:
                latest = (
                    await session.execute(
                        select(MentorshipSession.occurred_at)
                        .where(
                            MentorshipSession.organization_id == org_id,
                            MentorshipSession.mentorship_id == mentorship.id,
                        )
                        .order_by(MentorshipSession.occurred_at.desc())
                        .limit(1)
                    )
                ).scalar_one_or_none()
                if latest is not None and latest < cutoff:
                    await _event_bus.publish(
                        session,
                        name="mentorship.stalled",
                        organization_id=org_id,
                        actor_id=mentorship.mentee_id,
                        payload={
                            "mentorship_id": mentorship.id,
                            "mentor_id": mentorship.mentor_id,
                            "mentee_id": mentorship.mentee_id,
                            "topic": mentorship.topic,
                            "last_session_at": latest.isoformat(),
                        },
                        flush=False,
                    )
                    count += 1
            await session.flush()
        return count

    if db is None:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("mentor worker flagged %s stalled mentorships", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("mentor worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
