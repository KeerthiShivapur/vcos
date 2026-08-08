"""Industry worker (Phase 17) — keeps industry packs healthy.

Every pass:
  - ensures the global industry catalog rows exist for installed packs,
  - refreshes compliance posture for each enabled pack,
  - reports workflows that have been stuck without progress.

The worker is purely housekeeping — pack installs, selections and activations
stay user-driven through the API.

Run standalone: python -m app.workers.industry_worker
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.industry.framework.compliance_engine import industry_compliance_engine
from app.industry.framework.plugin_loader import industry_plugin_loader
from app.industry.framework.workflow_engine import industry_workflow_engine
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.industry")

_STALE_AFTER_DAYS = 30


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
                configs = await industry_plugin_loader.list_installed(session, organization_id=org_id)
                for config in configs:
                    if config.status in ("uninstalled", "disabled"):
                        continue
                    # keep the catalog materialized for installed packs (idempotent)
                    await industry_plugin_loader._ensure_industry_catalog(session, config.industry_key)
                    # keep posture warm so dashboards never start empty
                    posture = await industry_compliance_engine.latest(
                        session, organization_id=org_id, industry_key=config.industry_key
                    )
                    # flag workflows stuck without progress
                    workflows = await industry_workflow_engine.list_workflows(
                        session, organization_id=org_id, industry_key=config.industry_key
                    )
                    stale = 0
                    cutoff = utcnow() - timedelta(days=_STALE_AFTER_DAYS)
                    for workflow in workflows:
                        if workflow.status != "active":
                            continue
                        if workflow.started_at is not None and workflow.started_at < cutoff:
                            if workflow.progress <= 0:
                                stale += 1
                    count += stale
                    await session.flush()
            except Exception as exc:  # pragma: no cover
                logger.warning("industry worker skipped org %s: %s", org_id, exc)
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
                logger.info("industry worker found %s stale industry workflows", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("industry worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
