"""Users & invitations: directory, invite flow, role assignment, status."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_organization, get_current_user, require_permission
from app.models.organization import Organization
from app.models.user import User
from app.models.invitation import Invitation
from app.schemas.common import Message, Paginated
from app.schemas.users import AssignRoleRequest, InviteResult, InviteUserRequest, UserOut
from app.schemas.auth import UpdateProfileRequest
from app.db.database import get_db
from app.services.audit_service import audit_service
from app.services.auth_service import AuthError, auth_service
from app.services.event_service import event_service
from app.services.permission_service import permission_service
from app.services.rate_limit import rate_limiter

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("", response_model=Paginated[UserOut])
async def list_users(
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str = Query(None),
    status: str = Query(None),
):
    from sqlalchemy import func, or_

    filters = [User.organization_id == org.id]
    if status:
        filters.append(User.status == status)
    if search:
        pattern = f"%{search.lower()}%"
        filters.append(
            or_(
                func.lower(User.full_name).like(pattern),
                func.lower(User.email).like(pattern),
                func.lower(User.job_title).like(pattern),
            )
        )
    total = (await db.execute(select(func.count()).select_from(User).where(*filters))).scalar_one()
    result = await db.execute(
        select(User).where(*filters).order_by(User.created_at.asc()).offset((page - 1) * page_size).limit(page_size)
    )
    users = [UserOut.model_validate(u) for u in result.scalars().all()]
    return Paginated(
        items=users,
        total=total,
        page=page,
        page_size=page_size,
        pages=-(-total // page_size) if page_size else 0,
    )


@router.get("/me", response_model=UserOut)
async def my_profile(user: User = Depends(get_current_user)):
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_my_profile(
    payload: UpdateProfileRequest,
    request: Request,
    user: User = Depends(require_permission("users:profile")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(user, field, value)
    await audit_service.log(
        db,
        organization_id=org.id,
        action="user.profile.updated",
        actor_id=user.id,
        actor_email=user.email,
        resource_type="user",
        resource_id=user.id,
        ip_address=get_client_ip(request),
    )
    await db.commit()
    return UserOut.model_validate(user)


@router.post("/invite", response_model=InviteResult, status_code=201)
async def invite_user(
    payload: InviteUserRequest,
    request: Request,
    user: User = Depends(require_permission("users:invite")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    allowed, retry = await rate_limiter.check(f"invite:{payload.email}")
    if not allowed:
        raise HTTPException(429, f"Too many attempts, retry in {retry}s")
    try:
        result = await auth_service.invite(
            db,
            organization=org,
            inviter=user,
            email=payload.email,
            full_name=payload.full_name,
            role=payload.role,
            message=payload.message,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    await db.commit()
    return InviteResult(
        invitation=result["invitation"],
        token=result.get("token"),
        url=result.get("url"),
    )


@router.get("/invitations", response_model=list[dict])
async def list_invitations(
    user: User = Depends(require_permission("invitations:read")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Invitation).where(Invitation.organization_id == org.id).order_by(Invitation.created_at.desc())
    )
    return [
        {
            "id": i.id,
            "email": i.email,
            "full_name": i.full_name,
            "role": i.role,
            "status": i.status,
            "message": i.message,
            "created_at": i.created_at,
            "expires_at": i.token_expires_at,
        }
        for i in result.scalars().all()
    ]


@router.post("/invitations/{invitation_id}/resend", response_model=InviteResult)
async def resend_invitation(
    invitation_id: str,
    request: Request,
    user: User = Depends(require_permission("invitations:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    invitation = await db.get(Invitation, invitation_id)
    if invitation is None or invitation.organization_id != org.id:
        raise HTTPException(404, "Invitation not found")
    allowed, retry = await rate_limiter.check(f"invite_resend:{invitation.email}")
    if not allowed:
        raise HTTPException(429, f"Too many attempts, retry in {retry}s")
    try:
        result = await auth_service.resend_invitation(
            db,
            organization=org,
            actor=user,
            invitation_id=invitation_id,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    await db.commit()
    return InviteResult(
        invitation=result["invitation"],
        token=result.get("token"),
        url=result.get("url"),
    )


@router.post("/invitations/{invitation_id}/revoke", response_model=Message)
async def revoke_invitation(
    invitation_id: str,
    request: Request,
    user: User = Depends(require_permission("invitations:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    invitation = await db.get(Invitation, invitation_id)
    if invitation is None or invitation.organization_id != org.id:
        raise HTTPException(404, "Invitation not found")
    if invitation.status == "pending":
        invitation.status = "revoked"
        await audit_service.log(
            db,
            organization_id=org.id,
            action="invitation.revoked",
            actor_id=user.id,
            actor_email=user.email,
            resource_type="invitation",
            resource_id=invitation.id,
            ip_address=get_client_ip(request),
            details={"email": invitation.email},
        )
        await event_service.emit(
            db,
            name="invitation.revoked",
            actor_id=user.id,
            organization_id=org.id,
            payload={"invitation_id": invitation.id},
        )
        await db.commit()
        return Message(message="Invitation revoked")
    return Message(message="Invitation is not pending")


@router.get("/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None or user.organization_id != org.id:
        raise HTTPException(404, "User not found")
    return UserOut.model_validate(user)


@router.patch("/{user_id}/status", response_model=UserOut)
async def update_user_status(
    user_id: str,
    payload: dict,
    request: Request,
    actor: User = Depends(require_permission("users:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    from app.schemas.users import UpdateUserStatusRequest

    body = UpdateUserStatusRequest(**payload)
    target = await db.get(User, user_id)
    if target is None or target.organization_id != org.id:
        raise HTTPException(404, "User not found")
    if target.id == actor.id and body.status != "active":
        raise HTTPException(400, "You cannot change your own status")
    target.status = body.status
    await audit_service.log(
        db,
        organization_id=org.id,
        action="user.status.updated",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="user",
        resource_id=target.id,
        ip_address=get_client_ip(request),
        details={"status": body.status, "target": target.email},
    )
    await event_service.emit(
        db,
        name="user.status.updated",
        actor_id=actor.id,
        organization_id=org.id,
        payload={"user_id": target.id, "status": body.status},
    )
    await db.commit()
    return UserOut.model_validate(target)


@router.post("/{user_id}/roles", response_model=UserOut)
async def assign_roles(
    user_id: str,
    payload: AssignRoleRequest,
    request: Request,
    actor: User = Depends(require_permission("users:manage")),
    org: Organization = Depends(get_current_organization),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(User, user_id)
    if target is None or target.organization_id != org.id:
        raise HTTPException(404, "User not found")
    from app.models.role import Role

    role = await db.get(Role, payload.role_id)
    if role is None or role.organization_id != org.id:
        raise HTTPException(400, "Invalid role")
    from app.models.role import Permission, RolePermission

    target_perm_rows = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.role_id == role.id)
    )
    target_perms = set(target_perm_rows.scalars().all())
    actor_perms = await permission_service.user_permission_codes(db, user_id=actor.id, organization_id=org.id)
    if not target_perms.issubset(actor_perms):
        raise HTTPException(403, "You cannot assign a role that grants permissions you do not have.")
    await permission_service.assign_role(
        db, user_id=target.id, role_id=role.id, organization_id=org.id, replace_all=payload.replace_all
    )
    target.role = role.code
    await audit_service.log(
        db,
        organization_id=org.id,
        action="user.role.assigned",
        actor_id=actor.id,
        actor_email=actor.email,
        resource_type="user",
        resource_id=target.id,
        ip_address=get_client_ip(request),
        details={"role": role.code, "target": target.email},
    )
    await event_service.emit(
        db,
        name="role.assigned",
        actor_id=actor.id,
        organization_id=org.id,
        payload={"user_id": target.id, "role_id": role.id},
    )
    await db.commit()
    return UserOut.model_validate(target)
