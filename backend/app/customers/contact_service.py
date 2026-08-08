"""Contact service (Phase 12.4 — Contact Management).

Every customer can have a full contact roster — CEO, CTO, engineering,
finance, HR, legal, procurement, support — with emails, phones, LinkedIn
profiles, decision-maker flags and relationship history.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.events.event_bus import EventBus
from app.models.customer import Customer, CustomerContact

logger = logging.getLogger("vcos.customers.contact")

_event_bus = EventBus()

CONTACT_ROLES = [
    "ceo", "cto", "cfo", "manager", "finance", "support", "hr", "legal",
    "procurement", "technical", "executive", "other",
]


class ContactService:
    async def create(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                     data: dict[str, Any], actor_id: Optional[str] = None, flush: bool = True) -> Optional[CustomerContact]:
        customer = (
            await db.execute(
                select(Customer).where(Customer.organization_id == organization_id, Customer.id == customer_id)
            )
        ).scalar_one_or_none()
        if customer is None:
            return None
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        if data.get("is_primary"):
            await db.execute(
                CustomerContact.__table__.update()
                .where(CustomerContact.organization_id == organization_id,
                       CustomerContact.customer_id == customer_id)
                .values(is_primary=False)
            )
        contact = CustomerContact(
            organization_id=organization_id, customer_id=customer_id,
            name=name,
            role=data.get("role", "other") if data.get("role") in CONTACT_ROLES else "other",
            designation=data.get("designation"),
            email=data.get("email"),
            phone=data.get("phone"),
            linkedin=data.get("linkedin"),
            timezone=data.get("timezone"),
            preferred_language=data.get("preferred_language", "en"),
            decision_maker=bool(data.get("decision_maker", False)),
            is_primary=bool(data.get("is_primary", False)),
            notes=data.get("notes"),
        )
        db.add(contact)
        await db.flush()
        if flush:
            customer.last_activity_at = ensure_aware(contact.created_at) if contact.created_at else None
            await _event_bus.publish(
                db, name="contact.created", organization_id=organization_id, actor_id=actor_id,
                payload={"contact_id": contact.id, "customer_id": customer.id,
                         "name": contact.name, "customer_name": customer.company_name},
                flush=False,
            )
            await db.flush()
        return contact

    async def get(self, db: AsyncSession, *, organization_id: str, contact_id: str) -> Optional[CustomerContact]:
        return (
            await db.execute(
                select(CustomerContact).where(
                    CustomerContact.organization_id == organization_id, CustomerContact.id == contact_id
                )
            )
        ).scalar_one_or_none()

    async def update(self, db: AsyncSession, *, organization_id: str, contact_id: str,
                     data: dict[str, Any]) -> Optional[CustomerContact]:
        contact = await self.get(db, organization_id=organization_id, contact_id=contact_id)
        if contact is None:
            return None
        for field in ("name", "designation", "email", "phone", "linkedin", "timezone",
                      "preferred_language", "notes"):
            if field in data and data[field] is not None:
                setattr(contact, field, data[field])
        if data.get("role") in CONTACT_ROLES:
            contact.role = data["role"]
        if "decision_maker" in data:
            contact.decision_maker = bool(data["decision_maker"])
        if "is_primary" in data and data["is_primary"]:
            await db.execute(
                CustomerContact.__table__.update()
                .where(CustomerContact.organization_id == organization_id,
                       CustomerContact.customer_id == contact.customer_id,
                       CustomerContact.id != contact.id)
                .values(is_primary=False)
            )
            contact.is_primary = True
        await db.flush()
        return contact

    async def delete(self, db: AsyncSession, *, organization_id: str, contact_id: str) -> bool:
        contact = await self.get(db, organization_id=organization_id, contact_id=contact_id)
        if contact is None:
            return False
        await db.delete(contact)
        await db.flush()
        return True

    async def list_by_customer(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                               search: Optional[str] = None) -> list[dict[str, Any]]:
        query = select(CustomerContact).where(
            CustomerContact.organization_id == organization_id, CustomerContact.customer_id == customer_id
        )
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(CustomerContact.name).like(pattern),
                    func.lower(CustomerContact.email).like(pattern),
                    func.lower(CustomerContact.designation).like(pattern),
                )
            )
        rows = await db.execute(query.order_by(CustomerContact.created_at.asc()))
        return [self._dict(c) for c in rows.scalars().all()]

    async def list_all(self, db: AsyncSession, *, organization_id: str, search: Optional[str] = None,
                       customer_id: Optional[str] = None, decision_maker: Optional[bool] = None,
                       ) -> list[dict[str, Any]]:
        query = select(CustomerContact, Customer).join(
            Customer, (Customer.organization_id == CustomerContact.organization_id) & (Customer.id == CustomerContact.customer_id)
        ).where(CustomerContact.organization_id == organization_id)
        if customer_id:
            query = query.where(CustomerContact.customer_id == customer_id)
        if decision_maker is not None:
            query = query.where(CustomerContact.decision_maker.is_(decision_maker))
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(CustomerContact.name).like(pattern),
                    func.lower(CustomerContact.email).like(pattern),
                    func.lower(Customer.company_name).like(pattern),
                )
            )
        rows = await db.execute(query.order_by(CustomerContact.created_at.desc()))
        result = []
        for contact, customer in rows.all():
            item = self._dict(contact)
            item["customer_name"] = customer.company_name
            result.append(item)
        return result

    def _dict(self, contact: CustomerContact) -> dict[str, Any]:
        return {
            "id": contact.id,
            "customer_id": contact.customer_id,
            "name": contact.name,
            "role": contact.role,
            "designation": contact.designation,
            "email": contact.email,
            "phone": contact.phone,
            "linkedin": contact.linkedin,
            "timezone": contact.timezone,
            "preferred_language": contact.preferred_language,
            "decision_maker": contact.decision_maker,
            "is_primary": contact.is_primary,
            "notes": contact.notes,
            "created_at": ensure_aware(contact.created_at).isoformat() if contact.created_at else None,
        }


contact_service = ContactService()
