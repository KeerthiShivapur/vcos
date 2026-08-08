"""Vendor contract service (Phase 13 — Finance & Business Operations).

Tracks vendor contracts, renewals and obligations so AI can remind teams
about expiries and vendor risk.
"""

import logging
from datetime import date
from typing import Any, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.events.event_bus import EventBus
from app.finance.parse import to_date
from app.models.finance import Vendor, VendorContract

logger = logging.getLogger("vcos.finance.vendor_contract")

_event_bus = EventBus()


class VendorContractService:
    async def create(
        self, db: AsyncSession, *, organization_id: str, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("title is required")
        vendor_id = data.get("vendor_id")
        if not vendor_id:
            raise ValueError("vendor_id is required")
        from app.finance.vendor_service import vendor_service
        vendor = await vendor_service.get(db, organization_id=organization_id, vendor_id=vendor_id)
        if vendor is None:
            raise ValueError("Invalid vendor_id reference")
        contract = VendorContract(
            organization_id=organization_id,
            vendor_id=vendor_id,
            title=title,
            value=float(data["value"]) if data.get("value") is not None else None,
            currency=data.get("currency") or "USD",
            effective_from=to_date(data.get("effective_from")),
            expires_at=to_date(data.get("expires_at")),
            auto_renew=bool(data.get("auto_renew", False)),
            status=data.get("status", "active") if data.get("status") in ("active", "expiring", "expired", "terminated") else "active",
            notes=data.get("notes"),
        )
        self._apply_renewal_status(contract)
        db.add(contract)
        await db.flush()
        await _event_bus.publish(
            db, name="vendor_contract.created", organization_id=organization_id, actor_id=actor_id,
            payload={"vendor_contract_id": contract.id, "title": contract.title, "vendor_id": vendor_id},
            flush=False,
        )
        return await self._dict(db, contract, organization_id=organization_id)

    async def get(self, db: AsyncSession, *, organization_id: str, contract_id: str) -> Optional[VendorContract]:
        row = await db.execute(
            select(VendorContract).where(
                VendorContract.organization_id == organization_id, VendorContract.id == contract_id
            )
        )
        return row.scalar_one_or_none()

    async def list_contracts(
        self, db: AsyncSession, *, organization_id: str,
        vendor_id: Optional[str] = None, status: Optional[str] = None,
        expiring_soon: bool = False, limit: int = 200,
    ) -> list[dict[str, Any]]:
        query = select(VendorContract).where(VendorContract.organization_id == organization_id)
        if vendor_id:
            query = query.where(VendorContract.vendor_id == vendor_id)
        if status:
            query = query.where(VendorContract.status == status)
        if expiring_soon:
            query = query.where(VendorContract.renewal_status.in_(("due_soon", "overdue")))
        rows = await db.execute(query.order_by(VendorContract.created_at.desc()).limit(limit))
        result = []
        for contract in rows.scalars().all():
            self._apply_renewal_status(contract)
            result.append(await self._dict(db, contract, organization_id=organization_id))
        if expiring_soon:
            result.sort(key=lambda item: item.get("days_left") or 9999)
        return result

    async def update(
        self, db: AsyncSession, *, organization_id: str, contract: VendorContract, data: dict[str, Any],
        actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        for field in ("title", "notes"):
            if field in data:
                setattr(contract, field, data.get(field))
        if "value" in data:
            contract.value = float(data["value"]) if data.get("value") is not None else None
        if "currency" in data and data.get("currency"):
            contract.currency = data["currency"]
        if "effective_from" in data:
            contract.effective_from = to_date(data.get("effective_from"))
        if "expires_at" in data:
            contract.expires_at = to_date(data.get("expires_at"))
        if "auto_renew" in data:
            contract.auto_renew = bool(data.get("auto_renew"))
        if "status" in data and data["status"] in ("active", "expiring", "expired", "terminated"):
            contract.status = data["status"]
        if "vendor_id" in data and data.get("vendor_id"):
            contract.vendor_id = data["vendor_id"]
        self._apply_renewal_status(contract)
        await db.flush()
        return await self._dict(db, contract, organization_id=organization_id)

    async def renew(
        self, db: AsyncSession, *, organization_id: str, contract: VendorContract,
        data: dict[str, Any], actor_id: Optional[str] = None,
    ) -> dict[str, Any]:
        expires_at = to_date(data.get("expires_at"))
        if not expires_at:
            raise ValueError("expires_at is required to renew")
        contract.expires_at = expires_at
        if "value" in data and data.get("value") is not None:
            contract.value = float(data["value"])
        contract.status = "active"
        self._apply_renewal_status(contract)
        await db.flush()
        await _event_bus.publish(
            db, name="vendor_contract.renewed", organization_id=organization_id, actor_id=actor_id,
            payload={"vendor_contract_id": contract.id, "expires_at": expires_at.isoformat()},
            flush=False,
        )
        return await self._dict(db, contract, organization_id=organization_id)

    async def delete(self, db: AsyncSession, *, organization_id: str, contract: VendorContract) -> None:
        await db.delete(contract)

    def _apply_renewal_status(self, contract: VendorContract) -> None:
        if contract.status == "terminated":
            contract.renewal_status = "not_due"
            return
        today = date.today()
        if not contract.expires_at:
            contract.renewal_status = "not_due"
            return
        days = (contract.expires_at - today).days
        if days < 0:
            contract.renewal_status = "overdue"
            contract.status = "expired" if contract.status != "expired" else contract.status
        elif days <= 90:
            contract.renewal_status = "due_soon"
            contract.status = "expiring" if contract.status == "active" else contract.status
        else:
            contract.renewal_status = "not_due"

    async def _dict(self, db: AsyncSession, contract: VendorContract, *, organization_id: str) -> dict[str, Any]:
        vendor = None
        if contract.vendor_id:
            vendor = await db.get(Vendor, contract.vendor_id)
        days_left = None
        if contract.expires_at:
            days_left = (contract.expires_at - date.today()).days
        return {
            "id": contract.id,
            "vendor_id": contract.vendor_id,
            "vendor_name": vendor.name if vendor else None,
            "title": contract.title,
            "value": contract.value,
            "currency": contract.currency,
            "effective_from": contract.effective_from.isoformat() if contract.effective_from else None,
            "expires_at": contract.expires_at.isoformat() if contract.expires_at else None,
            "days_left": days_left,
            "renewal_status": contract.renewal_status,
            "auto_renew": contract.auto_renew,
            "status": contract.status,
            "notes": contract.notes,
            "created_at": ensure_aware(contract.created_at).isoformat() if contract.created_at else None,
        }


vendor_contract_service = VendorContractService()
