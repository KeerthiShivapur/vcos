"""Asset service (Phase 11.8 — Assets & Equipment).

Tracks the full asset lifecycle — laptop, phone, monitor, software,
license, access card — from purchase to assignment, return, maintenance
and loss, with org-wide summaries for the HR dashboard.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.events.event_bus import EventBus
from app.hr.parse import to_date
from app.models.employee import Employee
from app.models.hr import EmployeeAsset

logger = logging.getLogger("vcos.hr.assets")

_event_bus = EventBus()

CATEGORIES = ["laptop", "phone", "monitor", "software", "license", "access_card", "vehicle", "other"]
STATUSES = ["available", "assigned", "returned", "lost", "maintenance"]


class AssetService:
    async def create_asset(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> EmployeeAsset:
        asset = EmployeeAsset(
            organization_id=organization_id,
            employee_id=data.get("employee_id"),
            name=data["name"],
            category=data.get("category", "other") if data.get("category") in CATEGORIES else "other",
            serial_number=data.get("serial_number"),
            purchase_date=to_date(data.get("purchase_date")),
            warranty_until=to_date(data.get("warranty_until")),
            status=data.get("status", "available") if data.get("status") in STATUSES else "available",
            condition=data.get("condition"),
            notes=data.get("notes"),
        )
        if asset.status == "assigned" and asset.employee_id:
            asset.assigned_at = utcnow()
            asset.assigned_by = data.get("assigned_by")
            await self._publish_assigned(db, asset)
        db.add(asset)
        await db.flush()
        return asset

    async def assign(
        self, db: AsyncSession, *, organization_id: str, asset_id: str, employee_id: str, assigned_by: Optional[str] = None,
    ) -> Optional[EmployeeAsset]:
        asset = (
            await db.execute(
                select(EmployeeAsset).where(EmployeeAsset.organization_id == organization_id, EmployeeAsset.id == asset_id)
            )
        ).scalar_one_or_none()
        if asset is None or asset.status not in ("available", "returned"):
            return None
        asset.employee_id = employee_id
        asset.status = "assigned"
        asset.assigned_at = utcnow()
        asset.returned_at = None
        asset.assigned_by = assigned_by
        await self._publish_assigned(db, asset)
        await db.flush()
        return asset

    async def _publish_assigned(self, db: AsyncSession, asset: EmployeeAsset) -> None:
        if not asset.employee_id:
            return
        employee = await db.get(Employee, asset.employee_id)
        await _event_bus.publish(
            db,
            name="asset.assigned",
            organization_id=asset.organization_id,
            actor_id=asset.employee_id,
            payload={
                "asset_id": asset.id,
                "employee_id": asset.employee_id,
                "employee_name": employee.full_name if employee else None,
                "name": asset.name,
                "category": asset.category,
            },
            flush=False,
        )

    async def update_status(
        self, db: AsyncSession, *, organization_id: str, asset_id: str, status: str, notes: Optional[str] = None,
    ) -> Optional[EmployeeAsset]:
        if status not in STATUSES:
            raise ValueError(f"invalid asset status: {status}")
        asset = (
            await db.execute(
                select(EmployeeAsset).where(EmployeeAsset.organization_id == organization_id, EmployeeAsset.id == asset_id)
            )
        ).scalar_one_or_none()
        if asset is None:
            return None
        asset.status = status
        if notes is not None:
            asset.notes = notes
        if status == "assigned":
            asset.assigned_at = utcnow()
        if status in ("returned", "lost", "maintenance"):
            asset.returned_at = utcnow()
            if status == "returned":
                asset.employee_id = None
        await db.flush()
        return asset

    async def list_assets(
        self, db: AsyncSession, *, organization_id: str,
        employee_id: Optional[str] = None, status: Optional[str] = None, category: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        query = select(EmployeeAsset).where(EmployeeAsset.organization_id == organization_id)
        if employee_id:
            query = query.where(EmployeeAsset.employee_id == employee_id)
        if status:
            query = query.where(EmployeeAsset.status == status)
        if category:
            query = query.where(EmployeeAsset.category == category)
        rows = await db.execute(query.order_by(EmployeeAsset.created_at.desc()))
        result = []
        for asset in rows.scalars().all():
            employee = await db.get(Employee, asset.employee_id) if asset.employee_id else None
            result.append(
                {
                    "id": asset.id,
                    "employee_id": asset.employee_id,
                    "employee_name": employee.full_name if employee else None,
                    "name": asset.name,
                    "category": asset.category,
                    "serial_number": asset.serial_number,
                    "purchase_date": asset.purchase_date.isoformat() if asset.purchase_date else None,
                    "warranty_until": asset.warranty_until.isoformat() if asset.warranty_until else None,
                    "status": asset.status,
                    "condition": asset.condition,
                    "notes": asset.notes,
                    "assigned_at": asset.assigned_at.isoformat() if asset.assigned_at else None,
                    "returned_at": asset.returned_at.isoformat() if asset.returned_at else None,
                }
            )
        return result

    async def summary(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        assets = (
            await db.execute(select(EmployeeAsset).where(EmployeeAsset.organization_id == organization_id))
        ).scalars().all()
        by_status: dict[str, int] = {}
        by_category: dict[str, int] = {}
        for asset in assets:
            by_status[asset.status] = by_status.get(asset.status, 0) + 1
            by_category[asset.category] = by_category.get(asset.category, 0) + 1
        return {
            "total": len(assets),
            "assigned": by_status.get("assigned", 0),
            "available": by_status.get("available", 0),
            "in_maintenance": by_status.get("maintenance", 0),
            "lost": by_status.get("lost", 0),
            "returned": by_status.get("returned", 0),
            "by_status": by_status,
            "by_category": by_category,
        }


asset_service = AssetService()
