"""Relationship intelligence (Phase 12.13).

Links customers to people, projects, contracts, meetings and support in the
organization graph, then identifies strong/weak relationships and single
points of failure so leadership can diversify coverage before churn.
"""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.intelligence.graph_engine import GraphEngine
from app.models.contract import Contract
from app.models.customer import (
    Customer,
    CustomerMeetingLink,
    CustomerNote,
    CustomerProjectLink,
)
from app.models.employee import Employee
from app.models.ticket import SupportTicket

logger = logging.getLogger("vcos.customers.relationship")

graph_engine = GraphEngine()


class RelationshipService:

    async def build_graph(self, db: AsyncSession, *, organization_id: str) -> dict[str, int]:
        """Re-derive relationship edges for all customers of the organization."""
        customers = (
            await db.execute(select(Customer).where(Customer.organization_id == organization_id))
        ).scalars().all()
        owners = (
            await db.execute(select(Employee).where(Employee.organization_id == organization_id))
        ).scalars().all()
        owner_by_id = {employee.id: employee for employee in owners}
        edge_count = 0

        notes = (
            await db.execute(
                select(CustomerNote).where(CustomerNote.organization_id == organization_id)
            )
        ).scalars().all()
        meeting_links = (
            await db.execute(
                select(CustomerMeetingLink).where(CustomerMeetingLink.organization_id == organization_id)
            )
        ).scalars().all()
        project_links = (
            await db.execute(
                select(CustomerProjectLink).where(CustomerProjectLink.organization_id == organization_id)
            )
        ).scalars().all()
        contracts = (
            await db.execute(
                select(Contract).where(Contract.organization_id == organization_id)
            )
        ).scalars().all()
        tickets = (
            await db.execute(
                select(SupportTicket).where(SupportTicket.organization_id == organization_id)
            )
        ).scalars().all()

        async def add_edge(source_type: str, source_id: str, target_type: str, target_id: str,
                           relation: str, weight: float, evidence: str):
            nonlocal edge_count
            if not source_id or not target_id:
                return
            await graph_engine.upsert_edge(
                db, organization_id=organization_id,
                source_type=source_type, source_id=source_id,
                target_type=target_type, target_id=target_id,
                relation=relation, weight=weight, evidence=evidence,
            )
            edge_count += 1

        for customer in customers:
            company = customer.company_name or customer.id
            await add_edge("customer", customer.id, "company", customer.id, "has_company", 0.9,
                           f"{company} is an external company record")
            if customer.owner_id:
                owner = owner_by_id.get(customer.owner_id)
                if owner:
                    await add_edge("employee", customer.owner_id, "customer", customer.id, "owns", 0.8,
                                   f"{owner.name or owner.email} owns the account {company}")
        for note in notes:
            if note.author_id:
                await add_edge("employee", note.author_id, "customer", note.customer_id, "touched", 0.2,
                               f"Engaged by an employee on {note.customer_id[:8]}")
        for link in meeting_links:
            await add_edge("meeting", link.meeting_id, "customer", link.customer_id, "meets", 0.4,
                           f"Customer meeting on record")
        for link in project_links:
            await add_edge("project", link.project_id, "customer", link.customer_id, "serves", 0.5,
                           f"Linked project")
        for contract in contracts:
            if contract.customer_id:
                await add_edge("contract", contract.id, "customer", contract.customer_id, "contracted", 0.6,
                               f"Contract: {contract.title or contract.id}")
        for ticket in tickets:
            if ticket.customer_id:
                await add_edge("ticket", ticket.id, "customer", ticket.customer_id, "supports", 0.3,
                               f"Support ticket: {ticket.subject or ticket.id}")
        await db.flush()
        return {"customers": len(customers), "edges": edge_count}

    async def relationships(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        customers = (
            await db.execute(select(Customer).where(Customer.organization_id == organization_id))
        ).scalars().all()
        from app.models.customer import CustomerContact

        contacts = (
            await db.execute(
                select(CustomerContact).where(CustomerContact.organization_id == organization_id)
            )
        ).scalars().all()
        meeting_links = (
            await db.execute(
                select(CustomerMeetingLink).where(CustomerMeetingLink.organization_id == organization_id)
            )
        ).scalars().all()
        project_links = (
            await db.execute(
                select(CustomerProjectLink).where(CustomerProjectLink.organization_id == organization_id)
            )
        ).scalars().all()
        notes = (
            await db.execute(
                select(CustomerNote).where(CustomerNote.organization_id == organization_id)
            )
        ).scalars().all()
        tickets = (
            await db.execute(
                select(SupportTicket).where(SupportTicket.organization_id == organization_id)
            )
        ).scalars().all()

        def count_by(rows, key: str) -> dict[str, int]:
            counts: dict[str, int] = {}
            for row in rows:
                customer_id = getattr(row, key)
                if customer_id:
                    counts[customer_id] = counts.get(customer_id, 0) + 1
            return counts

        contact_count = count_by(contacts, "customer_id")
        meeting_count = count_by(meeting_links, "customer_id")
        project_count = count_by(project_links, "customer_id")
        note_count = count_by(notes, "customer_id")
        ticket_count = count_by(tickets, "customer_id")

        result = []
        for customer in customers:
            contacts_n = contact_count.get(customer.id, 0)
            meetings_n = meeting_count.get(customer.id, 0)
            projects_n = project_count.get(customer.id, 0)
            tickets_n = ticket_count.get(customer.id, 0)
            engagement = contacts_n + meetings_n + projects_n + note_count.get(customer.id, 0)
            result.append({
                "customer_id": customer.id,
                "company_name": customer.company_name,
                "health_score": customer.health_score,
                "health_status": customer.health_status,
                "owner_id": customer.owner_id,
                "contacts": contacts_n,
                "meetings": meetings_n,
                "projects": projects_n,
                "tickets": tickets_n,
                "engagement": engagement,
                "strength": self._strength(customer.health_score or 0, engagement),
            })
        result.sort(key=lambda item: item["strength"])
        return {"relationships": result, "total": len(result)}

    def _strength(self, health: int, engagement: int) -> float:
        return round(min(100.0, health * 0.7 + min(engagement, 10) * 3), 1)

    async def risks(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        """Single points of failure: one owner holding too much exposure."""
        customers = (
            await db.execute(select(Customer).where(Customer.organization_id == organization_id))
        ).scalars().all()
        owners: dict[str, list[dict[str, Any]]] = {}
        for customer in customers:
            if not customer.owner_id:
                continue
            owners.setdefault(customer.owner_id, []).append({
                "customer_id": customer.id,
                "company_name": customer.company_name,
                "health_score": customer.health_score,
                "value": customer.lifetime_value or 0,
            })
        employees = {
            employee.id: employee
            for employee in (await db.execute(select(Employee).where(Employee.organization_id == organization_id))).scalars()
        }
        exposed = []
        for owner_id, owned in owners.items():
            if len(owned) < 3:
                continue
            employee = employees.get(owner_id)
            total_value = sum(item["value"] for item in owned)
            at_risk = sum(1 for item in owned if (item["health_score"] or 0) < 50)
            exposed.append({
                "owner_id": owner_id,
                "owner_name": employee.name if employee else "Unknown",
                "customers": len(owned),
                "at_risk": at_risk,
                "total_value": total_value,
            })
        exposed.sort(key=lambda item: item["customers"], reverse=True)
        return {"single_points_of_failure": exposed, "total": len(exposed)}


relationship_service = RelationshipService()
