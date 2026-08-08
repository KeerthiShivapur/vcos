"""Customer Portal API (Phase 12 — Secure External Access).

Portal users are external identities scoped to a single customer. They
authenticate with email + password and receive a `portal`-type JWT. Every
portal endpoint resolves the token to a PortalUser and can only access that
user's customer data — hard customer-level isolation.
"""

from typing import Any

import jwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import bearer_scheme, require_permission
from app.core.security import PORTAL, create_portal_token, decode_token
from app.customers.portal_service import portal_service
from app.db.database import get_db
from app.models.portal import PortalUser

router = APIRouter(prefix="/portal", tags=["Customer Portal"])

_missing = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


async def get_portal_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> PortalUser:
    if credentials is None:
        raise _missing
    try:
        payload = decode_token(credentials.credentials, PORTAL)
    except jwt.PyJWTError as exc:
        raise _missing from exc
    user = await db.get(PortalUser, payload.get("sub"))
    if user is None or user.status != "active":
        raise _missing
    return user


@router.post("/auth/login")
async def portal_login(payload: dict[str, Any], db: AsyncSession = Depends(get_db)):
    email = (payload.get("email") or "").strip().lower()
    password = payload.get("password") or ""
    user = await portal_service.authenticate(db, email=email, password=password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_portal_token(user.id, user.organization_id)
    await db.commit()
    return {
        "access_token": token,
        "token_type": "bearer",
        "portal_user": {
            "id": user.id, "email": user.email, "full_name": user.full_name,
            "portal_role": user.portal_role,
        },
    }


@router.get("/me")
async def portal_me(user: PortalUser = Depends(get_portal_user)):
    return {
        "id": user.id, "customer_id": user.customer_id, "email": user.email,
        "full_name": user.full_name, "portal_role": user.portal_role,
    }


@router.get("/customer")
async def portal_customer(
    user: PortalUser = Depends(get_portal_user),
    db: AsyncSession = Depends(get_db),
):
    data = await portal_service.customer_data(db, organization_id=user.organization_id, portal_user_id=user.id)
    if data is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return data


@router.get("/tickets")
async def portal_tickets(
    user: PortalUser = Depends(get_portal_user),
    db: AsyncSession = Depends(get_db),
):
    return await portal_service.tickets(db, organization_id=user.organization_id, portal_user_id=user.id)


@router.post("/tickets")
async def portal_raise_ticket(
    payload: dict[str, Any],
    user: PortalUser = Depends(get_portal_user),
    db: AsyncSession = Depends(get_db),
):
    ticket = await portal_service.raise_ticket(
        db, organization_id=user.organization_id, portal_user_id=user.id, data=payload)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return ticket


@router.get("/contracts")
async def portal_contracts(
    user: PortalUser = Depends(get_portal_user),
    db: AsyncSession = Depends(get_db),
):
    return await portal_service.contracts(db, organization_id=user.organization_id, portal_user_id=user.id)


# ------------------------------------------------------------------ admin (internal team manages portal users)

@router.post("/users")
async def create_portal_user(
    payload: dict[str, Any],
    user: PortalUser = Depends(get_portal_user),
    db: AsyncSession = Depends(get_db),
):
    """Only customer_admin portal users can invite additional portal users."""
    if user.portal_role != "customer_admin":
        raise HTTPException(status_code=403, detail="Requires customer_admin role")
    try:
        created = await portal_service.create_user(
            db, organization_id=user.organization_id, customer_id=user.customer_id,
            data=payload, actor_id=None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if created is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"id": created.id, "email": created.email, "portal_role": created.portal_role}


# ------------------------------------------------------------------ admin (internal team)

@router.post("/admin/users")
async def admin_create_portal_user(
    payload: dict[str, Any],
    user: Any = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    """Internal team creates portal access for a customer."""
    from app.api.deps import get_current_organization
    from app.models.organization import Organization

    org: Organization = await get_current_organization(user=user, db=db)
    try:
        created = await portal_service.create_user(
            db, organization_id=org.id, customer_id=payload.get("customer_id", ""),
            data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if created is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"id": created.id, "email": created.email, "portal_role": created.portal_role}


@router.get("/admin/users")
async def admin_list_portal_users(
    customer_id: str,
    user: Any = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    from app.api.deps import get_current_organization
    from app.models.organization import Organization

    org: Organization = await get_current_organization(user=user, db=db)
    return await portal_service.list_users(db, organization_id=org.id, customer_id=customer_id)


@router.patch("/admin/users/{portal_user_id}")
async def admin_update_portal_user(
    portal_user_id: str,
    payload: dict[str, Any],
    user: Any = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.api.deps import get_current_organization
    from app.models.organization import Organization

    org: Organization = await get_current_organization(user=user, db=db)
    updated = await portal_service.update_user(
        db, organization_id=org.id, portal_user_id=portal_user_id, data=payload)
    if updated is None:
        raise HTTPException(status_code=404, detail="Portal user not found")
    await db.commit()
    return {"id": updated.id, "status": updated.status}


@router.delete("/admin/users/{portal_user_id}")
async def admin_delete_portal_user(
    portal_user_id: str,
    user: Any = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    from app.api.deps import get_current_organization
    from app.models.organization import Organization

    org: Organization = await get_current_organization(user=user, db=db)
    if not await portal_service.delete_user(db, organization_id=org.id, portal_user_id=portal_user_id):
        raise HTTPException(status_code=404, detail="Portal user not found")
    await db.commit()
    return {"deleted": True}
