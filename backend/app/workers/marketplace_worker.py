"""Marketplace worker (Phase 18) — keeps the ecosystem marketplace healthy.

Every pass:
  - refreshes downloads, ratings and review counts for published listings,
  - revokes expired developer API keys,
  - expires developer certification credentials.

Run standalone: python -m app.workers.marketplace_worker
"""

import asyncio
import logging
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.db.database import SessionLocal
from app.models.developer import CertificationCredential, DeveloperApiKey, ExtensionInstall
from app.models.enterprise import MarketplaceItem, MarketplaceReview

logger = logging.getLogger("vcos.workers.marketplace")


async def run_once(db: Optional[AsyncSession] = None) -> int:
    total = 0
    owns_session = db is None

    async def _work(session: AsyncSession) -> int:
        count = 0
        # refresh downloads + ratings + review counts for published listings
        listings = (
            await session.execute(select(MarketplaceItem).where(MarketplaceItem.published.is_(True)))
        ).scalars().all()
        for listing in listings:
            installed = (
                await session.execute(
                    select(func.count(ExtensionInstall.id))
                    .where(
                        ExtensionInstall.marketplace_item_id == listing.id,
                        ExtensionInstall.status == "installed",
                    )
                )
            ).scalars().one()
            listing.downloads = int(installed)
            reviews = (
                await session.execute(
                    select(MarketplaceReview).where(MarketplaceReview.item_id == listing.id)
                )
            ).scalars().all()
            if reviews:
                listing.rating = round(sum(r.rating for r in reviews) / len(reviews), 1)
                listing.review_count = len(reviews)
            count += 1
        # revoke expired API keys
        expired_keys = (
            await session.execute(
                select(DeveloperApiKey).where(
                    DeveloperApiKey.status == "active",
                    DeveloperApiKey.expires_at < utcnow(),
                )
            )
        ).scalars().all()
        for key in expired_keys:
            key.status = "revoked"
            count += 1
        # expire certifications
        expired_certs = (
            await session.execute(
                select(CertificationCredential).where(
                    CertificationCredential.status == "passed",
                    CertificationCredential.expires_at < utcnow(),
                )
            )
        ).scalars().all()
        for cert in expired_certs:
            cert.status = "expired"
            count += 1
        await session.flush()
        return count

    if owns_session:
        async with SessionLocal() as db:
            total = await _work(db)
            await db.commit()
    else:
        total = await _work(db)
    return total


async def run_forever(interval_seconds: int = 3600) -> None:
    while True:
        try:
            total = await run_once()
            if total:
                logger.info("marketplace worker refreshed %s items", total)
        except Exception as exc:  # pragma: no cover
            logger.exception("marketplace worker error: %s", exc)
        await asyncio.sleep(interval_seconds)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_forever())
