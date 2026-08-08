"""Opportunities API (Phase 12 — Customers, CRM & External Relationships)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.customers.opportunity_service import opportunity_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/opportunities", tags=["Opportunities"])


@router.post("")
async def create_opportunity(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        opportunity = await opportunity_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": opportunity.id, "title": opportunity.title, "stage": opportunity.stage}


@router.get("")
async def list_opportunities(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    stage: Optional[str] = Query(None),
    owner_id: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
):
    return await opportunity_service.list_opportunities(
        db, organization_id=org.id, stage=stage, owner_id=owner_id,
        customer_id=customer_id, search=search)


@router.get("/pipeline")
async def pipeline(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await opportunity_service.pipeline(db, organization_id=org.id)


@router.get("/{opportunity_id}")
async def get_opportunity(
    opportunity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    opportunity = await opportunity_service.get(db, organization_id=org.id, opportunity_id=opportunity_id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    return opportunity_service._dict(opportunity)


@router.patch("/{opportunity_id}")
async def update_opportunity(
    opportunity_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    opportunity = await opportunity_service.update(
        db, organization_id=org.id, opportunity_id=opportunity_id, data=payload, actor_id=user.id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    await db.commit()
    return {"id": opportunity.id, "stage": opportunity.stage, "probability": opportunity.probability}


@router.post("/{opportunity_id}/won")
async def close_won(
    opportunity_id: str,
    payload: dict[str, Any] = {},
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        result = await opportunity_service.close_won(
            db, organization_id=org.id, opportunity_id=opportunity_id,
            note=payload.get("note"), actor_id=user.id,
            create_customer=payload.get("create_customer", True),
            customer_data=payload.get("customer_data"))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await db.commit()
    return result


@router.post("/{opportunity_id}/lost")
async def close_lost(
    opportunity_id: str,
    payload: dict[str, Any] = {},
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    opportunity = await opportunity_service.close_lost(
        db, organization_id=org.id, opportunity_id=opportunity_id,
        reason=payload.get("reason"), actor_id=user.id)
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    await db.commit()
    return {"id": opportunity.id, "stage": "lost", "reason": opportunity.close_reason}


@router.delete("/{opportunity_id}")
async def delete_opportunity(
    opportunity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await opportunity_service.delete(db, organization_id=org.id, opportunity_id=opportunity_id):
        raise HTTPException(status_code=404, detail="Opportunity not found")
    await db.commit()
    return {"deleted": True}


@router.get("/{opportunity_id}/activities")
async def opportunity_activities(
    opportunity_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await opportunity_service.activities(db, organization_id=org.id, opportunity_id=opportunity_id)


@router.post("/{opportunity_id}/activities")
async def add_opportunity_activity(
    opportunity_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    ok = await opportunity_service.add_activity(
        db, organization_id=org.id, opportunity_id=opportunity_id,
        kind=payload.get("kind", "noted"), content=payload.get("content"), actor_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Opportunity not found")
    await db.commit()
    return {"added": True}
