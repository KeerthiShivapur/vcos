from __future__ import annotations

"""Developer billing service (Phase 18.18) â€” plans, quotas & billing events.

Subscriptions give developers metered quotas; the billing worker aggregates
monthly usage and this service tracks plan changes and emits billing.recorded
events used by the finance module.
"""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.developer import DeveloperSubscription

PLANS = {
    "free": {"quota": 1000, "revenue_share": 0.0},
    "pro": {"quota": 100000, "revenue_share": 0.1},
    "enterprise": {"quota": 1000000, "revenue_share": 0.15},
}
PERIOD_DAYS = 30


class DeveloperBillingService:
    async def get(self, db: AsyncSession, developer_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(DeveloperSubscription).where(DeveloperSubscription.developer_id == developer_id)
            )
        ).scalars().first()
        if row is None:
            return None
        return self.serialize(row)

    async def ensure(self, db: AsyncSession, developer_id: str) -> dict[str, Any]:
        row = (
            await db.execute(
                select(DeveloperSubscription).where(DeveloperSubscription.developer_id == developer_id)
            )
        ).scalars().first()
        if row is None:
            row = DeveloperSubscription(developer_id=developer_id, plan="free", status="active")
            db.add(row)
            await db.flush()
        return self.serialize(row)

    async def change_plan(
        self,
        db: AsyncSession,
        developer_id: str,
        plan: str,
        organization_id: Optional[str] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if plan not in PLANS:
            raise ValueError(f"plan must be one of {list(PLANS)}")
        row = (
            await db.execute(
                select(DeveloperSubscription).where(DeveloperSubscription.developer_id == developer_id)
            )
        ).scalars().first()
        if row is None:
            row = DeveloperSubscription(developer_id=developer_id, plan="free", status="active")
            db.add(row)
            await db.flush()
        row.plan = plan
        row.monthly_quota = PLANS[plan]["quota"]
        row.revenue_share = PLANS[plan]["revenue_share"]
        from datetime import timedelta

        today = utcnow().date()
        row.current_period_start = today.isoformat()
        row.current_period_end = (today + timedelta(days=PERIOD_DAYS)).isoformat()
        await db.flush()
        await publish_background_event(
            db, name="subscription.changed", organization_id=organization_id or developer_id,
            payload={"plan": plan, "quota": row.monthly_quota},
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    def serialize(self, row: DeveloperSubscription) -> dict[str, Any]:
        return {
            "id": row.id,
            "developer_id": row.developer_id,
            "plan": row.plan,
            "revenue_share": row.revenue_share,
            "status": row.status,
            "monthly_quota": row.monthly_quota,
            "current_period_start": row.current_period_start,
            "current_period_end": row.current_period_end,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


developer_billing_service = DeveloperBillingService()
