"""Support service (Phase 12.8 — Customer Support).

Tickets, requests, bugs, feature requests and escalations with priority,
SLA tracking, resolution and knowledge links. Suggested knowledge articles
are computed deterministically from the ticket text.
"""

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.event_bus import EventBus
from app.models.employee import Employee
from app.models.ticket import SupportTicket, TicketKnowledgeLink

logger = logging.getLogger("vcos.customers.support")

_event_bus = EventBus()

CATEGORIES = ["incident", "bug", "feature_request", "question", "escalation", "service_request"]
STATUSES = ["open", "in_progress", "waiting_customer", "escalated", "resolved", "closed"]
PRIORITIES = ["low", "medium", "high", "urgent"]
SLA_FIRST_RESPONSE = {"low": 2880, "medium": 1440, "high": 240, "urgent": 60}
SLA_RESOLUTION = {"low": 43200, "medium": 21600, "high": 7200, "urgent": 1440}


class SupportService:
    async def create(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
                     actor_id: Optional[str] = None, via_portal: bool = False,
                     portal_user_id: Optional[str] = None) -> SupportTicket:
        subject = (data.get("subject") or "").strip()
        if not subject:
            raise ValueError("subject is required")
        priority = data.get("priority", "medium") if data.get("priority") in PRIORITIES else "medium"
        category = data.get("category", "question") if data.get("category") in CATEGORIES else "question"
        ticket = SupportTicket(
            organization_id=organization_id,
            customer_id=data.get("customer_id"),
            contact_id=data.get("contact_id"),
            project_id=data.get("project_id"),
            category=category,
            subject=subject,
            description=data.get("description"),
            status=data.get("status", "open") if data.get("status") in STATUSES else "open",
            priority=priority,
            assignee_id=data.get("assignee_id"),
            reporter_id=data.get("reporter_id") or actor_id,
            sla_first_response_minutes=SLA_FIRST_RESPONSE[priority],
            sla_resolution_minutes=SLA_RESOLUTION[priority],
            via_portal=via_portal,
            portal_user_id=portal_user_id,
            duplicate_of=data.get("duplicate_of"),
        )
        db.add(ticket)
        await db.flush()
        if ticket.customer_id:
            from app.customers.customer_service import customer_service

            await customer_service.set_last_activity(db, organization_id=organization_id, customer_id=ticket.customer_id)
        await _event_bus.publish(
            db, name="ticket.created", organization_id=organization_id, actor_id=actor_id,
            payload={"ticket_id": ticket.id, "subject": ticket.subject,
                     "customer_id": ticket.customer_id, "priority": ticket.priority,
                     "category": ticket.category},
            flush=False,
        )
        await db.flush()
        return ticket

    async def get(self, db: AsyncSession, *, organization_id: str, ticket_id: str) -> Optional[SupportTicket]:
        return (
            await db.execute(
                select(SupportTicket).where(SupportTicket.organization_id == organization_id, SupportTicket.id == ticket_id)
            )
        ).scalar_one_or_none()

    async def update(self, db: AsyncSession, *, organization_id: str, ticket_id: str, data: dict[str, Any],
                     actor_id: Optional[str] = None) -> Optional[SupportTicket]:
        ticket = await self.get(db, organization_id=organization_id, ticket_id=ticket_id)
        if ticket is None:
            return None
        for field in ("subject", "description", "customer_id", "contact_id", "project_id",
                      "assignee_id", "resolution", "root_cause", "duplicate_of"):
            if field in data and data[field] is not None:
                setattr(ticket, field, data[field])
        if data.get("category") in CATEGORIES:
            ticket.category = data["category"]
        if data.get("priority") in PRIORITIES and data["priority"] != ticket.priority:
            ticket.priority = data["priority"]
            ticket.sla_first_response_minutes = SLA_FIRST_RESPONSE[ticket.priority]
            ticket.sla_resolution_minutes = SLA_RESOLUTION[ticket.priority]
        if data.get("status"):
            await self._set_status(db, ticket, status=data["status"], actor_id=actor_id, note=data.get("note"))
        if data.get("satisfaction_rating") is not None:
            ticket.satisfaction_rating = int(data["satisfaction_rating"])
        await db.flush()
        return ticket

    async def _set_status(self, db: AsyncSession, ticket: SupportTicket, *, status: str,
                          actor_id: Optional[str] = None, note: Optional[str] = None) -> None:
        if status not in STATUSES or status == ticket.status:
            return
        old = ticket.status
        ticket.status = status
        event_name = None
        if status == "resolved":
            ticket.resolved_at = utcnow()
            event_name = "ticket.resolved"
        elif status == "escalated":
            ticket.escalated_at = utcnow()
            event_name = "ticket.escalated"
        if status in ("in_progress", "open") and ticket.first_responded_at is None:
            ticket.first_responded_at = utcnow()
        if event_name:
            await _event_bus.publish(
                db, name=event_name, organization_id=ticket.organization_id, actor_id=actor_id,
                payload={"ticket_id": ticket.id, "subject": ticket.subject,
                         "customer_id": ticket.customer_id, "note": note},
                flush=False,
            )
        await _event_bus.publish(
            db, name="ticket.status_changed", organization_id=ticket.organization_id, actor_id=actor_id,
            payload={"ticket_id": ticket.id, "subject": ticket.subject, "from": old, "to": status},
            flush=False,
        )

    async def list_tickets(self, db: AsyncSession, *, organization_id: str, status: Optional[str] = None,
                           priority: Optional[str] = None, category: Optional[str] = None,
                           customer_id: Optional[str] = None, assignee_id: Optional[str] = None,
                           escalated: bool = False, search: Optional[str] = None,
                           ) -> list[dict[str, Any]]:
        query = select(SupportTicket).where(SupportTicket.organization_id == organization_id)
        if status:
            query = query.where(SupportTicket.status == status)
        if priority:
            query = query.where(SupportTicket.priority == priority)
        if category:
            query = query.where(SupportTicket.category == category)
        if customer_id:
            query = query.where(SupportTicket.customer_id == customer_id)
        if assignee_id:
            query = query.where(SupportTicket.assignee_id == assignee_id)
        if escalated:
            query = query.where(SupportTicket.status == "escalated")
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(SupportTicket.subject).like(pattern),
                    func.lower(SupportTicket.description).like(pattern),
                )
            )
        rows = await db.execute(query.order_by(SupportTicket.updated_at.desc()))
        result = []
        for ticket in rows.scalars().all():
            assignee = await db.get(Employee, ticket.assignee_id) if ticket.assignee_id else None
            result.append(self._dict(ticket, assignee_name=assignee.full_name if assignee else None))
        return result

    def _dict(self, ticket: SupportTicket, assignee_name: Optional[str] = None) -> dict[str, Any]:
        return {
            "id": ticket.id, "customer_id": ticket.customer_id, "contact_id": ticket.contact_id,
            "project_id": ticket.project_id, "category": ticket.category, "subject": ticket.subject,
            "description": ticket.description, "status": ticket.status, "priority": ticket.priority,
            "assignee_id": ticket.assignee_id, "assignee_name": assignee_name, "reporter_id": ticket.reporter_id,
            "resolution": ticket.resolution, "root_cause": ticket.root_cause,
            "sla_first_response_minutes": ticket.sla_first_response_minutes,
            "sla_resolution_minutes": ticket.sla_resolution_minutes,
            "sla_breached": self._sla_breached(ticket),
            "first_responded_at": ensure_aware(ticket.first_responded_at).isoformat() if ticket.first_responded_at else None,
            "resolved_at": ensure_aware(ticket.resolved_at).isoformat() if ticket.resolved_at else None,
            "escalated_at": ensure_aware(ticket.escalated_at).isoformat() if ticket.escalated_at else None,
            "via_portal": ticket.via_portal, "portal_user_id": ticket.portal_user_id,
            "duplicate_of": ticket.duplicate_of, "satisfaction_rating": ticket.satisfaction_rating,
            "created_at": ensure_aware(ticket.created_at).isoformat() if ticket.created_at else None,
            "updated_at": ensure_aware(ticket.updated_at).isoformat() if ticket.updated_at else None,
        }

    def _sla_breached(self, ticket: SupportTicket) -> bool:
        if ticket.status in ("resolved", "closed"):
            return False
        if ticket.created_at is None:
            return False
        created = ensure_aware(ticket.created_at)
        minutes = (utcnow() - created).total_seconds() / 60
        resolution = ticket.sla_resolution_minutes or SLA_RESOLUTION.get(ticket.priority, 21600)
        return minutes > resolution

    async def summary(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        tickets = (
            await db.execute(select(SupportTicket).where(SupportTicket.organization_id == organization_id))
        ).scalars().all()
        by_status: dict[str, int] = {}
        by_priority: dict[str, int] = {}
        open_tickets: list[dict[str, Any]] = []
        for ticket in tickets:
            by_status[ticket.status] = by_status.get(ticket.status, 0) + 1
            by_priority[ticket.priority] = by_priority.get(ticket.priority, 0) + 1
            if ticket.status in ("open", "in_progress", "waiting_customer", "escalated"):
                open_tickets.append(self._dict(ticket))
        open_tickets.sort(key=lambda item: ("urgent", "high", "medium", "low").index(item["priority"]))
        return {
            "total": len(tickets),
            "open": by_status.get("open", 0) + by_status.get("in_progress", 0) + by_status.get("waiting_customer", 0),
            "escalated": by_status.get("escalated", 0),
            "resolved": by_status.get("resolved", 0) + by_status.get("closed", 0),
            "by_status": by_status,
            "by_priority": by_priority,
            "sla_breached": sum(1 for ticket in tickets if self._sla_breached(ticket)),
            "recent": open_tickets[:10],
        }

    # ------------------------------------------------------------------ knowledge links

    async def link_knowledge(self, db: AsyncSession, *, organization_id: str, ticket_id: str,
                             document_id: str, document_title: Optional[str] = None,
                             kind: str = "suggested") -> Optional[TicketKnowledgeLink]:
        ticket = await self.get(db, organization_id=organization_id, ticket_id=ticket_id)
        if ticket is None:
            return None
        link = TicketKnowledgeLink(
            organization_id=organization_id, ticket_id=ticket_id, document_id=document_id,
            document_title=document_title, kind=kind,
        )
        db.add(link)
        await db.flush()
        return link

    async def knowledge_links(self, db: AsyncSession, *, organization_id: str, ticket_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(TicketKnowledgeLink).where(
                TicketKnowledgeLink.organization_id == organization_id, TicketKnowledgeLink.ticket_id == ticket_id
            )
        )
        return [{
            "id": link.id, "document_id": link.document_id, "document_title": link.document_title,
            "kind": link.kind,
            "created_at": ensure_aware(link.created_at).isoformat() if link.created_at else None,
        } for link in rows.scalars().all()]

    async def suggest_knowledge(self, db: AsyncSession, *, organization_id: str, ticket_id: str,
                                limit: int = 5) -> list[dict[str, Any]]:
        """Deterministic knowledge suggestions from ticket text."""
        from app.models.knowledge import Document

        ticket = await self.get(db, organization_id=organization_id, ticket_id=ticket_id)
        if ticket is None:
            return []
        terms = [t for t in (ticket.subject + " " + (ticket.description or "")).lower().split() if len(t) > 3]
        if not terms:
            return []
        docs = (
            await db.execute(
                select(Document).where(
                    Document.organization_id == organization_id,
                    Document.status == "published",
                ).limit(200)
            )
        ).scalars().all()
        scored = []
        for doc in docs:
            text = f"{doc.title} {doc.content or ''}".lower()
            score = sum(1 for term in set(terms) if term in text)
            if score:
                scored.append({"document_id": doc.id, "title": doc.title, "score": score})
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]

    async def delete(self, db: AsyncSession, *, organization_id: str, ticket_id: str) -> bool:
        ticket = await self.get(db, organization_id=organization_id, ticket_id=ticket_id)
        if ticket is None:
            return False
        await db.delete(ticket)
        await db.flush()
        return True


support_service = SupportService()
