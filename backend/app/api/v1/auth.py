"""Authentication endpoints: register, login, refresh, logout, passwords, sessions."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_client_ip, get_current_user
from app.core.config import get_settings
from app.core.security import create_access_token, create_refresh_token
from app.core.timeutils import utcnow
from app.models.user import Session, User
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    InviteRegisterRequest,
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    ResetPasswordRequest,
    SessionOut,
    UserOut,
    VerifyEmailRequest,
)
from app.schemas.auth import LoginResult
from app.schemas.common import Message, TokenPair
from app.schemas.organization import OrganizationOut
from app.db.database import get_db
from app.services.auth_service import AuthError, auth_service
from app.services.audit_service import audit_service
from app.services.rate_limit import rate_limiter

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _login_result(data: dict) -> LoginResult:
    settings = get_settings()
    user = data["user"]
    org = data["organization"]
    return LoginResult(
        access_token=create_access_token(user.id, org.id),
        refresh_token=create_refresh_token(user.id, org.id, data["session"].id),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        user=UserOut.model_validate(user),
        organization=OrganizationOut.model_validate(org),
    )


@router.post("/register", response_model=LoginResult, status_code=201)
async def register(payload: RegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Register a new company and its founding administrator."""
    print(f"DEBUG Register request: email={payload.email}, org_name={payload.organization_name}, org_slug={payload.organization_slug}")
    allowed, retry = await rate_limiter.check(f"register:{request.client.host}")
    if not allowed:
        raise HTTPException(429, f"Too many attempts, retry in {retry}s")
    try:
        data = await auth_service.register_organization(
            db, payload, ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent")
        )
        await db.commit()
    except AuthError as exc:
        print(f"DEBUG AuthError: {exc.message}")
        raise HTTPException(exc.status, exc.message) from exc
    except IntegrityError as exc:
        await db.rollback()
        print(f"DEBUG IntegrityError: {exc}")
        raise HTTPException(409, "This organization name or slug is already taken.") from exc
    return _login_result(data)


@router.post("/register/invite", response_model=LoginResult, status_code=201)
async def register_from_invite(payload: InviteRegisterRequest, request: Request, db: AsyncSession = Depends(get_db)):
    """Accept an invitation and create the employee account."""
    allowed, retry = await rate_limiter.check(f"register_invite:{request.client.host}")
    if not allowed:
        raise HTTPException(429, f"Too many attempts, retry in {retry}s")
    try:
        data = await auth_service.register_from_invitation(
            db,
            token=payload.token,
            full_name=payload.full_name,
            username=payload.username,
            password=payload.password,
            ip_address=get_client_ip(request),
            user_agent=request.headers.get("user-agent"),
        )
    except AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    await db.commit()
    return _login_result(data)


@router.post("/login", response_model=LoginResult)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    allowed, retry = await rate_limiter.check(f"login:{payload.email}")
    if not allowed:
        raise HTTPException(429, f"Too many attempts, retry in {retry}s")
    try:
        data = await auth_service.login(
            db, payload, ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent")
        )
    except AuthError as exc:
        await db.commit()
        raise HTTPException(exc.status, exc.message) from exc
    await db.commit()
    return _login_result(data)


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        data = await auth_service.refresh(
            db, payload.refresh_token, ip_address=get_client_ip(request), user_agent=request.headers.get("user-agent")
        )
    except AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    await db.commit()
    return TokenPair(
        access_token=data["access_token"],
        refresh_token=payload.refresh_token,
        expires_in=data["expires_in"],
    )


