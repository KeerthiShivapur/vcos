"""Roles & permissions management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.models.organization import Organization
from app.models.role import Permission, Role, RolePermission, UserRole
from app.models.user import User
from app.schemas.common import Message
from app.schemas.users import PermissionOut, RoleCreate, RoleOut, RoleUpdate
from app.db.database import get_db
from app.services.audit_service import audit_service
from app.services.event_service import event_service
from app.services.permission_service import permission_service

router = APIRouter(prefix="/roles", tags=["Roles & Permissions"])


@router.get("/permissions", response_model=list[PermissionOut])
async def list_permissions(
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    return [PermissionOut.model_validate(p) for p in await permission_service.catalog(db)]


@router.get("", response_model=list[RoleOut])
async def list_roles(
    user: User = Depends(require_permission("roles:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    roles = (
        await db.execute(
            select(Role)
            .where(Role.organization_id == org.id)
            .order_by(Role.is_system.desc(), Role.created_at.asc())
        )
    ).scalars().all()
    result: list[RoleOut] = []
    for role in roles:
        permissions = (
            await db.execute(
                select(Permission)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .where(RolePermission.role_id == role.id)
                .order_by(Permission.resource, Permission.action)
            )
        ).scalars().all()
        user_count = (
            await db.execute(
                select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id)
            )
        ).scalar_one()
        result.append(
            RoleOut(
                id=role.id,
                name=role.name,
                code=role.code,
                description=role.description,
                is_system=role.is_system,
                is_default=role.is_default,
                created_at=role.created_at,
                permissions=[PermissionOut.model_validate(p) for p in permissions],
                user_count=user_count,
            )
        )
    return result


@router.post("", response_model=RoleOut, status_code=201)
async def create_role(
    payload: RoleCreate,
    actor: User = Depends(require_permission("roles:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    existing = (
        await db.execute(
            select(Role).where(Role.organization_id == org.id, Role.code == payload.code)
        )
    ).scalar_one_or_none()
    if existing:
        raise HTTPException(409, "A role with this code already exists")
    role = Role(
        organization_id=org.id,
        name=payload.name,
        code=payload.code,
        description=payload.description,
        is_system=False,
    )
    db.add(role)
    await db.flush()
    if payload.permission_ids:
        permissions = await permission_service.catalog(db)
        valid = {p.id for p in permissions}
        for pid in payload.permission_ids:
            if pid in valid:
                db.add(RolePermission(role_id=role.id, permission_id=pid))
    await audit_service.log(
        db,
        organization_id=org.id,
        action="role.created",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="role",
        resource_id=role.id,
        details={"code": role.code},
    )
    await event_service.emit(
        db,
        name="role.created",
        actor_id=actor.id,
        organization_id=org.id,
        payload={"role_id": role.id},
    )
    await db.commit()
    return RoleOut(
        id=role.id,
        name=role.name,
        code=role.code,
        description=role.description,
        is_system=False,
        is_default=False,
        created_at=role.created_at,
        permissions=[],
        user_count=0,
    )


@router.patch("/{role_id}", response_model=RoleOut)
async def update_role(
    role_id: str,
    payload: RoleUpdate,
    actor: User = Depends(require_permission("roles:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if role is None or role.organization_id != org.id:
        raise HTTPException(404, "Role not found")
    data = payload.model_dump(exclude_unset=True)
    permission_ids = data.pop("permission_ids", None)
    if data.get("name") is not None:
        role.name = data["name"]
    if data.get("description") is not None:
        role.description = data["description"]
    if permission_ids is not None and not role.is_system:
        existing = (
            await db.execute(select(RolePermission).where(RolePermission.role_id == role.id))
        ).scalars().all()
        for rp in existing:
            await db.delete(rp)
        valid = {p.id for p in await permission_service.catalog(db)}
        for pid in permission_ids:
            if pid in valid:
                db.add(RolePermission(role_id=role.id, permission_id=pid))
    await audit_service.log(
        db,
        organization_id=org.id,
        action="role.updated",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="role",
        resource_id=role.id,
    )
    await db.commit()

    permissions = (
        await db.execute(
            select(Permission)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role.id)
            .order_by(Permission.resource, Permission.action)
        )
    ).scalars().all()
    user_count = (
        await db.execute(select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id))
    ).scalar_one()
    return RoleOut(
        id=role.id,
        name=role.name,
        code=role.code,
        description=role.description,
        is_system=role.is_system,
        is_default=role.is_default,
        created_at=role.created_at,
        permissions=[PermissionOut.model_validate(p) for p in permissions],
        user_count=user_count,
    )


@router.delete("/{role_id}", response_model=Message)
async def delete_role(
    role_id: str,
    actor: User = Depends(require_permission("roles:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    role = await db.get(Role, role_id)
    if role is None or role.organization_id != org.id:
        raise HTTPException(404, "Role not found")
    if role.is_system:
        raise HTTPException(400, "System roles cannot be deleted")
    member_count = (
        await db.execute(select(func.count()).select_from(UserRole).where(UserRole.role_id == role.id))
    ).scalar_one()
    if member_count:
        raise HTTPException(400, "Role is assigned to users and cannot be deleted")
    await audit_service.log(
        db,
        organization_id=org.id,
        action="role.deleted",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="role",
        resource_id=role.id,
        details={"code": role.code},
    )
    await db.delete(role)
    await db.commit()
    return Message(message="Role deleted")
