"""Finance reconciliation worker (Phase 13) — overdue invoices + risk metrics.

For every active org, marks overdue invoices, scans for financial risks
(duplicate payments, budget overruns, late invoices, vendor risk) and
records risk metrics so the finance dashboard reflects current posture.

Run standalone: python -m app.workers.reconciliation_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.finance.invoice_service import invoice_service
from app.finance.risk_service import risk_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.reconciliation")


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
                overdue = await invoice_service.mark_overdue(session, organization_id=org_id)
                result = await risk_service.scan(session, organization_id=org_id)
                count += overdue + result["total"]
            except Exception as exc:  # pragma: no cover
                logger.warning("reconciliation worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 21600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("reconciliation worker processed %s items", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("reconciliation worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
