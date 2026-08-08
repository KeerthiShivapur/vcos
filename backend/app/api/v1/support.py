"""Support API (Phase 12 — Customers, CRM & External Relationships)."""

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_organization, require_permission
from app.customers.support_service import support_service
from app.db.database import get_db
from app.models.organization import Organization
from app.models.user import User

router = APIRouter(prefix="/support", tags=["Support"])


@router.post("/tickets")
async def create_ticket(
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    try:
        ticket = await support_service.create(db, organization_id=org.id, data=payload, actor_id=user.id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await db.commit()
    return {"id": ticket.id, "subject": ticket.subject, "status": ticket.status}


@router.get("/tickets")
async def list_tickets(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    customer_id: Optional[str] = Query(None),
    assignee_id: Optional[str] = Query(None),
    escalated: bool = Query(False),
    search: Optional[str] = Query(None),
):
    return await support_service.list_tickets(
        db, organization_id=org.id, status=status, priority=priority, category=category,
        customer_id=customer_id, assignee_id=assignee_id, escalated=escalated, search=search)


@router.get("/summary")
async def summary(
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await support_service.summary(db, organization_id=org.id)


@router.get("/tickets/{ticket_id}")
async def get_ticket(
    ticket_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    ticket = await support_service.get(db, organization_id=org.id, ticket_id=ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return support_service._dict(ticket)


@router.patch("/tickets/{ticket_id}")
async def update_ticket(
    ticket_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    ticket = await support_service.update(
        db, organization_id=org.id, ticket_id=ticket_id, data=payload, actor_id=user.id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    await db.commit()
    return {"id": ticket.id, "status": ticket.status, "priority": ticket.priority}


@router.delete("/tickets/{ticket_id}")
async def delete_ticket(
    ticket_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    if not await support_service.delete(db, organization_id=org.id, ticket_id=ticket_id):
        raise HTTPException(status_code=404, detail="Ticket not found")
    await db.commit()
    return {"deleted": True}


@router.get("/tickets/{ticket_id}/knowledge")
async def knowledge_links(
    ticket_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
):
    return await support_service.knowledge_links(db, organization_id=org.id, ticket_id=ticket_id)


@router.post("/tickets/{ticket_id}/knowledge")
async def link_knowledge(
    ticket_id: str,
    payload: dict[str, Any],
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:manage")),
    db: AsyncSession = Depends(get_db),
):
    link = await support_service.link_knowledge(
        db, organization_id=org.id, ticket_id=ticket_id,
        document_id=payload.get("document_id", ""), document_title=payload.get("document_title"),
        kind=payload.get("kind", "suggested"))
    if link is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    await db.commit()
    return {"id": link.id, "document_id": link.document_id}


@router.get("/tickets/{ticket_id}/suggest")
async def suggest_knowledge(
    ticket_id: str,
    org: Organization = Depends(get_current_organization),
    user: User = Depends(require_permission("crm:read")),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(5, ge=1, le=20),
):
    return await support_service.suggest_knowledge(
        db, organization_id=org.id, ticket_id=ticket_id, limit=limit)
