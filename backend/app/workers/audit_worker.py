"""Audit retention worker.

Applies the organization retention policy (retention_days_audit) by pruning
old audit entries. Run standalone or via the platform worker supervisor.

Run standalone: python -m app.workers.audit_worker
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import SessionLocal
from app.models.organization import OrganizationSettings
from app.models.notification import AuditLog

logger = logging.getLogger("vcos.workers.audit")


async def run_once() -> int:
    async with SessionLocal() as db:
        settings_rows = (await db.execute(select(OrganizationSettings))).scalars().all()
        total = 0
        for row in settings_rows:
            cutoff = datetime.now(timezone.utc) - timedelta(days=row.retention_days_audit)
            result = await db.execute(
                delete(AuditLog).where(
                    AuditLog.organization_id == row.organization_id,
                    AuditLog.created_at < cutoff,
                )
            )
            total += result.rowcount or 0
        await db.commit()
        return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            pruned = await run_once()
            if pruned:
                logger.info("audit worker pruned %s rows", pruned)
        except Exception as exc:  # pragma: no cover
            logger.exception("audit worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
