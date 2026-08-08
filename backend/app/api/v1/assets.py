"""Assets API (Phase 11.8 — Assets & Equipment)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.asset_service import asset_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/assets", tags=["HR Assets"])


@router.post("")
async def create_asset(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    payload = dict(payload)
    payload["assigned_by"] = user.id
    asset = await asset_service.create_asset(db, organization_id=org.id, data=payload)
    await db.commit()
    return {"id": asset.id, "name": asset.name, "status": asset.status}


@router.get("")
async def list_assets(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
    employee_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
):
    return await asset_service.list_assets(
        db, organization_id=org.id, employee_id=employee_id, status=status, category=category
    )


@router.post("/{asset_id}/assign")
async def assign_asset(
    asset_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    asset = await asset_service.assign(
        db, organization_id=org.id, asset_id=asset_id,
        employee_id=payload.get("employee_id"), assigned_by=user.id,
    )
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found or not assignable")
    await db.commit()
    return {"id": asset.id, "status": asset.status, "employee_id": asset.employee_id}


@router.post("/{asset_id}/status")
async def update_asset_status(
    asset_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        asset = await asset_service.update_status(
            db, organization_id=org.id, asset_id=asset_id,
            status=payload.get("status", "available"), notes=payload.get("notes"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    await db.commit()
    return {"id": asset.id, "status": asset.status}


@router.get("/summary")
async def asset_summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("hr:read")),
    db: AsyncSession = Depends(get_db),
):
    return await asset_service.summary(db, organization_id=org.id)
