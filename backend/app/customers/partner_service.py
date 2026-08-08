"""Partner & vendor service (Phase 12.9/12.10 — External Ecosystem).

Partners: technology, business, consultants, resellers, distributors,
universities and government. Vendors additionally carry contracts, payment
terms, ratings and compliance posture.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.customers.parse import to_date
from app.events.event_bus import EventBus
from app.models.employee import Employee
from app.models.partner import Partner, PartnerContact, PartnerContractLink

logger = logging.getLogger("vcos.customers.partner")

_event_bus = EventBus()

KINDS = ["partner", "vendor", "consultant", "supplier", "reseller", "distributor", "government", "university"]
PARTNER_TYPES = ["technology", "business", "consulting", "referral", "integration", "channel"]
STATUSES = ["active", "inactive", "suspended"]


class PartnerService:
    async def create(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
                     actor_id: Optional[str] = None) -> Partner:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        kind = data.get("kind", "partner") if data.get("kind") in KINDS else "partner"
        partner = Partner(
            organization_id=organization_id,
            kind=kind,
            name=name,
            website=data.get("website"),
            industry=data.get("industry"),
            country=data.get("country"),
            description=data.get("description"),
            partner_type=data.get("partner_type") if data.get("partner_type") in PARTNER_TYPES else None,
            status=data.get("status", "active") if data.get("status") in STATUSES else "active",
            owner_id=data.get("owner_id"),
            started_at=to_date(data.get("started_at")),
            performance_score=data.get("performance_score"),
            rating=data.get("rating"),
            payment_terms=data.get("payment_terms"),
            attributes=data.get("metadata") or data.get("attributes"),
        )
        db.add(partner)
        await db.flush()
        await _event_bus.publish(
            db, name="partner.added", organization_id=organization_id, actor_id=actor_id,
            payload={"partner_id": partner.id, "name": partner.name, "kind": partner.kind},
            flush=False,
        )
        await db.flush()
        return partner

    async def get(self, db: AsyncSession, *, organization_id: str, partner_id: str) -> Optional[Partner]:
        return (
            await db.execute(
                select(Partner).where(Partner.organization_id == organization_id, Partner.id == partner_id)
            )
        ).scalar_one_or_none()

    async def update(self, db: AsyncSession, *, organization_id: str, partner_id: str,
                     data: dict[str, Any]) -> Optional[Partner]:
        partner = await self.get(db, organization_id=organization_id, partner_id=partner_id)
        if partner is None:
            return None
        for field in ("name", "website", "industry", "country", "description", "owner_id",
                      "performance_score", "rating", "payment_terms", "attributes"):
            if field in data and data[field] is not None:
                setattr(partner, field, data[field])
        if data.get("kind") in KINDS:
            partner.kind = data["kind"]
        if data.get("partner_type") in PARTNER_TYPES:
            partner.partner_type = data["partner_type"]
        if data.get("status") in STATUSES:
            partner.status = data["status"]
        if "started_at" in data:
            partner.started_at = to_date(data["started_at"])
        await db.flush()
        return partner

    async def delete(self, db: AsyncSession, *, organization_id: str, partner_id: str) -> bool:
        partner = await self.get(db, organization_id=organization_id, partner_id=partner_id)
        if partner is None:
            return False
        await db.delete(partner)
        await db.flush()
        return True

    async def list_partners(self, db: AsyncSession, *, organization_id: str, kind: Optional[str] = None,
                            status: Optional[str] = None, search: Optional[str] = None,
                            ) -> list[dict[str, Any]]:
        query = select(Partner).where(Partner.organization_id == organization_id)
        if kind:
            query = query.where(Partner.kind == kind)
        if status:
            query = query.where(Partner.status == status)
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(
                or_(func.lower(Partner.name).like(pattern), func.lower(Partner.industry).like(pattern))
            )
        rows = await db.execute(query.order_by(Partner.updated_at.desc()))
        result = []
        for partner in rows.scalars().all():
            owner = await db.get(Employee, partner.owner_id) if partner.owner_id else None
            result.append(self._dict(partner, owner_name=owner.full_name if owner else None))
        return result

    def _dict(self, partner: Partner, owner_name: Optional[str] = None) -> dict[str, Any]:
        return {
            "id": partner.id, "kind": partner.kind, "name": partner.name, "website": partner.website,
            "industry": partner.industry, "country": partner.country, "description": partner.description,
            "partner_type": partner.partner_type, "status": partner.status, "owner_id": partner.owner_id,
            "owner_name": owner_name,
            "started_at": partner.started_at.isoformat() if partner.started_at else None,
            "performance_score": partner.performance_score, "rating": partner.rating,
            "payment_terms": partner.payment_terms,
            "created_at": ensure_aware(partner.created_at).isoformat() if partner.created_at else None,
            "updated_at": ensure_aware(partner.updated_at).isoformat() if partner.updated_at else None,
        }

    # ------------------------------------------------------------------ partner contacts

    async def add_contact(self, db: AsyncSession, *, organization_id: str, partner_id: str,
                          data: dict[str, Any]) -> Optional[PartnerContact]:
        partner = await self.get(db, organization_id=organization_id, partner_id=partner_id)
        if partner is None:
            return None
        if data.get("is_primary"):
            await db.execute(
                PartnerContact.__table__.update()
                .where(PartnerContact.organization_id == organization_id, PartnerContact.partner_id == partner_id)
                .values(is_primary=False)
            )
        contact = PartnerContact(
            organization_id=organization_id, partner_id=partner_id,
            name=(data.get("name") or "").strip() or "Unnamed",
            role=data.get("role"), email=data.get("email"), phone=data.get("phone"),
            is_primary=bool(data.get("is_primary", False)),
        )
        db.add(contact)
        await db.flush()
        return contact

    async def list_contacts(self, db: AsyncSession, *, organization_id: str, partner_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(PartnerContact).where(
                PartnerContact.organization_id == organization_id, PartnerContact.partner_id == partner_id
            )
        )
        return [{
            "id": c.id, "partner_id": c.partner_id, "name": c.name, "role": c.role,
            "email": c.email, "phone": c.phone, "is_primary": c.is_primary,
        } for c in rows.scalars().all()]

    async def delete_contact(self, db: AsyncSession, *, organization_id: str, partner_id: str, contact_id: str) -> bool:
        contact = (
            await db.execute(
                select(PartnerContact).where(
                    PartnerContact.organization_id == organization_id,
                    PartnerContact.partner_id == partner_id,
                    PartnerContact.id == contact_id,
                )
            )
        ).scalar_one_or_none()
        if contact is None:
            return False
        await db.delete(contact)
        await db.flush()
        return True

    # ------------------------------------------------------------------ partner contracts

    async def link_contract(self, db: AsyncSession, *, organization_id: str, partner_id: str,
                            contract_id: str) -> Optional[PartnerContractLink]:
        partner = await self.get(db, organization_id=organization_id, partner_id=partner_id)
        if partner is None:
            return None
        link = PartnerContractLink(organization_id=organization_id, partner_id=partner_id, contract_id=contract_id)
        db.add(link)
        await db.flush()
        return link

    async def list_contract_links(self, db: AsyncSession, *, organization_id: str, partner_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(PartnerContractLink).where(
                PartnerContractLink.organization_id == organization_id, PartnerContractLink.partner_id == partner_id
            )
        )
        return [{"id": link.id, "contract_id": link.contract_id} for link in rows.scalars().all()]

    async def summary(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        partners = (
            await db.execute(select(Partner).where(Partner.organization_id == organization_id))
        ).scalars().all()
        by_kind: dict[str, int] = {}
        active = 0
        for partner in partners:
            by_kind[partner.kind] = by_kind.get(partner.kind, 0) + 1
            if partner.status == "active":
                active += 1
        return {"total": len(partners), "active": active, "by_kind": by_kind}


partner_service = PartnerService()
