"""Permission helpers for background engines.

Background engines (notification engine, briefs) need to find *who* should
receive an alert without going through the HTTP permission dependency. These
helpers resolve the same role -> permission graph the API uses.
"""

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.role import Permission, RolePermission, UserRoleModel

logger = logging.getLogger("vcos.models.permission_helpers")


async def users_with_permission(
    db: AsyncSession, *, organization_id: str, code: str,
) -> list[str]:
    """User ids of all active users holding a permission code (directly or via roles)."""
    rows = await db.execute(
        select(UserRoleModel.user_id)
        .join(RolePermission, RolePermission.role_id == UserRoleModel.role_id)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(
            UserRoleModel.organization_id == organization_id,
            Permission.code == code,
        )
    )
    return sorted(set(rows.scalars().all()))


async def user_permission_codes(
    db: AsyncSession, *, organization_id: str, user_id: str,
) -> set[str]:
    """Effective permission codes for a single user."""
    rows = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .join(UserRoleModel, UserRoleModel.role_id == RolePermission.role_id)
        .where(
            UserRoleModel.organization_id == organization_id,
            UserRoleModel.user_id == user_id,
        )
    )
    return set(rows.scalars().all())


async def organization_owner_user_ids(
    db: AsyncSession, *, organization_id: str,
) -> list[str]:
    """Fallback recipients: the organization's registered owner user(s)."""
    from app.models.organization import Organization

    org = await db.get(Organization, organization_id)
    if org is None:
        return []
    owner_id = getattr(org, "owner_id", None)
    if not owner_id:
        return []
    return [owner_id]
