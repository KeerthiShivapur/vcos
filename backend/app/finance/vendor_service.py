"""Vendor service (Phase 13 — Finance & Business Operations).

Vendors hold contacts, contracts, invoices, purchase orders, payments and
performance data. AI computes vendor risk and health from spend, delivery
and contract signals.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.events.event_bus import EventBus
from app.finance.parse import clamp_score
from app.models.finance import (
    Invoice,
    Payment,
    PurchaseOrder,
    Vendor,
    VendorContract,
)

logger = logging.getLogger("vcos.finance.vendor")

_event_bus = EventBus()

VENDOR_KINDS = ["supplier", "vendor", "consultant", "contractor", "partner"]
VENDOR_STATUSES = ["active", "inactive", "blacklisted"]


class VendorService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> Vendor:
        name = (data.get("name") or "").strip()
        if not name:
            raise ValueError("name is required")
        kind = data.get("kind", "vendor")
        if kind not in VENDOR_KINDS:
            raise ValueError(f"Invalid kind: {kind}")
        vendor = Vendor(
            organization_id=organization_id,
            name=name,
            kind=kind,
            contact_name=data.get("contact_name"),
            email=data.get("email"),
            phone=data.get("phone"),
            website=data.get("website"),
            country=data.get("country"),
            tax_id=data.get("tax_id"),
            payment_terms=data.get("payment_terms"),
            rating=int(data["rating"]) if data.get("rating") else None,
            status=data.get("status", "active") if data.get("status") in VENDOR_STATUSES else "active",
            description=data.get("description"),
            attributes=data.get("attributes") or {},
        )
        db.add(vendor)
        await db.flush()
        await _event_bus.publish(
            db, name="vendor.created", organization_id=organization_id, actor_id=actor_id,
            payload={"vendor_id": vendor.id, "name": vendor.name, "kind": vendor.kind},
            flush=False,
        )
        return vendor

    async def get(self, db: AsyncSession, *, organization_id: str, vendor_id: str) -> Optional[Vendor]:
        row = await db.execute(
            select(Vendor).where(Vendor.organization_id == organization_id, Vendor.id == vendor_id)
        )
        return row.scalar_one_or_none()

    async def detail(self, db: AsyncSession, *, organization_id: str, vendor_id: str) -> Optional[dict[str, Any]]:
        vendor = await self.get(db, organization_id=organization_id, vendor_id=vendor_id)
        if vendor is None:
            return None
        base = vendor.to_dict()
        base["risk"] = await self.risk_profile(db, organization_id=organization_id, vendor_id=vendor.id)
        contracts = (
            await db.execute(
                select(VendorContract).where(
                    VendorContract.organization_id == organization_id, VendorContract.vendor_id == vendor_id
                )
            )
        ).scalars().all()
        orders = (
            await db.execute(
                select(PurchaseOrder).where(
                    PurchaseOrder.organization_id == organization_id, PurchaseOrder.vendor_id == vendor_id
                )
            )
        ).scalars().all()
        invoices = (
            await db.execute(
                select(Invoice).where(
                    Invoice.organization_id == organization_id, Invoice.vendor_id == vendor_id
                )
            )
        ).scalars().all()
        payments = (
            await db.execute(
                select(Payment).where(
                    Payment.organization_id == organization_id, Payment.vendor_id == vendor_id
                )
            )
        ).scalars().all()
        base["contracts"] = [{
            "id": c.id, "title": c.title, "value": c.value, "currency": c.currency,
            "effective_from": c.effective_from.isoformat() if c.effective_from else None,
            "expires_at": c.expires_at.isoformat() if c.expires_at else None,
            "renewal_status": c.renewal_status, "status": c.status,
        } for c in contracts]
        base["orders"] = [{
            "id": o.id, "po_number": o.po_number, "title": o.title,
            "total_amount": o.total_amount, "status": o.status,
        } for o in orders]
        base["invoices"] = [{
            "id": i.id, "invoice_number": i.invoice_number, "title": i.title,
            "amount": i.amount, "status": i.status, "due_at": i.due_at.isoformat() if i.due_at else None,
        } for i in invoices]
        base["payments"] = [{
            "id": p.id, "amount": p.amount, "method": p.method, "status": p.status,
            "paid_at": ensure_aware(p.paid_at).isoformat() if p.paid_at else None,
        } for p in payments]
        base["total_spend"] = round(sum(p.amount or 0 for p in payments if p.status == "completed"), 2)
        return base

    async def list_vendors(
        self, db: AsyncSession, *, organization_id: str,
        kind: Optional[str] = None, status: Optional[str] = None, search: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(Vendor).where(Vendor.organization_id == organization_id)
        if kind:
            query = query.where(Vendor.kind == kind)
        if status:
            query = query.where(Vendor.status == status)
        if search:
            pattern = f"%{search.lower()}%"
            query = query.where(func.lower(Vendor.name).like(pattern))
        rows = await db.execute(query.order_by(Vendor.name))
        return [v.to_dict() for v in rows.scalars().all()]

    async def update(
        self, db: AsyncSession, *, organization_id: str, vendor: Vendor, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> Vendor:
        for field in ("name", "contact_name", "email", "phone", "website", "country", "tax_id",
                      "payment_terms", "description"):
            if field in data:
                setattr(vendor, field, data.get(field))
        if "kind" in data and data["kind"] in VENDOR_KINDS:
            vendor.kind = data["kind"]
        if "status" in data and data["status"] in VENDOR_STATUSES:
            vendor.status = data["status"]
        if "rating" in data:
            vendor.rating = int(data["rating"]) if data.get("rating") else None
        await db.flush()
        return vendor

    async def delete(self, db: AsyncSession, *, organization_id: str, vendor: Vendor) -> None:
        await db.delete(vendor)

    async def risk_profile(
        self, db: AsyncSession, *, organization_id: str, vendor_id: str,
    ) -> dict[str, Any]:
        vendor = await self.get(db, organization_id=organization_id, vendor_id=vendor_id)
        if vendor is None:
            return {"level": "unknown", "score": 0, "factors": {}}
        score = 50
        factors: dict[str, Any] = {}
        if vendor.status == "blacklisted":
            score += 40
            factors["status"] = {"level": "high"}
        overdue = (
            await db.execute(
                select(func.count(Invoice.id)).where(
                    Invoice.organization_id == organization_id,
                    Invoice.vendor_id == vendor_id,
                    Invoice.status == "overdue",
                )
            )
        ).scalar_one()
        late_payments = (
            await db.execute(
                select(func.count(Payment.id)).where(
                    Payment.organization_id == organization_id,
                    Payment.vendor_id == vendor_id,
                    Payment.status == "failed",
                )
            )
        ).scalar_one()
        if overdue:
            score += 15
            factors["overdue_invoices"] = {"count": int(overdue or 0), "level": "medium"}
        if late_payments:
            score += 10
            factors["late_payments"] = {"count": int(late_payments or 0), "level": "medium"}
        expiring = (
            await db.execute(
                select(func.count(VendorContract.id)).where(
                    VendorContract.organization_id == organization_id,
                    VendorContract.vendor_id == vendor_id,
                    VendorContract.renewal_status.in_(("due_soon", "overdue")),
                )
            )
        ).scalar_one()
        if expiring:
            score += 10
            factors["expiring_contracts"] = {"count": int(expiring or 0), "level": "low"}
        if vendor.rating and vendor.rating <= 2:
            score += 10
            factors["low_rating"] = {"rating": vendor.rating, "level": "low"}
        score = clamp_score(score, 50)
        if score >= 75:
            level = "high"
        elif score >= 60:
            level = "medium"
        else:
            level = "low"
        return {"level": level, "score": score, "factors": factors}

    async def summary(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        vendors = (
            await db.execute(select(Vendor).where(Vendor.organization_id == organization_id))
        ).scalars().all()
        by_kind: dict[str, int] = {}
        by_status: dict[str, int] = {}
        high_risk = 0
        for vendor in vendors:
            by_kind[vendor.kind] = by_kind.get(vendor.kind, 0) + 1
            by_status[vendor.status] = by_status.get(vendor.status, 0) + 1
            risk = await self.risk_profile(db, organization_id=organization_id, vendor_id=vendor.id)
            if risk["level"] in ("medium", "high"):
                high_risk += 1
        return {
            "total": len(vendors),
            "active": by_status.get("active", 0),
            "by_kind": by_kind,
            "by_status": by_status,
            "high_risk": high_risk,
        }


vendor_service = VendorService()
