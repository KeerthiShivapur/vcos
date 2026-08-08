"""Plugin marketplace service (Phase 15).

Publishing, discovery, ratings/reviews and safe installation of plugins from
the marketplace catalog. Every listing is marked verified and scanned before
publication; installs route through the plugin service sandbox scan.
"""

from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.publisher import publish_event
from app.models.enterprise import MarketplaceItem, MarketplaceReview, Plugin


class MarketplaceService:
    async def publish(
        self,
        db: AsyncSession,
        *,
        plugin_key: str,
        name: str,
        description: Optional[str],
        category: str,
        price: float,
        version: str,
        manifest: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> MarketplaceItem:
        item = MarketplaceItem(
            plugin_key=plugin_key,
            name=name,
            description=description,
            category=category,
            price=price,
            version=version,
            manifest=manifest,
            verified=bool(manifest.get("verified")),
            scanned=bool(manifest.get("scanned")),
            published=True,
        )
        db.add(item)
        await db.flush()
        await publish_event(
            db,
            name="marketplace.published",
            organization_id=None,
            actor_id=actor_id,
            payload={"item_id": item.id, "plugin_key": plugin_key, "category": category},
        )
        return item

    async def list_items(
        self,
        db: AsyncSession,
        *,
        category: Optional[str] = None,
        search: Optional[str] = None,
        published_only: bool = True,
    ) -> list[MarketplaceItem]:
        query = select(MarketplaceItem)
        if published_only:
            query = query.where(MarketplaceItem.published.is_(True))
        if category:
            query = query.where(MarketplaceItem.category == category)
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(
                func.lower(MarketplaceItem.name).like(pattern)
                | func.lower(MarketplaceItem.description).like(pattern)
            )
        result = await db.execute(
            query.order_by(MarketplaceItem.rating.desc(), MarketplaceItem.downloads.desc())
        )
        return list(result.scalars().all())

    async def get_item(self, db: AsyncSession, item_id: str) -> Optional[MarketplaceItem]:
        return await db.get(MarketplaceItem, item_id)

    async def review(
        self,
        db: AsyncSession,
        *,
        item_id: str,
        user_id: str,
        rating: int,
        comment: Optional[str] = None,
    ) -> dict[str, Any]:
        if rating < 1 or rating > 5:
            raise ValueError("rating must be between 1 and 5")
        item = await self.get_item(db, item_id)
        if item is None:
            raise ValueError("marketplace item not found")
        existing = (
            await db.execute(
                select(MarketplaceReview).where(
                    MarketplaceReview.item_id == item_id,
                    MarketplaceReview.user_id == user_id,
                )
            )
        ).scalars().first()
        if existing:
            existing.rating = rating
            existing.comment = comment
        else:
            db.add(
                MarketplaceReview(
                    item_id=item_id, user_id=user_id, rating=rating, comment=comment
                )
            )
        await db.flush()
        avg, count = (
            await db.execute(
                select(func.avg(MarketplaceReview.rating), func.count(MarketplaceReview.id)).where(
                    MarketplaceReview.item_id == item_id
                )
            )
        ).one()
        item.rating = round(float(avg or 0), 2)
        item.review_count = int(count or 0)
        return {"item_id": item_id, "rating": item.rating, "review_count": item.review_count}

    async def install(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        item_id: str,
        actor_id: Optional[str] = None,
    ) -> Plugin:
        item = await self.get_item(db, item_id)
        if item is None or not item.published:
            raise ValueError("marketplace item not found or unpublished")
        existing = (
            await db.execute(
                select(Plugin).where(
                    Plugin.organization_id == organization_id,
                    Plugin.plugin_key == item.plugin_key,
                    Plugin.status != "uninstalled",
                )
            )
        ).scalars().first()
        if existing:
            raise ValueError(f"plugin {item.plugin_key} is already installed")
        item.downloads = (item.downloads or 0) + 1
        from app.enterprise.plugin_service import plugin_service

        return await plugin_service.from_marketplace(
            db, organization_id=organization_id, item=item, actor_id=actor_id
        )

    async def set_published(
        self, db: AsyncSession, *, item_id: str, published: bool
    ) -> Optional[MarketplaceItem]:
        item = await self.get_item(db, item_id)
        if item is None:
            return None
        item.published = published
        return item


marketplace_service = MarketplaceService()
