from __future__ import annotations

"""Theme service (Phase 18.9) â€” organization branding themes.

Themes carry brand config (logo, fonts, colors, layout, icons, navigation,
widgets) and one active theme per organization; marketplace themes are
created via installs.
"""

from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.publisher import publish_background_event
from app.models.developer import Theme


class ThemeService:
    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        name: str,
        config: Optional[dict[str, Any]] = None,
        source: str = "custom",
        activate: bool = False,
        commit: bool = False,
    ) -> dict[str, Any]:
        row = Theme(
            organization_id=organization_id,
            name=name,
            config=config or {},
            source=source,
            active=False,
        )
        db.add(row)
        await db.flush()
        if activate:
            await self._activate(db, row, organization_id)
        await publish_background_event(
            db, name="theme.created", organization_id=organization_id,
            payload={"theme_id": row.id, "name": name},
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    async def list(self, db: AsyncSession, organization_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(Theme)
                .where(Theme.organization_id == organization_id)
                .order_by(Theme.created_at.desc())
            )
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    async def get(self, db: AsyncSession, organization_id: str, theme_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(Theme).where(
                    Theme.organization_id == organization_id,
                    Theme.id == theme_id,
                )
            )
        ).scalars().first()
        return self.serialize(row) if row else None

    async def update(
        self,
        db: AsyncSession,
        organization_id: str,
        theme_id: str,
        config: Optional[dict[str, Any]] = None,
        name: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(Theme).where(
                    Theme.organization_id == organization_id,
                    Theme.id == theme_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        if name is not None:
            row.name = name
        if config is not None:
            row.config = config
        await db.flush()
        return self.serialize(row)

    async def activate(self, db: AsyncSession, organization_id: str, theme_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(Theme).where(
                    Theme.organization_id == organization_id,
                    Theme.id == theme_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        await self._activate(db, row, organization_id)
        return self.serialize(row)

    async def delete(self, db: AsyncSession, organization_id: str, theme_id: str) -> bool:
        row = (
            await db.execute(
                select(Theme).where(
                    Theme.organization_id == organization_id,
                    Theme.id == theme_id,
                )
            )
        ).scalars().first()
        if row is None:
            return False
        await db.delete(row)
        await db.flush()
        return True

    async def _activate(self, db: AsyncSession, row: Theme, organization_id: str) -> None:
        others = (
            await db.execute(
                select(Theme).where(Theme.organization_id == organization_id, Theme.active.is_(True))
            )
        ).scalars().all()
        for other in others:
            other.active = False
        row.active = True
        await db.flush()
        await publish_background_event(
            db, name="theme.activated", organization_id=organization_id,
            payload={"theme_id": row.id},
        )

    def serialize(self, row: Theme) -> dict[str, Any]:
        return {
            "id": row.id,
            "organization_id": row.organization_id,
            "name": row.name,
            "config": row.config or {},
            "active": row.active,
            "source": row.source,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


theme_service = ThemeService()
