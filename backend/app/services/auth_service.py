"""Authentication service: register, login, refresh, sessions, invitations."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.timeutils import is_expired, utcnow
from app.core.security import (
    ACCESS,
    EMAIL_VERIFY,
    INVITE,
    PASSWORD_RESET,
    REFRESH,
    create_access_token,
    create_email_verification_token,
    create_invite_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.invitation import Invitation, PasswordReset
from app.models.organization import Organization
from app.models.role import UserRoleModel
from app.models.user import Session, User
from app.models.workspace import Workspace
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.audit_service import audit_service
from app.services.email_service import email_service, hash_token
from app.services.event_service import event_service
from app.services.notification_service import notification_service
from app.services.permission_service import permission_service

logger = logging.getLogger("vcos.auth")


class AuthError(Exception):
    def __init__(self, message: str, code: str = "auth_error", status: int = 400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_device(user_agent: Optional[str], device_name: Optional[str]) -> dict[str, str]:
    """Best-effort device/browser/OS extraction from the User-Agent header."""
    ua = user_agent or ""
    os_name = "Unknown"
    if "Windows" in ua:
        os_name = "Windows"
    elif "Mac OS X" in ua or "Macintosh" in ua:
        os_name = "macOS"
    elif "Linux" in ua:
        os_name = "Linux"
    elif "Android" in ua:
        os_name = "Android"
    elif "iPhone" in ua or "iPad" in ua:
        os_name = "iOS"

    browser = "Unknown"
    lower = ua.lower()
    if "edg/" in lower:
        browser = "Edge"
    elif "chrome/" in lower:
        browser = "Chrome"
    elif "safari/" in lower and "chromium" not in lower:
        browser = "Safari"
    elif "firefox/" in lower:
        browser = "Firefox"
    elif "postman" in lower:
        browser = "Postman"
    elif "python-httpx" in lower or "python-requests" in lower:
        browser = "API Client"

    device_type = "desktop"
    if "mobile" in lower or os_name in ("Android", "iOS"):
        device_type = "mobile"

    return {
        "os": os_name,
        "browser": browser,
        "device_type": device_type,
        "device_name": device_name or f"{os_name} · {browser}",
    }


def _public_frontend_url() -> str:
    """Frontend base for links (used for invite/verification URLs in dev)."""
    settings = get_settings()
    return "http://localhost:3000"


class AuthService:
    async def register_organization(
        self,
        db: AsyncSession,
        payload: RegisterRequest,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        existing = await db.execute(select(User.email).where(User.email == payload.email))
        if existing.scalars().first():
            raise AuthError("An account with this email already exists.", "email_taken", 409)

        from app.services.organization_service import organization_service

        created = await organization_service.create_organization_and_owner(
            db, payload=payload, ip_address=ip_address, user_agent=user_agent
        )
        org: Organization = created["organization"]
        owner: User = created["owner"]

        session = await self._create_session(
            db,
            user=owner,
            organization_id=org.id,
            remember_me=False,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await audit_service.log(
            db,
            organization_id=org.id,
            action="auth.login",
            actor_id=owner.id,
            actor_email=owner.email,
            resource_type="session",
            resource_id=session.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"session_id": session.id, "source": "register"},
        )
        await notification_service.create(
            db,
            organization_id=org.id,
            recipient_id=owner.id,
            type="system",
            title="Welcome to VCOS",
            body=f"Your organization {org.name} is ready. This is the beginning of your company operating system.",
            priority="high",
            link="/home",
        )
        await event_service.emit(
            db,
            name="user.login",
            actor_id=owner.id,
            organization_id=org.id,
            payload={"session_id": session.id, "source": "register"},
        )
        await db.flush()
        return {
            "user": owner,
            "organization": org,
            "session": session,
        }

    async def login(
        self,
        db: AsyncSession,
        payload: LoginRequest,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        candidates = (
            await db.execute(
                select(User).where(User.email == payload.email).order_by(User.created_at)
            )
        ).scalars().all()
        if not candidates:
            raise AuthError("Invalid email or password.", "invalid_credentials", 401)
        if len(candidates) == 1:
            user = candidates[0]
        else:
            matching = [
                c for c in candidates if verify_password(payload.password, c.hashed_password)
            ]
            if len(matching) != 1:
                raise AuthError("Invalid email or password.", "invalid_credentials", 401)
            user = matching[0]

        if user.locked_until and not is_expired(user.locked_until):
            raise AuthError("Account temporarily locked due to failed attempts.", "account_locked", 423)

        if not verify_password(payload.password, user.hashed_password):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            settings = get_settings()
            if user.failed_login_attempts >= settings.LOGIN_MAX_ATTEMPTS:
                user.locked_until = _now() + timedelta(minutes=settings.LOGIN_LOCKOUT_MINUTES)
                user.failed_login_attempts = 0
                await audit_service.log(
                    db,
                    organization_id=user.organization_id,
                    action="auth.login.failed",
                    actor_id=user.id,
                    actor_email=user.email,
                    details={"reason": "account_locked", "ip": ip_address},
                    severity="warning",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            else:
                await audit_service.log(
                    db,
                    organization_id=user.organization_id,
                    action="auth.login.failed",
                    actor_id=user.id,
                    actor_email=user.email,
                    details={"attempt": user.failed_login_attempts},
                    severity="warning",
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            await db.flush()
            raise AuthError("Invalid email or password.", "invalid_credentials", 401)

        if user.status == "suspended":
            raise AuthError("This account has been suspended.", "account_suspended", 403)
        if user.status == "deactivated":
            raise AuthError("This account has been deactivated.", "account_deactivated", 403)

        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = _now()
        user.last_login_ip = ip_address

        session = await self._create_session(
            db,
            user=user,
            organization_id=user.organization_id,
            remember_me=payload.remember_me,
            ip_address=ip_address,
            user_agent=user_agent,
            device_name=payload.device_name,
        )

        await audit_service.log(
            db,
            organization_id=user.organization_id,
            action="auth.login",
            actor_id=user.id,
            actor_email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"session_id": session.id, "device": session.device_name},
        )
        await event_service.emit(
            db,
            name="user.login",
            actor_id=user.id,
            organization_id=user.organization_id,
            payload={"session_id": session.id},
        )
        org = await db.get(Organization, user.organization_id)
        await db.flush()
        return {"user": user, "organization": org, "session": session}

    async def refresh(
        self,
        db: AsyncSession,
        refresh_token: str,
        *,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        try:
            payload = decode_token(refresh_token, REFRESH)
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid refresh token.", "invalid_refresh_token", 401) from exc
        session = await db.get(Session, payload.get("sid"))
        if session is None or session.revoked_at is not None or is_expired(session.expires_at):
            raise AuthError("Session is no longer valid.", "session_expired", 401)
        if session.user_id != payload.get("sub"):
            raise AuthError("Invalid session.", "invalid_session", 401)
        user = await db.get(User, session.user_id)
        if user is None or user.status != "active":
            raise AuthError("Account is not active.", "account_inactive", 403)
        session.last_activity_at = _now()
        await audit_service.log(
            db,
            organization_id=user.organization_id,
            action="auth.refresh",
            actor_id=user.id,
            actor_email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await db.flush()
        return {
            "access_token": create_access_token(user.id, user.organization_id),
            "expires_in": get_settings().ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            "user": user,
            "organization": await db.get(Organization, user.organization_id),
        }

    async def logout(
        self,
        db: AsyncSession,
        *,
        user: User,
        refresh_token: Optional[str] = None,
        all_devices: bool = False,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> None:
        now = _now()
        if all_devices:
            sessions = (
                await db.execute(
                    select(Session).where(
                        Session.user_id == user.id,
                        Session.revoked_at.is_(None),
                        Session.expires_at > now,
                    )
                )
            ).scalars().all()
            for s in sessions:
                s.revoked_at = now
            await audit_service.log(
                db,
                organization_id=user.organization_id,
                action="auth.logout.all",
                actor_id=user.id,
                actor_email=user.email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        else:
            if refresh_token:
                try:
                    payload = decode_token(refresh_token, REFRESH)
                    session = await db.get(Session, payload.get("sid"))
                    if session and session.user_id == user.id:
                        session.revoked_at = now
                except jwt.PyJWTError:
                    pass
            await audit_service.log(
                db,
                organization_id=user.organization_id,
                action="auth.logout",
                actor_id=user.id,
                actor_email=user.email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        await event_service.emit(
            db, name="user.logout", actor_id=user.id, organization_id=user.organization_id
        )
        await db.flush()

    async def _create_session(
        self,
        db: AsyncSession,
        *,
        user: User,
        organization_id: str,
        remember_me: bool,
        ip_address: Optional[str],
        user_agent: Optional[str],
        device_name: Optional[str] = None,
    ) -> Session:
        settings = get_settings()
        device = _parse_device(user_agent, device_name)
        now = _now()
        # Create a temporary session to get an ID for the refresh token
        session = Session(
            user_id=user.id,
            organization_id=organization_id,
            token_hash="pending",
            refresh_token_hash="pending",
            device_name=device["device_name"],
            device_type=device["device_type"],
            browser=device["browser"],
            os=device["os"],
            ip_address=ip_address,
            user_agent=(user_agent or "")[:500],
            expires_at=now + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
            last_activity_at=now,
            is_current=not remember_me,
        )
        db.add(session)
        await db.flush()
        # Now create the actual tokens with the session ID
        access_token = create_access_token(user.id, organization_id)
        refresh_token = create_refresh_token(user.id, organization_id, session.id)
        session.token_hash = hash_token(access_token)
        session.refresh_token_hash = hash_token(refresh_token)
        await db.flush()
        return session

    # ------------------------------------------------------------------ passwords
    async def forgot_password(self, db: AsyncSession, email: str, *, ip_address: Optional[str] = None) -> None:
        user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if user is None:
            return  # do not leak account existence
        settings = get_settings()
        token = create_password_reset_token(user.id, user.organization_id)
        db.add(
            PasswordReset(
                user_id=user.id,
                organization_id=user.organization_id,
                token_hash=hash_token(token),
                expires_at=_now() + timedelta(hours=settings.PASSWORD_RESET_TOKEN_EXPIRE_HOURS),
                ip_address=ip_address,
            )
        )
        reset_url = f"{_public_frontend_url()}/reset-password?token={token}"
        await email_service.send(
            to=email,
            subject="Reset your VCOS password",
            body=f"Hello {user.full_name},\n\nYou requested a password reset.\n\n{reset_url}\n\nIf you did not request this, you can ignore this email.",
        )
        await db.flush()

    async def reset_password(
        self,
        db: AsyncSession,
        token: str,
        new_password: str,
        *,
        ip_address: Optional[str] = None,
    ) -> None:
        try:
            payload = decode_token(token, PASSWORD_RESET)
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid or expired reset token.", "invalid_token", 400) from exc
        user = await db.get(User, payload.get("sub"))
        if user is None:
            raise AuthError("Invalid or expired reset token.", "invalid_token", 400)
        reset_row = (
            await db.execute(
                select(PasswordReset).where(
                    PasswordReset.token_hash == hash_token(token),
                    PasswordReset.user_id == user.id,
                    PasswordReset.used_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if reset_row is None:
            raise AuthError("Invalid or expired reset token.", "invalid_token", 400)
        reset_row.used_at = _now()
        user.password_hash = hash_password(new_password)
        user.failed_login_attempts = 0
        user.locked_until = None
        # Revoke all existing sessions for security.
        await db.execute(
            Session.__table__.update()
            .where(Session.user_id == user.id, Session.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await audit_service.log(
            db,
            organization_id=user.organization_id,
            action="auth.password.reset",
            actor_id=user.id,
            actor_email=user.email,
            ip_address=ip_address,
        )
        await event_service.emit(
            db, name="password.reset", actor_id=user.id, organization_id=user.organization_id
        )
        await db.flush()

    async def change_password(
        self,
        db: AsyncSession,
        *,
        user: User,
        current_password: str,
        new_password: str,
        ip_address: Optional[str] = None,
    ) -> None:
        if not verify_password(current_password, user.password_hash):
            await audit_service.log(
                db,
                organization_id=user.organization_id,
                action="auth.password.changed",
                actor_id=user.id,
                actor_email=user.email,
                outcome="failure",
                severity="warning",
                ip_address=ip_address,
            )
            raise AuthError("Current password is incorrect.", "wrong_password", 400)
        user.password_hash = hash_password(new_password)
        await audit_service.log(
            db,
            organization_id=user.organization_id,
            action="auth.password.changed",
            actor_id=user.id,
            actor_email=user.email,
            ip_address=ip_address,
        )
        await event_service.emit(
            db, name="password.changed", actor_id=user.id, organization_id=user.organization_id
        )
        await db.flush()

    async def verify_email(self, db: AsyncSession, token: str) -> User:
        try:
            payload = decode_token(token, EMAIL_VERIFY)
        except jwt.PyJWTError as exc:
            raise AuthError("Invalid or expired verification token.", "invalid_token", 400) from exc
        user = await db.get(User, payload.get("sub"))
        if user is None:
            raise AuthError("Invalid verification token.", "invalid_token", 400)
        if user.email_verified_at is None:
            user.email_verified_at = _now()
            await audit_service.log(
                db,
                organization_id=user.organization_id,
                action="auth.email.verified",
                actor_id=user.id,
                actor_email=user.email,
            )
            await event_service.emit(
                db, name="email.verified", actor_id=user.id, organization_id=user.organization_id
            )
            await db.flush()
        return user

# ------------------------------------------------------------------ invitations
    async def invite(
        self,
        db: AsyncSession,
        *,
        organization: Organization,
        inviter: User,
        email: str,
        full_name: Optional[str],
        role: str,
        message: Optional[str],
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        settings = get_settings()
        existing_user = (await db.execute(select(User).where(User.email == email, User.organization_id == organization.id))).scalar_one_or_none()
        if existing_user is not None:
            raise AuthError("This employee is already a member of the organization.", "already_member", 409)

        from app.models.invitation import Invitation

        pending = (
            await db.execute(
                select(Invitation).where(
                    Invitation.organization_id == organization.id,
                    Invitation.email == email,
                    Invitation.status == "pending",
                )
            )
        ).scalar_one_or_none()
        if pending is not None:
            raise AuthError("An invitation for this email is already pending.", "already_pending", 409)

        # Role can be an id (custom role) or a system role code.
        role_target: Optional[str] = None
        if len(role) == 32:
            from app.models.role import Role

            r = await db.get(Role, role)
            if r and r.organization_id == organization.id:
                role_target = r.id
        if role_target is None:
            from app.models.role import Role

            # Handle duplicate roles gracefully - use first() instead of scalar_one_or_none()
            r = (
                await db.execute(
                    select(Role).where(Role.organization_id == organization.id, Role.code == role)
                )
            ).scalars().first()
            role_target = r.id if r else None

        if role_target is None:
            raise AuthError("Invalid role.", "invalid_role", 400)

        # Assignment policy: an inviter cannot grant a role whose permissions
        # exceed their own effective permission set.
        from app.models.role import Permission, RolePermission

        target_perm_rows = await db.execute(
            select(Permission.code)
            .join(RolePermission, RolePermission.permission_id == Permission.id)
            .where(RolePermission.role_id == role_target)
        )
        target_perms = set(target_perm_rows.scalars().all())
        inviter_perms = await permission_service.user_permission_codes(
            db, user_id=inviter.id, organization_id=organization.id
        )
        if not target_perms.issubset(inviter_perms):
            raise AuthError(
                "You cannot invite someone into a role that grants permissions you do not have.",
                "role_not_allowed",
                403,
            )

        raw_token = create_invite_token()
        invitation = Invitation(
            organization_id=organization.id,
            invited_by=inviter.id,
            email=email,
            full_name=full_name,
            role=role_target,
            token_hash=hash_token(raw_token),
            token_expires_at=_now() + timedelta(days=7),
            message=message,
        )
        db.add(invitation)
        await db.flush()

        accept_url = f"{_public_frontend_url()}/register?invite={raw_token}"
        email_payload = await email_service.send(
            to=email,
            subject=f"You have been invited to join {organization.name} on VCOS",
            body=(
                f"Hello{(' ' + full_name) if full_name else ''},\n\n"
                f"{inviter.full_name} invited you to join {organization.name} on VCOS.\n\n"
                f"Complete your account setup here:\n{accept_url}\n\n"
                f"This invitation expires in 7 days."
            ),
        )

        await audit_service.log(
            db,
            organization_id=organization.id,
            action="user.invited",
            actor_id=inviter.id,
            actor_email=inviter.email,
            resource_type="invitation",
            resource_id=invitation.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"email": email, "role": role_target},
        )
        await event_service.emit(
            db,
            name="user.invited",
            actor_id=inviter.id,
            organization_id=organization.id,
            payload={"invitation_id": invitation.id, "email": email},
        )
        await notification_service.create(
            db,
            organization_id=organization.id,
            recipient_id=inviter.id,
            type="system",
            title="Invitation sent",
            body=f"Invitation sent to {email}.",
            priority="normal",
            link="/settings",
        )
        await db.flush()
        return {
            "invitation": invitation,
            "url": accept_url,
            "token": raw_token if email_payload.get("transport") == "console" else None,
        }

    async def resend_invitation(
        self,
        db: AsyncSession,
        *,
        organization: Organization,
        actor: User,
        invitation_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        invitation = await db.get(Invitation, invitation_id)
        if invitation is None or invitation.organization_id != organization.id:
            raise AuthError("Invitation not found.", "invitation_not_found", 404)
        if invitation.status not in ("pending", "expired"):
            raise AuthError("Only pending invitations can be resent.", "invitation_not_resendable", 400)

        existing_user = (
            await db.execute(
                select(User).where(User.email == invitation.email, User.organization_id == organization.id)
            )
        ).scalar_one_or_none()
        if existing_user is not None:
            raise AuthError("This email is already a member of the organization.", "already_member", 409)

        raw_token = create_invite_token()
        invitation.token_hash = hash_token(raw_token)
        invitation.token_expires_at = _now() + timedelta(days=7)
        invitation.status = "pending"
        invitation.accepted_at = None
        await db.flush()

        accept_url = f"{_public_frontend_url()}/register?invite={raw_token}"
        email_payload = await email_service.send(
            to=invitation.email,
            subject=f"You have been invited to join {organization.name} on VCOS",
            body=(
                f"Hello{(' ' + invitation.full_name) if invitation.full_name else ''},\n\n"
                f"{actor.full_name} re-sent an invitation to join {organization.name} on VCOS.\n\n"
                f"Complete your account setup here:\n{accept_url}\n\n"
                f"This invitation expires in 7 days."
            ),
        )

        await audit_service.log(
            db,
            organization_id=organization.id,
            action="invitation.resent",
            actor_id=actor.id,
            actor_email=actor.email,
            resource_type="invitation",
            resource_id=invitation.id,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"email": invitation.email},
        )
        await event_service.emit(
            db,
            name="invitation.resent",
            actor_id=actor.id,
            organization_id=organization.id,
            payload={"invitation_id": invitation.id, "email": invitation.email},
        )
        await notification_service.create(
            db,
            organization_id=organization.id,
            recipient_id=actor.id,
            type="system",
            title="Invitation re-sent",
            body=f"Invitation re-sent to {invitation.email}.",
            priority="normal",
            link="/settings",
        )
        await db.flush()
        return {
            "invitation": invitation,
            "url": accept_url,
            "token": raw_token if email_payload.get("transport") == "console" else None,
        }

    async def register_from_invitation(
        self,
        db: AsyncSession,
        *,
        token: str,
        full_name: str,
        username: Optional[str],
        password: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> dict[str, Any]:
        invitation = (
            await db.execute(
                select(Invitation).where(Invitation.token_hash == hash_token(token))
            )
        ).scalar_one_or_none()
        if invitation is None:
            raise AuthError("Invitation is invalid.", "invalid_invitation", 400)
        if invitation.status != "pending":
            raise AuthError("Invitation has already been used.", "invitation_used", 400)
        if is_expired(invitation.token_expires_at):
            raise AuthError("Invitation has expired.", "invitation_expired", 400)

        existing = (
            await db.execute(
                select(User).where(User.email == invitation.email, User.organization_id == invitation.organization_id)
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise AuthError("This email is already registered in the organization.", "already_member", 409)

        from app.models.role import Role

        role = await db.get(Role, invitation.role)
        role_code = role.code if role else "employee"

        user = User(
            organization_id=invitation.organization_id,
            email=invitation.email,
            username=username,
            full_name=full_name,
            password_hash=hash_password(password),
            status="active",
            role=role_code,
            email_verified_at=_now(),
        )
        db.add(user)
        await db.flush()
        db.add(UserRoleModel(user_id=user.id, role_id=invitation.role, organization_id=invitation.organization_id))
        db.add(Workspace(organization_id=invitation.organization_id, user_id=user.id))

        invitation.status = "accepted"
        invitation.accepted_at = _now()

        from app.people.employee_service import employee_service

        await employee_service.create_for_user(
            db,
            organization_id=user.organization_id,
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
            designation=None,
        )

        org = await db.get(Organization, invitation.organization_id)
        session = await self._create_session(
            db,
            user=user,
            organization_id=user.organization_id,
            remember_me=False,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await audit_service.log(
            db,
            organization_id=user.organization_id,
            action="auth.login",
            actor_id=user.id,
            actor_email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            details={"session_id": session.id, "source": "invitation"},
        )
        await notification_service.create(
            db,
            organization_id=user.organization_id,
            recipient_id=user.id,
            type="system",
            title=f"Welcome to {org.name if org else 'VCOS'}",
            body="Your workspace is ready. Set your profile and start working.",
            priority="high",
            link="/home",
        )
        await audit_service.log(
            db,
            organization_id=user.organization_id,
            action="invitation.accepted",
            actor_id=user.id,
            actor_email=user.email,
            resource_type="invitation",
            resource_id=invitation.id,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        await event_service.emit(
            db,
            name="user.created",
            actor_id=user.id,
            organization_id=user.organization_id,
            payload={"user_id": user.id, "source": "invitation"},
        )
        await event_service.emit(
            db,
            name="user.login",
            actor_id=user.id,
            organization_id=user.organization_id,
            payload={"session_id": session.id, "source": "invitation"},
        )
        await db.flush()
        return {"user": user, "organization": org, "session": session}


auth_service = AuthService()
