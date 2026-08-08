"""Wellbeing worker (Phase 11) — pattern-based wellbeing signals.

Recomputes risk levels for recent check-ins (in case thresholds changed)
and counts high-risk employees per org for HR follow-up. Explicitly
pattern-based only — no health claims.

Run standalone: python -m app.workers.wellbeing_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.hr.wellbeing_service import _compute_risk
from app.models.hr import WellbeingCheck
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.wellbeing")


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
                checks = (
                    await session.execute(
                        select(WellbeingCheck).where(WellbeingCheck.organization_id == org_id)
                    )
                ).scalars().all()
                for check in checks:
                    risk, signals = _compute_risk(check.metrics or {})
                    if risk != check.risk_level or signals != check.signals:
                        check.risk_level = risk
                        check.signals = signals
                        count += 1
                high_risk = [check for check in checks if check.risk_level == "high"]
                await session.flush()
                if high_risk:
                    logger.info("org %s has %s high-risk wellbeing check(s)", org_id, len(high_risk))
            except Exception as exc:  # pragma: no cover
                logger.warning("wellbeing worker skipped org %s: %s", org_id, exc)
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
                logger.info("wellbeing worker recomputed %s checks", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("wellbeing worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
