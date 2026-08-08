"""Executive reporting worker — automatic report generation.

Generates the weekly and monthly executive reports for every organization.

Run standalone: python -m app.workers.exec_reporting_worker
"""

import asyncio
import logging

from sqlalchemy import select

from app.db.database import SessionLocal
from app.executive.reporting import reporting_service
from app.models.organization import Organization

logger = logging.getLogger("vcos.workers.exec_reporting")


async def run_once() -> int:
    total = 0
    async with SessionLocal() as db:
        orgs = (await db.execute(select(Organization.id))).scalars().all()
        for organization_id in orgs:
            for report_type in ("weekly", "monthly"):
                try:
                    await reporting_service.generate(
                        db, organization_id=organization_id, report_type=report_type, persist=True
                    )
                    await db.commit()
                    total += 1
                except Exception as exc:  # pragma: no cover - per-org isolation
                    logger.warning("exec reporting worker failed for %s/%s: %s", organization_id, report_type, exc)
                    await db.rollback()
    return total


async def run_forever(interval_seconds: int = 86400) -> None:
    while True:
        try:
            processed = await run_once()
            if processed:
                logger.info("exec reporting worker generated %s reports", processed)
        except Exception as exc:  # pragma: no cover
            logger.exception("exec reporting worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
