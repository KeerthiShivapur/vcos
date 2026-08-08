"""Account teams API (Phase 12 — Customers, CRM & External Relationships)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.customers.account_service import account_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/accounts", tags=["Account Teams"])


@router.get("/{customer_id}/team")
async def list_team(
    customer_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await account_service.list_team(db, organization_id=org.id, customer_id=customer_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{customer_id}/team")
async def add_member(
    customer_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        member = await account_service.add_member(
            db, organization_id=org.id, customer_id=customer_id, data={**payload, "actor_id": user.id})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if member is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return member


@router.delete("/{customer_id}/team/{member_id}")
async def remove_member(
    customer_id: str, member_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await account_service.remove_member(
            db, organization_id=org.id, customer_id=customer_id, member_id=member_id):
        raise HTTPException(status_code=404, detail="Team member not found")
    await db.commit()
    return {"deleted": True}
