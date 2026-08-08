"""Finance analytics worker (Phase 13) — materializes financial metrics.

For every active org, records monthly financial metrics (revenue, operating
costs, net cash flow) into FinancialMetric rows so charts and comparisons
work even when raw invoices change.

Run standalone: python -m app.workers.finance_analytics_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.finance.analytics_service import financial_analytics
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.finance_analytics")


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
                data = await financial_analytics.dashboard(session, organization_id=org_id)
                for name, value in (
                    ("revenue", data.get("revenue", 0)),
                    ("operating_costs", data.get("operating_costs", 0)),
                    ("net_cash_flow", data.get("net_cash_flow", 0)),
                    ("pending_approvals", data.get("pending_approvals", 0)),
                ):
                    await financial_analytics.record_metric(
                        session, organization_id=org_id, metric_type=name,
                        period=data.get("month", ""), value=float(value or 0),
                    )
                    count += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("finance analytics worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 43200) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("finance analytics worker recorded %s metrics", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("finance analytics worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
