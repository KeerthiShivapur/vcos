"""Support worker (Phase 12) — SLA posture + escalation hygiene.

Flags tickets breaching their resolution SLA, re-checks statuses that may
have gone stale, and keeps the summary counters honest for leadership.

Run standalone: python -m app.workers.support_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.customers.support_service import SLA_RESOLUTION, support_service
from app.db.database import SessionLocal
from app.models.organization import Organization
from app.models.ticket import SupportTicket

logger = logging.getLogger("vcos.workers.support")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        org_ids = (
            await session.execute(select(Organization.id).where(Organization.status == "active"))
        ).scalars().all()
        for org_id in org_ids:
            try:
                tickets = (
                    await session.execute(
                        select(SupportTicket).where(
                            SupportTicket.organization_id == org_id,
                            SupportTicket.status.in_(("open", "in_progress", "waiting_customer")),
                        )
                    )
                ).scalars().all()
                now = utcnow()
                for ticket in tickets:
                    if ticket.created_at is None:
                        continue
                    created = ensure_aware(ticket.created_at)
                    minutes = (now - created).total_seconds() / 60
                    limit = ticket.sla_resolution_minutes or SLA_RESOLUTION.get(ticket.priority, 21600)
                    if minutes > limit and ticket.status != "escalated":
                        ticket.status = "escalated"
                        ticket.escalated_at = now
                        count += 1
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("support worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("support worker escalated %s stale ticket(s)", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("support worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
