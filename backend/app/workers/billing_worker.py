"""Developer billing worker (Phase 18) — records monetization usage billing.

Every pass, for every active developer subscription:
  - aggregates DeveloperUsage rows over the last 30 days,
  - computes overage above the monthly quota,
  - emits `billing.recorded` with the usage totals and estimated overage.

Run standalone: python -m app.workers.billing_worker
"""

import asyncio
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.events.publisher import publish_background_event
from app.models.developer import DeveloperSubscription, DeveloperUsage

logger = logging.getLogger("vcos.workers.billing")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        subscriptions = (
            await session.execute(
                select(DeveloperSubscription).where(DeveloperSubscription.status == "active")
            )
        ).scalars().all()
        cutoff = utcnow() - timedelta(days=30)
        for sub in subscriptions:
            try:
                total_requests = (
                    await session.execute(
                        select(func.sum(DeveloperUsage.value))
                        .where(
                            DeveloperUsage.developer_id == sub.developer_id,
                            DeveloperUsage.unit == "requests",
                            DeveloperUsage.created_at >= cutoff,
                        )
                    )
                ).scalars().one() or 0
                quota = sub.monthly_quota or 0
                overage = max(0, total_requests - quota)
                payload = {
                    "subscription_id": sub.id,
                    "developer_id": sub.developer_id,
                    "plan": sub.plan,
                    "revenue_share": sub.revenue_share,
                    "total_requests": total_requests,
                    "monthly_quota": quota,
                    "overage": overage,
                    "period": sub.current_period_end or utcnow().isoformat(),
                }
                await publish_background_event(
                    session,
                    name="billing.recorded",
                    organization_id="system",
                    payload=payload,
                )
                count += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("billing worker skipped subscription %s: %s", sub.id, exc)
        await session.flush()
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
                logger.info("billing worker recorded %s billing rows", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("billing worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
