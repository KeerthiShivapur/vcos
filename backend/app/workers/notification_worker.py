"""Notification worker.

Phase 1: notifications are written synchronously (in-app channel). This worker
marks deliveries, and later phases extend it with email/push fan-out, realtime
WebSocket delivery and digest aggregation.

Phase 9.14: the worker is also the heartbeat of the autonomous notification
engine — each pass surfaces high/critical risks to executives, workload flags
to managers, and repeated delay patterns, with a 24h dedup window.

Run standalone: python -m app.workers.notification_worker
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.notification import Notification

logger = logging.getLogger("vcos.workers.notification")


async def run_once() -> int:
    """Mark old notifications as delivered/readable, archive expired ones.

    Also runs the autonomous notification engine so the org's intelligence
    findings reach the people who can act on them.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=90)
    async with SessionLocal() as db:
        pending = (
            await db.execute(select(Notification).where(Notification.delivered_at.is_(None)))
        ).scalars().all()
        for n in pending:
            n.delivered_at = datetime.now(timezone.utc)
        expired = (
            await db.execute(
                select(Notification).where(
                    Notification.created_at < cutoff,
                    Notification.is_read.is_(True),
                    Notification.is_archived.is_(False),
                )
            )
        ).scalars().all()
        for n in expired:
            n.is_archived = True
        generated = 0
        org_ids = (
            await db.execute(select(Notification.organization_id).distinct())
        ).scalars().all()
        from app.intelligence.notification_engine import notification_engine

        for org_id in org_ids:
            try:
                generated += await notification_engine.generate(
                    db, organization_id=org_id
                )
            except Exception as exc:  # pragma: no cover - per-org isolation
                logger.warning("notification engine skipped org %s: %s", org_id, exc)
        await db.commit()
        return len(pending) + len(expired) + generated


async def run_forever(interval_seconds: int = 60) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("notification worker processed %s rows", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("notification worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
