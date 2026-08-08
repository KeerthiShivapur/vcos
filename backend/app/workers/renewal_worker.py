"""Renewal worker (Phase 12) — expiry hygiene + renewal readiness.

Refreshes contract renewal_status from expiry dates, logs due/expired
contracts and creates notifications for owners so renewals are worked
before they lapse.

Run standalone: python -m app.workers.renewal_worker
"""

import asyncio
import logging
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.models.contract import Contract
from app.models.notification import Notification
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.renewal")


async def _derive(expires_at: Optional[date], auto_renew: bool) -> str:
    if expires_at is None or auto_renew:
        return "not_due"
    days_left = (expires_at - date.today()).days
    if days_left < 0:
        return "due"
    if days_left <= 30:
        return "due_soon"
    return "not_due"


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
                contracts = (
                    await session.execute(
                        select(Contract).where(
                            Contract.organization_id == org_id,
                            Contract.status.in_(("active", "signed")),
                        )
                    )
                ).scalars().all()
                for contract in contracts:
                    derived = await _derive(contract.expires_at, contract.auto_renew)
                    if derived != contract.renewal_status:
                        contract.renewal_status = derived
                        count += 1
                        if derived == "due_soon":
                            owner_user_id = None
                            session.add(
                                Notification(
                                    organization_id=org_id,
                                    recipient_id=owner_user_id,
                                    type="renewal",
                                    title=f"Renewal due soon: {contract.title[:80]}",
                                    body=f"'{contract.title}' expires {contract.expires_at}. Start the renewal conversation now.",
                                    priority="high",
                                    channel="in_app",
                                    entity_type="contract",
                                    entity_id=contract.id,
                                    delivered_at=None,
                                )
                            )
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("renewal worker skipped org %s: %s", org_id, exc)
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
                logger.info("renewal worker refreshed %s contract(s)", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("renewal worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
