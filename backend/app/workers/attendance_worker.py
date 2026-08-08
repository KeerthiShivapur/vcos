"""Attendance worker (Phase 11) — anomaly detection for attendance records.

Every pass flags records from previous days that are still open (forgot to
clock out) and returns the number of anomalies found so HR can review.

Run standalone: python -m app.workers.attendance_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.hr.attendance_service import attendance_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.attendance")


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
                anomalies = await attendance_service.detect_anomalies(session, organization_id=org_id)
                for anomaly in anomalies:
                    logger.info("attendance anomaly in org %s: %s", org_id, anomaly)
                count += len(anomalies)
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("attendance worker skipped org %s: %s", org_id, exc)
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
                logger.info("attendance worker flagged %s anomalies", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("attendance worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