@router.post("/logout", response_model=Message)
async def logout(
    payload: LogoutRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.logout(
        db,
        user=user,
        refresh_token=payload.refresh_token,
        all_devices=payload.all_devices,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return Message(message="Logged out")


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    from app.services.permission_service import permission_service

    perms = await permission_service.user_permission_codes(
        db, user_id=user.id, organization_id=user.organization_id
    )
    out = UserOut.model_validate(user)
    out.permissions = sorted(perms)
    return out


@router.get("/debug/permissions")
async def debug_permissions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """Debug endpoint to check database permissions."""
    from app.models.role import UserRoleModel, Role, RolePermission, Permission
    from sqlalchemy import select
    from app.models.permission_helpers import user_permission_codes
    
    # Check UserRoleModel
    result = await db.execute(select(UserRoleModel).where(
        UserRoleModel.user_id == user.id,
        UserRoleModel.organization_id == user.organization_id
    ))
    user_roles = result.scalars().all()
    
    role_details = []
    for ur in user_roles:
        role = await db.get(Role, ur.role_id)
        role_details.append({
            "user_role_id": ur.id,
            "role_id": ur.role_id,
            "role_code": role.code if role else "NOT FOUND",
            "role_name": role.name if role else "NOT FOUND",
        })
    
    # Check permissions via helper
    codes = await user_permission_codes(db, organization_id=user.organization_id, user_id=user.id)
    
    # Check all roles in org
    result = await db.execute(select(Role).where(Role.organization_id == user.organization_id))
    all_roles = result.scalars().all()
    
    all_perms = []
    for role in all_roles:
        result = await db.execute(select(RolePermission).where(RolePermission.role_id == role.id))
        rps = result.scalars().all()
        for rp in rps:
            perm = await db.get(Permission, rp.permission_id)
            all_perms.append({
                "role_code": role.code,
                "role_name": role.name,
                "perm_code": perm.code if perm else "NOT FOUND",
                "perm_name": perm.name if perm else "NOT FOUND",
            })
    
    return {
        "user_id": user.id,
        "user_role_field": user.role,
        "organization_id": user.organization_id,
        "user_roles": role_details,
        "permission_codes_from_helper": sorted(codes),
        "all_role_permissions": all_perms,
    }


@router.post("/forgot-password", response_model=Message)
async def forgot_password(payload: ForgotPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    await auth_service.forgot_password(db, payload.email, ip_address=get_client_ip(request))
    await db.commit()
    return Message(message="If that email exists, a reset link has been sent.")


@router.post("/reset-password", response_model=Message)
async def reset_password(payload: ResetPasswordRequest, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        await auth_service.reset_password(db, payload.token, payload.new_password, ip_address=get_client_ip(request))
    except AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    await db.commit()
    return Message(message="Password has been reset.")


@router.post("/change-password", response_model=Message)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    try:
        await auth_service.change_password(
            db,
            user=user,
            current_password=payload.current_password,
            new_password=payload.new_password,
            ip_address=get_client_ip(request),
        )
    except AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    await db.commit()
    return Message(message="Password changed.")


@router.post("/verify-email", response_model=Message)
async def verify_email(payload: VerifyEmailRequest, db: AsyncSession = Depends(get_db)):
    try:
        await auth_service.verify_email(db, payload.token)
    except AuthError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    await db.commit()
    return Message(message="Email verified.")


@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session)
        .where(
            Session.user_id == user.id,
            Session.organization_id == user.organization_id,
            Session.revoked_at.is_(None),
            Session.expires_at > utcnow(),
        )
        .order_by(Session.last_activity_at.desc())
    )
    return [SessionOut.model_validate(s) for s in result.scalars().all()]


@router.delete("/sessions/{session_id}", response_model=Message)
async def revoke_session(
    session_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(Session, session_id)
    if session is None or session.user_id != user.id or session.organization_id != user.organization_id:
        raise HTTPException(404, "Session not found")
    session.revoked_at = utcnow()
    await audit_service.log(
        db,
        organization_id=user.organization_id,
        action="auth.session.revoked",
        actor_id=user.id,
        actor_email=user.email,
        resource_type="session",
        resource_id=session.id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
    return Message(message="Session revoked")


@router.delete("/sessions", response_model=Message)
async def revoke_all_sessions(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await auth_service.logout(db, user=user, all_devices=True, ip_address=get_client_ip(request))
    await db.commit()
    return Message(message="All sessions revoked")
