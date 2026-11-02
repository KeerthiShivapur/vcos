"""Feature flag service (Phase 15).

Flag CRUD plus deterministic targeting evaluation: enabled globally, or
scoped to user lists, roles or a rollout percentage (stable hash so a user
keeps their assignment across evaluations).
"""

import hashlib
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.events.publisher import publish_event
from app.models.feature_flags import FeatureFlag


class FeatureFlagService:
    async def create(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        key: str,
        name: str,
        description: Optional[str] = None,
        enabled: bool = False,
        rules: Optional[dict[str, Any]] = None,
        updated_by: Optional[str] = None,
    ) -> FeatureFlag:
        flag = FeatureFlag(
            organization_id=organization_id,
            key=key,
            name=name,
            description=description,
            enabled=enabled,
            rules=rules or {},
            updated_by=updated_by,
        )
        db.add(flag)
        await db.flush()
        await publish_event(
            db,
            name="feature.enabled" if enabled else "feature.disabled",
            organization_id=organization_id,
            actor_id=updated_by,
            payload={"key": key, "enabled": enabled},
        )
        return flag

    async def update(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        flag_id: str,
        enabled: Optional[bool] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        rules: Optional[dict[str, Any]] = None,
        updated_by: Optional[str] = None,
    ) -> Optional[FeatureFlag]:
        flag = await db.get(FeatureFlag, flag_id)
        if flag is None or flag.organization_id != organization_id:
            return None
        previous = flag.enabled
        if enabled is not None:
            flag.enabled = enabled
        if name:
            flag.name = name
        if description is not None:
            flag.description = description
        if rules is not None:
            flag.rules = rules
        flag.updated_by = updated_by
        if enabled is not None and enabled != previous:
            await publish_event(
                db,
                name="feature.enabled" if enabled else "feature.disabled",
                organization_id=organization_id,
                actor_id=updated_by,
                payload={"key": flag.key, "enabled": enabled},
            )
        return flag

    async def list_flags(self, db: AsyncSession, organization_id: str) -> list[FeatureFlag]:
        result = await db.execute(
            select(FeatureFlag)
            .where(FeatureFlag.organization_id == organization_id)
            .order_by(FeatureFlag.created_at.desc())
        )
        return list(result.scalars().all())

    async def delete(
        self, db: AsyncSession, *, organization_id: str, flag_id: str
    ) -> bool:
        flag = await db.get(FeatureFlag, flag_id)
        if flag is None or flag.organization_id != organization_id:
            return False
        await db.delete(flag)
        return True

    async def evaluate(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        key: str,
        user_id: Optional[str] = None,
        roles: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        flag = (
            await db.execute(
                select(FeatureFlag).where(
                    FeatureFlag.organization_id == organization_id,
                    FeatureFlag.key == key,
                )
            )
        ).scalars().first()
        if flag is None:
            return {"key": key, "enabled": False, "reason": "unknown_flag"}
        if not flag.enabled:
            return {"key": key, "enabled": False, "reason": "disabled"}
        rules = flag.rules or {}
        users = set(rules.get("users") or [])
        if user_id and user_id in users:
            return {"key": key, "enabled": True, "reason": "user_targeted"}
        roles_allowed = set(rules.get("roles") or [])
        if roles_allowed and roles and roles_allowed.intersection(set(roles)):
            return {"key": key, "enabled": True, "reason": "role_targeted"}
        percentage = int(rules.get("percentage", 100))
        if percentage >= 100:
            return {"key": key, "enabled": True, "reason": "enabled"}
        if user_id:
            digest = int(hashlib.sha256(f"{key}:{user_id}".encode()).hexdigest(), 16) % 100
            if digest < percentage:
                return {"key": key, "enabled": True, "reason": "percentage"}
            return {"key": key, "enabled": False, "reason": "percentage"}
        return {"key": key, "enabled": False, "reason": "not_targeted"}


feature_flag_service = FeatureFlagService()
