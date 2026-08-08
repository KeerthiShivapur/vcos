"""SCIM 2.0 provisioning service (Phase 15).

Mirrors external directory users and groups into VCOS. User provisioning
creates or updates VCOS User records (identity service binding is optional);
group provisioning stores the directory group and its members so enterprise
admins can drive role assignments from identity providers.
"""

import secrets
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.models.enterprise import EnterpriseUser, ScimGroup
from app.models.user import User


def _scim_user_shape(user: User, external_id: str) -> dict[str, Any]:
    return {
        "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"],
        "id": external_id,
        "userName": user.username,
        "emails": [{"value": user.email, "primary": True}],
        "active": user.status == "active",
        "external_id": external_id,
        "vcos_user_id": user.id,
        "meta": {
            "resourceType": "User",
            "created": user.created_at.isoformat() if user.created_at else None,
        },
    }


class ScimService:
    async def create_user(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        user_name: str,
        emails: Optional[list[dict[str, Any]]] = None,
        active: bool = True,
        external_id: Optional[str] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        email = ""
        if emails:
            for entry in emails:
                if entry.get("primary") or not email:
                    email = entry.get("value", "")
        existing = (
            await db.execute(
                select(User).where(User.organization_id == organization_id, User.email == email.lower())
            )
        ).scalars().first() if email else None
        if existing is None:
            username = user_name
            conflict = (
                await db.execute(
                    select(User).where(
                        User.organization_id == organization_id, User.username == username
                    )
                )
            ).scalars().first()
            if conflict:
                username = f"{user_name}_{secrets.token_hex(3)}"
            existing = User(
                organization_id=organization_id,
                username=username,
                email=(email or f"{user_name}@scim.local").lower(),
                full_name=(attributes or {}).get("displayName", user_name),
                password_hash=secrets.token_hex(32),
                status="active" if active else "pending",
            )
            db.add(existing)
            await db.flush()
        subject = external_id or f"scim:{user_name}"
        binding = (
            await db.execute(
                select(EnterpriseUser).where(
                    EnterpriseUser.organization_id == organization_id,
                    EnterpriseUser.external_subject == subject,
                )
            )
        ).scalars().first()
        if binding is None:
            binding = EnterpriseUser(
                organization_id=organization_id,
                user_id=existing.id,
                external_subject=subject,
                provider="scim",
            )
            db.add(binding)
            await db.flush()
        if active and existing.status != "active":
            existing.status = "active"
        return _scim_user_shape(existing, subject)

    async def list_users(
        self, db: AsyncSession, *, organization_id: str, filter_str: Optional[str] = None
    ) -> list[dict[str, Any]]:
        query = select(EnterpriseUser).where(EnterpriseUser.organization_id == organization_id)
        if filter_str and filter_str.lower().startswith("username"):
            token = filter_str.split("eq")[-1].strip().strip('"').strip("'")
            result = await db.execute(query)
            out = []
            for binding in result.scalars().all():
                user = await db.get(User, binding.user_id)
                if user and token in (user.username or ""):
                    out.append(_scim_user_shape(user, binding.external_subject))
            return out
        result = await db.execute(query.order_by(EnterpriseUser.created_at.desc()))
        out = []
        for binding in result.scalars().all():
            user = await db.get(User, binding.user_id)
            if user:
                out.append(_scim_user_shape(user, binding.external_subject))
        return out

    async def get_user(
        self, db: AsyncSession, *, organization_id: str, external_id: str
    ) -> Optional[dict[str, Any]]:
        binding = (
            await db.execute(
                select(EnterpriseUser).where(
                    EnterpriseUser.organization_id == organization_id,
                    EnterpriseUser.external_subject == external_id,
                )
            )
        ).scalars().first()
        if binding is None:
            return None
        user = await db.get(User, binding.user_id)
        if user is None:
            return None
        return _scim_user_shape(user, binding.external_subject)

    async def update_user(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        external_id: str,
        active: Optional[bool] = None,
        user_name: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        binding = (
            await db.execute(
                select(EnterpriseUser).where(
                    EnterpriseUser.organization_id == organization_id,
                    EnterpriseUser.external_subject == external_id,
                )
            )
        ).scalars().first()
        if binding is None:
            return None
        user = await db.get(User, binding.user_id)
        if user is None:
            return None
        if active is not None:
            user.status = "active" if active else "suspended"
        if user_name:
            user.username = user_name
        return _scim_user_shape(user, binding.external_subject)

    async def delete_user(
        self, db: AsyncSession, *, organization_id: str, external_id: str
    ) -> bool:
        binding = (
            await db.execute(
                select(EnterpriseUser).where(
                    EnterpriseUser.organization_id == organization_id,
                    EnterpriseUser.external_subject == external_id,
                )
            )
        ).scalars().first()
        if binding is None:
            return False
        user = await db.get(User, binding.user_id)
        if user:
            user.status = "deactivated"
        await db.delete(binding)
        return True

    # --------------------------------------------------------------- groups

    async def upsert_group(
        self,
        db: AsyncSession,
        *,
        organization_id: str,
        external_id: str,
        display_name: str,
        member_external_ids: Optional[list[str]] = None,
        attributes: Optional[dict[str, Any]] = None,
    ) -> ScimGroup:
        group = (
            await db.execute(
                select(ScimGroup).where(
                    ScimGroup.organization_id == organization_id,
                    ScimGroup.external_id == external_id,
                )
            )
        ).scalars().first()
        if group is None:
            group = ScimGroup(
                organization_id=organization_id,
                external_id=external_id,
                display_name=display_name,
            )
            db.add(group)
        group.display_name = display_name
        if member_external_ids is not None:
            group.member_external_ids = member_external_ids
        if attributes is not None:
            group.attributes = attributes
        await db.flush()
        return group

    async def list_groups(self, db: AsyncSession, organization_id: str) -> list[ScimGroup]:
        result = await db.execute(
            select(ScimGroup)
            .where(ScimGroup.organization_id == organization_id)
            .order_by(ScimGroup.display_name)
        )
        return list(result.scalars().all())

    async def delete_group(
        self, db: AsyncSession, *, organization_id: str, external_id: str
    ) -> bool:
        group = (
            await db.execute(
                select(ScimGroup).where(
                    ScimGroup.organization_id == organization_id,
                    ScimGroup.external_id == external_id,
                )
            )
        ).scalars().first()
        if group is None:
            return False
        await db.delete(group)
        return True


scim_service = ScimService()
