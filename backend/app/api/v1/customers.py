"""Customers API (Phase 12 — Customers, CRM & External Relationships)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, get_current_user, require_permission
from app.customers.customer_service import customer_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/customers", tags=["Customers"])


@router.post("")
async def create_customer(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        customer = await customer_service.create(
            db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": customer.id, "company_name": customer.company_name, "status": customer.status}


@router.get("")
async def list_customers(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    segment: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    industry: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    owner_id: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
):
    return await customer_service.list_customers(
        db, organization_id=org.id, status=status, segment=segment, tier=tier,
        industry=industry, source=source, owner_id=owner_id, search=search, tag=tag,
    )


@router.get("/tags")
async def list_tags(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await customer_service.list_tags(db, organization_id=org.id)


@router.get("/{customer_id}")
async def get_customer(
    customer_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    customer = await customer_service.detail(db, organization_id=org.id, customer_id=customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@router.patch("/{customer_id}")
async def update_customer(
    customer_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    customer = await customer_service.update(
        db, organization_id=org.id, customer_id=customer_id, data=payload, actor_id=user.id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"id": customer.id, "status": customer.status}


@router.delete("/{customer_id}")
async def delete_customer(
    customer_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await customer_service.delete(db, organization_id=org.id, customer_id=customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"deleted": True}


# ------------------------------------------------------------------ tags

@router.post("/{customer_id}/tags")
async def add_tag(
    customer_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    ok = await customer_service.add_tag(
        db, organization_id=org.id, customer_id=customer_id,
        name=payload.get("name", ""), color=payload.get("color", "brand"))
    if not ok:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"added": payload.get("name")}


@router.delete("/{customer_id}/tags/{name}")
async def remove_tag(
    customer_id: str, name: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await customer_service.remove_tag(db, organization_id=org.id, customer_id=customer_id, name=name):
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"removed": name}


# ------------------------------------------------------------------ notes

@router.post("/{customer_id}/notes")
async def add_note(
    customer_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    note = await customer_service.add_note(
        db, organization_id=org.id, customer_id=customer_id,
        content=payload.get("content", ""), author_id=user.id, kind=payload.get("kind", "note"))
    if note is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"id": note.id, "kind": note.kind}


@router.get("/{customer_id}/notes")
async def list_notes(
    customer_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await customer_service.list_notes(db, organization_id=org.id, customer_id=customer_id)


# ------------------------------------------------------------------ addresses

@router.post("/{customer_id}/addresses")
async def add_address(
    customer_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    address = await customer_service.add_address(
        db, organization_id=org.id, customer_id=customer_id, data=payload)
    if address is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"id": address.id, "kind": address.kind}


@router.get("/{customer_id}/addresses")
async def list_addresses(
    customer_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await customer_service.list_addresses(db, organization_id=org.id, customer_id=customer_id)


@router.delete("/{customer_id}/addresses/{address_id}")
async def delete_address(
    customer_id: str, address_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await customer_service.delete_address(
            db, organization_id=org.id, customer_id=customer_id, address_id=address_id):
        raise HTTPException(status_code=404, detail="Address not found")
    await db.commit()
    return {"deleted": True}


# ------------------------------------------------------------------ relationships

@router.post("/{customer_id}/relationships")
async def add_relationship(
    customer_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    relation = await customer_service.add_relationship(
        db, organization_id=org.id, customer_id=customer_id, data=payload)
    if relation is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"id": relation.id, "relation_type": relation.relation_type}


@router.get("/{customer_id}/relationships")
async def list_relationships(
    customer_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await customer_service.list_relationships(db, organization_id=org.id, customer_id=customer_id)


@router.delete("/{customer_id}/relationships/{relation_id}")
async def delete_relationship(
    customer_id: str, relation_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await customer_service.delete_relationship(
            db, organization_id=org.id, customer_id=customer_id, relation_id=relation_id):
        raise HTTPException(status_code=404, detail="Relationship not found")
    await db.commit()
    return {"deleted": True}


# ------------------------------------------------------------------ links

@router.post("/{customer_id}/projects/{project_id}")
async def link_project(
    customer_id: str, project_id: str,
    payload: dict[str, Any] = {},
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await customer_service.link_project(
        db, organization_id=org.id, customer_id=customer_id, project_id=project_id,
        kind=payload.get("kind", "implementation"), actor_id=user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return result


@router.delete("/{customer_id}/projects/{project_id}")
async def unlink_project(
    customer_id: str, project_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await customer_service.unlink_project(
            db, organization_id=org.id, customer_id=customer_id, project_id=project_id):
        raise HTTPException(status_code=404, detail="Link not found")
    await db.commit()
    return {"deleted": True}


@router.post("/{customer_id}/meetings/{meeting_id}")
async def link_meeting(
    customer_id: str, meeting_id: str,
    payload: dict[str, Any] = {},
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await customer_service.link_meeting(
        db, organization_id=org.id, customer_id=customer_id, meeting_id=meeting_id,
        kind=payload.get("kind", "status"), actor_id=user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return result


@router.post("/{customer_id}/documents/{document_id}")
async def link_document(
    customer_id: str, document_id: str,
    payload: dict[str, Any] = {},
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    result = await customer_service.link_document(
        db, organization_id=org.id, customer_id=customer_id, document_id=document_id,
        kind=payload.get("kind", "other"), actor_id=user.id)
    if result is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return result


@router.delete("/{customer_id}/documents/{document_id}")
async def unlink_document(
    customer_id: str, document_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await customer_service.unlink_document(
            db, organization_id=org.id, customer_id=customer_id, document_id=document_id):
        raise HTTPException(status_code=404, detail="Link not found")
    await db.commit()
    return {"deleted": True}


# ------------------------------------------------------------------ timeline

@router.post("/{customer_id}/timeline")
async def add_timeline(
    customer_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    ok = await customer_service.add_timeline(
        db, organization_id=org.id, customer_id=customer_id,
        event=payload.get("event", "manual"), title=payload.get("title", ""),
        detail=payload.get("detail"), actor_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"added": True}


@router.get("/{customer_id}/timeline")
async def timeline(
    customer_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(50, ge=1, le=200),
):
    return await customer_service.timeline(db, organization_id=org.id, customer_id=customer_id, limit=limit)
