"""Leads API (Phase 12 — Customers, CRM & External Relationships)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.customers.lead_service import lead_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/leads", tags=["Leads"])


@router.post("")
async def create_lead(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        lead = await lead_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": lead.id, "company_name": lead.company_name, "score": lead.score, "duplicate_of": lead.duplicate_of}


@router.get("")
async def list_leads(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    owner_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    return await lead_service.list_leads(
        db, organization_id=org.id, status=status, source=source, owner_id=owner_id, search=search)


@router.get("/{lead_id}")
async def get_lead(
    lead_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.get(db, organization_id=org.id, lead_id=lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    return lead_service._dict(lead)


@router.patch("/{lead_id}")
async def update_lead(
    lead_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    lead = await lead_service.update(db, organization_id=org.id, lead_id=lead_id, data=payload, actor_id=user.id)
    if lead is None:
        raise HTTPException(status_code=404, detail="Lead not found")
    await db.commit()
    return {"id": lead.id, "status": lead.status, "score": lead.score}


@router.delete("/{lead_id}")
async def delete_lead(
    lead_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await lead_service.delete(db, organization_id=org.id, lead_id=lead_id):
        raise HTTPException(status_code=404, detail="Lead not found")
    await db.commit()
    return {"deleted": True}


@router.get("/{lead_id}/activities")
async def lead_activities(
    lead_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await lead_service.activities(db, organization_id=org.id, lead_id=lead_id)


@router.post("/{lead_id}/activities")
async def add_lead_activity(
    lead_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    ok = await lead_service.add_activity(
        db, organization_id=org.id, lead_id=lead_id,
        kind=payload.get("kind", "noted"), content=payload.get("content"), actor_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Lead not found")
    await db.commit()
    return {"added": True}
