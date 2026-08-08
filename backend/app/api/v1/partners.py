"""Partners & Vendors API (Phase 12 — Customers, CRM & External Relationships)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.customers.partner_service import partner_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/partners", tags=["Partners"])


@router.post("")
async def create_partner(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        partner = await partner_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": partner.id, "name": partner.name, "kind": partner.kind}


@router.get("")
async def list_partners(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    kind: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    return await partner_service.list_partners(
        db, organization_id=org.id, kind=kind, status=status, search=search)


@router.get("/summary")
async def summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await partner_service.summary(db, organization_id=org.id)


@router.get("/{partner_id}")
async def get_partner(
    partner_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    partner = await partner_service.get(db, organization_id=org.id, partner_id=partner_id)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    return partner_service._dict(partner)


@router.patch("/{partner_id}")
async def update_partner(
    partner_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    partner = await partner_service.update(db, organization_id=org.id, partner_id=partner_id, data=payload)
    if partner is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    await db.commit()
    return {"id": partner.id, "name": partner.name}


@router.delete("/{partner_id}")
async def delete_partner(
    partner_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await partner_service.delete(db, organization_id=org.id, partner_id=partner_id):
        raise HTTPException(status_code=404, detail="Partner not found")
    await db.commit()
    return {"deleted": True}


@router.get("/{partner_id}/contacts")
async def list_contacts(
    partner_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await partner_service.list_contacts(db, organization_id=org.id, partner_id=partner_id)


@router.post("/{partner_id}/contacts")
async def add_contact(
    partner_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    contact = await partner_service.add_contact(
        db, organization_id=org.id, partner_id=partner_id, data=payload)
    if contact is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    await db.commit()
    return {"id": contact.id, "name": contact.name}


@router.delete("/{partner_id}/contacts/{contact_id}")
async def delete_contact(
    partner_id: str, contact_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await partner_service.delete_contact(
            db, organization_id=org.id, partner_id=partner_id, contact_id=contact_id):
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.commit()
    return {"deleted": True}


@router.get("/{partner_id}/contracts")
async def list_contract_links(
    partner_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await partner_service.list_contract_links(db, organization_id=org.id, partner_id=partner_id)


@router.post("/{partner_id}/contracts")
async def link_contract(
    partner_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    link = await partner_service.link_contract(
        db, organization_id=org.id, partner_id=partner_id, contract_id=payload.get("contract_id", ""))
    if link is None:
        raise HTTPException(status_code=404, detail="Partner not found")
    await db.commit()
    return {"id": link.id, "contract_id": link.contract_id}
