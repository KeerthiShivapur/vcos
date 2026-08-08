"""Contacts API (Phase 12 — Customers, CRM & External Relationships)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.customers.contact_service import contact_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.post("")
async def create_contact(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    customer_id = payload.pop("customer_id", None)
    if not customer_id:
        raise HTTPException(status_code=400, detail="customer_id is required")
    try:
        contact = await contact_service.create(
            db, organization_id=org.id, customer_id=customer_id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if contact is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"id": contact.id, "name": contact.name}


@router.get("")
async def list_contacts(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    customer_id: Optional[str] = Query(None),
    decision_maker: Optional[bool] = Query(None),
    search: Optional[str] = Query(None),
):
    if customer_id:
        return await contact_service.list_by_customer(
            db, organization_id=org.id, customer_id=customer_id, search=search)
    return await contact_service.list_all(
        db, organization_id=org.id, search=search, customer_id=customer_id,
        decision_maker=decision_maker,
    )


@router.patch("/{contact_id}")
async def update_contact(
    contact_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    contact = await contact_service.update(db, organization_id=org.id, contact_id=contact_id, data=payload)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.commit()
    return {"id": contact.id, "name": contact.name}


@router.delete("/{contact_id}")
async def delete_contact(
    contact_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await contact_service.delete(db, organization_id=org.id, contact_id=contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.commit()
    return {"deleted": True}
