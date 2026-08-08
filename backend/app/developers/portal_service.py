from __future__ import annotations

"""Developer portal service (Phase 18.1) â€” developer registration & profile.

A developer is a global identity linked to a VCOS user account. The profile
holds public metadata and verification state; subscriptions are managed by
the billing service.
"""

import secrets
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.publisher import publish_background_event
from app.models.developer import Developer, DeveloperSubscription


def new_developer_key() -> str:
    return "dev_" + secrets.token_urlsafe(8)


class DeveloperPortalService:
    async def register(
        self,
        db: AsyncSession,
        *,
        user_id: str,
        name: str,
        email: str,
        bio: Optional[str] = None,
        website: Optional[str] = None,
        country: Optional[str] = None,
        organization_id: Optional[str] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        from app.developers.billing_service import PLANS

        existing = await self.find_by_user(db, user_id)
        if existing is not None:
            return self.serialize(existing)
        developer_key = new_developer_key()
        while (
            await db.execute(select(Developer).where(Developer.developer_key == developer_key))
        ).scalars().first() is not None:
            developer_key = new_developer_key()
        row = Developer(
            developer_key=developer_key,
            name=name,
            email=email,
            bio=bio,
            website=website,
            country=country,
            status="active",
            user_id=user_id,
        )
        db.add(row)
        await db.flush()
        db.add(
            DeveloperSubscription(
                developer_id=row.id,
                plan="free",
                status="active",
                monthly_quota=PLANS["free"]["quota"],
            )
        )
        await db.flush()
        await publish_background_event(
            db, name="developer.application.created",
            organization_id=organization_id or user_id,
            payload={"developer_id": row.id, "developer_key": developer_key},
        )
        if commit:
            await db.commit()
        return self.serialize(row)

    async def find_by_user(self, db: AsyncSession, user_id: str) -> Optional[Developer]:
        return (
            await db.execute(select(Developer).where(Developer.user_id == user_id))
        ).scalars().first()

    async def find_by_id(self, db: AsyncSession, developer_id: str) -> Optional[Developer]:
        return (
            await db.execute(select(Developer).where(Developer.id == developer_id))
        ).scalars().first()

    async def get_profile(self, db: AsyncSession, developer_id: str) -> Optional[dict[str, Any]]:
        row = await self.find_by_id(db, developer_id)
        if row is None:
            return None
        return self.serialize(row)

    async def list(self, db: AsyncSession, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            await db.execute(select(Developer).order_by(Developer.created_at.desc()).limit(limit))
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    async def set_verified(self, db: AsyncSession, developer_id: str, verified: bool = True) -> Optional[dict[str, Any]]:
        row = await self.find_by_id(db, developer_id)
        if row is None:
            return None
        row.verified = verified
        if verified and not row.verified_at:
            from app.core.timeutils import utcnow

            row.verified_at = utcnow()
        await db.flush()
        return self.serialize(row)

    def serialize(self, row: Developer) -> dict[str, Any]:
        return {
            "id": row.id,
            "developer_key": row.developer_key,
            "name": row.name,
            "email": row.email,
            "bio": row.bio,
            "website": row.website,
            "country": row.country,
            "status": row.status,
            "verified": row.verified,
            "verified_at": row.verified_at.isoformat() if row.verified_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


developer_portal_service = DeveloperPortalService()
