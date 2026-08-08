from __future__ import annotations

"""Extension marketplace service (Phase 18.6) â€” listings, installs & reviews.

Builds on the Phase 15 MarketplaceItem / MarketplaceReview tables. Developers
publish listings backed by their applications; organizations browse, install
(also as AI agents), uninstall and review extensions.
"""

import secrets
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.developer import AIAgent, DeveloperApplication, ExtensionInstall
from app.models.enterprise import MarketplaceItem, MarketplaceReview

CATEGORIES = (
    "analytics", "automation", "collaboration", "design", "developer-tools",
    "finance", "productivity", "security", "general",
)


class ExtensionMarketplaceService:
    # ------------------------------------------------------------- listings

    async def publish_listing(
        self,
        db: AsyncSession,
        *,
        developer_id: str,
        application_id: str,
        name: str,
        description: Optional[str] = None,
        category: str = "general",
        price: float = 0.0,
        commit: bool = False,
    ) -> Optional[dict[str, Any]]:
        app = (
            await db.execute(
                select(DeveloperApplication).where(
                    DeveloperApplication.developer_id == developer_id,
                    DeveloperApplication.id == application_id,
                )
            )
        ).scalars().first()
        if app is None:
            return None
        if category not in CATEGORIES:
            raise ValueError(f"category must be one of {CATEGORIES}")
        existing = (
            await db.execute(
                select(MarketplaceItem).where(MarketplaceItem.plugin_key == app.application_key)
            )
        ).scalars().first()
        if existing is not None:
            return self.serialize_item(existing)
        row = MarketplaceItem(
            plugin_key=app.application_key,
            name=name,
            description=description,
            category=category,
            price=price,
            version=app.version,
            verified=app.verified,
            manifest={
                "developer_id": developer_id,
                "application_id": application_id,
                "app_type": app.app_type,
            },
            published=True,
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="marketplace.published", organization_id=developer_id,
            payload={"item_id": row.id, "plugin_key": row.plugin_key},
        )
        if commit:
            await db.commit()
        return self.serialize_item(row)

    async def list_listings(
        self,
        db: AsyncSession,
        category: Optional[str] = None,
        published: bool = True,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        stmt = select(MarketplaceItem)
        if category:
            stmt = stmt.where(MarketplaceItem.category == category)
        if published is not None:
            stmt = stmt.where(MarketplaceItem.published == published)
        rows = (
            await db.execute(stmt.order_by(MarketplaceItem.downloads.desc()).limit(limit))
        ).scalars().all()
        return [self.serialize_item(r) for r in rows]

    async def get_listing(self, db: AsyncSession, item_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(select(MarketplaceItem).where(MarketplaceItem.id == item_id))
        ).scalars().first()
        return self.serialize_item(row) if row else None

    async def set_verified(
        self, db: AsyncSession, item_id: str, verified: bool = True
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(select(MarketplaceItem).where(MarketplaceItem.id == item_id))
        ).scalars().first()
        if row is None:
            return None
        row.verified = verified
        await db.flush()
        return self.serialize_item(row)

    # --------------------------------------------------------------- installs

    async def install(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        item_id: str,
        installed_by: Optional[str] = None,
        as_agent: bool = False,
        commit: bool = False,
    ) -> dict[str, Any]:
        item = (
            await db.execute(select(MarketplaceItem).where(MarketplaceItem.id == item_id))
        ).scalars().first()
        if item is None:
            raise ValueError("listing not found")
        existing = (
            await db.execute(
                select(ExtensionInstall).where(
                    ExtensionInstall.marketplace_item_id == item_id,
                    ExtensionInstall.organization_id == organization_id,
                )
            )
        ).scalars().first()
        if existing is not None:
            existing.status = "installed"
            existing.installed_at = utcnow()
            await db.flush()
            install = existing
        else:
            install = ExtensionInstall(
                marketplace_item_id=item_id,
                organization_id=organization_id,
                status="installed",
                installed_by=installed_by,
                installed_at=utcnow(),
            )
            db.add(install)
            await db.flush()
        item.downloads += 1
        await db.flush()
        if as_agent:
            existing_agent = (
                await db.execute(
                    select(AIAgent).where(AIAgent.organization_id == organization_id, AIAgent.agent_key == item.plugin_key)
                )
            ).scalars().first()
            if existing_agent is None:
                db.add(
                    AIAgent(
                        organization_id=organization_id,
                        agent_key=item.plugin_key,
                        name=item.name,
                        description=item.description,
                        role="assistant",
                        capabilities=[item.category],
                        status="installed",
                        installed_at=utcnow(),
                        verified=item.verified,
                    )
                )
                await db.flush()
        await publish_background_event(
            db, name="marketplace.installed", organization_id=organization_id,
            payload={"item_id": item_id, "plugin_key": item.plugin_key},
        )
        if commit:
            await db.commit()
        return self.serialize_install(install)

    async def uninstall(
        self, db: AsyncSession, organization_id: str, item_id: str
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(ExtensionInstall).where(
                    ExtensionInstall.marketplace_item_id == item_id,
                    ExtensionInstall.organization_id == organization_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.status = "uninstalled"
        await db.flush()
        return self.serialize_install(row)

    async def installed(
        self, db: AsyncSession, organization_id: str
    ) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ExtensionInstall)
                .where(
                    ExtensionInstall.organization_id == organization_id,
                    ExtensionInstall.status.in_(("installed", "disabled")),
                )
                .order_by(ExtensionInstall.installed_at.desc())
            )
        ).scalars().all()
        return [self.serialize_install(r) for r in rows]

    # --------------------------------------------------------------- reviews

    async def review(
        self,
        db: AsyncSession,
        *,
        item_id: str,
        user_id: str,
        rating: int,
        comment: Optional[str] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if rating < 1 or rating > 5:
            raise ValueError("rating must be between 1 and 5")
        item = (
            await db.execute(select(MarketplaceItem).where(MarketplaceItem.id == item_id))
        ).scalars().first()
        if item is None:
            raise ValueError("listing not found")
        existing = (
            await db.execute(
                select(MarketplaceReview).where(
                    MarketplaceReview.item_id == item_id,
                    MarketplaceReview.user_id == user_id,
                )
            )
        ).scalars().first()
        if existing is not None:
            existing.rating = rating
            existing.comment = comment
            row = existing
        else:
            row = MarketplaceReview(item_id=item_id, user_id=user_id, rating=rating, comment=comment)
            db.add(row)
            await db.flush()
        rows = (
            await db.execute(select(MarketplaceReview).where(MarketplaceReview.item_id == item_id))
        ).scalars().all()
        if rows:
            item.rating = round(sum(r.rating for r in rows) / len(rows), 2)
            item.review_count = len(rows)
        await db.flush()
        if commit:
            await db.commit()
        return self.serialize_review(row)

    async def reviews(self, db: AsyncSession, item_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(MarketplaceReview)
                .where(MarketplaceReview.item_id == item_id)
                .order_by(MarketplaceReview.created_at.desc())
            )
        ).scalars().all()
        return [self.serialize_review(r) for r in rows]

    # ------------------------------------------------------------ serializers

    def serialize_item(self, row: MarketplaceItem) -> dict[str, Any]:
        return {
            "id": row.id,
            "plugin_key": row.plugin_key,
            "name": row.name,
            "description": row.description,
            "category": row.category,
            "price": row.price,
            "rating": row.rating,
            "review_count": row.review_count,
            "downloads": row.downloads,
            "version": row.version,
            "verified": row.verified,
            "scanned": row.scanned,
            "published": row.published,
            "manifest": row.manifest or {},
        }

    def serialize_install(self, row: ExtensionInstall) -> dict[str, Any]:
        return {
            "id": row.id,
            "marketplace_item_id": row.marketplace_item_id,
            "organization_id": row.organization_id,
            "status": row.status,
            "settings": row.settings or {},
            "installed_by": row.installed_by,
            "installed_at": row.installed_at.isoformat() if row.installed_at else None,
        }

    def serialize_review(self, row: MarketplaceReview) -> dict[str, Any]:
        return {
            "id": row.id,
            "item_id": row.item_id,
            "user_id": row.user_id,
            "rating": row.rating,
            "comment": row.comment,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


extension_marketplace_service = ExtensionMarketplaceService()
