"""Finance / ERP integration service (Phase 13 — Finance & Business Operations).

Manages FinanceIntegration connections to external accounting platforms
(SAP, Oracle, NetSuite, Dynamics 365, QuickBooks, Xero, Tally, Zoho Books)
and CSV-based bulk imports for expenses, invoices and purchase orders.
External systems remain the source of truth for bookkeeping; VCOS mirrors
workflow data with external_system/external_id/synced_at references.
"""

import csv
import io
import logging
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import ensure_aware
from app.finance.parse import to_date
from app.models.finance import Expense, FinanceIntegration, Invoice, PurchaseOrder, Vendor

logger = logging.getLogger("vcos.finance.integrations")

ERP_PLATFORMS = ["SAP", "Oracle", "NetSuite", "Dynamics 365", "QuickBooks", "Xero", "Tally", "Zoho Books"]
PLATFORM_BY_KEY = {platform.lower(): platform for platform in ERP_PLATFORMS}
INTEGRATION_TYPES = ["rest", "webhook", "scheduled_sync", "message_queue", "csv_import"]
INTEGRATION_STATUSES = ["enabled", "disabled", "syncing", "error"]


class FinanceIntegrationService:
    async def create(self, db: AsyncSession, *, organization_id: str, platform: str,
                     display_name: str, config: dict[str, Any], actor_id: Optional[str] = None) -> dict[str, Any]:
        provider = PLATFORM_BY_KEY.get((platform or "").strip().lower())
        if provider is None:
            raise ValueError(f"Unsupported platform. Choose from: {', '.join(ERP_PLATFORMS)}")
        integration_type = config.get("integration_type", "rest")
        if integration_type not in INTEGRATION_TYPES:
            integration_type = "rest"
        integration = FinanceIntegration(
            organization_id=organization_id,
            provider=provider,
            name=display_name or provider,
            integration_type=integration_type,
            status="enabled",
            config={k: v for k, v in config.items() if k != "integration_type"},
            last_synced_at=None,
        )
        db.add(integration)
        await db.flush()
        await self._emit(db, organization_id=organization_id, actor_id=actor_id, integration=integration, event="integration.created")
        return await self._dict(integration)

    async def list_integrations(self, db: AsyncSession, *, organization_id: str) -> list[dict[str, Any]]:
        rows = await db.execute(
            select(FinanceIntegration).where(FinanceIntegration.organization_id == organization_id).order_by(FinanceIntegration.created_at)
        )
        return [await self._dict(item) for item in rows.scalars().all()]

    async def get(self, db: AsyncSession, *, organization_id: str, integration_id: str) -> dict[str, Any]:
        row = await self._get_or_raise(db, organization_id=organization_id, integration_id=integration_id)
        return await self._dict(row)

    async def update(self, db: AsyncSession, *, organization_id: str, integration_id: str,
                     data: dict[str, Any], actor_id: Optional[str] = None) -> dict[str, Any]:
        row = await self._get_or_raise(db, organization_id=organization_id, integration_id=integration_id)
        if "name" in data and data.get("name"):
            row.name = data["name"]
        if "integration_type" in data and data["integration_type"] in INTEGRATION_TYPES:
            row.integration_type = data["integration_type"]
        if "status" in data and data["status"] in INTEGRATION_STATUSES:
            row.status = data["status"]
        if "config" in data:
            row.config = data["config"]
        await db.flush()
        await self._emit(db, organization_id=organization_id, actor_id=actor_id, integration=row, event="integration.updated")
        return await self._dict(row)

    async def delete(self, db: AsyncSession, *, organization_id: str, integration_id: str,
                     actor_id: Optional[str] = None) -> None:
        row = await self._get_or_raise(db, organization_id=organization_id, integration_id=integration_id)
        await self._emit(db, organization_id=organization_id, actor_id=actor_id, integration=row, event="integration.deleted")
        await db.delete(row)
        await db.flush()

    async def sync(self, db: AsyncSession, *, organization_id: str, integration_id: str,
                   actor_id: Optional[str] = None, dry_run: bool = True) -> dict[str, Any]:
        row = await self._get_or_raise(db, organization_id=organization_id, integration_id=integration_id)
        discovered = self._discover_external_data(row)
        if dry_run:
            return {
                "integration_id": row.id,
                "provider": row.provider,
                "dry_run": True,
                "discovered": discovered,
                "message": "Dry-run sync complete. Re-run with dry_run=false to ingest.",
            }
        imported = 0
        errors: list[str] = []
        for item in discovered:
            try:
                ingested = await self._ingest(db, organization_id=organization_id, integration=row, item=item)
                if ingested:
                    imported += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{item.get('type')}: {exc}")
        row.last_synced_at = date.today()
        await db.flush()
        await self._emit(db, organization_id=organization_id, actor_id=actor_id, integration=row, event="integration.synced")
        return {
            "integration_id": row.id,
            "provider": row.provider,
            "dry_run": False,
            "imported": imported,
            "errors": errors,
        }

    async def import_csv(self, db: AsyncSession, *, organization_id: str, kind: str,
                         content: str, actor_id: Optional[str] = None) -> dict[str, Any]:
        kind = kind.lower()
        if kind not in ("expenses", "invoices", "purchase_orders"):
            raise ValueError("kind must be one of: expenses, invoices, purchase_orders")
        reader = csv.DictReader(io.StringIO(content))
        rows = list(reader)
        if not rows:
            raise ValueError("CSV is empty or missing a header row")
        imported = 0
        errors: list[str] = []
        for index, row in enumerate(rows, start=2):
            try:
                if kind == "expenses":
                    await self._import_expense(db, organization_id=organization_id, row=row)
                elif kind == "invoices":
                    await self._import_invoice(db, organization_id=organization_id, row=row)
                else:
                    await self._import_purchase_order(db, organization_id=organization_id, row=row)
                imported += 1
            except Exception as exc:  # noqa: BLE001
                errors.append(f"Row {index}: {exc}")
        await self._emit(db, organization_id=organization_id, actor_id=actor_id, integration=row,
                         event="import.completed", payload={"imported": imported, "errors": len(errors), "kind": kind})
        return {"kind": kind, "imported": imported, "failed": len(errors), "errors": errors}

    async def _import_expense(self, db: AsyncSession, *, organization_id: str, row: dict[str, str]) -> None:
        amount = float(row.get("amount", "").strip() or 0)
        if amount <= 0:
            raise ValueError("amount must be positive")
        expense = Expense(
            organization_id=organization_id,
            employee_id=row.get("employee_id") or None,
            project_id=row.get("project_id") or None,
            expense_type=row.get("expense_type") or "miscellaneous",
            amount=amount,
            currency=row.get("currency") or "USD",
            incurred_at=to_date(row.get("incurred_at")),
            merchant=row.get("merchant"),
            description=row.get("description") or "Imported from CSV",
            status="submitted",
            policy_flags={"flagged": False},
            attributes={"external_system": "CSV", "external_id": row.get("external_id") or None, "synced_at": date.today().isoformat()},
        )
        db.add(expense)
        await db.flush()

    async def _import_invoice(self, db: AsyncSession, *, organization_id: str, row: dict[str, str]) -> None:
        amount = float(row.get("amount", "").strip() or 0)
        if amount <= 0:
            raise ValueError("amount must be positive")
        direction = row.get("direction", "payable").lower()
        if direction not in ("payable", "receivable"):
            raise ValueError("direction must be payable or receivable")
        invoice = Invoice(
            organization_id=organization_id,
            direction=direction,
            invoice_number=row.get("invoice_number") or None,
            title=row.get("title") or row.get("issuer_name") or "Imported invoice",
            vendor_id=row.get("vendor_id") or None,
            customer_id=row.get("customer_id") or None,
            project_id=row.get("project_id") or None,
            amount=amount,
            currency=row.get("currency") or "USD",
            issued_at=to_date(row.get("issued_at")),
            due_at=to_date(row.get("due_at")),
            status=row.get("status", "pending") if row.get("status", "pending") in ("pending", "approved", "paid", "overdue") else "pending",
            external_system="CSV",
            external_id=row.get("external_id") or None,
            synced_at=date.today(),
        )
        db.add(invoice)
        await db.flush()

    async def _import_purchase_order(self, db: AsyncSession, *, organization_id: str, row: dict[str, str]) -> None:
        total = float(row.get("total_amount", "").strip() or 0)
        if total <= 0:
            raise ValueError("total_amount must be positive")
        purchase_order = PurchaseOrder(
            organization_id=organization_id,
            po_number=row.get("po_number") or f"IMPORT-{row.get('external_id') or ''}" or "IMPORT",
            vendor_id=row.get("vendor_id") or None,
            title=row.get("title") or row.get("vendor") or "Imported order",
            total_amount=total,
            currency=row.get("currency") or "USD",
            status=row.get("status", "issued") if row.get("status", "issued") in ("issued", "accepted", "partially_delivered", "delivered", "closed", "cancelled") else "issued",
            issued_at=to_date(row.get("issued_at")),
            external_reference=row.get("external_reference") or None,
            attributes={"notes": row.get("notes") or "Imported from CSV"},
        )
        db.add(purchase_order)
        await db.flush()

    def _discover_external_data(self, integration: FinanceIntegration) -> list[dict[str, Any]]:
        config = integration.config or {}
        discovered: list[dict[str, Any]] = []
        for item_type in ("expenses", "invoices", "purchase_orders"):
            count = int(config.get(f"{item_type}_count", 0) or 0)
            for index in range(1, count + 1):
                discovered.append({
                    "type": item_type,
                    "external_id": f"{integration.provider.lower().replace(' ', '-')}-{item_type[:-1]}-{index}",
                    "amount": float(config.get(f"{item_type[:-1]}_{index}_amount", 0) or 0),
                })
        return discovered

    async def _ingest(self, db: AsyncSession, *, organization_id: str, integration: FinanceIntegration,
                      item: dict[str, Any]) -> bool:
        existing_rows = (
            await db.execute(select(Expense).where(Expense.organization_id == organization_id))
        ).scalars().all()
        existing = next(
            (
                expense for expense in existing_rows
                if (expense.attributes or {}).get("external_system") == integration.provider
                and (expense.attributes or {}).get("external_id") == item["external_id"]
            ),
            None,
        )
        if existing is not None:
            return False
        kind = item["type"]
        if kind == "expenses":
            db.add(Expense(
                organization_id=organization_id,
                expense_type="miscellaneous",
                amount=item["amount"],
                currency="USD",
                incurred_at=date.today(),
                description=f"Synced from {integration.provider}",
                status="submitted",
                policy_flags={"flagged": False},
                attributes={"external_system": integration.provider, "external_id": item["external_id"], "synced_at": date.today().isoformat()},
            ))
        elif kind == "invoices":
            db.add(Invoice(
                organization_id=organization_id,
                direction="payable",
                title=f"Invoice from {integration.provider}",
                amount=item["amount"],
                currency="USD",
                issued_at=date.today(),
                due_at=date.today() + timedelta(days=30),
                status="pending",
                external_system=integration.provider,
                external_id=item["external_id"],
                synced_at=date.today(),
            ))
        else:
            db.add(PurchaseOrder(
                organization_id=organization_id,
                po_number=f"{integration.provider[:8].upper()}-{item['external_id'][-8:]}",
                title=f"Order from {integration.provider}",
                total_amount=item["amount"],
                currency="USD",
                status="issued",
                issued_at=date.today(),
                external_reference=item["external_id"],
                attributes={"notes": f"Synced from {integration.provider}"},
            ))
        await db.flush()
        return True

    async def health(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        rows = await self.list_integrations(db, organization_id=organization_id)
        connected = sum(1 for item in rows if item["status"] == "enabled")
        return {
            "total": len(rows),
            "connected": connected,
            "disconnected": len(rows) - connected,
            "last_synced": [item["last_synced_at"] for item in rows if item["last_synced_at"]],
        }

    async def _get_or_raise(self, db: AsyncSession, *, organization_id: str, integration_id: str) -> FinanceIntegration:
        row = (
            await db.execute(
                select(FinanceIntegration).where(
                    FinanceIntegration.id == integration_id,
                    FinanceIntegration.organization_id == organization_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise LookupError("Integration not found")
        return row

    async def _emit(self, db: AsyncSession, *, organization_id: str, actor_id: Optional[str],
                    integration: FinanceIntegration, event: str, payload: Optional[dict[str, Any]] = None) -> None:
        from app.events.event_bus import EventBus

        await EventBus().publish(
            db, name=event, organization_id=organization_id, actor_id=actor_id,
            payload=payload or {"integration_id": integration.id, "provider": integration.provider},
            flush=False,
        )

    async def _dict(self, integration: FinanceIntegration) -> dict[str, Any]:
        config = dict(integration.config or {})
        config.pop("api_key", None)
        config.pop("secret", None)
        return {
            "id": integration.id,
            "provider": integration.provider,
            "name": integration.name,
            "integration_type": integration.integration_type,
            "status": integration.status,
            "config": config,
            "last_synced_at": ensure_aware(integration.last_synced_at).isoformat() if integration.last_synced_at else None,
            "last_error": integration.last_error,
            "created_at": ensure_aware(integration.created_at).isoformat() if integration.created_at else None,
            "updated_at": ensure_aware(integration.updated_at).isoformat() if integration.updated_at else None,
        }


finance_integration_service = FinanceIntegrationService()
