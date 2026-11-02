"""Roles & permissions management."""

from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.models.organization import Organization
from app.models.role import Permission, Role, RolePermission, UserRoleModelModel
from app.models.user import User
from app.models.enterprise import ExternalGroup, GroupRoleMapping, IdentityProvider
from app.schemas.common import Message
from app.schemas.users import PermissionOut, RoleCreate, RoleOut, RoleUpdate
from app.db.database import get_db
from app.services.audit_service import audit_service
from app.services.event_service import event_service
from app.services.permission_service import permission_service
from pydantic import BaseModel

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
                select(func.count()).select_from(UserRoleModel).where(UserRoleModel.role_id == role.id)
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
        await db.execute(select(func.count()).select_from(UserRoleModel).where(UserRoleModel.role_id == role.id))
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
        await db.execute(select(func.count()).select_from(UserRoleModel).where(UserRoleModel.role_id == role.id))
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


# =============================================================================
# Group-to-Role Mappings
# =============================================================================

class ExternalGroupOut(BaseModel):
    id: str
    organization_id: str
    identity_provider_id: str
    identity_provider_name: str
    external_group_id: str
    display_name: str
    description: Optional[str]
    members_count: int
    sync_status: str
    last_synced_at: Optional[datetime]

class GroupRoleMappingCreate(BaseModel):
    external_group_id: str
    role_id: str
    justification: Optional[str] = None
    expires_at: Optional[datetime] = None

class GroupRoleMappingUpdate(BaseModel):
    role_id: Optional[str] = None
    justification: Optional[str] = None
    expires_at: Optional[datetime] = None
    mapping_state: Optional[str] = None  # pending, active, revoked, expired

class GroupRoleMappingOut(BaseModel):
    id: str
    organization_id: str
    external_group_id: str
    external_group_name: str
    role_id: str
    role_name: str
    role_code: str
    mapped_by: str
    mapped_by_name: str
    mapping_state: str
    justification: Optional[str]
    expires_at: Optional[datetime]
    tenant_verified: bool
    group_verified: bool
    validated_by: Optional[str]
    validated_at: Optional[datetime]
    revoked_by: Optional[str]
    revoked_at: Optional[datetime]
    revocation_reason: Optional[str]
    created_at: datetime
    updated_at: datetime

