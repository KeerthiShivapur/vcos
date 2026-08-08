"""Procurement service (Phase 13 — Finance & Business Operations).

Purchase requests flow through manager → finance → procurement → vendor;
approved requests become purchase orders that track delivery and consume
budget. AI checks policy fit and recommends vendors.
"""

import logging
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware, utcnow
from app.events.event_bus import EventBus
from app.finance.parse import to_date
from app.models.finance import Budget, PurchaseOrder, PurchaseRequest, Vendor

logger = logging.getLogger("vcos.finance.procurement")

_event_bus = EventBus()

REQUEST_CATEGORIES = [
    "laptop", "monitor", "software", "furniture", "services", "cloud",
    "training", "equipment", "marketing", "other",
]
REQUEST_STATUSES = [
    "draft", "submitted", "manager_approved", "finance_approved", "approved",
    "rejected", "cancelled", "ordered",
]
ORDER_STATUSES = ["draft", "issued", "accepted", "partially_delivered", "delivered", "closed", "cancelled"]


class ProcurementService:
    # ------------------------------------------------------------ requests

    async def create_request(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        estimated_cost = float(data.get("estimated_cost") or 0)
        if estimated_cost < 0:
            raise ValueError("estimated_cost cannot be negative")
        category = data.get("category", "other")
        if category not in REQUEST_CATEGORIES:
            raise ValueError(f"Invalid category: {category}")
        request = PurchaseRequest(
            organization_id=organization_id,
            employee_id=data.get("employee_id") or actor_id,
            title=title,
            description=data.get("description"),
            category=category,
            quantity=int(data.get("quantity") or 1),
            estimated_cost=estimated_cost,
            currency=data.get("currency") or "USD",
            vendor_name=data.get("vendor_name"),
            vendor_id=data.get("vendor_id"),
            project_id=data.get("project_id"),
            budget_id=data.get("budget_id"),
            status="submitted",
            approver_id=data.get("approver_id"),
            attributes=data.get("attributes") or {},
        )
        db.add(request)
        await db.flush()
        request.policy_flags = await self._check_request_policy(db, request, organization_id=organization_id)
        await db.flush()
        await _event_bus.publish(
            db, name="purchase.requested", organization_id=organization_id, actor_id=actor_id,
            payload={"purchase_request_id": request.id, "title": request.title,
                     "estimated_cost": request.estimated_cost},
            flush=False,
        )
        return await self._request_dict(db, request, organization_id=organization_id)

    async def get_request(self, db: AsyncSession, *, organization_id: str, request_id: str) -> Optional[PurchaseRequest]:
        row = await db.execute(
            select(PurchaseRequest).where(
                PurchaseRequest.organization_id == organization_id, PurchaseRequest.id == request_id
            )
        )
        return row.scalar_one_or_none()

    async def detail_request(self, db: AsyncSession, *, organization_id: str, request_id: str) -> Optional[dict[str, Any]]:
        request = await self.get_request(db, organization_id=organization_id, request_id=request_id)
        if request is None:
            return None
        return await self._request_dict(db, request, organization_id=organization_id)

    async def list_requests(
        self, db: AsyncSession, *, organization_id: str,
        status: Optional[str] = None, category: Optional[str] = None,
        employee_id: Optional[str] = None, project_id: Optional[str] = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = select(PurchaseRequest).where(PurchaseRequest.organization_id == organization_id)
        if status:
            query = query.where(PurchaseRequest.status == status)
        if category:
            query = query.where(PurchaseRequest.category == category)
        if employee_id:
            query = query.where(PurchaseRequest.employee_id == employee_id)
        if project_id:
            query = query.where(PurchaseRequest.project_id == project_id)
        rows = await db.execute(query.order_by(PurchaseRequest.created_at.desc()).limit(limit))
        result = []
        for request in rows.scalars().all():
            result.append(await self._request_dict(db, request, organization_id=organization_id))
        return result

    async def decide_request(
        self, db: AsyncSession, *, organization_id: str, request: PurchaseRequest,
        decision: str, note: Optional[str] = None, actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if request.status in ("rejected", "cancelled", "ordered", "approved"):
            raise ValueError("Request has already been decided")
        if decision not in ("approve", "reject", "cancel"):
            raise ValueError("Invalid decision")
        if decision == "approve":
            if request.status in ("submitted",):
                request.status = "manager_approved"
                event = "purchase.manager_approved"
            elif request.status == "manager_approved":
                request.status = "approved"
                request.approver_id = actor_id or request.approver_id
                request.approved_at = utcnow()
                event = "purchase.approved"
            else:
                raise ValueError("Request must be manager-approved before finance approval")
        elif decision == "reject":
            request.status = "rejected"
            request.rejection_reason = note
            event = "purchase.rejected"
        else:
            request.status = "cancelled"
            event = "purchase.cancelled"
        await db.flush()
        await _event_bus.publish(
            db, name=event, organization_id=organization_id, actor_id=actor_id,
            payload={"purchase_request_id": request.id, "title": request.title, "note": note},
            flush=False,
        )
        return await self._request_dict(db, request, organization_id=organization_id)

    async def _check_request_policy(
        self, db: AsyncSession, request: PurchaseRequest, *, organization_id: str,
    ) -> dict[str, Any]:
        flags: dict[str, Any] = {}
        if request.estimated_cost and request.estimated_cost >= 2000:
            flags["high_value"] = {"threshold": 2000, "level": "medium"}
        if request.budget_id:
            from app.finance.budget_service import budget_service
            budget = await budget_service.get(db, organization_id=organization_id, budget_id=request.budget_id)
            if budget and (budget.remaining_amount or 0) < (request.estimated_cost or 0):
                flags["budget_shortfall"] = {
                    "remaining": budget.remaining_amount, "level": "high",
                }
        if request.category in ("laptop", "equipment") and request.quantity and request.quantity > 5:
            flags["bulk_purchase"] = {"quantity": request.quantity, "level": "low"}
        return flags

    # ------------------------------------------------------------- orders

    async def create_order(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        title = (data.get("title") or "").strip()
        request_id = data.get("purchase_request_id")
        vendor_id = data.get("vendor_id")
        if request_id:
            request = await self.get_request(db, organization_id=organization_id, request_id=request_id)
            if request is None:
                raise ValueError("Invalid purchase_request_id reference")
            request.status = "ordered"
            title = title or request.title
            vendor_id = vendor_id or request.vendor_id
            project_id = request.project_id
            budget_id = request.budget_id
        else:
            project_id = data.get("project_id")
            budget_id = data.get("budget_id")
        if not title:
            raise ValueError("title is required")
        order = PurchaseOrder(
            organization_id=organization_id,
            purchase_request_id=request_id,
            vendor_id=vendor_id,
            project_id=project_id,
            po_number=(data.get("po_number") or "").strip() or await self._next_po_number(db, organization_id),
            title=title,
            total_amount=float(data.get("total_amount") or 0),
            currency=data.get("currency") or "USD",
            status="issued",
            issued_at=utcnow(),
            expected_delivery_at=to_date(data.get("expected_delivery_at")),
            external_reference=data.get("external_reference"),
            attributes=data.get("attributes") or {},
        )
        db.add(order)
        await db.flush()
        if budget_id:
            from app.finance.budget_service import budget_service
            budget = await budget_service.get(db, organization_id=organization_id, budget_id=budget_id)
            if budget:
                await budget_service._refresh_usage(db, budget, organization_id=organization_id)
        await _event_bus.publish(
            db, name="purchase.ordered", organization_id=organization_id, actor_id=actor_id,
            payload={"purchase_order_id": order.id, "po_number": order.po_number, "title": order.title},
            flush=False,
        )
        return await self._order_dict(db, order, organization_id=organization_id)

    async def get_order(self, db: AsyncSession, *, organization_id: str, order_id: str) -> Optional[PurchaseOrder]:
        row = await db.execute(
            select(PurchaseOrder).where(PurchaseOrder.organization_id == organization_id, PurchaseOrder.id == order_id)
        )
        return row.scalar_one_or_none()

    async def detail_order(self, db: AsyncSession, *, organization_id: str, order_id: str) -> Optional[dict[str, Any]]:
        order = await self.get_order(db, organization_id=organization_id, order_id=order_id)
        if order is None:
            return None
        return await self._order_dict(db, order, organization_id=organization_id)

    async def list_orders(
        self, db: AsyncSession, *, organization_id: str,
        status: Optional[str] = None, vendor_id: Optional[str] = None, limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = select(PurchaseOrder).where(PurchaseOrder.organization_id == organization_id)
        if status:
            query = query.where(PurchaseOrder.status == status)
        if vendor_id:
            query = query.where(PurchaseOrder.vendor_id == vendor_id)
        rows = await db.execute(query.order_by(PurchaseOrder.created_at.desc()).limit(limit))
        result = []
        for order in rows.scalars().all():
            result.append(await self._order_dict(db, order, organization_id=organization_id))
        return result

    async def update_order(
        self, db: AsyncSession, *, organization_id: str, order: PurchaseOrder, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        if order.status in ("closed", "cancelled"):
            raise ValueError("Order is closed or cancelled")
        if "status" in data:
            new_status = data["status"]
            if new_status not in ORDER_STATUSES:
                raise ValueError(f"Invalid order status: {new_status}")
            if new_status == "delivered":
                order.delivered_at = utcnow()
            order.status = new_status
        if "expected_delivery_at" in data:
            order.expected_delivery_at = to_date(data.get("expected_delivery_at"))
        if "external_reference" in data:
            order.external_reference = data.get("external_reference")
        if "total_amount" in data:
            order.total_amount = float(data["total_amount"] or 0)
        await db.flush()
        if data.get("status") == "delivered":
            await _event_bus.publish(
                db, name="purchase.delivered", organization_id=organization_id, actor_id=actor_id,
                payload={"purchase_order_id": order.id, "po_number": order.po_number},
                flush=False,
            )
        return await self._order_dict(db, order, organization_id=organization_id)

    async def delete_request(self, db: AsyncSession, *, organization_id: str, request: PurchaseRequest) -> None:
        await db.delete(request)

    async def _next_po_number(self, db: AsyncSession, organization_id: str) -> str:
        count = (
            await db.execute(
                select(func.count(PurchaseOrder.id)).where(PurchaseOrder.organization_id == organization_id)
            )
        ).scalar_one()
        from app.core.timeutils import utcnow as _now

        return f"PO-{_now().year}-{count + 1:04d}"

    async def _request_dict(self, db: AsyncSession, request: PurchaseRequest, *, organization_id: str) -> dict[str, Any]:
        employee = None
        project = None
        budget = None
        vendor = None
        if request.employee_id:
            from app.models.employee import Employee
            employee = await db.get(Employee, request.employee_id)
        if request.project_id:
            from app.models.project import Project
            project = await db.get(Project, request.project_id)
        if request.budget_id:
            budget = await db.get(Budget, request.budget_id)
        if request.vendor_id:
            vendor = await db.get(Vendor, request.vendor_id)
        return {
            "id": request.id,
            "employee_id": request.employee_id,
            "employee_name": employee.full_name if employee else None,
            "title": request.title,
            "description": request.description,
            "category": request.category,
            "quantity": request.quantity,
            "estimated_cost": request.estimated_cost,
            "currency": request.currency,
            "vendor_name": request.vendor_name,
            "vendor_id": request.vendor_id,
            "vendor_label": vendor.name if vendor else (request.vendor_name or None),
            "project_id": request.project_id,
            "project_name": project.name if project else None,
            "budget_id": request.budget_id,
            "budget_name": budget.name if budget else None,
            "status": request.status,
            "approver_id": request.approver_id,
            "approved_at": ensure_aware(request.approved_at).isoformat() if request.approved_at else None,
            "rejection_reason": request.rejection_reason,
            "policy_flags": request.policy_flags or {},
            "created_at": ensure_aware(request.created_at).isoformat() if request.created_at else None,
        }

    async def _order_dict(self, db: AsyncSession, order: PurchaseOrder, *, organization_id: str) -> dict[str, Any]:
        vendor = None
        project = None
        if order.vendor_id:
            vendor = await db.get(Vendor, order.vendor_id)
        if order.project_id:
            from app.models.project import Project
            project = await db.get(Project, order.project_id)
        return {
            "id": order.id,
            "purchase_request_id": order.purchase_request_id,
            "vendor_id": order.vendor_id,
            "vendor_name": vendor.name if vendor else None,
            "project_id": order.project_id,
            "project_name": project.name if project else None,
            "po_number": order.po_number,
            "title": order.title,
            "total_amount": order.total_amount,
            "currency": order.currency,
            "status": order.status,
            "issued_at": ensure_aware(order.issued_at).isoformat() if order.issued_at else None,
            "expected_delivery_at": order.expected_delivery_at.isoformat() if order.expected_delivery_at else None,
            "delivered_at": ensure_aware(order.delivered_at).isoformat() if order.delivered_at else None,
            "external_reference": order.external_reference,
            "created_at": ensure_aware(order.created_at).isoformat() if order.created_at else None,
        }


procurement_service = ProcurementService()
