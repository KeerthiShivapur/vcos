"""Compliance worker (Phase 11) — keeps compliance posture fresh.

Every pass refreshes the valid / expiring / expired status of compliance
records and training completions, then reports how many items need action
(expired, expiring within 30 days, missing trainings).

Run standalone: python -m app.workers.compliance_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.hr.compliance_service import compliance_service
from app.industry.framework.compliance_engine import industry_compliance_engine
from app.industry.framework.plugin_loader import industry_plugin_loader
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.compliance")


async def _industry_posture(session: AsyncSession, org_id: str) -> int:
    """Phase 17 — surface industry compliance action items for installed packs."""
    count = 0
    configs = await industry_plugin_loader.list_installed(session, organization_id=org_id)
    for config in configs:
        if config.status in ("uninstalled", "disabled"):
            continue
        posture = await industry_compliance_engine.latest(
            session, organization_id=org_id, industry_key=config.industry_key
        )
        count += posture.get("failed", 0) + posture.get("pending", 0)
    return count


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
                overview = await compliance_service.overview(session, organization_id=org_id)
                action_items = (
                    overview["documents"]["expired"]
                    + overview["documents"]["expiring_30"]
                    + overview["documents"]["expiring_60"]
                    + overview["trainings"]["missing"]
                    + overview["trainings"]["expired_completions"]
                )
                count += action_items
                count += await _industry_posture(session, org_id)
                await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("compliance worker skipped org %s: %s", org_id, exc)
        return count

    if owns_session:
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
                logger.info("compliance worker found %s action items", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("compliance worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
