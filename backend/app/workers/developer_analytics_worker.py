"""Developer analytics worker (Phase 18) — materializes developer ecosystem metrics.

Every pass, for every active developer:
  - aggregates usage (requests, errors, latency) per application and per key
    into the analytics window table, then emits `analytics.generated`,
  - materializes install counts and certification counts for the developer.

Run standalone: python -m app.workers.developer_analytics_worker
"""

import asyncio
import json
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.events.publisher import publish_background_event
from app.models.developer import (
    CertificationCredential,
    Developer,
    DeveloperApiKey,
    DeveloperApplication,
    DeveloperUsage,
)
from app.models.enterprise import MarketplaceItem

logger = logging.getLogger("vcos.workers.developer_analytics")

_RETENTION_DAYS = 90


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        developers = (await session.execute(select(Developer))).scalars().all()
        cutoff = utcnow() - timedelta(days=_RETENTION_DAYS)
        for developer in developers:
            try:
                apps = (
                    await session.execute(
                        select(DeveloperApplication).where(DeveloperApplication.developer_id == developer.id)
                    )
                ).scalars().all()
                app_ids = [a.id for a in apps]
                usage_rows = []
                if app_ids:
                    usage_rows = (
                        await session.execute(
                            select(DeveloperUsage).where(DeveloperUsage.application_id.in_(app_ids))
                        )
                    ).scalars().all()
                requests = sum(u.value for u in usage_rows if u.unit == "requests")
                errors = sum(u.value for u in usage_rows if u.unit == "errors")
                latency_rows = [u.value for u in usage_rows if u.unit == "latency_ms"]
                latency = sum(latency_rows)
                installs = 0
                for app in apps:
                    if app.app_type in ("plugin", "app"):
                        listing = (
                            await session.execute(
                                select(MarketplaceItem).where(MarketplaceItem.plugin_key == app.application_key)
                            )
                        ).scalars().first()
                        if listing is not None:
                            installs += listing.downloads
                certs = (
                    await session.execute(
                        select(CertificationCredential).where(
                            CertificationCredential.developer_id == developer.id,
                            CertificationCredential.status == "passed",
                        )
                    )
                ).scalars().all()
                payload = {
                    "developer_id": developer.id,
                    "applications": len(apps),
                    "requests": requests,
                    "errors": errors,
                    "avg_latency_ms": round(latency / len(latency_rows), 1) if latency_rows else 0.0,
                    "installs": installs,
                    "certifications": len(certs),
                    "period": utcnow().date().isoformat(),
                }
                await publish_background_event(
                    session,
                    name="analytics.generated",
                    organization_id=developer.user_id or "system",
                    payload=payload,
                )
                count += 1
            except Exception as exc:  # pragma: no cover
                logger.warning("developer analytics skipped developer %s: %s", developer.id, exc)
        # prune usage beyond retention
        pruned = (
            await session.execute(
                select(func.count(DeveloperUsage.id)).where(DeveloperUsage.created_at < cutoff)
            )
        ).scalars().one()
        if pruned:
            stale = (
                await session.execute(
                    select(DeveloperUsage.id).where(DeveloperUsage.created_at < cutoff).limit(500)
                )
            ).scalars().all()
            for usage_id in stale:
                row = await session.get(DeveloperUsage, usage_id)
                if row is not None:
                    await session.delete(row)
            count += len(stale)
        await session.flush()
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
                logger.info("developer analytics worker processed %s items", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("developer analytics worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
