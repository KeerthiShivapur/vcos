"""Shared FastAPI dependencies: auth, tenant isolation, RBAC enforcement."""

from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import ACCESS, decode_token
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User
from app.services.permission_service import permission_service

bearer_scheme = HTTPBearer(auto_error=False)

_missing = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def get_client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
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


async def get_current_organization(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organization:
    org = await db.get(Organization, user.organization_id)
    if org is None or org.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Organization is not active")
    return org


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
        codes = await permission_service.user_permission_codes(db, user.id, user.organization_id)
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
    return RequirePermission(code)


def get_settings_dep():
    return get_settings()
