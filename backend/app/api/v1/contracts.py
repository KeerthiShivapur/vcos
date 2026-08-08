"""Contracts API (Phase 12 — Customers, CRM & External Relationships)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.customers.contract_service import contract_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/contracts", tags=["Contracts"])


@router.post("")
async def create_contract(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        contract = await contract_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": contract.id, "title": contract.title, "status": contract.status}


@router.get("")
async def list_contracts(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    contract_type: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    expiring_soon: bool = Query(False),
    search: Optional[str] = Query(None),
):
    return await contract_service.list_contracts(
        db, organization_id=org.id, status=status, contract_type=contract_type,
        customer_id=customer_id, expiring_soon=expiring_soon, search=search)


@router.get("/renewals")
async def list_renewals(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    contract_id: Optional[str] = Query(None),
):
    return await contract_service.list_renewals(
        db, organization_id=org.id, status=status, contract_id=contract_id)


@router.get("/{contract_id}")
async def get_contract(
    contract_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    contract = await contract_service.get(db, organization_id=org.id, contract_id=contract_id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract_service._dict(contract)


@router.patch("/{contract_id}")
async def update_contract(
    contract_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    contract = await contract_service.update(
        db, organization_id=org.id, contract_id=contract_id, data=payload, actor_id=user.id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    await db.commit()
    return {"id": contract.id, "status": contract.status, "approval_status": contract.approval_status}


@router.post("/{contract_id}/sign")
async def sign_contract(
    contract_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    contract = await contract_service.sign(
        db, organization_id=org.id, contract_id=contract_id,
        signed_by=payload.get("signed_by") or user.email, actor_id=user.id)
    if contract is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    await db.commit()
    return {"id": contract.id, "status": contract.status, "signed_at": contract.signed_at.isoformat()}


@router.delete("/{contract_id}")
async def delete_contract(
    contract_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await contract_service.delete(db, organization_id=org.id, contract_id=contract_id):
        raise HTTPException(status_code=404, detail="Contract not found")
    await db.commit()
    return {"deleted": True}


# ------------------------------------------------------------------ versions

@router.post("/{contract_id}/versions")
async def new_version(
    contract_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    entry = await contract_service.new_version(
        db, organization_id=org.id, contract_id=contract_id,
        version=payload.get("version", "next"), change_note=payload.get("change_note"),
        editor_id=user.id, snapshot=payload.get("snapshot"))
    if entry is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    await db.commit()
    return {"id": entry.id, "version": entry.version}


@router.get("/{contract_id}/versions")
async def versions(
    contract_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await contract_service.versions(db, organization_id=org.id, contract_id=contract_id)


# ------------------------------------------------------------------ renewals

@router.post("/{contract_id}/renewals")
async def plan_renewal(
    contract_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    renewal = await contract_service.plan_renewal(
        db, organization_id=org.id, contract_id=contract_id, data=payload, actor_id=user.id)
    if renewal is None:
        raise HTTPException(status_code=404, detail="Contract not found")
    await db.commit()
    return {"id": renewal.id, "status": renewal.status}


@router.patch("/renewals/{renewal_id}")
async def update_renewal(
    renewal_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    renewal = await contract_service.update_renewal(
        db, organization_id=org.id, renewal_id=renewal_id, data=payload, actor_id=user.id)
    if renewal is None:
        raise HTTPException(status_code=404, detail="Renewal not found")
    await db.commit()
    return {"id": renewal.id, "status": renewal.status}


@router.delete("/renewals/{renewal_id}")
async def delete_renewal(
    renewal_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await contract_service.delete_renewal(db, organization_id=org.id, renewal_id=renewal_id):
        raise HTTPException(status_code=404, detail="Renewal not found")
    await db.commit()
    return {"deleted": True}
