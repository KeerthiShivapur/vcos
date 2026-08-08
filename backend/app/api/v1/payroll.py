"""Payroll integration API (Phase 11.10 — Payroll Integration).

References to external payroll providers (SAP / Oracle / Workday / ADP /
Gusto / local) and payroll run records. VCOS never computes salary — it
hands a payload to the provider and tracks the external reference.
"""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.db.database import get_db
from app.hr.payroll_service import payroll_service
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/payroll", tags=["HR Payroll"])


@router.post("/providers")
async def create_provider(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("payroll:manage")),
    db: AsyncSession = Depends(get_db),
):
    provider = await payroll_service.create_provider(db, organization_id=org.id, data=payload)
    await db.commit()
    return {"id": provider.id, "name": provider.name, "provider": provider.provider}


@router.get("/providers")
async def list_providers(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("payroll:read")),
    db: AsyncSession = Depends(get_db),
    active_only: bool = Query(False),
):
    providers = await payroll_service.list_providers(db, organization_id=org.id, active_only=active_only)
    return [
        {
            "id": provider.id,
            "name": provider.name,
            "provider": provider.provider,
            "is_active": provider.is_active,
        }
        for provider in providers
    ]


@router.patch("/providers/{provider_id}")
async def update_provider(
    provider_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("payroll:manage")),
    db: AsyncSession = Depends(get_db),
):
    provider = await payroll_service.update_provider(db, organization_id=org.id, provider_id=provider_id, data=payload)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    await db.commit()
    return {"id": provider.id, "is_active": provider.is_active}


@router.post("/runs")
async def create_run(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("payroll:manage")),
    db: AsyncSession = Depends(get_db),
):
    run = await payroll_service.create_run(db, organization_id=org.id, data=payload)
    await db.commit()
    return {"id": run.id, "status": run.status, "reference_id": run.reference_id}


@router.post("/runs/{run_id}/synced")
async def mark_synced(
    run_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("payroll:manage")),
    db: AsyncSession = Depends(get_db),
):
    run = await payroll_service.mark_synced(
        db, organization_id=org.id, run_id=run_id, reference_id=payload.get("reference_id")
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    await db.commit()
    return {"id": run.id, "status": run.status}


@router.post("/runs/{run_id}/failed")
async def mark_failed(
    run_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("payroll:manage")),
    db: AsyncSession = Depends(get_db),
):
    run = await payroll_service.mark_failed(db, organization_id=org.id, run_id=run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Payroll run not found")
    await db.commit()
    return {"id": run.id, "status": run.status}


@router.get("/runs")
async def list_runs(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("payroll:read")),
    db: AsyncSession = Depends(get_db),
    provider_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    return await payroll_service.list_runs(
        db, organization_id=org.id, provider_id=provider_id, status=status, limit=limit
    )


@router.get("/overview")
async def payroll_overview(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("payroll:read")),
    db: AsyncSession = Depends(get_db),
):
    return await payroll_service.overview(db, organization_id=org.id)
