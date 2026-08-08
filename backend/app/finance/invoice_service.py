"""Invoice & payment service (Phase 13 — Finance & Business Operations).

VCOS stores invoice references and workflow state; the external accounting
system remains the source of truth. Covers payable (vendor) and receivable
(customer) invoices plus the payment trail.
"""

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.event_bus import EventBus
from app.finance.parse import to_date
from app.models.finance import Invoice, Payment, Vendor

logger = logging.getLogger("vcos.finance.invoice")

_event_bus = EventBus()

INVOICE_STATUSES = ["draft", "pending", "approved", "paid", "overdue", "void", "cancelled"]
PAYMENT_METHODS = ["bank_transfer", "credit_card", "cheque", "cash", "erp_sync", "other"]
PAYMENT_STATUSES = ["scheduled", "pending", "completed", "failed"]


class InvoiceService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        amount = float(data.get("amount") or 0)
        if amount <= 0:
            raise ValueError("amount must be greater than zero")
        direction = data.get("direction", "payable")
        if direction not in ("payable", "receivable"):
            raise ValueError("direction must be payable or receivable")
        if direction == "payable" and not data.get("vendor_id"):
            raise ValueError("vendor_id is required for payable invoices")
        if direction == "receivable" and not data.get("customer_id"):
            raise ValueError("customer_id is required for receivable invoices")
        invoice = Invoice(
            organization_id=organization_id,
            direction=direction,
            vendor_id=data.get("vendor_id"),
            customer_id=data.get("customer_id"),
            project_id=data.get("project_id"),
            invoice_number=data.get("invoice_number"),
            reference_number=data.get("reference_number"),
            title=title,
            amount=amount,
            tax_amount=float(data.get("tax_amount") or 0),
            currency=data.get("currency") or "USD",
            issued_at=to_date(data.get("issued_at")),
            due_at=to_date(data.get("due_at")),
            status=data.get("status", "pending") if data.get("status") in INVOICE_STATUSES else "pending",
            external_system=data.get("external_system"),
            external_id=data.get("external_id"),
            attributes=data.get("attributes") or {},
        )
        db.add(invoice)
        await db.flush()
        await self._apply_overdue(db, invoice)
        await _event_bus.publish(
            db, name="invoice.received", organization_id=organization_id, actor_id=actor_id,
            payload={"invoice_id": invoice.id, "title": invoice.title, "amount": invoice.amount,
                     "direction": invoice.direction},
            flush=False,
        )
        return await self._dict(db, invoice, organization_id=organization_id)

    async def get(self, db: AsyncSession, *, organization_id: str, invoice_id: str) -> Optional[Invoice]:
        row = await db.execute(
            select(Invoice).where(Invoice.organization_id == organization_id, Invoice.id == invoice_id)
        )
        return row.scalar_one_or_none()

    async def detail(self, db: AsyncSession, *, organization_id: str, invoice_id: str) -> Optional[dict[str, Any]]:
        invoice = await self.get(db, organization_id=organization_id, invoice_id=invoice_id)
        if invoice is None:
            return None
        base = await self._dict(db, invoice, organization_id=organization_id)
        payments = (
            await db.execute(
                select(Payment).where(
                    Payment.organization_id == organization_id, Payment.invoice_id == invoice_id
                ).order_by(Payment.created_at.asc())
            )
        ).scalars().all()
        base["payments"] = [{
            "id": p.id, "amount": p.amount, "method": p.method, "status": p.status,
            "reference": p.reference, "paid_at": ensure_aware(p.paid_at).isoformat() if p.paid_at else None,
            "external_id": p.external_id,
        } for p in payments]
        base["paid_total"] = round(sum(p.amount for p in payments if p.status == "completed"), 2)
        return base

    async def list_invoices(
        self, db: AsyncSession, *, organization_id: str,
        direction: Optional[str] = None, status: Optional[str] = None,
        vendor_id: Optional[str] = None, customer_id: Optional[str] = None,
        project_id: Optional[str] = None, limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = select(Invoice).where(Invoice.organization_id == organization_id)
        if direction:
            query = query.where(Invoice.direction == direction)
        if status:
            query = query.where(Invoice.status == status)
        if vendor_id:
            query = query.where(Invoice.vendor_id == vendor_id)
        if customer_id:
            query = query.where(Invoice.customer_id == customer_id)
        if project_id:
            query = query.where(Invoice.project_id == project_id)
        rows = await db.execute(query.order_by(Invoice.created_at.desc()).limit(limit))
        result = []
        for invoice in rows.scalars().all():
            result.append(await self._dict(db, invoice, organization_id=organization_id))
        return result

    async def update(
        self, db: AsyncSession, *, organization_id: str, invoice: Invoice, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if invoice.status in ("paid", "void", "cancelled"):
            raise ValueError("Invoice is closed")
        for field in ("title", "invoice_number", "reference_number", "external_system", "external_id"):
            if field in data:
                setattr(invoice, field, data.get(field))
        if "amount" in data:
            invoice.amount = float(data["amount"] or 0)
        if "tax_amount" in data:
            invoice.tax_amount = float(data["tax_amount"] or 0)
        if "currency" in data and data.get("currency"):
            invoice.currency = data["currency"]
        if "issued_at" in data:
            invoice.issued_at = to_date(data.get("issued_at"))
        if "due_at" in data:
            invoice.due_at = to_date(data.get("due_at"))
        if "status" in data and data["status"] in INVOICE_STATUSES:
            invoice.status = data["status"]
            if data["status"] == "paid" and not invoice.paid_at:
                invoice.paid_at = utcnow()
        if "project_id" in data:
            invoice.project_id = data.get("project_id")
        await db.flush()
        await self._apply_overdue(db, invoice)
        return await self._dict(db, invoice, organization_id=organization_id)

    async def delete(self, db: AsyncSession, *, organization_id: str, invoice: Invoice) -> None:
        await db.delete(invoice)

    # ------------------------------------------------------------- payments

    async def create_payment(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        invoice_id = data.get("invoice_id")
        amount = float(data.get("amount") or 0)
        if amount <= 0:
            raise ValueError("amount must be greater than zero")
        invoice = None
        if invoice_id:
            invoice = await self.get(db, organization_id=organization_id, invoice_id=invoice_id)
            if invoice is None:
                raise ValueError("Invalid invoice_id reference")
        payment = Payment(
            organization_id=organization_id,
            invoice_id=invoice_id,
            vendor_id=data.get("vendor_id") or (invoice.vendor_id if invoice else None),
            amount=amount,
            currency=data.get("currency") or "USD",
            method=data.get("method", "bank_transfer") if data.get("method") in PAYMENT_METHODS else "bank_transfer",
            status=data.get("status", "pending") if data.get("status") in PAYMENT_STATUSES else "pending",
            reference=data.get("reference"),
            external_id=data.get("external_id"),
        )
        db.add(payment)
        await db.flush()
        if payment.status == "completed":
            payment.paid_at = utcnow()
            await db.flush()
            if invoice:
                await self._on_payment_completed(db, invoice, organization_id=organization_id, actor_id=actor_id)
        return {
            "id": payment.id,
            "invoice_id": payment.invoice_id,
            "vendor_id": payment.vendor_id,
            "amount": payment.amount,
            "currency": payment.currency,
            "method": payment.method,
            "status": payment.status,
            "reference": payment.reference,
            "external_id": payment.external_id,
            "paid_at": ensure_aware(payment.paid_at).isoformat() if payment.paid_at else None,
            "created_at": ensure_aware(payment.created_at).isoformat() if payment.created_at else None,
        }

    async def list_payments(
        self, db: AsyncSession, *, organization_id: str,
        status: Optional[str] = None, vendor_id: Optional[str] = None, limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = select(Payment).where(Payment.organization_id == organization_id)
        if status:
            query = query.where(Payment.status == status)
        if vendor_id:
            query = query.where(Payment.vendor_id == vendor_id)
        rows = await db.execute(query.order_by(Payment.created_at.desc()).limit(limit))
        result = []
        for payment in rows.scalars().all():
            invoice = None
            if payment.invoice_id:
                invoice = await self.get(db, organization_id=organization_id, invoice_id=payment.invoice_id)
            result.append({
                "id": payment.id,
                "invoice_id": payment.invoice_id,
                "invoice_title": invoice.title if invoice else None,
                "vendor_id": payment.vendor_id,
                "amount": payment.amount,
                "currency": payment.currency,
                "method": payment.method,
                "status": payment.status,
                "reference": payment.reference,
                "paid_at": ensure_aware(payment.paid_at).isoformat() if payment.paid_at else None,
                "created_at": ensure_aware(payment.created_at).isoformat() if payment.created_at else None,
            })
        return result

    async def update_payment(
        self, db: AsyncSession, *, organization_id: str, payment: Payment, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if "status" in data and data["status"] in PAYMENT_STATUSES:
            payment.status = data["status"]
            if data["status"] == "completed" and not payment.paid_at:
                payment.paid_at = utcnow()
                invoice = None
                if payment.invoice_id:
                    invoice = await self.get(db, organization_id=organization_id, invoice_id=payment.invoice_id)
                if invoice:
                    await self._on_payment_completed(db, invoice, organization_id=organization_id, actor_id=actor_id)
        if "reference" in data:
            payment.reference = data.get("reference")
        if "external_id" in data:
            payment.external_id = data.get("external_id")
        await db.flush()
        return await self.list_payments(db, organization_id=organization_id, limit=1) and {
            "id": payment.id, "status": payment.status, "amount": payment.amount,
            "paid_at": ensure_aware(payment.paid_at).isoformat() if payment.paid_at else None,
        }

    async def _on_payment_completed(
        self, db: AsyncSession, invoice: Invoice, *, organization_id: str, actor_id: Optional[str] = None,
    ) -> None:
        if invoice.status != "paid":
            invoice.status = "paid"
            invoice.paid_at = utcnow()
            await db.flush()
        await _event_bus.publish(
            db, name="payment.completed", organization_id=organization_id, actor_id=actor_id,
            payload={"invoice_id": invoice.id, "invoice_number": invoice.invoice_number,
                     "amount": invoice.amount, "direction": invoice.direction},
            flush=False,
        )

    # -------------------------------------------------------------- overdue

    async def _apply_overdue(self, db: AsyncSession, invoice: Invoice) -> None:
        if invoice.status == "pending" and invoice.due_at and invoice.due_at < date.today():
            invoice.status = "overdue"

    async def mark_overdue(self, db: AsyncSession, *, organization_id: str) -> int:
        rows = await db.execute(
            select(Invoice).where(
                Invoice.organization_id == organization_id,
                Invoice.status == "pending",
                Invoice.due_at.isnot(None),
                Invoice.due_at < date.today(),
            )
        )
        count = 0
        for invoice in rows.scalars().all():
            invoice.status = "overdue"
            count += 1
        if count:
            await db.flush()
        return count

    async def summary(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        await self.mark_overdue(db, organization_id=organization_id)
        invoices = (
            await db.execute(select(Invoice).where(Invoice.organization_id == organization_id))
        ).scalars().all()
        payable = [i for i in invoices if i.direction == "payable"]
        receivable = [i for i in invoices if i.direction == "receivable"]
        overdue = [i for i in invoices if i.status == "overdue"]
        payable_due = sum(i.amount for i in payable if i.status in ("pending", "overdue"))
        receivable_due = sum(i.amount for i in receivable if i.status in ("pending", "overdue"))
        paid_payable = sum(i.amount for i in payable if i.status == "paid")
        paid_receivable = sum(i.amount for i in receivable if i.status == "paid")
        return {
            "total": len(invoices),
            "payable": {
                "count": len(payable),
                "due": round(payable_due, 2),
                "paid": round(paid_payable, 2),
                "overdue": len([i for i in payable if i.status == "overdue"]),
            },
            "receivable": {
                "count": len(receivable),
                "due": round(receivable_due, 2),
                "paid": round(paid_receivable, 2),
                "overdue": len([i for i in receivable if i.status == "overdue"]),
            },
            "overdue": len(overdue),
        }

    async def _dict(self, db: AsyncSession, invoice: Invoice, *, organization_id: str) -> dict[str, Any]:
        vendor = None
        customer = None
        project = None
        if invoice.vendor_id:
            vendor = await db.get(Vendor, invoice.vendor_id)
        if invoice.customer_id:
            from app.models.customer import Customer
            customer = await db.get(Customer, invoice.customer_id)
        if invoice.project_id:
            from app.models.project import Project
            project = await db.get(Project, invoice.project_id)
        return {
            "id": invoice.id,
            "direction": invoice.direction,
            "vendor_id": invoice.vendor_id,
            "vendor_name": vendor.name if vendor else None,
            "customer_id": invoice.customer_id,
            "customer_name": customer.company_name if customer else None,
            "project_id": invoice.project_id,
            "project_name": project.name if project else None,
            "invoice_number": invoice.invoice_number,
            "reference_number": invoice.reference_number,
            "title": invoice.title,
            "amount": invoice.amount,
            "tax_amount": invoice.tax_amount,
            "currency": invoice.currency,
            "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
            "due_at": invoice.due_at.isoformat() if invoice.due_at else None,
            "status": invoice.status,
            "paid_at": ensure_aware(invoice.paid_at).isoformat() if invoice.paid_at else None,
            "payment_reference": invoice.payment_reference,
            "external_system": invoice.external_system,
            "external_id": invoice.external_id,
            "synced_at": ensure_aware(invoice.synced_at).isoformat() if invoice.synced_at else None,
            "created_at": ensure_aware(invoice.created_at).isoformat() if invoice.created_at else None,
        }


invoice_service = InvoiceService()
