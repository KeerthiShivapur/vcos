from __future__ import annotations

"""Developer application service (Phase 18.2) â€” apps, plugins & API keys.

Applications can be apps, plugins, agents, widgets, themes or workflow packs.
Each application can issue scoped API keys (only hashes are stored); the
plaintext secret is returned exactly once.
"""

import hashlib
import secrets
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.publisher import publish_background_event
from app.models.developer import DeveloperApplication, DeveloperApiKey

APP_TYPES = ("app", "plugin", "agent", "widget", "theme", "workflow_pack", "integration")


def _key_secret() -> tuple[str, str]:
    raw = "vcod_" + secrets.token_urlsafe(32)
    return raw, hashlib.sha256(raw.encode()).hexdigest()


class DeveloperApplicationService:
    async def create(
        self,
        db: AsyncSession,
        *,
        developer_id: str,
        name: str,
        app_type: str = "app",
        description: Optional[str] = None,
        scopes: Optional[list[str]] = None,
        endpoints: Optional[dict[str, Any]] = None,
        settings: Optional[dict[str, Any]] = None,
        commit: bool = False,
    ) -> dict[str, Any]:
        if app_type not in APP_TYPES:
            raise ValueError(f"app_type must be one of {APP_TYPES}")
        application_key = "app_" + secrets.token_urlsafe(10)
        row = DeveloperApplication(
            developer_id=developer_id,
            application_key=application_key,
            name=name,
            app_type=app_type,
            description=description,
            scopes=scopes or [],
            endpoints=endpoints or {},
            settings=settings or {},
            status="draft",
        )
        db.add(row)
        await db.flush()
        if commit:
            await db.commit()
        return self.serialize(row)

    async def list(self, db: AsyncSession, developer_id: str, limit: int = 100) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(DeveloperApplication)
                .where(DeveloperApplication.developer_id == developer_id)
                .order_by(DeveloperApplication.created_at.desc())
                .limit(limit)
            )
        ).scalars().all()
        return [self.serialize(r) for r in rows]

    async def get(self, db: AsyncSession, developer_id: str, application_id: str) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(DeveloperApplication).where(
                    DeveloperApplication.developer_id == developer_id,
                    DeveloperApplication.id == application_id,
                )
            )
        ).scalars().first()
        return self.serialize(row) if row else None

    async def update(
        self,
        db: AsyncSession,
        developer_id: str,
        application_id: str,
        **fields,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(DeveloperApplication).where(
                    DeveloperApplication.developer_id == developer_id,
                    DeveloperApplication.id == application_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        for key, value in fields.items():
            if key in ("name", "description", "version", "scopes", "endpoints", "settings") and value is not None:
                setattr(row, key, value)
        await db.flush()
        return self.serialize(row)

    async def publish(
        self, db: AsyncSession, developer_id: str, application_id: str,
        organization_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(DeveloperApplication).where(
                    DeveloperApplication.developer_id == developer_id,
                    DeveloperApplication.id == application_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        from app.core.timeutils import utcnow

        row.status = "published"
        row.published_at = utcnow()
        await db.flush()
        await publish_background_event(
            db, name="developer.app.published",
            organization_id=organization_id or developer_id,
            payload={"application_id": row.id, "application_key": row.application_key},
        )
        return self.serialize(row)

    async def delist(
        self, db: AsyncSession, developer_id: str, application_id: str,
        organization_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(DeveloperApplication).where(
                    DeveloperApplication.developer_id == developer_id,
                    DeveloperApplication.id == application_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.status = "archived"
        await db.flush()
        await publish_background_event(
            db, name="developer.app.delisted",
            organization_id=organization_id or developer_id,
            payload={"application_id": row.id},
        )
        return self.serialize(row)

    # ------------------------------------------------------------ API keys

    async def create_key(
        self,
        db: AsyncSession,
        *,
        developer_id: str,
        application_id: str,
        name: str,
        scopes: Optional[list[str]] = None,
        rate_limit_per_minute: int = 60,
        expires_at: Any = None,
        organization_id: Optional[str] = None,
        commit: bool = False,
    ) -> Optional[dict[str, Any]]:
        app = await self.get(db, developer_id, application_id)
        if app is None:
            return None
        raw, key_hash = _key_secret()
        row = DeveloperApiKey(
            developer_id=developer_id,
            application_id=application_id,
            name=name,
            key_prefix=raw[:10],
            key_hash=key_hash,
            scopes=scopes or [],
            rate_limit_per_minute=rate_limit_per_minute,
            status="active",
            expires_at=expires_at,
        )
        db.add(row)
        await db.flush()
        await publish_background_event(
            db, name="developer.api_key.created",
            organization_id=organization_id or developer_id,
            payload={"key_id": row.id, "application_id": application_id},
        )
        if commit:
            await db.commit()
        return {**self.serialize_key(row), "api_key": raw}

    async def list_keys(self, db: AsyncSession, developer_id: str, application_id: str) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(DeveloperApiKey).where(
                    DeveloperApiKey.developer_id == developer_id,
                    DeveloperApiKey.application_id == application_id,
                )
            )
        ).scalars().all()
        return [self.serialize_key(r) for r in rows]

    async def revoke_key(
        self, db: AsyncSession, developer_id: str, key_id: str,
        organization_id: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        row = (
            await db.execute(
                select(DeveloperApiKey).where(
                    DeveloperApiKey.developer_id == developer_id,
                    DeveloperApiKey.id == key_id,
                )
            )
        ).scalars().first()
        if row is None:
            return None
        row.status = "revoked"
        await db.flush()
        await publish_background_event(
            db, name="developer.api_key.revoked",
            organization_id=organization_id or developer_id,
            payload={"key_id": row.id},
        )
        return self.serialize_key(row)

    def serialize_key(self, row: DeveloperApiKey) -> dict[str, Any]:
        return {
            "id": row.id,
            "application_id": row.application_id,
            "name": row.name,
            "key_prefix": row.key_prefix,
            "scopes": row.scopes or [],
            "rate_limit_per_minute": row.rate_limit_per_minute,
            "status": row.status,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }

    def serialize(self, row: DeveloperApplication) -> dict[str, Any]:
        return {
            "id": row.id,
            "application_key": row.application_key,
            "name": row.name,
            "app_type": row.app_type,
            "description": row.description,
            "version": row.version,
            "status": row.status,
            "scopes": row.scopes or [],
            "endpoints": row.endpoints or {},
            "settings": row.settings or {},
            "verified": row.verified,
            "published_at": row.published_at.isoformat() if row.published_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }


developer_application_service = DeveloperApplicationService()