@router.get("/groups", response_model=list[ExternalGroupOut])
async def list_external_groups(
    user: User = Depends(require_permission("roles:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List all external groups from connected identity providers."""
    from app.models.enterprise import ExternalGroup, IdentityProvider
    
    result = await db.execute(
        select(ExternalGroup, IdentityProvider.name.label("provider_name"))
        .join(IdentityProvider, ExternalGroup.identity_provider_id == IdentityProvider.id)
        .where(ExternalGroup.organization_id == org.id)
        .order_by(ExternalGroup.display_name)
    )
    
    groups = []
    for group, provider_name in result.all():
        groups.append(ExternalGroupOut(
            id=group.id,
            organization_id=group.organization_id,
            identity_provider_id=group.identity_provider_id,
            identity_provider_name=provider_name,
            external_group_id=group.external_group_id,
            display_name=group.display_name,
            description=group.description,
            members_count=group.members_count,
            sync_status=group.sync_status,
            last_synced_at=group.last_synced_at,
        ))
    return groups


@router.get("/groups/{group_id}/mappings", response_model=list[GroupRoleMappingOut])
async def list_group_role_mappings(
    group_id: str,
    user: User = Depends(require_permission("roles:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """List all role mappings for an external group."""
    from app.models.enterprise import GroupRoleMapping, ExternalGroup, Role
    from app.models.role import Role
    from app.models.user import User as UserModel
    
    # Verify group belongs to organization
    group = await db.get(ExternalGroup, group_id)
    if not group or group.organization_id != org.id:
        raise HTTPException(404, "External group not found")
    
    result = await db.execute(
        select(GroupRoleMapping, Role.name.label("role_name"), Role.code.label("role_code"),
               UserModel.full_name.label("mapped_by_name"),
               UserModel.full_name.label("validated_by_name"),
               UserModel.full_name.label("revoked_by_name"))
        .join(Role, GroupRoleMapping.role_id == Role.id)
        .outerjoin(UserModel, GroupRoleMapping.mapped_by == UserModel.id)
        .outerjoin(UserModel, GroupRoleMapping.validated_by == UserModel.id)
        .outerjoin(UserModel, GroupRoleMapping.revoked_by == UserModel.id)
        .where(GroupRoleMapping.external_group_id == group_id)
        .where(GroupRoleMapping.organization_id == org.id)
        .order_by(GroupRoleMapping.created_at.desc())
    )
    
    mappings = []
    for row in result.all():
        mapping = row[0]
        mappings.append(GroupRoleMappingOut(
            id=mapping.id,
            organization_id=mapping.organization_id,
            external_group_id=mapping.external_group_id,
            external_group_name="",  # Will be populated from group
            role_id=mapping.role_id,
            role_name=row[1],
            role_code=row[2],
            mapped_by=mapping.mapped_by,
            mapped_by_name=row[3] or "",
            mapping_state=mapping.mapping_state,
            justification=mapping.justification,
            expires_at=mapping.expires_at,
            tenant_verified=mapping.tenant_verified,
            group_verified=mapping.group_verified,
            validated_by=mapping.validated_by,
            validated_at=mapping.validated_at,
            revoked_by=mapping.revoked_by,
            revoked_at=mapping.revoked_at,
            revocation_reason=mapping.revocation_reason,
            created_at=mapping.created_at,
            updated_at=mapping.updated_at,
        ))
    return mappings


@router.post("/groups/{group_id}/mappings", response_model=GroupRoleMappingOut, status_code=201)
async def create_group_role_mapping(
    group_id: str,
    payload: GroupRoleMappingCreate,
    user: User = Depends(require_permission("roles:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Create a new group-to-role mapping with governance validation."""
    from app.models.enterprise import GroupRoleMapping, ExternalGroup, Role
    
    # Verify group belongs to organization
    group = await db.get(ExternalGroup, group_id)
    if not group or group.organization_id != org.id:
        raise HTTPException(404, "External group not found")
    
    # Verify role exists and belongs to organization
    role = await db.get(Role, payload.role_id)
    if not role or role.organization_id != org.id:
        raise HTTPException(404, "Role not found")
    
    # Check for existing mapping
    existing = await db.execute(
        select(GroupRoleMapping)
        .where(GroupRoleMapping.external_group_id == group_id)
        .where(GroupRoleMapping.role_id == payload.role_id)
        .where(GroupRoleMapping.organization_id == org.id)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, "This group is already mapped to this role")
    
    # Governance validation: check if user can assign this role
    if role.is_system:
        raise HTTPException(403, "Cannot map external groups to system roles directly")
    
    # Create mapping
    mapping = GroupRoleMapping(
        organization_id=org.id,
        external_group_id=group_id,
        role_id=payload.role_id,
        mapped_by=user.id,
        mapping_state="pending",  # Requires validation
        justification=payload.justification,
        expires_at=payload.expires_at,
        tenant_verified=False,  # Requires admin validation
        group_verified=False,   # Requires admin validation
    )
    db.add(mapping)
    await db.flush()
    
    # Log audit event
    await audit_service.log(
        db,
        organization_id=org.id,
        action="group_role_mapping.created",
        actor_id=user.id,
        actor_email=user.email,
        resource_type="group_role_mapping",
        resource_id=mapping.id,
        details={
            "external_group_id": group_id,
            "external_group_name": group.display_name,
            "role_id": payload.role_id,
            "role_name": role.name,
            "justification": payload.justification,
        },
    )
    await db.commit()
    await db.refresh(mapping)
    
    # Return with populated names
    return GroupRoleMappingOut(
        id=mapping.id,
        organization_id=mapping.organization_id,
        external_group_id=mapping.external_group_id,
        external_group_name=group.display_name,
        role_id=mapping.role_id,
        role_name=role.name,
        role_code=role.code,
        mapped_by=mapping.mapped_by,
        mapped_by_name=user.full_name,
        mapping_state=mapping.mapping_state,
        justification=mapping.justification,
        expires_at=mapping.expires_at,
        tenant_verified=mapping.tenant_verified,
        group_verified=mapping.group_verified,
        validated_by=mapping.validated_by,
        validated_at=mapping.validated_at,
        revoked_by=mapping.revoked_by,
        revoked_at=mapping.revoked_at,
        revocation_reason=mapping.revocation_reason,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


@router.patch("/groups/{group_id}/mappings/{mapping_id}", response_model=GroupRoleMappingOut)
async def update_group_role_mapping(
    group_id: str,
    mapping_id: str,
    payload: GroupRoleMappingUpdate,
    user: User = Depends(require_permission("roles:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Update a group-to-role mapping."""
    from app.models.enterprise import GroupRoleMapping, Role
    
    mapping = await db.get(GroupRoleMapping, mapping_id)
    if not mapping or mapping.organization_id != org.id or mapping.external_group_id != group_id:
        raise HTTPException(404, "Group role mapping not found")
    
    # Validate role if changing
    if payload.role_id and payload.role_id != mapping.role_id:
        role = await db.get(Role, payload.role_id)
        if not role or role.organization_id != org.id:
            raise HTTPException(404, "Role not found")
        if role.is_system:
            raise HTTPException(403, "Cannot map external groups to system roles directly")
        mapping.role_id = payload.role_id
    
    if payload.justification is not None:
        mapping.justification = payload.justification
    if payload.expires_at is not None:
        mapping.expires_at = payload.expires_at
    if payload.mapping_state is not None:
        old_state = mapping.mapping_state
        mapping.mapping_state = payload.mapping_state
        # Handle state transitions
        if payload.mapping_state == "active" and old_state == "pending":
            mapping.validated_by = user.id
            mapping.validated_at = datetime.now(timezone.utc)
        elif payload.mapping_state == "revoked" and old_state != "revoked":
            mapping.revoked_by = user.id
            mapping.revoked_at = datetime.now(timezone.utc)
    
    await db.commit()
    await db.refresh(mapping)
    
    # Fetch related data for response
    role = await db.get(Role, mapping.role_id)
    group = await db.get(ExternalGroup, mapping.external_group_id)
    
    return GroupRoleMappingOut(
        id=mapping.id,
        organization_id=mapping.organization_id,
        external_group_id=mapping.external_group_id,
        external_group_name=group.display_name if group else "",
        role_id=mapping.role_id,
        role_name=role.name if role else "",
        role_code=role.code if role else "",
        mapped_by=mapping.mapped_by,
        mapped_by_name="",  # Would need to fetch user
        mapping_state=mapping.mapping_state,
        justification=mapping.justification,
        expires_at=mapping.expires_at,
        tenant_verified=mapping.tenant_verified,
        group_verified=mapping.group_verified,
        validated_by=mapping.validated_by,
        validated_at=mapping.validated_at,
        revoked_by=mapping.revoked_by,
        revoked_at=mapping.revoked_at,
        revocation_reason=mapping.revocation_reason,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )


@router.delete("/groups/{group_id}/mappings/{mapping_id}", response_model=Message)
async def delete_group_role_mapping(
    group_id: str,
    mapping_id: str,
    user: User = Depends(require_permission("roles:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a group-to-role mapping."""
    from app.models.enterprise import GroupRoleMapping
    
    mapping = await db.get(GroupRoleMapping, mapping_id)
    if not mapping or mapping.organization_id != org.id or mapping.external_group_id != group_id:
        raise HTTPException(404, "Group role mapping not found")
    
    # Soft delete by setting state to revoked
    mapping.mapping_state = "revoked"
    mapping.revoked_by = user.id
    mapping.revoked_at = datetime.now(timezone.utc)
    
    await audit_service.log(
        db,
        organization_id=org.id,
        action="group_role_mapping.revoked",
        actor_id=user.id,
        actor_email=user.email,
        resource_type="group_role_mapping",
        resource_id=mapping.id,
        details={
            "external_group_id": group_id,
            "role_id": mapping.role_id,
        },
    )
    await db.commit()
    
    return Message(message="Group role mapping revoked")


@router.post("/groups/{group_id}/mappings/{mapping_id}/validate", response_model=GroupRoleMappingOut)
async def validate_group_role_mapping(
    group_id: str,
    mapping_id: str,
    user: User = Depends(require_permission("roles:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    """Validate a pending group-to-role mapping (admin approval)."""
    from app.models.enterprise import GroupRoleMapping, ExternalGroup, Role
    
    mapping = await db.get(GroupRoleMapping, mapping_id)
    if not mapping or mapping.organization_id != org.id or mapping.external_group_id != group_id:
        raise HTTPException(404, "Group role mapping not found")
    
    if mapping.mapping_state != "pending":
        raise HTTPException(400, "Only pending mappings can be validated")
    
    # Verify tenant ownership (group belongs to same tenant as org)
    group = await db.get(ExternalGroup, group_id)
    if not group or group.organization_id != org.id:
        raise HTTPException(404, "External group not found")
    
    # Mark as validated
    mapping.mapping_state = "active"
    mapping.tenant_verified = True
    mapping.group_verified = True
    mapping.validated_by = user.id
    mapping.validated_at = datetime.now(timezone.utc)
    
    await audit_service.log(
        db,
        organization_id=org.id,
        action="group_role_mapping.validated",
        actor_id=user.id,
        actor_email=user.email,
        resource_type="group_role_mapping",
        resource_id=mapping.id,
        details={
            "external_group_id": group_id,
            "external_group_name": group.display_name,
            "role_id": mapping.role_id,
        },
    )
    await db.commit()
    await db.refresh(mapping)
    
    role = await db.get(Role, mapping.role_id)
    group = await db.get(ExternalGroup, mapping.external_group_id)
    
    return GroupRoleMappingOut(
        id=mapping.id,
        organization_id=mapping.organization_id,
        external_group_id=mapping.external_group_id,
        external_group_name=group.display_name if group else "",
        role_id=mapping.role_id,
        role_name=role.name if role else "",
        role_code=role.code if role else "",
        mapped_by=mapping.mapped_by,
        mapped_by_name="",
        mapping_state=mapping.mapping_state,
        justification=mapping.justification,
        expires_at=mapping.expires_at,
        tenant_verified=mapping.tenant_verified,
        group_verified=mapping.group_verified,
        validated_by=mapping.validated_by,
        validated_at=mapping.validated_at,
        revoked_by=mapping.revoked_by,
        revoked_at=mapping.revoked_at,
        revocation_reason=mapping.revocation_reason,
        created_at=mapping.created_at,
        updated_at=mapping.updated_at,
    )
