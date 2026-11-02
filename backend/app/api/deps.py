"""Shared FastAPI dependencies: auth, tenant isolation, RBAC enforcement.

This module provides FastAPI dependency injection for authentication,
authorization, and tenant isolation.
"""

from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Query, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import ACCESS, decode_token
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.services.permission_service import permission_service

bearer_scheme = HTTPBearer(auto_error=False)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

_missing = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def get_client_ip(request: Request) -> Optional[str]:
    """Extract client IP from request."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Get current authenticated user from JWT token."""
    if credentials is None:
        raise _missing
    try:
        payload = decode_token(credentials.credentials, ACCESS)
    except jwt.PyJWTError as exc:
        raise _missing from exc
    user = await db.get(User, payload.get("sub"))
    if user is None or user.status != "active":
        raise _missing
    return user


async def get_current_user_ws(
    token: str = Query(...),
    organization_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """Get current user for WebSocket connections."""
    try:
        payload = decode_token(token, ACCESS)
    except jwt.PyJWTError:
        return None
    user = await db.get(User, payload.get("sub"))
    if user is None or user.status != "active":
        return None
    if str(user.organization_id) != organization_id:
        return None
    return user


async def get_current_organization(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    """Get current organization from authenticated user."""
    org = await db.get(Organization, user.organization_id)
    if org is None or org.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is not active")

    # Set tenant context for RLS policies (PostgreSQL only)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name == "postgresql":
        await db.execute(
            text("SELECT set_config('app.current_organization_id', :org_id, false)"),
            {"org_id": str(org.id)},
        )
    return org


async def get_current_organization_ws(
    token: str = Query(...),
    organization_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
) -> Optional[Organization]:
    """Get current organization for WebSocket connections."""
    user = await get_current_user_ws(token, organization_id, db)
    if not user:
        return None
    
    result = await db.execute(
        select(Organization).where(Organization.id == organization_id)
    )
    org = result.scalar_one_or_none()
    
    if org and org.is_active:
        return org
    
    return None


async def get_current_user_id(
    user: User = Depends(get_current_user),
) -> str:
    """Extract user ID from current user."""
    return user.id


async def get_current_org_id(
    org: Organization = Depends(get_current_organization),
) -> str:
    """Extract organization ID from current organization."""
    return org.id


class RequirePermission:
    """RBAC dependency factory: require_permission("users:invite")."""
    
    def __init__(self, code: str):
        self.code = code

    async def __call__(
        self,
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_db),
        request: Request = None,
    ) -> User:
        codes = await permission_service.user_permission_codes(db, user.organization_id, user.id)
        if self.code not in codes:
            try:
                from app.services.audit_service import audit_service
                await audit_service.log(
                    db,
                    organization_id=user.organization_id,
                    action="authz.denied",
                    actor_id=user.id,
                    actor_email=user.email,
                    resource_type="permission",
                    resource_id=self.code,
                    ip_address=get_client_ip(request) if request is not None else None,
                    details={"permission": self.code},
                    severity="warning",
                    outcome="failure",
                )
            except Exception:
                pass
            try:
                await db.commit()
            except Exception:
                pass
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Missing permission: {self.code}",
            )
        return user


def require_permission(code: str) -> RequirePermission:
    """Create a permission dependency."""
    return RequirePermission(code)


def require_role(*roles: str):
    """Dependency to require specific role(s)."""
    async def role_checker(
        user: User = Depends(get_current_user),
    ) -> User:
        # TODO: Implement role checking logic
        return user
    return role_checker


def get_settings_dep():
    """Get settings dependency."""
    return get_settings()


# Explicit exports
__all__ = [
    "get_client_ip",
    "get_current_user",
    "get_current_user_ws",
    "get_current_organization",
    "get_current_organization_ws",
    "get_current_user_id",
    "get_current_org_id",
    "RequirePermission",
    "require_permission",
    "require_role",
    "get_settings_dep",
    "get_db",
    "oauth2_scheme",
    "bearer_scheme",
]