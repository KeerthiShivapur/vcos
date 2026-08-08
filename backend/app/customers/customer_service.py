"""Customer service (Phase 12.1 — Customer Foundation).

Customers are the anchor of the external relationship operating system:
CRUD with tenant isolation, contacts, tags, notes, addresses,
relationships, health snapshots, timeline, and link tables that connect
customers to projects, meetings and documents across VCOS.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.customers.parse import to_date, to_dt
from app.events.event_bus import EventBus
from app.models.customer import (
    Customer,
    CustomerAddress,
    CustomerContact,
    CustomerDocumentLink,
    CustomerHealth,
    CustomerMeetingLink,
    CustomerNote,
    CustomerProjectLink,
    CustomerRelationship,
    CustomerTag,
    CustomerTimeline,
)
from app.models.employee import Employee

logger = logging.getLogger("vcos.customers.customer")

_event_bus = EventBus()

CUSTOMER_STATUSES = ["prospect", "customer", "inactive"]
SEGMENTS = ["enterprise", "mid_market", "smb", "startup", "government", "nonprofit"]
TIERS = ["basic", "silver", "gold", "platinum", "enterprise"]
SOURCES = ["website", "referral", "marketing", "events", "cold_outreach", "partner", "advertisement"]
NOTE_KINDS = ["note", "call", "email", "meeting", "follow_up", "decision"]
RELATION_TYPES = ["partner", "vendor", "investor", "consultant", "government", "university", "other"]
LINK_KINDS = ["implementation", "support", "pilot", "expansion", "other"]
DOC_KINDS = ["proposal", "contract", "requirement", "faq", "training", "deployment", "other"]
MEETING_KINDS = ["discovery", "proposal", "status", "review", "training", "other"]


class CustomerService:
    # ------------------------------------------------------------------ CRUD

    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any], actor_id: Optional[str] = None,
    ) -> Customer:
        name = (data.get("company_name") or "").strip()
        if not name:
            raise ValueError("company_name is required")
        status = data.get("status", "customer")
        customer = Customer(
            organization_id=organization_id,
            company_name=name,
            status=status if status in CUSTOMER_STATUSES else "customer",
            segment=data.get("segment", "mid_market") if data.get("segment") in SEGMENTS else "mid_market",
            tier=data.get("tier", "basic") if data.get("tier") in TIERS else "basic",
            industry=data.get("industry"),
            website=data.get("website"),
            country=data.get("country"),
            timezone=data.get("timezone", "UTC"),
            employee_count=data.get("employee_count"),
            source=data.get("source", "website") if data.get("source") in SOURCES else "website",
            owner_id=data.get("owner_id"),
            description=data.get("description"),
            first_contact_at=to_dt(data.get("first_contact_at")) or utcnow(),
            annual_value=data.get("annual_value"),
            attributes=data.get("metadata") or data.get("attributes"),
        )
        db.add(customer)
        await db.flush()
        await _event_bus.publish(
            db, name="customer.created", organization_id=organization_id, actor_id=actor_id,
            payload={"customer_id": customer.id, "company_name": customer.company_name, "status": customer.status},
            flush=False,
        )
        await self._timeline(
            db, organization_id=organization_id, customer_id=customer.id,
            event="customer.created", title=f"Customer created — {customer.company_name}",
            detail=data.get("description"), actor_id=actor_id,
        )
        if data.get("notes"):
            await self.add_note(
                db, organization_id=organization_id, customer_id=customer.id,
                content=data["notes"], author_id=actor_id, kind="note", flush=False,
            )
        if data.get("contacts"):
            from app.customers.contact_service import contact_service

            for contact in data["contacts"]:
                await contact_service.create(
                    db, organization_id=organization_id, customer_id=customer.id,
                    data=contact, actor_id=actor_id, flush=False,
                )
        return customer

    async def get(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> Optional[Customer]:
        return (
            await db.execute(
                select(Customer).where(Customer.organization_id == organization_id, Customer.id == customer_id)
            )
        ).scalar_one_or_none()

    async def update(
        self, db: AsyncSession, *, organization_id: str, customer_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> Optional[Customer]:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        editable = [
            "company_name", "status", "segment", "tier", "industry", "website", "country",
            "timezone", "employee_count", "source", "owner_id", "description",
            "first_contact_at", "annual_value", "attributes",
        ]
        changed = []
        for field in editable:
            if field in data and data[field] is not None:
                old = getattr(customer, field)
                setattr(customer, field, data[field])
                if old != data[field]:
                    changed.append(field)
        if data.get("status") in CUSTOMER_STATUSES:
            customer.status = data["status"]
        if changed or data.get("status"):
            await _event_bus.publish(
                db, name="customer.updated", organization_id=organization_id, actor_id=actor_id,
                payload={"customer_id": customer.id, "company_name": customer.company_name,
                         "changed": changed, "status": customer.status},
                flush=False,
            )
            await self._timeline(
                db, organization_id=organization_id, customer_id=customer.id,
                event="customer.updated",
                title=f"Customer updated — {customer.company_name}",
                detail=", ".join(changed) if changed else "status change", actor_id=actor_id,
            )
        await db.flush()
        return customer

    async def delete(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> bool:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return False
        await db.delete(customer)
        await db.flush()
        return True

    async def list_customers(
        self, db: AsyncSession, *, organization_id: str,
        status: Optional[str] = None, segment: Optional[str] = None, tier: Optional[str] = None,
        industry: Optional[str] = None, source: Optional[str] = None, owner_id: Optional[str] = None,
        search: Optional[str] = None, tag: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(Customer).where(Customer.organization_id == organization_id)
        if status:
            query = query.where(Customer.status == status)
        if segment:
            query = query.where(Customer.segment == segment)
        if tier:
            query = query.where(Customer.tier == tier)
        if industry:
            query = query.where(func.lower(Customer.industry) == industry.lower())
        if source:
            query = query.where(Customer.source == source)
        if owner_id:
            query = query.where(Customer.owner_id == owner_id)
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(
                or_(
                    func.lower(Customer.company_name).like(pattern),
                    func.lower(Customer.industry).like(pattern),
                    func.lower(Customer.country).like(pattern),
                )
            )
        rows = await db.execute(query.order_by(Customer.updated_at.desc()))
        result = []
        for customer in rows.scalars().all():
            owner = await db.get(Employee, customer.owner_id) if customer.owner_id else None
            item = self._base_dict(customer)
            item["owner_name"] = owner.full_name if owner else None
            item["tags"] = list(customer.attributes.get("tags", []) if customer.attributes else [])
            result.append(item)
        if tag:
            result = [item for item in result if tag in item.get("tags", [])]
        return result

    def _base_dict(self, customer: Customer) -> dict[str, Any]:
        return {
            "id": customer.id,
            "company_name": customer.company_name,
            "status": customer.status,
            "segment": customer.segment,
            "tier": customer.tier,
            "industry": customer.industry,
            "website": customer.website,
            "country": customer.country,
            "timezone": customer.timezone,
            "employee_count": customer.employee_count,
            "source": customer.source,
            "owner_id": customer.owner_id,
            "description": customer.description,
            "health_score": customer.health_score,
            "health_status": customer.health_status,
            "annual_value": customer.annual_value,
            "last_activity_at": ensure_aware(customer.last_activity_at).isoformat() if customer.last_activity_at else None,
            "first_contact_at": ensure_aware(customer.first_contact_at).isoformat() if customer.first_contact_at else None,
            "created_at": ensure_aware(customer.created_at).isoformat() if customer.created_at else None,
            "updated_at": ensure_aware(customer.updated_at).isoformat() if customer.updated_at else None,
        }

    async def detail(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> Optional[dict[str, Any]]:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        owner = await db.get(Employee, customer.owner_id) if customer.owner_id else None
        contacts = (
            await db.execute(
                select(CustomerContact).where(
                    CustomerContact.organization_id == organization_id, CustomerContact.customer_id == customer_id
                ).order_by(CustomerContact.created_at.asc())
            )
        ).scalars().all()
        notes = (
            await db.execute(
                select(CustomerNote).where(
                    CustomerNote.organization_id == organization_id, CustomerNote.customer_id == customer_id
                ).order_by(CustomerNote.created_at.desc())
            )
        ).scalars().all()
        tags = await self._customer_tags(db, organization_id=organization_id, customer_id=customer_id)
        health = (
            await db.execute(
                select(CustomerHealth).where(
                    CustomerHealth.organization_id == organization_id, CustomerHealth.customer_id == customer_id
                )
            )
        ).scalar_one_or_none()
        projects = (
            await db.execute(
                select(CustomerProjectLink).where(
                    CustomerProjectLink.organization_id == organization_id, CustomerProjectLink.customer_id == customer_id
                ).order_by(CustomerProjectLink.created_at.desc())
            )
        ).scalars().all()
        meetings = (
            await db.execute(
                select(CustomerMeetingLink).where(
                    CustomerMeetingLink.organization_id == organization_id, CustomerMeetingLink.customer_id == customer_id
                ).order_by(CustomerMeetingLink.created_at.desc())
            )
        ).scalars().all()
        documents = (
            await db.execute(
                select(CustomerDocumentLink).where(
                    CustomerDocumentLink.organization_id == organization_id, CustomerDocumentLink.customer_id == customer_id
                ).order_by(CustomerDocumentLink.created_at.desc())
            )
        ).scalars().all()
        team = await self._account_team(db, organization_id=organization_id, customer_id=customer_id)
        base = self._base_dict(customer)
        base["owner_name"] = owner.full_name if owner else None
        base["contacts"] = [self._contact_dict(c) for c in contacts]
        base["notes"] = [self._note_dict(n) for n in notes]
        base["tags"] = tags
        base["health"] = {
            "score": health.score if health else customer.health_score,
            "status": health.status if health else customer.health_status,
            "renewal_probability": health.renewal_probability if health else None,
            "factors": health.factors if health else {},
            "signals": health.signals if health else [],
            "computed_at": ensure_aware(health.computed_at).isoformat() if health and health.computed_at else None,
        }
        base["projects"] = [self._project_link_dict(p) for p in projects]
        base["meetings"] = [self._meeting_link_dict(m) for m in meetings]
        base["documents"] = [self._document_link_dict(d) for d in documents]
        base["account_team"] = team
        base["contact_count"] = len(contacts)
        base["note_count"] = len(notes)
        base["project_count"] = len(projects)
        base["meeting_count"] = len(meetings)
        base["document_count"] = len(documents)
        return base

    # ------------------------------------------------------------------ tags

    async def list_tags(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(CustomerTag).where(CustomerTag.organization_id == organization_id).order_by(CustomerTag.name)
        )
        return [{"id": t.id, "name": t.name, "color": t.color} for t in rows.scalars().all()]

    async def ensure_tag(self, db: AsyncSession, *, organization_id: str, name: str, color: str = "brand") -> CustomerTag:
        tag = (
            await db.execute(
                select(CustomerTag).where(CustomerTag.organization_id == organization_id, CustomerTag.name == name)
            )
        ).scalar_one_or_none()
        if tag is None:
            tag = CustomerTag(organization_id=organization_id, name=name, color=color)
            db.add(tag)
            await db.flush()
        return tag

    async def add_tag(
        self, db: AsyncSession, *, organization_id: str, customer_id: str, name: str, color: str = "brand",
    ) -> bool:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return False
        tag = await self.ensure_tag(db, organization_id=organization_id, name=name, color=color)
        tags = list(customer.attributes.get("tags", []) if customer.attributes else [])
        if tag.name not in tags:
            tags.append(tag.name)
            customer.attributes = {**(customer.attributes or {}), "tags": tags}
            await db.flush()
        return True

    async def remove_tag(self, db: AsyncSession, *, organization_id: str, customer_id: str, name: str) -> bool:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return False
        tags = list(customer.attributes.get("tags", []) if customer.attributes else [])
        if name in tags:
            tags.remove(name)
            customer.attributes = {**(customer.attributes or {}), "tags": tags}
            await db.flush()
        return True

    async def _customer_tags(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> list[str]:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return []
        return list(customer.attributes.get("tags", []) if customer.attributes else [])

    # ------------------------------------------------------------------ notes

    async def add_note(
        self, db: AsyncSession, *, organization_id: str, customer_id: str, content: str,
        author_id: Optional[str] = None, kind: str = "note", flush: bool = True,
    ) -> Optional[CustomerNote]:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        note = CustomerNote(
            organization_id=organization_id, customer_id=customer_id, author_id=author_id,
            kind=kind if kind in NOTE_KINDS else "note", content=content,
        )
        db.add(note)
        customer.last_activity_at = utcnow()
        await db.flush()
        await self._timeline(
            db, organization_id=organization_id, customer_id=customer_id,
            event="customer.note.added", title=f"{kind.title()} logged — {customer.company_name}",
            detail=content[:200], actor_id=author_id, flush=False,
        )
        if flush:
            await db.flush()
        return note

    def _note_dict(self, note: CustomerNote) -> dict[str, Any]:
        return {
            "id": note.id,
            "customer_id": note.customer_id,
            "author_id": note.author_id,
            "kind": note.kind,
            "content": note.content,
            "pinned": note.pinned,
            "created_at": ensure_aware(note.created_at).isoformat() if note.created_at else None,
        }

    def _contact_dict(self, contact: CustomerContact) -> dict[str, Any]:
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

    async def list_notes(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(CustomerNote).where(
                CustomerNote.organization_id == organization_id, CustomerNote.customer_id == customer_id
            ).order_by(CustomerNote.created_at.desc())
        )
        return [self._note_dict(n) for n in rows.scalars().all()]

    # ------------------------------------------------------------------ addresses

    async def add_address(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                          data: dict[str, Any]) -> Optional[CustomerAddress]:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        if data.get("is_primary"):
            await db.execute(
                CustomerAddress.__table__.update()
                .where(CustomerAddress.organization_id == organization_id,
                       CustomerAddress.customer_id == customer_id)
                .values(is_primary=False)
            )
        address = CustomerAddress(organization_id=organization_id, customer_id=customer_id, **{
            "kind": data.get("kind", "registered"), "line1": data.get("line1"), "line2": data.get("line2"),
            "city": data.get("city"), "state": data.get("state"), "postal_code": data.get("postal_code"),
            "country": data.get("country"), "is_primary": bool(data.get("is_primary", False)),
        })
        db.add(address)
        await db.flush()
        return address

    async def list_addresses(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(CustomerAddress).where(
                CustomerAddress.organization_id == organization_id, CustomerAddress.customer_id == customer_id
            )
        )
        result = []
        for address in rows.scalars().all():
            result.append({
                "id": address.id, "kind": address.kind, "line1": address.line1, "line2": address.line2,
                "city": address.city, "state": address.state, "postal_code": address.postal_code,
                "country": address.country, "is_primary": address.is_primary,
            })
        return result

    async def delete_address(self, db: AsyncSession, *, organization_id: str, customer_id: str, address_id: str) -> bool:
        address = (
            await db.execute(
                select(CustomerAddress).where(
                    CustomerAddress.organization_id == organization_id,
                    CustomerAddress.customer_id == customer_id,
                    CustomerAddress.id == address_id,
                )
            )
        ).scalar_one_or_none()
        if address is None:
            return False
        await db.delete(address)
        await db.flush()
        return True

    # ------------------------------------------------------------------ relationships

    async def add_relationship(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                               data: dict[str, Any]) -> Optional[CustomerRelationship]:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        relation = CustomerRelationship(
            organization_id=organization_id, customer_id=customer_id,
            relation_type=data.get("relation_type", "other") if data.get("relation_type") in RELATION_TYPES else "other",
            entity_id=data.get("entity_id"), entity_type=data.get("entity_type"),
            name=data.get("name"), description=data.get("description"),
            status=data.get("status", "active") if data.get("status") in ("active", "paused", "ended") else "active",
        )
        db.add(relation)
        await db.flush()
        return relation

    async def list_relationships(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(CustomerRelationship).where(
                CustomerRelationship.organization_id == organization_id, CustomerRelationship.customer_id == customer_id
            )
        )
        result = []
        for rel in rows.scalars().all():
            result.append({
                "id": rel.id, "relation_type": rel.relation_type, "entity_id": rel.entity_id,
                "entity_type": rel.entity_type, "name": rel.name, "description": rel.description,
                "status": rel.status,
                "created_at": ensure_aware(rel.created_at).isoformat() if rel.created_at else None,
            })
        return result

    async def delete_relationship(self, db: AsyncSession, *, organization_id: str, customer_id: str, relation_id: str) -> bool:
        rel = (
            await db.execute(
                select(CustomerRelationship).where(
                    CustomerRelationship.organization_id == organization_id,
                    CustomerRelationship.customer_id == customer_id,
                    CustomerRelationship.id == relation_id,
                )
            )
        ).scalar_one_or_none()
        if rel is None:
            return False
        await db.delete(rel)
        await db.flush()
        return True

    # ------------------------------------------------------------------ links (projects / meetings / documents)

    async def link_project(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                           project_id: str, kind: str = "implementation", actor_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        link = (
            await db.execute(
                select(CustomerProjectLink).where(
                    CustomerProjectLink.organization_id == organization_id,
                    CustomerProjectLink.customer_id == customer_id,
                    CustomerProjectLink.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            link = CustomerProjectLink(
                organization_id=organization_id, customer_id=customer_id, project_id=project_id,
                kind=kind if kind in LINK_KINDS else "implementation",
            )
            db.add(link)
            await db.flush()
        else:
            link.kind = kind
            link.status = "active"
        await _event_bus.publish(
            db, name="customer.project.linked", organization_id=organization_id, actor_id=actor_id,
            payload={"customer_id": customer.id, "company_name": customer.company_name, "project_id": project_id},
            flush=False,
        )
        await self._timeline(
            db, organization_id=organization_id, customer_id=customer_id,
            event="customer.project.linked", title=f"Project linked — {customer.company_name}",
            detail=f"project_id={project_id}", actor_id=actor_id, flush=False,
        )
        await db.flush()
        return {"customer_id": customer.id, "project_id": project_id, "kind": link.kind}

    async def unlink_project(self, db: AsyncSession, *, organization_id: str, customer_id: str, project_id: str) -> bool:
        link = (
            await db.execute(
                select(CustomerProjectLink).where(
                    CustomerProjectLink.organization_id == organization_id,
                    CustomerProjectLink.customer_id == customer_id,
                    CustomerProjectLink.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            return False
        await db.delete(link)
        await db.flush()
        return True

    async def link_meeting(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                           meeting_id: str, kind: str = "status", actor_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        link = (
            await db.execute(
                select(CustomerMeetingLink).where(
                    CustomerMeetingLink.organization_id == organization_id,
                    CustomerMeetingLink.customer_id == customer_id,
                    CustomerMeetingLink.meeting_id == meeting_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            link = CustomerMeetingLink(
                organization_id=organization_id, customer_id=customer_id, meeting_id=meeting_id,
                kind=kind if kind in MEETING_KINDS else "status",
            )
            db.add(link)
            await db.flush()
        else:
            link.kind = kind
        customer.last_activity_at = utcnow()
        await _event_bus.publish(
            db, name="customer.meeting.linked", organization_id=organization_id, actor_id=actor_id,
            payload={"customer_id": customer.id, "company_name": customer.company_name, "meeting_id": meeting_id},
            flush=False,
        )
        await self._timeline(
            db, organization_id=organization_id, customer_id=customer_id,
            event="customer.meeting.linked", title=f"Meeting linked — {customer.company_name}",
            detail=f"meeting_id={meeting_id}", actor_id=actor_id, flush=False,
        )
        await db.flush()
        return {"customer_id": customer.id, "meeting_id": meeting_id, "kind": link.kind}

    async def link_document(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                            document_id: str, kind: str = "other", actor_id: Optional[str] = None) -> Optional[dict[str, Any]]:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return None
        link = (
            await db.execute(
                select(CustomerDocumentLink).where(
                    CustomerDocumentLink.organization_id == organization_id,
                    CustomerDocumentLink.customer_id == customer_id,
                    CustomerDocumentLink.document_id == document_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            link = CustomerDocumentLink(
                organization_id=organization_id, customer_id=customer_id, document_id=document_id,
                kind=kind if kind in DOC_KINDS else "other",
            )
            db.add(link)
            await db.flush()
        else:
            link.kind = kind
        customer.last_activity_at = utcnow()
        await _event_bus.publish(
            db, name="customer.document.linked", organization_id=organization_id, actor_id=actor_id,
            payload={"customer_id": customer.id, "company_name": customer.company_name, "document_id": document_id},
            flush=False,
        )
        await db.flush()
        return {"customer_id": customer.id, "document_id": document_id, "kind": link.kind}

    async def unlink_document(self, db: AsyncSession, *, organization_id: str, customer_id: str, document_id: str) -> bool:
        link = (
            await db.execute(
                select(CustomerDocumentLink).where(
                    CustomerDocumentLink.organization_id == organization_id,
                    CustomerDocumentLink.customer_id == customer_id,
                    CustomerDocumentLink.document_id == document_id,
                )
            )
        ).scalar_one_or_none()
        if link is None:
            return False
        await db.delete(link)
        await db.flush()
        return True

    def _project_link_dict(self, link: CustomerProjectLink) -> dict[str, Any]:
        return {"id": link.id, "project_id": link.project_id, "kind": link.kind, "status": link.status}

    def _meeting_link_dict(self, link: CustomerMeetingLink) -> dict[str, Any]:
        return {"id": link.id, "meeting_id": link.meeting_id, "kind": link.kind}

    def _document_link_dict(self, link: CustomerDocumentLink) -> dict[str, Any]:
        return {"id": link.id, "document_id": link.document_id, "kind": link.kind}

    # ------------------------------------------------------------------ account team

    async def _account_team(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> list[dict[str, Any]]:
        from app.models.portal import AccountTeam

        rows = await db.execute(
            select(AccountTeam).where(
                AccountTeam.organization_id == organization_id, AccountTeam.customer_id == customer_id
            )
        )
        result = []
        for member in rows.scalars().all():
            employee = await db.get(Employee, member.employee_id) if member.employee_id else None
            result.append({
                "id": member.id, "employee_id": member.employee_id,
                "employee_name": employee.full_name if employee else None,
                "role": member.role, "is_primary": member.is_primary,
            })
        return result

    # ------------------------------------------------------------------ timeline

    async def _timeline(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                        event: str, title: str, detail: Optional[str] = None,
                        actor_id: Optional[str] = None, payload: Optional[dict[str, Any]] = None,
                        flush: bool = True) -> None:
        db.add(CustomerTimeline(
            organization_id=organization_id, customer_id=customer_id, event=event,
            title=title, detail=detail, actor_id=actor_id, payload=payload or {},
        ))
        if flush:
            await db.flush()

    async def add_timeline(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                           event: str, title: str, detail: Optional[str] = None,
                           actor_id: Optional[str] = None) -> bool:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer is None:
            return False
        await self._timeline(db, organization_id=organization_id, customer_id=customer_id,
                             event=event, title=title, detail=detail, actor_id=actor_id)
        return True

    async def timeline(self, db: AsyncSession, *, organization_id: str, customer_id: str,
                       limit: int = 50) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(CustomerTimeline).where(
                CustomerTimeline.organization_id == organization_id, CustomerTimeline.customer_id == customer_id
            ).order_by(CustomerTimeline.created_at.desc()).limit(limit)
        )
        result = []
        for entry in rows.scalars().all():
            result.append({
                "id": entry.id, "event": entry.event, "title": entry.title, "detail": entry.detail,
                "actor_id": entry.actor_id, "payload": entry.payload or {},
                "created_at": ensure_aware(entry.created_at).isoformat() if entry.created_at else None,
            })
        return result

    # ------------------------------------------------------------------ health hooks

    async def set_last_activity(self, db: AsyncSession, *, organization_id: str, customer_id: str) -> None:
        customer = await self.get(db, organization_id=organization_id, customer_id=customer_id)
        if customer:
            customer.last_activity_at = utcnow()
            await db.flush()


customer_service = CustomerService()
