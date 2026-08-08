"""Payroll integration service (Phase 11.10 — Payroll Integration).

VCOS does NOT re-implement payroll. It keeps a loose coupling to external
providers (SAP, Oracle, Workday, ADP, Gusto or a local system) via provider
references and payroll run records that carry the external reference id and
the payload handed to the provider. Nothing here computes salary.
"""

import logging
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.timeutils import utcnow
from app.hr.parse import to_date
from app.models.hr import PayrollProvider, PayrollRun

logger = logging.getLogger("vcos.hr.payroll")

PROVIDER_VENDORS = ["sap", "oracle", "workday", "adp", "gusto", "local", "custom"]
RUN_STATUSES = ["pending", "synced", "failed"]


class PayrollService:
    # ------------------------------------------------------------------ providers

    async def create_provider(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> PayrollProvider:
        provider = PayrollProvider(
            organization_id=organization_id,
            name=data["name"],
            provider=data.get("provider", "custom") if data.get("provider") in PROVIDER_VENDORS else "custom",
            config=data.get("config") or {},
            is_active=bool(data.get("is_active", True)),
        )
        db.add(provider)
        await db.flush()
        return provider

    async def list_providers(self, db: AsyncSession, *, organization_id: str, active_only: bool = False) -> list[PayrollProvider]:
        query = select(PayrollProvider).where(PayrollProvider.organization_id == organization_id)
        if active_only:
            query = query.where(PayrollProvider.is_active.is_(True))
        return (await db.execute(query.order_by(PayrollProvider.name))).scalars().all()

    async def update_provider(self, db: AsyncSession, *, organization_id: str, provider_id: str, data: dict[str, Any]) -> Optional[PayrollProvider]:
        provider = (
            await db.execute(
                select(PayrollProvider).where(PayrollProvider.organization_id == organization_id, PayrollProvider.id == provider_id)
            )
        ).scalar_one_or_none()
        if provider is None:
            return None
        for field in ("name", "provider", "config", "is_active"):
            if field in data:
                setattr(provider, field, data[field])
        await db.flush()
        return provider

    # ------------------------------------------------------------------ runs

    async def create_run(self, db: AsyncSession, *, organization_id: str, data: dict[str, Any]) -> PayrollRun:
        run = PayrollRun(
            organization_id=organization_id,
            provider_id=data.get("provider_id"),
            period_start=to_date(data.get("period_start")),
            period_end=to_date(data.get("period_end")),
            status=data.get("status", "pending") if data.get("status") in RUN_STATUSES else "pending",
            employee_count=int(data.get("employee_count", 0)),
            gross_amount=float(data.get("gross_amount", 0.0)),
            reference_id=data.get("reference_id"),
            payload=data.get("payload") or {},
        )
        if run.status == "synced":
            run.synced_at = utcnow()
        db.add(run)
        await db.flush()
        return run

    async def mark_synced(self, db: AsyncSession, *, organization_id: str, run_id: str, reference_id: Optional[str] = None) -> Optional[PayrollRun]:
        run = (
            await db.execute(
                select(PayrollRun).where(PayrollRun.organization_id == organization_id, PayrollRun.id == run_id)
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        run.status = "synced"
        run.synced_at = utcnow()
        if reference_id:
            run.reference_id = reference_id
        await db.flush()
        return run

    async def mark_failed(self, db: AsyncSession, *, organization_id: str, run_id: str) -> Optional[PayrollRun]:
        run = (
            await db.execute(
                select(PayrollRun).where(PayrollRun.organization_id == organization_id, PayrollRun.id == run_id)
            )
        ).scalar_one_or_none()
        if run is None:
            return None
        run.status = "failed"
        await db.flush()
        return run

    async def list_runs(
        self, db: AsyncSession, *, organization_id: str, provider_id: Optional[str] = None,
        status: Optional[str] = None, limit: int = 50,
    ) -> list[dict[str, Any]]:
        query = select(PayrollRun).where(PayrollRun.organization_id == organization_id)
        if provider_id:
            query = query.where(PayrollRun.provider_id == provider_id)
        if status:
            query = query.where(PayrollRun.status == status)
        rows = await db.execute(query.order_by(PayrollRun.created_at.desc()).limit(limit))
        result = []
        for run in rows.scalars().all():
            provider = await db.get(PayrollProvider, run.provider_id) if run.provider_id else None
            result.append(
                {
                    "id": run.id,
                    "provider_id": run.provider_id,
                    "provider_name": provider.name if provider else None,
                    "provider_vendor": provider.provider if provider else None,
                    "period_start": run.period_start.isoformat() if run.period_start else None,
                    "period_end": run.period_end.isoformat() if run.period_end else None,
                    "status": run.status,
                    "employee_count": run.employee_count,
                    "gross_amount": run.gross_amount,
                    "reference_id": run.reference_id,
                    "synced_at": run.synced_at.isoformat() if run.synced_at else None,
                }
            )
        return result

    # ------------------------------------------------------------------ overview

    async def overview(self, db: AsyncSession, *, organization_id: str) -> dict[str, Any]:
        providers = await self.list_providers(db, organization_id=organization_id)
        runs = await self.list_runs(db, organization_id=organization_id, limit=500)
        return {
            "providers": len(providers),
            "active_providers": sum(1 for provider in providers if provider.is_active),
            "runs": {
                "total": len(runs),
                "synced": sum(1 for run in runs if run["status"] == "synced"),
                "pending": sum(1 for run in runs if run["status"] == "pending"),
                "failed": sum(1 for run in runs if run["status"] == "failed"),
            },
            "last_run": runs[0] if runs else None,
            "latest_synced_gross": next((run["gross_amount"] for run in runs if run["status"] == "synced"), 0.0),
        }


payroll_service = PayrollService()
